"""Multilingual and Language Selection test suite for English, Hindi, Telugu, Code-mix, and Switching."""
import pytest
from app.conversation.language import (
    LanguageDetector,
    LanguagePreferenceParser,
    normalize_multilingual_text,
    INITIAL_ACKNOWLEDGMENT,
    SWITCH_ACKNOWLEDGMENT,
    LANGUAGE_CLARIFICATION_PROMPT
)
from app.session.state import SessionState
from app.conversation.manager import ConversationManager
from app.rag.mock import MockRAGProvider


def test_language_detector():
    # 1. English
    assert LanguageDetector.detect_language("When does CSE admission start?") == "en-IN"

    # 2. Hindi (Devanagari)
    assert LanguageDetector.detect_language("CSE का एडमिशन कब शुरू होगा?") == "hi-IN"

    # 3. Hindi (Roman code-mix)
    assert LanguageDetector.detect_language("CSE ka admission kab start hoga?") == "hi-IN"

    # 4. Telugu (Telugu Script)
    assert LanguageDetector.detect_language("సార్ CSE అడ్మిషన్ ఎప్పుడు స్టార్ట్ అవుతుంది?") == "te-IN"

    # 5. Telugu (Roman script / Code-mix)
    assert LanguageDetector.detect_language("Sir CSE admission eppudu start裂avutundi?") == "te-IN"
    assert LanguageDetector.detect_language("Sir CSE fee entha cheppandi?") == "te-IN"


def test_language_preference_parser():
    # English selections
    assert LanguagePreferenceParser.parse_language_preference("English") == "en-IN"
    assert LanguagePreferenceParser.parse_language_preference("I prefer English") == "en-IN"
    assert LanguagePreferenceParser.parse_language_preference("English please") == "en-IN"
    assert LanguagePreferenceParser.parse_language_preference("speak in english") == "en-IN"
    assert LanguagePreferenceParser.parse_language_preference("I want to talk in English") == "en-IN"

    # Hindi selections
    assert LanguagePreferenceParser.parse_language_preference("Hindi") == "hi-IN"
    assert LanguagePreferenceParser.parse_language_preference("हिंदी") == "hi-IN"
    assert LanguagePreferenceParser.parse_language_preference("Hindi mein baat kijiye") == "hi-IN"
    assert LanguagePreferenceParser.parse_language_preference("hindi please") == "hi-IN"
    assert LanguagePreferenceParser.parse_language_preference("I want to talk in Hindi") == "hi-IN"

    # Telugu selections
    assert LanguagePreferenceParser.parse_language_preference("Telugu") == "te-IN"
    assert LanguagePreferenceParser.parse_language_preference("తెలుగు") == "te-IN"
    assert LanguagePreferenceParser.parse_language_preference("Telugu lo maatladandi") == "te-IN"
    assert LanguagePreferenceParser.parse_language_preference("Telugu lo cheppandi") == "te-IN"
    assert LanguagePreferenceParser.parse_language_preference("తెలుగులో మాట్లాడండి") == "te-IN"
    assert LanguagePreferenceParser.parse_language_preference("I want to talk in Telugu") == "te-IN"
    assert LanguagePreferenceParser.parse_language_preference("నాకు తెలుగులో మాట్లాడాలి") == "te-IN"

    # Ambiguous greetings without language preference
    assert LanguagePreferenceParser.parse_language_preference("Hello") is None
    assert LanguagePreferenceParser.parse_language_preference("హలో") is None
    assert LanguagePreferenceParser.parse_language_preference("नमस्ते") is None
    assert LanguagePreferenceParser.parse_language_preference("Hi") is None


def test_ambiguous_greeting_clarification():
    conv = ConversationManager()
    session = SessionState(session_id="s_amb", organization_id="org1", agent_id="a1")
    
    # User says "Hello" on turn 1 -> seamlessly continues in English
    resp = conv.handle_language_selection_or_switch(session, "Hello")
    assert session.language_selection_complete is True
    assert session.preferred_language == "en-IN"
    assert "English" in resp

    # Next user switches to "Telugu"
    resp2 = conv.handle_language_selection_or_switch(session, "Telugu lo matladandi")
    assert session.preferred_language == "te-IN"
    assert "Telugu" in resp2 or "తెలుగు" in resp2


