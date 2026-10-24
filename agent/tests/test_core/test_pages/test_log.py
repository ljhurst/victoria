from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from victoria.core.config import WikiFiles
from victoria.core.pages import log
from victoria.core.storage import wiki
from victoria.core.storage.errors import ConditionalWriteFailedError

BUCKET = "victoria-test"


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_first_append_creates_the_log(s3_bucket):
    log.append(BUCKET, WikiFiles(), "remember", "wiki/house/plants.md — filed it")

    content = wiki.get_file(BUCKET, "log.md").content
    assert "remember" in content
    assert "wiki/house/plants.md — filed it" in content


def test_later_appends_keep_earlier_entries(s3_bucket):
    log.append(BUCKET, WikiFiles(), "remember", "first entry")
    log.append(BUCKET, WikiFiles(), "consolidate", "second entry")

    content = wiki.get_file(BUCKET, "log.md").content
    assert content.index("first entry") < content.index("second entry")
    assert "consolidate" in content


def test_a_concurrent_write_fails_the_append_instead_of_losing_it(s3_bucket):
    log.append(BUCKET, WikiFiles(), "remember", "first entry")
    stale = wiki.get_file_with_etag(BUCKET, "log.md")
    wiki.put_file(BUCKET, "log.md", stale.content + "someone else\n")

    with (
        patch.object(log.wiki, "get_file_with_etag", return_value=stale),
        pytest.raises(ConditionalWriteFailedError),
    ):
        log.append(BUCKET, WikiFiles(), "remember", "second entry")

    assert "someone else" in wiki.get_file(BUCKET, "log.md").content
