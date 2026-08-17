import pytest
from pydantic import TypeAdapter, ValidationError

from victoria.core.storage.models import WikiPath

_wiki_path = TypeAdapter(WikiPath)


@pytest.mark.parametrize(
    "path",
    [
        "CONVENTIONS.md",
        "index.md",
        "log.md",
        "wiki/house/plants.md",
        "wiki/business/hours.md",
        "wiki/house/tools/power-tools.md",  # a split category page
    ],
)
def test_accepts_valid_wiki_paths(path):
    assert _wiki_path.validate_python(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "search.db",  # binary sidecar, not a page path
        "wiki/house/plants",  # missing .md
        "wiki/garage/tools.md",  # not house or business
        "../etc/passwd",  # traversal
        "/wiki/house/plants.md",  # leading slash
        "",
    ],
)
def test_rejects_invalid_wiki_paths(path):
    with pytest.raises(ValidationError):
        _wiki_path.validate_python(path)
