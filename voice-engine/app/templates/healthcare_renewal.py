"""Healthcare & Insurance Renewal Agent Template."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_generic_system_prompt
from app.tools.base import BaseTool, ToolRegistry, ToolExecutionResult
from app.tools.handoff import RequestHumanHandoffTool


class GetRenewalDetailsTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_renewal_details"

    @property
    def description(self) -> str:
        return "Retrieve existing health policy coverage amount and renewal deadline."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "policy_id": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, policy_id: str = "POL-HEALTH-01", **kwargs) -> ToolExecutionResult:
        data = {
            "policy_id": policy_id,
            "coverage_sum_insured_inr": 500000,
            "expiry_date": "Next month on the 15th",
            "annual_premium_inr": 12500,
            "no_claim_bonus_percentage": 20
        }
        return ToolExecutionResult(tool_name=self.name, success=True, data=data)


class GetPlanInformationTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_plan_information"

    @property
    def description(self) -> str:
        return "Get details on health insurance plan upgrades or rider add-ons."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_type": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, plan_type: str = "Standard", **kwargs) -> ToolExecutionResult:
        riders = [
            {"name": "Critical Illness Rider", "premium_add_on_inr": 2000},
            {"name": "OPD and Pharmacy Coverage", "premium_add_on_inr": 3500}
        ]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"plan": plan_type, "available_riders": riders})


class RecordRenewalIntentTool(BaseTool):
    @property
    def name(self) -> str:
        return "record_renewal_intent"

    @property
    def description(self) -> str:
        return "Record the policyholder's intent to renew, upgrade, or switch health plan."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "policy_id": {"type": "string"},
                "intent": {"type": "string", "enum": ["renew_same_plan", "upgrade_plan", "undecided", "discontinue"]}
            },
            "required": ["intent"]
        }

    async def execute(self, organization_id: str, agent_id: str, intent: str = "renew_same_plan", **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"renewal_status": "INTENT_RECORDED", "intent": intent})


class ScheduleCallbackTool(BaseTool):
    @property
    def name(self) -> str:
        return "schedule_callback"

    @property
    def description(self) -> str:
        return "Schedule an insurance counselor call for detailed plan queries."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "phone_number": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"callback": "CONFIRMED"})


class HealthcareRenewalTemplate(BaseAgentTemplate):
    """Healthcare & Policy Renewal Agent Template."""

    HEALTHCARE_KEYWORDS = {
        "policy", "insurance", "renewal", "renew", "premium", "coverage", "sum insured",
        "cashless", "hospital", "network", "rider", "claim", "expiry", "expire",
        "పాలసీ", "ఇన్సూరెన్స్", "రెన్యూవల్", "ప్రీమియం", "కవరేజ్",
        "पॉलिसी", "बीमा", "रिन्यू", "प्रीमियम", "कवरेज", "तारीख"
    }

    @property
    def template_type(self) -> str:
        return "healthcare_renewal"

    @property
    def default_agent_name(self) -> str:
        return "Meera"

    @property
    def default_business_name(self) -> str:
        return "ABC Health Services"

    @property
    def default_persona_title(self) -> str:
        return "Renewal Assistant"

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
            "assist members with healthcare plan and insurance renewals, explain policy expiry dates, "
            "premium amounts, and coverage options in clear spoken terms"
        )
        rules = (
            "1. STRICT MEDICAL SAFETY: You are an administrative policy assistant. NEVER provide medical diagnosis, "
            "treatment advice, clinical assessments, or drug recommendations.\n"
            "2. Clarify policy dates, premium amounts, and no-claim bonus status.\n"
            "3. If member has complex claim or clinical questions, offer a human counselor handoff."
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
            return f"{biz_name} కి స్వాగతం. మీ పాలసీ రెన్యూవల్ గురించి నేను మీకు ఎలా సహాయపడగలను?"
        elif lang == "hi-IN":
            return f"{biz_name} में आपका स्वागत है। पॉलिसी रिन्यूअल के लिए मैं आपकी क्या सहायता कर सकती हूँ?"
        return f"Welcome to {biz_name}. How can I help you today?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} తో మాట్లాడినందుకు ధన్యవాదాలు. ఆరోగ్యంగా ఉండండి!"
        elif lang == "hi-IN":
            return f"{biz_name} में कॉल करने के लिए धन्यवाद। स्वस्थ रहें!"
        return f"Thank you for contacting {biz_name}. Wishing you good health and a great day!"

    def get_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(GetRenewalDetailsTool())
        registry.register(GetPlanInformationTool())
        registry.register(RecordRenewalIntentTool())
        registry.register(ScheduleCallbackTool())
        registry.register(RequestHumanHandoffTool())
        return registry

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        return any(k in clean for k in self.HEALTHCARE_KEYWORDS)

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = " ".join([m.get("content", "") for m in messages]).lower()
        return {
            "intent": "renew" if "renew" in text else "inquiry",
            "upgrade_interested": any(w in text for w in ["upgrade", "rider", "increase", "higher"]),
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
            "key_outcome": "Health policy renewal discussed" + (" (Handoff requested)" if handoff else ""),
            "handoff_status": handoff
        }
