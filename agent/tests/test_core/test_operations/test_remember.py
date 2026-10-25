from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from victoria.core import observability
from victoria.core.config import CoreSettings
from victoria.core.integrations.models import ToolCall
from victoria.core.operations import remember
from victoria.core.pages import edits
from victoria.core.pages.models import PageAction
from victoria.core.storage import search_index, wiki
from victoria.core.storage.errors import ConditionalWriteFailedError
from victoria.core.storage.models import IndexEntry

BUCKET = "victoria-test"
SEED_INDEX = "# Wiki index\n\n## House\n\n_(no pages yet — created by `remember` as topics come up)_\n\n## Business\n\n_(no pages yet — created by `remember` as topics come up)_\n"


@pytest.fixture
def settings():
    return CoreSettings(wiki_bucket=BUCKET)


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        wiki.put_file(BUCKET, "CONVENTIONS.md", "conventions text")
        wiki.put_file(BUCKET, "index.md", SEED_INDEX)
        wiki.put_file(BUCKET, "log.md", "# log\n")
        yield client


PLANTS_PAGE = (
    "---\ntitle: Plants\ntags: [garden, parking-strip]\nlast-updated: 2026-01-01\n---\n\n"
    "## Hydrangeas\nStruggling, planted this year.\n"
)


def _note(summary="filed hydrangea note under plants.md", **fields) -> ToolCall:
    return ToolCall(name="file_note", input={"summary": summary, **fields})


def _create(path="wiki/house/plants.md", text=PLANTS_PAGE) -> ToolCall:
    return ToolCall(
        name="str_replace_based_edit_tool",
        input={"command": "create", "path": path, "file_text": text},
    )


def _replace(old, new, path="wiki/house/plants.md") -> ToolCall:
    return ToolCall(
        name="str_replace_based_edit_tool",
        input={"command": "str_replace", "path": path, "old_str": old, "new_str": new},
    )


def _model_returns(*responses: list[ToolCall]):
    return patch.object(remember.anthropic_client, "call_tools", side_effect=list(responses))


def _index_page(settings, path, title, tags, body):
    with search_index.open_session(BUCKET, settings.search_index.db_key) as index:
        index.upsert_page(IndexEntry(path=path, title=title, tags=tags, body=body))


def test_remember_gives_the_model_the_domains_and_how_to_edit(s3_bucket, settings):
    captured = {}

    def fake_call_tools(*_args, **kwargs):
        captured.update(kwargs)
        return [_note(), _create()]

    with patch.object(remember.anthropic_client, "call_tools", side_effect=fake_call_tools):
        remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    assert "existing domains are: house, business." in captured["system"]
    assert "Write every fact the note states and nothing else" in captured["system"]
    assert "never call view" in captured["system"]
    assert [tool["name"] for tool in captured["tools"]] == [
        "str_replace_based_edit_tool",
        "file_note",
    ]


def test_remember_files_into_a_new_domain(s3_bucket, settings):
    page = "---\ntitle: Tools\n---\n\nsocket set\n"
    with _model_returns([_note(), _create("wiki/garage/tools.md", page)]):
        remember.remember(settings, "fake-api-key", "bought a new socket set")

    assert wiki.file_exists(BUCKET, "wiki/garage/tools.md")
    index = wiki.get_file(BUCKET, "index.md").content
    assert "[Tools](wiki/garage/tools.md)" in index.split("## Garage")[1]


def test_remember_creates_new_page_and_links_it(s3_bucket, settings):
    with _model_returns([_note(), _create()]):
        result = remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    assert result.page == "wiki/house/plants.md"
    assert result.action == PageAction.CREATE
    assert result.summary == "filed hydrangea note under plants.md"
    page = wiki.get_file(BUCKET, "wiki/house/plants.md").content
    assert "last-updated: 2026-01-01" not in page
    assert page.count("last-updated:") == 1

    index = wiki.get_file(BUCKET, "index.md")
    assert "[Plants](wiki/house/plants.md)" in index.content

    log = wiki.get_file(BUCKET, "log.md")
    assert "wiki/house/plants.md — filed hydrangea note under plants.md" in log.content

    results = search_index.search_wiki(BUCKET, settings.search_index.db_key, "hydrangeas", 10)
    assert [hit.path for hit in results.hits] == ["wiki/house/plants.md"]
    assert results.hits[0].title == "Plants"


