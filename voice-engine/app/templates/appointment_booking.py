"""Appointment Booking Agent Template."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_generic_system_prompt
from app.tools.base import BaseTool, ToolRegistry, ToolExecutionResult
from app.tools.handoff import RequestHumanHandoffTool


class GetServicesTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_services"

    @property
    def description(self) -> str:
        return "Retrieve the list of available clinic or facility services."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        services = [
            {"id": "s1", "name": "General Consultation", "duration_mins": 30, "fee_inr": 500},
            {"id": "s2", "name": "Dental Checkup", "duration_mins": 45, "fee_inr": 700},
            {"id": "s3", "name": "Pediatric Care", "duration_mins": 30, "fee_inr": 600}
        ]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"services": services})


class GetStaffTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_staff"

    @property
    def description(self) -> str:
        return "Retrieve the list of available doctors or specialists."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "specialty": {"type": "string", "description": "Medical specialty or department"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        staff = [
            {"name": "Dr. Sharma", "specialty": "General Physician", "availability": "Mon-Fri 10am-4pm"},
            {"name": "Dr. Reddy", "specialty": "Dentist", "availability": "Mon-Sat 11am-6pm"}
        ]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"staff": staff})


class CheckAvailabilityTool(BaseTool):
    @property
    def name(self) -> str:
        return "check_availability"

    @property
    def description(self) -> str:
        return "Check available appointment slots for a doctor and date."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "doctor_name": {"type": "string"},
                "preferred_date": {"type": "string", "description": "Date formatted YYYY-MM-DD"}
            },
            "required": ["preferred_date"]
        }

    async def execute(self, organization_id: str, agent_id: str, preferred_date: str = "", **kwargs) -> ToolExecutionResult:
        slots = ["10:30 AM", "02:00 PM", "04:30 PM"]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"date": preferred_date, "available_slots": slots})


class CreateAppointmentTool(BaseTool):
    @property
    def name(self) -> str:
        return "create_appointment"

    @property
    def description(self) -> str:
        return "Book and confirm a new appointment slot for the patient."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patient_name": {"type": "string"},
                "phone_number": {"type": "string"},
                "service": {"type": "string"},
                "date": {"type": "string"},
                "time_slot": {"type": "string"}
            },
            "required": ["patient_name", "phone_number", "date", "time_slot"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        apt_id = f"APT-{kwargs.get('phone_number', '1234')[-4:]}-OK"
        return ToolExecutionResult(
            tool_name=self.name,
            success=True,
            data={"appointment_id": apt_id, "status": "CONFIRMED", **kwargs}
        )


class RescheduleAppointmentTool(BaseTool):
    @property
    def name(self) -> str:
        return "reschedule_appointment"

    @property
    def description(self) -> str:
        return "Reschedule an existing appointment to a new date and time."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string"},
                "new_date": {"type": "string"},
                "new_time_slot": {"type": "string"}
            },
            "required": ["appointment_id", "new_date", "new_time_slot"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"status": "RESCHEDULED", **kwargs})


class CancelAppointmentTool(BaseTool):
    @property
    def name(self) -> str:
        return "cancel_appointment"

    @property
    def description(self) -> str:
        return "Cancel an existing appointment upon patient request."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string"},
                "cancellation_reason": {"type": "string"}
            },
            "required": ["appointment_id"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"status": "CANCELLED", **kwargs})


class AppointmentBookingTemplate(BaseAgentTemplate):
    """Appointment Booking & Clinic Scheduling Agent Template."""

    APPOINTMENT_KEYWORDS = {
        "appointment", "book", "booking", "schedule", "reschedule", "cancel", "slot",
        "doctor", "consultation", "clinic", "timing", "available", "time", "date",
        "అపాయింట్మెంట్", "బుక్", "డాక్టర్", "టైమ్", "తేదీ", "రద్దు",
        "अपॉइंटमेंट", "बुक", "डॉक्टर", "तारीख", "समय"
    }

    @property
    def template_type(self) -> str:
        return "appointment_booking"

    @property
    def default_agent_name(self) -> str:
        return "Ananya"

    @property
    def default_business_name(self) -> str:
        return "City Clinic"

    @property
    def default_persona_title(self) -> str:
        return "Appointment Assistant"

    def get_system_prompt(
        self,
        session: Any,
        verified_context: str = "",
        lang: str = "en-IN"
    ) -> str:
        agent_name = getattr(session, "agent_name", None) or self.default_agent_name
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        active_lang = lang or getattr(session, "preferred_language", None) or getattr(session, "language", "en-IN")

        tasks = (
            "help patients identify required services, check doctor availability, "
            "book or reschedule appointments, and confirm scheduling details"
        )
        rules = (
            "1. Ask for preferred date and time clearly.\n"
            "2. Confirm the caller's full name and ten-digit phone number before finalizing booking.\n"
            "3. Never provide medical prescriptions or clinical diagnoses."
        )

        return build_generic_system_prompt(
            business_name=biz_name,
            agent_name=agent_name,
            role_persona=self.default_persona_title,
            industry_tasks=tasks,
            specific_rules=rules,
            language_hint=active_lang,
            preferred_language=active_lang,
            verified_context=verified_context
        )

    def get_greeting(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} కి స్వాగతం. నేను మీకు ఎలా సహాయపడగలను?"
        elif lang == "hi-IN":
            return f"{biz_name} में आपका स्वागत है। मैं आपकी क्या मदद कर सकती हूँ?"
        return f"Welcome to {biz_name}. How can I help you today?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} కి కాల్ చేసినందుకు ధన్యవాదాలు. మీ రోజు శుభంగా ఉండాలి!"
        elif lang == "hi-IN":
            return f"{biz_name} में कॉल करने के लिए धन्यवाद। आपका दिन शुभ हो!"
        return f"Thank you for contacting {biz_name}. Have a wonderful day!"

    def get_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(GetServicesTool())
        registry.register(GetStaffTool())
        registry.register(CheckAvailabilityTool())
        registry.register(CreateAppointmentTool())
        registry.register(RescheduleAppointmentTool())
        registry.register(CancelAppointmentTool())
        registry.register(RequestHumanHandoffTool())
        return registry

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        return any(k in clean for k in self.APPOINTMENT_KEYWORDS)

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = " ".join([m.get("content", "") for m in messages])
        return {
            "service_requested": "General Consultation" if "consult" in text.lower() else "Appointment Inquiry",
            "caller_intent": "book_appointment" if any(w in text.lower() for w in ["book", "appointment", "slot"]) else "general_inquiry",
            "follow_up_required": True
        }

    def generate_summary(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        duration_sec: float = 0.0,
        handoff: bool = False
    ) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "category": self.template_type,
            "total_turns": len([m for m in messages if m.get("role") == "user"]),
            "duration_seconds": duration_sec,
            "key_outcome": "Appointment inquiry addressed" + (" (Handoff requested)" if handoff else ""),
            "handoff_status": handoff
        }
