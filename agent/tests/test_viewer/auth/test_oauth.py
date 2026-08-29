import asyncio

import pytest

from victoria.viewer.auth import oauth
from victoria.viewer.config import ViewerSettings

SETTINGS = ViewerSettings(
    WIKI_BUCKET="b",
    LASSO_ISSUER_URL="https://lasso.example.com/",
    VIEWER_BASE_URL="http://localhost:8000",
    VIEWER_RESOURCE_URL="https://viewer.example.com/",
    VIEWER_SESSION_SECRET="x",
)


@pytest.fixture(autouse=True)
def _stub_discovery(monkeypatch):
    async def _endpoints(_issuer):
        return {
            "authorization_endpoint": "https://lasso.example.com/auth",
            "token_endpoint": "https://lasso.example.com/token",
            "end_session_endpoint": "https://lasso.example.com/session/end",
        }

    monkeypatch.setattr(oauth, "_discover", _endpoints)


def test_authorize_url_carries_pkce_and_resource():
    url = asyncio.run(oauth.authorize_url(SETTINGS, state="st", verifier="v"))
    assert "code_challenge=" in url and "code_challenge_method=S256" in url
    assert "resource=https%3A%2F%2Fviewer.example.com%2F" in url
    assert "scope=openid+victoria%3Aread" in url


def test_exchange_code_sends_resource_on_the_token_request(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "tok", "id_token": "idt", "token_type": "Bearer"}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def post(self, _url, data):
            captured.update(data)
            return _Resp()

    monkeypatch.setattr(oauth.httpx, "AsyncClient", lambda **_: _Client())

    tokens = asyncio.run(oauth.exchange_code(SETTINGS, code="c", verifier="v"))

    assert tokens.access_token == "tok"
    assert tokens.id_token == "idt"
    assert captured["resource"] == "https://viewer.example.com/"
    assert captured["code_verifier"] == "v"


def test_logout_url_points_at_end_session_with_hint_and_redirect():
    url = asyncio.run(oauth.logout_url(SETTINGS, id_token="idt"))
    assert url.startswith("https://lasso.example.com/session/end?")
    assert "id_token_hint=idt" in url
    assert "post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Flogged-out" in url
