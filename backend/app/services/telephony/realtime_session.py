"""Realtime Voice Session model and queue management.

Provides bounded asynchronous audio queues, concurrency-safe lifecycle tracking,
backpressure enforcement, and interruption / barge-in cancellation.
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.lifecycle.session import CallSessionState
from backend.app.services.telephony.metrics import get_gateway_metrics

logger = logging.getLogger("telephony.realtime_session")


class ConnectionState(str, Enum):
    """WebSocket connection lifecycle states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    CLOSED = "closed"


class SessionStats:
    """Diagnostic counters for audio packet throughput and quality."""

    def __init__(self) -> None:
        self.frames_received: int = 0
        self.frames_sent: int = 0
        self.frames_dropped: int = 0
        self.interruptions_triggered: int = 0
        self.bytes_received: int = 0
        self.bytes_sent: int = 0


class RealtimeVoiceSession:
    """Stateful abstraction representing an active realtime audio session."""

    def __init__(
        self,
        session_id: str,
        call_sid: str | None = None,
        organization_id: str | None = None,
        agent_id: str | None = None,
        agent_config: Any | None = None,
        max_queue_size: int = 100,
        backpressure_strategy: str = "drop_oldest",
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
    ) -> None:
        self.session_id: str = session_id
        self.call_sid: str | None = call_sid
        self.call_id: str | None = call_id or call_sid
        self.outbound_job_id: str | None = outbound_job_id
        self.campaign_id: str | None = campaign_id
        self.contact_id: str | None = contact_id
        self.organization_id: str | None = organization_id
        self.agent_id: str | None = agent_id
        self.agent_config: Any | None = agent_config

        self.provider: str = provider
        self.stream_sid: str | None = stream_sid
        self.from_number: str | None = from_number
        self.to_number: str | None = to_number
        self.call_direction: str | None = call_direction
        self.provider_metadata: dict[str, Any] = provider_metadata or {}

        self.max_queue_size: int = max_queue_size
        self.backpressure_strategy: str = backpressure_strategy

        self.connection_state: ConnectionState = ConnectionState.DISCONNECTED
        self.lifecycle_state: CallSessionState = CallSessionState.INITIATED

        now = datetime.now(timezone.utc)
        self.created_at: datetime = now
        self.last_activity_at: datetime = now

        # Bounded asynchronous audio queues
        self.inbound_audio_queue: asyncio.Queue[AudioFrame] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self.outbound_audio_queue: asyncio.Queue[AudioFrame] = asyncio.Queue(
            maxsize=max_queue_size
        )

        # Control and cancellation signals
        self.cancellation_event: asyncio.Event = asyncio.Event()
        self.interruption_event: asyncio.Event = asyncio.Event()

        # Connection and task tracking
        self.active_websocket: WebSocket | None = None
        self.active_tasks: set[asyncio.Task[Any]] = set()

        # Performance & backpressure metrics
        self.stats: SessionStats = SessionStats()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._metrics = get_gateway_metrics()

        # Voice Engine contract tracking & post-call intelligence
        self.active_generation_id: str | None = None
        self.cancelled_generations: set[str] = set()
        self.lead_data: dict[str, Any] | None = None
        self.call_summary_data: dict[str, Any] | None = None
        self.response_latencies: dict[str, Any] | None = None
        self.voice_engine_client: Any | None = None

    def touch_activity(self) -> None:
        """Update last recorded activity timestamp."""
        self.last_activity_at = datetime.now(timezone.utc)

    def is_expired(
        self,
        max_idle_seconds: int = 1800,
        max_duration_seconds: int = 3600,
    ) -> bool:
        """Check if the session has exceeded idle or absolute lifetime boundaries."""
        now = datetime.now(timezone.utc)
        idle_duration = (now - self.last_activity_at).total_seconds()
        total_duration = (now - self.created_at).total_seconds()
        return (
            idle_duration >= max_idle_seconds or total_duration >= max_duration_seconds
        )

    async def push_inbound_frame(self, frame: AudioFrame) -> bool:
        """Enqueue an incoming caller audio frame with explicit backpressure handling."""
        self.touch_activity()
        if self.cancellation_event.is_set():
            return False

        if self.inbound_audio_queue.full():
            self._metrics.record_queue_overflow()
            if self.backpressure_strategy == "drop_oldest":
                try:
                    # Drop oldest unconsumed frame to make room for newest audio
                    self.inbound_audio_queue.get_nowait()
                    self.inbound_audio_queue.task_done()
                    self.stats.frames_dropped += 1
                    self._metrics.record_frame_dropped()
                    logger.debug(
                        "Inbound queue full for session %s: dropped oldest frame",
                        self.session_id,
                    )
                except (asyncio.QueueEmpty, ValueError):
                    pass
            else:
                # Reject new frame
                self.stats.frames_dropped += 1
                self._metrics.record_frame_dropped()
                return False

        try:
            self.inbound_audio_queue.put_nowait(frame)
            self.stats.frames_received += 1
            self.stats.bytes_received += len(frame.data)
            self._metrics.record_frame_received(byte_count=len(frame.data))
            return True
        except asyncio.QueueFull:
            self.stats.frames_dropped += 1
            self._metrics.record_frame_dropped()
            return False

    async def push_outbound_frame(self, frame: AudioFrame) -> bool:
        """Enqueue an outbound audio frame to be streamed to the client."""
        self.touch_activity()
        if self.cancellation_event.is_set():
            return False

        if self.outbound_audio_queue.full():
            self._metrics.record_queue_overflow()
            if self.backpressure_strategy == "drop_oldest":
                try:
                    self.outbound_audio_queue.get_nowait()
                    self.outbound_audio_queue.task_done()
                    self.stats.frames_dropped += 1
                    self._metrics.record_frame_dropped()
                except (asyncio.QueueEmpty, ValueError):
                    pass
            else:
                self.stats.frames_dropped += 1
                self._metrics.record_frame_dropped()
                return False

        try:
            self.outbound_audio_queue.put_nowait(frame)
            return True
        except asyncio.QueueFull:
            self.stats.frames_dropped += 1
            self._metrics.record_frame_dropped()
            return False

    def drain_outbound_queue(self, generation_id: str | None = None) -> int:
        """Clear pending outbound audio frames (used on barge-in / interruption).

        If generation_id is provided, only frames matching that generation_id are drained.
        If generation_id is None, all pending frames are cleared.
        """
        drained_count = 0
        if generation_id is None:
            while not self.outbound_audio_queue.empty():
                try:
                    self.outbound_audio_queue.get_nowait()
                    self.outbound_audio_queue.task_done()
                    drained_count += 1
                except (asyncio.QueueEmpty, ValueError):
                    break
        else:
            retained: list[AudioFrame] = []
            while not self.outbound_audio_queue.empty():
                try:
                    frame = self.outbound_audio_queue.get_nowait()
                    self.outbound_audio_queue.task_done()
                    frame_gen = frame.metadata.get("generation_id", "")
                    if frame_gen == generation_id or not frame_gen:
                        drained_count += 1
                    else:
                        retained.append(frame)
                except (asyncio.QueueEmpty, ValueError):
                    break

            for frame in retained:
                try:
                    self.outbound_audio_queue.put_nowait(frame)
                except asyncio.QueueFull:
                    break

        return drained_count

    def set_stream_sid(self, stream_sid: str) -> None:
        """Associate carrier stream identifier with active session."""
        self.stream_sid = stream_sid

    def cancel_generation(self, generation_id: str) -> int:
        """Record cancelled generation and purge corresponding audio frames."""
        self.cancelled_generations.add(generation_id)
        return self.drain_outbound_queue(generation_id=generation_id)

    def trigger_interruption(self, generation_id: str | None = None) -> int:
        """Handle caller barge-in / interruption.

        Sets interruption event, marks generation as cancelled, drains outbound audio,
        and resets for caller input.
        """
        self.stats.interruptions_triggered += 1
        self._metrics.record_interruption()
        self.interruption_event.set()
        if generation_id:
            self.cancelled_generations.add(generation_id)
        drained = self.drain_outbound_queue(generation_id=generation_id)
        logger.info(
            "Interruption triggered for session %s (generation=%s, drained %s outbound frames)",
            self.session_id,
            generation_id or "all",
            drained,
        )
        return drained

    async def close(self, reason: str = "normal_closure") -> None:
        """Clean up and cancel all resources associated with this session."""
        async with self._lock:
            self.cancellation_event.set()
            self.connection_state = ConnectionState.CLOSED
            self.lifecycle_state = CallSessionState.DISCONNECTED

            # Drain queues to release references
            self.drain_outbound_queue()
            while not self.inbound_audio_queue.empty():
                try:
                    self.inbound_audio_queue.get_nowait()
                    self.inbound_audio_queue.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    break

            # Cancel active background tasks
            for task in list(self.active_tasks):
                if not task.done():
                    task.cancel()
            self.active_tasks.clear()

            # Close active websocket if open
            if self.active_websocket is not None:
                try:
                    await self.active_websocket.close(code=1000, reason=reason)
                except (RuntimeError, WebSocketDisconnect, OSError):
                    pass
                except Exception as ws_err:  # noqa: BLE001
                    logger.debug("Error closing session websocket: %s", ws_err)
                self.active_websocket = None
