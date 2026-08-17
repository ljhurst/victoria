import boto3
import pytest
from moto import mock_aws

from victoria.core.storage import wiki
from victoria.core.storage.models import PageContent

BUCKET = "victoria-test"


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_put_and_get_file(s3_bucket):
    wiki.put_file(BUCKET, "wiki/house/tools.md", "# Tools\n")
    assert wiki.get_file(BUCKET, "wiki/house/tools.md") == PageContent(
        path="wiki/house/tools.md", content="# Tools\n"
    )


def test_file_exists(s3_bucket):
    assert not wiki.file_exists(BUCKET, "wiki/house/tools.md")
    wiki.put_file(BUCKET, "wiki/house/tools.md", "# Tools\n")
    assert wiki.file_exists(BUCKET, "wiki/house/tools.md")


def test_list_files_scoped_to_prefix(s3_bucket):
    wiki.put_file(BUCKET, "wiki/house/tools.md", "a")
    wiki.put_file(BUCKET, "wiki/house/plants.md", "b")
    wiki.put_file(BUCKET, "wiki/business/hours.md", "c")

    assert sorted(wiki.list_files(BUCKET, "wiki/house/").paths) == [
        "wiki/house/plants.md",
        "wiki/house/tools.md",
    ]


def test_get_file_with_etag_changes_on_write(s3_bucket):
    wiki.put_file(BUCKET, "wiki/house/tools.md", "v1")
    etag1 = wiki.get_file_with_etag(BUCKET, "wiki/house/tools.md").etag
    wiki.put_file(BUCKET, "wiki/house/tools.md", "v2")
    etag2 = wiki.get_file_with_etag(BUCKET, "wiki/house/tools.md").etag
    assert etag1 != etag2


def test_conditional_write_succeeds_with_matching_etag(s3_bucket):
    wiki.put_file(BUCKET, "wiki/house/tools.md", "v1")
    etag = wiki.get_file_with_etag(BUCKET, "wiki/house/tools.md").etag
    wiki.put_file(BUCKET, "wiki/house/tools.md", "v2", if_match=etag)
    assert wiki.get_file(BUCKET, "wiki/house/tools.md") == PageContent(
        path="wiki/house/tools.md", content="v2"
    )


def test_conditional_write_fails_on_stale_etag(s3_bucket):
    wiki.put_file(BUCKET, "wiki/house/tools.md", "v1")
    stale_etag = wiki.get_file_with_etag(BUCKET, "wiki/house/tools.md").etag
    wiki.put_file(BUCKET, "wiki/house/tools.md", "v2")  # a racing writer

    with pytest.raises(wiki.ConditionalWriteFailedError):
        wiki.put_file(BUCKET, "wiki/house/tools.md", "v3", if_match=stale_etag)
