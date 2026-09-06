"""Standardized Error Codes and Exceptions for Telephony / Voice Gateway."""

from enum import Enum
from typing import Any


class GatewayErrorCode(str, Enum):
    """Categorized internal error codes for the Voice Gateway."""

    VALIDATION_FAILED = "VALIDATION_FAILED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    SIGNATURE_MISSING = "SIGNATURE_MISSING"
    MALFORMED_MESSAGE = "MALFORMED_MESSAGE"
    OVERSIZED_PAYLOAD = "OVERSIZED_PAYLOAD"
    INVALID_FRAME_TYPE = "INVALID_FRAME_TYPE"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_CLOSED = "SESSION_CLOSED"
    DUPLICATE_CONNECTION = "DUPLICATE_CONNECTION"
    QUEUE_OVERFLOW = "QUEUE_OVERFLOW"
    RATE_LIMITED = "RATE_LIMITED"
    MAX_SESSIONS_EXCEEDED = "MAX_SESSIONS_EXCEEDED"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    HEARTBEAT_TIMEOUT = "HEARTBEAT_TIMEOUT"
    TIMEOUT = "TIMEOUT"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    SHUTDOWN_IN_PROGRESS = "SHUTDOWN_IN_PROGRESS"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class GatewayError(Exception):
    """Base exception for Gateway runtime failures."""

    def __init__(
        self,
        code: GatewayErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: GatewayErrorCode = code
        self.message: str = message
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert error to a sanitized dictionary for logging/diagnostics."""
        return {
            "error_code": self.code.value,
            "message": self.message,
            "details": self.details,
        }
