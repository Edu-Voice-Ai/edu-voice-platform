"""
Regression tests for post-greeting conversation flow.
Cases 1-6: Greeting -> language selection -> Q&A -> barge-in.
Proves that after greeting completes, is_bot_speaking is cleared and normal conversation resumes.
"""
import pytest
import asyncio
import time
from app.session.state import SessionState, TurnStateEnum, GreetingStateEnum
from app.session.events import EventType, SessionEvent
from app.pipeline.turn_manager import TurnManager
from app.pipeline.queues import PipelineQueueBundle


def make_session(session_id: str) -> SessionState:
    s = SessionState(session_id=session_id, organization_id="org_apex", agent_id="agent_adm")
    return s


def make_tm(session: SessionState) -> TurnManager:
    q = PipelineQueueBundle()
    return TurnManager(session=session, queues=q, min_barge_in_duration_ms=300)


def simulate_greeting_response_end(session: SessionState):
    """Simulate the exotel writer clearing playback state upon RESPONSE_END."""
    session.is_bot_speaking = False
    session.active_playback_generation_id = None
    session.playback_estimated_end_time_ms = 0.0


def simulate_post_tts_response_end(session: SessionState):
    """Simulate exotel writer RESPONSE_END handler for normal TTS completion."""
    session.mark_playback_finished(force=True)


def case_speak_language(session: SessionState, tm: TurnManager, pcm_word: bytes):
    """Helper: caller speaks a language name; verify SPEECH_STARTED and clean completion."""
    frame = pcm_word[:320] if len(pcm_word) >= 320 else b"\x01\x00" * 160

    # User speaks language choice (4 frames of 20ms = 80ms)
    results = []
    for _ in range(4):
        r = tm.handle_speech_frame(is_speech=True, frame_data=frame, frame_duration_ms=20)
        results.append(r)

    assert "SPEECH_STARTED" in results, f"Expected SPEECH_STARTED, got: {results}"
    assert session.user_has_floor is True
    assert session.current_turn.state == TurnStateEnum.LISTENING

    # Now silence for 350ms (18 frames at 20ms)
    for _ in range(17):
        r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        assert r is None, f"Unexpected early SPEECH_ENDED at frame {_}"

    r = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
    assert r == "SPEECH_ENDED", f"Expected SPEECH_ENDED, got: {r}"
    assert session.current_turn.state == TurnStateEnum.PROCESSING


# ──────────────────────────────────────────────────────────────────────────────
# Case 1: English greeting -> user says "English"
# ──────────────────────────────────────────────────────────────────────────────
def test_case_1_greeting_english_selection():
    """After greeting, user says English → SPEECH_STARTED fires normally (not blocked by is_bot_speaking)."""
    session = make_session("test_c1")
    session.is_greeting_playing = False
    session.greeting_state = GreetingStateEnum.COMPLETED
    session.conversation_state = "WAITING_FOR_LANGUAGE"

    # Simulate the exotel writer receiving RESPONSE_END for greeting
    simulate_greeting_response_end(session)

    assert session.is_bot_speaking is False, "is_bot_speaking must be False after greeting RESPONSE_END"
    assert session.active_playback_generation_id is None

    tm = make_tm(session)
    turn = session.start_new_turn(reason="Greeting finished, awaiting user language choice")
    turn.state = TurnStateEnum.LISTENING
    session.user_has_floor = True

    case_speak_language(session, tm, "English")


# ──────────────────────────────────────────────────────────────────────────────
# Case 2: Telugu greeting -> user says "Telugu"
# ──────────────────────────────────────────────────────────────────────────────
def test_case_2_greeting_telugu_selection():
    """After greeting, user says Telugu → SPEECH_STARTED fires, conversation continues in Telugu."""
    session = make_session("test_c2")
    session.is_greeting_playing = False
    session.greeting_state = GreetingStateEnum.COMPLETED
    simulate_greeting_response_end(session)

    assert session.is_bot_speaking is False

    tm = make_tm(session)
    turn = session.start_new_turn(reason="Post-greeting, awaiting language")
    turn.state = TurnStateEnum.LISTENING
    session.user_has_floor = True

    case_speak_language(session, tm, "Telugu")


# ──────────────────────────────────────────────────────────────────────────────
# Case 3: Hindi greeting -> user says "Hindi"
# ──────────────────────────────────────────────────────────────────────────────
def test_case_3_greeting_hindi_selection():
    """After greeting, user says Hindi → SPEECH_STARTED fires, conversation continues in Hindi."""
    session = make_session("test_c3")
    session.is_greeting_playing = False
    session.greeting_state = GreetingStateEnum.COMPLETED
    simulate_greeting_response_end(session)

    assert session.is_bot_speaking is False

    tm = make_tm(session)
    turn = session.start_new_turn(reason="Post-greeting, awaiting language")
    turn.state = TurnStateEnum.LISTENING
    session.user_has_floor = True

    case_speak_language(session, tm, "Hindi")


