"""Semantic Query Normalizer & Intent Classifier for Cross-Language RAG Grounding."""
import re
from enum import Enum
from typing import Set, Tuple, List, Optional
from pydantic import BaseModel
from app.core.logging import get_logger

logger = get_logger("rag.normalizer")


class SemanticIntent(str, Enum):
    LIST_AVAILABLE_COURSES = "LIST_AVAILABLE_COURSES"
    FEES_INQUIRY = "FEES_INQUIRY"
    ELIGIBILITY_INQUIRY = "ELIGIBILITY_INQUIRY"
    ADMISSION_DATES_INQUIRY = "ADMISSION_DATES_INQUIRY"
    HOSTEL_INQUIRY = "HOSTEL_INQUIRY"
    CAMPUS_INQUIRY = "CAMPUS_INQUIRY"
    GENERAL_INQUIRY = "GENERAL_INQUIRY"


class NormalizedQuery(BaseModel):
    intent: SemanticIntent
    canonical_keywords: List[str]
    courses_mentioned: List[str]
    raw_query: str


class SemanticQueryNormalizer:
    """Normalizes multilingual user speech queries (Telugu, Hindi, English) to canonical semantic intents."""

    # Course Keywords (strict course identifiers only, not general inquiry terms)
    COURSE_MARKERS = {
        "course", "courses", "కోర్సులు", "కోర్సు", "కోర్స్", "కోర్సులున్నాయి", "కోర్సులున్నాయా",
        "కోర్సుల", "కోర్సులేంటి", "కోర్సులేమిటి", "కోర్సులు ఏమున్నాయి", "ఏమున్నాయి", "ఏమి కోర్సులు",
        "कोर्स", "कोर्सेस", "पाठ्यक्रम", "programs", "program", "degrees", "degree",
        "streams", "branch", "branches", "offer", "offering", "offers"
    }

    # Fee Keywords
    FEE_MARKERS = {
        "fee", "fees", "tuition", "cost", "charge", "charges", "price", "annual",
        "ఫీజు", "ఫీజులు", "ఫీజ్", "ఖర్చు", "entha", "feesentha",
        "फीस", "फी", "खर्च", "kitna", "kitni", "paisa", "rupees"
    }

    # Eligibility Keywords
    ELIGIBILITY_MARKERS = {
        "eligibility", "eligible", "criteria", "cutoff", "qualification",
        "requirements", "అర్హత", "ఎలిజిబిలిటీ",
        "योग्यता", "एलिजिबिलिटी", "पात्रता"
    }

    # Date Keywords
    DATE_MARKERS = {
        "date", "dates", "when", "schedule", "deadline", "last date", "start date",
        "open", "close", "session", "academic", "eppudu", "kab",
        "ఎప్పుడు", "తేదీ", "తేదీలు", "స్టార్ట్", "లాస్ట్ డేట్",
        "कब", "तारीख", "तारीखें", "शुरू", "अंतिम तारीख"
    }

    # Hostel Keywords
    HOSTEL_MARKERS = {
        "hostel", "hostels", "accommodation", "room", "rooms", "stay", "mess",
        "హాస్టల్", "హాస్టల్స్", "రూమ్", "భోజనం", "వసతి", "హాస్టల్ వివరాలు", "హాస్టల్ ఫెసిలిటీ",
        "పార్సల్",  # Sarvam STT frequent telephony homophone for హాస్టల్ (e.g. "పార్సల్ ఫెసిలిటీ")
        "हॉस्टल", "कमरा", "रहना"
    }

    # Specific Course Identifiers
    CSE_IDENTIFIERS = {"cse", "csc", "computer", "computers", "software", "సిఎస్ఇ", "సిఎస్సి", "సిఎస్సీ", "కంప్యూటర్", "सीएसई", "कंप्यूटर"}
    ECE_IDENTIFIERS = {"ece", "electronics", "communication", "ఈసిఈ", "ఈసీఈ", "ఎలక్ట్రానిక్స్", "ईसीई", "इलेक्ट्रॉनिक्स"}
    MECH_IDENTIFIERS = {"mech", "mechanical", "మెకానికల్", "मैकेनिकल"}

    @classmethod
    def normalize(cls, query_text: str) -> NormalizedQuery:
        """Classify intent and generate canonical search terms for authoritative RAG retrieval."""
        text_lower = query_text.lower().strip()
        words = set(re.findall(r'[\w\u0900-\u097F\u0C00-\u0C7F]+', text_lower))

        # Detect specific course mentions
        courses_mentioned = []
        if words & cls.CSE_IDENTIFIERS or any(k in text_lower for k in ["cse", "csc", "computer science", "కంప్యూటర్", "సిఎస్ఇ", "సిఎస్సి"]):
            courses_mentioned.append("CSE")
        if words & cls.ECE_IDENTIFIERS or any(k in text_lower for k in ["ece", "electronics", "ఎలక్ట్రానిక్స్", "ఈసిఈ", "ఈసీఈ"]):
            courses_mentioned.append("ECE")
        if words & cls.MECH_IDENTIFIERS or any(k in text_lower for k in ["mech", "mechanical", "మెకానికల్"]):
            courses_mentioned.append("MECH")

        canonical_keywords = []

        # 1. Hostel Inquiry check (checked before general fee to catch 'hostel fee')
        if words & cls.HOSTEL_MARKERS or any(k in text_lower for k in ["hostel", "హాస్టల్", "हॉस्टल"]):
            intent = SemanticIntent.HOSTEL_INQUIRY
            canonical_keywords = ["hostel", "facilities", "ac", "non-ac", "fee", "food"]
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text
            )

        # 2. Admission Dates Inquiry check
        if words & cls.DATE_MARKERS or any(k in text_lower for k in ["date", "dates", "deadline", "when", "eppudu", "kab", "ఎప్పుడు", "कब", "last date", "start date", "లాస్ట్ డేట్"]):
            intent = SemanticIntent.ADMISSION_DATES_INQUIRY
            canonical_keywords = ["admission", "dates", "2026", "session", "open", "close", "deadline"]
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text
            )

        # 3. Eligibility Inquiry check
        if words & cls.ELIGIBILITY_MARKERS or any(k in text_lower for k in ["eligibility", "eligible", "అర్హత", "योग्यता"]):
            intent = SemanticIntent.ELIGIBILITY_INQUIRY
            canonical_keywords = ["eligibility", "criteria", "pcm", "12th", "jee", "eapcet", "aggregate"]
            if courses_mentioned:
                canonical_keywords.extend(courses_mentioned)
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text
            )

        # 4. Fee Inquiry check
        if words & cls.FEE_MARKERS or any(k in text_lower for k in ["fee", "fees", "ఫీజు", "ఫీజ్", "ఫీజులు", "फीस", "फी"]):
            intent = SemanticIntent.FEES_INQUIRY
            canonical_keywords = ["fee", "fees", "tuition", "cost", "inr", "annual"]
            if courses_mentioned:
                canonical_keywords.extend(courses_mentioned)
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text
            )

        # 5. Course List / Overview check
        if words & cls.COURSE_MARKERS or any(k in text_lower for k in ["course", "courses", "కోర్సులు", "కోర్సు", "कोर्स", "कोर्सेस", "programs"]):
            intent = SemanticIntent.LIST_AVAILABLE_COURSES
            canonical_keywords = ["courses", "btech", "cse", "ece", "computer science", "engineering", "programs"]
            if courses_mentioned:
                canonical_keywords.extend(courses_mentioned)
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text
            )

        # Default / Specific Course check
        if courses_mentioned and any(k in text_lower for k in ["details", "about", "వివరాలు", "గురించి"]):
            intent = SemanticIntent.LIST_AVAILABLE_COURSES
            canonical_keywords = ["courses", "btech", "fees"] + courses_mentioned
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text
            )

        # General inquiry fallback
        return NormalizedQuery(
            intent=SemanticIntent.GENERAL_INQUIRY,
            canonical_keywords=list(words),
            courses_mentioned=[],
            raw_query=query_text
        )
