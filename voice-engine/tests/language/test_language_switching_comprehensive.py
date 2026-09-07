"""Comprehensive test suite for language switching permutations, phrase robustness, and combined queries."""
import pytest
from app.conversation.language import LanguagePreferenceParser
from app.conversation.manager import ConversationManager
from app.session.state import SessionState


def test_all_six_language_switch_permutations():
    """Verify all 6 bidirectional language switch pairs."""
    # 1. Telugu -> Hindi
    assert LanguagePreferenceParser.detect_language_switch("Switch to Hindi") == "hi-IN"
    assert LanguagePreferenceParser.detect_language_switch("हिंदी में बोलिए") == "hi-IN"
    assert LanguagePreferenceParser.detect_language_switch("Hindi mein boliye") == "hi-IN"

    # 2. Hindi -> Telugu
    assert LanguagePreferenceParser.detect_language_switch("Switch to Telugu") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("తెలుగులో మాట్లాడండి") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("Telugu lo matladandi") == "te-IN"

    # 3. English -> Telugu
    assert LanguagePreferenceParser.detect_language_switch("Telugu please") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("speak in Telugu") == "te-IN"

    # 4. English -> Hindi
    assert LanguagePreferenceParser.detect_language_switch("Hindi please") == "hi-IN"
    assert LanguagePreferenceParser.detect_language_switch("speak in Hindi") == "hi-IN"

    # 5. Telugu -> English
    assert LanguagePreferenceParser.detect_language_switch("Switch to English") == "en-IN"
    assert LanguagePreferenceParser.detect_language_switch("English lo cheppandi") == "en-IN"
    assert LanguagePreferenceParser.detect_language_switch("English please") == "en-IN"

    # 6. Hindi -> English
    assert LanguagePreferenceParser.detect_language_switch("Speak English") == "en-IN"
    assert LanguagePreferenceParser.detect_language_switch("English me boliye") == "en-IN"
    assert LanguagePreferenceParser.detect_language_switch("English please") == "en-IN"


def test_specific_user_phrases():
    """Verify exact phrases requested by user."""
    # Telugu
    assert LanguagePreferenceParser.detect_language_switch("Telugu") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("తెలుగులో మాట్లాడండి") == "te-IN"
    assert LanguagePreferenceParser.detect_language_switch("Telugu lo matladandi") == "te-IN"

    # Hindi
    assert LanguagePreferenceParser.detect_language_switch("Hindi") == "hi-IN"
    assert LanguagePreferenceParser.detect_language_switch("हिंदी में बोलिए") == "hi-IN"
    assert LanguagePreferenceParser.detect_language_switch("Hindi mein boliye") == "hi-IN"
    assert LanguagePreferenceParser.detect_language_switch("Hindi me baat kijiye") == "hi-IN"

    # English
    assert LanguagePreferenceParser.detect_language_switch("English") == "en-IN"
    assert LanguagePreferenceParser.detect_language_switch("Speak English") == "en-IN"
    assert LanguagePreferenceParser.detect_language_switch("English please") == "en-IN"


def test_engineering_does_not_trigger_english_switch():
    """Negative test: 'engineering courses' must NOT trigger English switch."""
    assert LanguagePreferenceParser.detect_language_switch("What are the engineering courses?") is None
    assert LanguagePreferenceParser.detect_language_switch("engineering fee entha?") is None
    assert LanguagePreferenceParser.detect_language_switch("engineering admissions kab start honge?") is None


def test_combined_language_switch_and_question():
    """Verify combined language switch + domain question preserves both."""
    conv = ConversationManager()

    # Case 1: "Switch to Hindi, what is the CSE fee?"
    s1 = SessionState(session_id="s_comb_1", organization_id="o1", agent_id="a1")
    s1.language_selection_complete = True
    s1.preferred_language = "te-IN"
    s1.language = "te-IN"

    resp1 = conv.handle_language_selection_or_switch(s1, "Switch to Hindi, what is the CSE fee?")
    # Because there is a specific question, handle_language_selection_or_switch returns None
    # allowing FastQueryRouter / LLM to answer the question directly!
    assert resp1 is None
    # But language was updated atomically!
    assert s1.preferred_language == "hi-IN"
    assert s1.language == "hi-IN"

    # Case 2: "తెలుగులో మాట్లాడండి, CSE fee ఎంత?"
    s2 = SessionState(session_id="s_comb_2", organization_id="o1", agent_id="a1")
    s2.language_selection_complete = True
    s2.preferred_language = "en-IN"
    s2.language = "en-IN"

    resp2 = conv.handle_language_selection_or_switch(s2, "తెలుగులో మాట్లాడండి, CSE fee ఎంత?")
    assert resp2 is None
    assert s2.preferred_language == "te-IN"
    assert s2.language == "te-IN"

    # Case 3: "English please, what courses do you offer?"
    s3 = SessionState(session_id="s_comb_3", organization_id="o1", agent_id="a1")
    s3.language_selection_complete = True
    s3.preferred_language = "hi-IN"
    s3.language = "hi-IN"

    resp3 = conv.handle_language_selection_or_switch(s3, "English please, what courses do you offer?")
    assert resp3 is None
    assert s3.preferred_language == "en-IN"
    assert s3.language == "en-IN"
