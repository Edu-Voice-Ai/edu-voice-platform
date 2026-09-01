"""Multilingual detection, script recognition, and language preference parsing."""
import re
from typing import Optional, Tuple, Dict

SUPPORTED_LANGUAGES = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "te-IN": "Telugu"
}

LANGUAGE_NAMES = {
    "en-IN": "English",
    "hi-IN": "Hindi (हिन्दी)",
    "te-IN": "Telugu (తెలుగు)"
}

INITIAL_GREETING_TEMPLATE = (
    "Welcome to {institution_name}. Which language do you prefer? English, Hindi, or Telugu?"
)

LANGUAGE_STYLE_MAPPING = {
    "te-IN": "telugish",
    "hi-IN": "hinglish",
    "en-IN": "indian_english"
}

INITIAL_ACKNOWLEDGMENT = {
    "en-IN": "Sure. We will continue in English. How can I help you with admissions today?",
    "hi-IN": "ज़रूर, अब से हम Hindi में बात करेंगे। आपको किस course के बारे में details चाहिए?",
    "te-IN": "సరే, ఇక నుంచి మనం Telugu లో మాట్లాడుకుందాం. మీకు ఏ course details కావాలి?"
}

SWITCH_ACKNOWLEDGMENT = {
    "en-IN": "Sure, switching to English. How can I help you with admissions?",
    "hi-IN": "ज़रूर, Hindi में बात करते हैं। बताइए आपको क्या details चाहिए?",
    "te-IN": "సరే, Telugu లో మాట్లాడుతాను. మీకు ఏ details కావాలి?"
}

LANGUAGE_CLARIFICATION_PROMPT = {
    "en-IN": "Sure. Which language do you prefer: English, Hindi, or Telugu?",
    "hi-IN": "नमस्ते। आप किस भाषा में बात करना पसंद करेंगे: इंग्लिश, हिंदी, या तेलुगु?",
    "te-IN": "నమస్కారం. మీరు ఏ భాషలో మాట్లాడాలనుకుంటున్నారు: ఇంగ్లీష్, హిందీ, లేదా తెలుగు?"
}

BARGE_IN_ACKNOWLEDGMENT = {
    "te-IN": "అవును, చెప్పండి.",
    "hi-IN": "हाँ, बोलिए.",
    "en-IN": "Yes, go ahead."
}


class LanguageDetector:
    """Detects and categorizes language scripts for Indian multilingual voice interactions."""

    TELUGU_RANGE = (0x0C00, 0x0C7F)
    DEVANAGARI_RANGE = (0x0900, 0x097F)

    # Common Telugu Roman keywords
    TELUGU_ROMAN_MARKERS = {
        "eppudu", "entha", "ekkada", "ela", "avuthundi", "avutundi", "undha", "undi",
        "cheskovali", "cheppandi", "kavali", "telusukovali", "namaskaram", "namaste",
        "matladandi", "matladu", "lo", "cheppandi", "matladali", "naaku"
    }

    # Common Hindi Roman keywords
    HINDI_ROMAN_MARKERS = {
        "kab", "kitna", "kahan", "kaise", "hoga", "hogi", "hai", "karna", "bataiye",
        "chahiye", "pata", "batao", "namaskar", "namaste", "baat", "kijiye", "boliye", "mein", "karni"
    }

    @classmethod
    def detect_language(cls, text: str) -> str:
        """
        Detect language code from text.
        Returns:
            "te-IN" for Telugu or Roman Telugu
            "hi-IN" for Hindi or Roman Hindi
            "en-IN" for English or default Indian English
        """
        if not text:
            return "en-IN"

        # Check native Unicode scripts
        has_telugu = any(cls.TELUGU_RANGE[0] <= ord(c) <= cls.TELUGU_RANGE[1] for c in text)
        if has_telugu:
            return "te-IN"

        has_devanagari = any(cls.DEVANAGARI_RANGE[0] <= ord(c) <= cls.DEVANAGARI_RANGE[1] for c in text)
        if has_devanagari:
            return "hi-IN"

        # Check Romanized code-mixing markers
        tokens = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
        telugu_matches = tokens.intersection(cls.TELUGU_ROMAN_MARKERS)
        hindi_matches = tokens.intersection(cls.HINDI_ROMAN_MARKERS)

        if len(telugu_matches) >= 1 and (len(telugu_matches) >= len(hindi_matches)):
            return "te-IN"
        if len(hindi_matches) >= 1:
            return "hi-IN"

        return "en-IN"


