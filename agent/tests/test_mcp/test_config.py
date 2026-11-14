import pytest
from pydantic import ValidationError

from victoria.core.integrations.models import AnthropicFederation
from victoria.mcp.config import get_anthropic_federation


@pytest.fixture(autouse=True)
def fresh_federation_cache():
    get_anthropic_federation.cache_clear()
    yield
    get_anthropic_federation.cache_clear()


def test_anthropic_federation_reads_the_lambda_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FEDERATION_RULE_ID", "fdrl_1")
    monkeypatch.setenv("ANTHROPIC_ORGANIZATION_ID", "org_1")
    monkeypatch.setenv("ANTHROPIC_SERVICE_ACCOUNT_ID", "svac_1")

    federation = get_anthropic_federation()

    assert isinstance(federation, AnthropicFederation)
    assert federation.model_dump() == {
        "federation_rule_id": "fdrl_1",
        "organization_id": "org_1",
        "service_account_id": "svac_1",
    }


def test_anthropic_federation_fails_loudly_when_unconfigured(monkeypatch):
    for name in ("FEDERATION_RULE_ID", "ORGANIZATION_ID", "SERVICE_ACCOUNT_ID"):
        monkeypatch.delenv(f"ANTHROPIC_{name}", raising=False)

    with pytest.raises(ValidationError):
        get_anthropic_federation()
