"""Concurrency-safe Session Manager for Realtime Voice Sessions.

Ensures async-safe creation, retrieval, connection registration, background pruning,
and deterministic cleanup without memory leaks.
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.lifecycle.session import CallSessionState
from backend.app.services.telephony.metrics import get_gateway_metrics
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    RealtimeVoiceSession,
)

logger = logging.getLogger("telephony.session_manager")


class RealtimeSessionManager:
    """Manages active realtime voice sessions, lifecycle pruners, and connection capacity."""

    def __init__(self, settings: TelephonySettings | None = None) -> None:
        self.settings: TelephonySettings = settings or get_telephony_settings()
        self._sessions: dict[str, RealtimeVoiceSession] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._metrics = get_gateway_metrics()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._is_shutting_down: bool = False

    def is_ready(self) -> bool:
        """Check if manager is operational and has available session capacity."""
        if self._is_shutting_down:
            return False
        return len(self._sessions) < self.settings.max_active_sessions

    def reset_shutdown_state(self) -> None:
        """Reset shutdown flag when application initializes/restarts."""
        self._is_shutting_down = False

    async def create_session(
        self,
        session_id: str,
        call_sid: str | None = None,
        organization_id: str | None = None,
        agent_id: str | None = None,
        agent_config: Any | None = None,
        provider: str = "generic",
        stream_sid: str | None = None,
        from_number: str | None = None,
        to_number: str | None = None,
        call_direction: str | None = None,
        provider_metadata: dict[str, Any] | None = None,
        outbound_job_id: str | None = None,
        campaign_id: str | None = None,
        contact_id: str | None = None,
        call_id: str | None = None,
    ) -> RealtimeVoiceSession:
        """Create and register a new RealtimeVoiceSession in a thread-safe manner."""
        async with self._lock:
            if self._is_shutting_down:
                raise GatewayError(
                    code=GatewayErrorCode.SHUTDOWN_IN_PROGRESS,
                    message="Gateway is shutting down and cannot accept new sessions",
                )

            if (
                len(self._sessions) >= self.settings.max_active_sessions
                and session_id not in self._sessions
            ):
                self._metrics.record_rate_limited()
                raise GatewayError(
                    code=GatewayErrorCode.MAX_SESSIONS_EXCEEDED,
                    message=f"Maximum active sessions ({self.settings.max_active_sessions}) reached",
                )

            if session_id in self._sessions:
                # Cleanly replace existing session
                old = self._sessions[session_id]
                await old.close(reason="replaced_by_new_session")
                self._metrics.record_session_closed()

            session = RealtimeVoiceSession(
                session_id=session_id,
                call_sid=call_sid,
                organization_id=organization_id,
                agent_id=agent_id,
                agent_config=agent_config,
                max_queue_size=self.settings.max_audio_queue_size,
                backpressure_strategy=self.settings.backpressure_drop_strategy,
                provider=provider,
                stream_sid=stream_sid,
                from_number=from_number,
                to_number=to_number,
                call_direction=call_direction,
                provider_metadata=provider_metadata,
                outbound_job_id=outbound_job_id,
                campaign_id=campaign_id,
                contact_id=contact_id,
                call_id=call_id,
            )
            self._sessions[session_id] = session
            self._metrics.record_session_created()
            logger.info("Created realtime session: %s", session_id)
            return session

    async def get_session(self, session_id: str) -> RealtimeVoiceSession | None:
        """Retrieve an active session by ID."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def get_or_create_session(
        self,
        session_id: str,
        call_sid: str | None = None,
        provider: str = "generic",
        stream_sid: str | None = None,
        from_number: str | None = None,
        to_number: str | None = None,
        call_direction: str | None = None,
        provider_metadata: dict[str, Any] | None = None,
    ) -> RealtimeVoiceSession:
        """Retrieve existing session or create a new instance if absent."""
        async with self._lock:
            if session_id not in self._sessions:
                if self._is_shutting_down:
                    raise GatewayError(
                        code=GatewayErrorCode.SHUTDOWN_IN_PROGRESS,
                        message="Gateway is shutting down",
                    )
                if len(self._sessions) >= self.settings.max_active_sessions:
                    self._metrics.record_rate_limited()
                    raise GatewayError(
                        code=GatewayErrorCode.MAX_SESSIONS_EXCEEDED,
                        message=f"Maximum active sessions ({self.settings.max_active_sessions}) reached",
                    )

                session = RealtimeVoiceSession(
                    session_id=session_id,
                    call_sid=call_sid,
                    max_queue_size=self.settings.max_audio_queue_size,
                    backpressure_strategy=self.settings.backpressure_drop_strategy,
                    provider=provider,
                    stream_sid=stream_sid,
                    from_number=from_number,
                    to_number=to_number,
                    call_direction=call_direction,
                    provider_metadata=provider_metadata,
                )
                self._sessions[session_id] = session
                self._metrics.record_session_created()
                logger.info("Lazily initialized realtime session: %s", session_id)
            return self._sessions[session_id]

    async def register_connection(
        self,
        session_id: str,
        websocket: WebSocket,
        allow_reconnect: bool = False,
    ) -> tuple[RealtimeVoiceSession | None, bool]:
        """Register an incoming WebSocket connection to a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None, False

            if session.active_websocket is not None and not allow_reconnect:
                logger.warning(
                    "Duplicate WebSocket connection rejected for session %s",
                    session_id,
                )
                return session, False

            session.active_websocket = websocket
            session.connection_state = ConnectionState.CONNECTED
            session.lifecycle_state = CallSessionState.CONNECTED
            session.touch_activity()
            return session, True

    async def terminate_session(
        self,
        session_id: str,
        reason: str = "normal_termination",
    ) -> RealtimeVoiceSession | None:
        """Gracefully close and terminate a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                await session.close(reason=reason)
                self._metrics.record_session_closed()
                logger.info("Terminated session %s (reason: %s)", session_id, reason)
            return session

    async def remove_session(self, session_id: str) -> RealtimeVoiceSession | None:
        """Remove session from manager storage and ensure cleanup."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                await session.close(reason="removed_from_manager")
                self._metrics.record_session_closed()
                logger.info("Removed session from manager: %s", session_id)
            return session

    async def cleanup_inactive_sessions(
        self,
        max_idle_seconds: int | None = None,
        max_duration_seconds: int | None = None,
    ) -> int:
        """Prune inactive or expired sessions."""
        idle_limit = (
            self.settings.session_timeout_seconds
            if max_idle_seconds is None
            else max_idle_seconds
        )
        duration_limit = (
            self.settings.max_session_duration_seconds
            if max_duration_seconds is None
            else max_duration_seconds
        )
        to_prune: list[str] = []

        async with self._lock:
            for s_id, s in self._sessions.items():
                if (
                    s.is_expired(idle_limit, duration_limit)
                    or s.connection_state == ConnectionState.CLOSED
                ):
                    to_prune.append(s_id)

            for s_id in to_prune:
                stale_session = self._sessions.pop(s_id, None)
                if stale_session:
                    await stale_session.close(reason="expired_cleanup")
                    self._metrics.record_session_closed()

        if to_prune:
            logger.info("Pruned %s stale/expired sessions", len(to_prune))
        return len(to_prune)

    def start_cleanup_loop(self) -> None:
        """Start background task for periodic session expiration sweeping."""
        self._is_shutting_down = False
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self._periodic_cleanup_loop(),
                name="telephony_session_pruner",
            )

    def stop_cleanup_loop(self) -> None:
        """Cancel background periodic session pruner."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None

    async def _periodic_cleanup_loop(self) -> None:
        """Background coroutine sweeping for stale sessions at configured intervals."""
        while not self._is_shutting_down:
            try:
                await asyncio.sleep(self.settings.session_cleanup_interval_seconds)
                await self.cleanup_inactive_sessions()
            except asyncio.CancelledError:
                break
            except (RuntimeError, OSError) as exc:
                logger.warning("Error in background session cleanup loop: %s", exc)

    async def active_session_count(self) -> int:
        """Return number of active registered sessions."""
        async with self._lock:
            return len(self._sessions)

    async def close_all(self, reason: str = "server_shutdown") -> None:
        """Close and cleanup all tracked sessions on server shutdown."""
        self._is_shutting_down = True
        self.stop_cleanup_loop()
        async with self._lock:
            for session in self._sessions.values():
                await session.close(reason=reason)
                self._metrics.record_session_closed()
            self._sessions.clear()


# Global singleton instance for app-wide lifecycle management
_global_session_manager: RealtimeSessionManager | None = None


def get_realtime_session_manager(
    settings: TelephonySettings | None = None,
) -> RealtimeSessionManager:
    """Dependency provider / accessor for global RealtimeSessionManager."""
    global _global_session_manager
    if _global_session_manager is None:
        _global_session_manager = RealtimeSessionManager(settings=settings)
    return _global_session_manager
