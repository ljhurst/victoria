"""Lambda entrypoint (DESIGN §9, §14): MCP HTTP events -> mcp/server.

Phase 2 will add EventBridge -> core/operations/consolidate.consolidate
routing here (§9) once on-demand consolidate proves insufficient. v1 has
exactly one trigger, so there's no event-source branch yet.
"""

from mangum import Mangum

from victoria.mcp.config import get_mcp_settings
from victoria.mcp.server import build_app

_mcp_auth_param = get_mcp_settings().mcp_auth_param


def handler(event: dict, context: object) -> dict:
    app = build_app(mcp_auth_param=_mcp_auth_param)
    mangum = Mangum(app, lifespan="auto")

    return mangum(event, context)
