"""Custom Agent Template for Arbitrary Injected Business Configurations."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_generic_system_prompt
from app.tools.base import ToolRegistry
from app.tools.handoff import RequestHumanHandoffTool


class CustomTemplate(BaseAgentTemplate):
    """Custom & Extensible Agent Template.
    
    Accepts arbitrary business configuration, dynamic system prompts, custom greetings,
    and injected tool definitions without modifying core Voice Engine code.
    """

    def __init__(
        self,
        custom_system_prompt: Optional[str] = None,
        custom_greeting: Optional[str] = None,
        custom_goodbye: Optional[str] = None,
        custom_agent_name: str = "Assistant",
        custom_business_name: str = "Custom Business",
        custom_persona_title: str = "Customer Assistant",
        custom_tasks: str = "assist callers with general inquiries, answer business questions, and provide help",
        custom_keywords: Optional[List[str]] = None,
        custom_tools: Optional[ToolRegistry] = None
    ):
        self._custom_system_prompt = custom_system_prompt
        self._custom_greeting = custom_greeting
        self._custom_goodbye = custom_goodbye
        self._agent_name = custom_agent_name
        self._business_name = custom_business_name
        self._persona_title = custom_persona_title
        self._tasks = custom_tasks
        self._keywords = set(custom_keywords) if custom_keywords else set()
        self._tools = custom_tools or ToolRegistry()
        if not self._tools.get_tool("request_human_handoff"):
            self._tools.register(RequestHumanHandoffTool())

    @property
    def template_type(self) -> str:
        return "custom"

    @property
    def default_agent_name(self) -> str:
        return self._agent_name

    @property
    def default_business_name(self) -> str:
        return self._business_name

    @property
    def default_persona_title(self) -> str:
        return self._persona_title

    def get_system_prompt(
        self,
        session: Any,
        verified_context: str = "",
        lang: str = "en-IN"
    ) -> str:
        # 1. Direct prompt override configured on session or template
        override = getattr(session, "system_prompt", None) or self._custom_system_prompt
        if override:
            context_section = f"\nVERIFIED BUSINESS KNOWLEDGE:\n{verified_context}\n" if verified_context else ""
            return f"{override}\n{context_section}".strip()

        agent_name = getattr(session, "agent_name", None) or self.default_agent_name
        biz_name = getattr(session, "business_name", None) or self.default_business_name
        active_lang = lang or getattr(session, "preferred_language", None) or getattr(session, "language", "en-IN")

        return build_generic_system_prompt(
            business_name=biz_name,
            agent_name=agent_name,
            role_persona=self.default_persona_title,
            industry_tasks=self._tasks,
            language_hint=active_lang,
            preferred_language=active_lang,
            verified_context=verified_context
        )

    def get_greeting(self, session: Any, lang: str = "en-IN") -> str:
        greeting_override = getattr(session, "greeting_message", None) or self._custom_greeting
        if greeting_override:
            return greeting_override

        biz_name = getattr(session, "business_name", None) or self.default_business_name
        if lang == "te-IN":
            return f"{biz_name} కి స్వాగతం. నేను మీకు ఎలా సహాయపడగలను?"
        elif lang == "hi-IN":
            return f"{biz_name} में आपका स्वागत है। मैं आपकी क्या सहायता कर सकता हूँ?"
        return f"Welcome to {biz_name}. How can I assist you today?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        goodbye_override = getattr(session, "goodbye_message", None) or self._custom_goodbye
        if goodbye_override:
            return goodbye_override

        biz_name = getattr(session, "business_name", None) or self.default_business_name
        return f"Thank you for reaching out to {biz_name}. Have a wonderful day!"

    def get_tool_registry(self) -> ToolRegistry:
        return self._tools

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        if self._keywords:
            return any(k in clean for k in self._keywords)
        # Default: treated as domain query if 2+ words are spoken
        return len(clean.split()) >= 2

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "custom_lead": True,
            "message_count": len(messages),
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
            "key_outcome": "Custom agent conversation concluded" + (" (Handoff requested)" if handoff else ""),
            "handoff_status": handoff
        }
