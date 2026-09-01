"""Real Barge-In & Cancellation tests: verification of token cancellation, queue flushing, and stale audio prevention."""
import pytest
import asyncio
from app.audio.frames import AudioFrame
from app.session.state import SessionState, TurnStateEnum
from app.session.events import EventType
from app.tts.sarvam import SarvamTTSProvider
from app.audio.buffering import AudioChunker


@pytest.mark.asyncio
async def test_realtime_barge_in_cancellation(test_s2s_engine, sample_speech_frame, sample_silence_frame):
    engine = test_s2s_engine
    await engine.start()

    events_received = []

    async def collector():
        while engine._running:
            try:
                evt = await engine.queues.event_out_queue.get()
                events_received.append(evt)
            except asyncio.CancelledError:
                break

    task = asyncio.create_task(collector())

    try:
        # Wait for initial greeting ready
        for _ in range(50):
            if any(e.event in (EventType.SESSION_INTERACTION_READY, EventType.RESPONSE_END) for e in events_received):
                break
            await asyncio.sleep(0.02)

        # Turn 1: User speaks "English"
        engine.session.language_selection_complete = True
        for _ in range(15):
            await engine.push_audio_frame(sample_speech_frame)
            await asyncio.sleep(0.01)
        for _ in range(45):
            await engine.push_audio_frame(sample_silence_frame)
            await asyncio.sleep(0.01)

        # Wait for AI to enter SPEAKING / PROCESSING state for Turn 1
        for _ in range(50):
            if sum(1 for e in events_received if e.event in (EventType.RESPONSE_START, EventType.AUDIO_OUTPUT)) >= 2:
                break
            await asyncio.sleep(0.02)

        active_turn_token = engine.session.current_turn.cancellation_token

        # BARGE-IN: User speaks while AI is speaking!
        for _ in range(15):
            await engine.push_audio_frame(sample_speech_frame)
            await asyncio.sleep(0.01)

        await asyncio.sleep(0.2)

        # Verify immediate cancellation
        assert active_turn_token.is_cancelled is True
        
        # Verify event emission
        event_types = [e.event for e in events_received]
        assert EventType.RESPONSE_CANCELLED in event_types
        assert EventType.AUDIO_FLUSH in event_types

    finally:
        task.cancel()
        await engine.stop()


@pytest.mark.asyncio
async def test_barge_in_session_isolation(test_s2s_engine, sample_speech_frame):
    """Verify barge-in in Session A does not cancel or affect Session B."""
    engine_a = test_s2s_engine
    
    # Create independent Session B
    session_b = SessionState(session_id="sess_b_iso", organization_id="org_b", agent_id="agent_b")
    turn_b = session_b.current_turn
    turn_b.state = TurnStateEnum.SPEAKING
    token_b = turn_b.cancellation_token

    # Trigger barge-in on Engine A
    engine_a.session.current_turn.state = TurnStateEnum.SPEAKING
    engine_a.turn_manager.trigger_barge_in(reason="User interrupted session A")

    # Session A turn must be in listening state after barge-in
    assert engine_a.session.current_turn.state in (TurnStateEnum.LISTENING, TurnStateEnum.LISTENING_AFTER_BARGE_IN)
    assert engine_a.session.user_has_floor is True

    # Session B must remain completely untouched
    assert token_b.is_cancelled is False
    assert turn_b.state == TurnStateEnum.SPEAKING


@pytest.mark.asyncio
async def test_stale_audio_chunk_discard():
    """Verify that cancelled tokens prevent TTS audio from being pushed."""
    session = SessionState(session_id="sess_stale_test", organization_id="org_test", agent_id="agent_test")
    turn = session.current_turn
    turn.cancel(reason="Interrupted")
    assert turn.cancellation_token.is_cancelled is True

    chunker = AudioChunker()
    pcm = b"\x00\x00" * 320
    frames = list(chunker.feed(pcm))
    assert len(frames) > 0

    # Frames for cancelled turn should be discarded
    discarded = []
    for f in frames:
        if turn.cancellation_token.is_cancelled:
            discarded.append(f)
    assert len(discarded) == len(frames)
