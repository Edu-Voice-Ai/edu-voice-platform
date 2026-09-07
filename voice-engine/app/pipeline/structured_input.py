"""Structured numeric input handler, digit normalizer, and pause-tolerant multi-segment accumulator."""
import re
import time
from enum import Enum
from typing import List, Optional, Tuple, Dict
from app.core.logging import get_logger

logger = get_logger("pipeline.structured_input")


class StructuredInputMode(str, Enum):
    NORMAL = "NORMAL"
    NUMERIC = "NUMERIC"
    PHONE_NUMBER = "PHONE_NUMBER"
    OTP = "OTP"
    PIN = "PIN"
    STUDENT_ID = "STUDENT_ID"
    APPLICATION_ID = "APPLICATION_ID"
    DATE = "DATE"
    TIME = "TIME"
    POSTAL_CODE = "POSTAL_CODE"


class DigitNormalizer:
    """Normalizes spoken words and symbols into raw digits across English, Hindi, and Telugu."""

    # Words to digits mappings
    WORD_TO_DIGIT: Dict[str, str] = {
        # English words
        "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
        
        # Hindi words (Devanagari)
        "शून्य": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4",
        "पांच": "5", "पाँच": "5", "छह": "6", "छः": "6", "सात": "7",
        "आठ": "8", "नौ": "9",
        
        # Hindi words (Roman script)
        "shunya": "0", "ek": "1", "do": "2", "teen": "3", "chaar": "4", "char": "4",
        "paanch": "5", "panch": "5", "chhah": "6", "che": "6", "saat": "7", "sat": "7",
        "aath": "8", "ath": "8", "nau": "9", "no": "9",

        # Telugu words (Telugu script)
        "సున్నా": "0", "ఒకటి": "1", "రెండు": "2", "మూడు": "3", "నాలుగు": "4",
        "ఐదు": "5", "ఆరు": "6", "ఏడు": "7", "ఎనిమిది": "8", "తొమ్మిది": "9",
        
        # Telugu words (Roman script)
        "sunna": "0", "okati": "1", "rendu": "2", "moodu": "3", "naalugu": "4",
        "nalugu": "4", "aidu": "5", "aaru": "6", "yedu": "7", "edu": "7",
        "enimidi": "8", "tommidi": "9"
    }

    # Indic Unicode digits conversion
    INDIC_DIGIT_MAP = str.maketrans({
        # Devanagari ०-९
        "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
        "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
        # Telugu ౦-౯
        "౦": "0", "౧": "1", "౨": "2", "౩": "3", "౪": "4",
        "౫": "5", "౬": "6", "౭": "7", "౮": "8", "౯": "9"
    })

    @classmethod
    def extract_digits(cls, text: str) -> str:
        """Extract all numeric digits from text, resolving number words and Indic digits."""
        if not text:
            return ""

        # 1. Translate Indic Unicode digits (०-९, ౦-౯)
        translated = text.translate(cls.INDIC_DIGIT_MAP)

        # 2. Tokenize by whitespace, hyphens, and commas
        raw_tokens = re.split(r"[\s,]+", translated.lower().strip())
        digit_chars = []

        i = 0
        while i < len(raw_tokens):
            token = raw_tokens[i].strip(".,-?!;:()\"'")
            if not token:
                i += 1
                continue

            # Handle multipliers like "double seven" -> 77, "triple zero" -> 000
            if token in ("double", "डबल", "డబుల్") and i + 1 < len(raw_tokens):
                next_tok = raw_tokens[i + 1].strip(".,-?!;:()\"'")
                val = cls.WORD_TO_DIGIT.get(next_tok, next_tok if next_tok.isdigit() else "")
                if val and len(val) == 1:
                    digit_chars.append(val * 2)
                    i += 2
                    continue
            elif token in ("triple", "ट्रिपल", "ట్రిపుల్") and i + 1 < len(raw_tokens):
                next_tok = raw_tokens[i + 1].strip(".,-?!;:()\"'")
                val = cls.WORD_TO_DIGIT.get(next_tok, next_tok if next_tok.isdigit() else "")
                if val and len(val) == 1:
                    digit_chars.append(val * 3)
                    i += 2
                    continue

            # Check full word match
            if token in cls.WORD_TO_DIGIT:
                digit_chars.append(cls.WORD_TO_DIGIT[token])
            elif token.isdigit():
                digit_chars.append(token)
            else:
                # Check for direct embedded digits within alphanumeric string (e.g. "720a" or "720-770")
                for char in token:
                    if char.isdigit():
                        digit_chars.append(char)

            i += 1

        return "".join(digit_chars)

    @classmethod
    def has_digit_sequence(cls, text: str) -> bool:
        """Returns True if text contains at least one digit or spoken number word."""
        digits = cls.extract_digits(text)
        return len(digits) >= 1

    @classmethod
    def mask_phone_number(cls, phone_number: str) -> str:
        """Safely mask sensitive phone number digits for logging (e.g. 7207702245 -> ******2245)."""
        if not phone_number:
            return ""
        if len(phone_number) <= 4:
            return "*" * len(phone_number)
        return "*" * (len(phone_number) - 4) + phone_number[-4:]


