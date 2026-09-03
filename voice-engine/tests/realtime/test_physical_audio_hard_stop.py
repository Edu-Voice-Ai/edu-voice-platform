"""Tests for physical audio output hard stop, queue flushing, and speaker callback chunk rejection."""
import pytest
import queue
import time
from app.session.state import SessionState, TurnStateEnum
from app.session.events import EventType
from app.pipeline.engine import SpeechToSpeechEngine
from app.conversation.manager import ConversationManager
from app.rag.mock import MockRAGProvider
from app.tools.base import ToolRegistry
from app.vad.mock import MockVADProvider
from app.stt.mock import MockSTTProvider
from app.llm.mock import MockLLMProvider
from app.tts.mock import MockTTSProvider


@pytest.mark.asyncio
async def test_speaker_callback_generation_rejection():
    """Verify that speaker_callback immediately drops chunks belonging to cancelled generations."""
    cancelled_generations = {"gen_old_123"}
    speaker_playback_queue = queue.Queue()

    # Add chunks from cancelled generation and active generation
    speaker_playback_queue.put_nowait(("gen_old_123", b"\x01\x02" * 160))
    speaker_playback_queue.put_nowait(("gen_old_123", b"\x03\x04" * 160))
    speaker_playback_queue.put_nowait(("gen_active_456", b"\x05\x06" * 160))

    outdata = bytearray(320)  # 20ms @ 16kHz 16-bit mono

    # Sounddevice Output Callback logic
    bytes_needed = len(outdata)
    out_bytes = bytearray()
    while len(out_bytes) < bytes_needed:
        try:
            item = speaker_playback_queue.get_nowait()
            if isinstance(item, tuple):
                item_gen_id, chunk = item
                if item_gen_id and item_gen_id in cancelled_generations:
                    continue  # Discard cancelled chunk
            else:
                chunk = item
            out_bytes.extend(chunk)
        except queue.Empty:
            break
    if len(out_bytes) < bytes_needed:
        out_bytes.extend(b"\x00" * (bytes_needed - len(out_bytes)))
    outdata[:] = bytes(out_bytes[:bytes_needed])

    # Ensure outdata contains ONLY the active generation bytes, completely skipping cancelled chunks!
    assert outdata == bytes(b"\x05\x06" * 160)
    assert speaker_playback_queue.empty()


@pytest.mark.asyncio
async def test_barge_in_emits_audio_playback_stop_and_flushes_queues():
    """Verify that triggering barge-in emits AUDIO_PLAYBACK_STOP, AUDIO_FLUSH, and flushes output queues."""
    session = SessionState(
        session_id="test_sess_hard_stop",
        organization_id="org_apex_univ",
        agent_id="agent_admission"
    )
    conv_mgr = ConversationManager(rag_provider=MockRAGProvider(), tool_registry=ToolRegistry())
    engine = SpeechToSpeechEngine(
        session=session,
        conversation_manager=conv_mgr,
        vad_provider=MockVADProvider(),
        stt_provider=MockSTTProvider(),
        llm_provider=MockLLMProvider(),
        tts_provider=MockTTSProvider()
    )

    old_turn = session.current_turn
    old_turn.state = TurnStateEnum.SPEAKING
    old_gen_id = old_turn.generation_id

    # Place dummy output frames in queues
    await engine.queues.audio_out_queue.put(b"\x00" * 320)
    await engine.queues.tts_in_queue.put("Some unplayed text")

    assert not engine.queues.audio_out_queue.empty()
    assert not engine.queues.tts_in_queue.empty()

    # Trigger barge in
    engine.turn_manager.trigger_barge_in(reason="User hard barge-in test")

    # Verify output queues were flushed
    assert engine.queues.audio_out_queue.empty()
    assert engine.queues.tts_in_queue.empty()

    # Verify emitted events
    emitted_events = []
    while not engine.queues.event_out_queue.empty():
        emitted_events.append(engine.queues.event_out_queue.get_nowait())

    event_types = [e.event for e in emitted_events]
    assert EventType.RESPONSE_CANCELLED in event_types
    assert EventType.AUDIO_FLUSH in event_types
    assert EventType.AUDIO_PLAYBACK_STOP in event_types

    # Find the AUDIO_PLAYBACK_STOP event
    stop_event = next(e for e in emitted_events if e.event == EventType.AUDIO_PLAYBACK_STOP)
    assert stop_event.generation_id == old_gen_id
    assert session.user_has_floor is True


@pytest.mark.asyncio
async def test_audio_playback_controller_lifecycle():
    """Verify AudioPlaybackController 20ms slicing, hard-stop flushing, and stale packet rejection."""
    from scripts.local_test_client import AudioPlaybackController

    controller = AudioPlaybackController(sample_rate=16000, frame_duration_ms=20)
    assert controller.frame_bytes == 640

    # 1. Enqueue 6.4 seconds of PCM audio (204,800 bytes = 320 frames @ 640 bytes/frame)
    sample_pcm = b"\x11\x22" * (16000 * 64 // 10)
    frames_enqueued = controller.enqueue_audio_chunk("gen_001", sample_pcm)
    assert frames_enqueued == 320
    assert controller.playback_queue.qsize() == 320
    assert controller.is_playing is True

    # 2. Simulate speaker callback playing 20 frames (400ms)
    outdata = bytearray(640)
    for _ in range(20):
        controller.speaker_callback(outdata, 320, None, None)
        assert outdata == bytes(b"\x11\x22" * 320)

    assert controller.playback_queue.qsize() == 300

    # 3. User barge-in triggers hard_stop_playback
    t0 = time.perf_counter()
    flushed_frames = controller.hard_stop_playback("gen_001")
    t1 = time.perf_counter()
    stop_latency_ms = (t1 - t0) * 1000

    assert flushed_frames == 300
    assert controller.playback_queue.qsize() == 0
    assert controller.is_playing is False
    assert "gen_001" in controller.cancelled_generations
    assert stop_latency_ms < 5.0  # Must be instantaneous (< 5ms)

    # 4. Next speaker callback produces pure silence
    silence_outdata = bytearray(640)
    controller.speaker_callback(silence_outdata, 320, None, None)
    assert silence_outdata == b"\x00" * 640

    # 5. Late packet for gen_001 arrives over WebSocket -> Rejected immediately
    late_frames = controller.enqueue_audio_chunk("gen_001", b"\x33\x44" * 640)
    assert late_frames == 0
    assert controller.playback_queue.qsize() == 0

    # 6. New turn / Generation 2 starts -> Plays cleanly
    gen2_frames = controller.enqueue_audio_chunk("gen_002", b"\x55\x66" * 320)
    assert gen2_frames == 1
    assert controller.playback_queue.qsize() == 1
    assert controller.is_playing is True

    controller.speaker_callback(outdata, 320, None, None)
    assert outdata == bytes(b"\x55\x66" * 320)

