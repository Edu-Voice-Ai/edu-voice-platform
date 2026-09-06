"""Deterministic tests for continuous speech, internal pauses, phonetic dips, and adaptive endpointing."""
import pytest
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.turn_manager import TurnManager
from app.pipeline.structured_input import StructuredInputMode


def test_continuous_speech_multi_clause_with_natural_pauses():
    """
    Test: 'I want to know what courses you have ... [200ms pause] ... and what the fees are ...
    [300ms pause] ... and whether hostel is available'
    Expected: Exactly ONE user turn (1 SPEECH_STARTED, 1 SPEECH_ENDED at the very end).
    """
    session = SessionState(session_id="test_continuous", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)

    events = []

    # 1. Clause 1: "I want to know what courses you have" (600ms speech = 30 frames)
    for _ in range(30):
        r = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
        if r:
            events.append(r)
    assert events == ["SPEECH_STARTED"]
    assert session.current_turn.state == TurnStateEnum.LISTENING
    turn_id = session.current_turn.turn_id

    # 2. Internal Pause 1: 200ms silence (10 frames)
    for _ in range(10):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            events.append(r)
    # MUST NOT END TURN
    assert events == ["SPEECH_STARTED"]
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 3. Clause 2: "and what the fees are" (500ms speech = 25 frames)
    for _ in range(25):
        r = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
        if r:
            events.append(r)
    assert events == ["SPEECH_STARTED"]

    # 4. Internal Pause 2: 300ms silence (15 frames)
    for _ in range(15):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            events.append(r)
    assert events == ["SPEECH_STARTED"]
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 5. Acoustic Dip: Unvoiced plosive /t/ or breath (40ms = 2 non-speech frames) inside clause
    tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
    tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
    # Speech resumes immediately
    for _ in range(20):
        r = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
        if r:
            events.append(r)
    assert events == ["SPEECH_STARTED"]

    # 6. Internal Pause 3: 260ms silence (13 frames, below 350ms threshold)
    for _ in range(13):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            events.append(r)
    assert events == ["SPEECH_STARTED"]
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 7. Clause 3: "and whether hostel is available" (600ms speech = 30 frames)
    for _ in range(30):
        r = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
        if r:
            events.append(r)
    assert events == ["SPEECH_STARTED"]

    # 8. Final sustained silence: 360ms silence (18 frames, threshold is 350ms for conversational turn)
    for _ in range(18):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            events.append(r)

    assert events == ["SPEECH_STARTED", "SPEECH_ENDED"]
    assert session.current_turn.state == TurnStateEnum.PROCESSING
    assert session.current_turn.turn_id == turn_id


def test_silence_does_not_accumulate_across_speech_segments():
    """Verify that multiple separate sub-threshold silences do NOT sum up to trigger premature endpointing."""
    session = SessionState(session_id="test_no_cum_silence", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)

    # Start speech
    for _ in range(10):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # 1st silence: 200ms (10 frames)
    for _ in range(10):
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None

    # Single speech frame resumes speech -> MUST IMMEDIATELY RESET SILENCE COUNTER!
    assert tm.handle_speech_frame(is_speech=True, frame_duration_ms=20) is None

    # 2nd silence: 200ms (10 frames)
    for _ in range(10):
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None

    # Resume speech
    assert tm.handle_speech_frame(is_speech=True, frame_duration_ms=20) is None

    # 3rd silence: 200ms (10 frames)
    for _ in range(10):
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None

    assert session.current_turn.state == TurnStateEnum.LISTENING


def test_short_answers_adaptive_timing():
    """Verify short confirmation ('Yes' / 'Telugu' <= 500ms speech) finalizes at 350ms silence."""
    session = SessionState(session_id="test_short_ans", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)

    # 300ms speech ("Yes")
    for _ in range(15):
        tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)

    # 280ms silence (14 frames) -> NOT finalized
    for _ in range(14):
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None

    # Reaching 360ms silence (4 more frames = 18 frames total, >350ms and >=2 consecutive)
    res = None
    for _ in range(4):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            res = r
    assert res == "SPEECH_ENDED"
    assert session.current_turn.state == TurnStateEnum.PROCESSING


def test_phonetic_dips_do_not_cut_off_speech():
    """Verify unvoiced plosives (/p/, /t/, /k/) and short dips (20-40ms) do not terminate speech."""
    session = SessionState(session_id="test_phonetic_dips", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)

    events = []
    # Speech with alternating unvoiced consonant dips
    for _ in range(5):
        # 80ms voiced speech
        for _ in range(4):
            r = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20)
            if r:
                events.append(r)
        # 20ms unvoiced consonant dip
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        if r:
            events.append(r)

    assert events == ["SPEECH_STARTED"]
    assert session.current_turn.state == TurnStateEnum.LISTENING
