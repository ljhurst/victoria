"""Lasso access-token verification, shared by the MCP server's resource-server
check and the viewer's session guard. Signature/`iss`/`aud`/`exp` are all
verified against Lasso's published JWKS — nothing here needs a secret.
"""

import logging

import jwt
from jwt import PyJWKClient, PyJWKClientError
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class VerifiedToken(BaseModel):
    token: str
    client_id: str
    subject: str | None
    scopes: list[str]
    expires_at: int | None
    claims: dict


class LassoTokenValidator:
    def __init__(self, *, issuer_url: str, audience: str) -> None:
        self._issuer_url = issuer_url
        self._audience = audience
        self._jwks_client = PyJWKClient(f"{issuer_url.rstrip('/')}/jwks")

    def validate(self, token: str) -> VerifiedToken | None:
        """Returns the verified token, or None if it fails any check."""
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer_url,
                audience=self._audience,
                leeway=60,
            )
        except (jwt.PyJWTError, PyJWKClientError) as e:
            logger.warning("Lasso token rejected: %s: %s", type(e).__name__, e)
            return None

        return VerifiedToken(
            token=token,
            client_id=claims["client_id"],
            subject=claims.get("sub"),
            scopes=claims.get("scope", "").split(),
            expires_at=claims.get("exp"),
            claims=claims,
        )
