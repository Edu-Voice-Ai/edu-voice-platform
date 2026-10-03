"""Telephony service orchestration layer.

Coordinates webhook ingestion, verification, routing resolution, and session lifecycle.
"""

import logging

from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.lifecycle.session import (
    CallSessionLifecycleManager,
    CallSessionState,
)
from backend.app.services.telephony.routing.resolver import (
    BaseTenantCallRouter,
    UnresolvedBackendTenantCallRouter,
)
from backend.app.services.telephony.schemas import (
    CallEventType,
    CallStatusEventPayload,
    InboundCallPayload,
    TelephonyWebhookResponse,
)
from backend.app.services.telephony.security.verifier import (
    BaseWebhookVerifier,
    HMACSHA256WebhookVerifier,
)

logger = logging.getLogger("telephony.service")


class TelephonyService:
    """Service layer for telephony webhooks and call gateway operations."""

    def __init__(
        self,
        settings: TelephonySettings | None = None,
        verifier: BaseWebhookVerifier | None = None,
        router: BaseTenantCallRouter | None = None,
        session_manager: CallSessionLifecycleManager | None = None,
    ) -> None:
        self.settings = settings or get_telephony_settings()
        self.verifier = verifier or HMACSHA256WebhookVerifier()
        self.router = router or UnresolvedBackendTenantCallRouter()
        self.session_manager = session_manager or CallSessionLifecycleManager()

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature: str | None,
        timestamp_header: str | None = None,
    ) -> tuple[bool, str | None]:
        """Verify the cryptographic signature of an incoming webhook."""
        if not self.settings.signature_verification_enabled:
            return True, None

        secret_val = self.settings.webhook_secret.get_secret_value()
        result = self.verifier.verify(
            payload_bytes=payload_bytes,
            signature=signature,
            timestamp_header=timestamp_header,
            secret=secret_val,
            tolerance_seconds=self.settings.webhook_tolerance_seconds,
        )
        return result.is_valid, result.error_message

    async def process_inbound_call(
        self,
        payload: InboundCallPayload,
    ) -> TelephonyWebhookResponse:
        """Process validated inbound call webhook and initialize session tracking."""
        logger.info(
            "Processing inbound call: call_sid=%s, direction=%s",
            payload.call_sid,
            payload.direction,
        )

        # Resolve DID to tenant organization & AI agent
        resolution = await self.router.resolve_did(inbound_did=payload.to_number)

        # Register session in lifecycle manager
        session = self.session_manager.create_session(
            call_sid=payload.call_sid,
            from_number=payload.from_number,
            to_number=payload.to_number,
            organization_id=resolution.organization_id,
            agent_id=resolution.agent_id,
        )

        logger.info(
            "Call session created: call_sid=%s, org_id=%s, state=%s",
            session.call_sid,
            session.organization_id,
            session.state,
        )

        return TelephonyWebhookResponse(
            status="accepted",
            call_sid=payload.call_sid,
            action="process",
            message="Inbound call accepted and session initialized",
        )

    async def process_status_event(
        self,
        payload: CallStatusEventPayload,
    ) -> TelephonyWebhookResponse:
        """Process call status/lifecycle update callback."""
        logger.info(
            "Processing status event: call_sid=%s, event_type=%s, status=%s",
            payload.call_sid,
            payload.event_type,
            payload.call_status,
        )

        if payload.event_type == CallEventType.CALL_DISCONNECTED:
            self.session_manager.end_session(
                call_sid=payload.call_sid,
                reason=payload.hangup_cause or "provider_hangup",
            )
        elif payload.event_type == CallEventType.CALL_CONNECTED:
            self.session_manager.transition_state(
                call_sid=payload.call_sid,
                new_state=CallSessionState.CONNECTED,
            )

        return TelephonyWebhookResponse(
            status="accepted",
            call_sid=payload.call_sid,
            action="acknowledged",
            message="Status event processed successfully",
        )
