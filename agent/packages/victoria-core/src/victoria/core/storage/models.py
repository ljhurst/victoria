"""Structured data shapes for the storage layer (DESIGN §7). Shared between
wiki.py and search_index.py — SearchHit needs WikiPath, so both live here
rather than one file reaching into the other for a type.

ListFilesResult, PageContent, and SearchResults are what mcp/handlers.py's
read tools return. The mcp SDK uses BaseModel subclasses directly as a
tool's output schema (rather than its generic {"result": ...} fallback for
bare types), and validates whatever a tool returns against them — so these
aren't just documentation, they're enforced at the MCP boundary. Because of
that, PageContent deliberately carries no etag — anything in it is a token
cost paid on every get_file tool call, and the calling model never needs
one. RawContent and PageVersion are the opposite: purely internal (S3
conditional-write bookkeeping, search.db's binary content), never returned
by an MCP tool, so no such constraint applies to them.
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

WikiPath = Annotated[
    str,
    StringConstraints(
        pattern=r"^(CONVENTIONS\.md|index\.md|log\.md|wiki/(house|business)/.+\.md)$"
    ),
    Field(description="A wiki page's S3 key, e.g. 'wiki/house/plants.md' or 'index.md'."),
]


class ListFilesResult(BaseModel):
    paths: list[WikiPath]


class PageContent(BaseModel):
    path: WikiPath
    content: str


class PageVersion(PageContent):
    etag: str


class SearchHit(BaseModel):
    path: WikiPath
    title: str
    snippet: str


class SearchResults(BaseModel):
    hits: list[SearchHit]


class IndexEntry(BaseModel):
    """What upsert_page() writes into the FTS5 index — one named object
    instead of four positional strings that could be passed in the wrong
    order."""

    path: WikiPath
    title: str
    tags: str
    body: str


class RawContent(BaseModel):
    content: bytes
    etag: str
