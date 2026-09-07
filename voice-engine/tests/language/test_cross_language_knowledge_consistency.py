"""Cross-Language Knowledge Consistency Test Suite.

Verifies that the same authoritative institution facts are retrieved and presented
identically across English, Hindi, Telugu, Telugish, and Hinglish.
"""
import pytest
from app.session.state import SessionState
from app.conversation.manager import ConversationManager
from app.rag.mock import MockRAGProvider
from app.rag.base import RetrievalQuery
from app.rag.normalizer import SemanticQueryNormalizer, SemanticIntent


@pytest.mark.asyncio
async def test_semantic_query_normalizer_courses():
    """Verify equivalent course queries across languages normalize to LIST_AVAILABLE_COURSES."""
    te_q = SemanticQueryNormalizer.normalize("మీ దగ్గర ఏమేం కోర్సులు ఉన్నాయి?")
    hi_q = SemanticQueryNormalizer.normalize("आपके पास कौन-कौन से courses हैं?")
    en_q = SemanticQueryNormalizer.normalize("What courses do you offer?")
    
    assert te_q.intent == SemanticIntent.LIST_AVAILABLE_COURSES
    assert hi_q.intent == SemanticIntent.LIST_AVAILABLE_COURSES
    assert en_q.intent == SemanticIntent.LIST_AVAILABLE_COURSES


@pytest.mark.asyncio
async def test_semantic_query_normalizer_fees():
    """Verify equivalent fee queries across languages normalize to FEES_INQUIRY with CSE entity."""
    te_q = SemanticQueryNormalizer.normalize("CSE fee ఎంత?")
    hi_q = SemanticQueryNormalizer.normalize("CSE ki fee kya hai?")
    en_q = SemanticQueryNormalizer.normalize("What is the tuition fee for CSE?")
    
    assert te_q.intent == SemanticIntent.FEES_INQUIRY
    assert "CSE" in te_q.courses_mentioned
    assert hi_q.intent == SemanticIntent.FEES_INQUIRY
    assert "CSE" in hi_q.courses_mentioned
    assert en_q.intent == SemanticIntent.FEES_INQUIRY
    assert "CSE" in en_q.courses_mentioned


@pytest.mark.asyncio
async def test_cross_lingual_rag_retrieval_consistency():
    """Verify RAG provider returns the identical authoritative knowledge items across languages."""
    rag = MockRAGProvider()
    org_id = "org_apex_univ"
    agent_id = "agent_admission"
    
    # 1. Course overview queries in Telugu, Hindi, English
    q_te = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="మీ దగ్గర ఏమేం కోర్సులు ఉన్నాయి?", top_k=2)
    q_hi = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="आपके पास कौन-कौन से courses हैं?", top_k=2)
    q_en = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="What courses do you offer?", top_k=2)
    
    res_te = await rag.retrieve(q_te)
    res_hi = await rag.retrieve(q_hi)
    res_en = await rag.retrieve(q_en)
    
    assert res_te.has_verified_info is True
    assert res_hi.has_verified_info is True
    assert res_en.has_verified_info is True
    
    # Authoritative course items must match exactly across all 3 languages
    te_ids = {item.id for item in res_te.items}
    hi_ids = {item.id for item in res_hi.items}
    en_ids = {item.id for item in res_en.items}
    
    assert te_ids == hi_ids == en_ids
    assert "kb_1" in te_ids
    assert "CSE" in res_te.items[0].content
    assert "ECE" in res_te.items[0].content


@pytest.mark.asyncio
async def test_cross_lingual_fees_retrieval_consistency():
    """Verify fee retrieval returns identical authoritative facts across languages."""
    rag = MockRAGProvider()
    org_id = "org_apex_univ"
    agent_id = "agent_admission"
    
    q_te = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="CSE ఫీజు ఎంత?", top_k=2)
    q_hi = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="CSE की फीस कितनी है?", top_k=2)
    q_en = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="What is the CSE fee?", top_k=2)
    
    res_te = await rag.retrieve(q_te)
    res_hi = await rag.retrieve(q_hi)
    res_en = await rag.retrieve(q_en)
    
    assert {i.id for i in res_te.items} == {i.id for i in res_hi.items} == {i.id for i in res_en.items}
    assert "1,50,000" in res_te.items[0].content
    assert "1,50,000" in res_hi.items[0].content
    assert "1,50,000" in res_en.items[0].content


@pytest.mark.asyncio
async def test_cross_lingual_eligibility_retrieval_consistency():
    """Verify eligibility retrieval returns identical facts across languages."""
    rag = MockRAGProvider()
    org_id = "org_apex_univ"
    agent_id = "agent_admission"
    
    q_te = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="CSE eligibility criteria ఏంటి?", top_k=2)
    q_hi = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="CSE की eligibility क्या है?", top_k=2)
    q_en = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="What is the eligibility for CSE?", top_k=2)
    
    res_te = await rag.retrieve(q_te)
    res_hi = await rag.retrieve(q_hi)
    res_en = await rag.retrieve(q_en)
    
    assert {i.id for i in res_te.items} == {i.id for i in res_hi.items} == {i.id for i in res_en.items}
    assert "60%" in res_te.items[0].content
    assert "60%" in res_hi.items[0].content
    assert "60%" in res_en.items[0].content


