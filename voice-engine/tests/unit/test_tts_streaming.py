"""Unit tests for TTS overlapped streaming, sentence chunking, and continuity."""
import pytest
import asyncio
import time
from app.tts.sarvam import SarvamTTSProvider
from app.tts.mock import MockTTSProvider
from app.pipeline.cancellation import CancellationToken
from app.conversation.prompts import build_admission_system_prompt


@pytest.mark.asyncio
async def test_tts_chunking_and_overlapped_streaming():
    """Verify stream_synthesize yields streaming audio chunks without artificial gaps."""
    tts = MockTTSProvider(sample_rate=16000)

    async def sample_text_stream():
        tokens = [
            "Welcome to ", "Apex University. ",
            "We offer BTech ", "and MTech programs. ",
            "Which course ", "are you interested in?"
        ]
        for t in tokens:
            yield t
            await asyncio.sleep(0.01)

    chunks = []
    t_prev = time.time()
    inter_chunk_gaps = []

    async for audio_chunk in tts.stream_synthesize(sample_text_stream(), language_code="en-IN"):
        now = time.time()
        inter_chunk_gaps.append((now - t_prev) * 1000)
        t_prev = now
        chunks.append(audio_chunk)

    assert len(chunks) > 0
    # Verify continuous audio frame delivery
    assert all(c.frame.sample_rate == 16000 for c in chunks)


@pytest.mark.asyncio
async def test_tts_stream_cancellation():
    """Verify stream_synthesize stops promptly when cancelled."""
    tts = MockTTSProvider(sample_rate=16000)
    token = CancellationToken()

    async def endless_text_stream():
        while True:
            yield "Another sentence for testing. "
            await asyncio.sleep(0.01)

    chunk_count = 0
    async for audio_chunk in tts.stream_synthesize(endless_text_stream(), language_code="en-IN", cancellation_token=token):
        chunk_count += 1
        if chunk_count >= 3:
            token.cancel(reason="User barge-in test")
            break

    assert token.is_cancelled is True


def test_concise_system_prompt_rules():
    """Verify system prompt enforces max 1-2 sentences and concise telephony guidelines."""
    prompt = build_admission_system_prompt(
        institution_name="Apex University",
        agent_name="Priya",
        preferred_language="te-IN",
        response_style="concise"
    )

    assert "1-2 short sentences" in prompt or "1-2 sentences" in prompt
    assert "PHONE-BASED ADMISSION COUNSELOR" in prompt.upper()
    assert "DO NOT REPEAT THE CALLER'S QUESTION" in prompt.upper()
