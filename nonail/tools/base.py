"""Base interface for tools — every NoNail tool implements this contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """Uniform result returned by every tool invocation."""
    output: str = ""
    error: str | None = None
    is_error: bool = False

    @classmethod
    def ok(cls, output: str) -> ToolResult:
        return cls(output=output)

    @classmethod
    def fail(cls, error: str) -> ToolResult:
        return cls(error=error, is_error=True)


class Tool(ABC):
    """Base class for all NoNail tools."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON-Schema for the tool's parameters."""
        ...

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool and return a ToolResult."""
        ...

    def to_openai_schema(self) -> dict:
        """Return the tool in OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema(),
            },
        }
