from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws
from pydantic import ValidationError

from victoria.core.config import CoreSettings
from victoria.core.operations import remember
from victoria.core.operations.models import FileNoteDecision, PageAction
from victoria.core.storage import search_index, wiki
from victoria.core.storage.models import IndexEntry

BUCKET = "victoria-test"
SEED_INDEX = "# Victoria — wiki index\n\n## House\n\n_(no pages yet — created by `remember` as topics come up)_\n\n## Business\n\n_(no pages yet — created by `remember` as topics come up)_\n"


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


def _decision_fields(**overrides) -> dict:
    fields = {
        "page_path": "wiki/house/plants.md",
        "action": PageAction.CREATE,
        "title": "Plants",
        "tags": ["garden", "parking-strip"],
        "full_content": "---\ntitle: Plants\n---\n\n## Hydrangeas\nStruggling, planted this year.\n",
        "summary": "filed hydrangea note under plants.md",
        "page_getting_large": False,
    }
    fields.update(overrides)
    return fields


def _fake_decision(**overrides) -> FileNoteDecision:
    return FileNoteDecision(**_decision_fields(**overrides))


class TestEnsureLinked:
    def test_appends_link_replacing_placeholder(self):
        result = remember._ensure_linked(SEED_INDEX, "wiki/house/plants.md", "Plants")
        assert "[Plants](wiki/house/plants.md)" in result
        house_section = result.split("## House")[1].split("## Business")[0]
        assert "_(no pages yet" not in house_section

    def test_is_idempotent(self):
        once = remember._ensure_linked(SEED_INDEX, "wiki/house/plants.md", "Plants")
        twice = remember._ensure_linked(once, "wiki/house/plants.md", "Plants")
        assert once == twice
        assert once.count("plants.md") == 1

    def test_business_page_goes_under_business_heading(self):
        result = remember._ensure_linked(SEED_INDEX, "wiki/business/hours.md", "Hours")
        business_section = result.split("## Business")[1]
        assert "[Hours](wiki/business/hours.md)" in business_section
        house_section = result.split("## House")[1].split("## Business")[0]
        assert "hours.md" not in house_section


def test_remember_creates_new_page_and_links_it(s3_bucket, settings):
    with patch.object(remember.anthropic_client, "call_forced_tool", return_value=_fake_decision()):
        result = remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    assert result.page == "wiki/house/plants.md"
    assert result.action == PageAction.CREATE
    assert wiki.file_exists(BUCKET, "wiki/house/plants.md")

    index = wiki.get_file(BUCKET, "index.md")
    assert "[Plants](wiki/house/plants.md)" in index.content

    log = wiki.get_file(BUCKET, "log.md")
    assert "wiki/house/plants.md" in log.content

    results = search_index.search_wiki(BUCKET, settings.search_index.db_key, "hydrangeas", 10)
    assert [hit.path for hit in results.hits] == ["wiki/house/plants.md"]


def test_remember_finds_and_includes_related_pages(s3_bucket, settings):
    # a pre-existing indexed page that a search would surface — exercises
    # the branch that used to do hit["path"] on a SearchHit (an
    # AttributeError, since SearchHit is a Pydantic model, not a dict) but
    # was never covered because every other test's bucket starts empty
    # a real indexed page needs both the search entry *and* the actual page
    # content in S3 — get_file_with_etag would otherwise legitimately fail
    # and get silently caught by _related_pages' stale-index-entry fallback
    wiki.put_file(BUCKET, "wiki/house/plants.md", "Hydrangeas planted in the parking strip.")
    with search_index.open_session(BUCKET, settings.search_index.db_key) as index:
        index.upsert_page(
            IndexEntry(
                path="wiki/house/plants.md",
                title="Plants",
                tags="garden",
                body="Hydrangeas planted in the parking strip.",
            )
        )

    captured = {}

    def fake_call_forced_tool(*_args, **kwargs):
        captured["user_message"] = kwargs["user_message"]
        return _fake_decision()

    with patch.object(
        remember.anthropic_client, "call_forced_tool", side_effect=fake_call_forced_tool
    ):
        remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    assert "wiki/house/plants.md" in captured["user_message"]
    assert "Hydrangeas planted in the parking strip." in captured["user_message"]


def test_remember_updates_existing_page_with_conditional_write(s3_bucket, settings):
    wiki.put_file(BUCKET, "wiki/house/plants.md", "---\ntitle: Plants\n---\n\noriginal\n")

    updated = _fake_decision(
        action=PageAction.UPDATE,
        full_content="---\ntitle: Plants\n---\n\noriginal\n\n## Hydrangeas\nnew note\n",
    )
    with patch.object(remember.anthropic_client, "call_forced_tool", return_value=updated):
        result = remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    assert result.action == PageAction.UPDATE
    assert "new note" in wiki.get_file(BUCKET, "wiki/house/plants.md").content
    # index.md untouched for an update to an already-linked page
    assert wiki.get_file(BUCKET, "index.md").content == SEED_INDEX


def test_remember_does_not_relink_an_already_linked_page(s3_bucket, settings):
    already_linked_index = remember._ensure_linked(SEED_INDEX, "wiki/house/plants.md", "Plants")
    wiki.put_file(BUCKET, "index.md", already_linked_index)
    wiki.put_file(BUCKET, "wiki/house/plants.md", "---\ntitle: Plants\n---\n\noriginal\n")

    # even though the decision says "create", the page already exists and is
    # already linked — the conditional write on it must succeed (right etag
    # picked up) rather than raising ConditionalWriteFailed
    with patch.object(remember.anthropic_client, "call_forced_tool", return_value=_fake_decision()):
        result = remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    assert result.page == "wiki/house/plants.md"
    assert wiki.get_file(BUCKET, "index.md").content.count("plants.md") == 1


def test_remember_propagates_invalid_decision_before_writing(s3_bucket, settings):
    # call_forced_tool validates FileNoteDecision the moment the model
    # responds, before remember() does anything else — a bad page_path never
    # becomes a usable decision, so nothing gets written. Uses the real
    # FileNoteDecision validation (not a hand-rolled error) to match exactly
    # what call_forced_tool actually does.
    def raise_on_call(*_args, **_kwargs):
        return FileNoteDecision(**_decision_fields(page_path="not-a-wiki-page.txt"))

    with (
        patch.object(remember.anthropic_client, "call_forced_tool", side_effect=raise_on_call),
        pytest.raises(ValidationError),
    ):
        remember.remember(settings, "fake-api-key", "hydrangeas struggling")

    assert not wiki.file_exists(BUCKET, "not-a-wiki-page.txt")
