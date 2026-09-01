"""Unit tests for Telugu fluency, name continuity, acronyms, and TTS chunking."""
import pytest
from app.tts.text_normalizer import SpeechTextNormalizer


def test_name_and_honorific_normalization():
    """Verify names and honorifics are normalized cleanly without orphan punctuation."""
    raw = "Namaskaram Aravind Kumar garu , how can I help you?"
    normalized = SpeechTextNormalizer.normalize_for_speech(raw)
    assert "Aravind Kumar garu," in normalized


def test_telugu_name_and_honorific():
    """Verify Telugu native script names with honorifics."""
    raw = "నమస్కారం అరవింద్ కుమార్ గారు , మీకు ఏ సమాచారం కావాలి?"
    normalized = SpeechTextNormalizer.normalize_for_speech(raw)
    assert "అరవింద్ కుమార్ గారు," in normalized


def test_acronym_normalization():
    """Verify educational acronyms are normalized for fluid pronunciation."""
    assert SpeechTextNormalizer.normalize_for_speech("B.Tech in C.S.E.") == "BTech in CSE."
    assert SpeechTextNormalizer.normalize_for_speech("M.Tech and Ph.D") == "MTech and PhD"
    assert SpeechTextNormalizer.normalize_for_speech("U.G. and P.G. courses") == "UG and PG courses"


def test_safe_chunk_boundary():
    """Verify boundary checks protect names and prefixes."""
    assert SpeechTextNormalizer.is_safe_chunk_boundary("Mr.") is False
    assert SpeechTextNormalizer.is_safe_chunk_boundary("Dr.") is False
    assert SpeechTextNormalizer.is_safe_chunk_boundary("Aravind") is False
    assert SpeechTextNormalizer.is_safe_chunk_boundary("Aravind Kumar.") is True
    assert SpeechTextNormalizer.is_safe_chunk_boundary("మా దగ్గర BTech CSE course ఉంది.") is True


def test_extract_safe_chunk_telugu_sentence_boundary():
    """Verify Telugu sentences are split at sentence boundaries without splitting words."""
    text = "మా దగ్గర UG, PG, ఇంకా diploma courses ఉన్నాయి. మీకు ఏ course గురించి details కావాలి?"
    
    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(text, min_chars=40, max_chars=250, is_eof=False)
    assert chunk1 == "మా దగ్గర UG, PG, ఇంకా diploma courses ఉన్నాయి."
    assert rest1 == "మీకు ఏ course గురించి details కావాలి?"

    chunk2, rest2 = SpeechTextNormalizer.extract_safe_chunk(rest1, min_chars=40, max_chars=250, is_eof=True)
    assert chunk2 == "మీకు ఏ course గురించి details కావాలి?"
    assert rest2 == ""


def test_extract_safe_chunk_no_mid_word_splitting():
    """Verify stream fed word-by-word or character-by-character never slices words in half."""
    text = "Your counsellor is Aravind Kumar. The admission process for Computer Science and Engineering is open."
    
    # Simulate gradual streaming
    buf = ""
    chunks = []
    for char in text:
        buf += char
        chunk, buf = SpeechTextNormalizer.extract_safe_chunk(buf, min_chars=30, max_chars=100, is_eof=False)
        if chunk:
            chunks.append(chunk)

    final_chunk, _ = SpeechTextNormalizer.extract_safe_chunk(buf, min_chars=30, max_chars=100, is_eof=True)
    if final_chunk:
        chunks.append(final_chunk)

    full_reconstructed = " ".join(chunks)
    # Check that critical words and names are intact
    assert "Aravind Kumar." in chunks[0]
    assert "Computer Science and Engineering" in full_reconstructed
    assert not any("admis" in c and "sion" not in c for c in chunks)
    assert not any("Engin" in c and "eering" not in c for c in chunks)


def test_extract_safe_chunk_oversized_fallback():
    """Verify oversized text without period falls back to last whitespace before max_chars."""
    long_sentence = (
        "We offer a four year undergraduate Bachelor of Technology degree in Computer Science and Engineering "
        "with multiple specializations including Artificial Intelligence and Machine Learning as well as Data Science"
    )
    chunk, rest = SpeechTextNormalizer.extract_safe_chunk(long_sentence, min_chars=40, max_chars=120, is_eof=False)
    assert chunk is not None
    # Must end at a complete word, not mid-word
    last_word = chunk.split()[-1]
    assert last_word in ["multiple", "Engineering", "Science", "degree"]
    assert len(chunk) <= 120
    assert not chunk.endswith("multi") and not chunk.endswith("Engin")
