from typing import Any

from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    input: dict[str, Any]
