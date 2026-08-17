from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from victoria.core.config import CoreSettings
from victoria.core.operations import consolidate
from victoria.core.storage import wiki
from victoria.core.storage.models import ListFilesResult, PageContent

BUCKET = "victoria-test"


@pytest.fixture
def settings():
    return CoreSettings(wiki_bucket=BUCKET)


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        wiki.put_file(BUCKET, "CONVENTIONS.md", "conventions text")
        wiki.put_file(BUCKET, "index.md", "# index\n")
        wiki.put_file(BUCKET, "log.md", "# log\n")
        yield client


def test_consolidate_returns_report_and_appends_log(s3_bucket, settings):
    with patch.object(
        consolidate.anthropic_client, "run_tool_loop", return_value="No issues found."
    ):
        result = consolidate.consolidate(settings, "fake-api-key")

    assert result.report == "No issues found."
    assert "No issues found." in wiki.get_file(BUCKET, "log.md").content


def test_consolidate_dispatch_wires_all_four_tools(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/tools.md", "---\ntitle: Tools\n---\n\ndrill\n")

    results = {}

    def fake_run_tool_loop(*_args, dispatch, **_kwargs):
        # called synchronously inside consolidate's `with` block, as the real
        # tool loop would — unlike capturing dispatch for use afterwards,
        # which would outlive the temp dir search.db lives in
        results["list_files"] = dispatch("list_files", {"prefix": "wiki/house/"})
        results["get_file"] = dispatch("get_file", {"path": "wiki/house/tools.md"})
        dispatch("put_file", {"path": "wiki/house/tools.md", "content": "updated content"})
        return "done"

    with patch.object(
        consolidate.anthropic_client, "run_tool_loop", side_effect=fake_run_tool_loop
    ):
        consolidate.consolidate(settings, "fake-api-key")

    assert results["list_files"] == ListFilesResult(paths=["wiki/house/tools.md"])
    assert "drill" in results["get_file"].content
    assert wiki.get_file(BUCKET, "wiki/house/tools.md") == PageContent(
        path="wiki/house/tools.md", content="updated content"
    )
