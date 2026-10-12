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
    fee_type: str = "general"


class SemanticQueryNormalizer:
    """Normalizes multilingual user speech queries (Telugu, Hindi, English) to canonical semantic intents."""

    # Course Keywords (strict course identifiers only, not general inquiry terms)
    COURSE_MARKERS = {
        "course", "courses", "కోర్సులు", "కోర్సు", "కోర్స్", "కోర్సులున్నాయి", "కోర్సులున్నాయా",
        "కోర్సుల", "కోర్సులేంటి", "కోర్సులేమిటి",
        "कोर्स", "कोर्सेस", "पाठ्यक्रम", "programs", "program", "degrees", "degree",
        "streams", "branch", "branches", "offer", "offering", "offers"
    }

    # Fee Keywords (single words)
    FEE_MARKERS = {
        "fee", "fees", "tuition", "cost", "charge", "charges", "price", "annual", "pricing", "much",
        "ఫీజు", "ఫీజులు", "ఫీజ్", "ఖర్చు", "ఖర్చెంత", "ఫీజెంత", "ఎంత", "ఎంతవుతుంది", "ఎంతవుద్ది",
        "entha", "yentha", "karchu", "kharchu", "feesentha", "fizu", "feezu", "mottham",
        "फीस", "फी", "खर्च", "शुल्क", "लागत", "कुल", "kitna", "kitni", "kitne", "paisa", "rupees", "daakhila"
    }

    # Fee Multi-Word Phrases
    FEE_PHRASES = [
        "how much", "what is the fee", "what is fee", "what are the fees", "how much is",
        "total cost", "total fee", "total fees", "tuition fee", "tuition fees",
        "admission fee", "admission fees", "hostel fee", "hostel fees", "one time fee", "onetime fee",
        "overall cost", "full fee", "full cost",
        # Telugu / Tenglish phrases
        "ఫీజు ఎంత", "ఎంత ఫీజు", "ఖర్చు ఎంత", "ఎంత ఖర్చు", "ఫీజ్ ఎంత", "ఎంత అవుతుంది", "ఎంత అవుద్ది",
        "మొత్తం ఎంత", "మొత్తం ఖర్చు", "మొత్తం ఫీజు", "టోటల్ ఎంత", "టోటల్ ఖర్చు",
        "fee entha", "fees entha", "karchu entha", "kharchu entha", "yentha fee", "entha fee",
        "admission fee entha", "hostel fee entha", "total cost entha", "total fee entha",
        # Hindi / Hinglish phrases
        "फीस कितनी", "कितनी फीस", "कितना खर्च", "कुल फीस", "कुल लागत", "दाखिला फीस",
        "kitni fees", "kitna fee", "kitna kharch", "kul fees", "kul kharch"
    ]

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
        "హాస్టల్", "హాస్టల్స్", "రూమ్", "భోజనం",
        "हॉस्टल", "कमरा", "रहना"
    }

    # Specific Course Identifiers
    CSE_IDENTIFIERS = {"cse", "csc", "computer", "computers", "software", "సిఎస్ఇ", "సిఎస్సి", "సిఎస్సీ", "కంప్యూటర్", "सीएसई", "कंप्यूटर"}
    ECE_IDENTIFIERS = {"ece", "electronics", "communication", "ఈసిఈ", "ఎలక్ట్రానిక్స్", "ईसीई", "इलेक्ट्रॉनिक्स"}
    MECH_IDENTIFIERS = {"mech", "mechanical", "మెకానికల్", "मैकेनिकल"}

    @classmethod
    def detect_fee_type(cls, text_lower: str) -> str:
        """Classify fee subcategory: hostel, admission, total, tuition, or general."""
        if any(k in text_lower for k in ["hostel", "హాస్టల్", "हॉस्टल", "mess", "accommodation"]):
            return "hostel"
        if any(k in text_lower for k in [
            "admission fee", "admission charge", "admission cost", "one time", "onetime",
            "అడ్మిషన్ ఫీజు", "అడ్మిషన్", "దాఖిలా", "दाखिला फीस", "दाखिला शुल्क", "प्रवेश शुल्क"
        ]):
            return "admission"
        if any(k in text_lower for k in [
            "total cost", "total fee", "total fees", "overall cost", "full fee", "full cost",
            "4 year", "4 years", "four year", "4-year",
            "మొత్తం ఖర్చు", "మొత్తం ఫీజు", "మొత్తం ఎంత", "టోటల్ ఖర్చు", "టోటల్ ఫీజు", "మొత్తం", "టోటల్",
            "कुल फीस", "कुल लागत", "कुल खर्च", "पूरा खर्च", "कुल"
        ]):
            return "total"
        if any(k in text_lower for k in ["tuition", "ట్యూషన్", "ट्यूशन"]):
            return "tuition"
        return "general"

    @classmethod
    def normalize(cls, query_text: str) -> NormalizedQuery:
        """Classify intent and generate canonical search terms for authoritative RAG retrieval."""
        text_lower = query_text.lower().strip()
        words = set(re.findall(r'[\w\u0900-\u097F\u0C00-\u0C7F]+', text_lower))
        fee_type = cls.detect_fee_type(text_lower)

        # Detect specific course mentions
        courses_mentioned = []
        if words & cls.CSE_IDENTIFIERS or any(k in text_lower for k in ["cse", "csc", "computer science", "కంప్యూటర్", "సిఎస్ఇ", "సిఎస్సి"]):
            courses_mentioned.append("CSE")
        if words & cls.ECE_IDENTIFIERS or any(k in text_lower for k in ["ece", "electronics", "ఎలక్ట్రానిక్స్", "ఈసిఈ"]):
            courses_mentioned.append("ECE")
        if words & cls.MECH_IDENTIFIERS or any(k in text_lower for k in ["mech", "mechanical", "మెకానికల్"]):
            courses_mentioned.append("MECH")

        canonical_keywords = []

        # 1. Hostel Inquiry check (hostel facilities and hostel fees)
        if fee_type == "hostel" or words & cls.HOSTEL_MARKERS or any(k in text_lower for k in ["hostel", "హాస్టల్", "हॉस्टल"]):
            intent = SemanticIntent.HOSTEL_INQUIRY
            canonical_keywords = ["hostel", "facilities", "ac", "non-ac", "fee", "food"]
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text,
                fee_type="hostel"
            )

        # 2. Admission Dates Inquiry check
        if words & cls.DATE_MARKERS or any(k in text_lower for k in ["date", "dates", "deadline", "when", "eppudu", "kab", "ఎప్పుడు", "कब", "last date", "start date", "లాస్ట్ డేట్"]):
            intent = SemanticIntent.ADMISSION_DATES_INQUIRY
            canonical_keywords = ["admission", "dates", "2026", "session", "open", "close", "deadline"]
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text,
                fee_type="general"
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
                raw_query=query_text,
                fee_type="general"
            )

        # 4. Fee Inquiry check (evaluated before Course List to catch "How much is the course?")
        is_fee_query = (
            bool(words & cls.FEE_MARKERS)
            or any(p in text_lower for p in cls.FEE_PHRASES)
            or fee_type in ("admission", "total", "tuition")
        )

        if is_fee_query:
            intent = SemanticIntent.FEES_INQUIRY
            canonical_keywords = ["fee", "fees", "tuition", "cost", "inr", "annual"]
            if fee_type == "admission":
                canonical_keywords.extend(["admission", "one-time"])
            elif fee_type == "total":
                canonical_keywords.extend(["total", "4-year", "full"])
            elif fee_type == "tuition":
                canonical_keywords.extend(["tuition", "academic"])
            if courses_mentioned:
                canonical_keywords.extend(courses_mentioned)
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text,
                fee_type=fee_type
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
                raw_query=query_text,
                fee_type="general"
            )

        # Default / Specific Course check
        if courses_mentioned and any(k in text_lower for k in ["details", "about", "వివరాలు", "గురించి"]):
            intent = SemanticIntent.LIST_AVAILABLE_COURSES
            canonical_keywords = ["courses", "btech", "fees"] + courses_mentioned
            return NormalizedQuery(
                intent=intent,
                canonical_keywords=canonical_keywords,
                courses_mentioned=courses_mentioned,
                raw_query=query_text,
                fee_type="general"
            )

        # General inquiry fallback
        return NormalizedQuery(
            intent=SemanticIntent.GENERAL_INQUIRY,
            canonical_keywords=list(words),
            courses_mentioned=[],
            raw_query=query_text,
            fee_type="general"
        )
