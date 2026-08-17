"""Audit trail: append-only log.md (DESIGN §3), shared by remember and
consolidate — the append pattern (read current content + etag, fall back to
empty on first write, conditional put) was duplicated between them.
"""

from victoria.core.config import WikiFiles
from victoria.core.storage import wiki


def append(bucket: str, wiki_files: WikiFiles, tool: str, message: str) -> None:
    try:
        log_page = wiki.get_file_with_etag(bucket, wiki_files.log)
        log_content, log_etag = log_page.content, log_page.etag
    except Exception:  # noqa: BLE001 — no log.md yet is fine, start fresh
        log_content, log_etag = "", None

    log_line = f"\n{tool} — {message}"
    wiki.put_file(bucket, wiki_files.log, log_content + log_line + "\n", if_match=log_etag)
