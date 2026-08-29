import functools
from collections.abc import Awaitable, Callable

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

from victoria.viewer.auth import oauth
from victoria.viewer.config import get_session_secret, get_viewer_settings
from victoria.viewer.routes import auth, pages

Handler = Callable[[Request], Awaitable[Response]]


def build_app() -> Starlette:
    settings = get_viewer_settings()

    middleware = [
        Middleware(
            SessionMiddleware,
            secret_key=get_session_secret(),
            https_only=settings.https_only,
            same_site="lax",
        )
    ]

    routes = [
        Route("/healthz", _healthz, name="healthz"),
        Route("/", _home, name="home"),
        Route("/login", auth.login, name="login"),
        Route("/auth/callback", auth.callback, name="callback"),
        Route("/logout", auth.logout, name="logout"),
        Route("/logged-out", auth.logged_out, name="logged_out"),
        Route("/browse", _protected(pages.browse), name="browse_root"),
        Route("/browse/{path:path}", _protected(pages.browse), name="browse"),
        Route("/raw/{path:path}", _protected(pages.raw), name="raw"),
    ]

    return Starlette(routes=routes, middleware=middleware)


async def _healthz(request: Request) -> Response:
    return PlainTextResponse("ok")


async def _home(request: Request) -> Response:
    return RedirectResponse("/browse/index.md")


def _protected(handler: Handler) -> Handler:
    @functools.wraps(handler)
    async def wrapper(request: Request) -> Response:
        token = request.session.get("access_token")
        if token and await oauth.verify_read_token(get_viewer_settings(), token) is not None:
            return await handler(request)

        request.session.pop("access_token", None)
        return RedirectResponse("/login")

    return wrapper
