from starlette.types import ASGIApp, Message, Receive, Scope, Send

from victoria.core.observability import timed

_UNLOGGED_PATHS = frozenset({"/healthz"})


class RequestLoggingMiddleware:
    """Logs each HTTP request's method, path and response status. The query
    string is left out on purpose: the OAuth callback carries its code and
    state there."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _UNLOGGED_PATHS:
            await self._app(scope, receive, send)
            return

        with timed("request", method=scope["method"], path=scope["path"]) as extra:

            async def send_and_record_status(message: Message) -> None:
                if message["type"] == "http.response.start":
                    extra["status"] = message["status"]
                await send(message)

            await self._app(scope, receive, send_and_record_status)
