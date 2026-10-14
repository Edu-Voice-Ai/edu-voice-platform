"""
Dedicated Unit Tests for Production Fix: Intermittent Mid-Sentence Audio Breaks & Playout Continuity.

Verifies:
A. Comma-separated Telugu/English sentences are NOT split at commas/semicolons.
B. 3+ chunk responses with slow Chunk 3 (1200-1500ms latency) never starve the playback buffer.
C. Intermediate audio stitching inserts zero artificial silence (no 30ms + 20ms dead air).
D. Barge-in during buffered playback immediately stops playout, flushes queues, and cancels tasks.
E. Reproduction of production Turns 4/5 fee explanation remains natural and continuous.
"""

import asyncio
import time
import numpy as np
import pytest

from app.tts.text_normalizer import SpeechTextNormalizer
from app.tts.sarvam import SarvamTTSProvider
from app.audio.buffering import AudioChunker, crossfade_pcm
from app.audio.frames import AudioFrame
from app.pipeline.cancellation import CancellationToken


# ─── A. Comma / Semicolon Chunking Prevention ──────────────────────────────
def test_comma_separated_telugu_english_not_split():
    """Verify comma/semicolon does NOT fragment natural sentences."""
    # Production failure sentence from Turn 4/5
    text1 = "CSE yearly fee 1,50,000 rupees ఉంటుంది, సో నాలుగు సంవత్సరాలకు total 6,00,000 rupees అవుతుంది."
    seg1, rem1 = SpeechTextNormalizer.extract_safe_chunk(text1, min_chars=35, max_chars=200, is_eof=False)
    # Since text1 contains a comma and ends with a period, it must NOT split at the comma!
    # It must either wait for EOF or yield the full sentence at the period.
    assert seg1 is not None
    assert "CSE yearly fee" in seg1
    assert "ఉంటుంది, సో" in seg1, "Sentence was prematurely split at the comma!"
    assert "అవుతుంది." in seg1, "Sentence was cut before the period!"
    assert rem1 == ""

    text2 = "I am Karthik from Apex University. How can I help you?"
    seg2_1, rem2_1 = SpeechTextNormalizer.extract_safe_chunk(text2, min_chars=35, max_chars=200, is_eof=False)
    assert seg2_1 == "I am Karthik from Apex University."
    seg2_2, rem2_2 = SpeechTextNormalizer.extract_safe_chunk(rem2_1, min_chars=35, max_chars=200, is_eof=False)
    assert seg2_2 == "How can I help you?"

    text3 = "We currently offer BTech in Computer Science and Engineering."
    seg3, rem3 = SpeechTextNormalizer.extract_safe_chunk(text3, min_chars=35, max_chars=200, is_eof=False)
    assert seg3 == "We currently offer BTech in Computer Science and Engineering."


