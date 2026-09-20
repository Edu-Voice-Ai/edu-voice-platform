"""
Edu-Voice-Ai — Health & Readiness Endpoints
"""

from fastapi import APIRouter, status
from app.core.config import settings
from app.db.session import check_database_health
from app.services.voice_engine import voice_engine_client
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def get_health() -> HealthResponse:
    """Basic liveness probe to verify FastAPI application is running."""
    return HealthResponse(
        status="ok",
        service="edu-voice-backend",
        version="1.0.0",
        environment=settings.ENVIRONMENT,
    )


@router.get("/ready", response_model=ReadinessResponse, status_code=status.HTTP_200_OK)
async def get_readiness() -> ReadinessResponse:
    """Readiness probe to verify database and critical dependencies."""
    db_healthy = await check_database_health()
    voice_health = await voice_engine_client.check_health()

    is_ready = db_healthy
    return ReadinessResponse(
        status="ready" if is_ready else "degraded",
        database=db_healthy,
        details={
            "database": "connected" if db_healthy else "disconnected",
            "voice_engine": voice_health.get("status", "unknown"),
        },
    )
