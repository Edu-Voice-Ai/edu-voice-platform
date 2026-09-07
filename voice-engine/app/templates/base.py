"""Base classes and contracts for multi-industry Agent Templates."""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.tools.base import ToolRegistry


class BusinessConfiguration(BaseModel):
    """Extensible business metadata and industry variables."""
    business_name: str = "Apex University"
    industry: str = "education"
    operating_hours: Optional[str] = None
    contact_phone: Optional[str] = None
    custom_variables: Dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """Comprehensive agent configuration model."""
    agent_id: str = "agent_default"
    organization_id: str = "org_default"
    template_type: str = "education"
    agent_name: str = "Priya"
    business_name: str = "Apex University"
    language: str = "en-IN"
    supported_languages: List[str] = Field(default_factory=lambda: ["en-IN", "hi-IN", "te-IN"])
    system_prompt: Optional[str] = None
    greeting_message: Optional[str] = None
    goodbye_message: Optional[str] = None
    tools: List[str] = Field(default_factory=list)
    knowledge_sources: List[str] = Field(default_factory=list)
    business_configuration: Dict[str, Any] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=dict)


class BaseAgentTemplate(ABC):
    """Abstract Base Class for industry-specific Agent Templates.
    
    Templates supply business personality, prompts, tools, domain keywords, and extraction
    without touching the realtime Speech-to-Speech audio pipeline.
    """
    
    @property
    @abstractmethod
    def template_type(self) -> str:
        """Identifier for this template category (e.g. 'education', 'appointment_booking')."""
        pass

    @property
    @abstractmethod
    def default_agent_name(self) -> str:
        """Default agent persona name."""
        pass

    @property
    @abstractmethod
    def default_business_name(self) -> str:
        """Default company or institution name."""
        pass

    @property
    @abstractmethod
    def default_persona_title(self) -> str:
        """Human-facing role title (e.g. 'Admissions Counselor', 'Appointment Assistant')."""
        pass

    @abstractmethod
    def get_system_prompt(
        self,
        session: Any,
        verified_context: str = "",
        lang: str = "en-IN"
    ) -> str:
        """Build the complete grounded system prompt for LLM generation."""
        pass

    @abstractmethod
    def get_greeting(self, session: Any, lang: str = "en-IN") -> str:
        """Initial greeting spoken by the agent when a call starts."""
        pass

    @abstractmethod
    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        """Farewell message spoken when user explicitly exits."""
        pass

    @abstractmethod
    def get_tool_registry(self) -> ToolRegistry:
        """Instantiate and return the domain-scoped tool registry."""
        pass

    @abstractmethod
    def is_domain_query(self, user_text: str) -> bool:
        """Check if user text contains industry-specific domain inquiry keywords."""
        pass

    def get_fast_router_rules(self, session: Any, user_text: str) -> Optional[str]:
        """Optional deterministic fast path resolution for frequent FAQs (returns response text or None)."""
        return None

    @abstractmethod
    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract structured domain lead/data from dialogue history."""
        pass

    @abstractmethod
    def generate_summary(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        duration_sec: float = 0.0,
        handoff: bool = False
    ) -> Dict[str, Any]:
        """Produce structured call summary and outcome."""
        pass
