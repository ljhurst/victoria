from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from victoria.core.integrations.models import AnthropicFederation


class McpSettings(BaseSettings):
    lasso_issuer_url: str = Field(validation_alias="LASSO_ISSUER_URL")
    resource_server_url: str = Field(validation_alias="VICTORIA_RESOURCE_URL")


class AnthropicFederationSettings(AnthropicFederation, BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANTHROPIC_", frozen=True)


@lru_cache(maxsize=1)
def get_mcp_settings() -> McpSettings:
    return McpSettings()


@lru_cache(maxsize=1)
def get_anthropic_federation() -> AnthropicFederation:
    return AnthropicFederationSettings()
