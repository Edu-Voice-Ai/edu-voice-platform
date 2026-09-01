"""Unit and style verification tests for Modern Telugish, Hinglish, and Indian English."""
import pytest
from app.session.state import SessionState
from app.conversation.prompts import build_admission_system_prompt, LANGUAGE_STYLE_MAPPING
from app.conversation.language import INITIAL_ACKNOWLEDGMENT, SWITCH_ACKNOWLEDGMENT


def test_conversation_style_mapping():
    """Verify standard ISO codes map to appropriate conversational styles."""
    session = SessionState(session_id="s1", organization_id="org1", agent_id="a1")
    
    session.preferred_language = "te-IN"
    assert session.conversation_style == "telugish"

    session.preferred_language = "hi-IN"
    assert session.conversation_style == "hinglish"

    session.preferred_language = "en-IN"
    assert session.conversation_style == "indian_english"


def test_telugish_prompt_guidelines():
    """Verify Telugish system prompt enforces modern conversational style with natural English words."""
    prompt = build_admission_system_prompt(preferred_language="te-IN")
    
    assert "ACTIVE SPEECH STYLE: TELUGISH" in prompt
    assert "MODERN CONVERSATIONAL TELUGISH" in prompt
    assert "AVOID overly formal, literary, or Sanskritized Telugu" in prompt
    assert "Telugu script" in prompt


def test_hinglish_prompt_guidelines():
    """Verify Hinglish system prompt enforces modern conversational style."""
    prompt = build_admission_system_prompt(preferred_language="hi-IN")
    
    assert "ACTIVE SPEECH STYLE: HINGLISH" in prompt
    assert "MODERN CONVERSATIONAL HINGLISH" in prompt
    assert "AVOID overly formal or pure literary Sanskritized Hindi" in prompt
    assert "Devanagari script" in prompt


def test_telugish_and_hinglish_acknowledgments():
    """Verify acknowledgment strings use natural Telugish and Hinglish phrasing."""
    assert "తెలుగు" in INITIAL_ACKNOWLEDGMENT["te-IN"] or "Telugu" in INITIAL_ACKNOWLEDGMENT["te-IN"] or "course" in INITIAL_ACKNOWLEDGMENT["te-IN"]
    assert "हिंदी" in INITIAL_ACKNOWLEDGMENT["hi-IN"] or "Hindi" in INITIAL_ACKNOWLEDGMENT["hi-IN"] or "details" in INITIAL_ACKNOWLEDGMENT["hi-IN"]
    assert "English" in INITIAL_ACKNOWLEDGMENT["en-IN"]
