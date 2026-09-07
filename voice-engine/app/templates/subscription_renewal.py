"""Subscription Renewal Agent Template."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_generic_system_prompt
from app.tools.base import BaseTool, ToolRegistry, ToolExecutionResult
from app.tools.handoff import RequestHumanHandoffTool


class GetSubscriptionTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_subscription"

    @property
    def description(self) -> str:
        return "Retrieve the member's current active plan, renewal date, and billing cycle."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "member_id": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, member_id: str = "MEM-202", **kwargs) -> ToolExecutionResult:
        data = {
            "member_id": member_id,
            "plan_name": "Pro Annual Membership",
            "expiry_date": "In 7 days",
            "renewal_price_inr": 4999,
            "auto_renew_enabled": False
        }
        return ToolExecutionResult(tool_name=self.name, success=True, data=data)


class GetPlanDetailsTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_plan_details"

    @property
    def description(self) -> str:
        return "Compare features and pricing between Standard, Pro, and Premium tiers."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_plan": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, target_plan: str = "Premium", **kwargs) -> ToolExecutionResult:
        tiers = [
            {"tier": "Pro", "price_annual": "INR 4,999", "features": "HD streaming, 2 devices, priority support"},
            {"tier": "Premium", "price_annual": "INR 7,999", "features": "4K Ultra HD, 5 devices, VIP lounge access"}
        ]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"plans": tiers})


class RecordRenewalIntentTool(BaseTool):
    @property
    def name(self) -> str:
        return "record_renewal_intent"

    @property
    def description(self) -> str:
        return "Record subscriber intention (renew now, upgrade, pause, or churn risk)."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": ["renew", "upgrade", "cancel", "considering"]}
            },
            "required": ["intent"]
        }

    async def execute(self, organization_id: str, agent_id: str, intent: str = "renew", **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"renewal_intent": intent, "recorded": True})


class RequestUpgradeTool(BaseTool):
    @property
    def name(self) -> str:
        return "request_upgrade"

    @property
    def description(self) -> str:
        return "Apply upgrade discount to renew subscriber at a higher tier."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "upgrade_to": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, upgrade_to: str = "Premium", **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"upgraded_to": upgrade_to, "discount_applied": "20% OFF"})


class RequestCancellationTool(BaseTool):
    @property
    def name(self) -> str:
        return "request_cancellation"

    @property
    def description(self) -> str:
        return "Process membership cancellation feedback and disable renewal."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"status": "CANCELLATION_RECORDED"})


class ScheduleCallbackTool(BaseTool):
    @property
    def name(self) -> str:
        return "schedule_callback"

    @property
    def description(self) -> str:
        return "Schedule retention specialist callback."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "phone_number": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"callback_scheduled": True})


class SubscriptionRenewalTemplate(BaseAgentTemplate):
    """Subscription & Membership Renewal Agent Template."""

    SUBSCRIPTION_KEYWORDS = {
        "subscription", "membership", "renew", "renewal", "plan", "upgrade", "downgrade",
        "cancel subscription", "billing", "validity", "expires", "auto renew", "tier",
        "సబ్‌స్క్రిప్షన్", "మెంబర్‌షిప్", "రెన్యూ", "ప్లాన్",
        "सब्सक्रिप्शन", "मेंबरशिप", "रिन्यू", "प्लान", "वैधता"
    }

    @property
    def template_type(self) -> str:
        return "subscription_renewal"

    @property
    def default_agent_name(self) -> str:
        return "Neha"

    @property
    def default_business_name(self) -> str:
        return "ABC Services"

    @property
    def default_persona_title(self) -> str:
        return "Subscription Assistant"

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
            "assist subscribers with upcoming plan expirations, explain renewal benefits, "
            "highlight upgrade discounts, and handle cancellation or downgrade requests politely"
        )
        rules = (
            "1. Explain current plan benefits and exact expiration dates.\n"
            "2. Offer configured loyalty renewal perks or upgrade discounts.\n"
            "3. If member insists on canceling, process the request politely without aggressive resistance."
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
            return f"{biz_name} కి స్వాగతం. మీ సబ్‌స్క్రిప్షన్ వివరాలపై నేను మీకు ఎలా సహాయపడగలను?"
        elif lang == "hi-IN":
            return f"{biz_name} में आपका स्वागत है। आपके सब्सक्रिप्शन रिन्यूअल में मैं आपकी क्या मदद कर सकती हूँ?"
        return f"Welcome to {biz_name}. How can I assist you today?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} తో మాట్లాడినందుకు ధన్యవాదాలు. మీ రోజు శుభంగా ఉండాలి!"
        elif lang == "hi-IN":
            return f"{biz_name} से जुड़ने के लिए धन्यवाद। आपका दिन शुभ हो!"
        return f"Thank you for contacting {biz_name}. Have a wonderful day!"

    def get_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(GetSubscriptionTool())
        registry.register(GetPlanDetailsTool())
        registry.register(RecordRenewalIntentTool())
        registry.register(RequestUpgradeTool())
        registry.register(RequestCancellationTool())
        registry.register(ScheduleCallbackTool())
        registry.register(RequestHumanHandoffTool())
        return registry

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        return any(k in clean for k in self.SUBSCRIPTION_KEYWORDS)

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = " ".join([m.get("content", "") for m in messages]).lower()
        return {
            "renewal_intent": "upgrade" if "upgrade" in text else ("cancel" if "cancel" in text else "renew"),
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
            "key_outcome": "Subscription renewal conversation completed" + (" (Handoff requested)" if handoff else ""),
            "handoff_status": handoff
        }
