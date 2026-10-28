import json
import time
from unittest.mock import Mock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from victoria.mcp.auth import get_lasso_validator
from victoria.mcp.config import get_mcp_settings
from victoria.mcp.server import build_app

ISSUER_URL = "https://lasso.example.com"
RESOURCE_SERVER_URL = "https://victoria.example.com"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _mcp_env(monkeypatch):
    monkeypatch.setenv("LASSO_ISSUER_URL", ISSUER_URL)
    monkeypatch.setenv("VICTORIA_RESOURCE_URL", RESOURCE_SERVER_URL)
    get_mcp_settings.cache_clear()
    get_lasso_validator.cache_clear()
    yield
    get_mcp_settings.cache_clear()
    get_lasso_validator.cache_clear()


def test_only_the_read_tools_are_marked_read_only():
    token = jwt.encode(
        {
            "iss": ISSUER_URL,
            "aud": RESOURCE_SERVER_URL,
            "sub": "claude-mcp",
            "client_id": "claude-mcp",
            "scope": "victoria:read victoria:write",
            "exp": int(time.time()) + 3600,
        },
        _private_key,
        algorithm="RS256",
    )
    signing_key = Mock(key=_private_key.public_key())

    with (
        patch("victoria.core.auth.PyJWKClient.get_signing_key_from_jwt", return_value=signing_key),
        TestClient(build_app()) as client,
    ):
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
            },
        )

    data = next(line for line in response.text.splitlines() if line.startswith("data:"))
    tools = {
        tool["name"]: tool for tool in json.loads(data.removeprefix("data:"))["result"]["tools"]
    }
    read_only = {
        name for name, tool in tools.items() if (tool.get("annotations") or {}).get("readOnlyHint")
    }
    assert set(tools) == {"list_files", "get_file", "search_wiki", "remember", "consolidate"}
    assert read_only == {"list_files", "get_file", "search_wiki"}
