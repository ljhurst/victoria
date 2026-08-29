from botocore.exceptions import ClientError
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from victoria.core.storage import wiki
from victoria.core.storage.models import PageContent
from victoria.viewer.config import get_viewer_settings
from victoria.viewer.content.constants import TEMPLATES
from victoria.viewer.content.nav import build_tree
from victoria.viewer.content.render import render_page


async def browse(request: Request) -> Response:
    settings = get_viewer_settings()
    path = request.path_params.get("path") or "index.md"

    content = await _load_page(settings.wiki_bucket, path)
    page = render_page(path, content.content)
    listing = await run_in_threadpool(wiki.list_pages, settings.wiki_bucket)
    template = "_page.html" if request.headers.get("HX-Request") else "browse.html"

    return TEMPLATES.TemplateResponse(
        request,
        template,
        {"page": page, "tree": build_tree(listing.paths), "current": path},
    )


async def raw(request: Request) -> Response:
    content = await _load_page(get_viewer_settings().wiki_bucket, request.path_params["path"])
    return PlainTextResponse(content.content)


async def _load_page(bucket: str, path: str) -> PageContent:
    try:
        return await run_in_threadpool(wiki.get_file, bucket, path)
    except (ClientError, ValidationError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=404, detail=f"No such page: {path}") from e
