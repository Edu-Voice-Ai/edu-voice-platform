"""Deterministic Fee-Grounding Safety Guard and Anti-Hallucination Tests.

Verifies:
1. Empty fee retrieval produces a deterministic boundary response offering counselor assistance.
2. Irrelevant RAG records (eligibility, dates) do not authorize a fee answer.
3. Ambiguous fee records do not authorize unsupported numerical amounts.
4. Annual tuition, admission fee, hostel fee, and total fees remain strictly distinct.
5. Verified information for one category is usable without inventing missing categories.
6. A non-Apex tenant never receives Apex-specific numerical fee fallbacks.
7. English, Telugu, Tenglish, and Hindi boundary responses operate accurately.
8. Context-dependent course follow-ups continue to function when verified fee data exists.
"""

from typing import List, Optional
import pytest
from app.session.state import SessionState
from app.conversation.router import FastQueryRouter, QueryComplexity
from app.rag.base import RAGProvider, RetrievalQuery, RetrievalResult, KnowledgeItem
from app.rag.mock import MockRAGProvider


class EmptyRAGProvider(RAGProvider):
    """RAG provider that returns zero records."""
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        return RetrievalResult(items=[], has_verified_info=False)


class IrrelevantRAGProvider(RAGProvider):
    """RAG provider returning non-fee records (e.g. eligibility and dates only)."""
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        items = [
            KnowledgeItem(
                id="elig_1",
                organization_id=query.organization_id,
                agent_id=query.agent_id,
                title="Eligibility Criteria",
                content="Eligibility for BTech CSE requires 60% aggregate in 12th Standard PCM and entrance rank.",
                category="eligibility"
            ),
            KnowledgeItem(
                id="dates_1",
                organization_id=query.organization_id,
                agent_id=query.agent_id,
                title="Academic Calendar",
                content="Admissions open on May 15 and close on July 31.",
                category="dates"
            )
        ]
        return RetrievalResult(items=items, has_verified_info=True)


class TuitionOnlyRAGProvider(RAGProvider):
    """RAG provider with verified annual tuition only; no hostel, admission, or total fee records."""
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        items = [
            KnowledgeItem(
                id="kb_tuition_only",
                organization_id=query.organization_id,
                agent_id=query.agent_id,
                title="Tuition Fees",
                content="Apex University offers BTech CSE with an annual tuition fee of INR 1,50,000 per year.",
                category="fees"
            )
        ]
        return RetrievalResult(items=items, has_verified_info=True)


class CustomTenantRAGProvider(RAGProvider):
    """RAG provider for a non-Apex tenant (e.g. Zenith College BBA)."""
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        items = [
            KnowledgeItem(
                id="zenith_bba",
                organization_id="org_zenith_college",
                agent_id=query.agent_id,
                title="BBA Program Fees",
                content="Zenith College offers BBA at INR 95,000 per year.",
                category="fees"
            )
        ]
        return RetrievalResult(items=items, has_verified_info=True)


# ─── 1. Empty RAG Grounding Protection Tests ──────────────────────────────────

@pytest.mark.asyncio
async def test_empty_rag_produces_deterministic_boundary_english():
    session = SessionState(
        session_id="s_empty_en",
        organization_id="org_empty_inst",
        agent_id="agent_1",
        preferred_language="en-IN",
        institution_name="Sunrise Institute"
    )
    rag = EmptyRAGProvider()
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the fee?", rag)
    assert comp == QueryComplexity.SIMPLE
    assert resp is not None
    assert "verified fee details" in resp.lower()
    assert "counselor" in resp.lower()
    # Ensure zero numerical amounts were invented
    assert not any(char.isdigit() for char in resp)


@pytest.mark.asyncio
async def test_empty_rag_produces_deterministic_boundary_telugu():
    session = SessionState(
        session_id="s_empty_te",
        organization_id="org_empty_inst",
        agent_id="agent_1",
        preferred_language="te-IN",
        institution_name="Sunrise Institute"
    )
    rag = EmptyRAGProvider()
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session, "ఫీజు ఎంత?", rag)
    assert comp == QueryComplexity.SIMPLE
    assert resp is not None
    assert "ఖచ్చితమైన ఫీజు వివరాలు లేవు" in resp
    assert "కౌన్సెలర్" in resp
    assert not any(char.isdigit() for char in resp)


@pytest.mark.asyncio
async def test_empty_rag_produces_deterministic_boundary_hindi():
    session = SessionState(
        session_id="s_empty_hi",
        organization_id="org_empty_inst",
        agent_id="agent_1",
        preferred_language="hi-IN",
        institution_name="Sunrise Institute"
    )
    rag = EmptyRAGProvider()
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session, "फीस कितनी है?", rag)
    assert comp == QueryComplexity.SIMPLE
    assert resp is not None
    assert "सत्यापित जानकारी नहीं है" in resp
    assert "काउंसलर" in resp
    assert not any(char.isdigit() for char in resp)


@pytest.mark.asyncio
async def test_empty_rag_tenglish_query():
    session = SessionState(
        session_id="s_empty_tenglish",
        organization_id="org_empty_inst",
        agent_id="agent_1",
        preferred_language="te-IN",
        institution_name="Sunrise Institute"
    )
    rag = EmptyRAGProvider()
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session, "fee entha?", rag)
    assert comp == QueryComplexity.SIMPLE
    assert resp is not None
    assert "ఖచ్చితమైన ఫీజు వివరాలు లేవు" in resp
    assert not any(char.isdigit() for char in resp)


