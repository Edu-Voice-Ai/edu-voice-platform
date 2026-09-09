"""Multilingual Handoff Intent and Entity Detection according to Universal Specification."""
import re
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel
from app.tools.handoff import HANDOFF_ROLE_ENUM, HANDOFF_DEPARTMENT_ENUM, ROLE_TO_DEPARTMENT


class HandoffDetectionResult(BaseModel):
    is_handoff_requested: bool
    requested_role: str = "admission_counselor"
    requested_department: str = "admissions"
    reason: str = ""
    confidence: float = 0.0
    is_ambiguous: bool = False
    is_cancellation: bool = False
    clarification_prompt: Optional[str] = None


# Role keyword patterns across languages
ROLE_PATTERNS = {
    "admission_counselor": [
        r"admission\s*counselor", r"admission\s*officer", r"admissions?", r"counselor",
        r"అడ్మిషన్\s*కౌన్సిలర్", r"కౌన్సిలర్", r"అడ్మిషన్", r"కౌన్సిలర్‌",
        r"एडमिशन\s*काउंसलर", r"काउंसलर", r"एडमिशन", r"दाखिला"
    ],
    "accounts_officer": [
        r"accounts?\s*officer", r"accounts?", r"finance", r"fee\s*department", r"fees?\s*section",
        r"అకౌంట్స్", r"ఫీజు\s*సెక్షన్", r"ఖాతాలు",
        r"अकाउंट्स", r"अकाउंट", r"फीस\s*विभाग", r"लेखा"
    ],
    "principal": [
        r"principal", r"director", r"dean", r"head\s*of\s*institution",
        r"ప్రిన్సిపాల్", r"డైరెక్టర్", r"డీన్",
        r"प्रिंसिपल", r"निदेशक", r"डीन"
    ],
    "hostel_warden": [
        r"hostel\s*warden", r"warden", r"hostel\s*incharge", r"hostel\s*caretaker",
        r"హాస్టల్\s*వార్డెన్", r"వార్డెన్", r"హాస్టల్\s*ఇన్‌ఛార్జ్",
        r"हॉस्टल\s*वार्डन", r"वार्डन", r"हॉस्टल\s*प्रभारी"
    ],
    "administrator": [
        r"administrator", r"admin\s*office", r"registrar", r"clerk",
        r"అడ్మినిస్ట్రేటర్", r"అడ్మిన్", r"రిజిస్ట్రార్",
        r"प्रशासक", r"एडमिन", r"रजिस्ट्रार"
    ],
    "general_counselor": [
        r"representative", r"human", r"person", r"someone", r"staff", r"agent", r"operator",
        r"మనిషి", r"సిబ్బంది", r"ఎవరితోనైనా",
        r"इंसान", r"व्यक्ति", r"स्टाफ", r"प्रतिनिधि"
    ]
}

# Strong explicit handoff intents
ENGLISH_EXPLICIT = [
    r"(?:i\s+(?:want|would\s+like)\s+to\s+|let\s+me\s+|can\s+i\s+|please\s+)?(?:talk|speak)\s+(?:to|with)\s+(?:a\s+|an\s+|the\s+)?(?:human|person|counselor|admission|staff|officer|someone|representative|agent|principal|warden|director)",
    r"(?:please\s+)?(?:connect|transfer)\s+(?:me|this\s+call|my\s+call)?\s*(?:to|with)?\s*(?:a\s+|an\s+|the\s+)?(?:human|person|counselor|admission|accounts|hostel|principal|department|agent|someone|staff|officer|warden)",
    r"transfer\s+(?:this\s+call|my\s+call|the\s+call|me)?\s*(?:to\s+an?\s+agent)?",
    r"connect\s+me\s+to\s+a\s+human",
    r"i\s+want\s+to\s+talk\s+to\s+a\s+human",
    r"can\s+i\s+talk\s+to\s+a\s+real\s+person",
    r"give\s+me\s+a\s+human",
    r"human\s+counselor",
    r"human\s+agent",
    r"speak\s+to\s+the\s+principal",
    r"talk\s+to\s+admission\s+counselor",
]

TELUGU_EXPLICIT = [
    r"(?:కౌన్సిలర్|కౌన్సిలర్‌|అడ్మిషన్\s*కౌన్సిలర్|మనిషి|వార్డెన్|ప్రిన్సిపాల్|అకౌంట్స్|స్టాఫ్)(?:\s*గారితో|\s*తో|\s*తోటి)?\s*మాట్లాడాలి",
    r"ఒక\s*మనిషితో\s*మాట్లాడించండి",
    r"మనిషితో\s*మాట్లాడించండి",
    r"మాట్లాడించండి",
    r"(?:కాల్\s*)?(?:ట్రాన్స్‌ఫర్|ట్రాన్స్\s*ఫర్|ట్రాన్స్ఫర్)\s*చేయండి",
    r"(?:counselor|human|agent|person|admission|principal|warden|accounts)\s*(?:tho|thoti|garitho)\s*(?:matladali|matladandi)",
    r"call\s*transfer\s*cheyandi",
    r"admission\s*counselor\s*tho\s*matladali",
]

