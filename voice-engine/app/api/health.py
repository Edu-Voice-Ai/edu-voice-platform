"""Healthcheck, liveness, and telemetry endpoints."""
from fastapi import APIRouter
from app.session.manager import get_session_manager
from app.metrics.events import MetricsCollector

router = APIRouter(tags=["Health & Telemetry"])


@router.get("/health")
async def health_check():
    """Service health and liveness probe."""
    manager = get_session_manager()
    active_sessions = await manager.active_session_count()
    return {
        "status": "healthy",
        "service": "edu-voice-engine",
        "active_sessions": active_sessions
    }


@router.get("/metrics")
async def get_metrics():
    """Retrieve turn latency percentiles and performance metrics."""
    tracker = MetricsCollector.get_tracker()
    return tracker.calculate_percentiles()