# ─── 2. Irrelevant RAG Records Guard ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_irrelevant_rag_records_do_not_authorize_fee_answer():
    """Eligibility or calendar records returned by RAG must NOT authorize a fee answer."""
    session = SessionState(
        session_id="s_irrelevant",
        organization_id="org_test",
        agent_id="agent_1",
        preferred_language="en-IN",
        institution_name="Test College"
    )
    rag = IrrelevantRAGProvider()
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the annual fee?", rag)
    assert comp == QueryComplexity.SIMPLE
    assert resp is not None
    assert "verified fee details" in resp.lower()
    assert "counselor" in resp.lower()
    # Must NOT return eligibility percentage (60%) or dates as fee figures
    assert "60%" not in resp
    assert "July 31" not in resp


# ─── 3. Category Specificity & Missing Category Isolation ─────────────────────

@pytest.mark.asyncio
async def test_tuition_verified_while_hostel_and_admission_missing():
    """
    Missing hostel or admission fee records must not invalidate verified tuition fees,
    nor should annual tuition be presented as total cost.
    """
    session = SessionState(
        session_id="s_cat_spec",
        organization_id="org_apex_univ",
        agent_id="agent_1",
        preferred_language="en-IN",
        institution_name="Apex University"
    )
    rag = TuitionOnlyRAGProvider()

    # 1. Verified annual tuition is answered accurately
    comp_t, resp_t = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the CSE annual fee?", rag)
    assert comp_t == QueryComplexity.SIMPLE
    assert "1,50,000" in resp_t

    # 2. Missing hostel fee produces safe boundary response (does NOT invent a number)
    comp_h, resp_h = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the hostel fee?", rag)
    assert comp_h == QueryComplexity.SIMPLE
    assert "verified fee details" in resp_h.lower()
    assert "counselor" in resp_h.lower()
    assert not any(char.isdigit() for char in resp_h)

    # 3. Missing admission fee produces safe boundary response
    comp_a, resp_a = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the one-time admission fee?", rag)
    assert comp_a == QueryComplexity.SIMPLE
    assert "verified fee details" in resp_a.lower()
    assert "counselor" in resp_a.lower()

    # 4. Total 4-year cost: Annual tuition must NOT be presented as 4-year total when total is absent
    comp_tot, resp_tot = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the total 4-year cost?", rag)
    assert comp_tot == QueryComplexity.SIMPLE
    assert "verified fee details" in resp_tot.lower()


# ─── 4. Non-Apex Tenant Isolation & No Apex Numerical Leakage ─────────────────

@pytest.mark.asyncio
async def test_non_apex_tenant_never_leaks_apex_fees():
    """
    Zenith College caller asking about unsupported fees or courses must receive
    a safe boundary response without leaking Apex University fees or text.
    """
    session = SessionState(
        session_id="s_zenith_safe",
        organization_id="org_zenith_college",
        agent_id="agent_zenith",
        preferred_language="en-IN",
        institution_name="Zenith College"
    )
    rag = CustomTenantRAGProvider()

    # 1. Supported BBA fee inquiry returns verified Zenith content
    comp_bba, resp_bba = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the fee?", rag)
    assert comp_bba == QueryComplexity.SIMPLE
    assert "Zenith College offers BBA at INR 95,000 per year." in resp_bba
    assert "Apex University" not in resp_bba
    assert "1,50,000" not in resp_bba

    # 2. Unsupported course query (e.g. BTech CSE) returns safe boundary response
    comp_cse, resp_cse = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the BTech CSE fee?", rag)
    assert comp_cse == QueryComplexity.SIMPLE
    assert "verified fee details" in resp_cse.lower()
    assert "Apex University" not in resp_cse
    assert "1,50,000" not in resp_cse
    assert "95,000" not in resp_cse

    # 3. Unsupported category query (hostel fee) returns safe boundary response
    comp_hostel, resp_hostel = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the hostel fee?", rag)
    assert comp_hostel == QueryComplexity.SIMPLE
    assert "verified fee details" in resp_hostel.lower()
    assert "80,000" not in resp_hostel


# ─── 5. Context-Dependent Course Follow-ups With Verified RAG ─────────────────

@pytest.mark.asyncio
async def test_course_context_followup_with_verified_rag():
    """Context-dependent follow-up inquiries still work seamlessly when verified RAG data exists."""
    session = SessionState(
        session_id="s_context_followup",
        organization_id="org_apex_univ",
        agent_id="agent_admission",
        preferred_language="en-IN",
        institution_name="Apex University"
    )
    rag = MockRAGProvider()

    # Turn 1: Discuss ECE
    comp1, _ = await FastQueryRouter.route_and_resolve_fast_path(session, "Tell me about BTech ECE", rag)
    assert session.active_course == "ECE"

    # Turn 2: Follow-up fee inquiry inherits ECE
    comp2, resp2 = await FastQueryRouter.route_and_resolve_fast_path(session, "How much is the fee?", rag)
    assert comp2 == QueryComplexity.SIMPLE
    assert "1,20,000" in resp2
    assert "ECE" in resp2
    assert "1,50,000" not in resp2
