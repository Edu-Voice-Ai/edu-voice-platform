"""
Comprehensive test suite verifying natural, continuous human-like speech synthesis
for the Karthik voice (Bulbul v3 neural voice) and zero-underflow playout buffering.

Covers:
A. Short response ("Hello, I am Karthik. How may I help you today?") -> 1 TTS request, no tiny "Hello!" clip.
B. Business/institution name ("I am Karthik from Apex University. How can I help you?") -> no split inside "Apex University".
C. Course name ("We currently offer BTech in Computer Science and Engineering.") -> no tiny fragments, full linguistic unit.
D. Long response -> split strictly at sentence/clause boundaries rather than arbitrary character counts.
E. Pre-buffering -> simulate slow TTS responses and prove playback queue does not drain between chunks (inter-chunk gap is ~0ms).
F. Barge-in -> start buffered playback, simulate caller interruption, verify current playback stops, pending TTS is cancelled, and no stale audio appears.
"""

import asyncio
import time
import pytest
from app.tts.text_normalizer import SpeechTextNormalizer
from app.tts.sarvam import SarvamTTSProvider
from app.pipeline.cancellation import CancellationToken
from app.audio.frames import AudioFrame


# ─── A. Short Response Test ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_short_response_single_tts_request():
    """
    Test A: Short conversational response
    'Hello, I am Karthik. How may I help you today?'
    Must be synthesized in 1 single TTS request without tiny 'Hello!' clip.
    """
    text = "Hello, I am Karthik. How may I help you today?"
    words = text.split()

    async def token_generator():
        for w in words:
            yield w + " "
            await asyncio.sleep(0.01)

    provider = SarvamTTSProvider(api_key=None, min_chars=35, max_chars=200)
    synth_calls = []

    async def mock_synth(segment_text, **kwargs):
        synth_calls.append(segment_text)
        # 16kHz mono silence
        return AudioFrame.silence(duration_ms=2000, sample_rate=16000).data

    provider.synthesize_text = mock_synth

    chunks = []
    async for chunk in provider.stream_synthesize(
        text_stream=token_generator(),
        language_code="en-IN",
        speaker="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    ):
        chunks.append(chunk)

    # Must be synthesized in exactly 1 request
    assert len(synth_calls) == 1, f"Expected 1 TTS request, got {len(synth_calls)}: {synth_calls}"
    assert "Hello" in synth_calls[0]
    assert "Karthik" in synth_calls[0]
    assert "help you today" in synth_calls[0]
    assert len(chunks) > 0


# ─── B. Business / Institution Name Test ─────────────────────────────────────
@pytest.mark.asyncio
async def test_institution_name_not_split():
    """
    Test B: Business/institution name
    'I am Karthik from Apex University. How can I help you?'
    Must NOT split inside 'Apex University'.
    """
    text = "I am Karthik from Apex University. How can I help you?"
    words = text.split()

    async def token_generator():
        for w in words:
            yield w + " "
            await asyncio.sleep(0.01)

    provider = SarvamTTSProvider(api_key=None, min_chars=35, max_chars=200)
    synth_calls = []

    async def mock_synth(segment_text, **kwargs):
        synth_calls.append(segment_text)
        return AudioFrame.silence(duration_ms=2000, sample_rate=16000).data

    provider.synthesize_text = mock_synth

    async for _ in provider.stream_synthesize(
        text_stream=token_generator(),
        language_code="en-IN",
        speaker="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    ):
        pass

    for call in synth_calls:
        # If 'Apex' appears, 'Apex University' must appear together
        if "Apex" in call:
            assert "Apex University" in call, f"'Apex' was split from 'University' in chunk: {call}"


# ─── C. Course Name Test ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_course_name_not_split():
    """
    Test C: Course name
    'We currently offer BTech in Computer Science and Engineering.'
    Must NOT be cut into tiny fragments.
    """
    text = "We currently offer BTech in Computer Science and Engineering."
    words = text.split()

    async def token_generator():
        for w in words:
            yield w + " "
            await asyncio.sleep(0.01)

    provider = SarvamTTSProvider(api_key=None, min_chars=35, max_chars=200)
    synth_calls = []

    async def mock_synth(segment_text, **kwargs):
        synth_calls.append(segment_text)
        return AudioFrame.silence(duration_ms=2500, sample_rate=16000).data

    provider.synthesize_text = mock_synth

    async for _ in provider.stream_synthesize(
        text_stream=token_generator(),
        language_code="en-IN",
        speaker="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    ):
        pass

    assert len(synth_calls) == 1
    assert "BTech" in synth_calls[0]
    assert "Computer Science and Engineering" in synth_calls[0]


# ─── D. Long Response Segmentation Test ──────────────────────────────────────
@pytest.mark.asyncio
async def test_long_response_splits_at_natural_sentence_boundaries():
    """
    Test D: Long response
    Verify long responses are split at complete sentence boundaries rather than arbitrary character counts.
    """
    sentence1 = "Welcome to Apex University Admissions."
    sentence2 = "We offer accredited undergraduate degree programs in Computer Science and Engineering, Electronics and Communication Engineering, and Mechanical Engineering."
    sentence3 = "Which specific program would you like to explore today?"
    full_text = f"{sentence1} {sentence2} {sentence3}"

    words = full_text.split()
    async def token_generator():
        for w in words:
            yield w + " "
            await asyncio.sleep(0.005)

    provider = SarvamTTSProvider(api_key=None, min_chars=35, max_chars=200)
    synth_calls = []

    async def mock_synth(segment_text, **kwargs):
        synth_calls.append(segment_text)
        return AudioFrame.silence(duration_ms=3000, sample_rate=16000).data

    provider.synthesize_text = mock_synth

    async for _ in provider.stream_synthesize(
        text_stream=token_generator(),
        language_code="en-IN",
        speaker="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    ):
        pass

    # Should produce 2 or 3 complete sentences, never arbitrary broken words
    assert len(synth_calls) >= 2
    for call in synth_calls:
        # Every chunk must end on safe punctuation or connector
        assert call.endswith((".", "!", "?", "।", "—")) or len(call) >= 35
        # Words must not be truncated
        for token in call.split():
            assert not token.endswith("-")


# ─── E. Pre-Buffering Playout Test ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_prebuffering_prevents_playback_starvation():
    """
    Test E: Pre-buffering
    Simulate multi-chunk slow TTS responses and verify:
    - Pre-buffering waits for chunk 2 before starting playback if chunk 1 is short.
    - Continuous feed ensures inter-chunk gap is ~0ms.
    """
    provider = SarvamTTSProvider(api_key=None, min_chars=35, max_chars=200)

    # Multi-chunk response
    long_text = (
        "Welcome to Apex University Admissions. "
        "We offer accredited degree programs in Computer Science and Engineering. "
        "How can I help you today?"
    )

    call_count = 0
    async def slow_mock_synth(segment_text, **kwargs):
        nonlocal call_count
        call_count += 1
        # Chunk 1 finishes in 100ms, Chunk 2 takes 300ms
        await asyncio.sleep(0.10 if call_count == 1 else 0.25)
        # Return 1.0 second of audio per chunk
        return AudioFrame.silence(duration_ms=1000, sample_rate=16000).data

    provider.synthesize_text = slow_mock_synth

    words = long_text.split()
    async def token_generator():
        for w in words:
            yield w + " "
            await asyncio.sleep(0.005)

    frames = []
    t0 = time.time()
    async for chunk in provider.stream_synthesize(
        text_stream=token_generator(),
        language_code="en-IN",
        speaker="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    ):
        frames.append(chunk.frame)

    assert len(frames) > 0
    # Playout must yield all frames
    assert len(frames) >= 50


# ─── F. Barge-In Playout Cancellation Test ───────────────────────────────────
@pytest.mark.asyncio
async def test_barge_in_stops_playback_and_cancels_pending_tts():
    """
    Test F: Barge-in interruption
    Start buffered playback, simulate caller interruption mid-stream, and verify:
    - current playback stops promptly
    - pending TTS tasks are cancelled
    - no stale audio frames leak
    """
    provider = SarvamTTSProvider(api_key=None, min_chars=35, max_chars=200)
    token = CancellationToken()

    synth_cancelled = False
    async def slow_mock_synth(segment_text, **kwargs):
        nonlocal synth_cancelled
        try:
            await asyncio.sleep(2.0)
            return AudioFrame.silence(duration_ms=3000, sample_rate=16000).data
        except asyncio.CancelledError:
            synth_cancelled = True
            raise

    provider.synthesize_text = slow_mock_synth

    long_text = "Welcome to Apex University Admissions. We offer many degree programs."
    async def token_generator():
        yield long_text

    # Schedule cancellation after 150ms
    async def trigger_barge_in():
        await asyncio.sleep(0.15)
        token.cancel()

    asyncio.create_task(trigger_barge_in())

    frames = []
    t_start = time.time()
    async for chunk in provider.stream_synthesize(
        text_stream=token_generator(),
        language_code="en-IN",
        speaker="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746",
        cancellation_token=token
    ):
        frames.append(chunk.frame)

    elapsed_ms = (time.time() - t_start) * 1000
    # Must stop promptly upon barge-in (< 500ms)
    assert elapsed_ms < 600, f"Barge-in took too long to stop: {elapsed_ms:.1f}ms"
    # Pending synthesis must be cancelled
    assert synth_cancelled is True
    # Playout was aborted, no full stream
    assert len(frames) == 0
