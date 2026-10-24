from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from victoria.core.observability import timed


async def log_tool_calls(ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
    if ctx.method != "tools/call":
        return await call_next(ctx)

    params = ctx.params or {}
    arguments = params.get("arguments") or {}
    arg_chars = {name: len(str(value)) for name, value in arguments.items()}

    with timed("tool_call", tool=params.get("name"), arg_chars=arg_chars) as extra:
        result = await call_next(ctx)
        extra["tool_error"] = isinstance(result, dict) and bool(result.get("isError"))
    return result
