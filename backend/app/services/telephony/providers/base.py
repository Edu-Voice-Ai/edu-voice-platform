"""Telephony Provider Interface Abstraction.

Establishes a provider-neutral boundary decoupling the Voice Gateway core from
telecom carrier specific protocols (e.g. Exotel, Twilio, Plivo).
"""

from abc import ABC, abstractmethod
from typing import Any

from backend.app.services.telephony.events import NormalizedTelephonyEvent


class BaseTelephonyProvider(ABC):
    """Abstract interface representing a telephony provider adapter."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifying name for the telephony provider."""

    @abstractmethod
    def normalize_inbound_call(
        self,
        raw_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> NormalizedTelephonyEvent:
        """Normalize vendor-specific inbound webhook payload into a NormalizedTelephonyEvent."""

    @abstractmethod
    def normalize_media_event(
        self,
        raw_data: str | bytes | dict[str, Any],
        call_id: str,
        session_id: str | None = None,
    ) -> NormalizedTelephonyEvent:
        """Normalize incoming streaming media or audio chunk into a NormalizedTelephonyEvent."""

    @abstractmethod
    def normalize_call_event(
        self,
        raw_payload: dict[str, Any],
    ) -> NormalizedTelephonyEvent:
        """Normalize vendor call status or lifecycle callback into a NormalizedTelephonyEvent."""

    @abstractmethod
    def normalize_termination(
        self,
        call_id: str,
        reason: str | None = None,
        session_id: str | None = None,
    ) -> NormalizedTelephonyEvent:
        """Normalize call hangup / disconnect into a NormalizedTelephonyEvent."""

    @abstractmethod
    async def transfer_call(
        self,
        call_id: str,
        target_phone_number: str,
    ) -> dict[str, Any]:
        """Initiate human-agent escalation transfer via carrier telephony API."""

    @abstractmethod
    async def check_health(self) -> bool:
        """Verify provider adapter configuration and readiness."""
