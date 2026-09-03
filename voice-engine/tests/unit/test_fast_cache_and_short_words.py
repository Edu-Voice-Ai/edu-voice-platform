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


def test_backchannel_hum_suppressed_even_with_high_vad_confidence():
    """Verify 'Hmm' with conf=0.99 and low flux is strictly suppressed during playback."""
    from app.pipeline.turn_manager import TurnManager
    from app.vad.features import AcousticFeatures

    session = SessionState(session_id="test_barge_suppress", organization_id="org_test", agent_id="agent_test")
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_playing_01"
    session.current_turn.state = TurnStateEnum.SPEAKING
    queues = PipelineQueueBundle()

    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=200)

    # Frame of 20ms silence bytes
    dummy_frame = b"\x00" * 640

    # Simulate 10 frames of 'Hmm' hum: high VAD conf, but low spectral flux / is_backchannel_hum=True
    hum_features = AcousticFeatures(
        rms=0.015,
        snr_db=12.0,
        zcr=0.04,
        speech_band_ratio=0.85,
        pitch_periodicity=0.5,
        spectral_centroid=600.0,
        echo_correlation=0.0,
        is_transient=False,
        is_breath_or_mouth=False,
        is_acoustic_echo=False,
        is_valid_speech=True,
        vocal_band_rms=0.014,
        vocal_energy_ratio=0.85,
        spectral_flux=0.02,  # Very low flux (static hum)
        is_backchannel_hum=True
    )

    for _ in range(10):
        transition = tm.handle_speech_frame(
            is_speech=True,
            frame_data=dummy_frame,
            frame_duration_ms=20,
            vad_confidence=0.95,  # High VAD confidence!
            acoustic_features=hum_features
        )
        assert transition is None, "Hmm with low flux must NOT trigger barge-in!"

    # Now simulate real interruption ("ఆగండి" / "Wait"): high flux, high confidence
    speech_features = AcousticFeatures(
        rms=0.040,
        snr_db=18.0,
        zcr=0.08,
        speech_band_ratio=0.90,
        pitch_periodicity=0.7,
        spectral_centroid=900.0,
        echo_correlation=0.0,
        is_transient=False,
        is_breath_or_mouth=False,
        is_acoustic_echo=False,
        is_valid_speech=True,
        vocal_band_rms=0.038,
        vocal_energy_ratio=0.90,
        spectral_flux=0.25,  # High flux (dynamic speech)
        is_backchannel_hum=False
    )

    triggered = False
    for _ in range(12):
        t = tm.handle_speech_frame(
            is_speech=True,
            frame_data=dummy_frame,
            frame_duration_ms=20,
            vad_confidence=0.95,
            acoustic_features=speech_features
        )
        if t == "BARGE_IN":
            triggered = True
            break

    assert triggered is True, "Dynamic real speech with flux=0.25 must trigger barge-in after 200ms!"


def test_telugu_ece_fee_query_matches_fast_router():
    """Verify 'కాదు నాకు ఈసీఈ ఫీజు ఎంత అని చెప్పండి.' matches FastRouter as SIMPLE ECE fees."""
    from app.rag.normalizer import SemanticQueryNormalizer
    from app.conversation.router import FastQueryRouter, QueryComplexity

    q = "కాదు నాకు ఈసీఈ ఫీజు ఎంత అని చెప్పండి."
    norm = SemanticQueryNormalizer.normalize(q)
    assert "ECE" in norm.courses_mentioned
    complexity = FastQueryRouter.classify_complexity(norm, q)
    assert complexity == QueryComplexity.SIMPLE

