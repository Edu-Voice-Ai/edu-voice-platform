"""Unit tests for Sarvam Realtime Streaming STT WebSocket adapter and fallback mechanisms."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.stt.sarvam import SarvamSTTProvider, SarvamStreamingSTTSession
from app.stt.base import STTResult


@pytest.mark.asyncio
async def test_streaming_session_audio_push_and_turn_reset():
    """Verify audio chunks accumulate in turn buffer and clear cleanly on reset."""
    provider = SarvamSTTProvider(api_key="test_key")
    session = provider.create_streaming_session(language_code="en-IN")

    pcm_chunk_1 = b"\x00\x01" * 320  # 20ms @ 16kHz
    pcm_chunk_2 = b"\x00\x02" * 320

    await session.push_audio(pcm_chunk_1)
    await session.push_audio(pcm_chunk_2)

    assert len(session._turn_audio_buffer) == 1280

    await session.reset()
    assert len(session._turn_audio_buffer) == 0
    assert session._final_transcript == ""
    assert session._interim_transcript == ""

    await session.close()


@pytest.mark.asyncio
async def test_streaming_session_successful_realtime_finalize():
    """Verify streaming session returns low-latency transcript when WebSocket delivers final event."""
    provider = SarvamSTTProvider(api_key="test_key")
    session = provider.create_streaming_session(language_code="te-IN")

    mock_ws = AsyncMock()
    session._ws = mock_ws
    session._is_connected = True

    # Simulate incoming final transcript event from Sarvam server
    async def simulate_incoming():
        await asyncio.sleep(0.02)
        session._final_transcript = "అవును, కోర్సు వివరాలు చెప్పండి"
        session._final_language = "te-IN"
        session._final_event.set()

    asyncio.create_task(simulate_incoming())

    result = await session.finalize(language_code="te-IN")

    assert isinstance(result, STTResult)
    assert result.text == "అవును, కోర్సు వివరాలు చెప్పండి"
    assert result.language_code == "te-IN"
    assert mock_ws.send.called

    await session.close()


@pytest.mark.asyncio
async def test_streaming_session_timeout_fallback_to_batch_rest():
    """Verify streaming session seamlessly falls back to batch REST transcribe_audio on timeout."""
    provider = SarvamSTTProvider(api_key="test_key")
    session = provider.create_streaming_session(language_code="en-IN")

    mock_ws = AsyncMock()
    # WS is connected, but server never replies to flush (times out)
    session._ws = mock_ws
    session._is_connected = True

    pcm_data = b"\x00\x05" * 3200
    await session.push_audio(pcm_data)

    mock_rest_result = STTResult(text="What is the admission fee for BTech?", language_code="en-IN")
    with patch.object(provider, "transcribe_audio", AsyncMock(return_value=mock_rest_result)) as mock_transcribe:
        result = await session.finalize(language_code="en-IN")

        assert result.text == "What is the admission fee for BTech?"
        assert mock_transcribe.called
        assert len(mock_transcribe.call_args[0][0]) == 6400

    await session.close()


@pytest.mark.asyncio
async def test_streaming_session_ws_error_fallback_to_batch_rest():
    """Verify streaming session gracefully handles WebSocket connection errors and falls back."""
    provider = SarvamSTTProvider(api_key="test_key")
    session = provider.create_streaming_session(language_code="hi-IN")

    # No active WS connection (e.g. handshake failed or offline)
    session._ws = None
    session._is_connected = False

    pcm_data = b"\x00\x03" * 1600
    await session.push_audio(pcm_data)

    mock_rest_result = STTResult(text="हाँ, मुझे प्रवेश की जानकारी चाहिए", language_code="hi-IN")
    with patch.object(provider, "transcribe_audio", AsyncMock(return_value=mock_rest_result)) as mock_transcribe:
        result = await session.finalize(language_code="hi-IN")

        assert result.text == "हाँ, मुझे प्रवेश की जानकारी चाहिए"
        assert mock_transcribe.called

    await session.close()


@pytest.mark.asyncio
async def test_streaming_session_interim_transcript_fallback_when_final_missing():
    """Verify that if interim transcript arrived but final event flag didn't, interim transcript is used."""
    provider = SarvamSTTProvider(api_key="test_key")
    session = provider.create_streaming_session(language_code="en-IN")

    mock_ws = AsyncMock()
    session._ws = mock_ws
    session._is_connected = True

    async def simulate_incoming_interim():
        await asyncio.sleep(0.01)
        session._interim_transcript = "Hello, can you hear me"
        session._final_language = "en-IN"
        session._final_event.set()

    asyncio.create_task(simulate_incoming_interim())

    result = await session.finalize(language_code="en-IN")

    assert result.text == "Hello, can you hear me"
    assert result.language_code == "en-IN"

    await session.close()


@pytest.mark.asyncio
async def test_streaming_session_timeout_uses_interim_without_rest():
    """Flush timeout should return interim transcript immediately instead of waiting on batch REST."""
    provider = SarvamSTTProvider(api_key="test_key")
    session = provider.create_streaming_session(language_code="te-IN")

    mock_ws = AsyncMock()
    session._ws = mock_ws
    session._is_connected = True
    session._interim_transcript = "CSE fee entha"
    session._final_language = "te-IN"

    with patch.object(provider, "transcribe_audio", AsyncMock()) as mock_transcribe:
        result = await session.finalize(language_code="te-IN")
        assert result.text == "CSE fee entha"
        assert result.language_code == "te-IN"
        assert mock_transcribe.called is False

    await session.close()
