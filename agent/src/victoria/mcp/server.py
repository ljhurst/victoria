"""MCP server setup and tool registration (DESIGN §14).

Auth lives in mcp/auth.py — see its module docstring for the static_headers
vs. OAuth rationale (DESIGN §5).
"""

from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http import TransportSecuritySettings
from starlette.applications import Starlette

from victoria.mcp import handlers
from victoria.mcp.auth import BearerAuthMiddleware


def build_app(*, mcp_auth_param: str) -> Starlette:
    server = MCPServer(
        name="victoria",
        instructions=(
            "Victoria is a personal admin wiki for house and business/LLC "
            "topics. Use the read tools freely for lookups. Use remember to "
            "file new information — it handles curation internally, so just "
            "pass it the raw note. Use consolidate sparingly, when asked to "
            "check the wiki for problems."
        ),
    )

    server.add_tool(handlers.list_files)
    server.add_tool(handlers.get_file)
    server.add_tool(handlers.search_wiki)
    server.add_tool(handlers.remember)
    server.add_tool(handlers.consolidate)

    # DNS-rebinding host validation defaults to allowing only localhost —
    # it's meant for locally-bound MCP servers reachable from a browser tab.
    # This server is an internet-facing Lambda Function URL with a fixed,
    # non-attacker-controlled hostname, and the real access boundary is
    # BearerAuthMiddleware below, so that protection doesn't apply here.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = server.streamable_http_app(stateless_http=True, transport_security=security)
    app.add_middleware(BearerAuthMiddleware, ssm_param=mcp_auth_param)

    return app
