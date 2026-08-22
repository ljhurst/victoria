from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http import TransportSecuritySettings
from starlette.applications import Starlette

from victoria.mcp import handlers
from victoria.mcp.auth import LassoTokenVerifier


def build_app(*, lasso_issuer_url: str, resource_server_url: str) -> Starlette:
    server = MCPServer(
        name="victoria",
        instructions=(
            "Victoria is a personal admin wiki for any topic. "
            "Use the read tools freely for lookups. "
            "Use remember to file new information — it handles curation internally, so just pass it the raw note. "
            "Use consolidate sparingly, when asked to check the wiki for problems."
        ),
        token_verifier=LassoTokenVerifier(
            issuer_url=lasso_issuer_url, resource_server_url=resource_server_url
        ),
        auth=AuthSettings(
            issuer_url=lasso_issuer_url,
            resource_server_url=resource_server_url,
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
