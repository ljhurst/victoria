"""Anthropic API client + model tiering (DESIGN §9): cheap model inside
remember's merge decision, stronger model for consolidate's cross-page synthesis.
"""

from collections.abc import Callable
from typing import Any

import anthropic
from pydantic import BaseModel

from victoria.core.observability import timed

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-5"

MAX_LINT_TOOL_ITERATIONS = 8


def get_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def call_forced_tool[ModelT: BaseModel](
    client: anthropic.Anthropic,
    *,
    model: str,
    system: str,
    user_message: str,
    tool: dict[str, Any],
    response_model: type[ModelT],
) -> ModelT:
    """Send one message, forcing the model to call `tool`. Validates that
    tool call's input against response_model and returns it. Used for
    remember's single merge-decision call (DESIGN §7) — not a loop, since
    there's exactly one decision to make."""
    with timed("anthropic_call", model=model, tool=tool["name"]) as extra:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": user_message}],
        )
        extra.update(_response_fields(response))
    for block in response.content:
        if block.type == "tool_use" and block.name == tool["name"]:
            return response_model.model_validate(block.input)
    raise RuntimeError(f"model did not call the forced tool {tool['name']!r}")


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
