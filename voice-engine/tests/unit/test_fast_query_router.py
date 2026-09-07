import pytest
import pytest_asyncio
from app.conversation.router import FastQueryRouter, QueryComplexity
from app.rag.client import MockRAGProvider
from app.session.state import SessionState


@pytest.mark.asyncio
async def test_fast_query_router_courses_and_fees():
    rag = MockRAGProvider()
    session = SessionState(session_id="s_test", organization_id="org_apex_univ", agent_id="agent_admission")
    session.preferred_language = "te-IN"

    # 1. Course inquiry in Telugu -> Telugu response
    complexity, resp = await FastQueryRouter.route_and_resolve_fast_path(session, "మీ దగ్గర ఏమేమి courses ఉన్నాయి?", rag)
    assert complexity == QueryComplexity.SIMPLE
    assert resp is not None
    assert "మా Apex University లో" in resp or "అందుబాటులో ఉన్నాయి" in resp
    assert "CSE" in resp

    # 2. CSE Fee inquiry in Telugu -> Telugu response
    complexity, resp_fee = await FastQueryRouter.route_and_resolve_fast_path(session, "CSE fee ఎంత?", rag)
    assert complexity == QueryComplexity.SIMPLE
    assert resp_fee is not None
    assert "1,50,000" in resp_fee
    assert "ఉంటుంది" in resp_fee or "రూపాయలు" in resp_fee or "rupees" in resp_fee

    # 3. Hostel inquiry in Telugu -> Telugu response
    complexity, resp_hostel = await FastQueryRouter.route_and_resolve_fast_path(session, "హాస్టల్ ఫెసిలిటీ ఉందా?", rag)
    assert complexity == QueryComplexity.SIMPLE
    assert resp_hostel is not None
    assert "అవునండి" in resp_hostel or "ఉన్నాయి" in resp_hostel

    # 4. Hindi Language support
    session.preferred_language = "hi-IN"
    complexity, resp_hi = await FastQueryRouter.route_and_resolve_fast_path(session, "BTech फीस कितनी है?", rag)
    assert complexity == QueryComplexity.SIMPLE
    assert resp_hi is not None
    assert "1,50,000" in resp_hi
    assert "रुपये" in resp_hi or "फीस" in resp_hi

    # 5. English Language support
    session.preferred_language = "en-IN"
    complexity, resp_en = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the BTech CSE fee?", rag)
    assert complexity == QueryComplexity.SIMPLE
    assert resp_en is not None
    assert "INR 1,50,000" in resp_en or "1,50,000" in resp_en
    assert "Apex University" in resp_en


@pytest.mark.asyncio
async def test_fast_query_router_complex_and_goodbye():
    rag = MockRAGProvider()
    session = SessionState(session_id="s_test2", organization_id="org_apex_univ", agent_id="agent_admission")
    session.preferred_language = "en-IN"

    # 1. Complex comparative query falls back to LLM (returns None)
    complexity, resp = await FastQueryRouter.route_and_resolve_fast_path(session, "Can you compare CSE vs ECE placements and give me suggestions?", rag)
    assert complexity == QueryComplexity.COMPLEX
    assert resp is None

    # 2. Goodbye detection
    complexity, bye_resp = await FastQueryRouter.route_and_resolve_fast_path(session, "Thank you, bye!", rag)
    assert complexity == QueryComplexity.GOODBYE
    assert bye_resp is not None
    assert session.conversation_state == "COMPLETED"

    # 3. Normal question is NEVER goodbye
    assert FastQueryRouter.is_explicit_goodbye("What is the hostel fee?") is False
    assert FastQueryRouter.is_explicit_goodbye("BTech eligibility details please") is False
