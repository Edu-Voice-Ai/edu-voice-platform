"""LLM Provider Protocol, streaming chunks, tool calling, and response models."""
from typing import Protocol, runtime_checkable, AsyncIterator, List, Dict, Any, Optional
from dataclasses import dataclass, field
from app.pipeline.cancellation import CancellationToken


@dataclass
class ToolCall:
    """Tool invocation representation."""
    name: str
    arguments: Dict[str, Any]
    id: str = ""


@dataclass
class LLMChunk:
    """Incremental delta from streaming LLM response."""
    delta: str
    is_complete: bool = False
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: Optional[str] = None


@dataclass
class LLMResponse:
    """Complete LLM generation output."""
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for streaming LLM generation providers."""

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[CancellationToken] = None,
        temperature: float = 0.3,
        max_tokens: int = 256
    ) -> AsyncIterator[LLMChunk]:
        """Stream token deltas cooperatively checking cancellation."""
        ...

    async def generate_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 256
    ) -> LLMResponse:
        """Non-streaming complete response generation."""
        ...
