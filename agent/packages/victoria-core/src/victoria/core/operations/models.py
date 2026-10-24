"""Structured results for the two agent operations (DESIGN §3, §7). See
core/storage/models.py's docstring for why these are enforced, not just
documented, at the MCP boundary.
"""

from enum import Enum

from pydantic import BaseModel

from victoria.core.storage.models import WikiPath


class PageAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"


class StrReplace(BaseModel):
    """One exact-text replacement in an existing page. old_str must occur
    exactly once; appending is a replacement of the last line with itself
    plus the new text."""

    path: WikiPath
    old_str: str
    new_str: str = ""


class Create(BaseModel):
    """A whole new page, frontmatter included."""

    path: WikiPath
    file_text: str


EditCommand = StrReplace | Create


class PageEdits(BaseModel):
    """What remember's model call returns: the edits to one page plus the
    one-line summary and size flag. Paths are WikiPaths, so a bad path fails
    here, before anything is written."""

    commands: list[EditCommand]
    summary: str
    page_getting_large: bool = False


class PagePlan(BaseModel):
    """A page write ready to perform: the final text, and the version tag of
    the page the edits were applied to (None for a new page) so the write can
    fail rather than overwrite a concurrent change."""

    path: WikiPath
    action: PageAction
    title: str
    tags: list[str]
    content: str
    base_etag: str | None
    summary: str
    page_getting_large: bool = False


class RememberResult(BaseModel):
    page: WikiPath
    action: PageAction
    summary: str
    page_getting_large: bool = False


class ConsolidateResult(BaseModel):
    report: str
