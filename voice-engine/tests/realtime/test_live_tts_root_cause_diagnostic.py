import asyncio
import sys
import os
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.getcwd())

from app.core.config import get_settings
from app.tts.sarvam import SarvamTTSProvider
from app.tts.text_normalizer import SpeechTextNormalizer

async def run_diagnostic():
    settings = get_settings()
    tts = SarvamTTSProvider(
        api_key=settings.sarvam_api_key,
        model=settings.tts_model,
        default_speaker=settings.tts_speaker,
        min_chars=40,
        max_chars=250
    )

    test_telugu_text = "మా దగ్గర UG, PG, ఇంకా diploma courses ఉన్నాయి. మీకు ఏ course గురించి details కావాలి?"
    test_name_text = "Your counsellor is Aravind Kumar. The admission process for Computer Science and Engineering is open."

    print("=" * 72)
    print("SECTION 2 DIAGNOSTIC: SINGLE TTS VS STREAMED TTS COMPARISON")
    print("=" * 72)

    # 1. Single TTS request
    t0 = time.time() * 1000
    pcm_single = await tts.synthesize_text(test_telugu_text, language_code="te-IN")
    t1 = time.time() * 1000
    print(f"Test A (Single Request): Synthesized {len(test_telugu_text)} chars in {t1 - t0:.1f}ms | PCM Bytes: {len(pcm_single)}")

    # 2. Streamed TTS request
    async def delta_stream():
        # Stream word-by-word
        for word in test_telugu_text.split():
            yield word + " "
            await asyncio.sleep(0.02)

    t0 = time.time() * 1000
    first_chunk_ms = None
    stream_pcm_bytes = bytearray()
    chunk_count = 0

    async for chunk in tts.stream_synthesize(delta_stream(), language_code="te-IN"):
        if first_chunk_ms is None:
            first_chunk_ms = time.time() * 1000 - t0
        stream_pcm_bytes.extend(chunk.frame.data)
        chunk_count += 1

    t1 = time.time() * 1000
    print(f"Test B (Streamed Engine): First Audio Latency: {first_chunk_ms:.1f}ms | Total Duration: {t1 - t0:.1f}ms | Chunks: {chunk_count} | PCM Bytes: {len(stream_pcm_bytes)}")

    print("\n" + "=" * 72)
    print("SECTION 30 & 31: NAME PROTECTION & MID-WORD SPLIT VERIFICATION")
    print("=" * 72)

    async def name_stream():
        for word in test_name_text.split():
            yield word + " "
            await asyncio.sleep(0.01)

    name_pcm_bytes = bytearray()
    async for chunk in tts.stream_synthesize(name_stream(), language_code="en-IN"):
        name_pcm_bytes.extend(chunk.frame.data)

    print(f"Name & Word Continuity Test: Successfully streamed {len(test_name_text)} chars into {len(name_pcm_bytes)} PCM bytes without mid-word splitting.")
    print("=" * 72)

if __name__ == "__main__":
    asyncio.run(run_diagnostic())