HINDI_EXPLICIT = [
    r"(?:काउंसलर|एडमिशन\s*काउंसलर|इंसान|व्यक्ति|स्टाफ|प्रतिनिधि|प्रिंसिपल|वार्डन|अकाउंट्स)(?:\s*विभाग|\s*डिपार्टमेंट|\s*सर|\s*जी)?\s*से\s*बात\s*(?:करनी\s*है|कराइए|करवाइए|करा\s*दो|कराओ)",
    r"(?:कृपया\s+)?(?:मुझे\s+)?(?:किसी\s+)?इंसान\s*से\s*(?:कनेक्ट\s*करें|बात)",
    r"किसी\s*से\s*बात\s*करवाइए",
    r"(?:कॉल\s*)?ट्रांसफर\s*(?:कीजिए|करो|कर\s*दो|कराओ)",
    r"(?:hostel\s*warden|counselor|principal|accounts|human\s*agent|human)\s*se\s*(?:connect\s*karo|baat\s*karni\s*hai|baat\s*karwao)",
    r"transfer\s*kijiye",
]

# Cancellation keywords during transfer waiting
CANCELLATION_PATTERNS = [
    r"never\s*mind",
    r"cancel\s*(?:the\s*)?(?:transfer|call|handoff)",
    r"wait\s*,?\s*i(?:'ll|\s+will)\s+just\s+ask\s+you",
    r"no\s+need\s+to\s+transfer",
    r"don'?t\s+transfer",
    r"వద్దు\s*లెండి",
    r"ఆగండి\s*నేనే\s*అడుగుతాను",
    r"ట్రాన్స్‌ఫర్\s*వద్దు",
    r"రద్దు\s*చేయండి",
    r"नहीं\s*रहने\s*दीजिए",
    r"ट्रांसफर\s*मत\s*कीजिए",
    r"रद्द\s*करें"
]

# Ambiguous inquiries that should elicit clarification instead of direct handoff
AMBIGUOUS_PATTERNS = [
    r"are\s+you\s+a\s+human",
    r"are\s+you\s+an\s+ai",
    r"is\s+there\s+anyone\s+there",
    r"do\s+you\s+have\s+counselors",
    r"మీరు\s*మనిషా",
    r"మీరు\s*ai\s*నా",
    r"కౌన్సిలర్లు\s*ఉన్నారా",
    r"क्या\s*आप\s*इंसान\s*हैं",
    r"क्या\s*वहाँ\s*कोई\s*है"
]


