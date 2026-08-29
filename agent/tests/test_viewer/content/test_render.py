from victoria.viewer.content.render import render_page


def test_title_from_frontmatter():
    page = render_page("wiki/house/tools.md", "---\ntitle: Tools\ntags: [garage]\n---\n\nbody\n")
    assert page.title == "Tools"
    assert "tags:" not in page.html


def test_title_falls_back_to_first_heading():
    page = render_page("wiki/house/tools.md", "# My Heading\n\ntext\n")
    assert page.title == "My Heading"


def test_relative_md_links_are_rewritten_to_browse_routes():
    page = render_page("wiki/house/tools.md", "[p](plants.md#hydrangeas) [s](tools/hand.md)\n")
    assert 'href="/browse/wiki/house/plants.md#hydrangeas"' in page.html
    assert 'href="/browse/wiki/house/tools/hand.md"' in page.html


def test_external_and_anchor_links_are_left_alone():
    page = render_page("index.md", "[x](https://example.com) [a](#section)\n")
    assert 'href="https://example.com"' in page.html
    assert 'href="#section"' in page.html


def test_headings_get_anchor_ids():
    page = render_page("index.md", "## Parking Strip\n")
    assert 'id="parking-strip"' in page.html