def test_language_switch_detector():
    # Switch to English
    assert LanguagePreferenceParser.detect_language_switch("Switch to English") == "en-IN"
    assert LanguagePreferenceParser.detect_language_switch("English lo cheppandi") == "en-IN"
    assert LanguagePreferenceParser.detect_language_switch("Please speak in English") == "en-IN"

    # Switch to Hindi
    assert LanguagePreferenceParser.detect_language_switch("Switch to Hindi") == "hi-IN"
    assert LanguagePreferenceParser.detect_language_switch("अब हिंदी में बोलिए") == "hi-IN"
    assert LanguagePreferenceParser.detect_language_switch("Hindi mein baat kijiye") == "hi-IN"

    # Switch to Telugu
    assert LanguagePreferenceParser.detect_language_switch("Switch to Telugu") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("తెలుగులో మాట్లాడండి") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("Telugu lo matladandi") == "te-IN"

    # Non-switch query
    assert LanguagePreferenceParser.detect_language_switch("What is the CSE fee?") is None


def test_multilingual_text_normalization():
    raw_te = "  సార్    CSE   fee   entha?  \n "
    normalized = normalize_multilingual_text(raw_te)
    assert normalized == "సార్ CSE fee entha?"


@pytest.mark.asyncio
async def test_initial_language_selection_and_persistence():
    rag = MockRAGProvider()
    conv = ConversationManager(rag_provider=rag)

    # Session starts unselected
    session = SessionState(session_id="sess_lang_test", organization_id="org_apex_univ", agent_id="agent_1")
    assert session.preferred_language is None
    assert session.language_selection_complete is False

    # Turn 1: User says "Telugu"
    ack_1 = conv.handle_language_selection_or_switch(session, "Telugu")
    assert session.preferred_language == "te-IN"
    assert session.language_selection_complete is True
    assert "Telugu" in ack_1 or "తెలుగు" in ack_1

    # Turn 2: User asks admission question in Telugu / Code-mix
    msgs_turn2 = await conv.assemble_llm_messages(session, "What is CSE fee?")
    assert session.preferred_language == "te-IN"
    assert session.language_selection_complete is True
    # Verify prompt instructs Telugu
    system_msg = msgs_turn2[0]["content"]
    assert "TE-IN" in system_msg.upper() or "TELUGU" in system_msg.upper()


@pytest.mark.asyncio
async def test_explicit_language_switching():
    conv = ConversationManager()
    session = SessionState(session_id="sess_switch_test", organization_id="org_apex_univ", agent_id="agent_1")

    # Initial selection: English
    conv.handle_language_selection_or_switch(session, "English")
    assert session.preferred_language == "en-IN"

    # Turn 2: User requests mid-call switch to Hindi
    ack = conv.handle_language_selection_or_switch(session, "Hindi mein baat kijiye")
    assert session.preferred_language == "hi-IN"
    assert "Hindi" in ack or "हिंदी" in ack

    # Turn 3: User requests mid-call switch to Telugu
    ack_te = conv.handle_language_selection_or_switch(session, "తెలుగులో మాట్లాడండి")
    assert session.preferred_language == "te-IN"
    assert "Telugu" in ack_te or "తెలుగు" in ack_te


@pytest.mark.asyncio
async def test_session_language_isolation():
    """Verify 2 concurrent sessions maintain independent preferred languages."""
    conv = ConversationManager()
    session_1 = SessionState(session_id="sess_1", organization_id="org_apex_univ", agent_id="agent_1")
    session_2 = SessionState(session_id="sess_2", organization_id="org_apex_univ", agent_id="agent_1")

    conv.handle_language_selection_or_switch(session_1, "Telugu")
    conv.handle_language_selection_or_switch(session_2, "Hindi")

    assert session_1.preferred_language == "te-IN"
    assert session_2.preferred_language == "hi-IN"


def test_barge_in_acknowledgment_mapping():
    """Verify deterministic language-specific acknowledgments for barge-in."""
    from app.conversation.language import BARGE_IN_ACKNOWLEDGMENT
    assert BARGE_IN_ACKNOWLEDGMENT["te-IN"] == "అవును, చెప్పండి."
    assert BARGE_IN_ACKNOWLEDGMENT["hi-IN"] == "हाँ, बोलिए."
    assert BARGE_IN_ACKNOWLEDGMENT["en-IN"] == "Yes, go ahead."