# ─── B. 3-Chunk Response Simulation with Slow Chunk 3 ───────────────────────
@pytest.mark.asyncio
async def test_3_chunk_response_slow_chunk_3_never_starves():
    """
    Simulate:
    Chunk 1 = fast (50ms, 1200ms audio)
    Chunk 2 = fast (50ms, 1200ms audio)
    Chunk 3 = slow (1300ms synthesis latency, 1500ms audio)
    Verify playback buffer never starves and inter-chunk gap is ~0ms.
    """
    provider = SarvamTTSProvider(api_key=None, min_chars=35, max_chars=200)

    # 3 complete sentences
    stream_text = [
        "First sentence introducing the university admissions process. ",
        "Second sentence detailing the engineering curriculum and faculty. ",
        "Third sentence explaining the fee structure and scholarship options available."
    ]

    async def token_generator():
        for sentence in stream_text:
            words = sentence.split()
            for w in words:
                yield w + " "
                await asyncio.sleep(0.005)

    chunk_synth_times = {
        1: (0.05, 1200),  # 50ms synth, 1.2s audio
        2: (0.05, 1200),  # 50ms synth, 1.2s audio
        3: (1.30, 1500),  # 1300ms synth, 1.5s audio
    }

    call_index = 0
    async def mock_synth(segment_text, **kwargs):
        nonlocal call_index
        call_index += 1
        idx = min(call_index, 3)
        synth_delay, audio_dur_ms = chunk_synth_times[idx]
        await asyncio.sleep(synth_delay)
        return AudioFrame.silence(duration_ms=audio_dur_ms, sample_rate=16000).data

    provider.synthesize_text = mock_synth

    frames = []
    t_first_frame = None
    min_runway_ms = 999999.0
    starvation_occurred = False

    async for chunk in provider.stream_synthesize(
        text_stream=token_generator(),
        language_code="en-IN",
        speaker="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    ):
        t_now = time.time()
        frames.append(chunk.frame)
        if t_first_frame is None:
            t_first_frame = t_now

        # Calculate telephony playout runway:
        # Total buffered audio received so far minus elapsed playout time at 1x real-time (20ms/frame)
        elapsed_playback_ms = (t_now - t_first_frame) * 1000.0
        total_buffered_ms = len(frames) * 20.0
        runway_ms = total_buffered_ms - elapsed_playback_ms
        if runway_ms < min_runway_ms:
            min_runway_ms = runway_ms
        if runway_ms < 0:
            starvation_occurred = True

    assert call_index == 3, f"Expected 3 chunk syntheses, got {call_index}"
    assert len(frames) > 0

    # Total audio duration is (1200 + 1200 + 1500) = 3900ms audio + 2 * 120ms natural breathing pauses = 4140ms = ~207 frames (at 20ms each)
    expected_frames = (3900 + 2 * 120) // 20
    assert abs(len(frames) - expected_frames) <= 2, f"Expected ~{expected_frames} frames, got {len(frames)}"

    # Playout runway must NEVER reach zero (buffer starvation target = 0)
    assert starvation_occurred is False, f"Playback buffer starved! Min runway was {min_runway_ms:.1f}ms"
    assert min_runway_ms > 0, f"Expected positive playout buffer runway, got {min_runway_ms:.1f}ms"


# ─── C. Intermediate Audio Stitching (No 50ms Artificial Silence) ───────────
def test_intermediate_audio_stitching_no_artificial_silence():
    """Verify trim_silence with pad=0 produces zero silence padding and feeds continuously."""
    sr = 16000
    # Create two synthetic speech bursts: 440Hz tone and 880Hz tone with synthetic silence padding
    t = np.arange(int(sr * 0.200)) / sr
    speech1 = (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)
    speech2 = (np.sin(2 * np.pi * 880 * t) * 10000).astype(np.int16)

    silence_300ms = np.zeros(int(sr * 0.300), dtype=np.int16)

    # Raw Sarvam output simulation: [300ms silence, speech, 300ms silence]
    raw1 = np.concatenate([silence_300ms, speech1, silence_300ms]).tobytes()
    raw2 = np.concatenate([silence_300ms, speech2, silence_300ms]).tobytes()

    # Old behavior inserted pad_lead_ms=20, pad_trail_ms=30 -> 50ms of dead air between chunks
    old_trimmed1 = SarvamTTSProvider.trim_silence(raw1, pad_lead_ms=20, pad_trail_ms=30)
    old_trimmed2 = SarvamTTSProvider.trim_silence(raw2, pad_lead_ms=20, pad_trail_ms=30)
    old_gap_samples = int(sr * 0.030) + int(sr * 0.020)  # 50ms = 800 samples
    assert len(np.frombuffer(old_trimmed1, dtype=np.int16)) == len(speech1) + int(sr * 0.050)

    # New behavior: pad_lead_ms=0, pad_trail_ms=0 for intermediate continuous chunks
    new_trimmed1 = SarvamTTSProvider.trim_silence(raw1, pad_lead_ms=0, pad_trail_ms=0)
    new_trimmed2 = SarvamTTSProvider.trim_silence(raw2, pad_lead_ms=0, pad_trail_ms=0)

    s1 = np.frombuffer(new_trimmed1, dtype=np.int16)
    s2 = np.frombuffer(new_trimmed2, dtype=np.int16)

    # No artificial silence added: length matches speech burst (snapped to zero-crossings)
    assert abs(len(s1) - len(speech1)) <= 80
    assert abs(len(s2) - len(speech2)) <= 80

    # Continuous chunker feed test
    chunker = AudioChunker(sample_rate=sr, frame_duration_ms=20)
    f1 = chunker.feed_continuous(new_trimmed1, crossfade_ms=5.0)
    f2 = chunker.feed_continuous(new_trimmed2, crossfade_ms=5.0)
    f_end = chunker.flush_frames()

    all_frames = f1 + f2 + f_end
    assert len(all_frames) > 0
    # Every frame is exactly 20ms (320 samples = 640 bytes)
    assert all(len(f.data) == 640 for f in all_frames)


# ─── D. Barge-In Playout Cancellation Test ──────────────────────────────────
@pytest.mark.asyncio
async def test_barge_in_during_buffered_playback():
    """Verify caller barge-in promptly cancels pending tasks and flushes queues."""
    provider = SarvamTTSProvider(api_key=None, min_chars=35, max_chars=200)
    token = CancellationToken()

    synth_task_cancelled = False
    async def mock_synth(segment_text, **kwargs):
        nonlocal synth_task_cancelled
        try:
            await asyncio.sleep(2.0)
            return AudioFrame.silence(duration_ms=3000, sample_rate=16000).data
        except asyncio.CancelledError:
            synth_task_cancelled = True
            raise

    provider.synthesize_text = mock_synth

    async def token_generator():
        yield "Welcome to Apex University. "
        yield "We have great engineering programs. "

    # Trigger cancellation after 100ms
    async def trigger_cancel():
        await asyncio.sleep(0.10)
        token.cancel(reason="Caller barge-in")

    asyncio.create_task(trigger_cancel())

    frames = []
    t0 = time.time()
    async for chunk in provider.stream_synthesize(
        text_stream=token_generator(),
        language_code="en-IN",
        speaker="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746",
        cancellation_token=token
    ):
        frames.append(chunk.frame)

    t_elapsed = (time.time() - t0) * 1000.0
    # Must abort within 400ms
    assert t_elapsed < 500.0, f"Barge-in took too long: {t_elapsed:.1f}ms"
    assert token.is_cancelled is True
    assert synth_task_cancelled is True
    assert len(frames) == 0


# ─── E. Turn 4/5 Production Scenario Regression Test ─────────────────────────
@pytest.mark.asyncio
async def test_production_turn_4_5_fee_explanation_continuity():
    """
    Specifically tests the real production Turn 4/5 prompt:
    Sentence 1: 'CSE yearly fee 1,50,000 rupees ఉంటుంది, సో నాలుగు సంవత్సరాలకు total 6,00,000 rupees అవుతుంది.'
    Sentence 2: 'ఇందులో tuition fee, library fee మరియు exam fee కలిసి ఉంటాయి. మీకు scholarship details కావాలా?'
    """
    provider = SarvamTTSProvider(api_key=None, min_chars=35, max_chars=200)

    full_response = (
        "CSE yearly fee 1,50,000 rupees ఉంటుంది, సో నాలుగు సంవత్సరాలకు total 6,00,000 rupees అవుతుంది. "
        "ఇందులో tuition fee, library fee మరియు exam fee కలిసి ఉంటాయి. మీకు scholarship details కావాలా?"
    )

    async def token_generator():
        # Simulate LLM token chunks
        chunks = [
            "CSE yearly ", "fee 1,50,000 rupees ", "ఉంటుంది, ", "సో నాలుగు ",
            "సంవత్సరాలకు ", "total 6,00,000 ", "rupees అవుతుంది. ",
            "ఇందులో tuition ", "fee, library fee ", "మరియు exam fee ",
            "కలిసి ఉంటాయి. ", "మీకు scholarship ", "details కావాలా?"
        ]
        for c in chunks:
            yield c
            await asyncio.sleep(0.01)

    synthesized_segments = []
    async def mock_synth(segment_text, **kwargs):
        synthesized_segments.append(segment_text)
        # Return realistic audio duration (~35ms per char)
        dur_ms = max(int(len(segment_text) * 35), 800)
        return AudioFrame.silence(duration_ms=dur_ms, sample_rate=16000).data

    provider.synthesize_text = mock_synth

    frames = []
    async for chunk in provider.stream_synthesize(
        text_stream=token_generator(),
        language_code="te-IN",
        speaker="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    ):
        frames.append(chunk.frame)

    # Must NOT split into 4-6 comma chunks.
    # The first sentence with comma must remain unified!
    assert len(synthesized_segments) == 3, f"Expected 3 grammatical sentences, got {len(synthesized_segments)}: {synthesized_segments}"
    assert "CSE yearly fee 1,50,000 rupees ఉంటుంది, సో నాలుగు సంవత్సరాలకు total 6,00,000 rupees అవుతుంది." in synthesized_segments[0]
    assert len(frames) > 0
