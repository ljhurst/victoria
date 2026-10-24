from datetime import date

import pytest

from victoria.core.integrations.anthropic_client import ToolCall
from victoria.core.operations import page_edits
from victoria.core.operations.models import Create, PageAction, StrReplace
from victoria.core.storage.models import PageVersion

TODAY = date(2026, 10, 24)
PATH = "wiki/personal/recipes.md"
PAGE = PageVersion(
    path=PATH,
    etag='"v1"',
    content=(
        "---\ntitle: Recipes\ntags: [cooking, baking]\nlast-updated: 2026-10-01\n---\n\n"
        "## Cookies\n\n- 350F, 12 minutes\n- Rest 5 minutes\n\n## Soup\n\n- Simmer 30 minutes\n"
    ),
)


def _replace(old, new, path=PATH):
    return StrReplace(path=path, old_str=old, new_str=new)


def _call(command, **fields):
    return ToolCall(name="str_replace_based_edit_tool", input={"command": command, **fields})


def _note(**fields):
    return ToolCall(name="file_note", input={"summary": "filed it", **fields})


class TestApplyEdits:
    def test_appends_to_a_section_and_leaves_everything_else_untouched(self):
        edit = _replace("- Rest 5 minutes", "- Rest 5 minutes\n- Crispy outside, chewy inside")

        path, action, content = page_edits.apply_edits(PAGE, [edit], today=TODAY)

        assert (path, action) == (PATH, PageAction.UPDATE)
        assert "- Rest 5 minutes\n- Crispy outside, chewy inside\n\n## Soup" in content
        untouched = PAGE.content.replace("last-updated: 2026-10-01", "last-updated: 2026-10-24")
        assert content.replace("\n- Crispy outside, chewy inside", "") == untouched

    def test_sets_last_updated_to_today(self):
        _, _, content = page_edits.apply_edits(PAGE, [_replace("30 minutes", "35")], today=TODAY)

        assert "last-updated: 2026-10-24" in content
        assert "2026-10-01" not in content

    def test_adds_last_updated_when_the_frontmatter_lacks_it(self):
        page = PageVersion(path=PATH, etag="e", content="---\ntitle: Recipes\n---\n\nbody\n")

        _, _, content = page_edits.apply_edits(page, [_replace("body", "body2")], today=TODAY)

        assert content.startswith("---\ntitle: Recipes\nlast-updated: 2026-10-24\n---\n")

    def test_page_without_frontmatter_is_left_without_one(self):
        page = PageVersion(path=PATH, etag="e", content="just text\n")

        _, _, content = page_edits.apply_edits(page, [_replace("text", "words")], today=TODAY)

        assert content == "just words\n"

    def test_edits_apply_in_order_to_the_text_so_far(self):
        edits = [_replace("12 minutes", "13 minutes"), _replace("13 minutes", "13-14 minutes")]

        _, _, content = page_edits.apply_edits(PAGE, edits, today=TODAY)

        assert "- 350F, 13-14 minutes" in content

    @pytest.mark.parametrize(
        ("old_str", "count"),
        [("not on the page", 0), ("minutes", 3), ("## ", 2)],
        ids=["no-match", "several-matches", "heading-prefix"],
    )
    def test_old_str_must_match_exactly_once(self, old_str, count):
        with pytest.raises(page_edits.EditError, match=f"matched {count} times"):
            page_edits.apply_edits(PAGE, [_replace(old_str, "x")], today=TODAY)

    def test_a_later_edit_failing_rejects_the_whole_set(self):
        edits = [_replace("12 minutes", "13 minutes"), _replace("not there", "x")]

        with pytest.raises(page_edits.EditError):
            page_edits.apply_edits(PAGE, edits, today=TODAY)

        assert "12 minutes" in PAGE.content

    @pytest.mark.parametrize(
        "edit",
        [
            _replace("last-updated: 2026-10-01", "last-updated: 2026-10-24"),
            _replace("title: Recipes", "title: All recipes"),
            _replace("- Rest 5 minutes", "- Rest 5 minutes"),
        ],
        ids=["date-only", "frontmatter-only", "no-op"],
    )
    def test_edits_that_leave_the_body_unchanged_are_rejected(self, edit):
        with pytest.raises(page_edits.EditError, match="left the page's text unchanged"):
            page_edits.apply_edits(PAGE, [edit], today=TODAY)

    def test_editing_a_page_that_was_not_shown_is_rejected(self):
        with pytest.raises(page_edits.PageNotShownError) as raised:
            page_edits.apply_edits(None, [_replace("a", "b")], today=TODAY)

        assert raised.value.path == PATH

    def test_creates_a_new_page(self):
        text = "---\ntitle: Plants\ntags: [garden]\nlast-updated: 2020-01-01\n---\n\n## Ferns\n"

        path, action, content = page_edits.apply_edits(
            None, [Create(path="wiki/house/plants.md", file_text=text)], today=TODAY
        )

        assert (path, action) == ("wiki/house/plants.md", PageAction.CREATE)
        assert "last-updated: 2026-10-24" in content
        assert content.endswith("## Ferns\n")

    def test_create_over_a_shown_page_is_rejected(self):
        with pytest.raises(page_edits.EditError, match="already exists"):
            page_edits.apply_edits(PAGE, [Create(path=PATH, file_text="x")], today=TODAY)

    def test_edits_must_target_one_page(self):
        edits = [_replace("a", "b"), _replace("a", "b", path="wiki/house/plants.md")]

        with pytest.raises(page_edits.EditError, match="exactly one page"):
            page_edits.apply_edits(PAGE, edits, today=TODAY)

    def test_create_cannot_be_combined_with_other_edits(self):
        edits = [Create(path=PATH, file_text="x"), _replace("a", "b")]

        with pytest.raises(page_edits.EditError, match="single create"):
            page_edits.apply_edits(None, edits, today=TODAY)

    def test_edit_after_create_is_rejected(self):
        edits = [_replace("Simmer", "Boil"), Create(path=PATH, file_text="x")]

        with pytest.raises(page_edits.EditError, match="created or edited"):
            page_edits.apply_edits(PAGE, edits, today=TODAY)


