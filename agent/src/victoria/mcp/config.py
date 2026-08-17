"""MCP-boundary settings: the SSM parameter paths used to resolve secrets
before calling into core/ — auth for the MCP transport itself, and the
Anthropic key core/'s operations need but never look up themselves. core/
only ever receives already-resolved values (DESIGN §14, §5, §7).
"""

from functools import lru_cache

from aws_lambda_powertools.utilities import parameters
from pydantic import Field
from pydantic_settings import BaseSettings


class McpSettings(BaseSettings):
    mcp_auth_param: str = Field(
        default="/victoria/mcp-auth-token", validation_alias="MCP_AUTH_SSM_PARAM"
    )
    anthropic_api_key_param: str = Field(
        default="/victoria/anthropic-api-key", validation_alias="ANTHROPIC_API_KEY_SSM_PARAM"
    )


@lru_cache(maxsize=1)
def get_mcp_settings() -> McpSettings:
    return McpSettings()


@lru_cache(maxsize=1)
def get_anthropic_api_key() -> str:
    return parameters.get_parameter(get_mcp_settings().anthropic_api_key_param, decrypt=True)
