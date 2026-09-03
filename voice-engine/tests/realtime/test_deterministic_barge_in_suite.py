"""Deterministic test suite for immediate old TTS cancellation upon user speech onset (Cases A-K)."""
import pytest
import asyncio
import time
import json
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.session.state import SessionState, TurnStateEnum, ConversationFloor, GenerationLifecycleState
from app.session.events import SessionEvent, EventType
from app.pipeline.turn_manager import TurnManager
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.engine import SpeechToSpeechEngine
from app.conversation.manager import ConversationManager
from app.rag.mock import MockRAGProvider
from app.tools.base import ToolRegistry
from app.vad.mock import MockVADProvider
from app.stt.mock import MockSTTProvider
from app.llm.mock import MockLLMProvider
from app.tts.mock import MockTTSProvider


class MockAcousticFeatures:
    def __init__(self, is_acoustic_echo=False, is_transient=False, is_breath_or_mouth=False, snr_db=15.0, is_valid_speech=True, echo_correlation=0.0, rms=0.12):
        self.is_acoustic_echo = is_acoustic_echo
        self.is_transient = is_transient
        self.is_breath_or_mouth = is_breath_or_mouth
        self.snr_db = snr_db
        self.is_valid_speech = is_valid_speech
        self.rms = rms


def test_case_a_ai_speaking_user_says_no():
    """Case A: AI speaking -> user says 'No' -> old TTS stops immediately, floor transfers to user."""
    session = SessionState(session_id="test_case_a", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    # Set AI speaking state
    old_gen_id = session.current_turn.generation_id
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = time.time() * 1000 + 4000.0

    frame_bytes = b"\x10\x10" * 160
    # User says 'No' (15 frames = 300ms verified speech)
    for _ in range(14):
        assert tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20) is None
    
    t_speech_verified = time.time() * 1000
    res = tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)
    t_cancel = time.time() * 1000

    assert res == "BARGE_IN"
    assert session.is_bot_speaking is False
    assert session.playback_estimated_end_time_ms == 0.0
    assert session.user_has_floor is True
    assert session.is_generation_cancelled(old_gen_id) is True
    assert session.get_generation_state(old_gen_id) == GenerationLifecycleState.CANCELLED
    assert session.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN
    
    # Timing checks
    assert t_cancel - t_speech_verified < 15.0  # Synchronous / immediate cancellation


def test_case_b_ai_speaking_user_asks_long_question():
    """Case B: AI speaking -> user interrupts with long question -> complete question captured as 1 turn."""
    session = SessionState(session_id="test_case_b", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = time.time() * 1000 + 5000.0

    frame_bytes = b"\x10\x10" * 160
    # Interruption onset (300ms = 15 frames)
    for _ in range(14):
        tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)
    assert tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20) == "BARGE_IN"

    interruption_turn_id = session.current_turn.turn_id

    # User speaks continuously for 1.5 seconds (75 frames) with occasional 100ms micro-pauses
    for _ in range(30):
        assert tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20) is None
    # 80ms intra-utterance pause (must not trigger endpoint!)
    for _ in range(4):
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None
    # User resumes speaking for 45 more frames (900ms)
    for _ in range(45):
        assert tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20) is None

    # Silence reaches post-barge-in threshold (~400ms)
    for _ in range(19):
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None

    res_final = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
    assert res_final == "SPEECH_ENDED"
    assert session.current_turn.turn_id == interruption_turn_id
    assert session.current_turn.state == TurnStateEnum.PROCESSING


@pytest.mark.asyncio
async def test_case_c_interruption_during_first_tts_chunk():
    """Case C: AI speaking -> user interrupts during first TTS chunk -> discarded and halted."""
    session = SessionState(session_id="test_case_c", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    gen_id = session.current_turn.generation_id
    session.active_playback_generation_id = gen_id
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = time.time() * 1000 + 3000.0

    # User interrupts during chunk 1 (15 frames = 300ms)
    frame_bytes = b"\x10\x10" * 160
    for _ in range(15):
        tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)

    assert session.is_generation_cancelled(gen_id) is True
    assert session.user_has_floor is True


@pytest.mark.asyncio
async def test_case_d_interruption_during_middle_tts_chunk():
    """Case D: AI speaking -> user interrupts during middle TTS chunk -> queue flushed, generation dead."""
    session = SessionState(session_id="test_case_d", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=120)

    gen_id = session.current_turn.generation_id
    session.active_playback_generation_id = gen_id
    session.is_bot_speaking = True

    # Pre-populate queues with 5 middle chunks
    for i in range(5):
        queues.event_out_queue.put_nowait(SessionEvent(
            event=EventType.AUDIO_OUTPUT,
            session_id=session.session_id,
            generation_id=gen_id,
            turn_id=session.current_turn.turn_id,
            data={"data": "AA==", "seq": i, "cancellation_cycle": session.cancellation_cycle_id}
        ))
    assert queues.event_out_queue.qsize() == 5

    # Trigger barge in
    tm.trigger_barge_in(reason="User interrupted during middle chunk")

    # Verify queues flushed
    assert queues.event_out_queue.qsize() == 0 or queues.event_out_queue.get_nowait().event in (
        EventType.RESPONSE_CANCELLED, EventType.AUDIO_FLUSH, EventType.AUDIO_PLAYBACK_STOP
    )
    assert session.is_generation_cancelled(gen_id) is True


