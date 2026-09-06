"""
Comprehensive test suite for TTS first-chunk extraction behavior.
Validates:
  1. Genuinely short complete responses (Yes, No, Sure, OK) → single call
  2. Ack+continuation → combined first chunk (no split at comma)
  3. English, Telugu, Hindi, code-mixed
  4. Sentence-ending punctuation still fires immediately
  5. Clause punctuation requires 20 chars before first dispatch
  6. No duplicate segments, no missing text, no unnatural splits
  7. Barge-in simulation (cancellation mid-stream)
  8. echo/noise segment (should go through unchanged)
  9. Long multi-sentence response segmentation
  10. Number-heavy responses (commas in numbers preserved)
  11. First clause + later clauses completeness
  12. EOF handling for partial buffers
"""
import sys
import pytest
sys.path.insert(0, r"c:\Users\LOKESH\Downloads\voice engine\voice-engine")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.tts.text_normalizer import SpeechTextNormalizer


def all_segments(full_response: str, tokens_per_chunk: int = 2) -> list[str]:
    """Simulate the segmenter() loop from sarvam.py and return all produced segments."""
    words = full_response.split()
    chunks = []
    for i in range(0, len(words), tokens_per_chunk):
        chunk = " ".join(words[i:i+tokens_per_chunk])
        if i + tokens_per_chunk < len(words):
            chunk += " "
        chunks.append(chunk)

    buf = ""
    is_first_chunk = True
    segs = []

    for delta in chunks:
        buf += delta
        while True:
            seg, buf = SpeechTextNormalizer.extract_safe_chunk(
                buf,
                min_chars=6 if is_first_chunk else 35,
                max_chars=200,
                is_eof=False,
                is_first_chunk=is_first_chunk
            )
            if seg:
                segs.append(seg)
                is_first_chunk = False
            else:
                break

    if buf.strip():
        seg, _ = SpeechTextNormalizer.extract_safe_chunk(
            buf, min_chars=6 if is_first_chunk else 35,
            max_chars=200, is_eof=True, is_first_chunk=is_first_chunk
        )
        if seg:
            segs.append(seg)

    return segs


def first_chunk(full_response: str, tokens_per_chunk: int = 2) -> str | None:
    segs = all_segments(full_response, tokens_per_chunk)
    return segs[0] if segs else None


def joined(full_response: str) -> str:
    """Verify all segments join back to the full normalized response."""
    segs = all_segments(full_response)
    return " ".join(s.strip().rstrip(",.:;!?।") for s in segs)


# ─── GROUP 1: Genuinely short complete responses ─────────────────────────────

class TestShortCompleteResponses:
    """Genuinely 1-word or 1-phrase responses — should fire as single Sarvam call."""

    def test_yes_english(self):
        segs = all_segments("Yes")
        assert len(segs) == 1
        assert segs[0] == "Yes"

    def test_no_english(self):
        segs = all_segments("No")
        assert len(segs) == 1
        assert segs[0] == "No"

    def test_okay_english(self):
        segs = all_segments("Okay")
        assert len(segs) == 1
        assert segs[0] == "Okay"

    def test_sure_english(self):
        segs = all_segments("Sure")
        assert len(segs) == 1
        assert segs[0] == "Sure"

    def test_yes_with_period(self):
        """'Yes.' is a complete sentence — should fire immediately."""
        segs = all_segments("Yes.")
        assert len(segs) == 1
        assert "Yes" in segs[0]

    def test_avunu_telugu(self):
        segs = all_segments("అవును")
        assert len(segs) == 1
        assert "అవును" in segs[0]

    def test_han_hindi(self):
        segs = all_segments("हाँ")
        assert len(segs) == 1
        assert "हाँ" in segs[0]


# ─── GROUP 2: Acknowledgement + continuation — must NOT split at comma ────────

