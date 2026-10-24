from datetime import date
from typing import Any

from pydantic import ValidationError

from victoria.core.integrations.models import ToolCall
from victoria.core.pages import frontmatter
from victoria.core.pages.models import (
    Create,
    EditCommand,
    EditedPage,
    PageAction,
    PageEdits,
    StrReplace,
)
from victoria.core.storage.models import PageVersion, WikiPath

EDITOR_TOOL_NAME = "str_replace_based_edit_tool"
NOTE_TOOL_NAME = "file_note"


class EditError(Exception):
    """The model's edits can't be applied. Nothing has been written."""


class PageNotShownError(EditError):
    """The edit needs a page the model wasn't shown (an update to an unseen
    page, or a create over an existing one). Showing it on a retry fixes it."""

    def __init__(self, path: WikiPath, message: str) -> None:
        super().__init__(message)
        self.path = path


def parse_edits(calls: list[ToolCall]) -> PageEdits:
    """Turn the model's tool calls into typed edits, rejecting anything that
    isn't an exact-text edit or a create."""
    commands: list[EditCommand] = []
    note: dict[str, Any] | None = None
    for call in calls:
        if call.name == NOTE_TOOL_NAME:
            note = call.input
        elif call.name == EDITOR_TOOL_NAME:
            commands.append(_parse_command(call.input))
        else:
            raise EditError(f"unknown tool {call.name!r}")

    if not commands:
        raise EditError("no edit was made; call str_replace or create")
    if note is None:
        raise EditError("file_note was not called")

    return PageEdits(
        commands=commands,
        summary=note["summary"],
        page_getting_large=bool(note.get("page_getting_large", False)),
    )


def apply_edits(
    shown: list[PageVersion], commands: list[EditCommand], *, today: date
) -> EditedPage:
    """Apply the edits to the page they target, taken from the pages the model
    was shown. All-or-nothing: any problem raises before a byte is written."""
    paths = {command.path for command in commands}
    if len(paths) != 1:
        raise EditError(f"edits must target exactly one page, got {sorted(paths)}")
    (path,) = paths
    base = next((page for page in shown if page.path == path), None)

    first = commands[0]
    if isinstance(first, Create):
        if len(commands) > 1:
            raise EditError("a new page is a single create command")
        if base is not None:
            raise EditError(f"{path} already exists; update it with str_replace")
        action, content = PageAction.CREATE, first.file_text
    else:
        action, content = PageAction.UPDATE, _replace(base, commands, path)

    content = frontmatter.with_last_updated(content, today)
    return EditedPage(
        path=path,
        action=action,
        content=content,
        base_etag=base.etag if base else None,
        title=frontmatter.page_title(content, path),
        tags=frontmatter.page_tags(content),
    )


def _replace(base: PageVersion | None, commands: list[EditCommand], path: WikiPath) -> str:
    if base is None:
        raise PageNotShownError(path, f"{path} was not shown; its text is needed to edit it")

    text = base.content
    for command in commands:
        if not isinstance(command, StrReplace):
            raise EditError("a page is either created or edited, not both")
        count = text.count(command.old_str)
        if count != 1:
            raise EditError(
                f"old_str {command.old_str[:80]!r} matched {count} times in {path}; "
                "it must match exactly once, copied exactly"
            )
        text = text.replace(command.old_str, command.new_str, 1)

    if frontmatter.body(text) == frontmatter.body(base.content):
        raise EditError(
            "the edits left the page's text unchanged; add the note's facts below the "
            "frontmatter with str_replace"
        )
    return text


def _parse_command(tool_input: dict[str, Any]) -> EditCommand:
    command = tool_input.get("command")
    path = str(tool_input.get("path", "")).lstrip("/")
    try:
        if command == "str_replace":
            return StrReplace(
                path=path,
                old_str=tool_input["old_str"],
                new_str=tool_input.get("new_str", ""),
            )
        if command == "create":
            return Create(path=path, file_text=tool_input["file_text"])
    except (ValidationError, KeyError) as e:
        raise EditError(
            f"invalid {command} command for path {path!r}: pages live at "
            "wiki/<domain>/<name>.md (no leading slash) and every field is required"
        ) from e
    raise EditError(f"the {command!r} command isn't available; use str_replace or create")
