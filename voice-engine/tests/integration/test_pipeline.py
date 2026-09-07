"""Level 1 S2S Core Smoke Test: Full pipeline from Audio In -> VAD -> STT -> LLM -> TTS -> Audio Out."""
import pytest
import asyncio
from app.audio.frames import AudioFrame
from app.session.events import EventType


@pytest.mark.asyncio
async def test_end_to_end_s2s_pipeline(test_s2s_engine, sample_speech_frame, sample_silence_frame):
    engine = test_s2s_engine
    await engine.start()

    received_events = []

    # Drain events in background
    async def event_collector():
        while engine._running:
            try:
                evt = await engine.queues.event_out_queue.get()
                received_events.append(evt)
            except asyncio.CancelledError:
                break

    collector_task = asyncio.create_task(event_collector())

    try:
        # Wait for initial greeting ready
        for _ in range(50):
            if any(e.event in (EventType.SESSION_INTERACTION_READY, EventType.RESPONSE_END) for e in received_events):
                break
            await asyncio.sleep(0.02)

        # 1. Feed speech frames (15 frames = 150ms > 40ms threshold)
        for _ in range(15):
            await engine.push_audio_frame(sample_speech_frame)
            await asyncio.sleep(0.01)

        # 2. Feed silence frames to complete turn (110 frames = 2200ms > 2000ms threshold)
        for _ in range(110):
            await engine.push_audio_frame(sample_silence_frame)
            await asyncio.sleep(0.005)

        # 3. Allow pipeline to process STT -> LLM -> TTS
        for _ in range(60):
            if sum(1 for e in received_events if e.event == EventType.RESPONSE_END) >= 2:
                break
            await asyncio.sleep(0.05)

        # Verify event sequence
        event_types = [e.event for e in received_events]
        assert EventType.SPEECH_START in event_types
        assert EventType.SPEECH_END in event_types
        assert EventType.TRANSCRIPT_FINAL in event_types
        assert EventType.RESPONSE_START in event_types
        assert EventType.RESPONSE_TEXT_DELTA in event_types
        assert EventType.AUDIO_OUTPUT in event_types
        assert EventType.RESPONSE_END in event_types

        # Verify output audio was placed in audio_out_queue
        assert not engine.queues.audio_out_queue.empty()
        out_frame = await engine.queues.audio_out_queue.get()
        assert isinstance(out_frame, AudioFrame)
        assert len(out_frame.data) > 0

    finally:
        collector_task.cancel()
        await engine.stop()
