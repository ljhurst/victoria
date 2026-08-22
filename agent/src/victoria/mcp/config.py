from functools import lru_cache

from aws_lambda_powertools.utilities import parameters
from pydantic import Field
from pydantic_settings import BaseSettings


class McpSettings(BaseSettings):
    lasso_issuer_url: str = Field(validation_alias="LASSO_ISSUER_URL")
    resource_server_url: str = Field(validation_alias="VICTORIA_RESOURCE_URL")
    anthropic_api_key_param: str = Field(
        default="/victoria/anthropic-api-key", validation_alias="ANTHROPIC_API_KEY_SSM_PARAM"
    )


@lru_cache(maxsize=1)
def get_mcp_settings() -> McpSettings:
    return McpSettings()


@lru_cache(maxsize=1)
def get_anthropic_api_key() -> str:
    return parameters.get_parameter(get_mcp_settings().anthropic_api_key_param, decrypt=True)
