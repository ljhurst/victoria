from unittest.mock import patch

from starlette.testclient import TestClient

from victoria.mcp.server import build_app

SSM_PARAM = "/victoria/mcp-auth-token"


def _app():
    return build_app(mcp_auth_param=SSM_PARAM)


def test_rejects_missing_bearer_token():
    with (
        patch("victoria.mcp.auth.parameters.get_parameter", return_value="secret-token"),
        TestClient(_app()) as client,
    ):
        response = client.post("/mcp", json={})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_rejects_wrong_bearer_token():
    with (
        patch("victoria.mcp.auth.parameters.get_parameter", return_value="secret-token"),
        TestClient(_app()) as client,
    ):
        response = client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_accepts_correct_bearer_token_and_reaches_the_app():
    with (
        patch("victoria.mcp.auth.parameters.get_parameter", return_value="secret-token"),
        TestClient(_app()) as client,
    ):
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={
                "Authorization": "Bearer secret-token",
                "Accept": "application/json, text/event-stream",
            },
        )
    # a wrong/missing token gets 401 from our middleware before reaching the
    # MCP app at all; a correct token reaching the app (any non-401 response,
    # even a protocol-level error from the stub request) proves the
    # middleware let it through.
    assert response.status_code != 401
