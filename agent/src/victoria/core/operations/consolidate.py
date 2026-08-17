"""consolidate() — the maintenance tool (DESIGN §9, §10): a full hand-rolled
tool-calling loop, since catching contradictions/staleness/orphans and
proposing or performing page splits needs real cross-page reasoning that a
single tool call can't do inline. v1 is invoked on demand via the consolidate
MCP tool, not on a schedule (§9 phase 2).
"""

from typing import Any

from pydantic import TypeAdapter

from victoria.core.config import CoreSettings
from victoria.core.integrations import anthropic_client
from victoria.core.operations import log
from victoria.core.operations.models import ConsolidateResult
from victoria.core.storage import search_index, wiki
from victoria.core.storage.models import IndexEntry, WikiPath

_WIKI_PATH = TypeAdapter(WikiPath)

_TOOLS = [
    {
        "name": "list_files",
        "description": "List wiki page paths under a prefix, e.g. 'wiki/house/'.",
        "input_schema": {
            "type": "object",
            "properties": {"prefix": {"type": "string"}},
            "required": ["prefix"],
        },
    },
    {
        "name": "get_file",
        "description": "Read a wiki page's full content by its path.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "search_wiki",
        "description": "Full-text search the wiki. Returns matching page paths + snippets.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "put_file",
        "description": (
            "Write a wiki page's complete new content — used to fix a contradiction, "
            "correct a stale claim, or perform a page split per CONVENTIONS.md. "
            "Not a diff — the whole file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
]

_SYSTEM_TEMPLATE = """You are Victoria's consolidation pass. Review the wiki for:
- contradictions between pages
- stale claims (dated information that's likely out of date)
- orphan pages (not linked from index.md)
- category pages that have grown large enough to be worth splitting into a
  directory, per the Splitting section of CONVENTIONS.md

Use list_files and get_file to survey the wiki (start from index.md and each
category page), search_wiki to check whether a fact appears elsewhere before
flagging a contradiction, and put_file to actually fix something you're
confident about (a split, a correction) — otherwise just report it.

CONVENTIONS.md:
{conventions}

When you're done, reply with a short plain-text report: what you found, what
you fixed directly, and what still needs a human decision."""


def _dispatch(
    bucket: str,
    index: search_index.SearchIndexSession,
    default_limit: int,
    name: str,
    tool_input: dict[str, Any],
) -> Any:
    if name == "list_files":
        return wiki.list_files(bucket, tool_input["prefix"])
    if name == "get_file":
        try:
            return wiki.get_file(bucket, tool_input["path"])
        except Exception as e:  # noqa: BLE001
            return f"error reading {tool_input['path']}: {e}"
    if name == "search_wiki":
        return index.search(tool_input["query"], default_limit)
    if name == "put_file":
        # Validate before any write, same reasoning as remember.py: failing
        # after wiki.put_file already succeeded would leave a confusing
        # half-completed state.
        path = _WIKI_PATH.validate_python(tool_input["path"])
        content = tool_input["content"]
        etag = None
        if wiki.file_exists(bucket, path):
            etag = wiki.get_file_with_etag(bucket, path).etag
        wiki.put_file(bucket, path, content, if_match=etag)
        index.upsert_page(IndexEntry(path=path, title=path, tags="", body=content))
        return f"wrote {path}"
    raise ValueError(f"unknown tool: {name}")


def consolidate(settings: CoreSettings, api_key: str) -> ConsolidateResult:
    bucket = settings.wiki_bucket
    conventions = wiki.get_file(bucket, settings.wiki_files.conventions).content

    with search_index.open_session(bucket, settings.search_index.db_key) as index:
        client = anthropic_client.get_client(api_key)
        report = anthropic_client.run_tool_loop(
            client,
            model=anthropic_client.SONNET_MODEL,
            system=_SYSTEM_TEMPLATE.format(conventions=conventions),
            user_message="Run a consolidation pass over the whole wiki now.",
            tools=_TOOLS,
            dispatch=lambda name, tool_input: _dispatch(
                bucket, index, settings.search_index.default_limit, name, tool_input
            ),
        )

    log.append(
        bucket,
        settings.wiki_files,
        "consolidate",
        report.splitlines()[0] if report else "no report",
    )

    return ConsolidateResult(report=report)
