import boto3
import pytest
from moto import mock_aws

from victoria.core.storage import search_index, wiki
from victoria.core.storage.models import IndexEntry

BUCKET = "victoria-test"
DB_KEY = "search.db"
LIMIT = 10


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_download_creates_empty_index_when_none_exists(s3_bucket, tmp_path):
    db_path = tmp_path / "search.db"
    etag = search_index.download(BUCKET, DB_KEY, db_path)
    assert etag is None
    assert db_path.exists()

    conn = search_index.open_connection(db_path)
    assert search_index.search(conn, "anything", LIMIT) == []


def test_upsert_and_search(tmp_path):
    db_path = tmp_path / "search.db"
    conn = search_index.open_connection(db_path)

    search_index.upsert_page(
        conn,
        IndexEntry(
            path="wiki/house/plants.md",
            title="Plants",
            tags="garden, parking-strip",
            body="Hydrangeas planted this year in the parking strip.",
        ),
    )
    search_index.upsert_page(
        conn,
        IndexEntry(
            path="wiki/house/tools.md",
            title="Tools",
            tags="garage",
            body="Cordless drill, circular saw.",
        ),
    )

    hits = search_index.search(conn, "hydrangeas", LIMIT)
    assert [h.path for h in hits] == ["wiki/house/plants.md"]


def test_upsert_replaces_existing_entry_for_same_path(tmp_path):
    db_path = tmp_path / "search.db"
    conn = search_index.open_connection(db_path)

    search_index.upsert_page(
        conn, IndexEntry(path="wiki/house/tools.md", title="Tools", tags="", body="drill")
    )
    search_index.upsert_page(
        conn, IndexEntry(path="wiki/house/tools.md", title="Tools", tags="", body="saw")
    )

    hits = search_index.search(conn, "drill", LIMIT)
    assert hits == []
    hits = search_index.search(conn, "saw", LIMIT)
    assert [h.path for h in hits] == ["wiki/house/tools.md"]


def test_delete_page_removes_it_from_search(tmp_path):
    db_path = tmp_path / "search.db"
    conn = search_index.open_connection(db_path)
    search_index.upsert_page(
        conn, IndexEntry(path="wiki/house/tools.md", title="Tools", tags="", body="drill")
    )
    search_index.delete_page(conn, "wiki/house/tools.md")
    assert search_index.search(conn, "drill", LIMIT) == []


def test_upload_then_download_round_trips(s3_bucket, tmp_path):
    local_path = tmp_path / "search.db"
    conn = search_index.open_connection(local_path)
    search_index.upsert_page(
        conn, IndexEntry(path="wiki/house/tools.md", title="Tools", tags="", body="drill")
    )
    conn.close()

    search_index.upload(BUCKET, DB_KEY, local_path, if_match=None)

    other_path = tmp_path / "downloaded.db"
    etag = search_index.download(BUCKET, DB_KEY, other_path)
    assert etag is not None

    conn2 = search_index.open_connection(other_path)
    hits = search_index.search(conn2, "drill", LIMIT)
    assert [h.path for h in hits] == ["wiki/house/tools.md"]


def test_upload_conditional_write_fails_on_stale_etag(s3_bucket, tmp_path):
    local_path = tmp_path / "search.db"
    conn = search_index.open_connection(local_path)
    search_index.upsert_page(
        conn, IndexEntry(path="wiki/house/tools.md", title="Tools", tags="", body="v1")
    )
    conn.close()
    search_index.upload(BUCKET, DB_KEY, local_path, if_match=None)
    stale_etag = wiki.get_bytes(BUCKET, DB_KEY).etag

    conn = search_index.open_connection(local_path)
    search_index.upsert_page(
        conn, IndexEntry(path="wiki/house/tools.md", title="Tools", tags="", body="v2")
    )
    conn.close()
    search_index.upload(BUCKET, DB_KEY, local_path, if_match=None)  # a racing writer

    with pytest.raises(wiki.ConditionalWriteFailedError):
        search_index.upload(BUCKET, DB_KEY, local_path, if_match=stale_etag)


def test_search_wiki_read_only_helper(s3_bucket, tmp_path):
    local_path = tmp_path / "search.db"
    conn = search_index.open_connection(local_path)
    search_index.upsert_page(
        conn, IndexEntry(path="wiki/house/plants.md", title="Plants", tags="", body="hydrangeas")
    )
    conn.close()
    search_index.upload(BUCKET, DB_KEY, local_path, if_match=None)

    results = search_index.search_wiki(BUCKET, DB_KEY, "hydrangeas", LIMIT)
    assert [hit.path for hit in results.hits] == ["wiki/house/plants.md"]
