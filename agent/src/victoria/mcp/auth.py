import jwt
from aws_lambda_powertools import Logger
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier

logger = Logger()


class LassoTokenVerifier(TokenVerifier):
    def __init__(self, *, issuer_url: str, resource_server_url: str) -> None:
        self._issuer_url = issuer_url
        self._resource_server_url = resource_server_url
        self._jwks_client = PyJWKClient(f"{issuer_url.rstrip('/')}/jwks")

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer_url,
                audience=self._resource_server_url,
            )
        except jwt.PyJWTError:
            logger.exception("LassoTokenVerifier rejected token")
            return None

        return AccessToken(
            token=token,
            client_id=claims["client_id"],
            scopes=claims.get("scope", "").split(),
            expires_at=claims.get("exp"),
            resource=self._resource_server_url,
            subject=claims.get("sub"),
            claims=claims,
        )
