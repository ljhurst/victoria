"""MCP transport auth (DESIGN §5).

Auth is `static_headers` — a fixed bearer token checked against SSM on every
request, not OAuth. Deliberately not using the mcp SDK's built-in
token_verifier/auth machinery: that path is wired for the OAuth Protected
Resource Metadata flow (it requires an issuer_url and serves
.well-known/oauth-protected-resource), which is exactly the Authorization
Server infrastructure static_headers exists to avoid — Victoria has no
existing identity provider and no multi-tenancy to justify standing one up
(DESIGN §5). A plain ASGI middleware that checks the header is simpler and
matches what static_headers actually is.
"""

import hmac

from aws_lambda_powertools.utilities import parameters
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """Checks Authorization: Bearer <token> against the SSM-stored static
    credential on every HTTP request. Not OAuth — see module docstring."""

    def __init__(self, app: ASGIApp, ssm_param: str) -> None:
        self.app = app
        self.ssm_param = ssm_param

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = _bearer_token(Request(scope))
        expected = parameters.get_parameter(self.ssm_param, decrypt=True)
        if not token or not hmac.compare_digest(token, expected):
            response = PlainTextResponse(
                "Unauthorized", status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")

    if not header.lower().startswith("bearer "):
        return None

    return header[len("bearer ") :].strip()
