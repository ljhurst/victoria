"""Turn a raw wiki page into HTML: pull the YAML frontmatter off for a title,
render the markdown body, and rewrite relative `*.md` links so they navigate
within the viewer instead of 404ing.
"""

import posixpath
import re

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from pydantic import BaseModel

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_HREF = re.compile(r'href="([^"]+)"')
_FIRST_HEADING = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_EXTERNAL = re.compile(r"\A([a-z][a-z0-9+.-]*:|//|#|/)")

_md = (
    MarkdownIt("commonmark", {"typographer": True})
    .enable(["table", "strikethrough"])
    .use(anchors_plugin, max_level=4)
)


class RenderedPage(BaseModel):
    path: str
    title: str
    html: str


def render_page(path: str, raw: str) -> RenderedPage:
    meta, body = _split_frontmatter(raw)

    title = _parse_title(meta, body, path)
    html = _rewrite_links(_md.render(body), path)

    return RenderedPage(path=path, title=str(title), html=html)


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    match = _FRONTMATTER.match(raw)
    if not match:
        return {}, raw
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), raw[match.end() :]


def _parse_title(meta: dict, body: str, path: str) -> str:
    return meta.get("title") or _first_heading(body) or path.rsplit("/", 1)[-1]


def _first_heading(body: str) -> str | None:
    match = _FIRST_HEADING.search(body)
    return match.group(1).strip() if match else None


def _rewrite_links(html: str, page_path: str) -> str:
    base_dir = posixpath.dirname(page_path)

    def _rewrite_link(match: re.Match) -> str:
        href = match.group(1)

        if _EXTERNAL.match(href):
            return match.group(0)

        target, sep, fragment = href.partition("#")

        if not target.endswith(".md"):
            return match.group(0)

        resolved = posixpath.normpath(posixpath.join(base_dir, target))

        return f'href="/browse/{resolved}{sep}{fragment}"'

    return _HREF.sub(_rewrite_link, html)
