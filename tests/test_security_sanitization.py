"""Security tests ensuring secret values are never exposed in representations or logs."""

import logging

import pytest
from pydantic import SecretStr

from backend.app.services.telephony.config import TelephonySettings
from backend.app.services.telephony.security.verifier import HMACSHA256WebhookVerifier


def test_secrets_masked_in_settings_representation() -> None:
    """Ensure SecretStr fields mask secret values in repr and str."""
    secret_value = "super_confidential_secret_key_999"
    internal_key = "internal_service_token_secret_888"
    settings = TelephonySettings(
        webhook_secret=SecretStr(secret_value),
        internal_service_key=SecretStr(internal_key),
    )

    settings_repr = repr(settings)
    settings_str = str(settings)

    assert secret_value not in settings_repr
    assert internal_key not in settings_repr

    assert secret_value not in settings_str
    assert internal_key not in settings_str


def test_verifier_does_not_leak_secret_in_error_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensure verifier failure messages and log outputs do not contain secret or expected signature."""
    secret_value = "super_confidential_secret_key_999"
    verifier = HMACSHA256WebhookVerifier()

    with caplog.at_level(logging.DEBUG):
        result = verifier.verify(
            payload_bytes=b'{"call_sid":"123"}',
            signature="wrong_sig",
            secret=secret_value,
        )

    assert result.is_valid is False
    # Verify secret is not in result error message
    assert secret_value not in (result.error_message or "")
    # Verify secret is not in captured logs
    assert secret_value not in caplog.text
