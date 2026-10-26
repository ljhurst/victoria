import time
from unittest.mock import Mock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKClientError
from starlette.testclient import TestClient

from victoria.core import auth as core_auth
from victoria.core import observability
from victoria.mcp.auth import get_lasso_validator
from victoria.mcp.config import get_mcp_settings
from victoria.mcp.server import build_app

ISSUER_URL = "https://lasso.example.com"
RESOURCE_SERVER_URL = "https://victoria.example.com"
RETIRED_RESOURCE_URL = "https://abc123.lambda-url.us-east-1.on.aws/"

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


def _app():
    return build_app()


def _token(*, issuer=ISSUER_URL, audience=RESOURCE_SERVER_URL, expires_in=3600, **extra_claims):
    claims = {
        "iss": issuer,
        "aud": audience,
        "client_id": "claude-mcp",
        "sub": "claude-mcp",
        "scope": "victoria:read victoria:write",
        "exp": int(time.time()) + expires_in,
        **extra_claims,
    }
    return jwt.encode(claims, _private_key, algorithm="RS256")


def _patch_jwks():
    """Stubs JWKS resolution so tests never hit the network — the signing
    key returned is always this module's test key, so signature checks
    still run for real against tokens signed with it."""
    signing_key = Mock(key=_private_key.public_key())
    return patch(
        "victoria.core.auth.PyJWKClient.get_signing_key_from_jwt", return_value=signing_key
    )


def test_rejects_missing_bearer_token():
    with _patch_jwks(), TestClient(_app()) as client:
        response = client.post("/mcp", json={})
    assert response.status_code == 401


@pytest.mark.parametrize("audience", ["https://someone-else.example.com", RETIRED_RESOURCE_URL])
def test_rejects_token_with_wrong_audience(audience):
    with _patch_jwks(), TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={},
            headers={"Authorization": f"Bearer {_token(audience=audience)}"},
        )
    assert response.status_code == 401


def test_rejects_token_with_wrong_issuer():
    with _patch_jwks(), TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={},
            headers={"Authorization": f"Bearer {_token(issuer='https://not-lasso.example.com')}"},
        )
    assert response.status_code == 401


def test_rejects_expired_token():
    with _patch_jwks(), TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={},
            headers={"Authorization": f"Bearer {_token(expires_in=-60)}"},
        )
    assert response.status_code == 401


def test_rejects_token_signed_by_a_different_key():
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {
            "iss": ISSUER_URL,
            "aud": RESOURCE_SERVER_URL,
            "client_id": "claude-mcp",
            "sub": "claude-mcp",
            "scope": "victoria:read",
            "exp": int(time.time()) + 3600,
        },
        other_key,
        algorithm="RS256",
    )
    with _patch_jwks(), TestClient(_app()) as client:
        response = client.post("/mcp", json={}, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_accepts_correct_token_and_reaches_the_app():
    with _patch_jwks(), TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={
                "Authorization": f"Bearer {_token()}",
                "Accept": "application/json, text/event-stream",
            },
        )
    # a bad/missing token gets 401 from our verifier before reaching the MCP
    # app at all; a valid token reaching the app (any non-401 response, even
    # a protocol-level error from the stub request) proves it let it through.
    assert response.status_code != 401


def test_serves_protected_resource_metadata():
    with TestClient(_app()) as client:
        response = client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == RESOURCE_SERVER_URL
    assert ISSUER_URL in body["authorization_servers"]


def test_successful_verification_logs_the_signing_key_stage():
    with (
        _patch_jwks(),
        patch.object(observability, "logger") as logger,
        TestClient(_app()) as client,
    ):
        client.post("/mcp", headers={"Authorization": f"Bearer {_token()}"}, json={})

    finished = [
        c.kwargs["stage"] for c in logger.info.call_args_list if c.args == ("stage finished",)
    ]
    assert "lasso_signing_key" in finished


def test_failed_signing_key_lookup_is_rejected_and_logged():
    with (
        patch.object(observability, "logger") as logger,
        patch.object(core_auth, "logger") as auth_logger,
        patch(
            "victoria.core.auth.PyJWKClient.get_signing_key_from_jwt",
            side_effect=PyJWKClientError("lasso unreachable"),
        ),
        TestClient(_app()) as client,
    ):
        response = client.post("/mcp", headers={"Authorization": f"Bearer {_token()}"}, json={})

    assert response.status_code == 401
    (failed,) = logger.error.call_args_list
    assert failed.kwargs["stage"] == "lasso_signing_key"
    assert failed.kwargs["error"] == "PyJWKClientError"
    auth_logger.warning.assert_called_once_with(
        "token rejected", error="PyJWKClientError", reason="lasso unreachable"
    )


def test_does_not_advertise_list_changed_notifications():
    """Clients open a long-lived subscription stream for change notifications,
    which a buffered Lambda response can never finish, so none are advertised."""
    protocol_version = "2026-07-28"
    envelope = {
        "io.modelcontextprotocol/protocolVersion": protocol_version,
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    with _patch_jwks(), TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "server/discover",
                "params": {"_meta": envelope},
            },
            headers={
                "Authorization": f"Bearer {_token()}",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": protocol_version,
                "Mcp-Method": "server/discover",
            },
        )

    assert response.status_code == 200
    assert response.json()["result"]["capabilities"]["tools"]["listChanged"] is False


def test_rebuilding_the_app_reuses_one_jwks_client():
    with patch("victoria.core.auth.PyJWKClient") as jwks_client:
        _app()
        _app()

    jwks_client.assert_called_once()