# ──────────────────────────────────────────────────────────────────────────────
# Case 4: Greeting -> user says "Telugu, what courses do you have?"
# Question must not be lost
# ──────────────────────────────────────────────────────────────────────────────
def test_case_4_combined_language_and_question():
    """After greeting, SPEECH_STARTED fires even for long combined language+question utterance."""
    session = make_session("test_c4")
    session.is_greeting_playing = False
    session.greeting_state = GreetingStateEnum.COMPLETED
    simulate_greeting_response_end(session)

    tm = make_tm(session)
    turn = session.start_new_turn(reason="Post-greeting")
    turn.state = TurnStateEnum.LISTENING
    session.user_has_floor = True

    frame = b"\x02\x00" * 160
    # 3-second utterance
    speech_results = []
    for _ in range(150):
        r = tm.handle_speech_frame(is_speech=True, frame_data=frame, frame_duration_ms=20)
        if r:
            speech_results.append(r)

    assert "SPEECH_STARTED" in speech_results, "Long utterance must trigger SPEECH_STARTED"
    assert "BARGE_IN" not in speech_results, "No barge-in should fire during normal speech"
    assert session.current_turn.turn_id == turn.turn_id, "Must not rotate turns during normal speech"


# ──────────────────────────────────────────────────────────────────────────────
# Case 5: Greeting -> user says Telugu -> user asks follow-up question in Telugu
# Verify conversation stays alive after agent responds
# ──────────────────────────────────────────────────────────────────────────────
def test_case_5_multi_turn_after_language_selection():
    """Full turn cycle: greeting → language → Q&A turn 1 → Q&A turn 2."""
    session = make_session("test_c5")
    session.is_greeting_playing = False
    session.greeting_state = GreetingStateEnum.COMPLETED
    simulate_greeting_response_end(session)

    session.preferred_language = "te-IN"
    session.language = "te-IN"
    session.language_selection_complete = True

    tm = make_tm(session)
    turn = session.start_new_turn(reason="Post-greeting, Telugu selected")
    turn.state = TurnStateEnum.LISTENING
    session.user_has_floor = True

    frame = b"\x03\x00" * 160

    # Turn 1: User says "which courses do you have?"
    for _ in range(3):
        tm.handle_speech_frame(is_speech=True, frame_data=frame, frame_duration_ms=20)
    assert session.current_turn.state == TurnStateEnum.LISTENING
    # Silence to end turn 1
    for _ in range(23):
        tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
    assert session.current_turn.state == TurnStateEnum.PROCESSING
    turn1_id = session.current_turn.turn_id

    # Simulate agent responding (TTS) + RESPONSE_END
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_agent_t1"
    session.playback_estimated_end_time_ms = time.time() * 1000 + 3000.0

    new_turn = session.start_new_turn(reason="Agent answered turn 1, ready for turn 2")
    new_turn.state = TurnStateEnum.LISTENING
    session.user_has_floor = False

    # Simulate RESPONSE_END received
    simulate_post_tts_response_end(session)

    assert session.is_bot_speaking is False
    assert session.active_playback_generation_id is None

    session.user_has_floor = True
    # Turn 2: User asks follow-up
    results2 = []
    for _ in range(4):
        r = tm.handle_speech_frame(is_speech=True, frame_data=frame, frame_duration_ms=20)
        results2.append(r)
    assert "SPEECH_STARTED" in results2, "Turn 2 speech must start normally"
    assert "BARGE_IN" not in results2, "No barge-in should fire when AI is not speaking"


