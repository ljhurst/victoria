from unittest.mock import patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http import TransportSecuritySettings
from starlette.testclient import TestClient

from victoria.core import observability
from victoria.mcp.tool_logging import log_tool_calls

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def echo(text: str) -> str:
    """Echo the text back."""
    return text


def explode(text: str) -> str:
    """Always fails."""
    raise ValueError("boom")


def ping() -> str:
    """Take no arguments."""
    return "pong"


@pytest.fixture
def client():
    server = MCPServer(name="test", middleware=[log_tool_calls])
    for tool in (echo, explode, ping):
        server.add_tool(tool)
    app = server.streamable_http_app(
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    with TestClient(app) as test_client:
        yield test_client


def _rpc(client, method, params=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    response = client.post("/mcp", headers=HEADERS, json=body)
    assert response.status_code == 200
    return response


def _finished(logger) -> list[dict]:
    return [c.kwargs for c in logger.info.call_args_list if c.args == ("stage finished",)]


def test_logs_tool_name_and_argument_sizes_not_values(client):
    with patch.object(observability, "logger") as logger:
        response = _rpc(client, "tools/call", {"name": "echo", "arguments": {"text": "secret"}})

    assert "secret" in response.text
    (started, _), (finished,) = logger.info.call_args_list[:2], _finished(logger)
    assert started.kwargs == {"stage": "tool_call", "tool": "echo", "arg_chars": {"text": 6}}
    assert finished["tool_error"] is False
    assert "secret" not in str(logger.mock_calls)


def test_tool_without_arguments(client):
    with patch.object(observability, "logger") as logger:
        _rpc(client, "tools/call", {"name": "ping"})

    (finished,) = _finished(logger)
    assert finished["tool"] == "ping"
    assert finished["arg_chars"] == {}
    assert finished["tool_error"] is False


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("explode", {"text": "x"}),
        ("echo", {}),
        ("no_such_tool", {}),
    ],
    ids=["tool-raises", "missing-argument", "unknown-tool"],
)
def test_flags_failed_tool_calls(client, name, arguments):
    with patch.object(observability, "logger") as logger:
        _rpc(client, "tools/call", {"name": name, "arguments": arguments})

    (finished,) = _finished(logger)
    assert finished["tool"] == name
    assert finished["tool_error"] is True


def test_ignores_other_methods(client):
    with patch.object(observability, "logger") as logger:
        response = _rpc(client, "tools/list")

    assert "echo" in response.text
    logger.info.assert_not_called()
