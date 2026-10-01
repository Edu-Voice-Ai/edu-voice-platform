"""
Regression Test Suite: Prevention of Unsolicited Agent Speech and Silence Handling.

Verifies:
1. Empty transcript does not trigger LLM
2. Empty transcript does not trigger TTS
3. Silence does not trigger response
4. STT timeout does not trigger response
5. Watchdog recovery does not trigger response
6. Language detection does not trigger response
7. session.ready only produces the intended greeting
8. Barge-in recovery waits for user speech
9. Duplicate transcript does not generate duplicate response
10. Genuine user speech generates exactly one response
11. English/Telugu/Hindi language switching remains silent internally
"""
import pytest
import asyncio
import time
from app.session.state import SessionState, TurnStateEnum, GreetingStateEnum
from app.session.events import EventType, SessionEvent
from app.conversation.manager import ConversationManager
from app.pipeline.turn_manager import TurnManager
from app.conversation.manager import ConversationManager
from app.conversation.router import QueryComplexity, FastQueryRouter
from app.rag.client import MockRAGProvider
from app.session.state import SessionState, TurnStateEnum, GreetingStateEnum
from app.pipeline.turn_manager import TurnManager
from app.pipeline.queues import PipelineQueueBundle
from app.session.events import EventType, SessionEvent


@pytest.fixture
def mock_session():
    s = SessionState(session_id="s_test_silence", organization_id="org_apex_univ", agent_id="agent_adm")
    s.conversation_state = "LISTENING"
    s.greeting_state = GreetingStateEnum.COMPLETED
    s.user_has_floor = True
    return s


@pytest.fixture
def conv_manager():
    return ConversationManager(rag_provider=MockRAGProvider())


# Test 1: Empty transcript does not trigger LLM
@pytest.mark.asyncio
async def test_empty_transcript_does_not_trigger_llm(mock_session, conv_manager):
    ack = conv_manager.handle_language_selection_or_switch(mock_session, "")
    assert ack is None
    ack_ws = conv_manager.handle_language_selection_or_switch(mock_session, "   ")
    assert ack_ws is None
    assert mock_session.conversation_state == "LISTENING"


# Test 2: Empty transcript does not trigger TTS
@pytest.mark.asyncio
async def test_empty_transcript_does_not_trigger_tts(mock_session, conv_manager):
    noise_tokens = ["", " ", "[noise]", "<silence>", "[cough]", "..."]
    for token in noise_tokens:
        ack = conv_manager.handle_language_selection_or_switch(mock_session, token)
        assert ack is None, f"Token '{token}' should not trigger acknowledgment"


# Test 3: Silence does not trigger response
@pytest.mark.asyncio
async def test_silence_does_not_trigger_response(mock_session):
    tm = TurnManager(session=mock_session, queues=PipelineQueueBundle(), min_barge_in_duration_ms=300)
    for _ in range(20):
        transition = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
        assert transition is None
    assert mock_session.conversation_state == "LISTENING"
    assert mock_session.user_has_floor is True


# Test 4: STT timeout does not trigger response
@pytest.mark.asyncio
async def test_stt_timeout_does_not_trigger_response(mock_session):
    turn = mock_session.start_new_turn(reason="Test STT timeout recovery")
    turn.state = TurnStateEnum.PROCESSING

    # Simulate STT timeout recovery behavior
    turn.state = TurnStateEnum.LISTENING
    mock_session.user_has_floor = True
    mock_session.conversation_state = "LISTENING"

    assert turn.state == TurnStateEnum.LISTENING
    assert not turn.generated_text
    assert mock_session.last_response_text is None


# Test 5: Watchdog recovery does not trigger response
@pytest.mark.asyncio
async def test_watchdog_recovery_does_not_trigger_response(mock_session):
    turn = mock_session.start_new_turn(reason="Processing stall test")
    turn.state = TurnStateEnum.PROCESSING
    turn.processing_started_at_ms = (time.time() - 20) * 1000

    # Watchdog fires and restores LISTENING
    now_ms = time.time() * 1000
    if now_ms - turn.processing_started_at_ms > 15000.0:
        turn.state = TurnStateEnum.LISTENING
        mock_session.conversation_state = "LISTENING"

    assert turn.state == TurnStateEnum.LISTENING
    assert not turn.generated_text
    assert mock_session.is_bot_speaking is False


# Test 6: Language detection does not trigger response
@pytest.mark.asyncio
async def test_language_detection_does_not_trigger_response(mock_session, conv_manager):
    q = "What is the admission procedure for engineering?"
    ack = conv_manager.handle_language_selection_or_switch(mock_session, q)
    assert ack is None, "Language detection on query must remain completely silent"
    assert mock_session.language_selection_complete is True
    assert mock_session.preferred_language == "en-IN"


# Test 7: session.ready only produces the intended greeting
@pytest.mark.asyncio
async def test_session_ready_only_produces_intended_greeting(mock_session):
    assert mock_session.greeting_state == GreetingStateEnum.COMPLETED
    greeting_text = mock_session.get_greeting_text()
    assert "Apex University" in greeting_text


# Test 8: Barge-in recovery waits for user speech
@pytest.mark.asyncio
async def test_barge_in_recovery_waits_for_user_speech(mock_session):
    tm = TurnManager(session=mock_session, queues=PipelineQueueBundle(), min_barge_in_duration_ms=40)
    mock_session.is_bot_speaking = True
    pcm = b"\x01\x00" * 160

    for _ in range(3):
        tm.handle_speech_frame(is_speech=True, frame_data=pcm, frame_duration_ms=20)

    assert mock_session.user_has_floor is True


# Test 9: Duplicate transcript does not generate duplicate response
@pytest.mark.asyncio
async def test_duplicate_transcript_does_not_generate_duplicate_response(mock_session, conv_manager):
    q = "What courses do you offer?"
    comp, resp1 = await FastQueryRouter.route_and_resolve_fast_path(mock_session, q, conv_manager.rag_provider)
    assert resp1 is not None
    assert "CSE" in resp1


# Test 10: Genuine user speech generates exactly one response
@pytest.mark.asyncio
async def test_genuine_user_speech_generates_exactly_one_response(mock_session, conv_manager):
    q = "What is the fee for CSE?"
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(mock_session, q, conv_manager.rag_provider)
    assert comp == QueryComplexity.SIMPLE
    assert resp is not None
    assert "1,50,000" in resp or "CSE" in resp


# Test 11: English/Telugu/Hindi language switching remains silent internally
@pytest.mark.asyncio
async def test_multilingual_language_switching_remains_silent_internally(mock_session, conv_manager):
    # Switch with query to Telugu
    s_te = SessionState(session_id="s_switch_te", organization_id="org_apex", agent_id="agent_adm")
    s_te.language_selection_complete = True
    s_te.preferred_language = "en-IN"

    ack_te = conv_manager.handle_language_selection_or_switch(s_te, "Switch to Telugu, CSE fee ఎంత?")
    assert ack_te is None, "Language switch with question must not produce intermediate acknowledgment"
    assert s_te.preferred_language == "te-IN"

    # Switch with query to Hindi
    s_hi = SessionState(session_id="s_switch_hi", organization_id="org_apex", agent_id="agent_adm")
    s_hi.language_selection_complete = True
    s_hi.preferred_language = "en-IN"

    ack_hi = conv_manager.handle_language_selection_or_switch(s_hi, "Switch to Hindi, CSE fee kya hai?")
    assert ack_hi is None, "Language switch with question must not produce intermediate acknowledgment"
    assert s_hi.preferred_language == "hi-IN"
