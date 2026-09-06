"""Telephony API router for inbound webhooks and lifecycle callbacks."""

import json
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ValidationError

from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.errors import GatewayError
from backend.app.services.telephony.logging import (
    StructuredGatewayLogger,
    mask_identifier,
    mask_phone_number,
)
from backend.app.services.telephony.routing.phone_assignment import (
    BackendPhoneAssignmentResolver,
    PhoneAssignmentRequest,
)
from backend.app.services.telephony.schemas import (
    CallStatusEventPayload,
    InboundCallPayload,
    TelephonyWebhookResponse,
)
from backend.app.services.telephony.service import TelephonyService
from backend.app.services.telephony.session_manager import get_realtime_session_manager

logger = logging.getLogger("telephony.router")
slog = StructuredGatewayLogger("telephony.router")

router = APIRouter(prefix="/telephony", tags=["Telephony"])


class ExotelDynamicResolverResponse(BaseModel):
    """Dynamic WebSocket streaming URL returned to Exotel VoiceBot applet."""

    url: str


def get_telephony_service(
    settings: Annotated[TelephonySettings, Depends(get_telephony_settings)],
) -> TelephonyService:
    """Dependency provider for TelephonyService instance."""
    return TelephonyService(settings=settings)


@router.post(
    "/webhook",
    response_model=TelephonyWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Inbound Call Webhook Intake",
    description="Intake endpoint for incoming calls from telephony provider.",
)
async def inbound_call_webhook(
    request: Request,
    service: Annotated[TelephonyService, Depends(get_telephony_service)],
    x_telephony_signature: Annotated[
        str | None, Header(alias="X-Telephony-Signature")
    ] = None,
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
    x_telephony_timestamp: Annotated[
        str | None, Header(alias="X-Telephony-Timestamp")
    ] = None,
    x_timestamp: Annotated[str | None, Header(alias="X-Timestamp")] = None,
) -> TelephonyWebhookResponse:
    """Intake, verify, validate, and process incoming telephony call webhook."""
    # Resolve signature and timestamp from supported header aliases
    signature = x_telephony_signature or x_signature
    timestamp = x_telephony_timestamp or x_timestamp

    # Read raw body bytes for cryptographic signature verification
    body_bytes = await request.body()

    # 1. Webhook Signature Verification
    is_valid, error_msg = service.verify_webhook_signature(
        payload_bytes=body_bytes,
        signature=signature,
        timestamp_header=timestamp,
    )

    if not is_valid:
        logger.warning("Rejected unauthorized webhook request: %s", error_msg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg or "Unauthorized: Webhook signature verification failed",
        )

    # 2. Payload Validation via Pydantic model
    try:
        json_data = await request.json()
        payload = InboundCallPayload.model_validate(json_data)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Invalid webhook payload received: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid webhook payload: {exc}",
        ) from exc

    # 3. Process via Telephony Service Layer
    return await service.process_inbound_call(payload=payload)


@router.post(
    "/events",
    response_model=TelephonyWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Call Status Event Callback Intake",
    description="Receives asynchronous status callbacks (connected, disconnected, hangup reasons).",
)
async def call_status_event_webhook(
    request: Request,
    service: Annotated[TelephonyService, Depends(get_telephony_service)],
    x_telephony_signature: Annotated[
        str | None, Header(alias="X-Telephony-Signature")
    ] = None,
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
    x_telephony_timestamp: Annotated[
        str | None, Header(alias="X-Telephony-Timestamp")
    ] = None,
    x_timestamp: Annotated[str | None, Header(alias="X-Timestamp")] = None,
) -> TelephonyWebhookResponse:
    """Intake, verify, and process call status events."""
    signature = x_telephony_signature or x_signature
    timestamp = x_telephony_timestamp or x_timestamp

    body_bytes = await request.body()

    is_valid, error_msg = service.verify_webhook_signature(
        payload_bytes=body_bytes,
        signature=signature,
        timestamp_header=timestamp,
    )

    if not is_valid:
        logger.warning("Rejected unauthorized event callback: %s", error_msg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg or "Unauthorized: Event signature verification failed",
        )

    try:
        json_data = await request.json()
        payload = CallStatusEventPayload.model_validate(json_data)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Invalid event payload received: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid event payload: {exc}",
        ) from exc

    return await service.process_status_event(payload=payload)


