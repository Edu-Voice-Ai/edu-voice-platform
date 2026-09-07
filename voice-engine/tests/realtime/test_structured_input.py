"""Automated test suite for Context-Aware Endpointing & Structured Numeric Input."""
import pytest
import asyncio
from app.pipeline.structured_input import (
    StructuredInputMode,
    DigitNormalizer,
    PhoneNumberValidator,
    StructuredInputDetector,
    NumericTurnAccumulator
)
from app.session.state import SessionState
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.turn_manager import TurnManager
from app.pipeline.engine import SpeechToSpeechEngine
from app.audio.frames import AudioFrame
from app.vad.mock import MockVADProvider
from app.stt.mock import MockSTTProvider
from app.llm.mock import MockLLMProvider
from app.tts.mock import MockTTSProvider
from app.conversation.manager import ConversationManager
from app.rag.mock import MockRAGProvider


def test_digit_normalizer():
    # 1. Plain digits with spaces and hyphens
    assert DigitNormalizer.extract_digits("720 770 2245") == "7207702245"
    assert DigitNormalizer.extract_digits("720-770-2245") == "7207702245"

    # 2. English spoken words
    assert DigitNormalizer.extract_digits("seven two zero seven seven zero two two four five") == "7207702245"
    assert DigitNormalizer.extract_digits("seven two zero double seven zero double two four five") == "7207702245"

    # 3. Hindi words (Devanagari)
    assert DigitNormalizer.extract_digits("सात दो शून्य सात सात शून्य दो दो चार पांच") == "7207702245"
    assert DigitNormalizer.extract_digits("७२०७७०२२४५") == "7207702245"

    # 4. Telugu words (Telugu Script)
    assert DigitNormalizer.extract_digits("ఏడు రెండు సున్నా ఏడు ఏడు సున్నా రెండు రెండు నాలుగు ఐదు") == "7207702245"
    assert DigitNormalizer.extract_digits("౭౨౦౭౭౦౨౨౪౫") == "7207702245"

    # 5. Roman Telugu / Hindi code-mix
    assert DigitNormalizer.extract_digits("yedu rendu sunna saat saat shunya double two four five") == "7207702245"

    # 6. Masking
    assert DigitNormalizer.mask_phone_number("7207702245") == "******2245"
    assert DigitNormalizer.mask_phone_number("720") == "***"


def test_phone_number_validator():
    # Valid Indian numbers
    is_v, clean = PhoneNumberValidator.validate_indian_mobile("7207702245")
    assert is_v and clean == "7207702245"

    is_v, clean = PhoneNumberValidator.validate_indian_mobile("+917207702245")
    assert is_v and clean == "7207702245"

    is_v, clean = PhoneNumberValidator.validate_indian_mobile("07207702245")
    assert is_v and clean == "7207702245"

    # Incomplete numbers
    is_v, _ = PhoneNumberValidator.validate_indian_mobile("720")
    assert not is_v

    is_v, _ = PhoneNumberValidator.validate_indian_mobile("7702245")
    assert not is_v


def test_structured_input_detector():
    # English prompt
    assert StructuredInputDetector.detect_mode_from_assistant_message(
        "Could you please tell me your phone number?"
    ) == StructuredInputMode.PHONE_NUMBER

    # Hindi prompt
    assert StructuredInputDetector.detect_mode_from_assistant_message(
        "कृपया अपना मोबाइल नंबर बता दीजिए।"
    ) == StructuredInputMode.PHONE_NUMBER

    # Telugu prompt
    assert StructuredInputDetector.detect_mode_from_assistant_message(
        "మీ phone number ఒకసారి చెప్తారా?"
    ) == StructuredInputMode.PHONE_NUMBER

    # Normal conversational prompt
    assert StructuredInputDetector.detect_mode_from_assistant_message(
        "We offer BTech in CSE and ECE. Would you like fee details?"
    ) == StructuredInputMode.NORMAL


def test_numeric_turn_accumulator_two_chunks():
    """Test: User says '720' ... pause 1s ... '7702245' -> Combined '7207702245'."""
    session_id = "test_sess_accum"
    segments = []

    # Chunk 1: "720"
    is_done, res, segments = NumericTurnAccumulator.handle_segment(
        session_id=session_id,
        current_segments=segments,
        new_transcript="720",
        mode=StructuredInputMode.PHONE_NUMBER
    )
    assert not is_done
    assert segments == ["720"]

    # Chunk 2: "7702245"
    is_done, res, segments = NumericTurnAccumulator.handle_segment(
        session_id=session_id,
        current_segments=segments,
        new_transcript="7702245",
        mode=StructuredInputMode.PHONE_NUMBER
    )
    assert is_done
    assert res == "7207702245"
    assert segments == []


