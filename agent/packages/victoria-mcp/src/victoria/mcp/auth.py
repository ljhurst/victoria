from mcp.server.auth.provider import AccessToken, TokenVerifier
from victoria.core.auth import LassoTokenValidator


class LassoTokenVerifier(TokenVerifier):
    def __init__(self, *, issuer_url: str, resource_server_url: str) -> None:
        self._resource_server_url = resource_server_url
        self._validator = LassoTokenValidator(issuer_url=issuer_url, audience=resource_server_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        verified = self._validator.validate(token)
        if verified is None:
            return None

        return AccessToken(
            token=verified.token,
            client_id=verified.client_id,
            scopes=verified.scopes,
            expires_at=verified.expires_at,
            resource=self._resource_server_url,
            subject=verified.subject,
            claims=verified.claims,
        )
