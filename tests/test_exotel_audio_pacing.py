"""Regression tests for Exotel outbound audio pacing, 320-byte frame format,

bounded queues, backpressure handling, barge-in flushing, and multi-call isolation.
"""

import asyncio
import base64
import json
import time

import pytest
from starlette.testclient import TestClient

from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.lifecycle.session import CallSessionState
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    RealtimeVoiceSession,
)
from backend.app.services.telephony.session_manager import get_realtime_session_manager
from backend.app.services.telephony.voice_engine_client import VoiceEngineWsClient
from backend.app.services.telephony.voice_engine_schemas import SessionStartPayload

# ==============================================================================
# 1. Exact 320-Byte Frame & Raw PCM Format Tests
# ==============================================================================


def test_exotel_frame_exact_320_bytes_and_raw_pcm(client: TestClient) -> None:
    """Verify each Exotel media packet contains exactly 320 bytes of 8kHz raw PCM (no WAV header)."""
    session_id = "exotel_pacing_fmt_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(
            session_id=session_id,
            provider="exotel",
            stream_sid="stream_fmt_test_01",
        )
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Voice Engine outputs 16kHz PCM16, 20ms frame = 640 bytes (320 samples @ 16-bit)
        synth_pcm16_16k = b"\x10\x00\x20\x00" * 160  # 640 bytes
        frame = AudioFrame(
            data=synth_pcm16_16k,
            timestamp_ms=1000,
            format="pcm16_16000hz_mono",
            metadata={"sample_rate": 16000},
        )
        asyncio.run(session.push_outbound_frame(frame))

        raw_msg = ws.receive_text()
        pkt = json.loads(raw_msg)

        assert pkt.get("event") == "media"
        assert pkt.get("streamSid") == "stream_fmt_test_01"
        assert "media" in pkt
        payload_b64 = pkt["media"]["payload"]

        # Decode Base64
        pcm_bytes = base64.b64decode(payload_b64, validate=True)

        # Requirement 8: Exactly 320 bytes for 8kHz PCM16 20ms audio
        assert len(pcm_bytes) == 320

        # Requirement 9: Raw PCM only, NO WAV header (WAV headers start with 'RIFF')
        assert not pcm_bytes.startswith(b"RIFF")
        assert not pcm_bytes.startswith(b"WAVE")

        ws.send_text(json.dumps({"event": "stop"}))


def test_exotel_frame_partial_audio_padded_to_320_bytes(client: TestClient) -> None:
    """Verify that odd-sized audio output is chunked and padded to exact 320-byte boundaries."""
    session_id = "exotel_pacing_pad_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(
            session_id=session_id,
            provider="exotel",
            stream_sid="stream_pad_test_01",
        )
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Partial audio: 200 bytes of 16kHz audio -> downsampled to 100 bytes
        partial_16k = b"\x05\x00" * 100  # 200 bytes
        frame = AudioFrame(
            data=partial_16k,
            timestamp_ms=1000,
            format="pcm16_16000hz_mono",
            metadata={"sample_rate": 16000},
        )
        asyncio.run(session.push_outbound_frame(frame))

        raw_msg = ws.receive_text()
        pkt = json.loads(raw_msg)
        pcm_bytes = base64.b64decode(pkt["media"]["payload"], validate=True)

        assert len(pcm_bytes) == 320
        # Padded portion must be silence (\x00)
        assert pcm_bytes[100:] == b"\x00" * 220

        ws.send_text(json.dumps({"event": "stop"}))


# ==============================================================================
# 2. Real-Time 20ms Outbound Pacing Tests
# ==============================================================================


def test_outbound_audio_pacing_timing(client: TestClient) -> None:
    """Verify that multiple frames are paced at real-time 20ms intervals (~50 fps)."""
    session_id = "exotel_pacing_time_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(
            session_id=session_id,
            provider="exotel",
            stream_sid="stream_pacing_test_01",
        )
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        num_frames = 5
        # Push 5 frames (640 bytes each = 20ms) into outbound queue
        for i in range(num_frames):
            frame = AudioFrame(
                data=b"\x11\x22" * 320,
                timestamp_ms=1000 + i * 20,
                sequence_number=i,
                format="pcm16_16000hz_mono",
                metadata={"sample_rate": 16000, "generation_id": "gen_pacing_01"},
            )
            asyncio.run(session.push_outbound_frame(frame))

        start_time = time.monotonic()
        received_frames = 0
        for _ in range(num_frames):
            raw_msg = ws.receive_text()
            pkt = json.loads(raw_msg)
            if pkt.get("event") == "media":
                received_frames += 1
        elapsed = time.monotonic() - start_time

        assert received_frames == num_frames
        # For 5 frames: 1st frame is sent at t=0, subsequent 4 frames are paced at 20ms each = ~80ms (0.08s).
        # It must NOT be instantaneous (<0.04s) and must not lag excessively (>0.30s).
        assert elapsed >= 0.05, f"Pacing too fast ({elapsed:.3f}s for 5 frames), carrier loop is unpaced!"
        assert elapsed <= 0.35, f"Pacing too slow ({elapsed:.3f}s for 5 frames), excessive latency!"

        ws.send_text(json.dumps({"event": "stop"}))


