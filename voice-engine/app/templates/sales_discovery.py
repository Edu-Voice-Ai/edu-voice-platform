"""Sales Discovery Agent Template."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_generic_system_prompt
from app.tools.base import BaseTool, ToolRegistry, ToolExecutionResult
from app.tools.handoff import RequestHumanHandoffTool


class QualifyLeadTool(BaseTool):
    @property
    def name(self) -> str:
        return "qualify_lead"

    @property
    def description(self) -> str:
        return "Evaluate B2B/B2C prospect qualification criteria (budget, authority, need, timeline)."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "budget_fit": {"type": "boolean"},
                "decision_maker": {"type": "boolean"},
                "timeline_days": {"type": "integer"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        qualified = kwargs.get("budget_fit", True) and kwargs.get("timeline_days", 30) <= 60
        return ToolExecutionResult(tool_name=self.name, success=True, data={"qualified": qualified, "tier": "HIGH" if qualified else "NURTURE"})


class GetProductInformationTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_product_information"

    @property
    def description(self) -> str:
        return "Retrieve features, pricing tiers, and capabilities for solution offerings."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, product_name: str = "", **kwargs) -> ToolExecutionResult:
        plans = [
            {"tier": "Starter", "price": "INR 4,999/mo", "best_for": "Small teams (up to 5 members)"},
            {"tier": "Growth", "price": "INR 14,999/mo", "best_for": "Growing companies with automation needs"},
            {"tier": "Enterprise", "price": "Custom Pricing", "best_for": "Large organizations with dedicated support"}
        ]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"product": product_name, "plans": plans})


class CaptureLeadTool(BaseTool):
    @property
    def name(self) -> str:
        return "capture_lead"

    @property
    def description(self) -> str:
        return "Save qualified sales lead with contact details and pain points."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "contact_name": {"type": "string"},
                "phone_number": {"type": "string"},
                "company_name": {"type": "string"},
                "needs_summary": {"type": "string"}
            },
            "required": ["contact_name", "phone_number"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        lead_id = f"LEAD-SALES-{kwargs.get('phone_number', '1234')[-4:]}"
        return ToolExecutionResult(tool_name=self.name, success=True, data={"lead_id": lead_id, "status": "SAVED", **kwargs})


class ScheduleCallbackTool(BaseTool):
    @property
    def name(self) -> str:
        return "schedule_callback"

    @property
    def description(self) -> str:
        return "Schedule a follow-up discovery call with an account executive."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "phone_number": {"type": "string"},
                "preferred_time": {"type": "string"}
            },
            "required": ["phone_number", "preferred_time"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"status": "CALLBACK_SCHEDULED", **kwargs})


class RequestSalesHandoffTool(BaseTool):
    @property
    def name(self) -> str:
        return "request_sales_handoff"

    @property
    def description(self) -> str:
        return "Transfer hot qualified lead immediately to an active sales representative."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "urgency": {"type": "string", "enum": ["normal", "urgent"]}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"handoff": "INITIATED", "target": "sales_queue"})


class SalesDiscoveryTemplate(BaseAgentTemplate):
    """Sales Discovery & Inbound Qualification Agent Template."""

    SALES_KEYWORDS = {
        "pricing", "demo", "software", "solution", "product", "features", "enterprise",
        "quote", "cost", "trial", "team", "subscription", "integration", "crm", "api",
        "డెమో", "ధర", "సాఫ్ట్‌వేర్", "సొల్యూషన్",
        "डेमो", "कीमत", "सॉफ्टवेयर", "प्लान", "फीचर्स"
    }

    @property
    def template_type(self) -> str:
        return "sales_discovery"

    @property
    def default_agent_name(self) -> str:
        return "Aarav"

    @property
    def default_business_name(self) -> str:
        return "ABC Solutions"

    @property
    def default_persona_title(self) -> str:
        return "Sales Assistant"

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
            "uncover customer business needs, explain relevant software product plans, "
            "qualify timeline and team size, and schedule sales demos or callbacks"
        )
        rules = (
            "1. Ask what primary challenge the customer is trying to solve.\n"
            "2. Offer a product demonstration or consultation with a product specialist.\n"
            "3. State public plan pricing accurately and do not invent arbitrary quotes."
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
            return f"{biz_name} में आपका स्वागत है। मैं आपकी क्या मदद कर सकता हूँ?"
        return f"Welcome to {biz_name}. How can I help you today?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} తో మాట్లాడినందుకు ధన్యవాదాలు. మీ రోజు శుభంగా ఉండాలి!"
        elif lang == "hi-IN":
            return f"{biz_name} से बात करने के लिए धन्यवाद। आपका दिन शुभ हो!"
        return f"Thank you for reaching out to {biz_name}. Have a wonderful day!"

    def get_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(QualifyLeadTool())
        registry.register(GetProductInformationTool())
        registry.register(CaptureLeadTool())
        registry.register(ScheduleCallbackTool())
        registry.register(RequestSalesHandoffTool())
        registry.register(RequestHumanHandoffTool())
        return registry

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        return any(k in clean for k in self.SALES_KEYWORDS)

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = " ".join([m.get("content", "") for m in messages]).lower()
        return {
            "interest": "demo" if "demo" in text else "pricing",
            "qualified": any(w in text for w in ["team", "company", "business", "users"]),
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
            "key_outcome": "Sales discovery completed" + (" (Handoff requested)" if handoff else ""),
            "handoff_status": handoff
        }
