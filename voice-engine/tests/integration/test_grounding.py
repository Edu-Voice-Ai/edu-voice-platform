"""Level 2 Grounding & Anti-Hallucination tests: Rejection of unverified facts."""
import pytest
from app.session.state import SessionState
from app.rag.mock import MockRAGProvider
from app.rag.base import RetrievalQuery
from app.llm.mock import MockLLMProvider
from app.conversation.manager import ConversationManager


@pytest.mark.asyncio
async def test_rag_tenant_filtering_isolation():
    rag = MockRAGProvider()
    
    # Query for Apex University
    q_apex = RetrievalQuery(organization_id="org_apex_univ", agent_id="agent_1", query_text="BTech CSE fee")
    res_apex = await rag.retrieve(q_apex)
    assert res_apex.has_verified_info is True
    assert any("1,50,000" in item.content for item in res_apex.items)

    # Query for Zenith College (different tenant)
    q_zenith = RetrievalQuery(organization_id="org_zenith_college", agent_id="agent_1", query_text="BTech CSE fee")
    res_zenith = await rag.retrieve(q_zenith)
    # Zenith does not offer BTech CSE, must not return Apex Univ data!
    assert not any("Apex" in item.content for item in res_zenith.items)


@pytest.mark.asyncio
async def test_anti_hallucination_refusal_on_missing_facts():
    """Test that when a fact is unverified (e.g. 2027 scholarship), LLM refuses to invent."""
    llm = MockLLMProvider()
    rag = MockRAGProvider()
    conv = ConversationManager(rag_provider=rag)
    
    session = SessionState(session_id="s1", organization_id="org_apex_univ", agent_id="agent_1")
    messages = await conv.assemble_llm_messages(session, "What is the 2027 scholarship amount?")
    
    resp = await llm.generate_chat(messages)
    content = resp.content.lower()
    
    # Must refuse or acknowledge limitation, NOT invent an amount
    assert "do not have verified information" in content or "connect you" in content
    assert "inr" not in content and "$" not in content
