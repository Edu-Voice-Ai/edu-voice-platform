"""
Edu-Voice-Ai — Voice Engine Client Service Boundary
Interface communicating with the separate Voice Engine container (Silero VAD + Parakeet-TDT + Qwen3-TTS).
"""

from typing import Any, Dict, Optional
import httpx
from app.core.config import settings
from app.core.exceptions import VoiceEngineException
from app.core.logging import logger


class VoiceEngineClient:
    """Client for orchestrating voice sessions with the dedicated Voice Engine container."""

    def __init__(
        self,
        base_url: str = settings.VOICE_ENGINE_URL,
        api_key: str = settings.VOICE_ENGINE_API_KEY,
        timeout_seconds: int = settings.VOICE_ENGINE_TIMEOUT_SECONDS,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout_seconds

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Voice-Engine-Key"] = self.api_key
        return headers

    async def check_health(self) -> Dict[str, Any]:
        """Queries the Voice Engine health and GPU readiness endpoint."""
        url = f"{self.base_url}/health"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_headers())
                if response.status_code == 200:
                    return response.json()
                return {"status": "unhealthy", "status_code": response.status_code}
        except httpx.RequestError as exc:
            logger.warning(f"Voice Engine health ping unreachable at {url}: {str(exc)}")
            return {"status": "unreachable", "error": str(exc)}

    async def start_voice_session(
        self,
        call_id: str,
        organization_id: str,
        agent_id: str,
        agent_config: Dict[str, Any],
        caller_number: str,
    ) -> Dict[str, Any]:
        """
        Signals the Voice Engine to initialize an inbound/outbound audio processing session.
        Voice Engine sets up Silero VAD, Parakeet-TDT STT, Groq orchestrator, and Qwen3-TTS pipeline.
        """
        url = f"{self.base_url}/api/v1/sessions/start"
        payload = {
            "call_id": call_id,
            "organization_id": organization_id,
            "agent_id": agent_id,
            "agent_config": agent_config,
            "caller_number": caller_number,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_headers())
                if response.status_code not in (200, 201):
                    logger.error(f"Voice Engine session initialization failed: {response.text}")
                    raise VoiceEngineException(
                        message=f"Voice Engine failed to start session: {response.status_code}",
                        details={"response": response.text},
                    )
                return response.json()
        except httpx.RequestError as exc:
            logger.error(f"Voice Engine network error during session start: {str(exc)}")
            raise VoiceEngineException(
                message="Voice Engine service is unreachable.",
                details={"error": str(exc)},
            )

    async def stop_voice_session(self, call_id: str, reason: str = "call_ended") -> Dict[str, Any]:
        """Signals the Voice Engine to cleanly flush audio buffers and teardown the pipeline."""
        url = f"{self.base_url}/api/v1/sessions/{call_id}/stop"
        payload = {"reason": reason}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self._get_headers())
                if response.status_code == 200:
                    return response.json()
                return {"status": "error", "status_code": response.status_code}
        except httpx.RequestError as exc:
            logger.warning(f"Failed to cleanly stop Voice Engine session for call {call_id}: {str(exc)}")
            return {"status": "unreachable", "error": str(exc)}


voice_engine_client = VoiceEngineClient()
