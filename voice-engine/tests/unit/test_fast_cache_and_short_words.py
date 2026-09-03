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

    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=240)

    # Frame of 20ms silence bytes
    dummy_frame = b"\x00" * 640

    # Simulate 10 frames of 'Hmm' hum: high VAD conf, but quiet and low spectral flux (< 0.15, rms < 0.035)
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
        spectral_flux=0.02,  # Very low flux (static hum < 0.15)
        is_backchannel_hum=True
    )

    for _ in range(15):
        transition = tm.handle_speech_frame(
            is_speech=True,
            frame_data=dummy_frame,
            frame_duration_ms=20,
            vad_confidence=0.95,  # High VAD confidence!
            acoustic_features=hum_features
        )
        assert transition is None, "Quiet Hmm (< 0.15 flux, < 0.035 rms) must NOT trigger barge-in!"

    # Now simulate real spoken word ("ఆగండి" / "Wait"):
    # Real speech has vocal_rms >= 0.030, spectral_flux >= 0.10, vocal_energy_ratio >= 0.55
    speech_features = AcousticFeatures(
        rms=0.042,
        snr_db=20.0,
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
        vocal_energy_ratio=0.85,
        spectral_flux=0.18,  # High spectral change from consonants/formant transitions
        is_backchannel_hum=False
    )

    triggered = False
    for _ in range(13):  # 12 frames = 240ms
        t = tm.handle_speech_frame(
            is_speech=True,
            frame_data=dummy_frame,
            frame_duration_ms=20,
            vad_confidence=0.90,
            acoustic_features=speech_features
        )
        if t == "BARGE_IN":
            triggered = True
            break

    assert triggered is True, "High energy word 'ఆగండి' (rms=0.042, flux=0.18) must trigger barge-in at 240ms!"


def test_robust_speech_detection_rejects_breaths_clicks_and_accepts_voiced_speech():
    """Verify robust multi-feature gating: rejects breath, clicks, and hums, but triggers on continuous voiced speech (180ms)."""
    import numpy as np
    from app.audio.features import AcousticFeatures, AcousticFeatureExtractor
    from app.pipeline.turn_manager import TurnManager

    session = SessionState(session_id="test_robust_voiced", organization_id="org_test", agent_id="agent_test")
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_playing_02"
    session.current_turn.state = TurnStateEnum.SPEAKING
    queues = PipelineQueueBundle()

    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=180)

    sr = 16000
    dummy_frame = b"\x00" * 640

    # 1. Breath noise: high ZCR, flat spectrum, low harmonicity
    breath_features = AcousticFeatures(
        rms=0.030,
        snr_db=10.0,
        zcr=0.42,
        speech_band_ratio=0.30,
        pitch_periodicity=0.12,
        spectral_centroid=3400.0,
        echo_correlation=0.0,
        is_transient=False,
        is_breath_or_mouth=True,
        is_acoustic_echo=False,
        is_valid_speech=False,
        vocal_band_rms=0.015,
        vocal_energy_ratio=0.30,
        spectral_flux=0.18,
        is_backchannel_hum=False,
        spectral_flatness=0.58,  # High flatness (white-noise like)
        harmonicity=0.12,
        pitch_f0_hz=0.0,
        is_voiced_frame=False
    )
    for _ in range(10):
        assert tm.handle_speech_frame(True, dummy_frame, 20, 0.85, breath_features) is None, "Breath noise must NOT trigger barge-in!"

    # 2. Transient line click: 1 frame burst with high centroid, zero harmonicity
    click_features = AcousticFeatures(
        rms=0.060,
        snr_db=22.0,
        zcr=0.02,
        speech_band_ratio=0.40,
        pitch_periodicity=0.05,
        spectral_centroid=3900.0,
        echo_correlation=0.0,
        is_transient=True,
        is_breath_or_mouth=False,
        is_acoustic_echo=False,
        is_valid_speech=False,
        vocal_band_rms=0.020,
        vocal_energy_ratio=0.40,
        spectral_flux=0.60,
        is_backchannel_hum=False,
        spectral_flatness=0.62,
        harmonicity=0.05,
        pitch_f0_hz=0.0,
        is_voiced_frame=False
    )
    assert tm.handle_speech_frame(True, dummy_frame, 20, 0.90, click_features) is None, "Line click must NOT trigger barge-in!"

    # 3. Real Voiced Speech across different pitches (e.g. female 240Hz):
    # energy >= 0.025, harmonicity >= 0.35, flatness <= 0.38, zcr <= 0.22, flux >= 0.08
    voiced_features = AcousticFeatures(
        rms=0.045,
        snr_db=20.0,
        zcr=0.09,
        speech_band_ratio=0.88,
        pitch_periodicity=0.75,
        spectral_centroid=1100.0,
        echo_correlation=0.0,
        is_transient=False,
        is_breath_or_mouth=False,
        is_acoustic_echo=False,
        is_valid_speech=True,
        vocal_band_rms=0.038,
        vocal_energy_ratio=0.85,
        spectral_flux=0.22,
        is_backchannel_hum=False,
        spectral_flatness=0.18,  # Low flatness (strong resonant formants)
        harmonicity=0.75,
        pitch_f0_hz=240.0,
        is_voiced_frame=True
    )

    triggered = False
    for _ in range(10):  # 9 frames = 180ms continuous persistence
        out = tm.handle_speech_frame(True, dummy_frame, 20, 0.92, voiced_features)
        if out == "BARGE_IN":
            triggered = True
            break
    assert triggered is True, "Continuous voiced frames (180ms) must trigger barge-in without fixed frequency restriction!"



