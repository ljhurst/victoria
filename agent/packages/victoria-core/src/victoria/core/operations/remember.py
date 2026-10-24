"""remember(text) — the curation-aware write tool (DESIGN §7).

Internally: search for related pages, ask a cheap model for the edits that
file the note (an exact-text replacement in an existing page, or a new page),
apply them to the page it was shown, write per CONVENTIONS.md, update
index.md and search.db, return a short summary. put_file stays an internal
primitive — never exposed directly to the calling model (DESIGN §7).
"""

import re
from datetime import UTC, datetime

import anthropic

from victoria.core.config import CoreSettings
from victoria.core.integrations import anthropic_client
from victoria.core.observability import logger, timed
from victoria.core.operations import log, page_edits
from victoria.core.operations.models import (
    Create,
    PageAction,
    PageEdits,
    PagePlan,
    RememberResult,
)
from victoria.core.storage import search_index, wiki
from victoria.core.storage.models import IndexEntry, PageContent, PageVersion, WikiPath

_EDITOR_TOOL = {
    "type": "text_editor_20250728",
    "name": page_edits.EDITOR_TOOL_NAME,
    "input_examples": [
        {
            "command": "str_replace",
            "path": "wiki/house/tools.md",
            "old_str": "Bought 2024, Ryobi 18V. Kept in the garage, top shelf.",
            "new_str": (
                "Bought 2024, Ryobi 18V. Kept in the garage, top shelf.\n"
                "- 2026-09-01: replaced battery."
            ),
        }
    ],
}

_FILE_NOTE_TOOL = {
    "name": page_edits.NOTE_TOOL_NAME,
    "description": "Report what was filed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One sentence describing what was filed and where.",
            },
            "page_getting_large": {
                "type": "boolean",
                "description": (
                    "True if the page now looks like a splitting candidate "
                    "per CONVENTIONS.md — a signal for consolidate, not an action to take now."
                ),
            },
        },
        "required": ["summary"],
    },
}

_SYSTEM_TEMPLATE = """You are Victoria's ingestion step. Your only job is to file a new \
piece of information into the wiki, following these conventions exactly:

{conventions}

The wiki's existing domains are: {domains}. A domain is one broad area of \
life. Use an existing domain (wiki/<domain>/...) when the note is about that \
area. If the note is about a different area of life (vehicles or travel, \
say), start a new domain rather than stretching an existing one to cover it, \
with a short lowercase name, hyphenated if it needs more than one word.

Write every fact the note states and nothing else, tersely and factually, as the Writing style \
section above describes: no background, suggestions, open questions or next \
steps.

How to file it:
- To add to an existing page, call str_replace_based_edit_tool with command \
str_replace. Set old_str to one unique line at the END of the section you are \
adding to (copy it exactly), and new_str to that same line followed by the new \
text. To add a new section, anchor on the last line of the page. Keep every \
other line of the page untouched. new_str adds only facts the note states.
- To start a new page, call str_replace_based_edit_tool with command create \
and file_text set to the whole new page, frontmatter included. file_text holds \
only facts the note states: no suggestions, no ideas for next time, no open \
questions, no "should" or "worth trying".
- Never edit the frontmatter. Ignore the conventions' rule about last-updated: it is \
set for you after your edit, and an edit that changes nothing below the frontmatter \
is rejected. Your edit must add the note's facts to the page text.
- The full text of every related page is already given in the user message, \
so never call view, and never use insert. Call str_replace or create directly.
- Make two tool calls in ONE response, with no text: first file_note (one-sentence \
summary), then the str_replace_based_edit_tool call. Both are needed; neither \
depends on the other's result."""