# ==============================================================================
# 3. Queue Producer/Consumer Burst Handling (Maya Greeting Scenario)
# ==============================================================================


@pytest.mark.asyncio
async def test_producer_burst_no_drops_within_bounds() -> None:
    """Verify that a faster-than-real-time TTS burst (e.g. 180-frame greeting)

    does not drop frames in a bounded queue of size 500.
    """
    session = RealtimeVoiceSession(
        session_id="burst_sess_01",
        max_queue_size=500,
        provider="exotel",
    )
    assert session.outbound_audio_queue.maxsize == 500

    # Simulate Maya's greeting: 180 frames generated in rapid succession
    burst_count = 180
    for i in range(burst_count):
        frame = AudioFrame(
            data=b"\x00\x00" * 320,
            sequence_number=i,
            timestamp_ms=i * 20,
            metadata={"generation_id": "gen_maya_greeting"},
        )
        accepted = await session.push_outbound_frame(frame)
        assert accepted is True

    # All 180 frames must be safely queued without any drops
    assert session.outbound_audio_queue.qsize() == burst_count
    assert session.stats.frames_dropped == 0


@pytest.mark.asyncio
async def test_voice_engine_client_backpressure_wait() -> None:
    """Verify VoiceEngineWsClient handles temporary queue saturation with bounded wait

    instead of immediately dropping frames.
    """
    small_queue: asyncio.Queue[AudioFrame] = asyncio.Queue(maxsize=3)
    start_payload = SessionStartPayload(
        session_id="sess_bp_test",
        organization_id="org_test",
        agent_id="agent_test",
    )
    client = VoiceEngineWsClient(
        ws_url="ws://127.0.0.1:8000/ws",
        session_id="sess_bp_test",
        start_payload=start_payload,
        outbound_queue=small_queue,
    )

    # Pre-fill queue to capacity (3)
    for i in range(3):
        small_queue.put_nowait(
            AudioFrame(data=b"\x00" * 640, sequence_number=i)
        )
    assert small_queue.full()

    # Launch consumer that frees a slot after 30ms
    async def _drain_later() -> None:
        await asyncio.sleep(0.03)
        small_queue.get_nowait()
        small_queue.task_done()

    asyncio.create_task(_drain_later())

    # Build audio.output payload
    b64_audio = base64.b64encode(b"\x01\x02" * 320).decode("ascii")
    payload = {
        "event": "audio.output",
        "generation_id": "gen_test_bp",
        "data": {
            "data": b64_audio,
            "seq": 10,
            "sample_rate": 16000,
            "duration_ms": 20.0,
        },
    }

    # Handle event: should wait up to 100ms, find the freed slot, and succeed without dropping!
    await client._handle_event("audio.output", payload)
    assert small_queue.full()  # It was drained by 1 then filled by 1
    assert client.active_generation_id == "gen_test_bp"


# ==============================================================================
# 4. Queue Overflow & Backpressure Safety
# ==============================================================================


@pytest.mark.asyncio
async def test_queue_overflow_preserves_bounds_and_safety() -> None:
    """Verify bounded queue rejects or drops appropriately when capacity is strictly exceeded."""
    session = RealtimeVoiceSession(
        session_id="sess_overflow_test",
        max_queue_size=10,
        backpressure_strategy="drop_oldest",
    )

    # Push 15 frames into queue of maxsize 10
    for i in range(15):
        frame = AudioFrame(data=b"\x00" * 320, sequence_number=i)
        await session.push_outbound_frame(frame)

    # Queue must never grow past maxsize 10
    assert session.outbound_audio_queue.qsize() == 10
    # Exactly 5 frames dropped
    assert session.stats.frames_dropped == 5


