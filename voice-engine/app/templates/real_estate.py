"""Real Estate Agent Template."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_generic_system_prompt
from app.tools.base import BaseTool, ToolRegistry, ToolExecutionResult
from app.tools.handoff import RequestHumanHandoffTool


class SearchPropertiesTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_properties"

    @property
    def description(self) -> str:
        return "Search available residential and commercial properties by location, type, and budget."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City or locality name"},
                "property_type": {"type": "string", "enum": ["apartment", "villa", "plot", "commercial", "all"]},
                "max_budget_inr": {"type": "number", "description": "Maximum budget in INR"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, location: str = "Hyderabad", **kwargs) -> ToolExecutionResult:
        listings = [
            {"id": "prop_101", "name": "Green Valley Heights", "type": "2BHK / 3BHK Apartment", "location": location, "price_range": "INR 75 Lakhs - 1.2 Cr"},
            {"id": "prop_102", "name": "Emerald County Villas", "type": "4BHK Luxury Villa", "location": location, "price_range": "INR 2.5 Cr - 3.5 Cr"}
        ]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"location": location, "properties": listings})


class GetPropertyDetailsTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_property_details"

    @property
    def description(self) -> str:
        return "Retrieve detailed specifications, amenities, and floor plans for a specific property."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "Unique property ID or name"}
            },
            "required": ["property_id"]
        }

    async def execute(self, organization_id: str, agent_id: str, property_id: str = "", **kwargs) -> ToolExecutionResult:
        details = {
            "property_id": property_id,
            "amenities": ["Clubhouse", "Swimming Pool", "Gym", "Power Backup", "24/7 Security"],
            "possession_date": "December 2026",
            "rera_approved": True
        }
        return ToolExecutionResult(tool_name=self.name, success=True, data=details)


class CapturePropertyLeadTool(BaseTool):
    @property
    def name(self) -> str:
        return "capture_property_lead"

    @property
    def description(self) -> str:
        return "Record prospect buyer/tenant preferences and contact info for agent follow-up."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "buyer_name": {"type": "string"},
                "phone_number": {"type": "string"},
                "budget": {"type": "string"},
                "preferred_location": {"type": "string"},
                "bedrooms": {"type": "string"}
            },
            "required": ["buyer_name", "phone_number"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        lead_id = f"RE-LEAD-{kwargs.get('phone_number', '0000')[-4:]}"
        return ToolExecutionResult(tool_name=self.name, success=True, data={"lead_id": lead_id, "status": "CAPTURED", **kwargs})


class ScheduleSiteVisitTool(BaseTool):
    @property
    def name(self) -> str:
        return "schedule_site_visit"

    @property
    def description(self) -> str:
        return "Schedule an in-person or virtual property site visit for a buyer."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "buyer_name": {"type": "string"},
                "phone_number": {"type": "string"},
                "property_name": {"type": "string"},
                "visit_date": {"type": "string"},
                "visit_time": {"type": "string"}
            },
            "required": ["buyer_name", "phone_number", "property_name", "visit_date"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        visit_id = f"VISIT-{kwargs.get('phone_number', '1234')[-4:]}"
        return ToolExecutionResult(tool_name=self.name, success=True, data={"visit_id": visit_id, "status": "SCHEDULED", **kwargs})


class RealEstateTemplate(BaseAgentTemplate):
    """Real Estate & Property Consultant Agent Template."""

    REAL_ESTATE_KEYWORDS = {
        "property", "apartment", "flat", "villa", "plot", "bhk", "2bhk", "3bhk", "4bhk",
        "house", "budget", "possession", "sqft", "square feet", "amenities", "site visit",
        "rera", "rent", "buy", "purchase", "invest", "builder", "realty",
        "ఫ్లాట్", "ఇల్లు", "విల్లా", "సైట్ విజిట్", "బడ్జెట్",
        "फ्लैट", "मकान", "विला", "प्रॉपर्टी", "बजट", "साइट विजिट"
    }

    @property
    def template_type(self) -> str:
        return "real_estate"

    @property
    def default_agent_name(self) -> str:
        return "Rahul"

    @property
    def default_business_name(self) -> str:
        return "ABC Realty"

    @property
    def default_persona_title(self) -> str:
        return "Property Consultant"

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
            "help prospective buyers and renters discover properties, understand locations, "
            "budgets, and configurations (1BHK, 2BHK, 3BHK, villas), and schedule site visits"
        )
        rules = (
            "1. Ask about preferred locality, budget range, and timeline for purchase/move-in.\n"
            "2. Offer site visits once preference is understood.\n"
            "3. State verified prices and configurations directly. Do not promise unverified discounts."
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
            return f"{biz_name} కి స్వాగతం. మీ కలల ఇంటిని వెతకడంలో నేను మీకు ఎలా సహాయపడగలను?"
        elif lang == "hi-IN":
            return f"{biz_name} में आपका स्वागत है। प्रॉपर्टी खोजने में मैं आपकी क्या मदद कर सकता हूँ?"
        return f"Welcome to {biz_name}. How can I help you find a property today?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} తో మాట్లాడినందుకు ధన్యవాదాలు. మీ ప్రాపర్టీ శోధనకు శుభాకాంక్షలు!"
        elif lang == "hi-IN":
            return f"{biz_name} से संपर्क करने के लिए धन्यवाद। आपका दिन शुभ हो!"
        return f"Thank you for contacting {biz_name}. Have a wonderful day!"

    def get_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(SearchPropertiesTool())
        registry.register(GetPropertyDetailsTool())
        registry.register(CapturePropertyLeadTool())
        registry.register(ScheduleSiteVisitTool())
        registry.register(RequestHumanHandoffTool())
        return registry

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        return any(k in clean for k in self.REAL_ESTATE_KEYWORDS)

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = " ".join([m.get("content", "") for m in messages]).lower()
        return {
            "property_type": "3BHK" if "3bhk" in text else ("2BHK" if "2bhk" in text else "apartment"),
            "site_visit_requested": any(w in text for w in ["visit", "see", "show", "schedule"]),
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
            "key_outcome": "Real estate enquiry qualified" + (" (Handoff requested)" if handoff else ""),
            "handoff_status": handoff
        }