def test_continuous_profile_refinement_every_5_turns():
    """Verify voice profile is re-averaged at turn 5."""
    import numpy as np
    from app.audio.speaker_lock import AdaptiveSpeakerVoiceProfiler, CallerVoiceProfile

    profiler = AdaptiveSpeakerVoiceProfiler(sample_rate=16000)
    profiler._profile = CallerVoiceProfile(
        pitch_f0_hz=150.0,
        spectral_centroid_hz=800.0,
        near_mic_crest_factor=3.5,
        baseline_rms=0.05,
        pitch_lower_hz=150.0 * 0.75,
        pitch_upper_hz=150.0 * 1.25,
    )
    profiler.is_enrolled = True

    # Generate new turn audio with pitch 170Hz
    t = np.linspace(0, 0.5, 8000, endpoint=False)
    turn_audio = (0.06 * np.sin(2 * np.pi * 170.0 * t)).astype(np.float32)

    # Turn 4: should NOT refine
    profiler.refine_profile(turn_audio, turn_number=4)
    assert profiler.profile.pitch_f0_hz == 150.0

    # Turn 5: SHOULD refine (re-averaged 70% historical, 30% new)
    profiler.refine_profile(turn_audio, turn_number=5)
    assert 150.0 < profiler.profile.pitch_f0_hz < 170.0
    assert profiler.profile.pitch_lower_hz == profiler.profile.pitch_f0_hz * 0.75


def test_telugu_ece_fee_query_matches_fast_router():
    """Verify 'కాదు నాకు ఈసీఈ ఫీజు ఎంత అని చెప్పండి.' matches FastRouter as SIMPLE ECE fees."""
    from app.rag.normalizer import SemanticQueryNormalizer
    from app.conversation.router import FastQueryRouter, QueryComplexity

    q = "కాదు నాకు ఈసీఈ ఫీజు ఎంత అని చెప్పండి."
    norm = SemanticQueryNormalizer.normalize(q)
    assert "ECE" in norm.courses_mentioned
    complexity = FastQueryRouter.classify_complexity(norm, q)
    assert complexity == QueryComplexity.SIMPLE


def test_post_playback_state_reset_guarantee():
    """Verify mark_playback_finished resets all speaking flags and arms VAD for LISTENING."""
    session = SessionState(session_id="test_reset", organization_id="org_test", agent_id="agent_test")
    session.is_bot_speaking = True
    session.user_has_floor = False
    session.active_playback_generation_id = "gen_123"
    session.current_turn.state = TurnStateEnum.SPEAKING
    assert session.is_assistant_speaking is True  # Computed property is True while speaking

    session.mark_playback_finished(force=True)

    assert session.is_bot_speaking is False
    assert session.is_assistant_speaking is False
    assert session.user_has_floor is True
    assert session.active_playback_generation_id is None
    assert session.current_turn.state == TurnStateEnum.LISTENING
    assert session.conversation_state == "LISTENING"


def test_telugu_hostel_and_course_queries_fast_route():
    """Verify common Telugu queries match FastQueryRouter as SIMPLE."""
    from app.rag.normalizer import SemanticQueryNormalizer, SemanticIntent
    from app.conversation.router import FastQueryRouter, QueryComplexity

    test_cases = [
        ("కోర్సులు ఏమున్నాయి?", SemanticIntent.LIST_AVAILABLE_COURSES),
        ("పార్సల్ ఫెసిలిటీ గురించి చెప్పండి.", SemanticIntent.HOSTEL_INQUIRY),
        ("హాస్టల్ వివరాలు చెప్పండి", SemanticIntent.HOSTEL_INQUIRY),
        ("హాస్టల్ ఫెసిలిటీ గురించి చెప్పండి.", SemanticIntent.HOSTEL_INQUIRY),
    ]

    for query_text, expected_intent in test_cases:
        norm = SemanticQueryNormalizer.normalize(query_text)
        assert norm.intent == expected_intent
        complexity = FastQueryRouter.classify_complexity(norm, query_text)
        assert complexity == QueryComplexity.SIMPLE

