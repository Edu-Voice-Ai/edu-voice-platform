"""Fee Answer Accuracy and Knowledge Retrieval Remediation Tests.

Verifies:
1. Exact fee query patterns: "How much?", "What is the fee?", "How much is the course?"
2. Fee entity distinctions: tuition, hostel, admission, and total costs.
3. Multilingual equivalents across English, Telugu, and Tenglish.
4. Context-dependent follow-up questions ("How much?" after discussing a specific course).
5. Proper-noun recognition for external institutions ("Loyola College?").
6. Tenant isolation (non-Apex tenants like Zenith College).
7. Missing or unoffered programs policy without hallucinating prices.
"""

import pytest
import pytest_asyncio
from app.session.state import SessionState
from app.conversation.router import FastQueryRouter, QueryComplexity
from app.rag.mock import MockRAGProvider
from app.rag.normalizer import SemanticQueryNormalizer, SemanticIntent


@pytest.fixture
def rag_provider():
    return MockRAGProvider()


@pytest.fixture
def session_apex_en():
    return SessionState(
        session_id="sess_fee_en",
        organization_id="org_apex_univ",
        agent_id="agent_admission",
        preferred_language="en-IN",
        language_selection_complete=True,
        institution_name="Apex University",
    )


@pytest.fixture
def session_apex_te():
    return SessionState(
        session_id="sess_fee_te",
        organization_id="org_apex_univ",
        agent_id="agent_admission",
        preferred_language="te-IN",
        language_selection_complete=True,
        institution_name="Apex University",
    )


# ─── 1. Core Fee Query Regression Matrix ──────────────────────────────────────

@pytest.mark.asyncio
async def test_general_fee_queries_english(session_apex_en, rag_provider):
    """Verify general fee queries return verified annual fees for CSE and ECE."""
    queries = ["How much?", "What is the fee?", "How much is the course?"]
    for q in queries:
        norm = SemanticQueryNormalizer.normalize(q)
        assert norm.intent == SemanticIntent.FEES_INQUIRY
        assert norm.fee_type == "general"

        comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session_apex_en, q, rag_provider)
        assert comp == QueryComplexity.SIMPLE
        assert resp is not None
        assert "1,50,000" in resp
        assert "1,20,000" in resp
        assert "Apex University" in resp


@pytest.mark.asyncio
async def test_distinct_fee_categories(session_apex_en, rag_provider):
    """Verify tuition, hostel, admission, and total cost return distinct numbers and categories."""
    # A. Tuition Fee
    comp, resp_tuition = await FastQueryRouter.route_and_resolve_fast_path(
        session_apex_en, "What is the tuition fee?", rag_provider
    )
    assert comp == QueryComplexity.SIMPLE
    assert "1,50,000" in resp_tuition
    assert "1,20,000" in resp_tuition

    # B. Hostel Fee
    comp, resp_hostel = await FastQueryRouter.route_and_resolve_fast_path(
        session_apex_en, "What is the hostel fee?", rag_provider
    )
    assert comp == QueryComplexity.SIMPLE
    assert "80,000" in resp_hostel
    assert "hostel" in resp_hostel.lower() or "hostels" in resp_hostel.lower()

    # C. One-Time Admission Fee (must NOT return tuition fee)
    comp, resp_admission = await FastQueryRouter.route_and_resolve_fast_path(
        session_apex_en, "What is the admission fee?", rag_provider
    )
    assert comp == QueryComplexity.SIMPLE
    assert "25,000" in resp_admission
    assert "admission fee" in resp_admission.lower()
    assert "1,50,000" not in resp_admission, "Admission fee must not confuse annual tuition!"

    # D. Total 4-Year Cost (must return 6,00,000 / 4,80,000, not 1,50,000)
    comp, resp_total = await FastQueryRouter.route_and_resolve_fast_path(
        session_apex_en, "What is the total cost?", rag_provider
    )
    assert comp == QueryComplexity.SIMPLE
    assert "6,00,000" in resp_total
    assert "4,80,000" in resp_total
    assert "total tuition fee" in resp_total.lower() or "4-year" in resp_total.lower()


# ─── 2. Multilingual Fee Regression: Telugu and Tenglish ─────────────────────