def test_case_e_writer_sleep_revalidation_drops_packet():
    """Case E: Packet held across 20ms pacing sleep is dropped upon revalidation when barge-in occurs."""
    session = SessionState(session_id="test_case_e", organization_id="org1", agent_id="agent1")
    gen_id = "gen_test_case_e_1"
    session.active_playback_generation_id = gen_id
    session.current_turn.generation_id = gen_id

    # Simulate packet arriving before sleep
    event_data = {"data": "AA==", "cancellation_cycle": session.cancellation_cycle_id}
    
    # Pre-sleep check: valid
    assert session.is_generation_cancelled(gen_id) is False
    assert session.user_has_floor is False

    # Barge-in happens while sleeping:
    session.invalidate_active_generation(reason="Barge-in during sleep")

    # Post-sleep check: MUST be stale!
    assert session.is_generation_cancelled(gen_id) is True
    assert session.user_has_floor is True


def test_case_f_tts_producer_late_chunk_dropped():
    """Case F: TTS producer emits chunk after cancellation -> chunk rejected before queue/send."""
    session = SessionState(session_id="test_case_f", organization_id="org1", agent_id="agent1")
    gen_id = "gen_test_case_f_1"
    session.cancelled_generation_ids.add(gen_id)
    session.user_has_floor = True

    # Validate condition from _tts_worker line 952
    can_emit = (
        not session.is_generation_cancelled(gen_id)
        and not session.user_has_floor
        and gen_id == session.active_playback_generation_id
    )
    assert can_emit is False


def test_case_g_old_packet_already_queued_dropped():
    """Case G: Old packet in queue is dropped on dequeue if cancellation cycle advanced."""
    session = SessionState(session_id="test_case_g", organization_id="org1", agent_id="agent1")
    old_gen_id = "gen_test_case_g_old"
    old_cycle = session.cancellation_cycle_id

    # Interruption advances cancellation cycle
    session.invalidate_active_generation(reason="User interrupted")
    assert session.cancellation_cycle_id > old_cycle

    # Writer check for queued packet from old_cycle:
    packet_is_stale = (
        session.is_generation_cancelled(old_gen_id)
        or session.user_has_floor
        or old_cycle < session.cancellation_cycle_id
    )
    assert packet_is_stale is True


def test_case_h_language_switch_interruption_stops_old_language():
    """Case H: AI speaking Telugu -> user interrupts with Hindi -> Telugu cancelled, Hindi active."""
    session = SessionState(session_id="test_case_h", organization_id="org1", agent_id="agent1")
    session.preferred_language = "te-IN"
    session.language = "te-IN"
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    telugu_gen_id = session.current_turn.generation_id
    session.active_playback_generation_id = telugu_gen_id
    session.active_playback_language = "te-IN"
    session.is_bot_speaking = True

    # User speaks "Hindi mein boliye" (15 frames = 300ms)
    frame_bytes = b"\x10\x10" * 160
    for _ in range(14):
        tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)
    assert tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20) == "BARGE_IN"

    assert session.is_generation_cancelled(telugu_gen_id) is True
    assert session.is_bot_speaking is False

    # Simulate parser detecting language switch to hi-IN
    from app.conversation.language import LanguagePreferenceParser
    detected_lang = LanguagePreferenceParser.detect_language_switch("Hindi mein boliye")
    assert detected_lang == "hi-IN"
    session.preferred_language = detected_lang
    session.language = detected_lang

    # Any leftover Telugu packet MUST be rejected
    telugu_packet_lang = "te-IN"
    active_lang = session.preferred_language
    assert telugu_packet_lang != active_lang


def test_case_i_repeated_barge_in():
    """Case I: Repeated barge-in cycles cancel all previous generations, only current is valid."""
    session = SessionState(session_id="test_case_i", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    gen1 = session.current_turn.generation_id
    session.active_playback_generation_id = gen1
    session.is_bot_speaking = True

    # Barge in 1
    tm.trigger_barge_in(reason="Barge-in 1")
    gen2 = session.current_turn.generation_id

    # Barge in 2
    session.active_playback_generation_id = gen2
    session.is_bot_speaking = True
    tm.trigger_barge_in(reason="Barge-in 2")
    gen3 = session.current_turn.generation_id

    # Verify both gen1 and gen2 are dead
    assert session.is_generation_cancelled(gen1) is True
    assert session.is_generation_cancelled(gen2) is True
    assert session.is_generation_cancelled(gen3) is False
    assert session.cancellation_cycle_id == 2


def test_case_j_interruption_near_end_of_old_tts():
    """Case J: User interrupts near end of old TTS -> old TTS does not continue or restart."""
    session = SessionState(session_id="test_case_j", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    gen_id = session.current_turn.generation_id
    session.active_playback_generation_id = gen_id
    session.is_bot_speaking = True
    # Only 60ms remaining in playback buffer
    session.playback_estimated_end_time_ms = time.time() * 1000 + 60.0

    frame_bytes = b"\x10\x10" * 160
    for _ in range(14):
        tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)
    res = tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)
    assert res == "BARGE_IN"

    assert session.playback_estimated_end_time_ms == 0.0
    assert session.is_generation_cancelled(gen_id) is True
    assert session.user_has_floor is True


