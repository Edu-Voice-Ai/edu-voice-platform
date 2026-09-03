"""Unit tests for FastRouter in-memory TTS pre-caching, short-word preservation, and deduplication fix."""
import asyncio
import pytest
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.engine import SpeechToSpeechEngine
from app.conversation.router import FastQueryRouter
from app.tts.mock import MockTTSProvider
from app.vad.silero import SileroVADProvider
from app.stt.mock import MockSTTProvider
from app.llm.mock import MockLLMProvider
from app.conversation.manager import ConversationManager
from app.rag.mock import MockRAGProvider
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.cancellation import CancellationToken


@pytest.mark.asyncio
async def test_fast_router_all_standard_responses_not_empty():
    """Verify get_all_standard_responses returns full coverage of Indic and English queries."""
    responses = FastQueryRouter.get_all_standard_responses()
    assert len(responses) >= 15
    langs = {r[0] for r in responses}
    assert "te-IN" in langs
    assert "hi-IN" in langs
    assert "en-IN" in langs


@pytest.mark.asyncio
async def test_warmup_fast_query_cache_populates_in_memory_pcm():
    """Verify warmup_fast_query_cache synthesizes and stores PCM16 bytes in RAM."""
    tts = MockTTSProvider()
    await SpeechToSpeechEngine.warmup_fast_query_cache(tts)
    
    assert len(SpeechToSpeechEngine._cached_fast_audio) > 0
    # Check that a Telugu hostel response is in the cache
    te_hostel_key = 'te-IN:అవునండి, boys and girls కి separate AC and Non-AC hostels ఉన్నాయి. ఫుడ్ తో కలిపి annual fee 80,000 rupees.'
    assert te_hostel_key in SpeechToSpeechEngine._cached_fast_audio
    pcm = SpeechToSpeechEngine._cached_fast_audio[te_hostel_key]
    assert isinstance(pcm, bytes)
    assert len(pcm) > 0


@pytest.mark.asyncio
async def test_short_words_40ms_to_60ms_not_dropped_as_transient():
    """Verify short words (40ms - 60ms) are NOT discarded as transient noise."""
    session = SessionState(session_id="test_short_word_sess", organization_id="org_test", agent_id="agent_test")
    session.language = "te-IN"
    session.current_turn.state = TurnStateEnum.PROCESSING
    queues = PipelineQueueBundle()
    stt = MockSTTProvider(default_text="హలో")
    conv = ConversationManager(rag_provider=MockRAGProvider())

    engine = SpeechToSpeechEngine(
        session=session,
        vad_provider=SileroVADProvider(threshold=0.5),
        stt_provider=stt,
        llm_provider=MockLLMProvider(),
        tts_provider=MockTTSProvider(),
        conversation_manager=conv,
        queues=queues
    )

    # 40ms of audio (1280 bytes @ 16kHz 16-bit mono)
    audio_40ms = b"\x00" * (16 * 2 * 40)
    token = CancellationToken()

    await engine._process_stt_turn(
        audio_bytes=audio_40ms,
        turn_id="turn_40ms",
        generation_id="gen_40ms",
        token=token
    )

    # Transcript should be produced and submitted to llm_in_queue, NOT discarded
    assert not queues.llm_in_queue.empty()
    item = await queues.llm_in_queue.get()
    assert item["text"] == "హలో"