@router.get(
    "/exotel/resolve",
    response_model=ExotelDynamicResolverResponse,
    status_code=status.HTTP_200_OK,
    summary="Exotel Dynamic VoiceBot Stream Resolver",
    description="Resolves Exotel call metadata, maps tenant DID via Aravind backend resolver, and returns dynamic WebSocket URL.",
)
@router.post(
    "/exotel/resolve",
    response_model=ExotelDynamicResolverResponse,
    status_code=status.HTTP_200_OK,
    summary="Exotel Dynamic VoiceBot Stream Resolver (POST)",
    description="POST variant of Exotel dynamic resolver for compatibility with webhook applets.",
)
async def exotel_dynamic_resolver(
    request: Request,
    settings: Annotated[TelephonySettings, Depends(get_telephony_settings)],
    call_sid: Annotated[str | None, Query(alias="CallSid")] = None,
    call_from: Annotated[str | None, Query(alias="CallFrom")] = None,
    call_to: Annotated[str | None, Query(alias="CallTo")] = None,
    direction: Annotated[str | None, Query(alias="Direction")] = None,
    created: Annotated[str | None, Query(alias="Created")] = None,
    dial_whom_number: Annotated[str | None, Query(alias="DialWhomNumber")] = None,
    from_param: Annotated[str | None, Query(alias="From")] = None,
    to_param: Annotated[str | None, Query(alias="To")] = None,
    current_time: Annotated[str | None, Query(alias="CurrentTime")] = None,
) -> ExotelDynamicResolverResponse:
    """Resolve dynamic Exotel VoiceBot call parameters into an active streaming session."""
    # Capture query parameters and optional POST body fields
    params: dict[str, Any] = dict(request.query_params)
    if request.method == "POST":
        try:
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                body_json = await request.json()
                if isinstance(body_json, dict):
                    params.update(body_json)
            elif (
                "application/x-www-form-urlencoded" in content_type
                or "multipart/form-data" in content_type
            ):
                form_data = await request.form()
                params.update(dict(form_data))
        except Exception as parse_err:  # noqa: BLE001
            logger.debug("Failed parsing POST body in exotel resolver: %s", parse_err)

    resolved_call_sid = (
        call_sid
        or params.get("CallSid")
        or params.get("call_sid")
    )
    if not resolved_call_sid:
        logger.warning("Rejected Exotel resolve request: missing CallSid")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required CallSid parameter",
        )

    resolved_from = (
        call_from
        or from_param
        or params.get("CallFrom")
        or params.get("From")
        or params.get("from")
        or "anonymous"
    )
    resolved_to = (
        to_param
        or call_to
        or dial_whom_number
        or params.get("To")
        or params.get("CallTo")
        or params.get("DialWhomNumber")
        or params.get("to")
        or settings.exotel_exophone
        or "unknown"
    )
    resolved_direction = (
        direction
        or params.get("Direction")
        or params.get("direction")
        or "inbound"
    )

    # 1. Resolve destination DID via Aravind's BackendPhoneAssignmentResolver
    slog.info(
        "did_resolution_started",
        destination_did=mask_phone_number(resolved_to),
        call_sid=mask_identifier(resolved_call_sid),
    )

    org_id = "pending_contract_org"
    agent_id = "pending_contract_admission_agent"
    agent_config = None

    try:
        resolver = BackendPhoneAssignmentResolver(settings=settings)
        resolution = await resolver.resolve_phone_assignment(
            PhoneAssignmentRequest(
                phone_number=resolved_to,
                caller_number=resolved_from,
                provider="exotel",
                call_sid=resolved_call_sid,
            )
        )
        if resolution and resolution.organization_id:
            org_id = resolution.organization_id
            agent_id = resolution.agent_id
            agent_config = resolution.agent_config
            slog.info(
                "did_resolution_success",
                organization_id=mask_identifier(org_id),
                agent_id=mask_identifier(agent_id),
            )
        else:
            slog.warning(
                "did_resolution_fallback",
                destination_did=mask_phone_number(resolved_to),
                status="provisional_default",
            )
    except (GatewayError, OSError, RuntimeError) as res_err:
        slog.warning(
            "did_resolution_failure",
            destination_did=mask_phone_number(resolved_to),
            error_code=getattr(res_err, "code", "resolution_error"),
            error=str(res_err),
        )

    # 2. Generate unique internal session_id
    unique_suffix = uuid.uuid4().hex[:12]
    session_id = f"exotel_{resolved_call_sid}_{unique_suffix}"

    # 3. Preserve session context and Exotel provider metadata
    provider_metadata: dict[str, Any] = {
        "call_sid": resolved_call_sid,
        "from": resolved_from,
        "to": resolved_to,
        "direction": resolved_direction,
        "created": created or params.get("Created"),
        "current_time": current_time or params.get("CurrentTime"),
        "dial_whom_number": dial_whom_number or params.get("DialWhomNumber"),
    }
    # Safely collect extra non-secret query params
    for k, v in params.items():
        if (
            k.lower() not in ("key", "token", "secret", "password", "authorization")
            and k not in provider_metadata
        ):
            provider_metadata[k] = str(v)

    # 4. Register session in RealtimeSessionManager
    manager = get_realtime_session_manager(settings=settings)
    await manager.create_session(
        session_id=session_id,
        call_sid=resolved_call_sid,
        organization_id=org_id,
        agent_id=agent_id,
        agent_config=agent_config,
        provider="exotel",
        stream_sid=None,
        from_number=resolved_from,
        to_number=resolved_to,
        call_direction=resolved_direction,
        provider_metadata=provider_metadata,
    )
    slog.info(
        "exotel_session_created",
        session_id=mask_identifier(session_id),
        call_sid=mask_identifier(resolved_call_sid),
        provider="exotel",
    )

    # 5. Build dynamic public WebSocket URL
    ws_scheme = settings.gateway_public_ws_scheme
    ws_host = settings.gateway_public_host
    ws_url = f"{ws_scheme}://{ws_host}/ws/telephony/stream/{session_id}"

    slog.info(
        "exotel_resolver_request",
        session_id=mask_identifier(session_id),
        call_sid=mask_identifier(resolved_call_sid),
        direction=resolved_direction,
        has_from=bool(resolved_from and resolved_from != "anonymous"),
        has_to=bool(resolved_to and resolved_to != "unknown"),
        status=200,
    )
    return ExotelDynamicResolverResponse(url=ws_url)
