"""Internal Telephony Router for Outbound Call Orchestration.

Implements:
- Contract 1: Backend → Yasin Outbound API (POST /api/v1/internal/telephony/outbound-calls)
- Contract 2: Outbound Job/Call ID & Idempotency Enforcement
- Contract 3: Authorized Outbound Caller-ID Execution
- Contract 4: Outbound Status State Machine & Callback Notifications
"""

import logging
import secrets
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from pydantic import ValidationError

from backend.app.services.telephony.clients.backend_client import (
    BackendStatusCallbackClient,
)
from backend.app.services.telephony.clients.exotel_client import ExotelApiClient
from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.idempotency import (
    IdempotencyConflictError,
    PersistentIdempotencyStore,
    get_idempotency_store,
)
from backend.app.services.telephony.logging import (
    StructuredGatewayLogger,
    mask_identifier,
    mask_phone_number,
)
from backend.app.services.telephony.outbound_schemas import (
    OutboundCallRequest,
    OutboundCallResponse,
    OutboundCallStatus,
    OutboundCallStatusCallbackPayload,
)
from backend.app.services.telephony.session_manager import (
    RealtimeSessionManager,
    get_realtime_session_manager,
)

logger = logging.getLogger("telephony.internal.router")
slog = StructuredGatewayLogger("telephony.internal.router")

router = APIRouter(prefix="/internal/telephony", tags=["Internal Telephony"])


def verify_internal_service_key(
    x_internal_service_key: Annotated[
        str | None, Header(alias="X-Internal-Service-Key")
    ] = None,
    settings: Annotated[TelephonySettings, Depends(get_telephony_settings)] = None,  # type: ignore[assignment]
) -> None:
    """Validate internal service shared secret using constant-time comparison."""
    configured_key = settings.internal_service_key.get_secret_value()
    if not configured_key or not x_internal_service_key:
        logger.warning("Rejected internal call: missing X-Internal-Service-Key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHORIZED_INTERNAL_SERVICE: Missing internal service key",
        )

    if not secrets.compare_digest(x_internal_service_key.strip(), configured_key.strip()):
        logger.warning("Rejected internal call: invalid X-Internal-Service-Key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHORIZED_INTERNAL_SERVICE: Invalid internal service key",
        )


async def _dispatch_outbound_call_task(
    request_data: OutboundCallRequest,
    gateway_call_id: str,
    settings: TelephonySettings,
    idempotency_store: PersistentIdempotencyStore,
    backend_client: BackendStatusCallbackClient,
    session_manager: RealtimeSessionManager,
) -> None:
    """Background task executing provider dialing and status callback."""
    exotel_client = ExotelApiClient(settings=settings)
    provider_call_id: str | None = None

    try:
        slog.info(
            "outbound_dialing_started",
            outbound_job_id=mask_identifier(request_data.outbound_job_id),
            call_id=mask_identifier(request_data.call_id),
            gateway_call_id=gateway_call_id,
            to=mask_phone_number(request_data.to_phone_number),
            from_caller_id=mask_phone_number(request_data.from_phone_number),
        )

        # 1. Dial via Exotel API
        # Provide resolver callback URL so customer connects to Gateway on answer
        ws_scheme = "https" if settings.gateway_public_ws_scheme == "wss" else "http"
        applet_url = (
            f"{ws_scheme}://{settings.gateway_public_host}/api/v1/telephony/exotel/resolve"
            f"?gateway_call_id={gateway_call_id}&outbound_job_id={request_data.outbound_job_id}"
            f"&call_id={request_data.call_id}&Direction=outbound"
        )

        dial_result = await exotel_client.initiate_outbound_call(
            from_phone_number=request_data.from_phone_number,
            to_phone_number=request_data.to_phone_number,
            applet_url=applet_url,
            custom_field=gateway_call_id,
        )
        provider_call_id = dial_result.get("provider_call_id")

        # 2. Update idempotency record
        await idempotency_store.update_status(
            outbound_job_id=request_data.outbound_job_id,
            status=OutboundCallStatus.RINGING,
            provider_call_id=provider_call_id,
        )

        slog.info(
            "outbound_call_dialed_success",
            outbound_job_id=mask_identifier(request_data.outbound_job_id),
            call_id=mask_identifier(request_data.call_id),
            gateway_call_id=gateway_call_id,
            provider_call_id=mask_identifier(provider_call_id or ""),
        )

        # 3. Notify Backend of status change to RINGING (Contract 4)
        callback_payload = OutboundCallStatusCallbackPayload(
            call_id=request_data.call_id,
            outbound_job_id=request_data.outbound_job_id,
            gateway_call_id=gateway_call_id,
            provider_call_id=provider_call_id,
            status=OutboundCallStatus.RINGING,
        )
        await backend_client.send_call_status(callback_payload)

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Outbound dialing failed for job=%s, call_id=%s: %s",
            request_data.outbound_job_id,
            request_data.call_id,
            str(exc),
        )
        # Update status to FAILED in idempotency store
        await idempotency_store.update_status(
            outbound_job_id=request_data.outbound_job_id,
            status=OutboundCallStatus.FAILED,
            provider_call_id=provider_call_id,
        )
        # Notify Backend of failure (Contract 4)
        failure_payload = OutboundCallStatusCallbackPayload(
            call_id=request_data.call_id,
            outbound_job_id=request_data.outbound_job_id,
            gateway_call_id=gateway_call_id,
            provider_call_id=provider_call_id,
            status=OutboundCallStatus.FAILED,
            failure_code="PROVIDER_ERROR",
            failure_reason=str(exc)[:200],
        )
        await backend_client.send_call_status(failure_payload)


