"""Automated regression tests verifying Telugu support, selection, and language switching."""
import pytest
from app.session.state import SessionState
from app.conversation.manager import ConversationManager
from app.conversation.language import LanguagePreferenceParser
from app.conversation.prompts import build_admission_system_prompt
from app.rag.mock import MockRAGProvider


def test_telugu_parser_variations():
    """Verify parser returns te-IN for all user utterances requesting Telugu."""
    # Test 1
    assert LanguagePreferenceParser.parse_language_preference("Telugu") == "te-IN"
    # Test 2
    assert LanguagePreferenceParser.parse_language_preference("తెలుగు") == "te-IN"
    # Test 3
    assert LanguagePreferenceParser.parse_language_preference("I want Telugu") == "te-IN"
    # Test 4
    assert LanguagePreferenceParser.parse_language_preference("I want to talk in Telugu") == "te-IN"
    # Test 5
    assert LanguagePreferenceParser.parse_language_preference("నాకు తెలుగులో మాట్లాడాలి") == "te-IN"
    assert LanguagePreferenceParser.parse_language_preference("Telugu lo maatladandi") == "te-IN"
    assert LanguagePreferenceParser.parse_language_preference("Telugu lo cheppandi") == "te-IN"
    assert LanguagePreferenceParser.parse_language_preference("తెలుగులో మాట్లాడండి") == "te-IN"


def test_telugu_switch_detector_variations():
    """Verify switch detector returns te-IN for mid-call switch requests."""
    assert LanguagePreferenceParser.detect_language_switch("I want Telugu") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("Telugu") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("తెలుగు") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("Telugu please") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("Switch to Telugu") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("I want to talk in Telugu") == "te-IN"


@pytest.mark.asyncio
async def test_telugu_selection_state_and_persistence():
    """Verify session state updates properly upon selecting Telugu and persists across turns."""
    rag = MockRAGProvider()
    conv = ConversationManager(rag_provider=rag)
    session = SessionState(session_id="sess_te_test", organization_id="org1", agent_id="a1")

    # Turn 1: Initial selection
    ack = conv.handle_language_selection_or_switch(session, "I want Telugu")
    assert session.preferred_language == "te-IN"
    assert session.language_selection_complete is True
    assert session.conversation_style == "telugish"
    assert ack is not None
    assert "Telugu" in ack or "తెలుగు" in ack

    # Turn 2: Subsequent admission turn remains in Telugu
    msgs = await conv.assemble_llm_messages(session, "CSE admission details cheppandi")
    assert session.preferred_language == "te-IN"
    assert session.conversation_style == "telugish"
    sys_prompt = msgs[0]["content"]
    assert "TELUGISH" in sys_prompt.upper()
    assert "Never tell the caller that Telugu is unsupported" in sys_prompt


@pytest.mark.asyncio
async def test_full_language_switching_cycle():
    """Verify explicit switching cycle: Telugu -> English -> Telugu."""
    conv = ConversationManager()
    session = SessionState(session_id="sess_cycle_test", organization_id="org1", agent_id="a1")

    # 1. Start in Telugu
    conv.handle_language_selection_or_switch(session, "Telugu")
    assert session.preferred_language == "te-IN"

    # 2. Switch to English
    ack_en = conv.handle_language_selection_or_switch(session, "English please")
    assert session.preferred_language == "en-IN"
    assert "English" in ack_en

    # 3. Switch back to Telugu
    ack_te = conv.handle_language_selection_or_switch(session, "I want Telugu")
    assert session.preferred_language == "te-IN"
    assert "Telugu" in ack_te or "తెలుగు" in ack_te
