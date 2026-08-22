import time
from unittest.mock import Mock, patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from victoria.mcp.server import build_app

ISSUER_URL = "https://lasso.example.com"
RESOURCE_SERVER_URL = "https://victoria.example.com"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _app():
    return build_app(lasso_issuer_url=ISSUER_URL, resource_server_url=RESOURCE_SERVER_URL)


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
    return patch("victoria.mcp.auth.PyJWKClient.get_signing_key_from_jwt", return_value=signing_key)


def test_rejects_missing_bearer_token():
    with _patch_jwks(), TestClient(_app()) as client:
        response = client.post("/mcp", json={})
    assert response.status_code == 401


def test_rejects_token_with_wrong_audience():
    with _patch_jwks(), TestClient(_app()) as client:
        response = client.post(
            "/mcp",
            json={},
            headers={
                "Authorization": f"Bearer {_token(audience='https://someone-else.example.com')}"
            },
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