def test_remember_finds_and_includes_related_pages(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    _index_page(settings, "wiki/house/plants.md", "Plants", "garden", PLANTS_PAGE)

    captured = {}

    def fake_call_tools(*_args, **kwargs):
        captured["user_message"] = kwargs["user_message"]
        return [_note(), _replace("Struggling, planted this year.", "Struggling.\nBloomed pink.")]

    with patch.object(remember.anthropic_client, "call_tools", side_effect=fake_call_tools):
        remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    assert "wiki/house/plants.md" in captured["user_message"]
    assert "Struggling, planted this year." in captured["user_message"]


def test_remember_updates_existing_page_by_applying_the_edit(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    _index_page(settings, "wiki/house/plants.md", "Plants", "garden", PLANTS_PAGE)
    edit = _replace(
        "Struggling, planted this year.",
        "Struggling, planted this year.\n- Bloomed pink 2026-07-02.",
    )

    with _model_returns([_note(), edit]):
        result = remember.remember(settings, "fake-api-key", "hydrangeas bloomed pink")

    assert result.action == PageAction.UPDATE
    page = wiki.get_file(BUCKET, "wiki/house/plants.md").content
    assert "- Bloomed pink 2026-07-02." in page
    assert "## Hydrangeas\nStruggling, planted this year.\n- Bloomed pink" in page
    assert "last-updated: 2026-01-01" not in page
    # index.md untouched for an update to an already-linked page
    assert wiki.get_file(BUCKET, "index.md").content == SEED_INDEX
    found = search_index.search_wiki(BUCKET, settings.search_index.db_key, "bloomed", 10)
    assert [hit.path for hit in found.hits] == ["wiki/house/plants.md"]


def test_remember_does_not_overwrite_a_page_changed_after_it_was_read(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    _index_page(settings, "wiki/house/plants.md", "Plants", "garden", PLANTS_PAGE)

    def concurrent_write_then_edit(*_args, **_kwargs):
        wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE + "\nsomeone else's note\n")
        return [_note(), _replace("Struggling", "Thriving")]

    with (
        patch.object(
            remember.anthropic_client, "call_tools", side_effect=concurrent_write_then_edit
        ),
        pytest.raises(ConditionalWriteFailedError),
    ):
        remember.remember(settings, "fake-api-key", "hydrangeas recovered")

    assert "someone else's note" in wiki.get_file(BUCKET, "wiki/house/plants.md").content


def test_remember_retries_once_when_an_edit_does_not_match(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    _index_page(settings, "wiki/house/plants.md", "Plants", "garden", PLANTS_PAGE)
    messages = []

    def fake_call_tools(*_args, **kwargs):
        messages.append(kwargs["user_message"])
        if len(messages) == 1:
            return [_note(), _replace("Struggling this year", "Thriving")]
        return [_note(), _replace("Struggling, planted this year.", "Thriving.")]

    with patch.object(remember.anthropic_client, "call_tools", side_effect=fake_call_tools):
        remember.remember(settings, "fake-api-key", "hydrangeas recovered")

    assert "rejected" not in messages[0]
    assert "Your previous edits were rejected" in messages[1]
    assert "matched 0 times" in messages[1]
    assert "Thriving." in wiki.get_file(BUCKET, "wiki/house/plants.md").content


def test_remember_retries_when_the_model_uses_an_unavailable_command(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    _index_page(settings, "wiki/house/plants.md", "Plants", "garden", PLANTS_PAGE)
    view = ToolCall(
        name="str_replace_based_edit_tool",
        input={"command": "view", "path": "wiki/house/plants.md"},
    )

    with _model_returns([_note(), view], [_note(), _replace("Struggling", "Thriving")]):
        remember.remember(settings, "fake-api-key", "hydrangeas recovered")

    assert "Thriving" in wiki.get_file(BUCKET, "wiki/house/plants.md").content


def test_remember_writes_nothing_when_the_retry_is_also_rejected(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    _index_page(settings, "wiki/house/plants.md", "Plants", "garden", PLANTS_PAGE)
    log_before = wiki.get_file(BUCKET, "log.md").content
    bad = [_note(), _replace("not on the page", "x")]

    with _model_returns(bad, bad), pytest.raises(edits.EditError, match="matched 0 times"):
        remember.remember(settings, "fake-api-key", "hydrangeas recovered")

    assert wiki.get_file(BUCKET, "wiki/house/plants.md").content == PLANTS_PAGE
    assert wiki.get_file(BUCKET, "log.md").content == log_before
    found = search_index.search_wiki(BUCKET, settings.search_index.db_key, "recovered", 10)
    assert found.hits == []


def test_remember_shows_the_model_a_page_it_edits_without_having_seen_it(s3_bucket, settings):
    # plants.md exists but search doesn't surface it, so the model isn't shown
    # it; editing it blind must not overwrite it
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    messages = []

    def fake_call_tools(*_args, **kwargs):
        messages.append(kwargs["user_message"])
        if len(messages) == 1:
            return [_note(), _replace("Struggling", "Thriving")]
        return [_note(), _replace("Struggling, planted this year.", "Thriving.")]

    with patch.object(remember.anthropic_client, "call_tools", side_effect=fake_call_tools):
        remember.remember(settings, "fake-api-key", "hydrangeas recovered")

    assert "Struggling, planted this year." not in messages[0]
    assert "was not shown" in messages[1]
    assert "Struggling, planted this year." in messages[1]
    page = wiki.get_file(BUCKET, "wiki/house/plants.md").content
    assert "## Hydrangeas\nThriving." in page
    assert page.startswith("---\ntitle: Plants")


def test_remember_does_not_let_a_create_overwrite_an_unseen_existing_page(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    messages = []

    def fake_call_tools(*_args, **kwargs):
        messages.append(kwargs["user_message"])
        if len(messages) == 1:
            return [_note(), _create(text="---\ntitle: Plants\n---\n\nclobbered\n")]
        return [_note(), _replace("Struggling, planted this year.", "Thriving.")]

    with patch.object(remember.anthropic_client, "call_tools", side_effect=fake_call_tools):
        result = remember.remember(settings, "fake-api-key", "hydrangeas recovered")

    assert result.action == PageAction.UPDATE
    page = wiki.get_file(BUCKET, "wiki/house/plants.md").content
    assert "clobbered" not in page
    assert "Thriving." in page


def _finished_stages(logger) -> list[str]:
    return [c.kwargs["stage"] for c in logger.info.call_args_list if c.args == ("stage finished",)]


def _outer_stages(logger) -> list[str]:
    return [stage for stage in _finished_stages(logger) if not stage.startswith("s3_")]


def test_remember_logs_each_stage_when_creating_a_page(s3_bucket, settings):
    with _model_returns([_note(), _create()]), patch.object(observability, "logger") as logger:
        remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    assert _outer_stages(logger) == [
        "read_wiki_context",
        "search_index_download",
        "related_pages",
        "apply_edits",
        "write_page",
        "link_in_index",
        "search_index_upload",
        "append_log",
        "remember",
    ]


def test_remember_skips_index_link_stage_when_updating_a_page(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    _index_page(settings, "wiki/house/plants.md", "Plants", "garden", PLANTS_PAGE)

    with (
        _model_returns([_note(), _replace("Struggling", "Thriving")]),
        patch.object(observability, "logger") as logger,
    ):
        remember.remember(settings, "fake-api-key", "hydrangeas recovered")

    stages = _outer_stages(logger)
    assert "write_page" in stages
    assert "link_in_index" not in stages
    assert stages[-1] == "remember"


def test_remember_logs_the_rejected_edit_before_retrying(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", PLANTS_PAGE)
    _index_page(settings, "wiki/house/plants.md", "Plants", "garden", PLANTS_PAGE)

    with (
        _model_returns(
            [_note(), _replace("not there", "x")], [_note(), _replace("Struggling", "Thriving")]
        ),
        patch.object(observability, "logger") as logger,
    ):
        remember.remember(settings, "fake-api-key", "hydrangeas recovered")

    (warning,) = logger.warning.call_args_list
    assert warning.args == ("edits rejected, retrying",)
    assert "matched 0 times" in warning.kwargs["reason"]


def test_remember_logs_failure_of_the_top_level_stage(s3_bucket, settings):
    with (
        patch.object(remember.anthropic_client, "call_tools", side_effect=TimeoutError),
        patch.object(observability, "logger") as logger,
        pytest.raises(TimeoutError),
    ):
        remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    failures = [(c.kwargs["stage"], c.kwargs["error"]) for c in logger.error.call_args_list]
    assert failures == [("remember", "TimeoutError")]


def test_remember_s3_calls_are_logged_inside_the_stage_that_made_them(s3_bucket, settings):
    with _model_returns([_note(), _create()]), patch.object(observability, "logger") as logger:
        remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    finished = _finished_stages(logger)
    assert finished[finished.index("write_page") - 1] == "s3_put"