class MultilingualHandoffDetector:
    """Zero-telephony, provider-agnostic handoff intent and role extraction engine."""

    @classmethod
    def extract_role_and_department(cls, text: str) -> Tuple[str, str]:
        """Extract requested role and mapped department from text."""
        lower = text.lower()
        for role, patterns in ROLE_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, lower, re.IGNORECASE):
                    dept = ROLE_TO_DEPARTMENT.get(role, "general")
                    return role, dept
        return "admission_counselor", "admissions"

    @classmethod
    def detect_cancellation(cls, text: str) -> bool:
        """Detect if caller is canceling an ongoing handoff during AWAITING_TRANSFER."""
        lower = text.lower()
        for pat in CANCELLATION_PATTERNS:
            if re.search(pat, lower, re.IGNORECASE):
                return True
        return False

    @classmethod
    def detect(
        cls,
        text: str,
        lang: str = "en-IN",
        out_of_scope_turns: int = 0,
        frustration_score: float = 0.0
    ) -> HandoffDetectionResult:
        """
        Evaluate caller utterance and conversational heuristics for handoff intent.
        Threshold for handoff.requested is confidence >= 0.85.
        """
        if not text:
            return HandoffDetectionResult(is_handoff_requested=False)

        clean = text.strip().lower()

        # 1. Check for cancellation
        if cls.detect_cancellation(clean):
            return HandoffDetectionResult(
                is_handoff_requested=False,
                is_cancellation=True,
                reason="Caller explicitly cancelled handoff"
            )

        # 2. Check for AI escalation heuristics
        # Rule 1: Two consecutive complex out-of-scope failures
        if out_of_scope_turns >= 2:
            role, dept = cls.extract_role_and_department(clean)
            return HandoffDetectionResult(
                is_handoff_requested=True,
                requested_role=role,
                requested_department=dept,
                reason="AI escalation: 2 consecutive out-of-scope knowledge failures",
                confidence=0.90
            )

        # Rule 2: Caller frustration / confusion score >= 0.85
        if frustration_score >= 0.85:
            role, dept = cls.extract_role_and_department(clean)
            return HandoffDetectionResult(
                is_handoff_requested=True,
                requested_role=role,
                requested_department=dept,
                reason=f"AI escalation: high caller frustration detected ({frustration_score:.2f})",
                confidence=0.92
            )

        # 3. Check explicit patterns across languages
        matched_explicit = False
        all_explicit = ENGLISH_EXPLICIT + TELUGU_EXPLICIT + HINDI_EXPLICIT
        for pat in all_explicit:
            if re.search(pat, clean, re.IGNORECASE):
                matched_explicit = True
                break

        if matched_explicit:
            role, dept = cls.extract_role_and_department(clean)
            return HandoffDetectionResult(
                is_handoff_requested=True,
                requested_role=role,
                requested_department=dept,
                reason=f"Caller explicitly requested human handoff to {role}",
                confidence=0.98
            )

        # 4. Check for ambiguous inquiries (confidence < 0.85) -> Clarify, do NOT handoff
        for pat in AMBIGUOUS_PATTERNS:
            if re.search(pat, clean, re.IGNORECASE):
                clarification = {
                    "te-IN": "అవునండి, నేను AI కౌన్సెలర్‌ని. మీరు మా అడ్మిషన్స్ కౌన్సిలర్ తో మాట్లాడాలనుకుంటున్నారా?",
                    "hi-IN": "हाँ, मैं एआई काउंसलर हूँ। क्या आप हमारे एडमिशन काउंसलर से बात करना चाहते हैं?",
                    "en-IN": "Yes, I am the AI counselor. Would you like me to connect you with a human admissions counselor?"
                }.get(lang, "Would you like me to connect you with a human admissions counselor?")
                return HandoffDetectionResult(
                    is_handoff_requested=False,
                    is_ambiguous=True,
                    confidence=0.50,
                    clarification_prompt=clarification,
                    reason="Ambiguous inquiry requiring caller clarification"
                )

        return HandoffDetectionResult(is_handoff_requested=False, confidence=0.0)

    @classmethod
    def get_holding_announcement(cls, role: str, lang: str = "en-IN") -> str:
        """Generate provider-agnostic pre-transfer holding announcement."""
        role_labels = {
            "admission_counselor": {"en": "an admission counselor", "te": "అడ్మిషన్ కౌన్సిలర్‌తో", "hi": "एडमिशन काउंसलर से"},
            "accounts_officer": {"en": "the accounts department", "te": "అకౌంట్స్ అధికారితో", "hi": "अकाउंट्स अधिकारी से"},
            "principal": {"en": "the principal's office", "te": "ప్రిన్సిపాల్ గారితో", "hi": "प्रिंसिपल कार्यालय से"},
            "hostel_warden": {"en": "the hostel warden", "te": "హాస్టల్ వార్డెన్‌తో", "hi": "हॉस्टल वार्डन से"},
            "administrator": {"en": "the administration office", "te": "అడ్మినిస్ట్రేటివ్ అధికారితో", "hi": "प्रशासनिक अधिकारी से"},
            "general_counselor": {"en": "a human representative", "te": "కౌన్సిలర్‌తో", "hi": "प्रतिनिधि से"},
        }
        labels = role_labels.get(role, role_labels["admission_counselor"])

        if lang == "te-IN":
            return f"దయచేసి వేచి ఉండండి, నేను మిమ్మల్ని {labels['te']} కనెక్ట్ చేస్తాను."
        elif lang == "hi-IN":
            return f"कृपया प्रतीक्षा करें, मैं आपको {labels['hi']} जोड़ रही हूँ।"
        return f"Please hold on while I connect you to {labels['en']}."

    @classmethod
    def get_fallback_announcement(cls, reason: str = "NO_ELIGIBLE_STAFF", lang: str = "en-IN") -> str:
        """Generate polite context-aware fallback response when transfer cannot complete."""
        if lang == "te-IN":
            return "క్షమించండి, ప్రస్తుతం మా అడ్మిషన్ కౌన్సెలర్లు అందరూ ఇతర కాల్స్‌లో బిజీగా ఉన్నారు. దయచేసి మీ వివరాలు చెబితే మేము తిరిగి కాల్ చేస్తాము."
        elif lang == "hi-IN":
            return "क्षमा करें, इस समय हमारे सभी एडमिशन काउंसलर अन्य कॉल पर व्यस्त हैं। क्या मैं आपकी जानकारी नोट कर लूँ ताकि आपको कॉल बैक किया जा सके?"
        return "I apologize, but all our admission counselors are currently assisting other callers. May I take your details so we can arrange a callback for you?"
