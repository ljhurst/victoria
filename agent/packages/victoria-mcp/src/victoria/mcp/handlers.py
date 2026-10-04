"""MCP tool-call requests -> core/ calls -> MCP responses (DESIGN §14).

Thin wrappers only — no business logic lives here, it's all in core/.
"""

from typing import Annotated

from pydantic import Field

from victoria.core.config import get_core_settings
from victoria.core.operations import consolidate as consolidate_core
from victoria.core.operations import remember as remember_core
from victoria.core.operations.models import ConsolidateResult, RememberResult
from victoria.core.storage import search_index, wiki
from victoria.core.storage.models import ListFilesResult, PageContent, SearchResults
from victoria.mcp.config import get_anthropic_api_key


def list_files(
    prefix: Annotated[str, Field(description="Path prefix, e.g. 'wiki/house/'.")],
) -> ListFilesResult:
    """List wiki page paths under a prefix."""
    return wiki.list_files(get_core_settings().wiki_bucket, prefix)


def get_file(
    path: Annotated[str, Field(description="As returned by list_files or search_wiki.")],
) -> PageContent:
    """Read a wiki page's full content by its path."""
    return wiki.get_file(get_core_settings().wiki_bucket, path)


def search_wiki(
    query: Annotated[str, Field(description="SQLite FTS5 query; plain keywords work.")],
) -> SearchResults:
    """Full-text search the wiki. Returns matching page paths + snippets."""
    settings = get_core_settings()

    return search_index.search_wiki(
        settings.wiki_bucket,
        settings.search_index.db_key,
        query,
        settings.search_index.default_limit,
    )


def remember(
    text: Annotated[str, Field(description="Plain prose; Victoria picks the page.")],
) -> RememberResult:
    """File new information into the wiki — the 'remember this' path."""
    return remember_core.remember(get_core_settings(), get_anthropic_api_key(), text)


def consolidate() -> ConsolidateResult:
    """Run a consolidation pass: contradictions, stale claims, orphan pages, splits."""
    return consolidate_core.consolidate(get_core_settings(), get_anthropic_api_key())