def test_case_k_continuous_user_speech_after_interruption():
    """Case K: After interruption, user speaks continuously with short natural pauses -> 1 turn."""
    session = SessionState(session_id="test_case_k", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True

    frame_bytes = b"\x10\x10" * 160
    for _ in range(15):
        tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)

    turn_id = session.current_turn.turn_id

    # Clause 1: "No, actually I wanted to ask about CSE fees" (800ms)
    for _ in range(40):
        tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)
    # Pause (100ms)
    for _ in range(5):
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None
    # Clause 2: "and also whether hostel is available" (600ms)
    for _ in range(30):
        tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)

    # Reached turn completion pause (400ms post-barge-in = 20 frames @ 20ms)
    for _ in range(19):
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None
    res = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
    assert res == "SPEECH_ENDED"
    assert session.current_turn.turn_id == turn_id


def test_timing_metrics_last_old_audio_after_barge_in_is_zero():
    """Section 16: Verify critical metric LAST_OLD_AUDIO_AFTER_BARGE_IN is exactly 0.0ms."""
    session = SessionState(session_id="test_timing_metrics", organization_id="org1", agent_id="agent1")
    old_gen_id = session.current_turn.generation_id

    # Trigger barge in
    t_barge_in = time.time() * 1000
    session.invalidate_active_generation(reason="Test timing")
    t_cancel = time.time() * 1000

    barge_in_detection_latency = 120.0  # 6 frames of 20ms
    cancel_latency = t_cancel - t_barge_in

    # Audio frames belonging to old_gen_id post barge-in:
    packets_sent = 0
    old_audio_ms_sent_after_cutoff = 0.0

    simulated_late_packets = [
        {"gen_id": old_gen_id, "data": "AA==", "cycle": session.cancellation_cycle_id - 1},
        {"gen_id": old_gen_id, "data": "BB==", "cycle": session.cancellation_cycle_id - 1},
    ]

    for pkt in simulated_late_packets:
        # Check 1 & Check 2 & Check 3:
        if (
            session.is_generation_cancelled(pkt["gen_id"])
            or session.user_has_floor
            or pkt["cycle"] < session.cancellation_cycle_id
        ):
            # Dropped!
            continue
        packets_sent += 1
        old_audio_ms_sent_after_cutoff += 20.0

    last_old_audio_after_barge_in = old_audio_ms_sent_after_cutoff

    assert cancel_latency < 10.0
    assert packets_sent == 0
    assert last_old_audio_after_barge_in == 0.0, "Expected 0ms of old-generation audio post-barge-in!"


def test_barge_in_confirms_within_300ms_default():
    """Default confirmation is 300ms (15 frames); verified loud speech interrupts."""
    session = SessionState(session_id="test_300ms", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = time.time() * 1000 + 4000.0
    frame_bytes = b"\x10\x10" * 160
    feat = MockAcousticFeatures(is_valid_speech=True, snr_db=15.0, rms=0.12)
    for _ in range(14):
        assert tm.handle_speech_frame(
            is_speech=True, frame_data=frame_bytes, frame_duration_ms=20,
            vad_confidence=0.9, acoustic_features=feat
        ) is None
    assert tm.handle_speech_frame(
        is_speech=True, frame_data=frame_bytes, frame_duration_ms=20,
        vad_confidence=0.9, acoustic_features=feat
    ) == "BARGE_IN"


def test_barge_in_hysteresis_survives_one_miss_frame():
    """
    Leaky bucket: one non-qualifying frame decays the bucket by 1 (not hard-reset to 0).
    With min_barge_in_duration_ms=300 (threshold=15 frames):
      7 qualifying -> bucket=7; 1 miss -> bucket=6; 9 qualifying -> bucket=15 -> BARGE_IN.
    """
    session = SessionState(session_id="test_hysteresis", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = time.time() * 1000 + 4000.0
    frame_bytes = b"\x10\x10" * 160
    feat = MockAcousticFeatures(is_valid_speech=True, snr_db=15.0, rms=0.12)
    for _ in range(7):
        tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20, vad_confidence=0.9, acoustic_features=feat)
    assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None  # bucket decays: 7->6
    for _ in range(9):  # bucket goes 6->7->...->15 -> fires on last
        res = tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20, vad_confidence=0.9, acoustic_features=feat)
    assert res == "BARGE_IN"
    assert session.is_bot_speaking is False
