"""Sarvam LLM Adapter for sarvam-105b-conversations."""
from typing import AsyncIterator, List, Dict, Any, Optional
import asyncio
import httpx
import json
from app.llm.base import LLMProvider, LLMChunk, LLMResponse, ToolCall
from app.pipeline.cancellation import CancellationToken
from app.core.errors import LLMError
from app.core.logging import get_logger

logger = get_logger("llm.sarvam")


class SarvamLLMProvider(LLMProvider):
    """Sarvam OpenAI-compatible / Chat API Provider with persistent HTTP connection pool."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "sarvam-105b-conversations",
        base_url: str = "https://api.sarvam.ai/v1"
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or getattr(self._client, "is_closed", False):
            self._client = httpx.AsyncClient(
                timeout=15.0,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[CancellationToken] = None,
        temperature: float = 0.3,
        max_tokens: int = 256
    ) -> AsyncIterator[LLMChunk]:
        """Stream token deltas from Sarvam LLM using pooled keep-alive HTTP connection."""
        if not self.api_key:
            logger.warning("SARVAM_API_KEY is not set; yielding fallback simulation")
            sample_text = "Welcome to Apex University. We offer BTech CSE with an annual fee of INR 1,50,000. How can I help you today?"
            for word in sample_text.split(" "):
                if cancellation_token and cancellation_token.is_cancelled:
                    return
                yield LLMChunk(delta=word + " ")
            yield LLMChunk(delta="", is_complete=True, finish_reason="stop")
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_effort": None,
            "stream": True
        }
        if tools:
            payload["tools"] = tools

        try:
            client = self._get_client()
            async with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    err_text = await resp.aread()
                    raise LLMError(f"Sarvam LLM stream returned {resp.status_code}: {err_text.decode('utf-8')}", provider="sarvam")

                async for line in resp.aiter_lines():
                    if cancellation_token and cancellation_token.is_cancelled:
                        logger.info("LLM generation cancelled by token")
                        return

                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    if line == "data: [DONE]":
                        yield LLMChunk(delta="", is_complete=True, finish_reason="stop")
                        break

                    data_str = line[5:].strip()
                    try:
                        chunk_json = json.loads(data_str)
                        choices = chunk_json.get("choices") or []
                        if not choices:
                            continue
                        choice = choices[0]
                        delta_obj = choice.get("delta", {}) or {}
                        delta = delta_obj.get("content") or ""
                        finish_reason = choice.get("finish_reason")
                        
                        parsed_tool_calls = []
                        raw_tools = delta_obj.get("tool_calls") or []
                        for tc in raw_tools:
                            fn = tc.get("function", {})
                            parsed_tool_calls.append(ToolCall(
                                name=fn.get("name", ""),
                                arguments=fn.get("arguments", {}),
                                id=tc.get("id", "")
                            ))

                        if delta:
                            yield LLMChunk(
                                delta=delta,
                                is_complete=bool(finish_reason),
                                finish_reason=finish_reason,
                                tool_calls=parsed_tool_calls if parsed_tool_calls else None
                            )
                        elif parsed_tool_calls:
                            yield LLMChunk(
                                delta="",
                                is_complete=bool(finish_reason),
                                finish_reason=finish_reason,
                                tool_calls=parsed_tool_calls
                            )
                        elif finish_reason:
                            yield LLMChunk(delta="", is_complete=True, finish_reason=finish_reason)
                    except json.JSONDecodeError:
                        continue
        except (httpx.TimeoutException, asyncio.TimeoutError) as e:
            raise LLMError(f"Sarvam LLM timeout error: {e}", provider="sarvam")
        except httpx.RequestError as e:
            raise LLMError(f"Sarvam LLM network error: {e}", provider="sarvam")

    async def generate_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 256
    ) -> LLMResponse:
        """Complete non-streaming generation."""
        if not self.api_key:
            return LLMResponse(content="Apex University offers BTech in CSE, ECE, and Mechanical Engineering.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            if resp.status_code != 200:
                raise LLMError(f"Sarvam LLM failed with {resp.status_code}: {resp.text}", provider="sarvam")
            
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            return LLMResponse(content=content, finish_reason=choice.get("finish_reason", "stop"))
