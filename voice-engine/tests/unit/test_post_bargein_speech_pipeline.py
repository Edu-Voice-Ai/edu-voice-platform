"""Unit tests verifying post-barge-in speech capture, inaudible clarification suppression, and buffer safety."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.turn_manager import TurnManager
from app.pipeline.engine import SpeechToSpeechEngine
from app.pipeline.cancellation import CancellationToken
from app.stt.sarvam import SarvamStreamingSTTSession, SarvamSTTProvider, STTResult
from app.audio.features import AcousticFeatures


@pytest.mark.asyncio
async def test_post_barge_in_inaudible_does_not_speak_clarification():
    """When a caller barges in and the initial fragment is empty/inaudible, engine MUST NOT speak clarification."""
    session = SessionState(session_id="test_post_barge_inaudible", organization_id="org1", agent_id="agent1", language="te-IN")
    queues = PipelineQueueBundle()
    mock_vad = MagicMock()
    mock_stt = MagicMock()
    mock_stt.transcribe_audio = AsyncMock(return_value=STTResult(text="", language_code="te-IN"))
    mock_llm = MagicMock()
    mock_tts = MagicMock()
    mock_conv = MagicMock()

    engine = SpeechToSpeechEngine(
        session=session,
        vad_provider=mock_vad,
        stt_provider=mock_stt,
        llm_provider=mock_llm,
        tts_provider=mock_tts,
        conversation_manager=mock_conv,
        queues=queues
    )
    engine._stt_session = None

    turn = session.current_turn
    turn.state = TurnStateEnum.LISTENING_AFTER_BARGE_IN
    turn.is_post_barge_in = True
    session.user_has_floor = True

    token = CancellationToken()
    audio_bytes = b"\x00\x00" * 3200

    await engine._process_stt_turn(audio_bytes, turn.turn_id, turn.generation_id, token)

    # Invariant: Must NOT queue any clarification TTS
    assert queues.tts_in_queue.empty(), "Clarification must not be placed in TTS queue for post-barge-in turn"
    # Invariant: Turn state must return to LISTENING
    assert turn.state == TurnStateEnum.LISTENING
    # Invariant: User retains conversational floor
    assert session.user_has_floor is True
    # Invariant: Assistant message history has no clarification
    assert len(session.messages) == 0


@pytest.mark.asyncio
async def test_sub_threshold_voiced_speech_does_not_speak_clarification():
    """Empty transcript with voiced speech < 160ms (ambient breath/cough) must not trigger clarification."""
    session = SessionState(session_id="test_sub_thresh_inaudible", organization_id="org1", agent_id="agent1", language="te-IN")
    queues = PipelineQueueBundle()
    mock_vad = MagicMock()
    mock_stt = MagicMock()
    mock_stt.transcribe_audio = AsyncMock(return_value=STTResult(text="[noise]", language_code="te-IN"))
    mock_llm = MagicMock()
    mock_tts = MagicMock()
    mock_conv = MagicMock()

    engine = SpeechToSpeechEngine(
        session=session,
        vad_provider=mock_vad,
        stt_provider=mock_stt,
        llm_provider=mock_llm,
        tts_provider=mock_tts,
        conversation_manager=mock_conv,
        queues=queues
    )
    engine._stt_session = None

    turn = session.current_turn
    turn.state = TurnStateEnum.PROCESSING
    engine.turn_manager._last_finalized_speech_ms = 80.0  # < 160ms

    token = CancellationToken()
    audio_bytes = b"\x00\x00" * 3200

    await engine._process_stt_turn(audio_bytes, turn.turn_id, turn.generation_id, token)

    assert queues.tts_in_queue.empty()
    assert turn.state == TurnStateEnum.LISTENING
    assert session.user_has_floor is True
    assert len(session.messages) == 0


def test_loud_caller_speech_overcomes_echo_correlation():
    """Loud speech (broadband_rms >= 0.035 or vocal_rms >= 0.030) must not be vetoed as echo even if echo_corr >= 0.60."""
    session = SessionState(session_id="test_loud_speech_echo", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=60)

    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True

    # Frame data with ~0.08 RMS
    loud_frame = (b"\x50\x10" * 160)

    # Acoustic features with high echo correlation (e.g. cross-correlation artifact) but loud genuine caller speech
    feat = AcousticFeatures(
        rms=0.08,
        snr_db=25.0,
        zcr=0.10,
        speech_band_ratio=0.88,
        pitch_periodicity=0.85,
        spectral_centroid=1800.0,
        echo_correlation=0.72,
        is_transient=False,
        is_breath_or_mouth=False,
        is_acoustic_echo=False,
        is_valid_speech=True,
        vocal_band_rms=0.07,
        vocal_energy_ratio=0.88,
        is_backchannel_hum=False,
        spectral_flatness=0.15,
        harmonicity=0.85,
        spectral_flux=0.60
    )

    # Feed frames to trigger barge-in
    res1 = tm.handle_speech_frame(is_speech=True, frame_data=loud_frame, frame_duration_ms=20, vad_confidence=0.95, acoustic_features=feat)
    assert res1 is None  # Frame 1
    res2 = tm.handle_speech_frame(is_speech=True, frame_data=loud_frame, frame_duration_ms=20, vad_confidence=0.95, acoustic_features=feat)
    assert res2 is None  # Frame 2
    res3 = tm.handle_speech_frame(is_speech=True, frame_data=loud_frame, frame_duration_ms=20, vad_confidence=0.95, acoustic_features=feat)
    assert res3 == "BARGE_IN", "Loud caller speech should overcome high cross-correlation and trigger BARGE_IN"
    assert session.current_turn.is_post_barge_in is True
    assert session.current_turn.barge_in_handled is True


@pytest.mark.asyncio
async def test_streaming_session_concurrent_turn_reset_isolation():
    """Finalizing an older turn must not clear or corrupt a subsequent turn that began buffering concurrently."""
    provider = SarvamSTTProvider(api_key="mock_key")
    provider.transcribe_audio = AsyncMock(return_value=STTResult(text="first turn query", language_code="te-IN"))
    session = SarvamStreamingSTTSession(provider=provider, language_code="te-IN")

    # Turn 1 buffers audio
    await session.push_audio(b"\x01" * 1600)
    session._current_turn_id = "turn_1"

    # Turn 2 begins while turn 1 finalizes
    session.reset_turn("turn_2")
    await session.push_audio(b"\x02" * 1600)

    # Finalize called for turn_1
    result = await session.finalize(language_code="te-IN", audio_bytes=b"\x01" * 1600, turn_id="turn_1")
    assert result.text == "first turn query"

    # Invariant: Turn 2's buffer must NOT be wiped by turn 1's finalization cleanup!
    assert len(session._turn_audio_buffer) == 1600
    assert session._current_turn_id == "turn_2"
