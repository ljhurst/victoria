"""The browser side of the Lasso OAuth 2.1 dance: authorization-code + PKCE
to log a human in, then verify the access token they came back with. The MCP
server only ever verifies tokens; the viewer also has to acquire them.
"""

import base64
import hashlib
import logging
import secrets

import httpx
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from victoria.core.auth import LassoTokenValidator, VerifiedToken
from victoria.viewer.config import ViewerSettings

logger = logging.getLogger(__name__)


class OAuthTokens(BaseModel):
    access_token: str
    id_token: str | None = None


READ_SCOPE = "victoria:read"

_discovery: dict[str, dict] = {}
_validators: dict[str, LassoTokenValidator] = {}


def new_pkce_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def authorize_url(settings: ViewerSettings, *, state: str, verifier: str) -> str:
    endpoints = await _discover(settings.lasso_issuer_url)
    params = {
        "response_type": "code",
        "client_id": settings.lasso_client_id,
        "redirect_uri": settings.redirect_uri,
        "scope": f"openid {READ_SCOPE}",
        "state": state,
        "code_challenge": pkce_challenge(verifier),
        "code_challenge_method": "S256",
        "resource": settings.resource_indicator,
    }
    return str(httpx.URL(endpoints["authorization_endpoint"], params=params))


async def exchange_code(settings: ViewerSettings, *, code: str, verifier: str) -> OAuthTokens:
    endpoints = await _discover(settings.lasso_issuer_url)
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            endpoints["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.redirect_uri,
                "client_id": settings.lasso_client_id,
                "code_verifier": verifier,
                # RFC 8707 wants the resource on the token request too, not
                # just at authorize — without it Lasso hands back an opaque
                # token with no victoria scope instead of the audience-bound JWT.
                "resource": settings.resource_indicator,
            },
        )
        response.raise_for_status()
        return OAuthTokens.model_validate(response.json())


async def logout_url(settings: ViewerSettings, *, id_token: str) -> str:
    endpoints = await _discover(settings.lasso_issuer_url)
    params = {
        "id_token_hint": id_token,
        "post_logout_redirect_uri": f"{settings.viewer_base_url.rstrip('/')}/logged-out",
    }
    return str(httpx.URL(endpoints["end_session_endpoint"], params=params))


async def verify_read_token(settings: ViewerSettings, token: str) -> VerifiedToken | None:
    """Returns the token only if it's valid, audience-bound to the viewer,
    and carries the read scope."""
    verified = await run_in_threadpool(_validator(settings).validate, token)
    if verified is None:
        return None
    if READ_SCOPE not in verified.scopes:
        logger.warning(
            "token verified but missing %s (client=%s, scopes=%s)",
            READ_SCOPE,
            verified.client_id,
            verified.scopes,
        )
        return None
    return verified


async def _discover(issuer_url: str) -> dict:
    if issuer_url not in _discovery:
        url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            _discovery[issuer_url] = response.json()
    return _discovery[issuer_url]


def _validator(settings: ViewerSettings) -> LassoTokenValidator:
    if settings.lasso_issuer_url not in _validators:
        _validators[settings.lasso_issuer_url] = LassoTokenValidator(
            issuer_url=settings.lasso_issuer_url, audience=settings.resource_indicator
        )
    return _validators[settings.lasso_issuer_url]