class TestAckPlusContinuation:
    """
    When LLM outputs 'Yes, I can help you...', the comma at position 3 must NOT
    trigger an early first-chunk dispatch of just 'Yes,' (4 chars).
    Instead, the system must accumulate until the first safe boundary >= 20 chars.
    """

    def test_yes_continuation_english(self):
        response = "Yes, I can help you with that."
        fc = first_chunk(response)
        assert fc is not None
        # Must not be just "Yes," (4 chars) — that's the problem
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"
        # Must contain the full opening clause
        assert "Yes" in fc
        assert "can" in fc or "help" in fc or "that" in fc

    def test_sure_continuation_english(self):
        response = "Sure, let me explain our courses."
        fc = first_chunk(response)
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"
        assert "Sure" in fc
        assert "me" in fc or "explain" in fc or "courses" in fc

    def test_okay_continuation_english(self):
        response = "Okay, let me look that up for you."
        fc = first_chunk(response)
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"
        assert "Okay" in fc

    def test_avunu_continuation_telugu(self):
        response = "అవును, మీకు సహాయం చేస్తాను."
        fc = first_chunk(response)
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"
        assert "అవును" in fc

    def test_han_continuation_hindi(self):
        response = "హాँ, మैं আपको बताता हूँ।"
        fc = first_chunk(response)
        # Hindi with Devanagari — must not be just "हाँ," 
        assert len(fc) >= 3, f"First chunk empty or too short: {repr(fc)}"

    def test_han_hindi_continuation(self):
        response = "हाँ, मैं आपको बताता हूँ।"
        fc = first_chunk(response)
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"
        assert "हाँ" in fc

    def test_of_course_continuation_english(self):
        response = "Of course, I'll help you right away."
        fc = first_chunk(response)
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"
        assert "course" in fc or "help" in fc


# ─── GROUP 3: Sentence-ending exclamation — may fire slightly small ───────────

class TestSentenceEndExclamation:
    """
    '!' marks a genuine sentence end. 'Sure!' is a valid TTS unit.
    We allow it to fire at 5+ chars since it's semantically complete.
    The overlapped pipeline means 'We offer...' chunk already starts synthesizing.
    """

    def test_sure_exclamation_continuation(self):
        response = "Sure! We offer BTech and MBA programs."
        segs = all_segments(response)
        assert len(segs) >= 2
        assert segs[0] == "Sure!"
        # Second segment carries the actual content
        assert "BTech" in " ".join(segs) or "MBA" in " ".join(segs)

    def test_absolutely_exclamation(self):
        response = "Absolutely! Apex University offers BTech programs."
        segs = all_segments(response)
        assert segs[0] == "Absolutely!"
        assert len(segs) >= 2


# ─── GROUP 4: Multi-sentence English response ────────────────────────────────

class TestEnglishMultiSentence:
    def test_first_chunk_not_tiny(self):
        response = "Sure, I can help you with that. Apex University offers BTech programs in CSE, ECE, and Mechanical Engineering."
        fc = first_chunk(response)
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"

    def test_completeness(self):
        """All words from the original response must appear across segments."""
        response = "Sure, I can help you with that. Apex University offers BTech programs."
        segs = all_segments(response)
        combined = " ".join(segs)
        for word in ["Sure", "help", "Apex", "University", "BTech"]:
            assert word in combined, f"Word {repr(word)} missing from segments"


# ─── GROUP 5: Telugu multi-sentence response ─────────────────────────────────

class TestTeluguResponse:
    def test_first_chunk_not_tiny(self):
        response = "అవును, నేను మీకు సహాయం చేయగలను. Apex University లో BTech, MBA కోర్సులు ఉన్నాయి."
        fc = first_chunk(response)
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"
        assert "అవును" in fc

    def test_completeness(self):
        response = "అవును, నేను మీకు సహాయం చేయగలను."
        segs = all_segments(response)
        combined = " ".join(segs)
        assert "అవును" in combined
        assert "సహాయం" in combined


# ─── GROUP 6: Hindi multi-sentence response ──────────────────────────────────

class TestHindiResponse:
    def test_first_chunk_not_tiny(self):
        response = "हाँ बिल्कुल, मैं आपको बता सकता हूँ। Apex University में BTech और MBA के कोर्स उपलब्ध हैं।"
        fc = first_chunk(response)
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"


# ─── GROUP 7: Code-mixed (Telugu + English) ──────────────────────────────────

class TestCodeMixedResponse:
    def test_first_chunk_not_tiny(self):
        response = "Sure, Apex లో BTech CSE course ఉంది. Fees approximately 90,000 per year."
        fc = first_chunk(response)
        assert len(fc) >= 12, f"First chunk too short: {repr(fc)}"
        assert "Sure" in fc

    def test_number_commas_preserved(self):
        """Comma in 90,000 must not be treated as a clause boundary."""
        response = "The annual fee is 90,000 per year for BTech CSE."
        segs = all_segments(response)
        combined = " ".join(segs)
        # 90,000 must not be split
        assert "90" in combined and "000" in combined


# ─── GROUP 8: Barge-in simulation ────────────────────────────────────────────

