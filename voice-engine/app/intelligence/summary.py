"""Call summarization model and extractor."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class CallSummary(BaseModel):
    """Structured summary for a completed voice call."""
    session_id: str
    total_turns: int
    duration_seconds: float
    topics_discussed: List[str] = Field(default_factory=list)
    key_outcome: str
    handoff_status: bool = False
    follow_up_recommended: bool = False


class CallSummarizer:
    """Generates structured call summaries from conversation logs."""

    @staticmethod
    def generate_summary(session_id: str, messages: List[Dict[str, Any]], duration_sec: float = 0.0, handoff_requested: bool = False) -> CallSummary:
        text_corpus = " ".join([m.get("content", "") for m in messages]).lower()
        
        topics = []
        if "fee" in text_corpus or "tuition" in text_corpus:
            topics.append("Fee Structure")
        if "admission" in text_corpus or "eligibility" in text_corpus:
            topics.append("Admission Eligibility")
        if "hostel" in text_corpus:
            topics.append("Hostel Amenities")
        if "course" in text_corpus or "cse" in text_corpus:
            topics.append("Course Selection")

        if not topics:
            topics.append("General Inquiry")

        outcome = "Caller inquired about " + ", ".join(topics)
        if handoff_requested:
            outcome += " (Human counselor handoff initiated)"

        return CallSummary(
            session_id=session_id,
            total_turns=len([m for m in messages if m.get("role") == "user"]),
            duration_seconds=duration_sec,
            topics_discussed=topics,
            key_outcome=outcome,
            handoff_status=handoff_requested,
            follow_up_recommended=True if topics else False
        )
