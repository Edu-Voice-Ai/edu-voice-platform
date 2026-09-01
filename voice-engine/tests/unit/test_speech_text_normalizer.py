"""Unit tests for SpeechTextNormalizer ensuring natural voice pronunciation without altering data."""
import pytest
from app.tts.text_normalizer import SpeechTextNormalizer


def test_10_digit_normalization_english():
    """Verify '10-digit' in English becomes 'ten-digit'."""
    raw = "Please tell me your 10-digit mobile number."
    normalized = SpeechTextNormalizer.normalize_for_speech(raw)
    assert normalized == "Please tell me your ten-digit mobile number."


def test_10_digit_normalization_telugish():
    """Verify '10-digit' in Telugish becomes 'ten-digit'."""
    raw = "మీ 10-digit mobile number చెప్పండి."
    normalized = SpeechTextNormalizer.normalize_for_speech(raw)
    assert normalized == "మీ ten-digit mobile number చెప్పండి."


def test_10_digit_normalization_hinglish():
    """Verify '10-digit' in Hinglish becomes 'ten-digit'."""
    raw = "Aap apna 10-digit mobile number batayenge?"
    normalized = SpeechTextNormalizer.normalize_for_speech(raw)
    assert normalized == "Aap apna ten-digit mobile number batayenge?"


def test_descriptor_variations():
    """Verify various casing, space, and hyphen variations."""
    assert SpeechTextNormalizer.normalize_for_speech("10-digit") == "ten-digit"
    assert SpeechTextNormalizer.normalize_for_speech("10 digit") == "ten digit"
    assert SpeechTextNormalizer.normalize_for_speech("10-Digit") == "ten-Digit"
    assert SpeechTextNormalizer.normalize_for_speech("10 DIGIT") == "ten DIGIT"
    assert SpeechTextNormalizer.normalize_for_speech("10 digits") == "ten digits"
    assert SpeechTextNormalizer.normalize_for_speech("12-digit code") == "twelve-digit code"
    assert SpeechTextNormalizer.normalize_for_speech("6 digit OTP") == "six digit OTP"


def test_phone_numbers_preserved():
    """Verify actual phone numbers are NOT converted or modified."""
    assert SpeechTextNormalizer.normalize_for_speech("Your number is 7207702245.") == "Your number is 7207702245."
    assert SpeechTextNormalizer.normalize_for_speech("7207702245 is your number.") == "7207702245 is your number."
    assert SpeechTextNormalizer.normalize_for_speech("Call us at 7207702245.") == "Call us at 7207702245."


def test_other_numeric_data_preserved():
    """Verify fees, years, and codes remain strictly numeric."""
    assert SpeechTextNormalizer.normalize_for_speech("Fee is ₹150000.") == "Fee is ₹150000."
    assert SpeechTextNormalizer.normalize_for_speech("Admissions start in 2027.") == "Admissions start in 2027."
    assert SpeechTextNormalizer.normalize_for_speech("Course code is 102.") == "Course code is 102."
    assert SpeechTextNormalizer.normalize_for_speech("₹10") == "₹10"
