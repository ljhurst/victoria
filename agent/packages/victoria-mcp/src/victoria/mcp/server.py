from starlette.applications import Starlette

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http import TransportSecuritySettings
from victoria.mcp import handlers
from victoria.mcp.auth import LassoTokenVerifier
from victoria.mcp.config import get_mcp_settings


def build_app() -> Starlette:
    settings = get_mcp_settings()

    server = MCPServer(
        name="victoria",
        instructions=(
            "Victoria is a personal admin wiki for any topic. "
            "Use the read tools freely for lookups. "
            "Use remember to file new information — it handles curation internally, so just pass it the raw note. "
            "Use consolidate sparingly, when asked to check the wiki for problems."
        ),
        token_verifier=LassoTokenVerifier(
            issuer_url=settings.lasso_issuer_url, resource_server_url=settings.resource_server_url
        ),
        auth=AuthSettings(
            issuer_url=settings.lasso_issuer_url,
            resource_server_url=settings.resource_server_url,
            required_scopes=["victoria:read", "victoria:write"],
        ),
    )

    server.add_tool(handlers.list_files)
    server.add_tool(handlers.get_file)
    server.add_tool(handlers.search_wiki)
    server.add_tool(handlers.remember)
    server.add_tool(handlers.consolidate)

    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    return server.streamable_http_app(stateless_http=True, transport_security=security)
