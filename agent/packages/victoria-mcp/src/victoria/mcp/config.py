from functools import lru_cache

from aws_lambda_powertools.utilities import parameters
from pydantic import Field
from pydantic_settings import BaseSettings

from victoria.core.observability import timed


class McpSettings(BaseSettings):
    lasso_issuer_url: str = Field(validation_alias="LASSO_ISSUER_URL")
    resource_server_url: str = Field(validation_alias="VICTORIA_RESOURCE_URL")
    resource_server_aliases: str = Field(
        default="", validation_alias="VICTORIA_RESOURCE_URL_ALIASES"
    )
    anthropic_api_key_param: str = Field(
        default="/victoria/anthropic-api-key", validation_alias="ANTHROPIC_API_KEY_SSM_PARAM"
    )

    @property
    def accepted_audiences(self) -> tuple[str, ...]:
        aliases = [a.strip() for a in self.resource_server_aliases.split(",") if a.strip()]
        return (self.resource_server_url, *aliases)


@lru_cache(maxsize=1)
def get_mcp_settings() -> McpSettings:
    return McpSettings()


@lru_cache(maxsize=1)
@timed("fetch_anthropic_api_key")
def get_anthropic_api_key() -> str:
    return parameters.get_parameter(get_mcp_settings().anthropic_api_key_param, decrypt=True)
