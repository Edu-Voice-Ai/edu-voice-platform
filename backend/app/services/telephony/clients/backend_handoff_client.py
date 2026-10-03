"""Authoritative Backend Human Handoff HTTP Client.

Implements client integration with Aravind's FastAPI internal endpoints:
1. POST /api/v1/internal/telephony/resolve-handoff (Deterministic Staff Match)
2. POST /api/v1/internal/telephony/handoff-status (Handoff Lifecycle Tracking)

Adheres strictly to UNIVERSAL_CALL_HANDOFF_REQUIREMENTS.md and YASIN_CALL_HANDOFF_IMPLEMENTATION.md.
"""

from __future__ import annotations

import json
import logging
import time

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.logging import (
    StructuredGatewayLogger,
    mask_phone_number,
)

logger = logging.getLogger("telephony.clients.backend_handoff")
slog = StructuredGatewayLogger("telephony.clients.backend_handoff")


class HandoffResolveRequest(BaseModel):
    """Payload sent by Gateway to Backend to resolve an eligible staff member."""

    model_config = ConfigDict(extra="ignore")

    call_id: str
    organization_id: str
    agent_id: str
    requested_role: str = "admission_counselor"
    requested_department: str = "admissions"
    requested_staff_id: str | None = None
    caller_phone_number: str | None = None
    reason: str = "caller_requested_human"
    confidence: float | None = None


class HandoffStaffData(BaseModel):
    """Staff and routing metadata returned by Backend resolve-handoff."""

    model_config = ConfigDict(extra="ignore")

    eligible: bool
    handoff_id: str | None = None
    organization_id: str | None = None
    staff_member_id: str | None = None
    staff_name: str | None = None
    staff_role: str | None = None
    staff_department: str | None = None
    destination_phone_number: str | None = None
    transfer_timeout_seconds: int = 25
    announcement_message: str | None = None
    holding_announcement: str | None = None
    error_code: str | None = None
    fallback_action: str | None = None
    fallback_message: str | None = None


class HandoffResolveResponse(BaseModel):
    """Envelope response from POST /api/v1/internal/telephony/resolve-handoff."""

    model_config = ConfigDict(extra="ignore")

    success: bool
    message: str | None = None
    data: HandoffStaffData


class HandoffStatusRequest(BaseModel):
    """Status update payload sent by Gateway to Backend."""

    model_config = ConfigDict(extra="ignore")

    handoff_id: str | None = None
    call_id: str
    organization_id: str
    status: str = Field(
        ...,
        description="One of: initiated, ringing, completed, busy, no_answer, failed, canceled",
    )
    provider_transfer_sid: str | None = None
    staff_member_id: str | None = None
    duration_seconds: int | None = None
    failure_reason: str | None = None


