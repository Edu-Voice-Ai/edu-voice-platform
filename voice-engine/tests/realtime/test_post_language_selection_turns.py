"""Deterministic tests for Post-Language Selection Conversation Turns and Flow."""
import pytest
import asyncio
from app.conversation.manager import ConversationManager
from app.conversation.router import FastQueryRouter, QueryComplexity
from app.rag.client import MockRAGProvider
from app.session.state import SessionState, TurnStateEnum, ConversationFloor
from app.session.events import EventType


@pytest.mark.asyncio
async def test_case_1_to_4_telugu_selection_and_domain_questions():
    """Verify selecting Telugu followed by courses, fees, eligibility, hostel all return Telugu answers."""
    rag = MockRAGProvider()
    conv = ConversationManager(rag_provider=rag)
    session = SessionState(session_id="s_te_domain", organization_id="org_apex_univ", agent_id="agent_admission")

    # Turn 1: User selects Telugu
    ack = conv.handle_language_selection_or_switch(session, "Telugu")
    assert session.language_selection_complete is True
    assert session.preferred_language == "te-IN"
    assert session.conversation_state == "LISTENING"
    assert ack is not None
    assert "తెలుగు" in ack

    # Turn 2: Courses question
    q_course = "మీ కాలేజీలో ఏ కోర్సులు ఉన్నాయి?"
    ack2 = conv.handle_language_selection_or_switch(session, q_course)
    assert ack2 is None, "Domain question must NOT be intercepted as language acknowledgment"
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session, q_course, rag)
    assert comp == QueryComplexity.SIMPLE
    assert resp is not None
    assert "మా Apex University లో" in resp or "అందుబాటులో ఉన్నాయి" in resp
    assert "CSE" in resp

    # Turn 3: Fees question
    q_fee = "CSE fee ఎంత?"
    ack3 = conv.handle_language_selection_or_switch(session, q_fee)
    assert ack3 is None
    comp, resp_fee = await FastQueryRouter.route_and_resolve_fast_path(session, q_fee, rag)
    assert comp == QueryComplexity.SIMPLE
    assert "1,50,000" in resp_fee
    assert "Apex University" in resp_fee

    # Turn 4: Eligibility question
    q_elig = "Eligibility ఏంటి?"
    ack4 = conv.handle_language_selection_or_switch(session, q_elig)
    assert ack4 is None
    comp, resp_elig = await FastQueryRouter.route_and_resolve_fast_path(session, q_elig, rag)
    assert comp == QueryComplexity.SIMPLE
    assert "12th Standard PCM" in resp_elig or "మార్కులు" in resp_elig

    # Turn 5: Hostel question
    q_hostel = "Hostel ఉందా?"
    ack5 = conv.handle_language_selection_or_switch(session, q_hostel)
    assert ack5 is None
    comp, resp_hostel = await FastQueryRouter.route_and_resolve_fast_path(session, q_hostel, rag)
    assert comp == QueryComplexity.SIMPLE
    assert "అవునండి" in resp_hostel
    assert "80,000" in resp_hostel


@pytest.mark.asyncio
async def test_case_5_to_7_hindi_selection_and_domain_questions():
    """Verify selecting Hindi followed by courses, fees, eligibility all return Hindi answers."""
    rag = MockRAGProvider()
    conv = ConversationManager(rag_provider=rag)
    session = SessionState(session_id="s_hi_domain", organization_id="org_apex_univ", agent_id="agent_admission")

    # Turn 1: User selects Hindi
    ack = conv.handle_language_selection_or_switch(session, "Hindi")
    assert session.language_selection_complete is True
    assert session.preferred_language == "hi-IN"
    assert ack is not None
    assert "Hindi" in ack or "हिंदी" in ack

    # Turn 2: Courses question
    q_course = "आपके कॉलेज में कौन-कौन से कोर्स हैं?"
    assert conv.handle_language_selection_or_switch(session, q_course) is None
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session, q_course, rag)
    assert comp == QueryComplexity.SIMPLE
    assert "Apex University में BTech" in resp
    assert "उपलब्ध हैं" in resp

    # Turn 3: Fees question
    q_fee = "CSE की फीस कितनी है?"
    assert conv.handle_language_selection_or_switch(session, q_fee) is None
    comp, resp_fee = await FastQueryRouter.route_and_resolve_fast_path(session, q_fee, rag)
    assert comp == QueryComplexity.SIMPLE
    assert "1,50,000" in resp_fee
    assert "रुपये" in resp_fee

    # Turn 4: Eligibility question
    q_elig = "एलिजिबिलिटी क्या है?"
    assert conv.handle_language_selection_or_switch(session, q_elig) is None
    comp, resp_elig = await FastQueryRouter.route_and_resolve_fast_path(session, q_elig, rag)
    assert comp == QueryComplexity.SIMPLE
    assert "12वीं PCM" in resp_elig or "पात्रता" in resp_elig


