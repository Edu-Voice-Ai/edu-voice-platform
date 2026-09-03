"""Unit tests for Feature A (Human Vocal Frequency Locking & Spectral Noise Isolation) and Feature B (Inaudibility Clarification)."""
import pytest
import asyncio
import numpy as np
from app.audio.frames import AudioFrame
from app.audio.features import AcousticFeatureExtractor, AcousticFeatures
from app.vad.silero import SileroVADProvider
from app.pipeline.turn_manager import TurnManager
from app.pipeline.engine import SpeechToSpeechEngine
from app.pipeline.cancellation import CancellationToken
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.queues import PipelineQueueBundle
from app.conversation.manager import ConversationManager
from app.conversation.prompts import INAUDIBLE_CLARIFICATION_PHRASES, INAUDIBLE_ESCALATION_PHRASES
from app.stt.mock import MockSTTProvider
from app.llm.mock import MockLLMProvider
from app.tts.mock import MockTTSProvider
from app.vad.mock import MockVADProvider
from app.rag.mock import MockRAGProvider


def test_vocal_band_filter_frequency_isolation():
    """Verify 300Hz-3400Hz Butterworth filter passes voice band and attenuates low/high noise."""
    sample_rate = 16000
    n = 320  # 20ms frame
    t = np.linspace(0, 0.02, n, endpoint=False)

    # 1. 1000Hz tone (representative human voice formant)
    voice_tone = (0.30 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    voice_rms, voice_ratio, _ = AcousticFeatureExtractor.compute_vocal_band_features(voice_tone, sample_rate)
    assert voice_ratio >= 0.70, f"Voice band ratio should be >= 0.70, got {voice_ratio:.2f}"
    assert voice_rms >= 0.10, f"Voice band RMS should be >= 0.10, got {voice_rms:.4f}"

    # 2. 60Hz hum / low-frequency rumble (breathing, AC, wind)
    low_hum = (0.30 * np.sin(2 * np.pi * 60 * t)).astype(np.float32)
    _, low_ratio, _ = AcousticFeatureExtractor.compute_vocal_band_features(low_hum, sample_rate)
    assert low_ratio < 0.20, f"Low frequency hum ratio should be < 0.20, got {low_ratio:.2f}"

    # 3. 6000Hz hiss / click noise (typing, fan hiss)
    high_hiss = (0.30 * np.sin(2 * np.pi * 6000 * t)).astype(np.float32)
    _, high_ratio, _ = AcousticFeatureExtractor.compute_vocal_band_features(high_hiss, sample_rate)
    assert high_ratio < 0.10, f"High frequency hiss ratio should be < 0.10, got {high_ratio:.2f}"


def test_turn_manager_noise_spectral_rejection():
    """Loud noise with vocal_energy_ratio < 0.60 must be rejected as noise and not start speech onset."""
    session = SessionState(session_id="test_noise_rej", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_speech_duration_ms=40)
    session.current_turn.state = TurnStateEnum.LISTENING
    session.user_has_floor = True

    # Simulate loud mechanical noise (e.g. keyboard typing / door slam)
    # RMS is loud (0.08), but vocal_energy_ratio is low (0.30)
    noise_features = AcousticFeatures(
        rms=0.08,
        snr_db=18.0,
        zcr=0.35,
        speech_band_ratio=0.30,
        pitch_periodicity=0.05,
        spectral_centroid=4200.0,
        echo_correlation=0.0,
        is_transient=False,
        is_breath_or_mouth=False,
        is_acoustic_echo=False,
        is_valid_speech=False,
        vocal_band_rms=0.02,
        vocal_energy_ratio=0.30
    )

    # Feed 5 frames of loud noise with vad_confidence=0.50
    for _ in range(5):
        res = tm.handle_speech_frame(
            is_speech=True,
            frame_duration_ms=20.0,
            vad_confidence=0.50,
            acoustic_features=noise_features
        )
        assert res is None, "Noise frame must not trigger SPEECH_STARTED"

    assert tm.is_in_speech is False, "Turn manager must not enter in_speech state for non-vocal noise"


@pytest.mark.asyncio
async def test_inaudible_audio_clarification_turn_processing():
    """When VAD detects speech but STT returns empty or noise markers, bot speaks a polite clarification."""
    session = SessionState(session_id="test_inaudible", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    conv = ConversationManager(rag_provider=MockRAGProvider())

    engine = SpeechToSpeechEngine(
        session=session,
        vad_provider=MockVADProvider(),
        stt_provider=MockSTTProvider(default_text=""),
        llm_provider=MockLLMProvider(),
        tts_provider=MockTTSProvider(),
        conversation_manager=conv,
        queues=queues
    )

    session.language = "te-IN"
    session.preferred_language = "te-IN"
    session.language_selection_complete = True
    session.current_turn.state = TurnStateEnum.PROCESSING
    token = CancellationToken()

    # 1. 200ms audio with empty STT transcript -> clarification phrase spoken
    audio_200ms = b"\x00" * (16 * 2 * 200)
    await engine._process_stt_turn(
        audio_bytes=audio_200ms,
        turn_id="turn_1",
        generation_id="gen_1",
        token=token
    )

    assert session.consecutive_empty_turns == 1
    # Check that Telugu clarification phrase was queued to TTS
    item = await queues.tts_in_queue.get()
    assert item["delta"] == INAUDIBLE_CLARIFICATION_PHRASES["te-IN"]
    eof = await queues.tts_in_queue.get()
    assert eof["delta"] == "__EOF__"

    # 2. Second consecutive empty turn
    await engine._process_stt_turn(
        audio_bytes=audio_200ms,
        turn_id="turn_2",
        generation_id="gen_2",
        token=token
    )
    assert session.consecutive_empty_turns == 2
    item2 = await queues.tts_in_queue.get()
    assert item2["delta"] == INAUDIBLE_CLARIFICATION_PHRASES["te-IN"]
    await queues.tts_in_queue.get()  # __EOF__

    # 3. Third consecutive empty turn -> Escalates to counselor handoff prompt
    await engine._process_stt_turn(
        audio_bytes=audio_200ms,
        turn_id="turn_3",
        generation_id="gen_3",
        token=token
    )
    assert session.consecutive_empty_turns == 3
    item3 = await queues.tts_in_queue.get()
    assert item3["delta"] == INAUDIBLE_ESCALATION_PHRASES["te-IN"]
    await queues.tts_in_queue.get()  # __EOF__


@pytest.mark.asyncio
async def test_inaudible_audio_idle_line_guard():
    """Short noise blips (< 100ms) with empty transcript must NOT speak clarification (guard against false idle triggers)."""
    session = SessionState(session_id="test_idle_guard", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    conv = ConversationManager(rag_provider=MockRAGProvider())

    engine = SpeechToSpeechEngine(
        session=session,
        vad_provider=MockVADProvider(),
        stt_provider=MockSTTProvider(default_text=""),
        llm_provider=MockLLMProvider(),
        tts_provider=MockTTSProvider(),
        conversation_manager=conv,
        queues=queues
    )

    session.language = "en-IN"
    session.current_turn.state = TurnStateEnum.PROCESSING
    token = CancellationToken()

    # Audio of only 60ms (< 100ms)
    short_audio = b"\x00" * (16 * 2 * 60)
    await engine._process_stt_turn(
        audio_bytes=short_audio,
        turn_id="turn_short",
        generation_id="gen_short",
        token=token
    )

    # Verify no clarification was queued and engine safely returned to LISTENING
    assert queues.tts_in_queue.empty() is True
    assert session.current_turn.state == TurnStateEnum.LISTENING
    assert session.consecutive_empty_turns == 0


def test_telephony_barge_in_qualification_borderline_ratio():
    """Real phone calls with compression (ratio 0.35-0.50) or high confidence (>=0.85) must trigger barge-in."""
    session = SessionState(session_id="test_barge_borderline", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(
        session=session,
        queues=queues,
        barge_in_min_confidence=0.40,
        barge_in_min_rms=0.008,
        vocal_energy_ratio_threshold=0.35,
        min_barge_in_duration_ms=80  # 4 frames @ 20ms
    )
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_1"
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.user_has_floor = False

    # Frame matching the failed call: conf=0.999, rms=0.07, vocal_rms=0.039, vocal_ratio=0.31
    call_features = AcousticFeatures(
        rms=0.07,
        snr_db=15.0,
        zcr=0.15,
        speech_band_ratio=0.31,
        pitch_periodicity=0.40,
        spectral_centroid=1800.0,
        echo_correlation=0.0,
        is_transient=False,
        is_breath_or_mouth=False,
        is_acoustic_echo=False,
        is_valid_speech=True,
        vocal_band_rms=0.039,
        vocal_energy_ratio=0.31
    )

    results = []
    for _ in range(4):
        r = tm.handle_speech_frame(
            is_speech=True,
            frame_duration_ms=20.0,
            vad_confidence=0.999,
            acoustic_features=call_features
        )
        if r:
            results.append(r)

    assert "BARGE_IN" in results, "4 frames of caller speech during playback must trigger BARGE_IN even with borderline ratio"


def test_consecutive_barge_in_on_new_playback_generation():
    """Test 2 barge-in must succeed after Test 1 barge-in when bot speaks again."""
    session = SessionState(session_id="test_rearm", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=80)
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_1"
    session.current_turn.state = TurnStateEnum.SPEAKING

    features = AcousticFeatures(
        rms=0.05, snr_db=12.0, zcr=0.10, speech_band_ratio=0.70, pitch_periodicity=0.50,
        spectral_centroid=1200.0, echo_correlation=0.0, is_transient=False,
        is_breath_or_mouth=False, is_acoustic_echo=False, is_valid_speech=True,
        vocal_band_rms=0.04, vocal_energy_ratio=0.70
    )

    # 1. First interruption on gen_1
    res1 = None
    for _ in range(4):
        res1 = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.90, acoustic_features=features)
    assert res1 == "BARGE_IN"

    # 2. Assistant starts speaking a second response (gen_2)
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_2"
    session.current_turn.state = TurnStateEnum.SPEAKING

    # 3. Second interruption (Test 2) on gen_2
    res2 = None
    for _ in range(4):
        res2 = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.90, acoustic_features=features)

    assert res2 == "BARGE_IN", "Second interruption on gen_2 must trigger BARGE_IN"

