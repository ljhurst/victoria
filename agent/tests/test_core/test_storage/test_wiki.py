from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from victoria.core import observability
from victoria.core.storage import wiki
from victoria.core.storage.errors import ConditionalWriteFailedError
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


def test_list_pages_excludes_search_db(s3_bucket):
    wiki.put_file(BUCKET, "index.md", "a")
    wiki.put_file(BUCKET, "wiki/house/tools.md", "b")
    wiki.put_bytes(BUCKET, "search.db", b"\x00binary")

    assert sorted(wiki.list_pages(BUCKET).paths) == ["index.md", "wiki/house/tools.md"]


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


def _finished(logger) -> dict[str, dict]:
    return {
        c.kwargs["stage"]: c.kwargs
        for c in logger.info.call_args_list
        if c.args == ("stage finished",)
    }


def test_s3_primitives_log_their_target_and_size(s3_bucket):
    with patch.object(observability, "logger") as logger:
        wiki.put_file(BUCKET, "wiki/house/tools.md", "# Tools\n")
        wiki.get_file(BUCKET, "wiki/house/tools.md")
        wiki.file_exists(BUCKET, "wiki/house/tools.md")
        wiki.list_files(BUCKET, "wiki/house/")

    finished = _finished(logger)
    assert finished["s3_put"]["key"] == "wiki/house/tools.md"
    assert finished["s3_put"]["bytes"] == 8
    assert finished["s3_put"]["conditional"] is False
    assert finished["s3_get"]["key"] == "wiki/house/tools.md"
    assert finished["s3_get"]["bytes"] == 8
    assert finished["s3_head"]["key"] == "wiki/house/tools.md"
    assert finished["s3_list"]["prefix"] == "wiki/house/"
    assert finished["s3_list"]["keys"] == 1


def test_missing_key_logs_failure_and_still_raises(s3_bucket):
    with patch.object(observability, "logger") as logger, pytest.raises(ClientError):
        wiki.get_file(BUCKET, "wiki/house/nope.md")

    (failed,) = logger.error.call_args_list
    assert failed.kwargs["stage"] == "s3_get"
    assert failed.kwargs["key"] == "wiki/house/nope.md"
    assert failed.kwargs["error"] == "NoSuchKey"


def test_file_exists_for_a_missing_key_is_not_a_failure(s3_bucket):
    with patch.object(observability, "logger") as logger:
        assert wiki.file_exists(BUCKET, "wiki/house/nope.md") is False

    logger.error.assert_not_called()


def test_failed_conditional_write_is_logged_and_raised(s3_bucket):
    wiki.put_file(BUCKET, "wiki/house/tools.md", "v1")

    with (
        patch.object(observability, "logger") as logger,
        pytest.raises(ConditionalWriteFailedError),
    ):
        wiki.put_file(BUCKET, "wiki/house/tools.md", "v2", if_match='"stale-etag"')

    (failed,) = logger.error.call_args_list
    assert failed.kwargs["stage"] == "s3_put"
    assert failed.kwargs["conditional"] is True
    assert failed.kwargs["error"] == "ConditionalWriteFailedError"
