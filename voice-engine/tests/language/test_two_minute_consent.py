"""Unit tests verifying direct language selection and continuous conversation with ZERO two-minute consent."""
import pytest
from app.session.state import SessionState
from app.conversation.manager import ConversationManager
from app.conversation.language import (
    LANGUAGE_SELECTION_ACKNOWLEDGMENT,
    SWITCH_ACKNOWLEDGMENT
)


def test_english_language_selection_direct_flow():
    """Verify English language selection directly transitions to LISTENING without asking two-minute consent."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_en_direct", organization_id="org_test", agent_id="agent_1")

    # Turn 1: User selects English
    ack_1 = manager.handle_language_selection_or_switch(session, "English")
    assert ack_1 == LANGUAGE_SELECTION_ACKNOWLEDGMENT["en-IN"]
    assert "two minutes" not in ack_1.lower()
    assert "may i speak with you" not in ack_1.lower()
    assert session.preferred_language == "en-IN"
    assert session.language_selection_complete is True
    assert session.waiting_for_consent is False
    assert session.consent_granted is True
    assert session.conversation_state == "LISTENING"

    # Turn 2: User asks a domain question immediately
    ack_2 = manager.handle_language_selection_or_switch(session, "What courses do you offer?")
    assert ack_2 is None  # Directly passes to FastQueryRouter / LLM
    assert session.conversation_state == "LISTENING"


def test_telugu_language_selection_direct_flow():
    """Verify Telugu language selection directly transitions to LISTENING without asking two-minute consent."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_te_direct", organization_id="org_test", agent_id="agent_1")

    # Turn 1: User selects Telugu
    ack_1 = manager.handle_language_selection_or_switch(session, "Telugu")
    assert ack_1 == LANGUAGE_SELECTION_ACKNOWLEDGMENT["te-IN"]
    assert "రెండు నిమిషాలు" not in ack_1
    assert session.preferred_language == "te-IN"
    assert session.language_selection_complete is True
    assert session.waiting_for_consent is False
    assert session.consent_granted is True
    assert session.conversation_state == "LISTENING"

    # Turn 2: User asks a domain question in Telugu
    ack_2 = manager.handle_language_selection_or_switch(session, "మీ దగ్గర ఏమేమి కోర్సులు ఉన్నాయి?")
    assert ack_2 is None  # Directly passes to FastQueryRouter / LLM
    assert session.conversation_state == "LISTENING"


def test_hindi_language_selection_direct_flow():
    """Verify Hindi language selection directly transitions to LISTENING without asking two-minute consent."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_hi_direct", organization_id="org_test", agent_id="agent_1")

    # Turn 1: User selects Hindi
    ack_1 = manager.handle_language_selection_or_switch(session, "Hindi")
    assert ack_1 == LANGUAGE_SELECTION_ACKNOWLEDGMENT["hi-IN"]
    assert "दो मिनट" not in ack_1
    assert session.preferred_language == "hi-IN"
    assert session.language_selection_complete is True
    assert session.waiting_for_consent is False
    assert session.consent_granted is True
    assert session.conversation_state == "LISTENING"

    # Turn 2: User asks a domain question in Hindi
    ack_2 = manager.handle_language_selection_or_switch(session, "BTech CSE की फीस कितनी है?")
    assert ack_2 is None  # Directly passes to FastQueryRouter / LLM
    assert session.conversation_state == "LISTENING"


def test_direct_domain_question_on_turn_one():
    """Verify user asking a domain question directly on Turn 1 sets language and passes through to Router/LLM immediately."""
    manager = ConversationManager()

    # Case A: English question directly on Turn 1
    session_en = SessionState(session_id="sess_t1_en", organization_id="org1", agent_id="agent1")
    ack_en = manager.handle_language_selection_or_switch(session_en, "What is the fee for BTech?")
    assert ack_en is None  # Answered directly by FastQuery/LLM
    assert session_en.preferred_language == "en-IN"
    assert session_en.language_selection_complete is True
    assert session_en.waiting_for_consent is False

    # Case B: Telugu question directly on Turn 1
    session_te = SessionState(session_id="sess_t1_te", organization_id="org1", agent_id="agent1")
    ack_te = manager.handle_language_selection_or_switch(session_te, "మీ దగ్గర ఏమేమి కోర్సులు ఉన్నాయి?")
    assert ack_te is None  # Answered directly by FastQuery/LLM
    assert session_te.preferred_language == "te-IN"
    assert session_te.language_selection_complete is True
    assert session_te.waiting_for_consent is False

    # Case C: Hindi question directly on Turn 1
    session_hi = SessionState(session_id="sess_t1_hi", organization_id="org1", agent_id="agent1")
    ack_hi = manager.handle_language_selection_or_switch(session_hi, "आपके पास कौन-कौन से कोर्स हैं?")
    assert ack_hi is None  # Answered directly by FastQuery/LLM
    assert session_hi.preferred_language == "hi-IN"
    assert session_hi.language_selection_complete is True
    assert session_hi.waiting_for_consent is False


def test_code_mixed_language_selection_and_switch():
    """Verify code-mixed language preference and mid-call language switching."""
    manager = ConversationManager()
    session = SessionState(session_id="sess_switch", organization_id="org1", agent_id="agent1")

    # Turn 1: Select Telugu in romanized/code-mixed script
    manager.handle_language_selection_or_switch(session, "Telugu lo matladandi")
    assert session.preferred_language == "te-IN"
    assert session.language_selection_complete is True

    # Turn 2: User explicitly asks to switch to English mid-call
    switch_ack = manager.handle_language_selection_or_switch(session, "Please switch to English")
    assert switch_ack == SWITCH_ACKNOWLEDGMENT["en-IN"]
    assert session.preferred_language == "en-IN"
    assert session.language == "en-IN"
    assert session.waiting_for_consent is False


def test_no_two_minute_phrasing_in_acknowledgments():
    """Verify that all language selection acknowledgments contain zero two-minute consent text."""
    for lang, ack in LANGUAGE_SELECTION_ACKNOWLEDGMENT.items():
        assert "two minutes" not in ack.lower()
        assert "may i speak" not in ack.lower()
        assert "రెండు నిమిషాలు" not in ack
        assert "दो मिनट" not in ack
