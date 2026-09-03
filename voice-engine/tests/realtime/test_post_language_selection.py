"""Automated regression tests for post-language-selection conversation flow and turn rotation."""
import pytest
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.turn_manager import TurnManager
from app.conversation.manager import ConversationManager


def test_turn_rotation_and_fresh_cancellation_token():
    """Verify start_new_turn produces a fresh turn with uncancelled token."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    t1 = session.current_turn
    assert t1.cancellation_token.is_cancelled is False

    # Cancel turn 1
    t1.cancel("Interrupted")
    assert t1.cancellation_token.is_cancelled is True
    assert t1.state == TurnStateEnum.INTERRUPTED

    # Start turn 2
    t2 = session.start_new_turn(reason="Test next turn")
    assert t2.turn_id != t1.turn_id
    assert t2.cancellation_token.is_cancelled is False
    assert t2.state == TurnStateEnum.LISTENING
    assert session.current_turn.cancellation_token.is_cancelled is False


def test_barge_in_rotates_to_fresh_turn():
    """Verify trigger_barge_in cancels old generation and immediately rotates to a clean uncancelled turn."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)

    # Simulate AI speaking
    session.current_turn.state = TurnStateEnum.SPEAKING
    old_turn_id = session.current_turn.turn_id

    # Trigger barge in
    tm.trigger_barge_in("User spoke during speaking")

    new_turn = session.current_turn
    assert new_turn.turn_id != old_turn_id
    assert new_turn.cancellation_token.is_cancelled is False
    assert new_turn.state in (TurnStateEnum.LISTENING, TurnStateEnum.LISTENING_AFTER_BARGE_IN)
    assert session.user_has_floor is True


def test_vad_speech_frame_turn_transitions():
    """Verify VAD state transitions and sustained speech requirements."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True  # Post-language-selection normal turn
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_speech_duration_ms=40, min_barge_in_duration_ms=160, min_silence_duration_ms=2000)

    # 1. Normal speech onset
    res1 = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert res1 is None  # Only 20ms accumulated
    res2 = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert res2 == "SPEECH_STARTED"  # 40ms reached
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 2. Silence detection (2000ms continuous silence)
    for _ in range(99):
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None
    res_end = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
    assert res_end == "SPEECH_ENDED"  # 2000ms reached
    assert session.current_turn.state == TurnStateEnum.PROCESSING


def test_language_selection_state_transition():
    """Verify language selection completes cleanly and transitions to LISTENING."""
    session = SessionState(session_id="test_sess", organization_id="org1", agent_id="agent1")
    cm = ConversationManager()

    ack = cm.handle_language_selection_or_switch(session, "Telugu")
    assert ack is not None
    assert session.preferred_language == "te-IN"
    assert session.language_selection_complete is True
