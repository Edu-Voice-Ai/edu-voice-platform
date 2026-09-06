"""
Unit tests for filler suppression, context-aware confirmation detection, and barge-in qualification.
"""
import pytest
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.engine import (
    is_filler_or_unprompted_backchannel,
    _did_assistant_ask_confirmation_or_question,
    PURE_FILLER_WORDS,
    CONFIRMATION_WORDS,
)
from app.pipeline.turn_manager import TurnManager
from app.pipeline.queues import PipelineQueueBundle
from app.audio.features import AcousticFeatures


def test_pure_filler_words_always_suppressed():
    session = SessionState(session_id="test-session", organization_id="test-org", agent_id="test-agent")
    # Even if bot asked a question, pure hesitation fillers are ignored
    session.append_message(role="assistant", content="Would you like to connect with an admissions counselor?")

    fillers = [
        "um", "umm", "uh", "uhh", "hmm", "hm", "hmmm", "mm", "mmm", "ah", "ahh",
        "ante", "antey", "aa", "aah",
        "ఉమ్", "ఉమ్మ్", "అంటే", "ఆ", "ఊ", "మ్మ్", "హ్మ్",
        "हम्म", "हम",
        "um uh", "hmm ante", "ఉమ్ అంటే", "హ్మ్ ఉమ్"
    ]
    for filler in fillers:
        should_ignore, reason = is_filler_or_unprompted_backchannel(filler, session)
        assert should_ignore is True, f"Expected '{filler}' to be ignored, got should_ignore={should_ignore}"
        assert reason == "pure_filler"


def test_confirmation_accepted_when_assistant_asked_question():
    session = SessionState(session_id="test-session-2", organization_id="test-org", agent_id="test-agent")
    # Assistant asked a question ending in '?'
    session.append_message(role="assistant", content="Would you like me to connect you with an admissions counselor?")

    confirmations = [
        "ha", "haa", "haan", "yes", "yeah", "yep", "ok", "okay", "sure",
        "హా", "అవును", "అవునండి", "సరే", "సరేనండి", "చెప్పండి",
        "avunu", "sare",
        "हाँ", "जी हाँ",
        "um yes", "ha um", "ఉమ్ అవును", "హా ఉమ్"
    ]
    for conf in confirmations:
        should_ignore, reason = is_filler_or_unprompted_backchannel(conf, session)
        assert should_ignore is False, f"Expected '{conf}' to be accepted as confirmation, got should_ignore={should_ignore}"
        assert reason == "valid_confirmation"


def test_confirmation_accepted_for_telugu_interrogative_markers_without_question_mark():
    session = SessionState(session_id="test-session-3", organization_id="test-org", agent_id="test-agent")
    # Telugu assistant question marker without explicit '?'
    session.append_message(role="assistant", content="అడ్మిషన్స్ కౌన్సెలర్ తో మాట్లాడించమంటారా")

    assert _did_assistant_ask_confirmation_or_question(session) is True

    should_ignore, reason = is_filler_or_unprompted_backchannel("హా", session)
    assert should_ignore is False
    assert reason == "valid_confirmation"

    should_ignore, reason = is_filler_or_unprompted_backchannel("అవును", session)
    assert should_ignore is False
    assert reason == "valid_confirmation"


def test_confirmation_suppressed_when_assistant_did_not_ask_question():
    session = SessionState(session_id="test-session-4", organization_id="test-org", agent_id="test-agent")
    # Assistant provided information, no question
    session.append_message(role="assistant", content="The BTech CSE annual tuition fee is one lakh twenty thousand rupees per year.")

    confirmations = ["ha", "haa", "హా", "avunu", "అవును", "yes", "ok", "okay", "hmm", "mm"]
    for conf in confirmations:
        should_ignore, reason = is_filler_or_unprompted_backchannel(conf, session)
        assert should_ignore is True, f"Expected standalone '{conf}' without prior question to be ignored, got should_ignore={should_ignore}"


