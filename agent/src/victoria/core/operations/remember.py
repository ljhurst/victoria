"""remember(text) — the curation-aware write tool (DESIGN §7).

Internally: search for related pages, decide merge-vs-new-page (one forced
tool call to a cheap model), write per CONVENTIONS.md, update index.md and
search.db, return a short summary. put_file stays an internal primitive —
never exposed directly to the calling model (DESIGN §7).
"""

import re

import anthropic

from victoria.core.config import CoreSettings
from victoria.core.integrations import anthropic_client
from victoria.core.operations import log
from victoria.core.operations.models import FileNoteDecision, PageAction, RememberResult
from victoria.core.storage import search_index, wiki
from victoria.core.storage.models import IndexEntry, PageVersion, WikiPath

_FILE_NOTE_TOOL = {
    "name": "file_note",
    "description": ("Record the decision for where and how to file this note into the wiki."),
    "input_schema": {
        "type": "object",
        "properties": {
            "page_path": {
                "type": "string",
                "description": (
                    "Full S3 key for the page, e.g. 'wiki/house/plants.md'. "
                    "Must start with 'wiki/house/' or 'wiki/business/'."
                ),
            },
            # Values here must stay in sync with PageAction (core/operations/models.py).
            "action": {"type": "string", "enum": ["create", "update"]},
            "title": {"type": "string", "description": "Page title, for the frontmatter."},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Freeform tags for the frontmatter and search index.",
            },
            "full_content": {
                "type": "string",
                "description": (
                    "The complete new page content (frontmatter + markdown body), "
                    "per CONVENTIONS.md — not a diff, the whole file."
                ),
            },
            "summary": {
                "type": "string",
                "description": "One sentence describing what was filed and where.",
            },
            "page_getting_large": {
                "type": "boolean",
                "description": (
                    "True if this page now looks like a splitting candidate "
                    "per CONVENTIONS.md — a signal for consolidate, not an action to take now."
                ),
            },
        },
        "required": ["page_path", "action", "title", "tags", "full_content", "summary"],
    },
}

_SYSTEM_TEMPLATE = """You are Victoria's ingestion step. Your only job is to decide \
where a new piece of information belongs in the wiki and produce that page's \
complete new content, following these conventions exactly:

{conventions}

Call file_note with your decision. full_content must be the ENTIRE page \
content, not just the new part — merge the new note into the existing page \
content if one was provided below, preserving everything still true."""


def _search_terms(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    return " OR ".join(words[:12]) or text


def _domain_heading(page_path: str) -> str:
    return "## House" if page_path.startswith("wiki/house/") else "## Business"


def _ensure_linked(index_md: str, page_path: str, title: str) -> str:
    if f"({page_path})" in index_md:
        return index_md
    heading = _domain_heading(page_path)
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
    client: anthropic.Anthropic, conventions: str, related_pages: list[PageVersion], text: str
) -> FileNoteDecision:
    related_block = (
        "\n\n".join(f"--- existing page: {p.path} ---\n{p.content}" for p in related_pages)
        or "(no related pages found)"
    )
    user_message = (
        f"New note to file:\n{text}\n\nRelated existing pages found via search:\n{related_block}"
    )
    return anthropic_client.call_forced_tool(
        client,
        model=anthropic_client.HAIKU_MODEL,
        system=_SYSTEM_TEMPLATE.format(conventions=conventions),
        user_message=user_message,
        tool=_FILE_NOTE_TOOL,
        response_model=FileNoteDecision,
    )


def _write_page(
    bucket: str,
    index: search_index.SearchIndexSession,
    decision: FileNoteDecision,
    existing_etag: str | None,
) -> None:
    wiki.put_file(bucket, decision.page_path, decision.full_content, if_match=existing_etag)
    index.upsert_page(
        IndexEntry(
            path=decision.page_path,
            title=decision.title,
            tags=", ".join(decision.tags),
            body=decision.full_content,
        )
    )


def _link_in_index(bucket: str, index_key: WikiPath, decision: FileNoteDecision) -> None:
    index_page = wiki.get_file_with_etag(bucket, index_key)
    updated_index = _ensure_linked(index_page.content, decision.page_path, decision.title)
    if updated_index != index_page.content:
        wiki.put_file(bucket, index_key, updated_index, if_match=index_page.etag)


def remember(settings: CoreSettings, api_key: str, text: str) -> RememberResult:
    bucket = settings.wiki_bucket
    conventions = wiki.get_file(bucket, settings.wiki_files.conventions).content
    client = anthropic_client.get_client(api_key)

    with search_index.open_session(bucket, settings.search_index.db_key) as index:
        related_pages = _related_pages(bucket, index, text)
        decision = _decide(client, conventions, related_pages, text)

        existing_etag = next((p.etag for p in related_pages if p.path == decision.page_path), None)
        if existing_etag is None and wiki.file_exists(bucket, decision.page_path):
            existing_etag = wiki.get_file_with_etag(bucket, decision.page_path).etag

        _write_page(bucket, index, decision, existing_etag)

        if decision.action == PageAction.CREATE:
            _link_in_index(bucket, settings.wiki_files.index, decision)

    log.append(
        bucket, settings.wiki_files, "remember", f"{decision.page_path} — {decision.summary}"
    )

    return RememberResult(
        page=decision.page_path,
        action=decision.action,
        summary=decision.summary,
        page_getting_large=decision.page_getting_large,
    )
