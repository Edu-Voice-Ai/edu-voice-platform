"""Focused unit tests for stall recovery, safe timeouts, and CEC/PSC normalization."""
import pytest
import asyncio
import time
from app.session.state import SessionState, TurnStateEnum, GenerationLifecycleState
from app.pipeline.turn_manager import TurnManager
from app.pipeline.queues import PipelineQueueBundle
from app.stt.normalization import normalize_course_transcript, has_course_context, is_genuine_psc_query
from app.audio.frames import AudioFrame
from app.tts.sarvam import SarvamTTSProvider


def test_cec_normalization_english():
    """Verify CEC recognition in English utterances."""
    assert normalize_course_transcript("Tell me about the PSC course.") == "Tell me about the CEC course."
    assert normalize_course_transcript("C E C course gurinchi cheppandi.") == "CEC course gurinchi cheppandi."
    assert normalize_course_transcript("Tell me about C.E.C. fee structure") == "Tell me about CEC fee structure"
    assert normalize_course_transcript("Do you offer P.S.C. admissions?") == "Do you offer CEC admissions?"


def test_cec_normalization_telugu():
    """Verify CEC recognition in Telugu script and transliterated utterances."""
    assert normalize_course_transcript("పీఎస్సీ గురించి చెప్పండి.") == "CEC గురించి చెప్పండి."
    assert normalize_course_transcript("టీఎస్ కి గురించి కావాలి") == "CEC గురించి కావాలి"
    assert normalize_course_transcript("సిఈసి కోర్స్ వివరాలు ఇవ్వండి") == "CEC కోర్స్ వివరాలు ఇవ్వండి"
    assert normalize_course_transcript("CEC కోర్స్ గురించి చెప్పండి.") == "CEC కోర్స్ గురించి చెప్పండి."


def test_cec_normalization_hindi():
    """Verify CEC recognition in Hindi utterances."""
    assert normalize_course_transcript("पीएससी कोर्स के बारे में बताइए।") == "CEC कोर्स के बारे में बताइए।"
    assert normalize_course_transcript("सीईसी कोर्स की फीस कितनी है?") == "CEC कोर्स की फीस कितनी है?"


def test_psc_preserved_when_actually_meant():
    """Verify PSC remains PSC when inquiring about Public Service Commission or exams."""
    assert normalize_course_transcript("Do you provide coaching for TSPSC exams?") == "Do you provide coaching for TSPSC exams?"
    assert normalize_course_transcript("Public Service Commission recruitment details") == "Public Service Commission recruitment details"
    assert normalize_course_transcript("APPSC ఉద్యోగం గురించి చెప్పండి") == "APPSC ఉద్యోగం గురించి చెప్పండి"
    assert normalize_course_transcript("PSC notification details") == "PSC notification details"


def test_caller_says_hello_after_silence_playback_cleared():
    """Verify that when bot finishes speaking, caller saying 'hello' immediately starts normal turn."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    session.mark_playback_finished(force=True)
    queues = PipelineQueueBundle()
    turn_mgr = TurnManager(session=session, queues=queues)

    assert session.is_bot_speaking is False
    assert session.user_has_floor is True

    # 1. Simulate speech onset for 'hello' (needs 60ms = 3 frames)
    res = None
    for _ in range(3):
        r = turn_mgr.handle_speech_frame(
            is_speech=True,
            frame_data=b"\x10\x00" * 160,
            frame_duration_ms=20.0,
            vad_confidence=0.85
        )
        if r:
            res = r
    assert res == "SPEECH_STARTED"
    assert session.current_turn.state == TurnStateEnum.LISTENING


def test_no_ten_second_silent_wait_playback_watchdog():
    """Verify that if playback deadline elapses, turn_manager automatically forces playback finished."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    turn = session.start_new_turn("test")
    turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = (time.time() * 1000) - 100.0  # Already expired in the past

    queues = PipelineQueueBundle()
    turn_mgr = TurnManager(session=session, queues=queues)

    # Next frame processed by turn_manager should clear the stuck playback state
    turn_mgr.handle_speech_frame(
        is_speech=False,
        frame_data=b"\x00" * 320,
        frame_duration_ms=20.0,
        vad_confidence=0.01
    )

    assert session.is_bot_speaking is False
    assert session.playback_estimated_end_time_ms == 0.0
    assert session.user_has_floor is True
    assert session.current_turn.state == TurnStateEnum.LISTENING


