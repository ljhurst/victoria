import re
from datetime import UTC, date, datetime
from typing import Any

import yaml

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_LAST_UPDATED = re.compile(r"^last-updated:.*$", re.MULTILINE)


def today() -> date:
    """The date stamped on pages as they are written."""
    return datetime.now(UTC).date()


def page_title(content: str, fallback: str) -> str:
    return str(_frontmatter(content).get("title") or fallback)


def page_tags(content: str) -> list[str]:
    tags = _frontmatter(content).get("tags") or []
    return [str(tag) for tag in tags] if isinstance(tags, list) else []


def body(content: str) -> str:
    """The page text below the frontmatter."""
    match = _FRONTMATTER.match(content)
    return content[match.end() :] if match else content


def with_last_updated(content: str, on: date) -> str:
    match = _FRONTMATTER.match(content)
    if match is None:
        return content

    line = f"last-updated: {on.isoformat()}"
    block = match.group(1)
    block = _LAST_UPDATED.sub(line, block) if _LAST_UPDATED.search(block) else f"{block}\n{line}"
    return f"---\n{block}\n---\n{content[match.end() :]}"


def _frontmatter(content: str) -> dict[str, Any]:
    match = _FRONTMATTER.match(content)
    if match is None:
        return {}
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}