@pytest.mark.asyncio
async def test_case_8_to_9_english_selection_and_domain_questions():
    """Verify selecting English followed by courses and fees all return English answers."""
    rag = MockRAGProvider()
    conv = ConversationManager(rag_provider=rag)
    session = SessionState(session_id="s_en_domain", organization_id="org_apex_univ", agent_id="agent_admission")

    # Turn 1: User selects English
    ack = conv.handle_language_selection_or_switch(session, "English")
    assert session.language_selection_complete is True
    assert session.preferred_language == "en-IN"
    assert "English" in ack

    # Turn 2: Courses question
    q_course = "What courses do you offer?"
    assert conv.handle_language_selection_or_switch(session, q_course) is None
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session, q_course, rag)
    assert comp == QueryComplexity.SIMPLE
    assert "Apex University currently offers BTech" in resp

    # Turn 3: Fees question
    q_fee = "What is the CSE fee?"
    assert conv.handle_language_selection_or_switch(session, q_fee) is None
    comp, resp_fee = await FastQueryRouter.route_and_resolve_fast_path(session, q_fee, rag)
    assert comp == QueryComplexity.SIMPLE
    assert "INR 1,50,000" in resp_fee or "1,50,000" in resp_fee


@pytest.mark.asyncio
async def test_case_13_14_15_combined_and_code_mixed_queries():
    """Verify combined language selection/switch + question in single turn."""
    rag = MockRAGProvider()
    conv = ConversationManager(rag_provider=rag)

    # 13. "Telugu, CSE fee ఎంత?"
    s1 = SessionState(session_id="s_comb_te", organization_id="org_apex_univ", agent_id="agent_admission")
    resp_ack1 = conv.handle_language_selection_or_switch(s1, "Telugu, CSE fee ఎంత?")
    assert resp_ack1 is None, "Combined selection + question must route directly to router/LLM"
    assert s1.preferred_language == "te-IN"
    comp1, resp1 = await FastQueryRouter.route_and_resolve_fast_path(s1, "CSE fee ఎంత?", rag)
    assert comp1 == QueryComplexity.SIMPLE
    assert "1,50,000" in resp1

    # 14. "Hindi mein boliye, CSE fee kya hai?"
    s2 = SessionState(session_id="s_comb_hi", organization_id="org_apex_univ", agent_id="agent_admission")
    s2.language_selection_complete = True
    s2.preferred_language = "te-IN"
    resp_ack2 = conv.handle_language_selection_or_switch(s2, "Hindi mein boliye, CSE fee kya hai?")
    assert resp_ack2 is None
    assert s2.preferred_language == "hi-IN"
    comp2, resp2 = await FastQueryRouter.route_and_resolve_fast_path(s2, "CSE fee kya hai?", rag)
    assert comp2 == QueryComplexity.SIMPLE
    assert "1,50,000" in resp2

    # 15. "Telugu lo CSE fee entha?"
    s3 = SessionState(session_id="s_comb_mix", organization_id="org_apex_univ", agent_id="agent_admission")
    s3.language_selection_complete = True
    s3.preferred_language = "en-IN"
    resp_ack3 = conv.handle_language_selection_or_switch(s3, "Telugu lo CSE fee entha?")
    assert resp_ack3 is None
    assert s3.preferred_language == "te-IN"
    comp3, resp3 = await FastQueryRouter.route_and_resolve_fast_path(s3, "CSE fee entha?", rag)
    assert comp3 == QueryComplexity.SIMPLE
    assert "1,50,000" in resp3


def test_no_two_minute_consent_and_single_acknowledgment():
    """Verify zero two-minute consent steps exist in session state or responses."""
    session = SessionState(session_id="s_consent_check", organization_id="org_apex_univ", agent_id="agent_admission")
    conv = ConversationManager()

    ack = conv.handle_language_selection_or_switch(session, "Telugu")
    assert "రెండు నిమిషాలు" not in ack
    assert "two minutes" not in ack.lower()
    assert "दो मिनट" not in ack

    assert session.waiting_for_consent is False
    assert session.consent_granted is True
    assert session.conversation_state == "LISTENING"
    assert session.language_selection_complete is True


@pytest.mark.asyncio
async def test_session_state_cleanup_after_playback():
    """Verify playback state is completely reset when TTS finishes so floor returns to IDLE."""
    import time
    session = SessionState(session_id="s_state_clean", organization_id="org1", agent_id="a1")
    session.active_playback_generation_id = "gen_123"
    session.active_playback_turn_id = "turn_123"
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = time.time() * 1000 + 10000.0

    # Before completion: floor is AI_SPEAKING
    assert session.floor == ConversationFloor.AI_SPEAKING

    # After completion (as performed in _tts_worker):
    session.current_turn.state = TurnStateEnum.IDLE
    session.is_bot_speaking = False
    session.active_playback_generation_id = None
    session.playback_estimated_end_time_ms = 0.0
    session.conversation_state = "LISTENING"
    session.user_has_floor = True

    # After completion: floor MUST be IDLE / ready for USER_SPEAKING
    assert session.floor == ConversationFloor.IDLE
    assert session.is_assistant_speaking is False
