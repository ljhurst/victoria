"""SQLite/FTS5 sidecar search index, synced to S3 (DESIGN §6).

The whole search.db lifecycle lives here: sync to/from S3, connection/schema
management, mutation, and query — all storage-layer plumbing, no business
logic (no LLM calls, no decisions), which is why it stays in storage/ rather
than operations/.
"""

import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from victoria.core.storage import wiki
from victoria.core.storage.models import IndexEntry, SearchHit, SearchResults, WikiPath

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(
    path UNINDEXED,
    title,
    tags,
    body
);
"""


# --- sync: S3 <-> local file ---


def download(bucket: str, key: str, local_path: Path) -> str | None:
    """Pull search.db from S3 into local_path. Returns its ETag, or None if
    the index doesn't exist yet (first run — an empty one is created)."""
    if not wiki.file_exists(bucket, key):
        _init_empty(local_path)
        return None

    raw = wiki.get_bytes(bucket, key)
    local_path.write_bytes(raw.content)

    return raw.etag


def upload(bucket: str, key: str, local_path: Path, *, if_match: str | None) -> str:
    return wiki.put_bytes(bucket, key, local_path.read_bytes(), if_match=if_match)


# --- connection / schema ---


def open_connection(local_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(local_path)
    conn.executescript(_SCHEMA)
    return conn


def _init_empty(local_path: Path) -> None:
    conn = open_connection(local_path)
    conn.commit()
    conn.close()


# --- mutation ---


def upsert_page(conn: sqlite3.Connection, entry: IndexEntry) -> None:
    conn.execute("DELETE FROM pages WHERE path = ?", (entry.path,))
    conn.execute(
        "INSERT INTO pages (path, title, tags, body) VALUES (?, ?, ?, ?)",
        (entry.path, entry.title, entry.tags, entry.body),
    )
    conn.commit()


def delete_page(conn: sqlite3.Connection, path: WikiPath) -> None:
    conn.execute("DELETE FROM pages WHERE path = ?", (path,))
    conn.commit()


# --- query ---


def search(conn: sqlite3.Connection, query: str, limit: int) -> list[SearchHit]:
    rows = conn.execute(
        """
        SELECT path, title, snippet(pages, 3, '[', ']', '...', 10) AS snippet
        FROM pages
        WHERE pages MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()

    return [SearchHit(path=r[0], title=r[1], snippet=r[2]) for r in rows]


# --- session: download once, mutate freely, upload only if changed ---


class SearchIndexSession:
    """A connected search.db that tracks whether anything was written, so
    open_session() knows whether an upload is needed on exit. Get one via
    open_session() — not constructed directly."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.dirty = False

    def search(self, query: str, limit: int) -> list[SearchHit]:
        return search(self._conn, query, limit)

    def upsert_page(self, entry: IndexEntry) -> None:
        upsert_page(self._conn, entry)
        self.dirty = True

    def delete_page(self, path: WikiPath) -> None:
        delete_page(self._conn, path)
        self.dirty = True


@contextmanager
def open_session(bucket: str, key: str) -> Iterator[SearchIndexSession]:
    """Download search.db, yield a session to query/mutate it, upload back on
    exit only if something changed. Replaces the download/open-connection/
    upload dance that used to be duplicated in remember.py, consolidate.py,
    and search_wiki() itself."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / key
        etag = download(bucket, key, db_path)
        conn = open_connection(db_path)
        session = SearchIndexSession(conn)
        try:
            yield session
        finally:
            if session.dirty:
                upload(bucket, key, db_path, if_match=etag)
            conn.close()


def search_wiki(bucket: str, key: str, query: str, limit: int) -> SearchResults:
    """Read-only convenience wrapper for the search_wiki MCP read tool (§7)."""
    with open_session(bucket, key) as index:
        hits = index.search(query, limit)

    return SearchResults(hits=hits)