class PhoneNumberValidator:
    """Validates and standardizes 10-digit Indian phone numbers."""

    @classmethod
    def validate_indian_mobile(cls, raw_digits: str, min_digits: int = 10, max_digits: int = 15) -> Tuple[bool, str]:
        """
        Validate Indian mobile number.
        Strips country code +91 or leading 0.
        Returns (is_valid, clean_10_digit_string).
        """
        clean = re.sub(r"\D", "", raw_digits)
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        elif clean.startswith("0") and len(clean) == 11:
            clean = clean[1:]

        # Check 10-digit standard Indian mobile starting with 6, 7, 8, 9
        if len(clean) == 10 and clean[0] in "6789":
            return True, clean

        # Allow general 10-digit number if min_digits <= len(clean) <= max_digits
        if min_digits <= len(clean) <= max_digits:
            return True, clean

        return False, clean


class StructuredInputDetector:
    """Detects whether assistant explicitly requests structured numeric input (e.g. phone number)."""

    PHONE_PROMPT_PATTERNS = [
        # English and code-mixed patterns
        r"\b(phone number|mobile number|contact number|your number|phone num)\b",
        # Hindi request patterns
        r"(अपना (10 अंकों का )?(फोन|मोबाइल|नंबर)|फोन नंबर|मोबाइल नंबर|नंबर बताइए|नंबर बता दीजिए|नंबर दीजिए|कांटेक्ट नंबर)",
        # Telugu request patterns
        r"(మీ (10 అంకెల )?(ఫోన్|మొబైల్)? నంబర్|ఫోన్ నంబర్|మొబైల్ నంబర్|నంబర్ చెప్తారా|నంబర్ చెప్పండి|నంబర్ ఇవ్వండి|నంబర్ చెప్పగలరా)"
    ]

    @classmethod
    def detect_mode_from_assistant_message(cls, assistant_text: str) -> StructuredInputMode:
        """Detects if assistant specifically asked the user for their phone number."""
        if not assistant_text:
            return StructuredInputMode.NORMAL

        text_lower = assistant_text.lower()
        
        # If message is already acknowledging/confirming a noted phone number, do NOT activate structured input mode
        if any(c in text_lower for c in ["noted your number", "call you back at", "నంబర్‌కి", "నంబర్‌కు", "నెంబరుకు", "నంబర్ నోట్", "नंबर नोट", "कॉल करेंगे"]):
            return StructuredInputMode.NORMAL

        for pattern in cls.PHONE_PROMPT_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return StructuredInputMode.PHONE_NUMBER

        return StructuredInputMode.NORMAL


class NumericTurnAccumulator:
    """
    Coordinates multi-segment buffering across speech pauses for structured numeric input.
    Prevents premature turn completion when a user speaks digits in groups (e.g. '720' ... '7702245').
    """

    @classmethod
    def handle_segment(
        cls,
        session_id: str,
        current_segments: List[str],
        new_transcript: str,
        mode: StructuredInputMode = StructuredInputMode.PHONE_NUMBER,
        target_digits: int = 10
    ) -> Tuple[bool, str, List[str]]:
        """
        Processes an incoming transcript segment.
        Returns:
            is_complete (bool): True if full phone number / target digits accumulated.
            resolved_text (str): Finalized numeric string or current combined representation.
            updated_segments (List[str]): New state of buffered segments.
        """
        extracted = DigitNormalizer.extract_digits(new_transcript)
        if not extracted:
            # User spoke non-digits
            combined_raw = " ".join(current_segments + [new_transcript])
            return True, combined_raw, []

        updated_segments = list(current_segments) + [extracted]
        combined_digits = "".join(updated_segments)

        masked_log = DigitNormalizer.mask_phone_number(combined_digits)
        logger.info(
            f"NUMERIC_SEGMENT_RECEIVED: {masked_log} (accumulated {len(combined_digits)}/{target_digits} digits)",
            extra={"session_id": session_id}
        )

        if mode == StructuredInputMode.PHONE_NUMBER:
            is_valid, clean_num = PhoneNumberValidator.validate_indian_mobile(combined_digits)
            if is_valid:
                logger.info(f"NUMERIC_BUFFER_FINALIZED: {DigitNormalizer.mask_phone_number(clean_num)}", extra={"session_id": session_id})
                return True, clean_num, []

            # If user has already spoken 10 or more digits
            if len(combined_digits) >= target_digits:
                return True, combined_digits[:target_digits], []

            # Incomplete digits: keep buffering
            return False, combined_digits, updated_segments

        # General numeric mode
        if len(combined_digits) >= target_digits:
            return True, combined_digits, []

        return False, combined_digits, updated_segments
