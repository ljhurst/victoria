import logging
import secrets

from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response

from victoria.viewer.auth import oauth
from victoria.viewer.config import get_viewer_settings
from victoria.viewer.content.constants import TEMPLATES

logger = logging.getLogger(__name__)


async def login(request: Request) -> Response:
    settings = get_viewer_settings()
    state = secrets.token_urlsafe(16)
    verifier = oauth.new_pkce_verifier()
    request.session["oauth"] = {"state": state, "verifier": verifier}

    url = await oauth.authorize_url(settings, state=state, verifier=verifier)
    return RedirectResponse(url)


async def callback(request: Request) -> Response:
    pending = request.session.pop("oauth", None)
    if not pending or not secrets.compare_digest(
        request.query_params.get("state", ""), pending["state"]
    ):
        return PlainTextResponse("OAuth state mismatch — try logging in again.", status_code=400)

    code = request.query_params.get("code")
    if not code:
        return PlainTextResponse("No authorization code in callback.", status_code=400)

    settings = get_viewer_settings()
    tokens = await oauth.exchange_code(settings, code=code, verifier=pending["verifier"])

    if await oauth.verify_read_token(settings, tokens.access_token) is None:
        return TEMPLATES.TemplateResponse(request, "denied.html", {}, status_code=403)

    request.session["access_token"] = tokens.access_token
    request.session["id_token"] = tokens.id_token
    return RedirectResponse("/browse/index.md", status_code=303)


async def logout(request: Request) -> Response:
    id_token = request.session.get("id_token")
    request.session.clear()
    if not id_token:
        logger.warning("logout: no id_token in session — Lasso SSO session left intact")
        return RedirectResponse("/logged-out")

    # RP-initiated logout: end the Lasso SSO session too, otherwise the next
    # protected request silently re-authenticates and nothing changed.
    url = await oauth.logout_url(get_viewer_settings(), id_token=id_token)
    return RedirectResponse(url)


async def logged_out(request: Request) -> Response:
    return TEMPLATES.TemplateResponse(request, "logged_out.html", {})
