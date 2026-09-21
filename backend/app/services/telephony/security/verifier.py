"""Cryptographic webhook signature verification framework.

Enforces timing-safe comparisons and replay protection while isolating
provider-specific signing adapters behind explicit interface boundaries.
"""

import abc
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger("telephony.security")


@dataclass(frozen=True)
class WebhookVerificationResult:
    """Outcome of signature verification."""

    is_valid: bool
    error_message: str | None = None


class BaseWebhookVerifier(abc.ABC):
    """Abstract interface for webhook signature verification."""

    @abc.abstractmethod
    def verify(
        self,
        payload_bytes: bytes,
        signature: str | None,
        timestamp_header: str | None = None,
        secret: str = "",
        tolerance_seconds: int = 300,
    ) -> WebhookVerificationResult:
        """Verify the webhook payload authenticity and integrity."""


class HMACSHA256WebhookVerifier(BaseWebhookVerifier):
    """Timing-safe HMAC-SHA256 signature verifier with replay attack protection.

    Generates HMAC-SHA256 hex digest over either the raw payload or
    (timestamp + '.' + payload) when timestamp header is supplied.
    """

    def verify(
        self,
        payload_bytes: bytes,
        signature: str | None,
        timestamp_header: str | None = None,
        secret: str = "",
        tolerance_seconds: int = 300,
    ) -> WebhookVerificationResult:
        """Verify HMAC-SHA256 signature using constant-time comparison."""
        if not secret:
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Webhook verification failed: Server secret is unconfigured",
            )

        if not signature or not signature.strip():
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Missing or empty signature header",
            )

        # Check timestamp replay protection if timestamp is provided
        if timestamp_header:
            try:
                ts = int(timestamp_header.strip())
                now = int(time.time())
                if abs(now - ts) > tolerance_seconds:
                    logger.warning(
                        "Webhook timestamp drift exceeded tolerance: drift=%s, max_tolerance=%s",
                        abs(now - ts),
                        tolerance_seconds,
                    )
                    return WebhookVerificationResult(
                        is_valid=False,
                        error_message="Webhook timestamp outside acceptable tolerance window",
                    )
                # Compute message over timestamp.payload
                message = f"{ts}.".encode() + payload_bytes
            except ValueError:
                return WebhookVerificationResult(
                    is_valid=False,
                    error_message="Invalid timestamp header format",
                )
        else:
            message = payload_bytes

        # Calculate expected HMAC-SHA256
        secret_bytes = secret.encode("utf-8")
        expected_sig = hmac.new(secret_bytes, message, hashlib.sha256).hexdigest()

        # Handle signature formats (e.g. 'v1=abc...' or plain hex 'abc...')
        clean_sig = signature.strip()
        if "=" in clean_sig:
            parts = clean_sig.split("=", 1)
            clean_sig = parts[1].strip()

        # Constant-time comparison
        is_match = hmac.compare_digest(expected_sig.lower(), clean_sig.lower())

        if not is_match:
            # Note: Never log the secret or expected signature value
            logger.warning("Webhook signature verification failed: signature mismatch")
            return WebhookVerificationResult(
                is_valid=False,
                error_message="Invalid webhook signature",
            )

        return WebhookVerificationResult(is_valid=True)