class LanguagePreferenceParser:
    """Parses initial language selections and explicit language switch requests."""

    @classmethod
    def is_ambiguous_greeting(cls, text: str) -> bool:
        """Check if utterance is just an initial greeting with no language preference indicated."""
        if not text:
            return True
        clean = text.lower().strip().strip(".,-?!;:()\"'")
        greetings = {
            "hello", "hi", "hey", "namaste", "namaskar", "namaskaram",
            "హలో", "నమస్కారం", "నమస్తే", "नमस्ते", "नमस्कार", "हेलो", "हाँ", "హా"
        }
        return clean in greetings

    @classmethod
    def parse_language_preference(cls, text: str) -> Optional[str]:
        """
        Parses initial user response to select preferred language.
        Supports natural language, native scripts, and code-mixed answers.
        Returns 'en-IN', 'hi-IN', 'te-IN', or None if completely ambiguous (like just 'hello').
        """
        if not text:
            return None

        if cls.is_ambiguous_greeting(text):
            return None

        # Check native Unicode scripts
        if any(0x0C00 <= ord(c) <= 0x0C7F for c in text):
            return "te-IN"
        if any(0x0900 <= ord(c) <= 0x097F for c in text):
            return "hi-IN"

        normalized = text.lower().strip()

        # 1. Check Telugu patterns
        telugu_patterns = [
            "telugu", "telgu", "telug", "telg", "pelugu", "talugu", "tilugu",
            "payu", "tell you", "tellu", "telu", "మాట్లాడతాను", "మాట్లాడండి",
            "matladandi", "matladu", "తెలుగులో"
        ]
        if any(k in normalized for k in telugu_patterns):
            return "te-IN"

        # 2. Check Hindi patterns
        hindi_patterns = ["hindi", "hind", "hndi", "हिंदी", "हिन्दी", "बात करो", "बात करें", "boliye"]
        if any(k in normalized for k in hindi_patterns):
            return "hi-IN"

        # 3. Check English patterns
        english_patterns = ["english", "eng", "inglish", "ఇంగ్లీష్", "इंग्लिश"]
        if any(k in normalized for k in english_patterns):
            return "en-IN"

        # 4. If user speaks in sentences or asks admission question, deduce from LanguageDetector
        detected = LanguageDetector.detect_language(text)
        if detected != "en-IN" or len(normalized.split()) >= 2:
            return detected

        return None

    @classmethod
    def detect_language_switch(cls, text: str) -> Optional[str]:
        """
        Detects if the user is explicitly requesting to switch languages during the call.
        Returns the new language code (e.g. 'en-IN', 'hi-IN', 'te-IN') or None if not switching.
        """
        if not text:
            return None

        normalized = text.lower().strip()

        # 1. Telugu switch (any mention of Telugu or script)
        telugu_switch = [
            "తెలుగు", "telugu", "telgu", "telug", "telg", "pelugu", "talugu",
            "payu", "tell you", "tellu", "telu", "మాట్లాడతాను", "మాట్లాడండి"
        ]
        if any(0x0C00 <= ord(c) <= 0x0C7F for c in text) or any(k in normalized for k in telugu_switch):
            return "te-IN"

        # 2. Hindi switch
        hindi_switch = ["hindi", "hind", "hndi", "हिंदी", "हिन्दी", "बात करो", "बात करें"]
        if any(0x0900 <= ord(c) <= 0x097F for c in text) or any(k in normalized for k in hindi_switch):
            return "hi-IN"

        # 3. English switch
        if any(k in normalized for k in ["english", "eng", "in english", "ఇంగ్లీష్", "ఇంగ్లీషు", "इंग्लिश"]):
            return "en-IN"

        return None


def normalize_multilingual_text(text: str) -> str:
    """Normalize whitespace and remove non-speech artifacts."""
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized
