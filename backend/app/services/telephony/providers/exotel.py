"""Exotel Telephony Provider Adapter.

Implements BaseTelephonyProvider for Exotel carrier integration,
normalizing Exotel webhooks, streaming media, and lifecycle callbacks
into provider-neutral NormalizedTelephonyEvent models.
"""

from typing import Any

from backend.app.services.telephony.clients.exotel_client import ExotelApiClient
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


class ExotelTelephonyProvider(BaseTelephonyProvider):
    """Exotel-specific telephony provider adapter."""

    def __init__(
        self,
        settings: TelephonySettings | None = None,
        api_client: ExotelApiClient | None = None,
    ) -> None:
        self.settings: TelephonySettings = settings or get_telephony_settings()
        self.api_client: ExotelApiClient = api_client or ExotelApiClient(settings=self.settings)

    @property
    def provider_name(self) -> str:
        return "exotel"

    def normalize_inbound_call(
        self,
        raw_payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> NormalizedTelephonyEvent:
        """Normalize Exotel inbound call webhook payload into NormalizedTelephonyEvent."""
        call_sid = (
            raw_payload.get("CallSid")
            or raw_payload.get("call_sid")
            or raw_payload.get("CallUUID")
            or raw_payload.get("call_id")
            or ""
        )
        if not call_sid:
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message="Missing CallSid in Exotel inbound webhook payload",
            )

        from_num = str(
            raw_payload.get("From")
            or raw_payload.get("from_number")
            or raw_payload.get("Caller")
            or ""
        ).strip()
        to_num = str(
            raw_payload.get("To")
            or raw_payload.get("to_number")
            or raw_payload.get("Called")
            or ""
        ).strip()

        return NormalizedTelephonyEvent(
            event_type=TelephonyEventType.CALL_CONNECTED,
            call_id=str(call_sid).strip(),
            from_number=from_num or None,
            to_number=to_num or None,
            provider_name=self.provider_name,
            provider_metadata={
                "call_type": raw_payload.get("CallType") or "inbound",
                "direction": raw_payload.get("Direction") or "inbound",
                "dial_whom_number": raw_payload.get("DialWhomNumber"),
                "raw_keys": list(raw_payload.keys()),
            },
        )

    def normalize_media_event(
        self,
        raw_data: str | bytes | dict[str, Any],
        call_id: str,
        session_id: str | None = None,
    ) -> NormalizedTelephonyEvent:
        """Normalize Exotel streaming media frame or JSON control packet."""
        if isinstance(raw_data, bytes):
            return NormalizedTelephonyEvent(
                event_type=TelephonyEventType.MEDIA,
                call_id=call_id,
                session_id=session_id,
                payload=raw_data,
                provider_name=self.provider_name,
            )

        if isinstance(raw_data, dict):
            event_name = str(
                raw_data.get("event") or raw_data.get("type") or "media"
            ).lower()
            if event_name in ("media", "audio"):
                media_payload = raw_data.get("payload") or raw_data.get("data")
                return NormalizedTelephonyEvent(
                    event_type=TelephonyEventType.MEDIA,
                    call_id=call_id,
                    session_id=session_id,
                    payload=media_payload.encode("utf-8") if isinstance(media_payload, str) else media_payload,
                    provider_name=self.provider_name,
                    provider_metadata={"chunk_index": raw_data.get("chunk_index")},
                )
            if event_name in ("dtmf", "digit"):
                digit = str(raw_data.get("digit") or raw_data.get("dtmf") or "0")
                return NormalizedTelephonyEvent(
                    event_type=TelephonyEventType.DTMF,
                    call_id=call_id,
                    session_id=session_id,
                    dtmf_digit=digit,
                    provider_name=self.provider_name,
                )

        raise GatewayError(
            code=GatewayErrorCode.INVALID_FRAME_TYPE,
            message=f"Unsupported Exotel media format: {type(raw_data).__name__}",
        )

    def normalize_call_event(
        self,
        raw_payload: dict[str, Any],
    ) -> NormalizedTelephonyEvent:
        """Normalize Exotel lifecycle status callback (completed, busy, failed, etc.)."""
        call_sid = (
            raw_payload.get("CallSid")
            or raw_payload.get("call_sid")
            or raw_payload.get("call_id")
            or ""
        )
        if not call_sid:
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message="Missing CallSid in Exotel status callback",
            )

        status_str = str(
            raw_payload.get("Status") or raw_payload.get("call_status") or "completed"
        ).lower()

        event_type = (
            TelephonyEventType.STOP
            if status_str in {"completed", "failed", "busy", "no-answer", "canceled", "disconnected"}
            else TelephonyEventType.CALL_CONNECTED
        )

        return NormalizedTelephonyEvent(
            event_type=event_type,
            call_id=str(call_sid).strip(),
            from_number=raw_payload.get("From"),
            to_number=raw_payload.get("To"),
            provider_name=self.provider_name,
            provider_metadata={
                "exotel_status": status_str,
                "duration": raw_payload.get("Duration"),
                "recording_url": raw_payload.get("RecordingUrl"),
            },
        )

    def normalize_termination(
        self,
        call_id: str,
        reason: str | None = None,
        session_id: str | None = None,
    ) -> NormalizedTelephonyEvent:
        """Normalize call hangup event into standard model."""
        return NormalizedTelephonyEvent(
            event_type=TelephonyEventType.STOP,
            call_id=call_id,
            session_id=session_id,
            provider_name=self.provider_name,
            provider_metadata={"termination_reason": reason or "normal_hangup"},
        )

    async def transfer_call(
        self,
        call_id: str,
        target_phone_number: str,
    ) -> dict[str, Any]:
        """Transfer call via Exotel API client."""
        return await self.api_client.transfer_call(
            call_id=call_id,
            target_phone_number=target_phone_number,
        )

    async def check_health(self) -> bool:
        """Verify Exotel provider configuration readiness."""
        return self.settings.is_exotel_configured
