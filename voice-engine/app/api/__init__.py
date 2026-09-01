"""API routers for HTTP health and WebSocket voice session."""
from app.api.health import router as health_router
from app.api.websocket import router as ws_router

__all__ = ["health_router", "ws_router"]
