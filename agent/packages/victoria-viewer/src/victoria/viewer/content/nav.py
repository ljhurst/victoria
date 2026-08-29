"""Flat list of wiki page keys → the nested tree the sidebar renders."""

from pydantic import BaseModel

_ROOT_ORDER = {"index.md": 0, "CONVENTIONS.md": 1, "log.md": 2}


class TreeNode(BaseModel):
    name: str
    path: str | None = None
    children: list["TreeNode"] = []


def build_tree(paths: list[str]) -> list[TreeNode]:
    root: list[TreeNode] = []
    index: dict[str, TreeNode] = {}

    for path in sorted(paths, key=_sort_key):
        parts = path.split("/")
        prefix = ""
        siblings = root

        for depth, part in enumerate(parts):
            prefix = f"{prefix}/{part}" if prefix else part
            node = index.get(prefix)

            if node is None:
                is_leaf = depth == len(parts) - 1
                node = TreeNode(name=part, path=path if is_leaf else None)
                index[prefix] = node
                siblings.append(node)

            siblings = node.children

    return root


def _sort_key(path: str) -> tuple:
    return (_ROOT_ORDER.get(path, 3), path)
