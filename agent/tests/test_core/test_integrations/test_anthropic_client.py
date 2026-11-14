from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from victoria.core import observability
from victoria.core.integrations import anthropic_client
from victoria.core.integrations.models import AnthropicFederation, ToolCall

TOOL = {"name": "file_note", "description": "d", "input_schema": {"type": "object"}}


def _response(blocks, *, stop_reason="tool_use"):
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(input_tokens=120, output_tokens=45),
        stop_reason=stop_reason,
        _request_id="req_123",
    )


def _tool_use(name, **tool_input):
    return SimpleNamespace(type="tool_use", name=name, id="tu_1", input=tool_input)


def test_call_tools_returns_every_tool_call_and_logs_usage():
    client = MagicMock()
    client.messages.create.return_value = _response(
        [
            SimpleNamespace(type="text", text="ignored"),
            _tool_use("file_note", summary="s"),
            _tool_use("str_replace_based_edit_tool", command="create", path="p"),
        ]
    )

    with patch.object(observability, "logger") as logger:
        calls = anthropic_client.call_tools(
            client,
            model="m",
            system="s",
            user_message="u",
            tools=[{"name": "file_note"}, {"name": "str_replace_based_edit_tool"}],
        )

    assert calls == [
        ToolCall(name="file_note", input={"summary": "s"}),
        ToolCall(name="str_replace_based_edit_tool", input={"command": "create", "path": "p"}),
    ]
    assert client.messages.create.call_args.kwargs["tool_choice"] == {"type": "any"}
    finished = logger.info.call_args_list[-1].kwargs
    assert finished["tools"] == ["file_note", "str_replace_based_edit_tool"]
    assert (finished["input_tokens"], finished["output_tokens"]) == (120, 45)
    assert finished["stop_reason"] == "tool_use"
    assert finished["request_id"] == "req_123"


def test_call_tools_reports_a_refusal_with_its_category():
    client = MagicMock()
    response = _response([], stop_reason="refusal")
    response.stop_details = SimpleNamespace(type="refusal", category="bio")
    client.messages.create.return_value = response

    with pytest.raises(RuntimeError, match="declined.*bio"):
        anthropic_client.call_tools(client, model="m", system="s", user_message="u", tools=[])


def test_call_tools_rejects_a_response_cut_off_mid_tool_call():
    client = MagicMock()
    client.messages.create.return_value = _response(
        [_tool_use("file_note", summary="s")], stop_reason="max_tokens"
    )

    with pytest.raises(RuntimeError, match="max_tokens"):
        anthropic_client.call_tools(client, model="m", system="s", user_message="u", tools=[])


def test_run_tool_loop_logs_each_iteration():
    tool_block = SimpleNamespace(type="tool_use", name="t", id="tu_1", input={})
    text_block = SimpleNamespace(type="text", text="done")
    client = MagicMock()
    client.messages.create.side_effect = [
        _response([tool_block]),
        _response([text_block], stop_reason="end_turn"),
    ]

    with patch.object(observability, "logger") as logger:
        anthropic_client.run_tool_loop(
            client,
            model="m",
            system="s",
            user_message="u",
            tools=[TOOL],
            dispatch=lambda name, args: "ok",
        )

    finished = [c.kwargs for c in logger.info.call_args_list if c.args == ("stage finished",)]
    assert [f["iteration"] for f in finished] == [0, 1]
    assert [f["stop_reason"] for f in finished] == ["tool_use", "end_turn"]


@pytest.fixture
def fresh_client_cache():
    anthropic_client.get_client.cache_clear()
    yield
    anthropic_client.get_client.cache_clear()


def test_get_client_with_federation_exchanges_an_sts_token(fresh_client_cache):
    federation = AnthropicFederation(
        federation_rule_id="fdrl_1", organization_id="org_1", service_account_id="svac_1"
    )

    with (
        patch.object(anthropic_client.anthropic, "WorkloadIdentityCredentials") as credentials,
        patch.object(anthropic_client.anthropic, "Anthropic") as client_class,
    ):
        anthropic_client.get_client(federation)

    credentials.assert_called_once_with(
        identity_token_provider=anthropic_client._sts_identity_token,
        federation_rule_id="fdrl_1",
        organization_id="org_1",
        service_account_id="svac_1",
    )
    client_class.assert_called_once_with(credentials=credentials.return_value)


def test_get_client_reuses_one_client_so_warm_lambdas_keep_their_token(fresh_client_cache):
    federation = AnthropicFederation(
        federation_rule_id="fdrl_1", organization_id="org_1", service_account_id="svac_1"
    )

    assert anthropic_client.get_client(federation) is anthropic_client.get_client(federation)


def test_get_client_without_federation_uses_the_sdk_default_credentials(fresh_client_cache):
    with patch.object(anthropic_client.anthropic, "Anthropic") as client_class:
        anthropic_client.get_client()

    client_class.assert_called_once_with()


def test_sts_identity_token_requests_a_fresh_anthropic_audience_jwt():
    sts = MagicMock()
    sts.get_web_identity_token.return_value = {"WebIdentityToken": "jwt"}

    with patch.object(anthropic_client.boto3, "client", return_value=sts) as boto_client:
        token = anthropic_client._sts_identity_token()

    assert token == "jwt"
    boto_client.assert_called_once_with("sts")
    sts.get_web_identity_token.assert_called_once_with(
        Audience=["https://api.anthropic.com"], SigningAlgorithm="RS256", DurationSeconds=900
    )
