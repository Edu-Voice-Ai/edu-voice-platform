"""Ecommerce Cart Recovery Agent Template."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_generic_system_prompt
from app.tools.base import BaseTool, ToolRegistry, ToolExecutionResult
from app.tools.handoff import RequestHumanHandoffTool


class GetCartTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_cart"

    @property
    def description(self) -> str:
        return "Retrieve the list of items in the customer's pending shopping cart."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cart_id": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, cart_id: str = "CART-99", **kwargs) -> ToolExecutionResult:
        items = [
            {"item": "Wireless Noise-Canceling Headphones", "qty": 1, "price_inr": 2999},
            {"item": "Fast USB-C Charging Adapter", "qty": 1, "price_inr": 899}
        ]
        return ToolExecutionResult(tool_name=self.name, success=True, data={"cart_id": cart_id, "items": items, "total_inr": 3898})


class GetProductDetailsTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_product_details"

    @property
    def description(self) -> str:
        return "Get warranty, return policy, and technical specs for cart products."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "item_name": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, item_name: str = "", **kwargs) -> ToolExecutionResult:
        info = {
            "item": item_name,
            "warranty": "1 Year Manufacturer Warranty",
            "return_policy": "7-day easy replacement",
            "delivery_speed": "2 business days with free delivery"
        }
        return ToolExecutionResult(tool_name=self.name, success=True, data=info)


class CheckProductAvailabilityTool(BaseTool):
    @property
    def name(self) -> str:
        return "check_product_availability"

    @property
    def description(self) -> str:
        return "Confirm stock availability for cart items."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "item_name": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, item_name: str = "", **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"item": item_name, "in_stock": True, "units_available": 12})


class CapturePurchaseIntentTool(BaseTool):
    @property
    def name(self) -> str:
        return "capture_purchase_intent"

    @property
    def description(self) -> str:
        return "Record shopper's intention (e.g. buying now, waiting for coupon, or removing item)."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": ["complete_purchase", "price_concern", "payment_failed", "cancelled"]}
            },
            "required": ["intent"]
        }

    async def execute(self, organization_id: str, agent_id: str, intent: str = "complete_purchase", **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"intent": intent, "discount_coupon_sent": True})


class RequestFollowupTool(BaseTool):
    @property
    def name(self) -> str:
        return "request_followup"

    @property
    def description(self) -> str:
        return "Trigger an SMS or WhatsApp checkout link to the customer's phone."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "phone_number": {"type": "string"}
            }
        }

    async def execute(self, organization_id: str, agent_id: str, **kwargs) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=self.name, success=True, data={"status": "CHECKOUT_LINK_SENT"})


class EcommerceCartTemplate(BaseAgentTemplate):
    """Ecommerce Cart Recovery Agent Template."""

    ECOMMERCE_KEYWORDS = {
        "cart", "order", "item", "product", "checkout", "discount", "coupon", "offer",
        "shipping", "delivery", "price", "warranty", "return", "payment", "buy",
        "కార్ట్", "ఆర్డర్", "డిస్కౌంట్", "ధర", "డెలివరీ",
        "कार्ट", "ऑर्डर", "डिस्काउंट", "कूपन", "सामान", "डिलीवरी"
    }

    @property
    def template_type(self) -> str:
        return "ecommerce_cart"

    @property
    def default_agent_name(self) -> str:
        return "Kavya"

    @property
    def default_business_name(self) -> str:
        return "ABC Store"

    @property
    def default_persona_title(self) -> str:
        return "Shopping Assistant"

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
            "help shoppers review products left in their online cart, answer questions about "
            "shipping, returns, and warranties, and assist with completing their checkout smoothly"
        )
        rules = (
            "1. Be friendly, helpful, and non-intrusive.\n"
            "2. Explain cart total, return policy, and warranty clearly.\n"
            "3. Offer to send a direct checkout link with any eligible discount."
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
            return f"నమస్తే! {biz_name} కి స్వాగతం. మీ కార్ట్ వివరాలపై నేను మీకు ఎలా సహాయపడగలను?"
        elif lang == "hi-IN":
            return f"नमस्ते! {biz_name} में आपका स्वागत है। आपके कार्ट के बारे में मैं आपकी क्या मदद कर सकती हूँ?"
        return f"Hi, welcome to {biz_name}. How can I help you today?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} ని సందర్శించినందుకు ధన్యవాదాలు. హ్యాపీ షాపింగ్!"
        elif lang == "hi-IN":
            return f"{biz_name} से जुड़ने के लिए धन्यवाद। हैप्पी शॉपिंग!"
        return f"Thank you for reaching out to {biz_name}. Happy shopping and have a great day!"

    def get_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(GetCartTool())
        registry.register(GetProductDetailsTool())
        registry.register(CheckProductAvailabilityTool())
        registry.register(CapturePurchaseIntentTool())
        registry.register(RequestFollowupTool())
        registry.register(RequestHumanHandoffTool())
        return registry

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        return any(k in clean for k in self.ECOMMERCE_KEYWORDS)

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        text = " ".join([m.get("content", "") for m in messages]).lower()
        return {
            "intent": "checkout" if any(w in text for w in ["buy", "purchase", "link", "complete"]) else "inquiry",
            "coupon_requested": any(w in text for w in ["coupon", "discount", "offer", "deal"]),
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
            "key_outcome": "Cart recovery inquiry resolved" + (" (Handoff requested)" if handoff else ""),
            "handoff_status": handoff
        }
