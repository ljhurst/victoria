from datetime import date

import pytest

from victoria.core.pages import frontmatter

PAGE = "---\ntitle: Recipes\ntags: [cooking, baking]\nlast-updated: 2026-10-01\n---\n\n## Cookies\n"


def test_reads_title_and_tags():
    assert frontmatter.page_title(PAGE, "fallback") == "Recipes"
    assert frontmatter.page_tags(PAGE) == ["cooking", "baking"]


def test_quoted_and_odd_tags():
    content = '---\ntitle: "Cookies: big"\ntags: ["cowboy cookies", 5]\n---\n'

    assert frontmatter.page_title(content, "x") == "Cookies: big"
    assert frontmatter.page_tags(content) == ["cowboy cookies", "5"]


@pytest.mark.parametrize(
    "content",
    ["no frontmatter", "---\n: : bad yaml [\n---\n", "---\n- just\n- a list\n---\n"],
    ids=["none", "bad-yaml", "not-a-mapping"],
)
def test_falls_back_when_frontmatter_is_missing_or_unreadable(content):
    assert frontmatter.page_title(content, "wiki/x/y.md") == "wiki/x/y.md"
    assert frontmatter.page_tags(content) == []


def test_body_is_the_text_below_the_frontmatter():
    assert frontmatter.body(PAGE) == "\n## Cookies\n"
    assert frontmatter.body("just text\n") == "just text\n"


def test_sets_last_updated():
    content = frontmatter.with_last_updated(PAGE, date(2026, 10, 24))

    assert "last-updated: 2026-10-24" in content
    assert "2026-10-01" not in content
    assert content.endswith("## Cookies\n")


def test_adds_last_updated_when_the_frontmatter_lacks_it():
    content = frontmatter.with_last_updated(
        "---\ntitle: Recipes\n---\n\nbody\n", date(2026, 10, 24)
    )

    assert content == "---\ntitle: Recipes\nlast-updated: 2026-10-24\n---\n\nbody\n"


def test_leaves_a_page_without_frontmatter_alone():
    assert frontmatter.with_last_updated("just text\n", date(2026, 10, 24)) == "just text\n"