def _search_terms(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    return " OR ".join(words[:12]) or text


def _domain_headings(index_md: str) -> dict[str, str]:
    headings = re.findall(r"^## (.+?)\s*$", index_md, flags=re.MULTILINE)
    return {_domain_slug(heading): f"## {heading}" for heading in headings}


def _domain_slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def _domain_heading(index_md: str, page_path: str) -> str:
    domain = page_path.split("/")[1]
    return _domain_headings(index_md).get(domain, f"## {domain.replace('-', ' ').title()}")


def _ensure_linked(index_md: str, page_path: str, title: str) -> str:
    if f"({page_path})" in index_md:
        return index_md
    heading = _domain_heading(index_md, page_path)
    link_line = f"- [{title}]({page_path})"
    placeholder = "_(no pages yet — created by `remember` as topics come up)_"

    if heading not in index_md:
        return index_md.rstrip("\n") + f"\n\n{heading}\n\n{link_line}\n"

    head, rest = index_md.split(heading, 1)
    if "\n## " in rest:
        section, tail = rest.split("\n## ", 1)
        tail = "## " + tail
    else:
        section, tail = rest, ""

    entry_lines = [
        line for line in section.splitlines() if line.strip() and line.strip() != placeholder
    ]
    entry_lines.append(link_line)
    new_section = "\n\n" + "\n".join(entry_lines) + "\n\n"

    return head + heading + new_section + tail


def _related_pages(
    bucket: str, index: search_index.SearchIndexSession, text: str
) -> list[PageVersion]:
    hits = index.search(_search_terms(text), limit=3)
    related_pages: list[PageVersion] = []
    for hit in hits:
        try:
            related_pages.append(wiki.get_file_with_etag(bucket, hit.path))
        except Exception:  # noqa: BLE001, S112 — a stale index entry shouldn't block filing
            continue
    return related_pages


def _decide(
    client: anthropic.Anthropic,
    conventions: str,
    domains: list[str],
    related_pages: list[PageContent],
    text: str,
    failure: str | None = None,
) -> PageEdits:
    related_block = (
        "\n\n".join(f"--- existing page: {p.path} ---\n{p.content}" for p in related_pages)
        or "(no related pages found)"
    )
    user_message = (
        f"New note to file:\n{text}\n\nRelated existing pages found via search:\n{related_block}"
    )
    if failure is not None:
        user_message += f"\n\nYour previous edits were rejected: {failure}\nTry again."

    calls = anthropic_client.call_tools(
        client,
        model=anthropic_client.HAIKU_MODEL,
        system=_SYSTEM_TEMPLATE.format(
            conventions=conventions, domains=", ".join(domains) or "(none yet)"
        ),
        user_message=user_message,
        tools=[_EDITOR_TOOL, _FILE_NOTE_TOOL],
    )
    return page_edits.parse_edits(calls)


def _plan_edit(
    bucket: str,
    client: anthropic.Anthropic,
    conventions: str,
    domains: list[str],
    related_pages: list[PageVersion],
    text: str,
) -> PagePlan:
    try:
        return _try_edit(bucket, client, conventions, domains, related_pages, text, None)
    except page_edits.EditError as first:
        logger.warning("edits rejected, retrying", reason=str(first))
        shown = list(related_pages)
        if isinstance(first, page_edits.PageNotShownError):
            shown.append(wiki.get_file_with_etag(bucket, first.path))
        return _try_edit(bucket, client, conventions, domains, shown, text, str(first))


def _try_edit(
    bucket: str,
    client: anthropic.Anthropic,
    conventions: str,
    domains: list[str],
    shown: list[PageVersion],
    text: str,
    failure: str | None,
) -> PagePlan:
    edits = _decide(client, conventions, domains, shown, text, failure)

    first = edits.commands[0]
    base = next((page for page in shown if page.path == first.path), None)
    if base is None and isinstance(first, Create) and wiki.file_exists(bucket, first.path):
        raise page_edits.PageNotShownError(
            first.path, f"{first.path} already exists; update it with str_replace"
        )

    with timed("apply_edits", edits=len(edits.commands)):
        path, action, content = page_edits.apply_edits(
            base, edits.commands, today=datetime.now(UTC).date()
        )

    return PagePlan(
        path=path,
        action=action,
        title=page_edits.page_title(content, path),
        tags=page_edits.page_tags(content),
        content=content,
        base_etag=base.etag if base else None,
        summary=edits.summary,
        page_getting_large=edits.page_getting_large,
    )


def _write_page(bucket: str, index: search_index.SearchIndexSession, plan: PagePlan) -> None:
    wiki.put_file(bucket, plan.path, plan.content, if_match=plan.base_etag)
    index.upsert_page(
        IndexEntry(
            path=plan.path,
            title=plan.title,
            tags=", ".join(plan.tags),
            body=plan.content,
        )
    )


def _link_in_index(bucket: str, index_key: WikiPath, plan: PagePlan) -> None:
    index_page = wiki.get_file_with_etag(bucket, index_key)
    updated_index = _ensure_linked(index_page.content, plan.path, plan.title)
    if updated_index != index_page.content:
        wiki.put_file(bucket, index_key, updated_index, if_match=index_page.etag)


@timed("remember")
def remember(settings: CoreSettings, api_key: str, text: str) -> RememberResult:
    bucket = settings.wiki_bucket
    with timed("read_wiki_context"):
        conventions = wiki.get_file(bucket, settings.wiki_files.conventions).content
        domains = list(_domain_headings(wiki.get_file(bucket, settings.wiki_files.index).content))
    client = anthropic_client.get_client(api_key)

    with search_index.open_session(bucket, settings.search_index.db_key) as index:
        with timed("related_pages"):
            related_pages = _related_pages(bucket, index, text)
        plan = _plan_edit(bucket, client, conventions, domains, related_pages, text)

        with timed("write_page", path=plan.path, action=plan.action.value):
            _write_page(bucket, index, plan)

        if plan.action == PageAction.CREATE:
            with timed("link_in_index"):
                _link_in_index(bucket, settings.wiki_files.index, plan)

    with timed("append_log"):
        log.append(bucket, settings.wiki_files, "remember", f"{plan.path} — {plan.summary}")

    return RememberResult(
        page=plan.path,
        action=plan.action,
        summary=plan.summary,
        page_getting_large=plan.page_getting_large,
    )