def test_numeric_turn_accumulator_three_chunks():
    """Test: User says '720' ... '770' ... '2245' -> Combined '7207702245'."""
    session_id = "test_sess_3chunks"
    segments = []

    # Chunk 1: "720"
    is_done, _, segments = NumericTurnAccumulator.handle_segment(session_id, segments, "720")
    assert not is_done

    # Chunk 2: "770"
    is_done, _, segments = NumericTurnAccumulator.handle_segment(session_id, segments, "770")
    assert not is_done

    # Chunk 3: "2245"
    is_done, res, segments = NumericTurnAccumulator.handle_segment(session_id, segments, "2245")
    assert is_done
    assert res == "7207702245"


def test_numeric_turn_accumulator_spoken_words():
    """Test: Spoken words 'seven two zero' and 'seven seven zero two two four five'."""
    session_id = "test_sess_words"
    segments = []

    is_done, _, segments = NumericTurnAccumulator.handle_segment(session_id, segments, "seven two zero")
    assert not is_done

    is_done, res, segments = NumericTurnAccumulator.handle_segment(session_id, segments, "seven seven zero two two four five")
    assert is_done
    assert res == "7207702245"


def test_numeric_turn_accumulator_codemix():
    """Test: Code-mixed 'నా phone number 720' ... '7702245'."""
    session_id = "test_sess_codemix"
    segments = []

    is_done, _, segments = NumericTurnAccumulator.handle_segment(session_id, segments, "నా phone number 720")
    assert not is_done

    is_done, res, segments = NumericTurnAccumulator.handle_segment(session_id, segments, "7702245")
    assert is_done
    assert res == "7207702245"


def test_context_aware_endpointing_silence_thresholds():
    """Verify TurnManager dynamically changes silence tolerance between normal and numeric modes."""
    session = SessionState(session_id="s1", organization_id="org1", agent_id="a1")
    queues = PipelineQueueBundle()
    tm = TurnManager(
        session=session,
        queues=queues,
        min_silence_duration_ms=400,
        language_selection_silence_ms=1000,
        structured_input_silence_ms=2000
    )

    # 1. Normal mode (after language selection) -> 400ms silence tolerance
    session.structured_input_mode = "NORMAL"
    session.language_selection_complete = True
    assert tm.effective_silence_duration_ms == 400

    # 2. Language selection mode (before selection) -> 1000ms silence tolerance
    session.language_selection_complete = False
    assert tm.effective_silence_duration_ms == 1000

    # 3. Phone number mode -> 2000ms silence tolerance
    session.structured_input_mode = "PHONE_NUMBER"
    assert tm.effective_silence_duration_ms == 2000

    # 4. Pending numeric input buffer -> 2000ms silence tolerance
    session.structured_input_mode = "NORMAL"
    session.language_selection_complete = True
    session.numeric_segments = ["720"]
    assert tm.effective_silence_duration_ms == 2000


@pytest.mark.asyncio
async def test_concurrent_sessions_numeric_isolation():
    """Test 2 simultaneous sessions entering numeric input mode independently."""
    sess_a = SessionState(session_id="sess_A", organization_id="org1", agent_id="a1")
    sess_b = SessionState(session_id="sess_B", organization_id="org1", agent_id="a1")

    # Session A receives "720"
    _, _, sess_a.numeric_segments = NumericTurnAccumulator.handle_segment(
        sess_a.session_id, sess_a.numeric_segments, "720"
    )

    # Session B receives "987"
    _, _, sess_b.numeric_segments = NumericTurnAccumulator.handle_segment(
        sess_b.session_id, sess_b.numeric_segments, "987"
    )

    # Session A completes with "7702245"
    is_done_a, res_a, sess_a.numeric_segments = NumericTurnAccumulator.handle_segment(
        sess_a.session_id, sess_a.numeric_segments, "7702245"
    )

    # Session B completes with "6543210"
    is_done_b, res_b, sess_b.numeric_segments = NumericTurnAccumulator.handle_segment(
        sess_b.session_id, sess_b.numeric_segments, "6543210"
    )

    assert is_done_a and res_a == "7207702245"
    assert is_done_b and res_b == "9876543210"
    assert sess_a.numeric_segments == []
    assert sess_b.numeric_segments == []