class BackendHandoffClient:
    """Authoritative client for dynamic staff resolution and handoff status reporting."""

    def __init__(
        self,
        settings: TelephonySettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_telephony_settings()
        self._http_client = http_client
        self._owns_client = http_client is None

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=1.0,
                    read=float(self.settings.did_resolve_timeout_ms) / 1000.0,
                    write=1.0,
                    pool=2.0,
                ),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._http_client

    async def close(self) -> None:
        """Close internal HTTP client if owned."""
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def resolve_handoff(
        self,
        request: HandoffResolveRequest,
    ) -> HandoffResolveResponse:
        """Query Backend to authoritatively select an active, eligible staff member.

        Fails closed on any network error, timeout, 5xx, or invalid payload.
        """
        url = f"{self.settings.backend_internal_url.rstrip('/')}/api/v1/internal/telephony/resolve-handoff"
        secret_key = (
            self.settings.internal_service_key.get_secret_value()
            if self.settings.internal_service_key
            else ""
        )
        headers = {
            "Content-Type": "application/json",
            "X-Internal-Service-Key": secret_key,
        }

        slog.info(
            "backend_resolve_handoff_request_start",
            call_id=request.call_id,
            org_id=request.organization_id,
            agent_id=request.agent_id,
            requested_role=request.requested_role,
            requested_dept=request.requested_department,
            caller=mask_phone_number(request.caller_phone_number or ""),
        )

        client = self._get_client()
        t0 = time.perf_counter()

        try:
            resp = await client.post(
                url,
                json=request.model_dump(exclude_none=True),
                headers=headers,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0

            if resp.status_code == 200:
                raw_json = resp.json()
                # If response wrapped in canonical {"success": true, "data": {...}}
                parsed = HandoffResolveResponse.model_validate(raw_json)
                slog.info(
                    "backend_resolve_handoff_success",
                    call_id=request.call_id,
                    eligible=parsed.data.eligible,
                    staff_id=parsed.data.staff_member_id,
                    staff_name=parsed.data.staff_name,
                    destination=mask_phone_number(parsed.data.destination_phone_number or ""),
                    error_code=parsed.data.error_code,
                    duration_ms=round(duration_ms, 2),
                )
                return parsed

            # If 4xx / 5xx error
            slog.warning(
                "backend_resolve_handoff_failed_http_status",
                call_id=request.call_id,
                status_code=resp.status_code,
                duration_ms=round(duration_ms, 2),
                body=resp.text[:200],
            )
            return HandoffResolveResponse(
                success=False,
                message=f"Backend HTTP error: {resp.status_code}",
                data=HandoffStaffData(
                    eligible=False,
                    error_code=f"HTTP_{resp.status_code}",
                    fallback_action="ai_announcement",
                    fallback_message="All our admission counselors are currently assisting other callers.",
                ),
            )

        except (httpx.TimeoutException, TimeoutError) as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            slog.warning(
                "backend_resolve_handoff_timeout",
                call_id=request.call_id,
                duration_ms=round(duration_ms, 2),
                error=str(exc),
            )
            return HandoffResolveResponse(
                success=False,
                message="Backend resolve-handoff timeout",
                data=HandoffStaffData(
                    eligible=False,
                    error_code="TIMEOUT",
                    fallback_action="ai_announcement",
                    fallback_message="All our admission counselors are currently assisting other callers.",
                ),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            slog.warning(
                "backend_resolve_handoff_malformed_response",
                call_id=request.call_id,
                duration_ms=round(duration_ms, 2),
                error=str(exc),
            )
            return HandoffResolveResponse(
                success=False,
                message=f"Backend malformed JSON response: {exc}",
                data=HandoffStaffData(
                    eligible=False,
                    error_code="MALFORMED_RESPONSE",
                    fallback_action="ai_announcement",
                    fallback_message="All our admission counselors are currently assisting other callers.",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.perf_counter() - t0) * 1000.0
            slog.warning(
                "backend_resolve_handoff_connection_error",
                call_id=request.call_id,
                duration_ms=round(duration_ms, 2),
                error=str(exc),
            )
            return HandoffResolveResponse(
                success=False,
                message=f"Backend resolve-handoff connection error: {exc}",
                data=HandoffStaffData(
                    eligible=False,
                    error_code="CONNECTION_ERROR",
                    fallback_action="ai_announcement",
                    fallback_message="All our admission counselors are currently assisting other callers.",
                ),
            )

    async def report_handoff_status(
        self,
        request: HandoffStatusRequest,
    ) -> bool:
        """Report handoff lifecycle status updates to the authoritative Backend.

        Statuses: initiated, ringing, completed, busy, no_answer, failed, canceled.
        """
        url = f"{self.settings.backend_internal_url.rstrip('/')}/api/v1/internal/telephony/handoff-status"
        secret_key = (
            self.settings.internal_service_key.get_secret_value()
            if self.settings.internal_service_key
            else ""
        )
        headers = {
            "Content-Type": "application/json",
            "X-Internal-Service-Key": secret_key,
        }

        slog.info(
            "backend_handoff_status_report",
            call_id=request.call_id,
            handoff_id=request.handoff_id,
            org_id=request.organization_id,
            status=request.status,
            staff_id=request.staff_member_id,
            provider_sid=request.provider_transfer_sid,
            failure_reason=request.failure_reason,
        )

        client = self._get_client()
        try:
            resp = await client.post(
                url,
                json=request.model_dump(exclude_none=True),
                headers=headers,
            )
            return resp.status_code in (200, 201, 204)
        except Exception as exc:  # noqa: BLE001
            slog.warning(
                "backend_handoff_status_report_failed",
                call_id=request.call_id,
                status=request.status,
                error=str(exc),
            )
            return False
