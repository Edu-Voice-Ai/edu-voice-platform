"""Structured Logging and Secret Sanitization for Telephony Gateway.

Ensures that log records never include sensitive authorization tokens,
secrets, passwords, API keys, or raw audio payloads.
"""

import json
import logging
from typing import Any

# Sensitive key patterns that must be redacted automatically
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "api_token",
    "token",
    "secret",
    "webhook_secret",
    "password",
    "authorization",
    "auth",
    "x-telephony-signature",
    "x-exotel-signature",
    "x-signature",
    "payload_b64",
    "audio_data",
    "raw_bytes",
}


def sanitize_value(key: str, val: Any) -> Any:
    """Scrub sensitive fields and truncate large byte/string representations."""
    key_lower = key.lower().replace("-", "_")
    for sensitive in SENSITIVE_KEYS:
        if sensitive in key_lower:
            return "[REDACTED]"

    if isinstance(val, (bytes, bytearray)):
        return f"[BINARY_DATA: {len(val)} bytes]"

    if isinstance(val, str) and len(val) > 256:
        return f"{val[:64]}... [TRUNCATED: {len(val)} chars]"

    if isinstance(val, dict):
        return {k: sanitize_value(k, v) for k, v in val.items()}

    if isinstance(val, (list, tuple)):
        return [sanitize_value(key, item) for item in val]

    return val


def mask_identifier(val: str | None, prefix_len: int = 4, suffix_len: int = 4) -> str:
    """Mask sensitive string leaving only small prefix/suffix visible for debugging."""
    if not val:
        return "none"
    s = str(val).strip()
    if len(s) <= prefix_len + suffix_len:
        return f"{s[:2]}...{s[-2:]}" if len(s) > 4 else "***"
    return f"{s[:prefix_len]}...{s[-suffix_len:]}"


def mask_phone_number(phone: str | None) -> str:
    """Mask phone number preserving country/area prefix and last 3 digits."""
    if not phone:
        return "none"
    p = str(phone).strip()
    if len(p) <= 5:
        return "***"
    return f"{p[:3]}...{p[-3:]}"


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-sanitized copy of a dictionary."""
    return {k: sanitize_value(k, v) for k, v in data.items()}


class StructuredGatewayLogger:
    """Helper for emitting structured JSON-like diagnostic log messages."""

    def __init__(self, logger_name: str = "telephony.gateway") -> None:
        self.logger = logging.getLogger(logger_name)

    def log_event(
        self,
        level: int,
        event_name: str,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit sanitized structured log entry."""
        payload: dict[str, Any] = {
            "event": event_name,
            "session_id": session_id or "unassigned",
        }
        for k, v in kwargs.items():
            payload[k] = sanitize_value(k, v)

        msg = json.dumps(payload)
        self.logger.log(level, msg)

    def info(
        self, event_name: str, session_id: str | None = None, **kwargs: Any
    ) -> None:
        self.log_event(logging.INFO, event_name, session_id, **kwargs)

    def warning(
        self, event_name: str, session_id: str | None = None, **kwargs: Any
    ) -> None:
        self.log_event(logging.WARNING, event_name, session_id, **kwargs)

    def error(
        self, event_name: str, session_id: str | None = None, **kwargs: Any
    ) -> None:
        self.log_event(logging.ERROR, event_name, session_id, **kwargs)

    def debug(
        self, event_name: str, session_id: str | None = None, **kwargs: Any
    ) -> None:
        self.log_event(logging.DEBUG, event_name, session_id, **kwargs)
