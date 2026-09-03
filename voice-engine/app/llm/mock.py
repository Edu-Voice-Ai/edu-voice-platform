"""Deterministic Mock LLM Provider for local testing and grounding verification."""
from typing import AsyncIterator, List, Dict, Any, Optional
import asyncio
from app.llm.base import LLMProvider, LLMChunk, LLMResponse
from app.pipeline.cancellation import CancellationToken


class MockLLMProvider(LLMProvider):
    """Mock LLM generating context-aware deterministic responses."""

    def __init__(self, responses: Optional[Dict[str, str]] = None, default_response: str = "BTech Computer Science and Engineering fee is INR 1,50,000 per annum at Apex University."):
        self.responses = responses or {}
        self.default_response = default_response

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[CancellationToken] = None,
        temperature: float = 0.3,
        max_tokens: int = 256
    ) -> AsyncIterator[LLMChunk]:
        # Extract last user message
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "").lower()
                break

        resp_text = self.default_response
        for key, val in self.responses.items():
            if key.lower() in last_user_msg:
                resp_text = val
                break

        # Grounding check for unverified facts
        if "2027 scholarship" in last_user_msg or "unverified" in last_user_msg:
            resp_text = "I do not have verified information regarding the 2027 scholarship amount. Would you like me to connect you with our admissions counselor?"

        tokens = resp_text.split(" ")
        for i, token in enumerate(tokens):
            if cancellation_token and cancellation_token.is_cancelled:
                return
            await asyncio.sleep(0.04)  # Realistic token streaming delay (~25 tokens/sec)
            is_last = (i == len(tokens) - 1)
            yield LLMChunk(delta=token + ("" if is_last else " "), is_complete=is_last, finish_reason="stop" if is_last else None)

    async def generate_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 256
    ) -> LLMResponse:
        chunks = []
        async for chunk in self.stream_chat(messages, tools=tools):
            chunks.append(chunk.delta)
        return LLMResponse(content="".join(chunks))
