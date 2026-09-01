"""Unit tests verifying first-chunk prioritization for ultra-fast time-to-first-audio synthesis."""
import pytest
from app.tts.text_normalizer import SpeechTextNormalizer


def test_first_chunk_prioritizes_introductory_clause():
    """Verify first chunk emits opening clause early to minimize time to first audio."""
    text = "Sure, we offer BTech CSE and ECE programs at Apex University."
    
    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        text, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    assert chunk1 == "Sure,"
    assert rest1 == "we offer BTech CSE and ECE programs at Apex University."

    # Subsequent chunk uses normal min_chars
    chunk2, rest2 = SpeechTextNormalizer.extract_safe_chunk(
        rest1, min_chars=35, max_chars=180, is_eof=True, is_first_chunk=False
    )
    assert chunk2 == "we offer BTech CSE and ECE programs at Apex University."
    assert rest2 == ""


def test_first_chunk_telugu_opening_clause():
    """Verify Telugu conversational opener ('సరేనండి,') is emitted as chunk 1."""
    text = "సరేనండి, మా దగ్గర BTech CSE మరియు ECE courses ఉన్నాయి."

    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        text, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    assert chunk1 == "సరేనండి,"
    assert rest1 == "మా దగ్గర BTech CSE మరియు ECE courses ఉన్నాయి."

    chunk2, rest2 = SpeechTextNormalizer.extract_safe_chunk(
        rest1, min_chars=35, max_chars=180, is_eof=True, is_first_chunk=False
    )
    assert chunk2 == "మా దగ్గర BTech CSE మరియు ECE courses ఉన్నాయి."
    assert rest2 == ""


def test_first_chunk_telugu_connector_boundary():
    """Verify Telugu sentence without comma splits safely at connector ('మరియు')."""
    text = "మా దగ్గర BTech CSE మరియు ECE courses అందుబాటులో ఉన్నాయి."

    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        text, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    assert chunk1 == "మా దగ్గర BTech CSE"
    assert "ECE courses" in rest1


def test_first_chunk_word_boundary_fallback():
    """Verify first chunk emits at safe word boundary around 28-35 chars if no punctuation exists."""
    text = "Apex University provides comprehensive four year undergraduate degree programs in engineering."

    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        text, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    assert chunk1 is not None
    assert len(chunk1) <= 35
    # Must end on a clean full word, not sliced
    last_word = chunk1.split()[-1]
    assert last_word in ["provides", "University", "Apex", "comprehensive"]
    assert not chunk1.endswith("provi")
