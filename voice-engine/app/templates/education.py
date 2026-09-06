"""Education Agent Template preserving existing admission baseline behavior."""
from typing import Dict, Any, List, Optional
from app.templates.base import BaseAgentTemplate
from app.conversation.prompts import build_admission_system_prompt
from app.tools.base import ToolRegistry
from app.tools.admission import (
    GetCoursesTool,
    GetFeeTool,
    GetEligibilityTool,
    GetAdmissionDatesTool,
    GetDocumentsRequiredTool,
    GetHostelInformationTool,
    GetCampusInformationTool,
    CreateLeadTool,
)
from app.tools.handoff import RequestHumanHandoffTool
from app.intelligence.lead_extraction import LeadExtractor
from app.intelligence.summary import CallSummarizer


class EducationTemplate(BaseAgentTemplate):
    """Education & University Admissions Agent Template (Apex University / Priya)."""

    ADMISSION_KEYWORDS = {
        "fee", "fees", "course", "courses", "cse", "csc", "ece", "hostel", "dates", "eligibility",
        "admission", "admissions", "placement", "placements", "campus", "scholarship", "btech", "mtech",
        "b.tech", "m.tech", "mba", "bba", "apply", "how to apply", "offer", "offering", "programs",
        "కాలేజ్", "ఫీజు", "ఎప్పుడు", "ఎంత", "కోర్సులు", "కోర్స్", "కోర్సు", "వివరాలు", "డీటెయిల్స్",
        "ఎలా", "ఉన్నాయి", "ఉంది", "చెప్పండి", "ఫీస్", "कब", "कितना", "कोर्स", "एडमिशन", "बताइए", "क्या"
    }

    @property
    def template_type(self) -> str:
        return "education"

    @property
    def default_agent_name(self) -> str:
        return "Priya"

    @property
    def default_business_name(self) -> str:
        return "Apex University"

    @property
    def default_persona_title(self) -> str:
        return "Admission Counselor"

    def get_system_prompt(
        self,
        session: Any,
        verified_context: str = "",
        lang: str = "en-IN"
    ) -> str:
        agent_name = getattr(session, "agent_name", None) or self.default_agent_name
        biz_name = getattr(session, "business_name", None) or getattr(session, "institution_name", self.default_business_name)
        active_lang = lang or getattr(session, "preferred_language", None) or getattr(session, "language", "en-IN")
        
        return build_admission_system_prompt(
            institution_name=biz_name,
            agent_name=agent_name,
            language_hint=active_lang,
            preferred_language=active_lang,
            verified_context=verified_context
        )

    def get_greeting(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or getattr(session, "institution_name", self.default_business_name)
        return f"Welcome to {biz_name}. Which language do you prefer? English, Hindi, or Telugu?"

    def get_goodbye(self, session: Any, lang: str = "en-IN") -> str:
        biz_name = getattr(session, "business_name", None) or getattr(session, "institution_name", self.default_business_name)
        if lang == "te-IN":
            return f"మాతో మాట్లాడినందుకు ధన్యవాదాలు. మీకు ఏవైనా సందేహాలు ఉంటే మళ్ళీ కాల్ చేయండి. All the best!"
        elif lang == "hi-IN":
            return f"बात करने के लिए धन्यवाद। यदि आपके कोई और प्रश्न हों, तो कृपया पुनः कॉल करें। शुभ दिन!"
        return f"Thank you for reaching out to {biz_name}. Have a wonderful day, and all the best!"

    def get_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(GetCoursesTool())
        registry.register(GetFeeTool())
        registry.register(GetEligibilityTool())
        registry.register(GetAdmissionDatesTool())
        registry.register(GetDocumentsRequiredTool())
        registry.register(GetHostelInformationTool())
        registry.register(GetCampusInformationTool())
        registry.register(CreateLeadTool())
        registry.register(RequestHumanHandoffTool())
        return registry

    def is_domain_query(self, user_text: str) -> bool:
        clean = user_text.lower().strip()
        return any(q in clean for q in self.ADMISSION_KEYWORDS)

    def extract_lead(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        lead = LeadExtractor.extract_from_messages(messages)
        return lead.model_dump()

    def generate_summary(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        duration_sec: float = 0.0,
        handoff: bool = False
    ) -> Dict[str, Any]:
        summary = CallSummarizer.generate_summary(
            session_id=session_id,
            messages=messages,
            duration_sec=duration_sec,
            handoff_requested=handoff
        )
        return summary.model_dump()
