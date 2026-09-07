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
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.logging import (
    StructuredGatewayLogger,
    mask_identifier,
    mask_phone_number,
)
from backend.app.services.telephony.routing.phone_assignment import (
    BackendPhoneAssignmentResolver,
    PhoneAssignmentRequest,
    PhoneAssignmentResolver,
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


def get_phone_assignment_resolver(
    settings: Annotated[TelephonySettings, Depends(get_telephony_settings)],
) -> PhoneAssignmentResolver:
    """Dependency provider for PhoneAssignmentResolver instance."""
    return BackendPhoneAssignmentResolver(settings=settings)


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
    resolver: Annotated[
        PhoneAssignmentResolver, Depends(get_phone_assignment_resolver)
    ],
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
        or params.get("Caller")
        or params.get("caller")
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
        or params.get("ExoPhone")
        or params.get("exophone")
        or params.get("Called")
        or params.get("called")
        or settings.exotel_exophone
        or ""
    )
    resolved_direction = (
        direction
        or params.get("Direction")
        or params.get("direction")
        or "inbound"
    )

    manager = get_realtime_session_manager(settings=settings)

    # Validate destination DID format
    if not resolved_to or resolved_to.strip() in ("", "unknown"):
        slog.warning(
            "did_resolution_rejected",
            call_sid=mask_identifier(resolved_call_sid),
            destination_did="unknown",
            error_code="INVALID_DID_FORMAT",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            reason="Missing or empty destination phone number",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="INVALID_DID_FORMAT: Destination number is missing or invalid",
        )

    # 1. Resolve destination DID via authoritative BackendPhoneAssignmentResolver
    slog.info(
        "did_resolution_started",
        destination_did=mask_phone_number(resolved_to),
        call_sid=mask_identifier(resolved_call_sid),
    )

    try:
        resolution = await resolver.resolve_phone_assignment(
            PhoneAssignmentRequest(
                phone_number=resolved_to,
                caller_number=resolved_from,
                provider="exotel",
                call_sid=resolved_call_sid,
            )
        )
    except GatewayError as ge:
        err_msg_lower = ge.message.lower()
        if "not found" in err_msg_lower or "did_not_found" in err_msg_lower:
            http_status = status.HTTP_404_NOT_FOUND
            error_code = "DID_NOT_FOUND"
            detail_msg = "Dialed number is not registered"
        elif "suspended" in err_msg_lower or "inactive" in err_msg_lower:
            if "organization" in err_msg_lower:
                error_code = "ORGANIZATION_INACTIVE"
                http_status = status.HTTP_403_FORBIDDEN
                detail_msg = "Institution account is inactive"
            elif "agent" in err_msg_lower:
                error_code = "AGENT_INACTIVE"
                http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
                detail_msg = "Assigned agent is currently inactive"
            else:
                error_code = "DID_INACTIVE"
                http_status = status.HTTP_403_FORBIDDEN
                detail_msg = "Destination number is inactive"
        elif "format" in err_msg_lower:
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
            error_code = "INVALID_DID_FORMAT"
            detail_msg = "Invalid destination number format"
        elif "no active" in err_msg_lower or "not assigned" in err_msg_lower or "assignment" in err_msg_lower:
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
            error_code = "NO_ACTIVE_ASSIGNMENT"
            detail_msg = "No active agent assigned to destination number"
        elif ge.code == GatewayErrorCode.AUTHENTICATION_FAILED or "unauthorized" in err_msg_lower:
            http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
            error_code = "UNAUTHORIZED_INTERNAL_SERVICE"
            detail_msg = "Telephony routing authentication failure"
        elif ge.code == GatewayErrorCode.TIMEOUT or "timed out" in err_msg_lower:
            http_status = status.HTTP_504_GATEWAY_TIMEOUT
            error_code = "TIMEOUT"
            detail_msg = "DID resolution timed out"
        elif ge.code == GatewayErrorCode.SERVICE_UNAVAILABLE or "unavailable" in err_msg_lower or "unreachable" in err_msg_lower:
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
            error_code = "DATABASE_UNAVAILABLE"
            detail_msg = "Routing database is temporarily unavailable"
        else:
            http_status = status.HTTP_502_BAD_GATEWAY
            error_code = "RESOLUTION_ERROR"
            detail_msg = "DID resolution failed"

        slog.warning(
            "did_resolution_rejected",
            call_sid=mask_identifier(resolved_call_sid),
            destination_did=mask_phone_number(resolved_to),
            error_code=error_code,
            status_code=http_status,
            reason=detail_msg,
        )
        raise HTTPException(
            status_code=http_status,
            detail=f"{error_code}: {detail_msg}",
        ) from ge
    except Exception as exc:
        slog.warning(
            "did_resolution_rejected",
            call_sid=mask_identifier(resolved_call_sid),
            destination_did=mask_phone_number(resolved_to),
            error_code="UNEXPECTED_RESOLVER_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            reason=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="RESOLUTION_ERROR: Unexpected resolver failure",
        ) from exc

    # Enforce authoritative tenant and agent validation (Zero default/placeholder tenants allowed)
    if (
        not resolution
        or not resolution.organization_id
        or not resolution.agent_id
        or resolution.organization_id.strip() in ("", "pending_contract_org", "unknown")
        or resolution.agent_id.strip() in ("", "pending_contract_admission_agent", "unknown")
    ):
        slog.warning(
            "did_resolution_rejected",
            call_sid=mask_identifier(resolved_call_sid),
            destination_did=mask_phone_number(resolved_to),
            error_code="NO_ACTIVE_ASSIGNMENT",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            reason="Missing or invalid organization_id or agent_id in resolution",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="NO_ACTIVE_ASSIGNMENT: Incomplete or invalid tenant routing assignment",
        )

    if not resolution.is_active:
        slog.warning(
            "did_resolution_rejected",
            call_sid=mask_identifier(resolved_call_sid),
            destination_did=mask_phone_number(resolved_to),
            error_code="DID_INACTIVE",
            status_code=status.HTTP_403_FORBIDDEN,
            reason="DID assignment is inactive",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="DID_INACTIVE: Destination number is inactive",
        )

    if resolution.agent_config and not resolution.agent_config.is_active:
        slog.warning(
            "did_resolution_rejected",
            call_sid=mask_identifier(resolved_call_sid),
            destination_did=mask_phone_number(resolved_to),
            error_code="AGENT_INACTIVE",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            reason="Assigned agent is inactive",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="AGENT_INACTIVE: Assigned agent is currently inactive",
        )

    org_id = resolution.organization_id.strip()
    agent_id = resolution.agent_id.strip()
    agent_config = resolution.agent_config

    slog.info(
        "did_resolution_success",
        destination_did=mask_phone_number(resolved_to),
        call_sid=mask_identifier(resolved_call_sid),
        organization_id=mask_identifier(org_id),
        agent_id=mask_identifier(agent_id),
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

    # 4. Register session in RealtimeSessionManager with authoritative tenant assignment
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