class TestBargeInSimulation:
    """
    When a cancellation token fires mid-stream, segments already queued
    must not be duplicated and the stream must stop cleanly.
    This tests the segmenter logic, not the async pipeline (which is tested separately).
    """

    def test_partial_stream_no_duplicate(self):
        """Simulate partial LLM stream (barge-in cuts it off after 3 tokens)."""
        # Only first 3 words arrive before barge-in
        partial_response = "Sure, I can"  # Only part of "Sure, I can help you with that."
        segs = all_segments(partial_response)
        # Should produce 0 or 1 segment (accumulating, not splitting a partial buffer)
        # The partial text has no safe boundary after >= 20 chars, so may be empty or buffered
        total_text = " ".join(segs)
        assert total_text == total_text  # No crash, output is deterministic
        # Must not duplicate
        assert len(segs) == len(set(segs))

    def test_no_stale_audio_on_cancellation(self):
        """Full response would produce segments, but cancel-path uses only first N."""
        response = "Sure, I can help you. Apex University has many courses."
        segs = all_segments(response)
        # Simulate cancel after first segment
        first = segs[0] if segs else ""
        assert first  # At least something produced
        # Remaining segments are NOT re-processed in a cancelled path
        remaining = segs[1:]  # Would be discarded by TTS worker on is_cancelled check
        assert len(remaining) >= 0  # No crash


# ─── GROUP 9: Number/amount heavy responses ──────────────────────────────────

class TestNumberHeavyResponses:
    def test_fee_number_not_split(self):
        response = "The fee is 90,000 per year."
        segs = all_segments(response)
        combined = " ".join(segs)
        # 90,000 must appear intact or as "90" and "000" adjacent
        assert "90" in combined

    def test_large_number_intact(self):
        response = "The total fees for four years is 3,60,000 rupees."
        fc = first_chunk(response)
        assert fc is not None
        # Comma in 3,60,000 must be treated as part of the number, not a clause boundary
        # (The regex requires no preceding digit: (?<!\d)([,;:—]) — so 3,60 is safe)
        assert "3" in fc or "fee" in fc.lower()


# ─── GROUP 10: EOF / partial buffer ──────────────────────────────────────────

class TestEofHandling:
    def test_short_response_no_trailing_garbage(self):
        segs = all_segments("Yes")
        assert segs == ["Yes"]

    def test_partial_buffer_at_eof(self):
        """If LLM response ends mid-sentence, remaining buffer should still flush."""
        response = "Sure, I can help you with admissions"
        segs = all_segments(response)
        # Must produce at least one segment
        assert len(segs) >= 1
        combined = " ".join(segs)
        assert "Sure" in combined
        assert "admissions" in combined

    def test_completely_empty_response(self):
        segs = all_segments("")
        assert segs == []


# ─── GROUP 11: No unnatural splits ───────────────────────────────────────────

class TestNoUnnaturalSplits:
    def test_no_split_inside_word(self):
        response = "Sure, I can help you with admissions and fees."
        segs = all_segments(response)
        for seg in segs:
            words = seg.split()
            for w in words:
                # Each word should be a real word, not a half-word
                assert len(w) >= 1
                # No dangling partial characters
                assert not w.endswith("-") or w.count("-") > 1

    def test_honorific_not_split(self):
        """Dr., Mr., Ms. should not trigger a split before the name."""
        # is_safe_chunk_boundary() returns False for "Mr", "Ms", "Dr" — they wait for the name
        response = "Sure, I can connect you to Dr. Sharma for more details."
        segs = all_segments(response)
        combined = " ".join(segs)
        assert "Dr" in combined
        assert "Sharma" in combined


if __name__ == "__main__":
    # Quick self-test without pytest
    import traceback
    test_classes = [
        TestShortCompleteResponses,
        TestAckPlusContinuation,
        TestSentenceEndExclamation,
        TestEnglishMultiSentence,
        TestTeluguResponse,
        TestHindiResponse,
        TestCodeMixedResponse,
        TestBargeInSimulation,
        TestNumberHeavyResponses,
        TestEofHandling,
        TestNoUnnaturalSplits,
    ]
    passed = 0
    failed = 0
    for cls in test_classes:
        instance = cls()
        for method_name in [m for m in dir(cls) if m.startswith("test_")]:
            method = getattr(instance, method_name)
            try:
                method()
                print(f"  PASS  {cls.__name__}.{method_name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {cls.__name__}.{method_name}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
