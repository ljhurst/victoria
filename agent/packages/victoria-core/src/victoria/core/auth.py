"""Lasso access-token verification, shared by the MCP server's resource-server
check and the viewer's session guard. Signature/`iss`/`aud`/`exp` are all
verified against Lasso's published JWKS — nothing here needs a secret.
"""

import jwt
from jwt import PyJWKClient
from pydantic import BaseModel


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
            )
        except jwt.PyJWTError:
            return None

        return VerifiedToken(
            token=token,
            client_id=claims["client_id"],
            subject=claims.get("sub"),
            scopes=claims.get("scope", "").split(),
            expires_at=claims.get("exp"),
            claims=claims,
        )
