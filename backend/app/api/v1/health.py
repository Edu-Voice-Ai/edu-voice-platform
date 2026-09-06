"""Health and readiness check endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.services.telephony.metrics import get_gateway_metrics
from backend.app.services.telephony.schemas import HealthResponse
from backend.app.services.telephony.session_manager import get_realtime_session_manager

router = APIRouter(tags=["Health"])


class ReadinessResponse(BaseModel):
    """Application readiness response."""

    status: str = Field(default="ready")
    service: str = Field(default="edu-voice-ai-backend")
    active_sessions: int = Field(default=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Process Liveness Check",
)
async def health_check() -> HealthResponse:
    """Return process liveness without external infrastructure dependencies."""
    return HealthResponse(
        status="ok",
        service="edu-voice-ai-backend",
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Process Readiness Check",
)
async def readiness_check() -> ReadinessResponse:
    """Return readiness status verifying Gateway initialized and accepting traffic."""
    manager = get_realtime_session_manager()
    if not manager.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway is not ready to accept connections",
        )

    active_count = await manager.active_session_count()
    return ReadinessResponse(
        status="ready",
        service="edu-voice-ai-backend",
        active_sessions=active_count,
    )


@router.get(
    "/metrics",
    summary="Internal Telephony Gateway Metrics Snapshot",
)
async def metrics_snapshot() -> dict:
    """Return current snapshot of internal gateway telemetry counters."""
    metrics = get_gateway_metrics()
    return metrics.get_snapshot()