@pytest.mark.asyncio
async def test_telugu_fee_queries(session_apex_te, rag_provider):
    """Verify Telugu fee questions return accurate Telugu responses with exact numbers."""
    # General fee in Telugu
    comp, resp_te = await FastQueryRouter.route_and_resolve_fast_path(session_apex_te, "ఎంత?", rag_provider)
    assert comp == QueryComplexity.SIMPLE
    assert "1,50,000" in resp_te
    assert "1,20,000" in resp_te
    assert "Apex University" in resp_te

    comp, resp_te_fee = await FastQueryRouter.route_and_resolve_fast_path(session_apex_te, "ఫీజు ఎంత?", rag_provider)
    assert comp == QueryComplexity.SIMPLE
    assert "1,50,000" in resp_te_fee

    # Hostel fee in Telugu
    comp, resp_te_hostel = await FastQueryRouter.route_and_resolve_fast_path(session_apex_te, "హాస్టల్ ఫీజు ఎంత?", rag_provider)
    assert comp == QueryComplexity.SIMPLE
    assert "80,000" in resp_te_hostel

    # Admission fee in Telugu
    comp, resp_te_adm = await FastQueryRouter.route_and_resolve_fast_path(session_apex_te, "అడ్మిషన్ ఫీజు ఎంత?", rag_provider)
    assert comp == QueryComplexity.SIMPLE
    assert "25,000" in resp_te_adm

    # Total cost in Telugu
    comp, resp_te_total = await FastQueryRouter.route_and_resolve_fast_path(session_apex_te, "మొత్తం ఖర్చు ఎంత?", rag_provider)
    assert comp == QueryComplexity.SIMPLE
    assert "6,00,000" in resp_te_total
    assert "4,80,000" in resp_te_total


@pytest.mark.asyncio
async def test_tenglish_code_switched_fee_queries(session_apex_te, rag_provider):
    """Verify Tenglish / code-switched queries are correctly normalized and resolved."""
    tenglish_cases = [
        ("fee entha?", "1,50,000"),
        ("karchu entha?", "1,50,000"),
        ("admission fee entha?", "25,000"),
        ("hostel fee entha?", "80,000"),
        ("total cost entha?", "6,00,000"),
    ]
    for query, expected_number in tenglish_cases:
        comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session_apex_te, query, rag_provider)
        assert comp == QueryComplexity.SIMPLE
        assert expected_number in resp, f"Failed for Tenglish query: {query}"


# ─── 3. Contextual Follow-up Resolution ──────────────────────────────────────

@pytest.mark.asyncio
async def test_contextual_follow_up_after_course_discussion(session_apex_en, rag_provider):
    """
    Test turn 1: User asks about BTech CSE.
    Test turn 2: User asks short follow-up 'How much?'.
    Session state must retain CSE context and answer specific CSE fee without guessing.
    """
    # Turn 1: Discuss CSE
    comp1, resp1 = await FastQueryRouter.route_and_resolve_fast_path(session_apex_en, "Tell me about BTech CSE", rag_provider)
    assert session_apex_en.active_course == "CSE"

    # Turn 2: Short follow-up "How much?"
    comp2, resp2 = await FastQueryRouter.route_and_resolve_fast_path(session_apex_en, "How much?", rag_provider)
    assert comp2 == QueryComplexity.SIMPLE
    assert "1,50,000" in resp2
    assert "CSE" in resp2
    # Ensure ECE fee is NOT confused when CSE was specifically active
    assert "1,20,000" not in resp2

    # Turn 3: Follow-up on total cost for active CSE course
    comp3, resp3 = await FastQueryRouter.route_and_resolve_fast_path(session_apex_en, "What is the total cost?", rag_provider)
    assert comp3 == QueryComplexity.SIMPLE
    assert "6,00,000" in resp3
    assert "4,80,000" not in resp3


# ─── 4. Proper Noun & External Institution Recognition Test ───────────────────

@pytest.mark.asyncio
async def test_proper_noun_external_institution_loyola(session_apex_en, rag_provider):
    """
    Verify 'Loyola College?' recognition:
    The assistant represents Apex University and must NOT hallucinate fees for Loyola College.
    """
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(session_apex_en, "Loyola College?", rag_provider)
    assert comp == QueryComplexity.SIMPLE
    assert resp is not None
    assert "Loyola College" in resp
    assert "Apex University" in resp
    assert "do not have fee or admission details" in resp.lower()

    # Telugu external institution recognition
    session_te = SessionState(
        session_id="s_te_ext",
        organization_id="org_apex_univ",
        agent_id="agent_admission",
        preferred_language="te-IN"
    )
    comp_te, resp_te = await FastQueryRouter.route_and_resolve_fast_path(session_te, "Loyola College వివరాలు చెప్పండి", rag_provider)
    assert comp_te == QueryComplexity.SIMPLE
    assert "Loyola College" in resp_te
    assert "Apex University" in resp_te


# ─── 5. Tenant Isolation Verification ────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_non_apex_institution(rag_provider):
    """
    Verify Zenith College tenant asking 'What is the fee?' gets Zenith College BBA fees,
    never leaking Apex University BTech fees.
    """
    sess_zenith = SessionState(
        session_id="s_zenith",
        organization_id="org_zenith_college",
        agent_id="agent_admission",
        institution_name="Zenith College",
        preferred_language="en-IN"
    )
    comp, resp = await FastQueryRouter.route_and_resolve_fast_path(sess_zenith, "What is the fee?", rag_provider)
    assert comp == QueryComplexity.SIMPLE
    assert resp is not None
    assert "Zenith College offers BBA at INR 95,000 per year." in resp
    assert "Apex University" not in resp
    assert "1,50,000" not in resp
