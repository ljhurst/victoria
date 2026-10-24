"""Structured results for the two agent operations (DESIGN §3, §7). See
core/storage/models.py's docstring for why these are enforced, not just
documented, at the MCP boundary.
"""

from pydantic import BaseModel

from victoria.core.pages.models import PageAction
from victoria.core.storage.models import WikiPath


class RememberResult(BaseModel):
    page: WikiPath
    action: PageAction
    summary: str
    page_getting_large: bool = False


class ConsolidateResult(BaseModel):
    report: str
