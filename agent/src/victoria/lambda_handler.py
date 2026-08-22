from mangum import Mangum

from victoria.mcp.config import get_mcp_settings
from victoria.mcp.server import build_app

_mcp_settings = get_mcp_settings()


def handler(event: dict, context: object) -> dict:
    app = build_app(
        lasso_issuer_url=_mcp_settings.lasso_issuer_url,
        resource_server_url=_mcp_settings.resource_server_url,
    )
    mangum = Mangum(app, lifespan="auto")

    return mangum(event, context)
