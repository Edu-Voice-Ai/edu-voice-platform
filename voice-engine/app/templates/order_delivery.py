"""Order & Delivery Support Agent Template."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_generic_system_prompt
from app.tools.base import BaseTool, ToolRegistry, ToolExecutionResult
from app.tools.handoff import RequestHumanHandoffTool


class GetOrderStatusTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_order_status"

    @property
    def description(self) -> str:
        return "Lookup order placement details, packed items, and payment confirmation."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, order_id: str = "ORD-5001", **kwargs) -> ToolExecutionResult:
        data = {
            "order_id": order_id,
            "items": "Smart Fitness Band (Black)",
            "order_status": "SHIPPED",
            "invoice_amount_inr": 1899,
            "placed_on": "Yesterday"
        }
        return ToolExecutionResult(tool_name=self.name, success=True, data=data)


class GetDeliveryStatusTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_delivery_status"

    @property
    def description(self) -> str:
        return "Track courier tracking number, current hub, and estimated time of arrival."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, order_id: str = "ORD-5001", **kwargs) -> ToolExecutionResult:
        tracking = {
            "order_id": order_id,
            "courier_partner": "Express Logistics",
            "tracking_number": "TRK98765432",
            "current_location": "Local Delivery Hub",
            "expected_delivery": "Today by 6:00 PM",
            "delivery_agent_contact": "Will be sent via SMS when out for delivery"
        }
        return ToolExecutionResult(tool_name=self.name, success=True, data=tracking)


class RescheduleDeliveryTool(BaseTool):
    @property
    def name(self) -> str:
        return "reschedule_delivery"

    @property
    def description(self) -> str:
        return "Change the scheduled delivery date or select evening delivery slot."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "preferred_date": {"type": "string"},
                "preferred_time_slot": {"type": "string"}
            },
            "required": ["order_id", "preferred_date"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"status": "RESCHEDULED", **kwargs})


class RequestCancellationTool(BaseTool):
    @property
    def name(self) -> str:
        return "request_cancellation"

    @property
    def description(self) -> str:
        return "Request order cancellation and automatic refund before delivery."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "reason": {"type": "string"}
            },
            "required": ["order_id"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"status": "CANCELLATION_INITIATED", **kwargs})


class CreateSupportRequestTool(BaseTool):
    @property
    def name(self) -> str:
        return "create_support_request"

    @property
    def description(self) -> str:
        return "File a formal delivery ticket for damaged package, late arrival, or missing items."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "issue_description": {"type": "string"}
            },
            "required": ["issue_description"]
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        ticket_id = f"TCK-{kwargs.get('order_id', '9999')[-4:]}"
        return ToolExecutionResult(tool_name=self.name, success=True, data={"ticket_id": ticket_id, "status": "OPEN", **kwargs})


class OrderDeliveryTemplate(BaseAgentTemplate):
    """Order & Logistics Support Agent Template."""

    ORDER_KEYWORDS = {
        "order", "delivery", "track", "tracking", "package", "courier", "where is",
        "arriving", "shipped", "delayed", "late", "damaged", "refund", "cancel order",
        "ఆర్డర్", "డెలివరీ", "ట్రాకింగ్", "ఎక్కడ ఉంది", "లేట్",
        "ऑर्डर", "डिलीवरी", "ट्रैकिंग", "पार्सल", "कहाँ है", "लेट"
    }

    @property
    def template_type(self) -> str:
        return "order_delivery"

    @property
    def default_agent_name(self) -> str:
        return "Ravi"

    @property
    def default_business_name(self) -> str:
        return "ABC Customer Support"

    @property
    def default_persona_title(self) -> str:
        return "Customer Support Assistant"

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
            "assist customers with tracking shipment statuses, expected delivery dates, "
            "rescheduling delivery slots, and resolving courier or package issues promptly"
        )
        rules = (
            "1. Ask for or confirm the order number or registered mobile number.\n"
            "2. State current courier location and expected delivery time directly.\n"
            "3. If package is damaged or delayed, offer to file a support ticket or connect with human support."
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
            return f"{biz_name} కి స్వాగతం. మీ ఆర్డర్ లేదా డెలివరీ వివరాలపై నేను మీకు ఎలా సహాయపడగలను?"
        elif lang == "hi-IN":
            return f"{biz_name} में आपका स्वागत है। आपके ऑर्डर और डिलीवरी में मैं आपकी क्या सहायता कर सकता हूँ?"
        return f"Welcome to {biz_name}. How can I help you today?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} కి కాల్ చేసినందుకు ధన్యవాదాలు. మీ రోజు శుభంగా ఉండాలి!"
        elif lang == "hi-IN":
            return f"{biz_name} में संपर्क करने के लिए धन्यवाद। आपका दिन शुभ हो!"
        return f"Thank you for contacting {biz_name}. Have a wonderful day!"

    def get_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(GetOrderStatusTool())
        registry.register(GetDeliveryStatusTool())
        registry.register(RescheduleDeliveryTool())
        registry.register(RequestCancellationTool())
        registry.register(CreateSupportRequestTool())
        registry.register(RequestHumanHandoffTool())
        return registry

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        return any(k in clean for k in self.ORDER_KEYWORDS)

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = " ".join([m.get("content", "") for m in messages]).lower()
        return {
            "issue_type": "delivery_delay" if "delay" in text or "late" in text else "status_check",
            "resolution": "in_progress",
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
            "key_outcome": "Delivery support request processed" + (" (Handoff requested)" if handoff else ""),
            "handoff_status": handoff
        }
