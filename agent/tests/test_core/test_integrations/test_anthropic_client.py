from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from victoria.core import observability
from victoria.core.integrations import anthropic_client

TOOL = {"name": "file_note", "description": "d", "input_schema": {"type": "object"}}


class Decision(BaseModel):
    page: str


def _response(block, *, stop_reason="tool_use"):
    return SimpleNamespace(
        content=[block],
        usage=SimpleNamespace(input_tokens=120, output_tokens=45),
        stop_reason=stop_reason,
        _request_id="req_123",
    )


def test_call_forced_tool_logs_usage_and_request_id():
    block = SimpleNamespace(type="tool_use", name="file_note", input={"page": "wiki/a.md"})
    client = MagicMock()
    client.messages.create.return_value = _response(block)

    with patch.object(observability, "logger") as logger:
        result = anthropic_client.call_forced_tool(
            client,
            model="m",
            system="s",
            user_message="u",
            tool=TOOL,
            response_model=Decision,
        )

    assert result.page == "wiki/a.md"
    finished = logger.info.call_args_list[-1]
    assert finished.kwargs == {
        "stage": "anthropic_call",
        "duration_ms": finished.kwargs["duration_ms"],
        "model": "m",
        "tool": "file_note",
        "input_tokens": 120,
        "output_tokens": 45,
        "stop_reason": "tool_use",
        "request_id": "req_123",
    }


def test_run_tool_loop_logs_each_iteration():
    tool_block = SimpleNamespace(type="tool_use", name="t", id="tu_1", input={})
    text_block = SimpleNamespace(type="text", text="done")
    client = MagicMock()
    client.messages.create.side_effect = [
        _response(tool_block),
        _response(text_block, stop_reason="end_turn"),
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