@router.post(
    "/outbound-calls",
    response_model=OutboundCallResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Backend Outbound Call Request",
    description="Initiates an outbound customer call connecting to Voice Engine (Contract 1).",
)
async def request_outbound_call(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[TelephonySettings, Depends(get_telephony_settings)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    _auth: None = Depends(verify_internal_service_key),
) -> OutboundCallResponse:
    """Process outbound call request with strict idempotency and tenant isolation."""
    # 1. Parse JSON body
    try:
        body_json = await request.json()
    except Exception as parse_err:
        logger.warning("Invalid JSON body received in outbound-calls: %s", parse_err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INVALID_REQUEST: Malformed JSON body",
        ) from parse_err

    # 2. Validate payload model
    try:
        call_req = OutboundCallRequest.model_validate(body_json)
    except ValidationError as val_err:
        errors = val_err.errors()
        if errors:
            first_err = errors[0]
            err_msg = str(first_err.get("msg", str(val_err)))
            loc_tuple = first_err.get("loc", ("request",))
            field_name = str(loc_tuple[-1]) if loc_tuple else "request"
        else:
            err_msg = str(val_err)
            field_name = "request"

        if "phone" in field_name.lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"INVALID_PHONE_NUMBER: {err_msg}",
            ) from val_err

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"INVALID_REQUEST: Validation failed on '{field_name}': {err_msg}",
        ) from val_err

    # 3. Validate Idempotency-Key consistency (Contract 1 & 2)
    effective_idempotency_key = idempotency_key or call_req.outbound_job_id
    if effective_idempotency_key != call_req.outbound_job_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INVALID_REQUEST: Idempotency-Key header must match outbound_job_id",
        )

    # 4. Enforce Persistent Idempotency Store (Contract 2)
    idempotency_store = get_idempotency_store(
        db_path=getattr(settings, "outbound_idempotency_store_path", "data/outbound_idempotency.db")
    )
    generated_gateway_call_id = f"gw_{uuid.uuid4().hex}"

    try:
        record, is_new = await idempotency_store.register_or_get(
            request=call_req,
            gateway_call_id=generated_gateway_call_id,
        )
    except IdempotencyConflictError as conflict_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"IDEMPOTENCY_CONFLICT: {conflict_err}",
        ) from conflict_err

    # Duplicate call protection: If existing record found, return mapping without re-dialing
    if not is_new:
        slog.info(
            "outbound_idempotent_duplicate_request",
            outbound_job_id=mask_identifier(record.outbound_job_id),
            call_id=mask_identifier(record.call_id),
            gateway_call_id=record.gateway_call_id,
            status=record.status.value,
        )
        return OutboundCallResponse(
            accepted=True,
            outbound_job_id=record.outbound_job_id,
            call_id=record.call_id,
            gateway_call_id=record.gateway_call_id,
            provider_call_id=record.provider_call_id,
            status=record.status,
        )

    # 5. Pre-register session in RealtimeSessionManager
    session_manager = get_realtime_session_manager(settings=settings)
    session_id = f"outbound_{call_req.call_id}_{record.gateway_call_id[:8]}"
    await session_manager.create_session(
        session_id=session_id,
        call_sid=call_req.call_id,
        call_id=call_req.call_id,
        outbound_job_id=call_req.outbound_job_id,
        campaign_id=call_req.campaign_id,
        contact_id=call_req.contact_id,
        organization_id=call_req.organization_id,
        agent_id=call_req.agent_id,
        from_number=call_req.from_phone_number,
        to_number=call_req.to_phone_number,
        call_direction="outbound",
        provider="exotel",
        provider_metadata={
            "gateway_call_id": record.gateway_call_id,
            "outbound_job_id": call_req.outbound_job_id,
            "language": call_req.language,
            "metadata": call_req.metadata,
        },
    )

    # 6. Schedule background dispatch task
    backend_client = BackendStatusCallbackClient(settings=settings)
    background_tasks.add_task(
        _dispatch_outbound_call_task,
        request_data=call_req,
        gateway_call_id=record.gateway_call_id,
        settings=settings,
        idempotency_store=idempotency_store,
        backend_client=backend_client,
        session_manager=session_manager,
    )

    slog.info(
        "outbound_call_accepted",
        outbound_job_id=mask_identifier(record.outbound_job_id),
        call_id=mask_identifier(record.call_id),
        gateway_call_id=record.gateway_call_id,
        status=OutboundCallStatus.DIALING.value,
    )

    return OutboundCallResponse(
        accepted=True,
        outbound_job_id=record.outbound_job_id,
        call_id=record.call_id,
        gateway_call_id=record.gateway_call_id,
        provider_call_id=None,
        status=OutboundCallStatus.DIALING,
    )
