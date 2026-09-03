"""Integration test simulating Backend / Control Plane contract interaction with Voice Engine."""
import pytest
from app.session.state import SessionState, TurnStateEnum
from app.session.events import EventType, SessionEvent
from app.rag.mock import MockRAGProvider
from app.rag.base import RetrievalQuery
from app.tools.admission import GetFeeTool, GetCoursesTool, CreateLeadTool
from app.tools.handoff import RequestHumanHandoffTool
from app.intelligence.lead_extraction import LeadExtractor
from app.intelligence.summary import CallSummarizer


@pytest.mark.asyncio
async def test_backend_control_plane_session_lifecycle():
    """Verify session initialization from backend parameters with tenant isolation and post-call intelligence."""
    org_id = "org_apex_univ"
    agent_id = "agent_admissions_v1"
    session_id = "sess_backend_test_001"

    # 1. Backend initializes session state
    session = SessionState(
        session_id=session_id,
        organization_id=org_id,
        agent_id=agent_id,
        preferred_language="te-IN",
        language_selection_complete=True
    )
    assert session.organization_id == org_id
    assert session.agent_id == agent_id
    assert session.preferred_language == "te-IN"
    assert session.conversation_style == "telugish"

    # 2. RAG retrieval strictly tenant-scoped
    rag = MockRAGProvider()
    q = RetrievalQuery(organization_id=org_id, agent_id=agent_id, query_text="What is the fee for BTech CSE?")
    res = await rag.retrieve(q)
    assert res.has_verified_info is True
    assert len(res.items) > 0
    assert any("1,50,000" in item.content for item in res.items)

    # 3. Tool execution
    fee_tool = GetFeeTool()
    fee_res = await fee_tool.execute(organization_id=org_id, agent_id=agent_id, course_name="CSE")
    assert fee_res.success is True
    assert fee_res.data["fee_details"]["tuition_fee_annual_inr"] == 150000

    # 4. Conversation turns
    session.append_message("user", "నా పేరు Aravind Kumar. నా నంబర్ 8121161040. BTech CSE fee ఎంత?")
    session.append_message("assistant", "నమస్కారం Aravind Kumar garu. BTech CSE fee ఏడాదికి ₹1,50,000. మీరు application submit చేశారా?")

    # 5. Lead Intelligence extraction
    lead = LeadExtractor.extract_from_messages(session.messages)
    assert lead.phone == "8121161040"
    assert lead.course is not None
    assert lead.interest_level in ["high", "medium", "low"]

    # 6. Post-call summarization
    summary = CallSummarizer.generate_summary(session_id=session_id, messages=session.messages, duration_sec=45.0)
    assert summary.session_id == session_id
    assert summary.total_turns == 1
    assert len(summary.key_outcome) > 0

    # 7. Human handoff simulation
    handoff_tool = RequestHumanHandoffTool()
    handoff_res = await handoff_tool.execute(
        organization_id=org_id,
        agent_id=agent_id,
        reason="Caller requested senior counselor regarding scholarship",
        caller_phone="8121161040"
    )
    assert handoff_res.success is True
    assert handoff_res.data.get("status") == "HANDOFF_SCHEDULED"
    assert handoff_res.data.get("type") == "human_handoff_requested"
