import boto3
import pytest
from moto import mock_aws

from victoria.core.config import get_core_settings
from victoria.core.storage import wiki
from victoria.mcp import handlers

BUCKET = "victoria-test"


@pytest.fixture
def s3_bucket():
    get_core_settings.cache_clear()
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        wiki.put_file(BUCKET, "wiki/house/plants.md", "hydrangeas")
        yield client
    get_core_settings.cache_clear()


def test_list_files_returns_typed_result(s3_bucket):
    result = handlers.list_files("wiki/house/")
    assert result.paths == ["wiki/house/plants.md"]


def test_get_file_returns_typed_result(s3_bucket):
    result = handlers.get_file("wiki/house/plants.md")
    assert result.path == "wiki/house/plants.md"
    assert result.content == "hydrangeas"
