"""Unit tests for Admission AI tools, human handoff, and lead extraction."""
import pytest
from app.tools.admission import GetCoursesTool, GetFeeTool, GetEligibilityTool, CreateLeadTool
from app.tools.handoff import RequestHumanHandoffTool
from app.intelligence.lead_extraction import LeadExtractor


@pytest.mark.asyncio
async def test_admission_tools_execution():
    courses_tool = GetCoursesTool()
    res = await courses_tool.execute(organization_id="org_apex", agent_id="agent_1")
    assert res.success is True
    assert "courses" in res.data
    assert len(res.data["courses"]) >= 3

    fee_tool = GetFeeTool()
    fee_res = await fee_tool.execute(organization_id="org_apex", agent_id="agent_1", course_name="CSE")
    assert fee_res.success is True
    assert fee_res.data["fee_details"]["tuition_fee_annual_inr"] == 150000

    eligibility_tool = GetEligibilityTool()
    el_res = await eligibility_tool.execute(organization_id="org_apex", agent_id="agent_1", course_name="CSE")
    assert el_res.success is True
    assert "60%" in el_res.data["eligibility"]


@pytest.mark.asyncio
async def test_human_handoff_tool():
    handoff_tool = RequestHumanHandoffTool()
    res = await handoff_tool.execute(organization_id="org_apex", agent_id="agent_1", reason="Caller is angry")
    assert res.success is True
    assert res.data["type"] == "human_handoff_requested"
    assert res.data["reason"] == "Caller is angry"


def test_lead_extractor_parsing():
    messages = [
        {"role": "user", "content": "Hi, my phone number is 9876543210 and I am interested in BTech CSE. Please call me back."}
    ]
    lead = LeadExtractor.extract_from_messages(messages)
    assert lead.phone == "9876543210"
    assert lead.course == "BTECH CSE"
    assert lead.callback_requested is True
    assert lead.interest_level == "high"
