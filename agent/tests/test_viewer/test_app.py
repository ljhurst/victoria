import base64
import json

import boto3
import pytest
from itsdangerous import TimestampSigner
from moto import mock_aws
from starlette.testclient import TestClient

from victoria.core.auth import VerifiedToken
from victoria.viewer import config
from victoria.viewer.app import build_app
from victoria.viewer.auth import oauth
from victoria.viewer.auth.oauth import OAuthTokens

BUCKET = "victoria-test"


@pytest.fixture(autouse=True)
def viewer_env(monkeypatch):
    monkeypatch.setenv("WIKI_BUCKET", BUCKET)
    monkeypatch.setenv("LASSO_ISSUER_URL", "https://lasso.example.com")
    monkeypatch.setenv("VIEWER_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("VIEWER_SESSION_SECRET", "test-secret")
    config.get_viewer_settings.cache_clear()
    config.get_session_secret.cache_clear()
    yield
    config.get_viewer_settings.cache_clear()
    config.get_session_secret.cache_clear()


@pytest.fixture
def wiki_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        client.put_object(Bucket=BUCKET, Key="index.md", Body=b"---\ntitle: Home\n---\n\n# Home\n")
        client.put_object(
            Bucket=BUCKET,
            Key="wiki/house/tools.md",
            Body=b"---\ntitle: Tools\n---\n\n# Tools\n\n[home](../../index.md)\n",
        )
        client.put_object(Bucket=BUCKET, Key="search.db", Body=b"\x00not markdown")
        yield client


def _verified_token():
    async def _ok(_settings, _token):
        return VerifiedToken(
            token="t",
            client_id="victoria-viewer",
            subject="luke",
            scopes=["victoria:read"],
            expires_at=None,
            claims={},
        )

    return _ok


@pytest.fixture
def authed(monkeypatch):
    monkeypatch.setattr(oauth, "verify_read_token", _verified_token())


def test_healthz_is_open():
    with TestClient(build_app()) as client:
        assert client.get("/healthz").text == "ok"


def test_unauthenticated_browse_redirects_to_login():
    with TestClient(build_app()) as client:
        response = client.get("/browse/index.md", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].endswith("/login")


def test_invalid_session_token_redirects_to_login(monkeypatch):
    async def _rejects(_settings, _token):
        return None

    monkeypatch.setattr(oauth, "verify_read_token", _rejects)
    with TestClient(build_app()) as client:
        client.cookies.set("session", _session_cookie({"access_token": "stale"}))
        response = client.get("/browse/index.md", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].endswith("/login")


def _stub_exchange(monkeypatch):
    async def _exchange(_settings, *, code, verifier):
        return OAuthTokens(access_token="fresh", id_token="idt")

    async def _discover(_issuer):
        return {"end_session_endpoint": "https://lasso.example.com/session/end"}

    monkeypatch.setattr(oauth, "exchange_code", _exchange)
    monkeypatch.setattr(oauth, "_discover", _discover)


def test_callback_with_a_scopeless_fresh_token_shows_denied(monkeypatch):
    async def _rejects(_settings, _token):
        return None

    _stub_exchange(monkeypatch)
    monkeypatch.setattr(oauth, "verify_read_token", _rejects)
    with TestClient(build_app()) as client:
        client.cookies.set("session", _session_cookie({"oauth": {"state": "s", "verifier": "v"}}))
        response = client.get("/auth/callback?code=c&state=s", follow_redirects=False)
    assert response.status_code == 403
    assert "victoria:read" in response.text


def test_callback_stores_tokens_and_redirects(monkeypatch):
    _stub_exchange(monkeypatch)
    monkeypatch.setattr(oauth, "verify_read_token", _verified_token())
    with TestClient(build_app()) as client:
        client.cookies.set("session", _session_cookie({"oauth": {"state": "s", "verifier": "v"}}))
        response = client.get("/auth/callback?code=c&state=s", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/browse/index.md"
        # the id_token is kept for RP-initiated logout
        logout = client.get("/logout", follow_redirects=False)
    assert logout.headers["location"].startswith("https://lasso.example.com/session/end")


def test_logout_without_a_session_goes_to_logged_out_page():
    with TestClient(build_app()) as client:
        response = client.get("/logout", follow_redirects=False)
    assert response.headers["location"] == "/logged-out"


def test_logged_out_page_is_open():
    with TestClient(build_app()) as client:
        response = client.get("/logged-out")
    assert response.status_code == 200
    assert "Signed out" in response.text


def test_browse_renders_page_and_sidebar(wiki_bucket, authed):
    with TestClient(build_app()) as client:
        client.cookies.set("session", _session_cookie({"access_token": "t"}))
        response = client.get("/browse/wiki/house/tools.md")
    assert response.status_code == 200
    assert "<h1" in response.text and "Tools" in response.text
    assert 'href="/browse/index.md"' in response.text  # sidebar link
    assert "search.db" not in response.text  # not a markdown page


def test_htmx_request_returns_fragment_only(wiki_bucket, authed):
    with TestClient(build_app()) as client:
        client.cookies.set("session", _session_cookie({"access_token": "t"}))
        response = client.get("/browse/index.md", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "<!doctype html>" not in response.text.lower()
    assert "markdown-body" in response.text


def test_missing_page_is_404(wiki_bucket, authed):
    with TestClient(build_app()) as client:
        client.cookies.set("session", _session_cookie({"access_token": "t"}))
        response = client.get("/browse/wiki/house/nope.md")
    assert response.status_code == 404


def _session_cookie(data: dict) -> str:
    """A signed session cookie in Starlette's SessionMiddleware format."""
    signer = TimestampSigner("test-secret")
    return signer.sign(base64.b64encode(json.dumps(data).encode())).decode()
