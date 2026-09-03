"""Automated endpointing timing and continuous silence tests."""
import pytest
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.turn_manager import TurnManager


def test_endpointing_one_second_pause_stays_same_turn():
    """Verify 1.0s pause inside a sentence resets silence timer and keeps same turn."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_silence_duration_ms=2000)

    # 1. User starts speaking "Hello my name is" (500ms speech)
    res_start = None
    for _ in range(25):
        r = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
        if r:
            res_start = r
    assert res_start == "SPEECH_STARTED"
    assert session.current_turn.state == TurnStateEnum.LISTENING
    turn_id_1 = session.current_turn.turn_id

    # 2. User pauses for 1000ms (50 frames of silence)
    res_pause = None
    for _ in range(50):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            res_pause = r
    # MUST NOT finalize turn after only 1000ms silence
    assert res_pause is None
    assert session.current_turn.state == TurnStateEnum.LISTENING
    assert session.current_turn.turn_id == turn_id_1

    # 3. User resumes speaking "Lokesh" (500ms speech)
    res_resume = None
    for _ in range(25):
        r = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
        if r:
            res_resume = r
    assert res_resume is None  # Already in speech, silence timer reset to 0.0
    assert session.current_turn.turn_id == turn_id_1

    # 4. User finishes and remains silent for 2000ms (100 frames of silence)
    res_end = None
    for _ in range(100):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            res_end = r
    assert res_end == "SPEECH_ENDED"
    assert session.current_turn.state == TurnStateEnum.PROCESSING


def test_endpointing_one_point_five_second_pause_stays_same_turn():
    """Verify 1.5s pause inside a sentence resets silence timer and keeps same turn."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_silence_duration_ms=2000)

    # 1. User starts speaking (400ms speech)
    for _ in range(20):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert session.current_turn.state == TurnStateEnum.LISTENING
    turn_id_1 = session.current_turn.turn_id

    # 2. User pauses for 1500ms (75 frames of silence)
    for _ in range(75):
        res = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        assert res is None  # MUST NOT finalize after 1.5s
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 3. User continues speaking (400ms speech)
    for _ in range(20):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert session.current_turn.turn_id == turn_id_1

    # 4. Final silence reaching 2000ms
    res_end = None
    for _ in range(100):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            res_end = r
    assert res_end == "SPEECH_ENDED"
    assert session.current_turn.state == TurnStateEnum.PROCESSING


def test_continuous_silence_threshold_exact_timing():
    """Verify endpointing requires exact 2000ms continuous silence."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_silence_duration_ms=2000)

    # Start speech
    for _ in range(10):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 1980ms of silence (99 frames)
    for _ in range(99):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        assert r is None

    # 100th frame (2000ms reached)
    r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
    assert r == "SPEECH_ENDED"
    assert session.current_turn.state == TurnStateEnum.PROCESSING


def test_no_speech_creates_no_turn():
    """Verify pure background silence does not create phantom turns."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_silence_duration_ms=2000)

    for _ in range(200):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        assert r is None
    assert session.current_turn.state == TurnStateEnum.IDLE


def test_adaptive_endpointing_short_utterance():
    """Verify short clear utterance (e.g. 'Yes', 'Telugu', 300ms speech) finalizes faster at 500ms."""
    session = SessionState(session_id="test_sess_adaptive_short", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, short_utterance_silence_ms=500, normal_silence_ms=650)

    # 300ms of short speech (15 frames)
    for _ in range(15):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 400ms silence (20 frames) -> not finalized yet (preserves natural micro-pause)
    for _ in range(20):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        assert r is None

    # Reaching 500ms silence (5 more frames = 25 total frames) -> finalizes at 500ms
    res = None
    for _ in range(5):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            res = r
    assert res == "SPEECH_ENDED"
    assert session.current_turn.state == TurnStateEnum.PROCESSING


def test_adaptive_endpointing_normal_conversational_utterance():
    """Verify normal sentence (800ms speech) uses 650ms silence and preserves 500ms mid-sentence pause."""
    session = SessionState(session_id="test_sess_adaptive_conv", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, short_utterance_silence_ms=500, normal_silence_ms=650)

    # 800ms speech (40 frames)
    for _ in range(40):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 500ms mid-sentence pause (25 frames) -> NOT finalized
    for _ in range(25):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        assert r is None
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # User finishes speaking and pauses to 660ms (33 frames total) -> finalizes at 650ms
    res = None
    for _ in range(8):  # 500ms + 160ms = 660ms
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            res = r
    assert res == "SPEECH_ENDED"
    assert session.current_turn.state == TurnStateEnum.PROCESSING


def test_adaptive_endpointing_structured_numeric_input_retains_2000ms():
    """Verify structured numeric input (phone, OTP) strictly retains conservative 2000ms endpoint."""
    from app.pipeline.structured_input import StructuredInputMode
    session = SessionState(session_id="test_sess_structured", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    session.structured_input_mode = StructuredInputMode.PHONE_NUMBER
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, structured_input_silence_ms=2000)

    # 300ms speech ("720")
    for _ in range(15):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 1500ms pause -> MUST NOT finalize!
    for _ in range(75):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        assert r is None
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # Finalizes only when 2000ms silence is reached
    res = None
    for _ in range(25):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            res = r
    assert res == "SPEECH_ENDED"
    assert session.current_turn.state == TurnStateEnum.PROCESSING


def test_post_barge_in_endpoint_is_400ms():
    """After barge-in, conversational endpointing uses ~400ms silence, not 800ms."""
    session = SessionState(session_id="test_sess_post_barge_ep", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=80)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    for _ in range(3):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert tm.handle_speech_frame(is_speech=True, frame_duration_ms=20) == "BARGE_IN"
    assert tm.effective_silence_duration_ms == 400.0
    for _ in range(10):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    for _ in range(19):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        assert r is None
    assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) == "SPEECH_ENDED"