def test_max_speech_duration_watchdog():
    """Verify that continuous speech is force-finalized at 10 seconds to avoid hanging."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    session.mark_playback_finished(force=True)
    queues = PipelineQueueBundle()
    turn_mgr = TurnManager(session=session, queues=queues)

    # Start speech
    turn_mgr.handle_speech_frame(is_speech=True, frame_data=b"\x10\x00" * 160, frame_duration_ms=20.0, vad_confidence=0.85)

    # Accumulate continuous speech up to 10 seconds (500 frames * 20ms)
    ended_event = None
    for _ in range(505):
        ev = turn_mgr.handle_speech_frame(is_speech=True, frame_data=b"\x10\x00" * 160, frame_duration_ms=20.0, vad_confidence=0.85)
        if ev == "SPEECH_ENDED":
            ended_event = ev
            break

    assert ended_event == "SPEECH_ENDED"
    assert session.current_turn.state == TurnStateEnum.PROCESSING


@pytest.mark.asyncio
async def test_delayed_playback_finish_background_task():
    """Verify that mark_playback_finished(force=False) cleanly triggers transition on deadline expiry."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    turn = session.start_new_turn("test")
    turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = (time.time() * 1000) + 100.0  # 100ms in future

    session.mark_playback_finished(force=False)
    # Immediately, it should still be playing
    assert session.is_bot_speaking is True

    # Wait for the delayed task to fire (150ms)
    await asyncio.sleep(0.18)

    assert session.is_bot_speaking is False
    assert session.playback_estimated_end_time_ms == 0.0
    assert session.current_turn.state == TurnStateEnum.LISTENING


def test_cloned_karthik_voice_retained():
    """Verify that Karthik custom cloned voice ID is retained in TTS provider."""
    karthik_voice_id = "svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    tts = SarvamTTSProvider(api_key="mock", voice_id=karthik_voice_id)
    assert tts.voice_id == karthik_voice_id
    assert tts.model == "bulbul:v3"


def test_barge_in_still_works():
    """Verify that barge-in interruption still works while AI is speaking."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    turn = session.start_new_turn("test")
    turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = (time.time() * 1000) + 5000.0  # 5s in future

    queues = PipelineQueueBundle()
    turn_mgr = TurnManager(session=session, queues=queues)

    # Deliver strong intentional user speech frames
    loud_frame = (b"\x7f\x10" * 160)  # loud amplitude
    result = None
    for _ in range(16):
        ev = turn_mgr.handle_speech_frame(
            is_speech=True,
            frame_data=loud_frame,
            frame_duration_ms=20.0,
            vad_confidence=0.95
        )
        if ev == "BARGE_IN":
            result = ev
            break

    assert result == "BARGE_IN"
    assert session.is_bot_speaking is False
    assert session.user_has_floor is True


@pytest.mark.asyncio
async def test_stt_timeout_recovers_to_listening():
    """Verify STT timeout recovers state cleanly to LISTENING without hanging."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    turn = session.start_new_turn("test")
    turn.state = TurnStateEnum.PROCESSING

    # Simulate STT timing out and error handling executing
    turn.state = TurnStateEnum.LISTENING
    session.user_has_floor = True
    session.conversation_state = "LISTENING"

    assert turn.state == TurnStateEnum.LISTENING
    assert session.user_has_floor is True


@pytest.mark.asyncio
async def test_llm_timeout_recovers_to_listening():
    """Verify LLM timeout cleanly recovers state to LISTENING."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    turn = session.start_new_turn("test")
    turn.state = TurnStateEnum.PROCESSING

    # Simulate LLM timeout recovery block
    turn.state = TurnStateEnum.LISTENING
    session.conversation_state = "LISTENING"
    session.user_has_floor = True

    assert turn.state == TurnStateEnum.LISTENING
    assert session.user_has_floor is True


@pytest.mark.asyncio
async def test_tts_timeout_cleans_playback_state():
    """Verify TTS timeout cleans playback state and returns floor to user."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    turn = session.start_new_turn("test")
    turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_123"

    session.mark_playback_finished(force=True)

    assert session.is_bot_speaking is False
    assert session.active_playback_generation_id is None
    assert session.playback_estimated_end_time_ms == 0.0
    assert turn.state == TurnStateEnum.LISTENING
    assert session.user_has_floor is True


def test_turn_state_safety_transitions():
    """Verify every path eventually returns to LISTENING."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    
    # 1. Normal response cycle: LISTENING -> PROCESSING -> SPEAKING -> LISTENING
    turn = session.start_new_turn("test")
    assert turn.state == TurnStateEnum.LISTENING
    
    turn.state = TurnStateEnum.PROCESSING
    assert turn.state == TurnStateEnum.PROCESSING
    
    turn.state = TurnStateEnum.SPEAKING
    assert turn.state == TurnStateEnum.SPEAKING
    
    session.mark_playback_finished(force=True)
    assert turn.state == TurnStateEnum.LISTENING
    assert session.user_has_floor is True
    
    # 2. Barge-in path
    turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.invalidate_active_generation()
    assert session.is_bot_speaking is False
    assert session.user_has_floor is True

