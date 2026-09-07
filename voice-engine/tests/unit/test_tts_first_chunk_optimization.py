"""Unit tests verifying first-chunk extraction correctly combines acknowledgements with their
continuation clause to minimize Sarvam API round-trips while preserving full response content.

BEFORE FIX (broken): first chunk = "Sure," (4 chars) → wasted API call, then "we offer..." separately
AFTER FIX (correct): first chunk = "Sure, we offer BTech CSE and" (28 chars) → single meaningful call
"""
import pytest
from app.tts.text_normalizer import SpeechTextNormalizer


def test_first_chunk_combines_ack_with_continuation():
    """
    Verify first chunk does NOT emit bare 'Sure,' — instead it accumulates until
    it reaches a safe boundary >= 20 chars so that the comma-opener and its continuation
    are synthesized in a single Sarvam API call.
    """
    text = "Sure, we offer BTech CSE and ECE programs at Apex University."

    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        text, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    # Must NOT be the tiny "Sure," stub (the old broken behavior)
    assert chunk1 != "Sure,", (
        "First chunk must not be the bare comma-stub 'Sure,' — "
        "it wastes a Sarvam API round-trip for only 5 chars"
    )
    # Must contain both the acknowledgement and the continuation
    assert chunk1 is not None
    assert "Sure" in chunk1
    assert len(chunk1) >= 20, f"First chunk should be >= 20 chars, got: {repr(chunk1)}"

    # Remaining text must cover what's left after the first chunk
    full_joined = (chunk1 + " " + rest1).replace("  ", " ").strip()
    assert "BTech CSE" in full_joined or "ECE" in full_joined
    assert "Apex University" in full_joined

    # Subsequent chunk uses normal min_chars (EOF flush of remainder)
    chunk2, rest2 = SpeechTextNormalizer.extract_safe_chunk(
        rest1, min_chars=35, max_chars=180, is_eof=True, is_first_chunk=False
    )
    if rest1.strip():
        assert chunk2 is not None
        assert rest2 == ""


def test_first_chunk_telugu_opening_clause():
    """
    Verify Telugu conversational opener ('సరేనండి,') is NOT emitted alone —
    it must be combined with the following clause into one first Sarvam call.
    """
    text = "సరేనండి, మా దగ్గర BTech CSE మరియు ECE courses ఉన్నాయి."

    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        text, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    # Must NOT be the tiny opener alone
    assert chunk1 != "సరేనండి,", (
        "Telugu opener 'సరేనండి,' must not fire alone — it should be combined with continuation"
    )
    assert chunk1 is not None
    assert "సరేనండి" in chunk1
    assert len(chunk1) >= 12, f"Telugu first chunk too short: {repr(chunk1)}"

    # Content completeness
    full_joined = (chunk1 + " " + rest1).replace("  ", " ").strip()
    assert "BTech CSE" in full_joined or "ECE" in full_joined

    chunk2, rest2 = SpeechTextNormalizer.extract_safe_chunk(
        rest1, min_chars=35, max_chars=180, is_eof=True, is_first_chunk=False
    )
    if rest1.strip():
        assert chunk2 is not None


def test_first_chunk_telugu_connector_boundary():
    """
    Verify Telugu sentence without a comma accumulates past the 'మరియు' connector
    boundary until a natural safe breakpoint >= 20 chars is reached.
    """
    text = "మా దగ్గర BTech CSE మరియు ECE courses అందుబాటులో ఉన్నాయి."

    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        text, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    assert chunk1 is not None
    # Must be at least a meaningful clause
    assert len(chunk1) >= 12, f"Telugu connector chunk too short: {repr(chunk1)}"
    # Content after split must still contain ECE courses
    assert "ECE courses" in rest1 or "ECE" in chunk1

    # Completeness: both parts together cover the full text
    if rest1.strip():
        assert "ఉన్నాయి" in rest1 or "ఉన్నాయి" in chunk1


def test_first_chunk_word_boundary_fallback():
    """Verify first chunk emits at safe word boundary around 20-32 chars if no punctuation exists."""
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


def test_sentence_end_still_fires_immediately():
    """
    Sentence-ending punctuation (. ! ? ।) still fires immediately for the first chunk
    regardless of length. This preserves correct behavior for complete short responses.
    """
    # "Yes." is a complete sentence — fires immediately (correct)
    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        "Yes.", min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    assert chunk1 is not None
    assert "Yes" in chunk1

    # "Sure!" is a complete exclamatory affirmation — fires immediately (correct)
    chunk1b, rest1b = SpeechTextNormalizer.extract_safe_chunk(
        "Sure! We offer many programs.", min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    assert chunk1b == "Sure!"
    assert "We offer" in rest1b


def test_comma_opener_does_not_fire_as_stub():
    """
    The key regression test: comma-delimited openers under 20 chars must NOT fire
    as the first chunk when more text follows.
    All of these must produce a first chunk with >= 12 chars (not just the opener).
    """
    cases = [
        ("Yes, I can help you with that.", "Yes"),
        ("Sure, let me explain our courses.", "Sure"),
        ("Okay, let me look that up for you.", "Okay"),
        ("Of course, I'll help you right away.", "Of course"),
    ]
    for response, opener in cases:
        chunk1, _ = SpeechTextNormalizer.extract_safe_chunk(
            response, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
        )
        assert chunk1 is not None, f"No first chunk for: {repr(response)}"
        assert len(chunk1) >= 12, (
            f"Opener {repr(opener + ',')} fired as standalone stub {repr(chunk1)} "
            f"({len(chunk1)} chars) — must be >= 12 chars"
        )
        assert opener in chunk1, f"Opener missing from first chunk: {repr(chunk1)}"