@pytest.mark.asyncio
async def test_cross_lingual_dates_retrieval_consistency():
    """Verify admission dates retrieval returns identical facts across languages."""
    rag = MockRAGProvider()
    org_id = "org_apex_univ"
    agent_id = "agent_admission"
    
    q_te = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="Admission ఎప్పుడు start అవుతుంది?", top_k=2)
    q_hi = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="Admission कब start होता है?", top_k=2)
    q_en = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="When do admissions start?", top_k=2)
    
    res_te = await rag.retrieve(q_te)
    res_hi = await rag.retrieve(q_hi)
    res_en = await rag.retrieve(q_en)
    
    assert {i.id for i in res_te.items} == {i.id for i in res_hi.items} == {i.id for i in res_en.items} == {"kb_3"}
    assert "May 15, 2026" in res_te.items[0].content
    assert "May 15, 2026" in res_hi.items[0].content
    assert "May 15, 2026" in res_en.items[0].content


@pytest.mark.asyncio
async def test_prompt_assembly_with_cross_lingual_rag():
    """Verify assemble_llm_messages injects verified facts for Telugu, Hindi, and English queries."""
    rag = MockRAGProvider()
    conv = ConversationManager(rag_provider=rag)
    
    # 1. Telugu Session
    sess_te = SessionState(session_id="s_te", organization_id="org_apex_univ", agent_id="agent_admission", preferred_language="te-IN", language_selection_complete=True)
    msgs_te = await conv.assemble_llm_messages(sess_te, "మీ దగ్గర ఏమేం కోర్సులు ఉన్నాయి?")
    sys_te = msgs_te[0]["content"]
    assert "VERIFIED INSTITUTIONAL KNOWLEDGE" in sys_te
    assert "BTech Computer Science and Engineering (CSE)" in sys_te
    assert "BTech Electronics and Communication (ECE)" in sys_te
    
    # 2. Hindi Session
    sess_hi = SessionState(session_id="s_hi", organization_id="org_apex_univ", agent_id="agent_admission", preferred_language="hi-IN", language_selection_complete=True)
    msgs_hi = await conv.assemble_llm_messages(sess_hi, "आपके पास कौन-कौन से courses हैं?")
    sys_hi = msgs_hi[0]["content"]
    assert "VERIFIED INSTITUTIONAL KNOWLEDGE" in sys_hi
    assert "BTech Computer Science and Engineering (CSE)" in sys_hi
    assert "BTech Electronics and Communication (ECE)" in sys_hi
    
    # 3. English Session
    sess_en = SessionState(session_id="s_en", organization_id="org_apex_univ", agent_id="agent_admission", preferred_language="en-IN", language_selection_complete=True)
    msgs_en = await conv.assemble_llm_messages(sess_en, "What courses do you offer?")
    sys_en = msgs_en[0]["content"]
    assert "VERIFIED INSTITUTIONAL KNOWLEDGE" in sys_en
    assert "BTech Computer Science and Engineering (CSE)" in sys_en
    assert "BTech Electronics and Communication (ECE)" in sys_en


@pytest.mark.asyncio
async def test_unoffered_courses_rejection_and_counselor_offer():
    """Verify that asking about MBA, MBBS, Law, etc. immediately returns the clear 1-sentence refusal with counselor offer."""
    from app.conversation.router import FastQueryRouter, QueryComplexity

    rag = MockRAGProvider()

    # English MBA check
    s_en = SessionState(session_id="s_en", organization_id="org_apex_univ", agent_id="agent_admission", preferred_language="en-IN")
    comp_en, resp_en = await FastQueryRouter.route_and_resolve_fast_path(s_en, "Do you have MBA course?", rag)
    assert comp_en == QueryComplexity.SIMPLE
    assert resp_en == "We do not offer MBA right now; we currently offer B.Tech in CSE and ECE. Would you like me to connect you with a human counselor?"

    # Telugu MBA check
    s_te = SessionState(session_id="s_te", organization_id="org_apex_univ", agent_id="agent_admission", preferred_language="te-IN")
    comp_te, resp_te = await FastQueryRouter.route_and_resolve_fast_path(s_te, "మీ కాలేజీలో MBA కోర్స్ ఉందా?", rag)
    assert comp_te == QueryComplexity.SIMPLE
    assert resp_te == "మా దగ్గర ప్రస్తుతం MBA కోర్స్ లేదు, కేవలం B.Tech CSE మరియు ECE మాత్రమే ఉన్నాయి. మీరు కౌన్సెలర్ తో మాట్లాడాలనుకుంటున్నారా?"

    # Hindi MBA check
    s_hi = SessionState(session_id="s_hi", organization_id="org_apex_univ", agent_id="agent_admission", preferred_language="hi-IN")
    comp_hi, resp_hi = await FastQueryRouter.route_and_resolve_fast_path(s_hi, "क्या आपके पास MBA कोर्स है?", rag)
    assert comp_hi == QueryComplexity.SIMPLE
    assert resp_hi == "हमारे पास अभी MBA कोर्स नहीं है, हम केवल B.Tech CSE और ECE प्रदान करते हैं। क्या आप काउंसलर से बात करना चाहेंगे?"

    # English MBBS check
    comp_mbbs, resp_mbbs = await FastQueryRouter.route_and_resolve_fast_path(s_en, "Can I apply for MBBS here?", rag)
    assert comp_mbbs == QueryComplexity.SIMPLE
    assert resp_mbbs == "We do not offer MBBS right now; we currently offer B.Tech in CSE and ECE. Would you like me to connect you with a human counselor?"

    # English Law check
    comp_law, resp_law = await FastQueryRouter.route_and_resolve_fast_path(s_en, "What is the fee for Law?", rag)
    assert comp_law == QueryComplexity.SIMPLE
    assert resp_law == "We do not offer Law right now; we currently offer B.Tech in CSE and ECE. Would you like me to connect you with a human counselor?"