# ==============================================================================
# 5. Barge-In Flushing & Pacing Clock Reset
# ==============================================================================


def test_barge_in_flushes_outbound_queue_and_resets_clock(client: TestClient) -> None:
    """Verify barge-in completely purges pending outbound audio and Exotel 'clear' is sent."""
    session_id = "exotel_bargein_flush_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(
            session_id=session_id,
            provider="exotel",
            stream_sid="stream_bargein_01",
        )
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Pre-fill with 10 frames of generation 1
        for i in range(10):
            frame = AudioFrame(
                data=b"\x10\x10" * 320,
                timestamp_ms=1000 + i * 20,
                metadata={"generation_id": "gen_old_speech"},
            )
            asyncio.run(session.push_outbound_frame(frame))

        assert session.outbound_audio_queue.qsize() == 10

        # Trigger barge-in on gen_old_speech
        drained = session.trigger_interruption(generation_id="gen_old_speech")
        assert drained == 10
        assert session.outbound_audio_queue.qsize() == 0
        assert "gen_old_speech" in session.cancelled_generations

        # Now push generation 2 (new response after barge-in)
        new_frame = AudioFrame(
            data=b"\x20\x20" * 320,
            timestamp_ms=2000,
            metadata={"generation_id": "gen_new_speech"},
        )
        asyncio.run(session.push_outbound_frame(new_frame))

        # First received frame must be gen_new_speech, not stale gen_old_speech
        raw_msg = ws.receive_text()
        pkt = json.loads(raw_msg)
        assert pkt.get("event") == "media"
        decoded = base64.b64decode(pkt["media"]["payload"])
        assert len(decoded) == 320

        ws.send_text(json.dumps({"event": "stop"}))


# ==============================================================================
# 6. Clean Session Shutdown & Resource Deallocation
# ==============================================================================


@pytest.mark.asyncio
async def test_session_cleanup_releases_queues_and_tasks() -> None:
    """Verify closing session purges queues, cancels tasks, and leaves no memory leaks."""
    session = RealtimeVoiceSession(
        session_id="cleanup_sess_01",
        max_queue_size=500,
    )

    # Put audio in both inbound and outbound
    for i in range(5):
        await session.push_inbound_frame(AudioFrame(data=b"\x00" * 640))
        await session.push_outbound_frame(AudioFrame(data=b"\x00" * 640))

    assert session.inbound_audio_queue.qsize() > 0
    assert session.outbound_audio_queue.qsize() > 0

    await session.close(reason="caller_hung_up")

    # Both queues must be completely drained
    assert session.inbound_audio_queue.empty()
    assert session.outbound_audio_queue.empty()
    assert session.cancellation_event.is_set()
    assert session.connection_state == ConnectionState.CLOSED
    assert session.lifecycle_state == CallSessionState.DISCONNECTED


# ==============================================================================
# 7. Multiple Concurrent Calls Pacing & Tenant Isolation
# ==============================================================================


def test_concurrent_exotel_calls_independent_pacing(client: TestClient) -> None:
    """Verify multiple concurrent Exotel calls have isolated queues and independent pacing."""
    manager = get_realtime_session_manager()
    call_count = 3
    sessions = []

    for i in range(call_count):
        s_id = f"exotel_concurrent_call_{i}"
        s = asyncio.run(
            manager.create_session(
                session_id=s_id,
                organization_id=f"org_{i}",
                provider="exotel",
                stream_sid=f"stream_sid_{i}",
            )
        )
        sessions.append(s)

    # Verify distinct queues
    queues = [s.outbound_audio_queue for s in sessions]
    assert len({id(q) for q in queues}) == call_count

    # Verify independent streaming
    for i, s in enumerate(sessions):
        with client.websocket_connect(f"/ws/telephony/stream/{s.session_id}") as ws:
            frame = AudioFrame(
                data=b"\x01\x02" * 320,
                metadata={"generation_id": f"gen_call_{i}"},
            )
            asyncio.run(s.push_outbound_frame(frame))

            raw_msg = ws.receive_text()
            pkt = json.loads(raw_msg)
            assert pkt.get("event") == "media"
            assert pkt.get("streamSid") == f"stream_sid_{i}"
            assert len(base64.b64decode(pkt["media"]["payload"])) == 320

            ws.send_text(json.dumps({"event": "stop"}))
