"""Unit tests verifying unique response generation and zero response reuse on follow-up user turns."""
import pytest
import asyncio
from app.session.state import SessionState, TurnStateEnum
from app.conversation.manager import ConversationManager
from app.conversation.router import FastQueryRouter, QueryComplexity
from app.rag.client import MockRAGProvider
from app.llm.mock import MockLLMProvider


@pytest.mark.asyncio
async def test_followup_turn_does_not_reuse_previous_response():
    """Verify Turn 2 follow-up ('I did not write GATE.') routes to LLM and does not repeat Turn 1 eligibility FAQ."""
    session = SessionState(session_id="test_sess_001", organization_id="org_apex_univ", agent_id="agent_admission")
    session.preferred_language = "en-IN"
    session.language_selection_complete = True
    rag = MockRAGProvider()
    mgr = ConversationManager(rag_provider=rag)

    # TURN 1: "What is the eligibility?"
    t1_text = "What is the eligibility?"
    c1, resp1 = await FastQueryRouter.route_and_resolve_fast_path(session, t1_text, rag)
    assert c1 == QueryComplexity.SIMPLE
    assert resp1 is not None
    assert "60%" in resp1
    session.append_message(role="user", content=t1_text)
    session.append_message(role="assistant", content=resp1)
    session.last_response_text = resp1

    # TURN 2: "I did not write GATE."
    turn2 = session.start_new_turn(reason="Turn 2 follow-up")
    assert turn2.turn_id != session.previous_turn_id
    assert turn2.generation_id != session.previous_generation_id

    t2_text = "I did not write GATE."
    c2, resp2 = await FastQueryRouter.route_and_resolve_fast_path(session, t2_text, rag)
    # Must NOT be resolved by Fast Router with the canned eligibility string
    assert c2 == QueryComplexity.COMPLEX
    assert resp2 is None

    # Verify LLM prompt assembly includes conversation history and new user query
    messages = await mgr.assemble_llm_messages(session, t2_text)
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user" and messages[1]["content"] == t1_text
    assert messages[2]["role"] == "assistant" and messages[2]["content"] == resp1
    assert messages[3]["role"] == "user" and messages[3]["content"] == t2_text


@pytest.mark.asyncio
async def test_telugu_followup_gate_query():
    """Verify Telugu follow-up ('Naaku GATE exam rayaledu.') routes to LLM for fresh contextual answer."""
    session = SessionState(session_id="test_sess_002", organization_id="org_apex_univ", agent_id="agent_admission")
    session.preferred_language = "te-IN"
    session.language = "te-IN"
    session.language_selection_complete = True
    rag = MockRAGProvider()

    # Turn 1: Eligibility
    t1_text = "Eligibility enti?"
    c1, resp1 = await FastQueryRouter.route_and_resolve_fast_path(session, t1_text, rag)
    assert c1 == QueryComplexity.SIMPLE
    assert "PCM" in resp1
    session.append_message(role="user", content=t1_text)
    session.append_message(role="assistant", content=resp1)

    # Turn 2: Follow-up on GATE
    t2_text = "Naaku GATE exam rayaledu."
    c2, resp2 = await FastQueryRouter.route_and_resolve_fast_path(session, t2_text, rag)
    assert c2 == QueryComplexity.COMPLEX
    assert resp2 is None


@pytest.mark.asyncio
async def test_anti_repetition_guard_in_fast_router():
    """Verify Fast Router will not repeat the same response twice in a row."""
    session = SessionState(session_id="test_sess_003", organization_id="org_apex_univ", agent_id="agent_admission")
    session.preferred_language = "en-IN"
    session.language_selection_complete = True
    rag = MockRAGProvider()

    t1_text = "What is the fee for BTech CSE?"
    c1, resp1 = await FastQueryRouter.route_and_resolve_fast_path(session, t1_text, rag)
    assert c1 == QueryComplexity.SIMPLE
    assert resp1 is not None
    session.append_message(role="user", content=t1_text)
    session.append_message(role="assistant", content=resp1)

    # User repeats the query or similar phrase
    t2_text = "What is the fee for BTech CSE?"
    c2, resp2 = await FastQueryRouter.route_and_resolve_fast_path(session, t2_text, rag)
    # Anti-repetition guard prevents repeating identical response back-to-back
    assert c2 == QueryComplexity.COMPLEX
    assert resp2 is None
