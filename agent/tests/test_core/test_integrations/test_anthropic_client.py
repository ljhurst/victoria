from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from victoria.core import observability
from victoria.core.integrations import anthropic_client
from victoria.core.integrations.models import ToolCall

TOOL = {"name": "file_note", "description": "d", "input_schema": {"type": "object"}}


def _response(blocks, *, stop_reason="tool_use"):
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(input_tokens=120, output_tokens=45),
        stop_reason=stop_reason,
        _request_id="req_123",
    )


def _tool_use(name, **tool_input):
    return SimpleNamespace(type="tool_use", name=name, id="tu_1", input=tool_input)


def test_call_tools_returns_every_tool_call_and_logs_usage():
    client = MagicMock()
    client.messages.create.return_value = _response(
        [
            SimpleNamespace(type="text", text="ignored"),
            _tool_use("file_note", summary="s"),
            _tool_use("str_replace_based_edit_tool", command="create", path="p"),
        ]
    )

    with patch.object(observability, "logger") as logger:
        calls = anthropic_client.call_tools(
            client,
            model="m",
            system="s",
            user_message="u",
            tools=[{"name": "file_note"}, {"name": "str_replace_based_edit_tool"}],
        )

    assert calls == [
        ToolCall(name="file_note", input={"summary": "s"}),
        ToolCall(name="str_replace_based_edit_tool", input={"command": "create", "path": "p"}),
    ]
    assert client.messages.create.call_args.kwargs["tool_choice"] == {"type": "any"}
    finished = logger.info.call_args_list[-1].kwargs
    assert finished["tools"] == ["file_note", "str_replace_based_edit_tool"]
    assert (finished["input_tokens"], finished["output_tokens"]) == (120, 45)
    assert finished["stop_reason"] == "tool_use"
    assert finished["request_id"] == "req_123"


def test_call_tools_rejects_a_response_cut_off_mid_tool_call():
    client = MagicMock()
    client.messages.create.return_value = _response(
        [_tool_use("file_note", summary="s")], stop_reason="max_tokens"
    )

    with pytest.raises(RuntimeError, match="max_tokens"):
        anthropic_client.call_tools(client, model="m", system="s", user_message="u", tools=[])


def test_run_tool_loop_logs_each_iteration():
    tool_block = SimpleNamespace(type="tool_use", name="t", id="tu_1", input={})
    text_block = SimpleNamespace(type="text", text="done")
    client = MagicMock()
    client.messages.create.side_effect = [
        _response([tool_block]),
        _response([text_block], stop_reason="end_turn"),
    ]

    with patch.object(observability, "logger") as logger:
        anthropic_client.run_tool_loop(
            client,
            model="m",
            system="s",
            user_message="u",
            tools=[TOOL],
            dispatch=lambda name, args: "ok",
        )

    finished = [c.kwargs for c in logger.info.call_args_list if c.args == ("stage finished",)]
    assert [f["iteration"] for f in finished] == [0, 1]
    assert [f["stop_reason"] for f in finished] == ["tool_use", "end_turn"]
