"""Unit tests for RealtimeVoiceSession and RealtimeSessionManager."""

import asyncio

import pytest

from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.lifecycle.session import CallSessionState
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    RealtimeVoiceSession,
)
from backend.app.services.telephony.session_manager import RealtimeSessionManager


@pytest.mark.asyncio
async def test_session_creation_and_defaults() -> None:
    """Test 1: Session creation and default attribute verification."""
    manager = RealtimeSessionManager()
    session = await manager.create_session(
        session_id="sess_123",
        call_sid="call_999",
        organization_id="org_abc",
        agent_id="agent_xyz",
    )
    assert session.session_id == "sess_123"
    assert session.call_sid == "call_999"
    assert session.organization_id == "org_abc"
    assert session.agent_id == "agent_xyz"
    assert session.connection_state == ConnectionState.DISCONNECTED
    assert session.lifecycle_state == CallSessionState.INITIATED
    assert session.inbound_audio_queue.maxsize == 500
    assert session.outbound_audio_queue.maxsize == 500


@pytest.mark.asyncio
async def test_session_retrieval() -> None:
    """Test 2: Session retrieval from manager."""
    manager = RealtimeSessionManager()
    await manager.create_session("sess_retrieval")

    retrieved = await manager.get_session("sess_retrieval")
    assert retrieved is not None
    assert retrieved.session_id == "sess_retrieval"

    missing = await manager.get_session("non_existent_session")
    assert missing is None


@pytest.mark.asyncio
async def test_session_removal_and_cleanup() -> None:
    """Test 3: Session removal and resource cleanup."""
    manager = RealtimeSessionManager()
    await manager.create_session("sess_remove")
    assert await manager.active_session_count() == 1

    removed = await manager.remove_session("sess_remove")
    assert removed is not None
    assert removed.connection_state == ConnectionState.CLOSED
    assert removed.cancellation_event.is_set()
    assert await manager.active_session_count() == 0


@pytest.mark.asyncio
async def test_session_lifecycle_transitions() -> None:
    """Test 4: Session lifecycle state transitions."""
    manager = RealtimeSessionManager()
    session = await manager.create_session("sess_lifecycle")

    session.lifecycle_state = CallSessionState.RINGING
    assert session.lifecycle_state == CallSessionState.RINGING

    session.lifecycle_state = CallSessionState.CONNECTED
    assert session.lifecycle_state == CallSessionState.CONNECTED

    await manager.terminate_session("sess_lifecycle", reason="normal_hangup")
    assert session.lifecycle_state == CallSessionState.DISCONNECTED
    assert session.connection_state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_concurrent_session_access() -> None:
    """Test 5: Concurrency-safe access to session manager."""
    manager = RealtimeSessionManager()

    async def _create_and_fetch(idx: int) -> None:
        s_id = f"concurrent_sess_{idx}"
        await manager.create_session(s_id)
        s = await manager.get_session(s_id)
        assert s is not None
        assert s.session_id == s_id

    tasks = [_create_and_fetch(i) for i in range(50)]
    await asyncio.gather(*tasks)
    assert await manager.active_session_count() == 50


@pytest.mark.asyncio
async def test_queue_bounds_and_capacity() -> None:
    """Test 11: Queue bounds and maxsize configuration."""
    session = RealtimeVoiceSession(session_id="sess_bounds", max_queue_size=5)
    assert session.inbound_audio_queue.maxsize == 5
    assert session.outbound_audio_queue.maxsize == 5

    for i in range(5):
        frame = AudioFrame(data=b"chunk", sequence_number=i)
        accepted = await session.push_inbound_frame(frame)
        assert accepted is True

    assert session.inbound_audio_queue.full() is True


@pytest.mark.asyncio
async def test_backpressure_drop_oldest_strategy() -> None:
    """Test 12 & 13: Backpressure drop-oldest behavior on full queue."""
    session = RealtimeVoiceSession(
        session_id="sess_bp_drop",
        max_queue_size=3,
        backpressure_strategy="drop_oldest",
    )

    # Push 3 frames
    await session.push_inbound_frame(AudioFrame(data=b"frame_1", sequence_number=1))
    await session.push_inbound_frame(AudioFrame(data=b"frame_2", sequence_number=2))
    await session.push_inbound_frame(AudioFrame(data=b"frame_3", sequence_number=3))
    assert session.inbound_audio_queue.full() is True

    # Push 4th frame -> frame_1 should be dropped
    pushed = await session.push_inbound_frame(
        AudioFrame(data=b"frame_4", sequence_number=4)
    )
    assert pushed is True
    assert session.stats.frames_dropped == 1

    # First dequeued frame should now be frame_2
    first_out = await session.inbound_audio_queue.get()
    assert first_out.sequence_number == 2


@pytest.mark.asyncio
async def test_backpressure_reject_strategy() -> None:
    """Test 13: Backpressure reject strategy when queue full."""
    session = RealtimeVoiceSession(
        session_id="sess_bp_reject",
        max_queue_size=2,
        backpressure_strategy="reject",
    )

    await session.push_inbound_frame(AudioFrame(data=b"frame_1", sequence_number=1))
    await session.push_inbound_frame(AudioFrame(data=b"frame_2", sequence_number=2))

    # Push 3rd frame -> rejected
    pushed = await session.push_inbound_frame(
        AudioFrame(data=b"frame_3", sequence_number=3)
    )
    assert pushed is False
    assert session.stats.frames_dropped == 1


@pytest.mark.asyncio
async def test_interruption_barge_in_drains_outbound() -> None:
    """Test 19: Interruption cancels/drains queued outbound frames."""
    session = RealtimeVoiceSession(session_id="sess_interrupt", max_queue_size=10)

    # Queue outbound frames (simulated speech response)
    for i in range(5):
        await session.push_outbound_frame(
            AudioFrame(data=b"speech_chunk", sequence_number=i)
        )

    assert session.outbound_audio_queue.qsize() == 5

    # Caller interrupts
    drained = session.trigger_interruption()
    assert drained == 5
    assert session.outbound_audio_queue.empty() is True
    assert session.interruption_event.is_set()
    assert session.stats.interruptions_triggered == 1


@pytest.mark.asyncio
async def test_idle_session_cleanup() -> None:
    """Test 16: Pruning inactive sessions based on timeout."""
    manager = RealtimeSessionManager()
    await manager.create_session("sess_old")

    # Prune with 0s max idle -> should clean up immediately
    pruned = await manager.cleanup_inactive_sessions(max_idle_seconds=0)
    assert pruned == 1
    assert await manager.active_session_count() == 0