class TestFrontmatter:
    def test_reads_title_and_tags(self):
        assert page_edits.page_title(PAGE.content, "fallback") == "Recipes"
        assert page_edits.page_tags(PAGE.content) == ["cooking", "baking"]

    def test_quoted_and_odd_tags(self):
        content = '---\ntitle: "Cookies: big"\ntags: ["cowboy cookies", 5]\n---\n'

        assert page_edits.page_title(content, "x") == "Cookies: big"
        assert page_edits.page_tags(content) == ["cowboy cookies", "5"]

    @pytest.mark.parametrize(
        "content",
        ["no frontmatter", "---\n: : bad yaml [\n---\n", "---\n- just\n- a list\n---\n"],
        ids=["none", "bad-yaml", "not-a-mapping"],
    )
    def test_falls_back_when_frontmatter_is_missing_or_unreadable(self, content):
        assert page_edits.page_title(content, "wiki/x/y.md") == "wiki/x/y.md"
        assert page_edits.page_tags(content) == []


class TestParseEdits:
    def test_collects_edits_and_the_note(self):
        calls = [
            _note(page_getting_large=True),
            _call("str_replace", path=PATH, old_str="a", new_str="b"),
        ]

        edits = page_edits.parse_edits(calls)

        assert edits.commands == [StrReplace(path=PATH, old_str="a", new_str="b")]
        assert edits.summary == "filed it"
        assert edits.page_getting_large is True

    def test_create_and_a_replace_without_new_str(self):
        calls = [
            _note(),
            _call("create", path="wiki/house/plants.md", file_text="x"),
            _call("str_replace", path=PATH, old_str="a"),
        ]

        commands = page_edits.parse_edits(calls).commands

        assert commands == [
            Create(path="wiki/house/plants.md", file_text="x"),
            StrReplace(path=PATH, old_str="a", new_str=""),
        ]

    @pytest.mark.parametrize("command", ["insert", "view", "undo_edit", None])
    def test_rejects_commands_other_than_str_replace_and_create(self, command):
        calls = [_note(), _call(command, path=PATH)]

        with pytest.raises(page_edits.EditError, match="isn't available"):
            page_edits.parse_edits(calls)

    def test_strips_the_leading_slash_the_editor_tool_uses_for_paths(self):
        calls = [
            _note(),
            _call("create", path="/wiki/house/plants.md", file_text="x"),
        ]

        assert page_edits.parse_edits(calls).commands == [
            Create(path="wiki/house/plants.md", file_text="x")
        ]

    @pytest.mark.parametrize(
        "fields",
        [
            {"path": "plants.md", "file_text": "x"},
            {"path": "wiki/Bad Domain/x.md", "file_text": "x"},
            {"path": "wiki/house/plants.md"},
        ],
        ids=["not-a-wiki-path", "bad-domain", "missing-field"],
    )
    def test_an_invalid_command_is_a_retryable_edit_error(self, fields):
        with pytest.raises(page_edits.EditError, match="wiki/<domain>/<name>.md"):
            page_edits.parse_edits([_note(), _call("create", **fields)])

    def test_requires_an_edit(self):
        with pytest.raises(page_edits.EditError, match="no edit"):
            page_edits.parse_edits([_note()])

    def test_requires_the_note(self):
        with pytest.raises(page_edits.EditError, match="file_note"):
            page_edits.parse_edits([_call("create", path=PATH, file_text="x")])

    def test_rejects_unknown_tools(self):
        with pytest.raises(page_edits.EditError, match="unknown tool"):
            page_edits.parse_edits([ToolCall(name="bash", input={})])
