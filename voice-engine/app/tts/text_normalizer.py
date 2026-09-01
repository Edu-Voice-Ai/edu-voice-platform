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
        """
        stripped = text.strip()
        if not stripped:
            return True

        tokens = stripped.split()
        if tokens:
            last_word = tokens[-1].strip(".,!?:;\"'")
            if last_word.lower() in ["mr", "ms", "dr", "sri", "prof", "గౌరవనీయ", "డాక్టర్", "శ్రీ"]:
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
        min_chars: int = 12,
        max_chars: int = 250,
        is_eof: bool = False,
        is_first_chunk: bool = False
    ) -> tuple[str | None, str]:
        """
        Extracts a safe linguistic chunk from the text buffer.
        NEVER splits inside a word, acronym, name, or course title.
        When is_first_chunk is True, extracts the first natural opening clause (6-28 chars)
        as early as possible to minimize time-to-first-audio.
        
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

        # 1. Sentence boundaries (. ! ? । \n), Clause boundaries (, ; : —), or Indic conjunction connectors
        # Clauses must be followed by whitespace and not preceded by digits to prevent breaking numbers like 1,50,000
        for m in re.finditer(r'(?:([.!?।\n])(?:\s+|$)|(?<!\d)([,;:—])\s+|(?<=\S)\s+(మరియు|లేదా)\s+)', working_buffer):
            is_connector = bool(m.group(3))
            end_pos = m.start() if is_connector else m.end()
            candidate = cls.normalize_for_speech(working_buffer[:end_pos].strip())
            delimiter = m.group(1) or m.group(2) or m.group(3)
            min_boundary_len = 3 if is_first_chunk else (min(min_chars, 6) if delimiter in ".!?।\n" else min_chars)
            
            # If is_first_chunk and a natural delimiter was found before 40 chars, extract immediately
            if is_first_chunk:
                if len(candidate) >= min_boundary_len and len(candidate) <= 40 and cls.is_safe_chunk_boundary(candidate):
                    remaining = working_buffer[m.start():].lstrip() if is_connector else working_buffer[end_pos:].lstrip()
                    return candidate, remaining
            else:
                if len(candidate) >= min_boundary_len and cls.is_safe_chunk_boundary(candidate):
                    remaining = working_buffer[m.start():].lstrip() if is_connector else working_buffer[end_pos:].lstrip()
                    return candidate, remaining

        # 1b. For the very first chunk without early punctuation, if buffer reaches 28-35 chars, emit at word boundary
        if is_first_chunk and len(working_buffer) >= 28:
            first_slice = working_buffer[:35]
            space_matches = list(re.finditer(r'\s+', first_slice))
            if space_matches:
                for sm in reversed(space_matches):
                    candidate = cls.normalize_for_speech(working_buffer[:sm.start()].strip())
                    if len(candidate) >= 4 and cls.is_safe_chunk_boundary(candidate):
                        remaining = working_buffer[sm.end():].lstrip()
                        return candidate, remaining

        # 2. If buffer exceeds max_chars, find safe clause or word boundary BEFORE max_chars
        if len(buffer) >= max_chars:
            # 2a. Clause delimiters (, ; : -)
            clause_matches = list(re.finditer(r'([,;:\-])(?:\s+)', buffer[:max_chars]))
            if clause_matches:
                for cm in reversed(clause_matches):
                    end_pos = cm.end()
                    candidate = buffer[:end_pos].strip()
                    if len(candidate) >= min_chars and cls.is_safe_chunk_boundary(candidate):
                        remaining = buffer[end_pos:].lstrip()
                        return candidate, remaining

            # 2b. Word boundary (whitespace)
            space_matches = list(re.finditer(r'\s+', buffer[:max_chars]))
            if space_matches:
                for sm in reversed(space_matches):
                    end_pos = sm.end()
                    candidate = buffer[:end_pos].strip()
                    if len(candidate) >= min_chars and cls.is_safe_chunk_boundary(candidate):
                        remaining = buffer[end_pos:].lstrip()
                        return candidate, remaining

        return None, buffer
