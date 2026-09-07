"""Voice Engine Contract and Gateway Transport Boundary.

Provides the concrete WebSocket transport adapter (WsVoiceEngineTransport) implementing
the canonical Voice Engine Transport Contract v1.0, alongside backwards-compatible stubs.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.events import (
    NormalizedTelephonyEvent,
    TelephonyEventType,
)
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.voice_engine_client import VoiceEngineWsClient
from backend.app.services.telephony.voice_engine_schemas import (
    SessionStartPayload,
)

logger = logging.getLogger("telephony.voice_engine.transport")


class BaseVoiceEngineTransport(ABC):
    """Abstract boundary between Voice Gateway and downstream Voice Engine."""

    @abstractmethod
    async def send_audio(self, session_id: str, frame: AudioFrame) -> None:
        """Forward incoming caller audio frame to Voice Engine."""

    @abstractmethod
    async def send_event(
        self, session_id: str, event: NormalizedTelephonyEvent
    ) -> None:
        """Forward normalized telephony lifecycle event (e.g. DTMF, STOP) to Voice Engine."""

    @abstractmethod
    async def get_outbound_queue(self, session_id: str) -> asyncio.Queue[AudioFrame]:
        """Obtain queue where Voice Engine produces synthesized bot audio frames."""

    @abstractmethod
    async def close_session(self, session_id: str) -> None:
        """Notify Voice Engine that session streaming has ended."""


def build_session_start_payload(
    session_id: str,
    organization_id: str | None = None,
    agent_id: str | None = None,
    agent_config: Any | None = None,
    sample_rate: int = 16000,
    call_id: str | None = None,
    call_direction: str = "inbound",
) -> SessionStartPayload:
    """Build a canonical SessionStartPayload from resolved session and agent metadata."""
    template_type = "education"
    business_name = "Apex University"
    agent_name = None
    language = "en-IN"
    greeting_message = None
    goodbye_message = None
    system_prompt = None

    if agent_config is not None:
        # Check if agent_config is ResolvedAgentConfig or dictionary
        if hasattr(agent_config, "organization_name") and agent_config.organization_name:
            business_name = agent_config.organization_name
        elif isinstance(agent_config, dict) and agent_config.get("organization_name"):
            business_name = agent_config["organization_name"]

        if hasattr(agent_config, "agent_name") and agent_config.agent_name:
            agent_name = agent_config.agent_name
        elif isinstance(agent_config, dict) and agent_config.get("agent_name"):
            agent_name = agent_config["agent_name"]

        if hasattr(agent_config, "language") and agent_config.language:
            language = agent_config.language
        elif isinstance(agent_config, dict) and agent_config.get("language"):
            language = agent_config["language"]

        if hasattr(agent_config, "welcome_message") and agent_config.welcome_message:
            greeting_message = agent_config.welcome_message
        elif isinstance(agent_config, dict) and agent_config.get("welcome_message"):
            greeting_message = agent_config["welcome_message"]

        if hasattr(agent_config, "system_prompt") and agent_config.system_prompt:
            system_prompt = agent_config.system_prompt
        elif isinstance(agent_config, dict) and agent_config.get("system_prompt"):
            system_prompt = agent_config["system_prompt"]

        # Custom settings / extra template overrides
        custom = (
            getattr(agent_config, "custom_settings", {})
            if hasattr(agent_config, "custom_settings")
            else (agent_config.get("custom_settings", {}) if isinstance(agent_config, dict) else {})
        )
        if isinstance(custom, dict):
            if custom.get("template_type"):
                template_type = str(custom["template_type"])
            if custom.get("business_name"):
                business_name = str(custom["business_name"])
            if custom.get("goodbye_message"):
                goodbye_message = str(custom["goodbye_message"])

    return SessionStartPayload(
        session_id=session_id,
        call_id=call_id,
        organization_id=organization_id,
        agent_id=agent_id,
        call_direction=call_direction,
        language=language,
        client_sample_rate=sample_rate,
        template_type=template_type,
        business_name=business_name,
        agent_name=agent_name,
        greeting_message=greeting_message,
        goodbye_message=goodbye_message,
        system_prompt=system_prompt,
    )


class WsVoiceEngineTransport(BaseVoiceEngineTransport):
    """Production WebSocket transport implementing Voice Engine Contract v1.0."""

    def __init__(
        self,
        settings: TelephonySettings | None = None,
        ws_url: str | None = None,
    ) -> None:
        self.settings: TelephonySettings = settings or get_telephony_settings()
        self.ws_url: str = ws_url or self.settings.voice_engine_ws_url
        self._clients: dict[str, VoiceEngineWsClient] = {}
        self._outbound_queues: dict[str, asyncio.Queue[AudioFrame]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def get_client(self, session_id: str) -> VoiceEngineWsClient | None:
        """Retrieve active VoiceEngineWsClient for a session."""
        async with self._lock:
            return self._clients.get(session_id)

    async def initialize_session(
        self,
        session_id: str,
        start_payload: SessionStartPayload | None = None,
        outbound_queue: asyncio.Queue[AudioFrame] | None = None,
        organization_id: str | None = None,
        agent_id: str | None = None,
        agent_config: Any | None = None,
        call_id: str | None = None,
        call_direction: str = "inbound",
        on_audio_output: Any | None = None,
        on_response_cancelled: Any | None = None,
        on_response_end: Any | None = None,
        on_lead_extracted: Any | None = None,
        on_call_summary: Any | None = None,
        on_error: Any | None = None,
    ) -> VoiceEngineWsClient:
        """Create and connect a new VoiceEngineWsClient instance."""
        # Multi-tenant security check: Voice Engine initialization is permitted ONLY with authoritative tenant identity
        resolved_org = (start_payload.organization_id if start_payload else organization_id) or ""
        resolved_agent = (start_payload.agent_id if start_payload else agent_id) or ""
        if (
            not resolved_org.strip()
            or not resolved_agent.strip()
            or resolved_org.strip() in ("", "pending_contract_org", "unknown", "default")
            or resolved_agent.strip() in ("", "pending_contract_admission_agent", "unknown", "default")
            or resolved_org.startswith("pending_")
            or resolved_agent.startswith("pending_")
        ):
            logger.warning(
                "voice_engine_init_rejected_unresolved_tenant: session_id=%s, org=%s, agent=%s",
                session_id,
                resolved_org,
                resolved_agent,
            )
            raise GatewayError(
                GatewayErrorCode.VALIDATION_FAILED,
                "Voice Engine session initialization rejected: authoritative organization_id and agent_id are required",
            )

        async with self._lock:
            if session_id in self._clients:
                existing = self._clients[session_id]
                if existing.is_ready:
                    return existing

            payload = start_payload or build_session_start_payload(
                session_id=session_id,
                organization_id=organization_id,
                agent_id=agent_id,
                agent_config=agent_config,
                sample_rate=self.settings.voice_engine_sample_rate,
                call_id=call_id,
                call_direction=call_direction,
            )

            if outbound_queue is not None:
                self._outbound_queues[session_id] = outbound_queue
            elif session_id not in self._outbound_queues:
                self._outbound_queues[session_id] = asyncio.Queue(
                    maxsize=self.settings.max_audio_queue_size
                )
            target_queue = self._outbound_queues[session_id]

            client = VoiceEngineWsClient(
                ws_url=self.ws_url,
                session_id=session_id,
                start_payload=payload,
                connect_timeout_seconds=self.settings.voice_engine_connect_timeout_seconds,
                init_timeout_seconds=self.settings.voice_engine_init_timeout_seconds,
                outbound_queue=target_queue,
                on_audio_output=on_audio_output,
                on_response_cancelled=on_response_cancelled,
                on_response_end=on_response_end,
                on_lead_extracted=on_lead_extracted,
                on_call_summary=on_call_summary,
                on_error=on_error,
            )

            self._clients[session_id] = client

        # Connect and await session.ready
        await client.connect_and_start()
        return client

    async def send_audio(self, session_id: str, frame: AudioFrame) -> None:
        """Forward incoming caller audio frame to Voice Engine via WebSocket."""
        client = await self.get_client(session_id)
        if not client or not client.is_ready:
            raise GatewayError(
                code=GatewayErrorCode.CONNECTION_FAILED,
                message=f"Voice Engine client not initialized or not ready for session {session_id}",
            )
        await client.send_audio_frame(frame=frame, use_binary=True)

    async def send_event(
        self, session_id: str, event: NormalizedTelephonyEvent
    ) -> None:
        """Handle lifecycle events (e.g. STOP triggers session.end)."""
        if event.event_type == TelephonyEventType.STOP:
            await self.close_session(session_id)

    async def get_outbound_queue(self, session_id: str) -> asyncio.Queue[AudioFrame]:
        """Obtain queue where Voice Engine produces synthesized bot audio frames."""
        async with self._lock:
            if session_id not in self._outbound_queues:
                self._outbound_queues[session_id] = asyncio.Queue(
                    maxsize=self.settings.max_audio_queue_size
                )
            return self._outbound_queues[session_id]

    async def close_session(self, session_id: str) -> None:
        """Close Voice Engine WebSocket connection for the given session."""
        client: VoiceEngineWsClient | None = None
        async with self._lock:
            client = self._clients.pop(session_id, None)
            self._outbound_queues.pop(session_id, None)

        if client is not None:
            await client.close_session(drain_timeout_seconds=0.5)


class UnresolvedVoiceEngineAdapter(BaseVoiceEngineTransport):
    """Placeholder adapter for stub mode / local fallback without live Voice Engine."""

    def __init__(self, stub_mode: bool = True) -> None:
        self.stub_mode: bool = stub_mode
        self._queues: dict[str, asyncio.Queue[AudioFrame]] = {}

    async def send_audio(self, session_id: str, frame: AudioFrame) -> None:
        if not self.stub_mode:
            raise GatewayError(
                code=GatewayErrorCode.INTERNAL_ERROR,
                message="Voice Engine integration is PENDING CONTRACT (owned by Lokesh)",
            )

    async def send_event(
        self, session_id: str, event: NormalizedTelephonyEvent
    ) -> None:
        if not self.stub_mode:
            raise GatewayError(
                code=GatewayErrorCode.INTERNAL_ERROR,
                message="Voice Engine integration is PENDING CONTRACT (owned by Lokesh)",
            )

    async def get_outbound_queue(self, session_id: str) -> asyncio.Queue[AudioFrame]:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue(maxsize=100)
        return self._queues[session_id]

    async def close_session(self, session_id: str) -> None:
        self._queues.pop(session_id, None)
