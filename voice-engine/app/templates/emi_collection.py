"""EMI & Payment Collection Agent Template."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_generic_system_prompt
from app.tools.base import BaseTool, ToolRegistry, ToolExecutionResult
from app.tools.handoff import RequestHumanHandoffTool


class GetAccountSummaryTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_account_summary"

    @property
    def description(self) -> str:
        return "Retrieve general loan/account status and tenure information (sanitized mock)."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, account_id: str = "ACC-1001", **kwargs) -> ToolExecutionResult:
        summary = {
            "account_id": account_id,
            "loan_type": "Personal Loan",
            "total_tenure_months": 24,
            "emis_paid": 14,
            "emis_remaining": 10
        }
        return ToolExecutionResult(tool_name=self.name, success=True, data=summary)


class GetDueInformationTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_due_information"

    @property
    def description(self) -> str:
        return "Retrieve current month EMI amount and official due date."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, account_id: str = "ACC-1001", **kwargs) -> ToolExecutionResult:
        due = {
            "due_amount_inr": 8500,
            "due_date": "10th of this month",
            "grace_period_days": 3,
            "status": "DUE"
        }
        return ToolExecutionResult(tool_name=self.name, success=True, data=due)


class RecordPaymentIntentTool(BaseTool):
    @property
    def name(self) -> str:
        return "record_payment_intent"

    @property
    def description(self) -> str:
        return "Record customer's stated intention regarding EMI clearance."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": ["pay_now", "pay_later", "dispute", "hardship"]}
            },
            "required": ["intent"]
        }

    async def execute(self, organization_id: str, agent_id: str, intent: str = "pay_later", **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"intent_recorded": intent, "acknowledged": True})


class RecordPromiseToPayTool(BaseTool):
    @property
    def name(self) -> str:
        return "record_promise_to_pay"

    @property
    def description(self) -> str:
        return "Register a formal Promise-to-Pay (PTP) date agreed with the customer."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ptp_date": {"type": "string", "description": "Agreed payment date YYYY-MM-DD"},
                "amount": {"type": "number"}
            },
            "required": ["ptp_date"]
        }

    async def execute(self, organization_id: str, agent_id: str, ptp_date: str = "", **kwargs) -> ToolExecutionResult:
        ptp_id = f"PTP-{ptp_date[-5:].replace('-', '')}"
        return ToolExecutionResult(tool_name=self.name, success=True, data={"ptp_id": ptp_id, "status": "CONFIRMED", "date": ptp_date})


class RequestCallbackTool(BaseTool):
    @property
    def name(self) -> str:
        return "request_callback"

    @property
    def description(self) -> str:
        return "Schedule an account manager or settlement officer callback."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"callback_status": "REQUESTED"})


class EMICollectionTemplate(BaseAgentTemplate):
    """EMI & Payment Collection Agent Template."""

    EMI_KEYWORDS = {
        "emi", "loan", "payment", "due", "overdue", "installment", "penalty", "clearance",
        "promise to pay", "ptp", "statement", "balance", "bank", "account",
        "ఈఎంఐ", "చెల్లింపు", "బకాయి", "లోన్", "డ్యూ",
        "ईएमआई", "लोन", "किश्त", "पेमेंट", "बकाया", "तारीख"
    }

    @property
    def template_type(self) -> str:
        return "emi_collection"

    @property
    def default_agent_name(self) -> str:
        return "Arjun"

    @property
    def default_business_name(self) -> str:
        return "ABC Finance"

    @property
    def default_persona_title(self) -> str:
        return "Payment Assistant"

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
            "help borrowers understand their upcoming or overdue EMI amounts, due dates, "
            "and record payment commitments or promise-to-pay dates in a polite and respectful manner"
        )
        rules = (
            "1. Always remain courteous, empathetic, and professional. Never threaten or use aggressive language.\n"
            "2. Explain the outstanding amount and due date clearly.\n"
            "3. Ask when the customer can make the payment and record the exact promise-to-pay date."
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
        agent_name = getattr(session, "agent_name", None) or self.default_agent_name
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"నమస్కారం, నేను {biz_name} నుండి {agent_name} ని. నేను మీకు ఎలా సహాయపడగలను?"
        elif lang == "hi-IN":
            return f"नमस्ते, मैं {biz_name} से {agent_name} बोल रहा हूँ। मैं आपकी क्या सहायता कर सकता हूँ?"
        return f"Hello, this is {agent_name} from {biz_name}. How can I assist you today?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} కి కాల్ చేసినందుకు ధన్యవాదాలు. మీ రోజు శుభంగా ఉండాలి!"
        elif lang == "hi-IN":
            return f"{biz_name} से बात करने के लिए धन्यवाद। आपका दिन शुभ हो!"
        return f"Thank you for your time with {biz_name}. Have a great day!"

    def get_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(GetAccountSummaryTool())
        registry.register(GetDueInformationTool())
        registry.register(RecordPaymentIntentTool())
        registry.register(RecordPromiseToPayTool())
        registry.register(RequestCallbackTool())
        registry.register(RequestHumanHandoffTool())
        return registry

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        return any(k in clean for k in self.EMI_KEYWORDS)

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = " ".join([m.get("content", "") for m in messages]).lower()
        return {
            "commitment_made": any(w in text for w in ["pay", "tomorrow", "next week", "clearing"]),
            "dispute_raised": any(w in text for w in ["dispute", "wrong", "issue", "already paid"]),
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
            "key_outcome": "Payment reminder discussed" + (" (Handoff requested)" if handoff else ""),
            "handoff_status": handoff
        }
