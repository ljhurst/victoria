from datetime import date
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from victoria.core.config import CoreSettings
from victoria.core.operations import consolidate
from victoria.core.pages import frontmatter
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


def test_consolidate_asks_for_style_violations_to_be_reported_not_rewritten(s3_bucket, settings):
    captured = {}

    def fake_run_tool_loop(*_args, system, **_kwargs):
        captured["system"] = system
        return "done"

    with patch.object(
        consolidate.anthropic_client, "run_tool_loop", side_effect=fake_run_tool_loop
    ):
        consolidate.consolidate(settings, "fake-api-key")

    assert "break the Writing style section" in captured["system"]
    assert "don't rewrite them" in captured["system"]


def test_consolidate_sets_last_updated_on_pages_it_writes(s3_bucket, settings):
    stale = "---\ntitle: Tools\nlast-updated: 2020-01-01\n---\n\ndrill\n"
    undated = "---\ntitle: Plants\n---\n\nferns\n"

    def fake_run_tool_loop(*_args, dispatch, **_kwargs):
        dispatch("put_file", {"path": "wiki/house/tools.md", "content": stale})
        dispatch("put_file", {"path": "wiki/house/plants.md", "content": undated})
        return "done"

    with (
        patch.object(frontmatter, "today", return_value=date(2026, 10, 24)),
        patch.object(consolidate.anthropic_client, "run_tool_loop", side_effect=fake_run_tool_loop),
    ):
        consolidate.consolidate(settings, "fake-api-key")

    assert "last-updated: 2026-10-24" in wiki.get_file(BUCKET, "wiki/house/tools.md").content
    assert "2020-01-01" not in wiki.get_file(BUCKET, "wiki/house/tools.md").content
    assert "last-updated: 2026-10-24" in wiki.get_file(BUCKET, "wiki/house/plants.md").content
