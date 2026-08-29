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


class FileNoteDecision(BaseModel):
    """remember's forced-tool-call output (DESIGN §7) — validated by
    call_forced_tool the moment the model responds, before remember() does
    anything else. page_path being a WikiPath means a bad path fails right
    here, before any write happens."""

    page_path: WikiPath
    action: PageAction
    title: str
    tags: list[str]
    full_content: str
    summary: str
    page_getting_large: bool = False


class RememberResult(BaseModel):
    page: WikiPath
    action: PageAction
    summary: str
    page_getting_large: bool = False


class ConsolidateResult(BaseModel):
    report: str
