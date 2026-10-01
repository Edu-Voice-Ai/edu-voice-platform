"""Domain-aware transcript normalization for course and academic entities."""
import re
from typing import Optional, Any
from app.core.logging import get_logger

logger = get_logger("stt.normalization")

# Course context keywords indicating the caller is inquiring about an academic course or admission
COURSE_CONTEXT_PATTERNS = [
    # English
    r"\b(course|courses|group|groups|stream|streams|branch|branches|subject|subjects|fee|fees|admission|admissions|eligibility|seats?|join|joining|offer|offering|details|inter|intermediate|college)\b",
    # Telugu
    r"(కోర్స్|కోర్సులు|కోర్సు|గ్రూప్|స్ట్రీమ్|ఇంటర్|ఇంటర్మీడియట్|ఫీజు|ఫీస్|అడ్మిషన్|అడ్మిషన్లు|సీట్లు|సీట్|ఎలిజిబిలిటీ|గురించి|ఉందా|ఉన్నాయా|చేరవచ్చా|చెప్పండి|కావాలి|వివరాలు|కాలేజ్)",
    # Hindi
    r"(कोर्स|विषय|स्ट्रीम|इंटर|इंटरमीडिएट|फीस|दाखिला|एडमिशन|सीट|योग्यता|बताइए|बारे में|चाहिए|जानकारी|कॉलेज)",
]

# Government exam / Public Service Commission indicators where PSC should NOT be normalized
PSC_EXAM_PATTERNS = [
    r"\b(public\s+service|tspsc|appsc|upsc|commission|govt\s+exam|civil\s+services?|job|jobs|notification|recruitment)\b",
    r"(ఉద్యోగం|కమిషన్|పరీక్ష|నోటిఫికేషన్|ఆయోగ్)",
    r"(नौकरी|आयोग|भर्ती|सरकारी\s+नौकरी|परीक्षा)",
]

# Regex patterns matching phonetic misrecognitions of "CEC"
# 1. Telugu: 'పీఎస్సీ', 'పీ.ఎస్.సి', 'పీ ఎస్ సీ', 'టీఎస్సీ', 'టీఎస్ కి' (in course context)
TELUGU_CANDIDATE_REGEX = re.compile(
    r"(పీ\s*ఎస్\s*సీ|పీ\s*\.?\s*ఎస్\s*\.?\s*సి\.?|పీఎస్సీ|టీఎస్సీ|టీఎస్\s*కి|సి\s*ఈ\s*సి|సి\s*\.?\s*ఈ\s*\.?\s*సి\.?|సిఇసి)",
    re.IGNORECASE
)

# 2. Hindi: 'पीएससी', 'पी.एस.सी.', 'सीईसी'
HINDI_CANDIDATE_REGEX = re.compile(
    r"(पी\s*एस\s*सी|पी\s*\.?\s*एस\s*\.?\s*सी\.?|पीएससी|सी\s*ई\s*सी)",
    re.IGNORECASE
)

# 3. English: 'PSC', 'P.S.C.', 'P S C', 'TSC', 'T.S.C.', 'C E C', 'C.E.C.'
ENGLISH_CANDIDATE_REGEX = re.compile(
    r"\b([Pp]\.?\s*[Ss]\.?\s*[Cc]\.?|[Tt]\.?\s*[Ss]\.?\s*[Cc]\.?|[Cc]\.?\s*[Ee]\.?\s*[Cc]\.?)\b\.?",
    re.IGNORECASE
)


def has_course_context(text: str) -> bool:
    """Check if the utterance contains signals of course/admission inquiry."""
    for pat in COURSE_CONTEXT_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def is_genuine_psc_query(text: str) -> bool:
    """Check if the utterance is explicitly referring to Public Service Commission or government exam."""
    for pat in PSC_EXAM_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def normalize_course_transcript(transcript: str, session: Optional[Any] = None) -> str:
    """
    Domain-aware normalization layer for academic course names.
    Corrects acoustic confusions (such as Sarvam STT hearing 'CEC' as 'PSC' or 'టీఎస్ కి')
    ONLY when the utterance is genuinely inquiring about academic courses.
    Never modifies genuine references to Public Service Commission (APPSC/TSPSC/UPSC).
    """
    if not transcript or not transcript.strip():
        return transcript

    cleaned = transcript.strip()

    # If the user is explicitly inquiring about government/public service commission, preserve PSC
    if is_genuine_psc_query(cleaned):
        return transcript

    # Must contain course inquiry context to justify normalizing acoustic candidates
    in_course_context = has_course_context(cleaned)

    # Candidate matches
    has_te_match = bool(TELUGU_CANDIDATE_REGEX.search(cleaned))
    has_hi_match = bool(HINDI_CANDIDATE_REGEX.search(cleaned))
    has_en_match = bool(ENGLISH_CANDIDATE_REGEX.search(cleaned))

    if not (has_te_match or has_hi_match or has_en_match):
        return transcript

    # If in course context, normalize candidate matches to canonical 'CEC'
    if in_course_context:
        normalized = cleaned
        if has_te_match:
            normalized = TELUGU_CANDIDATE_REGEX.sub("CEC", normalized)
        if has_hi_match:
            normalized = HINDI_CANDIDATE_REGEX.sub("CEC", normalized)
        if has_en_match:
            normalized = ENGLISH_CANDIDATE_REGEX.sub("CEC", normalized)

        # Clean any awkward double spaces or orphaned periods
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized != cleaned:
            logger.info(
                f"[COURSE_NORMALIZER] Normalized course transcript: \"{cleaned}\" -> \"{normalized}\""
            )
            return normalized

    return transcript
