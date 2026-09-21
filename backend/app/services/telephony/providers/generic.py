"""Generic / Standard Telephony Provider Adapter.

Provides a provider-neutral reference implementation of BaseTelephonyProvider.
Decouples the Voice Gateway core from carrier-specific protocols.
"""

from typing import Any

from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.events import (
    NormalizedTelephonyEvent,
    TelephonyEventType,
)
from backend.app.services.telephony.providers.base import BaseTelephonyProvider


class GenericTelephonyProvider(BaseTelephonyProvider):
    """Provider-neutral telephony provider adapter."""

    def __init__(self, settings: TelephonySettings | None = None) -> None:
        self.settings: TelephonySettings = settings or get_telephony_settings()

    @property
    def provider_name(self) -> str:
        return "generic"

    def normalize_inbound_call(
        self,
        raw_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> NormalizedTelephonyEvent:
        """Normalize generic inbound call webhook payload into NormalizedTelephonyEvent."""
        call_sid = (
            raw_payload.get("call_sid")
            or raw_payload.get("CallSid")
            or raw_payload.get("call_id")
            or raw_payload.get("CallUUID")
            or ""
        )
        if not call_sid:
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message="Missing call identifier in inbound webhook payload",
            )

        from_num = str(
            raw_payload.get("from_number")
            or raw_payload.get("From")
            or raw_payload.get("caller")
            or ""
        ).strip()
        to_num = str(
            raw_payload.get("to_number")
            or raw_payload.get("To")
            or raw_payload.get("called")
            or ""
        ).strip()

        return NormalizedTelephonyEvent(
            event_type=TelephonyEventType.CALL_CONNECTED,
            call_id=str(call_sid).strip(),
            from_number=from_num or None,
            to_number=to_num or None,
            provider_name=self.provider_name,
            provider_metadata={
                "call_type": raw_payload.get("CallType")
                or raw_payload.get("call_type")
                or "inbound",
                "direction": raw_payload.get("Direction")
                or raw_payload.get("direction")
                or "inbound",
                "raw_keys": list(raw_payload.keys()),
            },
        )

    def normalize_media_event(
        self,
        raw_data: str | bytes | dict[str, Any],
        call_id: str,
        session_id: str | None = None,
    ) -> NormalizedTelephonyEvent:
        """Normalize streaming media chunk or JSON control message."""
        if isinstance(raw_data, bytes):
            return NormalizedTelephonyEvent(
                event_type=TelephonyEventType.MEDIA,
                call_id=call_id,
                session_id=session_id,
                payload=raw_data,
                provider_name=self.provider_name,
            )

        if isinstance(raw_data, dict):
            event_str = str(
                raw_data.get("event") or raw_data.get("type") or "media"
            ).upper()
            if event_str == "MEDIA":
                return NormalizedTelephonyEvent(
                    event_type=TelephonyEventType.MEDIA,
                    call_id=call_id,
                    session_id=session_id,
                    provider_name=self.provider_name,
                    provider_metadata=raw_data,
                )
            if event_str == "START":
                return NormalizedTelephonyEvent(
                    event_type=TelephonyEventType.START,
                    call_id=call_id,
                    session_id=session_id,
                    provider_name=self.provider_name,
                    provider_metadata=raw_data,
                )
            if event_str == "STOP":
                return NormalizedTelephonyEvent(
                    event_type=TelephonyEventType.STOP,
                    call_id=call_id,
                    session_id=session_id,
                    stop_reason=raw_data.get("reason", "normal_hangup"),
                    provider_name=self.provider_name,
                    provider_metadata=raw_data,
                )

        raise GatewayError(
            code=GatewayErrorCode.MALFORMED_MESSAGE,
            message="Unsupported media frame format",
        )

    def normalize_call_event(
        self,
        raw_payload: dict[str, Any],
    ) -> NormalizedTelephonyEvent:
        """Normalize call status or lifecycle update."""
        call_sid = (
            raw_payload.get("call_sid")
            or raw_payload.get("CallSid")
            or raw_payload.get("call_id")
            or raw_payload.get("CallUUID")
            or ""
        )
        if not call_sid:
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message="Missing call identifier in call event payload",
            )

        status_str = str(
            raw_payload.get("status")
            or raw_payload.get("Status")
            or raw_payload.get("call_status")
            or ""
        ).lower()
        event_type = (
            TelephonyEventType.STOP
            if status_str
            in {"completed", "failed", "busy", "no-answer", "canceled", "disconnected"}
            else TelephonyEventType.CALL_CONNECTED
        )

        return NormalizedTelephonyEvent(
            event_type=event_type,
            call_id=str(call_sid).strip(),
            from_number=raw_payload.get("From") or raw_payload.get("from_number"),
            to_number=raw_payload.get("To") or raw_payload.get("to_number"),
            stop_reason=status_str if event_type == TelephonyEventType.STOP else None,
            provider_name=self.provider_name,
            provider_metadata=raw_payload,
        )

    def normalize_termination(
        self,
        call_id: str,
        reason: str | None = None,
        session_id: str | None = None,
    ) -> NormalizedTelephonyEvent:
        """Normalize call hangup / disconnect."""
        return NormalizedTelephonyEvent(
            event_type=TelephonyEventType.STOP,
            call_id=call_id,
            session_id=session_id,
            stop_reason=reason or "normal_hangup",
            provider_name=self.provider_name,
        )

    async def transfer_call(
        self,
        call_id: str,
        target_phone_number: str,
    ) -> dict[str, Any]:
        """Initiate human-agent escalation transfer."""
        return {
            "status": "transferred",
            "call_id": call_id,
            "target_phone_number": target_phone_number,
            "provider": self.provider_name,
        }

    async def check_health(self) -> bool:
        """Verify provider adapter readiness."""
        return True
