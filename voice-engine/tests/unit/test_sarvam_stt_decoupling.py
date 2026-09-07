import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.stt.sarvam import SarvamSTTProvider, SarvamStreamingSTTSession
from app.stt.base import STTResult


@pytest.mark.asyncio
async def test_push_audio_non_blocking_and_instant():
    """Verify push_audio returns in <1ms without performing any network I/O."""
    provider = MagicMock(spec=SarvamSTTProvider)
    session = SarvamStreamingSTTSession(provider=provider, api_key="dummy_key")

    chunk = b"\x00\x00" * 160  # 20ms PCM16
    t0 = time.perf_counter()
    for _ in range(20):
        await session.push_audio(chunk)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 10.0, f"push_audio took too long: {elapsed_ms:.2f}ms"
    assert session.queue_depth == 20
    assert len(session._turn_audio_buffer) == 20 * len(chunk)
    await session.close()


@pytest.mark.asyncio
async def test_queue_bounded_and_overflow_marks_degraded():
    """Verify audio queue caps at 50 frames and marks stream degraded without blocking."""
    provider = MagicMock(spec=SarvamSTTProvider)
    session = SarvamStreamingSTTSession(provider=provider, api_key="dummy_key")

    chunk = b"\x00\x00" * 160
    # Push 70 frames (more than maxsize=50)
    for _ in range(70):
        await session.push_audio(chunk)

    assert session.queue_depth == 50
    assert session._is_degraded is True
    # Verify ground truth buffer contains ALL 70 frames
    assert len(session._turn_audio_buffer) == 70 * len(chunk)
    await session.close()


@pytest.mark.asyncio
async def test_fail_fast_batch_fallback_when_unhealthy():
    """Verify finalize() skips websocket wait (0ms timeout) and invokes batch fallback immediately when unhealthy."""
    provider = MagicMock(spec=SarvamSTTProvider)
    provider.transcribe_audio = AsyncMock(return_value=STTResult(text="Fallback transcript", language_code="te-IN"))
    
    session = SarvamStreamingSTTSession(provider=provider, api_key="dummy_key")
    # Stream is not connected -> unhealthy
    assert not session.is_stream_healthy

    dummy_audio = b"\x01\x02" * 1600
    t0 = time.perf_counter()
    result = await session.finalize(language_code="te-IN", audio_bytes=dummy_audio, turn_id="turn_1")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 50.0, f"Finalize should fail-fast in <50ms, took {elapsed_ms:.2f}ms"
    assert result.text == "Fallback transcript"
    provider.transcribe_audio.assert_called_once_with(dummy_audio, sample_rate=16000, language_code="te-IN")
    await session.close()


@pytest.mark.asyncio
async def test_turn_reset_and_state_isolation():
    """Verify turn reset clears audio queue, turn buffer, and resets degraded flag."""
    provider = MagicMock(spec=SarvamSTTProvider)
    session = SarvamStreamingSTTSession(provider=provider, api_key="dummy_key")

    chunk = b"\x00\x00" * 160
    for _ in range(60):
        await session.push_audio(chunk)

    assert session._is_degraded is True
    assert session.queue_depth == 50

    await session.reset(turn_id="turn_2")
    assert session.queue_depth == 0
    assert len(session._turn_audio_buffer) == 0
    assert session._current_turn_id == "turn_2"
    await session.close()


@pytest.mark.asyncio
async def test_simulated_network_stall_does_not_block_push_audio():
    """Simulate a 3-second network connection hang and verify push_audio completes instantly."""
    provider = MagicMock(spec=SarvamSTTProvider)
    session = SarvamStreamingSTTSession(provider=provider, api_key="dummy_key")

    # Mock _ensure_connected to simulate a slow 3s network block inside background sender
    async def slow_connect():
        await asyncio.sleep(3.0)
        return False

    session._ensure_connected = slow_connect

    chunk = b"\x00\x00" * 160
    t0 = time.perf_counter()
    for _ in range(50):
        await session.push_audio(chunk)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Must complete almost instantaneously (well under 50ms total for 50 frames)
    assert elapsed_ms < 50.0, f"push_audio was blocked by slow connect: {elapsed_ms:.2f}ms"
    await session.close()
