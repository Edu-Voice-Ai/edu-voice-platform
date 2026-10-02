"""Speech text normalizer to ensure natural pronunciation of numeric descriptors, acronyms, and names."""
import re
from typing import Dict

DIGIT_DESCRIPTOR_MAP: Dict[str, str] = {
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
    "11": "eleven",
    "12": "twelve"
}

# Matches explicit descriptors like "10-digit", "10 digit", "10 digits", "10-Digit"
DESCRIPTOR_PATTERN = re.compile(
    r'\b(2|3|4|5|6|7|8|9|10|11|12)([ -]?)(digits?)\b',
    re.IGNORECASE
)


class SpeechTextNormalizer:
    """Normalizes written text for natural TTS pronunciation while preserving data integrity."""

    @classmethod
    def normalize_for_speech(cls, text: str) -> str:
        """
        Normalizes descriptors ('10-digit' -> 'ten-digit'), standardizes acronyms for fluent TTS,
        and cleans whitespace while keeping names and numbers intact.
        """
        if not text:
            return text

        # 0. Strip internal reasoning tags and markdown formatting
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'[*_~`#>]', '', text)
        text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)

        # 1. Normalize numeric descriptors
        def _replace_descriptor(match: re.Match) -> str:
            num = match.group(1)
            sep = match.group(2)
            word = match.group(3)
            word_equiv = DIGIT_DESCRIPTOR_MAP.get(num, num)
            return f"{word_equiv}{sep}{word}"

        normalized = DESCRIPTOR_PATTERN.sub(_replace_descriptor, text)

        # 2. Normalize acronym punctuation for fluid TTS without awkward letter-pauses
        normalized = re.sub(r'\bB\.Tech\b', 'BTech', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\bM\.Tech\b', 'MTech', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\bPh\.D\b', 'PhD', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\b([A-Za-z])\.([A-Za-z])\.([A-Za-z])\.', r'\1\2\3.', normalized)
        normalized = re.sub(r'\b([A-Za-z])\.([A-Za-z])\.', r'\1\2', normalized)
        normalized = re.sub(r'\b([A-Za-z])\.([A-Za-z])\b', r'\1\2', normalized)

        # 3. Clean up any weird double spaces or orphan punctuation around honorifics
        normalized = re.sub(r'\s+([,!?।])', r'\1', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    @classmethod
    def is_safe_chunk_boundary(cls, text: str) -> bool:
        """
        Checks if the end of text is a safe chunk boundary that won't split:
        - Multi-word capitalized names (e.g. 'Aravind Kumar', 'Lokesh Reddy')
        - Name + honorific combinations (e.g. 'Aravind garu', 'అరవింద్ గారు')
        - Multi-word course names (e.g. 'Computer Science', 'BTech CSE')
        - Business / institution names (e.g. 'Apex University')
        - Prepositions and conjunctions (e.g. 'in', 'and', 'from', 'at', 'of')
        """
        stripped = text.strip()
        if not stripped:
            return True

        tokens = stripped.split()
        if not tokens:
            return True

        last_word = tokens[-1].strip(".,!?:;\"'()[]")
        last_word_lower = last_word.lower()

        # 1. Trailing prepositions and conjunctions must NEVER end a spoken chunk
        dangling_connectors = {
            "in", "and", "or", "of", "for", "at", "to", "from", "with", "by", "on", "into", "onto",
            "as", "the", "a", "an", "is", "are", "was", "were", "and/or",
            "మరియు", "లేదా", "యొక్క", "లో", "నుండి", "తో", "గా", "కోసం"
        }
        if last_word_lower in dangling_connectors:
            return False

        # 2. Honorifics and titles
        honorifics = {"mr", "ms", "mrs", "dr", "sri", "prof", "shri", "smt", "గౌరవనీయ", "డాక్టర్", "శ్రీ"}
        if last_word_lower in honorifics:
            return False

        # 3. Institution / organization prefix words (e.g. 'Apex' before 'University')
        org_prefixes = {"apex", "saint", "st", "mount"}
        if last_word_lower in org_prefixes:
            return False

        # 4. Degree / branch abbreviations (e.g. 'BTech' before 'Computer Science', 'CSE', etc.)
        degree_words = {"btech", "mtech", "bba", "mba", "bsc", "msc", "phd", "b.tech", "m.tech"}
        if last_word_lower in degree_words and stripped[-1] not in [".", "!", "?", "।"]:
            return False

        # 5. Course / department prefix words
        course_prefixes = {"computer", "electronics", "data", "mechanical", "electrical", "civil"}
        if last_word_lower in course_prefixes:
            return False

        if len(tokens) == 1:
            # If single word has clause/sentence punctuation (e.g. 'Sure,', 'Hello!', 'Yes.'), it's safe
            if stripped[-1] in [",", ".", "!", "?", "।", ":", ";"]:
                return True
            # Unpunctuated single title word (e.g. 'Aravind') should wait for last name
            if last_word.istitle() and len(last_word) > 1:
                return False

        return True

    @classmethod
    def extract_safe_chunk(
        cls,
        buffer: str,
        min_chars: int = 35,
        max_chars: int = 250,
        is_eof: bool = False,
        is_first_chunk: bool = False
    ) -> tuple[str | None, str]:
        """
        Extracts a safe linguistic chunk from the text buffer.
        NEVER splits inside a word, acronym, name, course title, or between prepositions and nouns.

        Rules:
          - Does NOT dispatch standalone tiny fragments ("Hello!", "Sure!") when more text is available.
          - Prefers complete sentences.
          - When is_eof is True (entire response or stream ended), flushes the full remaining text as a clean unit.
          - Never splits unpunctuated text at arbitrary character boundaries.
        
        Returns:
            (extracted_chunk, remaining_buffer)
            extracted_chunk is None if buffer should continue accumulating.
        """
        if not buffer:
            return None, ""

        if is_eof:
            clean = cls.normalize_for_speech(buffer.strip())
            return (clean if clean else None), ""

        # Normalize abbreviations like B.Tech -> BTech before splitting on periods
        working_buffer = re.sub(r'\bB\.Tech\b', 'BTech', buffer, flags=re.IGNORECASE)
        working_buffer = re.sub(r'\bM\.Tech\b', 'MTech', working_buffer, flags=re.IGNORECASE)
        working_buffer = re.sub(r'\bPh\.D\b', 'PhD', working_buffer, flags=re.IGNORECASE)
        working_buffer = re.sub(r'\b([A-Za-z])\.([A-Za-z])\b', r'\1\2', working_buffer)

        # 1. Prefer complete sentence-terminal punctuation: (. ! ? । \n)
        # We do NOT treat comma, semicolon, or Indic conjunctions as normal chunk boundaries.
        # This keeps natural sentences intact (up to ~180 chars) and prevents acoustic/prosody discontinuities.
        for m in re.finditer(r'([.!?।\n])(?:\s+|$)', working_buffer):
            end_pos = m.end()
            candidate = cls.normalize_for_speech(working_buffer[:end_pos].strip())
            if not candidate:
                continue

            # Verify that the punctuation mark is not part of a protected abbreviation or title
            if not cls.is_safe_chunk_boundary(candidate):
                continue

            # When streaming, avoid dispatching tiny fragments (< 20 chars, e.g. "Sure!", "Yes.")
            # early if more text is being generated.
            if is_first_chunk and len(candidate) < 20:
                continue

            remaining = working_buffer[end_pos:].lstrip()
            return candidate, remaining

        # 2. Oversized Fallback: If buffer exceeds max_chars without sentence-terminal punctuation,
        # find safe clause boundary (, ; : -) or whitespace BEFORE max_chars to avoid buffer overflow.
        if len(working_buffer) >= max_chars:
            # 2a. Clause delimiters (, ; : -) followed by whitespace, not preceded by digits
            clause_matches = list(re.finditer(r'(?<!\d)([,;:\-])\s+', working_buffer[:max_chars]))
            if clause_matches:
                for cm in reversed(clause_matches):
                    end_pos = cm.end()
                    candidate = cls.normalize_for_speech(working_buffer[:end_pos].strip())
                    if len(candidate) >= min_chars and cls.is_safe_chunk_boundary(candidate):
                        remaining = working_buffer[end_pos:].lstrip()
                        return candidate, remaining

            # 2b. Word boundary (whitespace)
            space_matches = list(re.finditer(r'\s+', working_buffer[:max_chars]))
            if space_matches:
                for sm in reversed(space_matches):
                    end_pos = sm.end()
                    candidate = cls.normalize_for_speech(working_buffer[:end_pos].strip())
                    if len(candidate) >= min_chars and cls.is_safe_chunk_boundary(candidate):
                        remaining = working_buffer[end_pos:].lstrip()
                        return candidate, remaining

        return None, buffer
