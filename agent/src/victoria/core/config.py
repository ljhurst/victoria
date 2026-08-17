"""Settings for core/'s own business logic — nothing MCP-specific lives here
(DESIGN §14). See mcp/config.py for the MCP-boundary settings (auth, secret
resolution) that core/ never actually reads.
"""

from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class WikiFiles(BaseModel):
    """The wiki's root markdown files — read as text/prompt content, as
    distinct from search.db's binary sidecar (DESIGN §3)."""

    conventions: str = "CONVENTIONS.md"
    index: str = "index.md"
    log: str = "log.md"


class SearchIndexSettings(BaseModel):
    """The FTS5 sidecar's S3 key and default query result limit (DESIGN §6)."""

    db_key: str = "search.db"
    default_limit: int = 10


class CoreSettings(BaseSettings):
    wiki_bucket: str
    wiki_files: WikiFiles = WikiFiles()
    search_index: SearchIndexSettings = SearchIndexSettings()


@lru_cache(maxsize=1)
def get_core_settings() -> CoreSettings:
    return CoreSettings()
