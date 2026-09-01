"""Validated Pydantic Lead extraction schema and rule/LLM parser."""
import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from app.session.state import SessionState
from app.core.logging import get_logger

logger = get_logger("intelligence.leads")


class LeadData(BaseModel):
    """Validated structured prospect lead information."""
    name: Optional[str] = None
    phone: Optional[str] = None
    course: Optional[str] = None
    qualification: Optional[str] = None
    interest_level: str = Field(default="medium", pattern="^(low|medium|high)$")
    follow_up_required: bool = False
    callback_requested: bool = False
    preferred_time: Optional[str] = None
    raw_notes: Optional[str] = None


class LeadExtractor:
    """Extracts and validates structured admission lead data from dialogue history."""

    PHONE_REGEX = re.compile(r"\b(?:(?:\+91|91|0)?[6-9]\d{9})\b")

    @classmethod
    def extract_from_messages(cls, messages: List[Dict[str, Any]]) -> LeadData:
        """Extract lead fields using heuristic pattern matching and text parsing."""
        full_text = " ".join([m.get("content", "") for m in messages])
        
        # Phone extraction
        phone_match = cls.PHONE_REGEX.search(full_text)
        phone = phone_match.group(0) if phone_match else None

        # Course extraction
        course = None
        courses = ["btech cse", "cse", "btech ece", "ece", "mechanical", "mba", "bba", "mtech"]
        for c in courses:
            if c in full_text.lower():
                course = c.upper()
                break

        # Callback / Interest
        callback = any(w in full_text.lower() for w in ["call back", "callback", "call me", "reach me", "contact me"])
        interest = "high" if (phone and course) else ("medium" if (phone or course) else "low")

        lead = LeadData(
            name=None,
            phone=phone,
            course=course,
            qualification=None,
            interest_level=interest,
            follow_up_required=bool(phone or callback),
            callback_requested=callback,
            raw_notes=f"Auto-extracted from session with {len(messages)} messages"
        )
        return lead