def test_meaningful_speech_never_suppressed():
    session = SessionState(session_id="test-session-5", organization_id="test-org", agent_id="test-agent")
    session.append_message(role="assistant", content="Welcome to the university.")

    queries = [
        "what is the fee structure",
        "um what is the fee for cse",
        "ante nenu admissions gurinchi adagali",
        "హా బిటెక్ ఫీజు ఎంత?",
        "Telugu please",
        "English",
        "I want to apply for MBA",
    ]
    for q in queries:
        should_ignore, reason = is_filler_or_unprompted_backchannel(q, session)
        assert should_ignore is False, f"Expected meaningful speech '{q}' not to be ignored, got should_ignore={should_ignore}"
        assert reason == "meaningful_speech"


def test_turn_manager_backchannel_filler_does_not_interrupt_bot():
    session = SessionState(session_id="test-session-6", organization_id="test-org", agent_id="test-agent")
    tm = TurnManager(session=session, queues=PipelineQueueBundle())
    session.is_bot_speaking = True
    session.turn_count = 1

    # Simulate 10 frames of weak backchannel hum / filler sound
    for _ in range(10):
        feat = AcousticFeatures(
            rms=0.015,
            snr_db=15.0,
            zcr=0.05,
            speech_band_ratio=0.75,
            pitch_periodicity=0.8,
            spectral_centroid=400.0,
            echo_correlation=0.0,
            is_transient=False,
            is_breath_or_mouth=False,
            is_acoustic_echo=False,
            is_valid_speech=True,
            vocal_energy_ratio=0.75,
            spectral_flux=0.0005,
            is_backchannel_hum=True,
        )
        res = tm.handle_speech_frame(
            is_speech=True,
            vad_confidence=0.85,
            frame_duration_ms=20.0,
            acoustic_features=feat,
        )
        # Weak backchannel hum / filler sound should NOT trigger barge-in
        assert res != "BARGE_IN"
        assert tm._barge_in_stage != "CONFIRMED"


def test_turn_manager_strong_speech_interrupts_bot_promptly():
    session = SessionState(session_id="test-session-7", organization_id="test-org", agent_id="test-agent")
    tm = TurnManager(session=session, queues=PipelineQueueBundle())
    session.is_bot_speaking = True
    session.turn_count = 1

    triggered = False
    # Simulate strong crisp speech
    for _ in range(12):
        feat = AcousticFeatures(
            rms=0.08,
            snr_db=25.0,
            zcr=0.15,
            speech_band_ratio=0.92,
            pitch_periodicity=0.85,
            spectral_centroid=1800.0,
            echo_correlation=0.0,
            is_transient=False,
            is_breath_or_mouth=False,
            is_acoustic_echo=False,
            is_valid_speech=True,
            vocal_energy_ratio=0.92,
            spectral_flux=0.05,
            is_backchannel_hum=False,
        )
        res = tm.handle_speech_frame(
            is_speech=True,
            vad_confidence=0.95,
            frame_duration_ms=20.0,
            acoustic_features=feat,
        )
        if res == "BARGE_IN":
            triggered = True
            break

    assert triggered is True, "Strong user speech must trigger barge-in prompt interruption"


def test_turn_manager_loud_hmmm_does_not_interrupt_bot():
    """Verify that loud closed-mouth hums ('hmm', 'hmmm') with RMS > 0.10 never interrupt assistant playback."""
    session = SessionState(session_id="test-session-8", organization_id="test-org", agent_id="test-agent")
    tm = TurnManager(session=session, queues=PipelineQueueBundle())
    session.is_bot_speaking = True
    session.turn_count = 1

    # Simulate 15 frames (300ms) of loud 'hmmm...' into phone mic (RMS 0.11, low centroid 550Hz, low ZCR 0.08)
    for _ in range(15):
        feat = AcousticFeatures(
            rms=0.11,
            snr_db=22.0,
            zcr=0.08,
            speech_band_ratio=0.70,
            pitch_periodicity=0.85,
            spectral_centroid=550.0,
            echo_correlation=0.0,
            is_transient=False,
            is_breath_or_mouth=False,
            is_acoustic_echo=False,
            is_valid_speech=True,
            vocal_energy_ratio=0.70,
            spectral_flux=0.02,
            is_backchannel_hum=True,
        )
        res = tm.handle_speech_frame(
            is_speech=True,
            vad_confidence=0.98,
            frame_duration_ms=20.0,
            acoustic_features=feat,
        )
        # Should NEVER trigger barge-in
        assert res != "BARGE_IN"
        assert tm._barge_in_stage != "CONFIRMED"


