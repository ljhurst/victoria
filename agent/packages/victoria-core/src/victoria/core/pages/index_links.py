import re

from victoria.core.storage import wiki
from victoria.core.storage.models import WikiPath


def domain_headings(index_md: str) -> dict[str, str]:
    headings = re.findall(r"^## (.+?)\s*$", index_md, flags=re.MULTILINE)
    return {_domain_slug(heading): f"## {heading}" for heading in headings}


def ensure_linked(index_md: str, page_path: str, title: str) -> str:
    if f"({page_path})" in index_md:
        return index_md
    heading = _domain_heading(index_md, page_path)
    link_line = f"- [{title}]({page_path})"
    placeholder = "_(no pages yet — created by `remember` as topics come up)_"

    if heading not in index_md:
        return index_md.rstrip("\n") + f"\n\n{heading}\n\n{link_line}\n"

    head, rest = index_md.split(heading, 1)
    if "\n## " in rest:
        section, tail = rest.split("\n## ", 1)
        tail = "## " + tail
    else:
        section, tail = rest, ""

    entry_lines = [
        line for line in section.splitlines() if line.strip() and line.strip() != placeholder
    ]
    entry_lines.append(link_line)
    new_section = "\n\n" + "\n".join(entry_lines) + "\n\n"

    return head + heading + new_section + tail


def link_in_index(bucket: str, index_key: WikiPath, page_path: str, title: str) -> None:
    index_page = wiki.get_file_with_etag(bucket, index_key)
    updated_index = ensure_linked(index_page.content, page_path, title)
    if updated_index != index_page.content:
        wiki.put_file(bucket, index_key, updated_index, if_match=index_page.etag)


def _domain_slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def _domain_heading(index_md: str, page_path: str) -> str:
    domain = page_path.split("/")[1]
    return domain_headings(index_md).get(domain, f"## {domain.replace('-', ' ').title()}")
