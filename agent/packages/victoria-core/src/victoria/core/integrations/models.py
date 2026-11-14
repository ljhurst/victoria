from typing import Any

from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    input: dict[str, Any]


class AnthropicFederation(BaseModel, frozen=True):
    """The Console-side IDs a workload presents to exchange its identity token
    for an Anthropic access token. None of them are secret."""

    federation_rule_id: str
    organization_id: str
    service_account_id: str
