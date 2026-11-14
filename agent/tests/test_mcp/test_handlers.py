from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from victoria.core.config import get_core_settings
from victoria.core.storage import wiki
from victoria.mcp import handlers
from victoria.mcp.config import get_anthropic_federation

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


@pytest.fixture
def anthropic_federation_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FEDERATION_RULE_ID", "fdrl_1")
    monkeypatch.setenv("ANTHROPIC_ORGANIZATION_ID", "org_1")
    monkeypatch.setenv("ANTHROPIC_SERVICE_ACCOUNT_ID", "svac_1")
    get_anthropic_federation.cache_clear()
    yield
    get_anthropic_federation.cache_clear()


def test_remember_passes_the_federation_to_core(s3_bucket, anthropic_federation_env):
    with patch("victoria.core.operations.remember.remember") as remember_core:
        result = handlers.remember("hydrangeas bloomed")

    settings, federation, text = remember_core.call_args.args
    assert settings.wiki_bucket == BUCKET
    assert federation.federation_rule_id == "fdrl_1"
    assert text == "hydrangeas bloomed"
    assert result is remember_core.return_value


def test_consolidate_passes_the_federation_to_core(s3_bucket, anthropic_federation_env):
    with patch("victoria.core.operations.consolidate.consolidate") as consolidate_core:
        result = handlers.consolidate()

    settings, federation = consolidate_core.call_args.args
    assert settings.wiki_bucket == BUCKET
    assert federation.service_account_id == "svac_1"
    assert result is consolidate_core.return_value