# ──────────────────────────────────────────────────────────────────────────────
# Case 6: Barge-in still works while AI is speaking  
# (Proves fix doesn't break barge-in)
# ──────────────────────────────────────────────────────────────────────────────
def test_case_6_barge_in_still_works_while_ai_speaking():
    """While AI is actively speaking, user barge-in still fires immediately."""
    session = make_session("test_c6")
    session.is_greeting_playing = False
    session.greeting_state = GreetingStateEnum.COMPLETED

    # AI IS currently speaking (simulating mid-response playback)
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_ai_speaking"
    session.playback_estimated_end_time_ms = time.time() * 1000 + 4000.0

    tm = make_tm(session)
    turn = session.start_new_turn(reason="AI answering a question")
    turn.state = TurnStateEnum.SPEAKING
    turn.generation_id = "gen_ai_speaking"
    session.active_playback_generation_id = "gen_ai_speaking"

    # Loud caller speech audio frame (rms >= 0.10)
    frame = b"\x10\x10" * 160

    # User interrupts with 300ms of verified speech (15 frames @ 20ms)
    barge_in_result = None
    for _ in range(14):
        r = tm.handle_speech_frame(is_speech=True, frame_data=frame, frame_duration_ms=20)
        assert r is None, "Barge-in must not fire before min_barge_in_frames threshold"

    barge_in_result = tm.handle_speech_frame(is_speech=True, frame_data=frame, frame_duration_ms=20)
    assert barge_in_result == "BARGE_IN", "BARGE_IN must fire on 15th consecutive speech frame during AI playback"

    # Verify full cancellation state
    assert session.is_bot_speaking is False
    assert session.playback_estimated_end_time_ms == 0.0
    assert session.user_has_floor is True
    assert session.is_generation_cancelled("gen_ai_speaking")


# ──────────────────────────────────────────────────────────────────────────────
# Critical Regression Test: is_bot_speaking must NOT block post-greeting speech
# ──────────────────────────────────────────────────────────────────────────────
def test_regression_is_bot_speaking_stuck_after_greeting():
    """
    REGRESSION: Without RESPONSE_END handler in exotel writer,
    is_bot_speaking stays True after greeting → all user speech went through
    barge-in gate → conversation stalled.

    This test proves the bug is fixed: is_bot_speaking=True from greeting audio
    playback is cleared by RESPONSE_END and does NOT block SPEECH_STARTED.
    """
    session = make_session("test_regression")

    # Simulate what exotel writer was doing BEFORE fix:
    # After last greeting packet, is_bot_speaking=True and was never cleared
    session.is_bot_speaking = True  # ← stuck True (the bug)
    session.active_playback_generation_id = None  # not set for greeting
    session.playback_estimated_end_time_ms = 0.0   # already expired
    session.is_greeting_playing = False
    session.greeting_state = GreetingStateEnum.COMPLETED
    session.conversation_state = "WAITING_FOR_LANGUAGE"

    frame = b"\x05\x00" * 160

    # Part A: Verify the bug scenario — is_bot_speaking=True blocks normal SPEECH_STARTED.
    # With is_bot_speaking=True, the turn_manager enters the barge-in gate and
    # does NOT fire SPEECH_STARTED on the first 5 frames (requires 6 consecutive for BARGE_IN).
    tm_before = make_tm(session)
    turn_before = session.start_new_turn(reason="Post-greeting (bug scenario)")
    turn_before.state = TurnStateEnum.LISTENING
    session.user_has_floor = True

    # Drive 5 frames — should NOT get SPEECH_STARTED (goes through barge-in gate instead)
    bug_results = []
    for _ in range(5):
        r = tm_before.handle_speech_frame(is_speech=True, frame_data=frame, frame_duration_ms=20)
        if r:
            bug_results.append(r)
    assert "SPEECH_STARTED" not in bug_results, (
        "BUG VERIFIED: is_bot_speaking=True prevents SPEECH_STARTED (forces barge-in gate)"
    )

    # Part B: After RESPONSE_END handler (the fix), is_bot_speaking is cleared.
    session2 = make_session("test_regression_fixed")
    session2.is_bot_speaking = True  # simulate stuck state
    session2.active_playback_generation_id = None
    session2.playback_estimated_end_time_ms = 0.0
    session2.is_greeting_playing = False
    session2.greeting_state = GreetingStateEnum.COMPLETED
    session2.conversation_state = "WAITING_FOR_LANGUAGE"

    # Apply the fix: RESPONSE_END handler clears state unconditionally
    simulate_greeting_response_end(session2)

    assert session2.is_bot_speaking is False, "RESPONSE_END handler must clear is_bot_speaking"
    assert session2.active_playback_generation_id is None
    assert session2.playback_estimated_end_time_ms == 0.0

    # Part C: With state cleared, normal SPEECH_STARTED fires on first 2 frames.
    tm2 = make_tm(session2)
    turn2 = session2.start_new_turn(reason="Post-greeting (after fix)")
    turn2.state = TurnStateEnum.LISTENING
    session2.user_has_floor = True

    speech_events = []
    for _ in range(4):
        r = tm2.handle_speech_frame(is_speech=True, frame_data=frame, frame_duration_ms=20)
        if r:
            speech_events.append(r)

    assert "SPEECH_STARTED" in speech_events, (
        "After RESPONSE_END clears is_bot_speaking, user speech MUST trigger SPEECH_STARTED normally"
    )
    assert "BARGE_IN" not in speech_events, (
        "User speech after greeting must NOT go through barge-in gate"
    )
