"""Anthropic API client + model tiering (DESIGN §9): cheap model inside
remember's merge decision, stronger model for consolidate's cross-page synthesis.
"""

from collections.abc import Callable
from typing import Any

import anthropic

from victoria.core.integrations.models import ToolCall
from victoria.core.observability import timed

HAIKU_MODEL = "claude-haiku-5-5"
SONNET_MODEL = "claude-sonnet-5"

MAX_LINT_TOOL_ITERATIONS = 8


def get_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def call_tools(
    client: anthropic.Anthropic,
    *,
    model: str,
    system: str,
    user_message: str,
    tools: list[dict[str, Any]],
) -> list[ToolCall]:
    """Send one message, requiring the model to call at least one of `tools`,
    and return every tool call in its response. The caller applies them; no
    results are sent back, so this is one round trip."""
    with timed("anthropic_call", model=model, tools=[tool["name"] for tool in tools]) as extra:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=tools,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": user_message}],
        )
        extra.update(_response_fields(response))

    if response.stop_reason == "max_tokens":
        raise RuntimeError("model response was cut off at max_tokens")
    if response.stop_reason == "refusal":
        raise RuntimeError(f"model declined the request: {response.stop_details}")

    return [
        ToolCall(name=block.name, input=block.input)
        for block in response.content
        if block.type == "tool_use"
    ]


def run_tool_loop(
    client: anthropic.Anthropic,
    *,
    model: str,
    system: str,
    user_message: str,
    tools: list[dict[str, Any]],
    dispatch: Callable[[str, dict[str, Any]], Any],
    max_iterations: int = MAX_LINT_TOOL_ITERATIONS,
) -> str:
    """Hand-rolled tool-calling loop (DESIGN §10): send a message, catch
    tool_use blocks, dispatch to the given tools, feed tool_result back in,
    loop until the model stops calling tools. Returns the final text.
    Used by consolidate, which needs multi-step cross-page reasoning."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    for iteration in range(max_iterations):
        with timed("anthropic_call", model=model, iteration=iteration) as extra:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
            )
            extra.update(_response_fields(response))
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(block.text for block in response.content if block.type == "text")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = dispatch(block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"tool loop did not converge within {max_iterations} iterations")


def _response_fields(response: anthropic.types.Message) -> dict[str, Any]:
    return {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "stop_reason": response.stop_reason,
        "request_id": response._request_id,
    }
