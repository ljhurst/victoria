"""remember(text) — the curation-aware write tool (DESIGN §7).

Internally: search for related pages, ask a cheap model for the edits that
file the note (an exact-text replacement in an existing page, or a new page),
apply them to the page it was shown, write per CONVENTIONS.md, update
index.md and search.db, return a short summary. put_file stays an internal
primitive — never exposed directly to the calling model (DESIGN §7).
"""

import re

import anthropic

from victoria.core import observability
from victoria.core.config import CoreSettings
from victoria.core.integrations import anthropic_client
from victoria.core.observability import timed
from victoria.core.operations.models import RememberResult
from victoria.core.pages import edits, frontmatter, index_links, log
from victoria.core.pages.models import Create, EditedPage, PageAction, PageEdits
from victoria.core.storage import search_index, wiki
from victoria.core.storage.models import IndexEntry, PageContent, PageVersion

_EDITOR_TOOL = {
    "type": "text_editor_20250728",
    "name": edits.EDITOR_TOOL_NAME,
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
    "name": edits.NOTE_TOOL_NAME,
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
- The frontmatter is managed for you: never edit it. An edit that changes nothing below \
the frontmatter is rejected. Your edit must add the note's facts to the page text.
- The full text of every related page is already given in the user message, \
so never call view, and never use insert. Call str_replace or create directly.
- Make two tool calls in ONE response, with no text: first file_note (one-sentence \
summary), then the str_replace_based_edit_tool call. Both are needed; neither \
depends on the other's result."""


class PagePlan(EditedPage):
    summary: str
    page_getting_large: bool = False


@timed("remember")
def remember(settings: CoreSettings, api_key: str, text: str) -> RememberResult:
    bucket = settings.wiki_bucket
    with timed("read_wiki_context"):
        conventions = wiki.get_file(bucket, settings.wiki_files.conventions).content
        index_md = wiki.get_file(bucket, settings.wiki_files.index).content
        domains = list(index_links.domain_headings(index_md))
    client = anthropic_client.get_client(api_key)

    with search_index.open_session(bucket, settings.search_index.db_key) as index:
        with timed("related_pages"):
            related_pages = _related_pages(bucket, index, text)
        plan = _plan_edit(bucket, client, conventions, domains, related_pages, text)

        with timed("write_page", path=plan.path, action=plan.action.value):
            _write_page(bucket, index, plan)

        if plan.action == PageAction.CREATE:
            with timed("link_in_index"):
                index_links.link_in_index(bucket, settings.wiki_files.index, plan.path, plan.title)

    with timed("append_log"):
        log.append(bucket, settings.wiki_files, "remember", f"{plan.path} — {plan.summary}")

    return RememberResult(
        page=plan.path,
        action=plan.action,
        summary=plan.summary,
        page_getting_large=plan.page_getting_large,
    )


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
    except edits.EditError as first:
        observability.logger.warning("edits rejected, retrying", reason=str(first))
        shown = list(related_pages)
        if isinstance(first, edits.PageNotShownError):
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
    page_edits = _decide(client, conventions, domains, shown, text, failure)

    first = page_edits.commands[0]
    if (
        isinstance(first, Create)
        and all(page.path != first.path for page in shown)
        and wiki.file_exists(bucket, first.path)
    ):
        raise edits.PageNotShownError(
            first.path, f"{first.path} already exists; update it with str_replace"
        )

    with timed("apply_edits", edits=len(page_edits.commands)):
        edited = edits.apply_edits(shown, page_edits.commands, today=frontmatter.today())

    return PagePlan(
        **edited.model_dump(),
        summary=page_edits.summary,
        page_getting_large=page_edits.page_getting_large,
    )


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
    return edits.parse_edits(calls)


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


def _search_terms(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    return " OR ".join(words[:12]) or text
