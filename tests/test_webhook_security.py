"""Unit tests for cryptographic webhook signature verification."""

import time

from backend.app.services.telephony.security.verifier import (
    HMACSHA256WebhookVerifier,
)


def test_hmac_verifier_valid_signature(
    mock_webhook_secret: str,
    sign_payload,
) -> None:
    """Test verification succeeds with exact valid HMAC-SHA256 signature."""
    verifier = HMACSHA256WebhookVerifier()
    payload = (
        b'{"call_sid":"123","from_number":"+919999999999","to_number":"+918888888888"}'
    )
    sig = sign_payload(payload, None)

    res = verifier.verify(
        payload_bytes=payload,
        signature=sig,
        secret=mock_webhook_secret,
    )
    assert res.is_valid is True
    assert res.error_message is None


def test_hmac_verifier_valid_signature_with_prefix(
    mock_webhook_secret: str,
    sign_payload,
) -> None:
    """Test verification handles 'v1=...' or 'sha256=...' signature formats."""
    verifier = HMACSHA256WebhookVerifier()
    payload = b'{"call_sid":"123"}'
    raw_sig = sign_payload(payload, None)
    prefixed_sig = f"v1={raw_sig}"

    res = verifier.verify(
        payload_bytes=payload,
        signature=prefixed_sig,
        secret=mock_webhook_secret,
    )
    assert res.is_valid is True


def test_hmac_verifier_invalid_signature(mock_webhook_secret: str) -> None:
    """Test verification fails with incorrect signature string."""
    verifier = HMACSHA256WebhookVerifier()
    payload = b'{"call_sid":"123"}'
    wrong_sig = "a" * 64

    res = verifier.verify(
        payload_bytes=payload,
        signature=wrong_sig,
        secret=mock_webhook_secret,
    )
    assert res.is_valid is False
    assert "Invalid webhook signature" in (res.error_message or "")


def test_hmac_verifier_missing_or_empty_signature(mock_webhook_secret: str) -> None:
    """Test verification fails when signature is None or empty."""
    verifier = HMACSHA256WebhookVerifier()
    payload = b'{"call_sid":"123"}'

    res_none = verifier.verify(
        payload_bytes=payload,
        signature=None,
        secret=mock_webhook_secret,
    )
    assert res_none.is_valid is False
    assert "Missing or empty signature" in (res_none.error_message or "")

    res_empty = verifier.verify(
        payload_bytes=payload,
        signature="   ",
        secret=mock_webhook_secret,
    )
    assert res_empty.is_valid is False


def test_hmac_verifier_unconfigured_secret() -> None:
    """Test verification fails gracefully if server secret is not set."""
    verifier = HMACSHA256WebhookVerifier()
    payload = b'{"call_sid":"123"}'

    res = verifier.verify(
        payload_bytes=payload,
        signature="some_sig",
        secret="",
    )
    assert res.is_valid is False
    assert "Server secret is unconfigured" in (res.error_message or "")


def test_hmac_verifier_timestamp_replay_protection(
    mock_webhook_secret: str,
    sign_payload,
) -> None:
    """Test timestamp header drift within and outside tolerance window."""
    verifier = HMACSHA256WebhookVerifier()
    payload = b'{"call_sid":"123"}'
    now = int(time.time())

    # Valid timestamp within 300s window
    sig = sign_payload(payload, now)
    res_valid = verifier.verify(
        payload_bytes=payload,
        signature=sig,
        timestamp_header=str(now),
        secret=mock_webhook_secret,
        tolerance_seconds=300,
    )
    assert res_valid.is_valid is True

    # Expired timestamp (10 minutes in past)
    old_ts = now - 600
    old_sig = sign_payload(payload, old_ts)
    res_expired = verifier.verify(
        payload_bytes=payload,
        signature=old_sig,
        timestamp_header=str(old_ts),
        secret=mock_webhook_secret,
        tolerance_seconds=300,
    )
    assert res_expired.is_valid is False
    assert "acceptable tolerance window" in (res_expired.error_message or "")


def test_hmac_verifier_malformed_timestamp(mock_webhook_secret: str) -> None:
    """Test malformed non-integer timestamp header."""
    verifier = HMACSHA256WebhookVerifier()
    payload = b'{"call_sid":"123"}'

    res = verifier.verify(
        payload_bytes=payload,
        signature="abc",
        timestamp_header="not_a_number_timestamp",
        secret=mock_webhook_secret,
    )
    assert res.is_valid is False
    assert "Invalid timestamp header" in (res.error_message or "")


def test_hmac_verifier_raw_payload_success(
    mock_webhook_secret: str, sign_payload
) -> None:
    """Test HMAC verifier verifies payload bytes without timestamp header."""
    verifier = HMACSHA256WebhookVerifier()
    payload = b'{"call_sid":"call_raw_test_1"}'
    sig = sign_payload(payload, None)

    res = verifier.verify(
        payload_bytes=payload,
        signature=sig,
        secret=mock_webhook_secret,
    )
    assert res.is_valid is True
