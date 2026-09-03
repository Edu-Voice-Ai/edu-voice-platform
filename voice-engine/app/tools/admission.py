"""Admission AI Tools with strict verified institutional facts and development mocks."""
from typing import Dict, Any
from app.tools.base import BaseTool, ToolExecutionResult
from app.core.logging import get_logger

logger = get_logger("tools.admission")


class GetCoursesTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_courses"

    @property
    def description(self) -> str:
        return "Retrieve the list of approved academic courses offered by the educational institution."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "degree_level": {"type": "string", "enum": ["undergraduate", "postgraduate", "diploma", "all"], "default": "all"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, degree_level: str = "all", **kwargs) -> ToolExecutionResult:
        courses = [
            {"code": "BTECH-CSE", "name": "B.Tech Computer Science and Engineering", "duration": "4 Years", "seats": 180},
            {"code": "BTECH-ECE", "name": "B.Tech Electronics and Communication Engineering", "duration": "4 Years", "seats": 120}
        ]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"organization_id": organization_id, "courses": courses})


class GetFeeTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_fee"

    @property
    def description(self) -> str:
        return "Retrieve the verified tuition and fee structure for a specific course at the institution."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "course_name": {"type": "string", "description": "Name or code of the course (e.g. CSE, ECE, BTech)"}
            },
            "required": ["course_name"]
        }

    async def execute(self, organization_id: str, agent_id: str, course_name: str = "", **kwargs) -> ToolExecutionResult:
        c_lower = course_name.lower()
        if "cse" in c_lower or "computer" in c_lower:
            fee_info = {"course": "B.Tech Computer Science and Engineering", "tuition_fee_annual_inr": 150000, "admission_fee_one_time_inr": 25000, "currency": "INR"}
        elif "ece" in c_lower or "electronics" in c_lower:
            fee_info = {"course": "B.Tech Electronics and Communication", "tuition_fee_annual_inr": 120000, "admission_fee_one_time_inr": 25000, "currency": "INR"}
        else:
            fee_info = {"course": course_name, "tuition_fee_annual_inr": 100000, "admission_fee_one_time_inr": 20000, "currency": "INR"}
        
        return ToolExecutionResult(tool_name=self.name, success=True, data={"organization_id": organization_id, "fee_details": fee_info})


class GetEligibilityTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_eligibility"

    @property
    def description(self) -> str:
        return "Get verified admission eligibility criteria for a given course."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "course_name": {"type": "string", "description": "Name of the course"}
            },
            "required": ["course_name"]
        }

    async def execute(self, organization_id: str, agent_id: str, course_name: str = "", **kwargs) -> ToolExecutionResult:
        criteria = "Minimum 60% aggregate in Class 12 / Intermediate with Mathematics, Physics, and Chemistry. Valid score in State EAPCET / JEE Main."
        return ToolExecutionResult(tool_name=self.name, success=True, data={"course": course_name, "eligibility": criteria})


class GetAdmissionDatesTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_admission_dates"

    @property
    def description(self) -> str:
        return "Get important admission dates, application deadlines, and counseling schedules."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={
            "application_start": "2026-05-15",
            "application_deadline": "2026-07-31",
            "counseling_phase_1": "2026-08-05 to 2026-08-12",
            "classes_commence": "2026-09-01"
        })


class GetDocumentsRequiredTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_documents_required"

    @property
    def description(self) -> str:
        return "Get the checklist of required documents for admission verification."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        docs = [
            "10th Standard Marks Memo",
            "12th / Intermediate Marks Memo & Transfer Certificate",
            "Entrance Exam Rank Card (JEE / State EAPCET)",
            "Aadhaar Card Copy",
            "Passport-size Photographs (4 copies)",
            "Caste / Income Certificate (if applicable)"
        ]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"required_documents": docs})


class GetHostelInformationTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_hostel_information"

    @property
    def description(self) -> str:
        return "Get details on hostel accommodation, amenities, and fees."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={
            "ac_room_annual_inr": 110000,
            "non_ac_room_annual_inr": 80000,
            "includes_mess": True,
            "wifi_enabled": True,
            "separate_hostels_for_boys_and_girls": True
        })


class GetCampusInformationTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_campus_information"

    @property
    def description(self) -> str:
        return "Get campus location, infrastructure, transport, and lab facilities."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={
            "location": "Main Highway Campus, Tech Valley",
            "campus_size_acres": 45,
            "facilities": ["Central Digital Library", "AI & Robotics Research Lab", "Sports Complex", "Bus Transport covering 30 routes"]
        })


class CreateLeadTool(BaseTool):
    @property
    def name(self) -> str:
        return "create_lead"

    @property
    def description(self) -> str:
        return "Register an interested admission prospect lead for follow-up by the admissions counselor."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "student_name": {"type": "string"},
                "phone_number": {"type": "string"},
                "interested_course": {"type": "string"},
                "qualification": {"type": "string"},
                "preferred_callback_time": {"type": "string"}
            },
            "required": ["student_name", "phone_number"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        lead_id = f"lead_{int(kwargs.get('phone_number', '123')[-4:])}"
        logger.info(f"Admission Lead registered: {kwargs}")
        return ToolExecutionResult(tool_name=self.name, success=True, data={"lead_id": lead_id, "status": "REGISTERED", **kwargs})
