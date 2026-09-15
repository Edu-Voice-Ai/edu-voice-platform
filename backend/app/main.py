"""Edu-Voice-AI Backend Application Entrypoint."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.telephony import router as telephony_router
from backend.app.services.telephony.gateway import WebSocketAudioGateway
from backend.app.services.telephony.session_manager import get_realtime_session_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("edu_voice_ai")


@asynccontextmanager
async def app_lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and graceful shutdown."""
    from backend.app.services.telephony.config import get_telephony_settings

    settings = get_telephony_settings()
    exotel_report = settings.get_exotel_status_report()
    logger.info(
        "Exotel configuration: %s | Exotel account: %s | Exotel API credentials: %s | Exotel Exophone: %s",
        exotel_report["exotel_configuration"],
        exotel_report["exotel_account"],
        exotel_report["exotel_api_credentials"],
        exotel_report["exotel_exophone"],
    )

    manager = get_realtime_session_manager()
    logger.info("Initializing Voice Gateway background pruners...")
    manager.reset_shutdown_state()
    manager.start_cleanup_loop()

    yield

    logger.info("Gracefully shutting down Voice Gateway...")
    await manager.close_all(reason="server_shutdown")
    manager.stop_cleanup_loop()
    logger.info("Voice Gateway shutdown complete.")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    application = FastAPI(
        title="Edu-Voice-AI Gateway & Backend",
        description="Multi-tenant AI communication SaaS platform for educational institutions.",
        version="0.1.0",
        lifespan=app_lifespan,
    )

    # Basic CORS setup
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routers
    application.include_router(health_router, tags=["Health"])
    application.include_router(telephony_router, prefix="/api/v1")

    # Realtime Voice Gateway WebSocket Endpoints
    async def _handle_gateway_ws(websocket: WebSocket, session_id: str | None = None) -> None:
        from backend.app.api.v1.telephony import get_phone_assignment_resolver
        from backend.app.services.telephony.config import get_telephony_settings
        from backend.app.services.telephony.routing.phone_assignment import (
            BackendPhoneAssignmentResolver,
        )

        settings_getter = application.dependency_overrides.get(
            get_telephony_settings, get_telephony_settings
        )
        active_settings = settings_getter()

        resolver_getter = application.dependency_overrides.get(
            get_phone_assignment_resolver, None
        )
        if resolver_getter is not None:
            if callable(resolver_getter):
                try:
                    resolver = resolver_getter(settings=active_settings)
                except TypeError:
                    resolver = resolver_getter()
            else:
                resolver = resolver_getter
        else:
            resolver = BackendPhoneAssignmentResolver(settings=active_settings)

        gw = WebSocketAudioGateway(
            settings=active_settings,
            phone_assignment_resolver=resolver,
        )
        await gw.handle_stream(websocket=websocket, session_id=session_id)

    @application.websocket("/ws/telephony/stream/{session_id}")
    async def websocket_stream_session_endpoint(
        websocket: WebSocket,
        session_id: str,
    ) -> None:
        """Realtime WebSocket Audio Streaming Gateway Endpoint with session_id."""
        await _handle_gateway_ws(websocket=websocket, session_id=session_id)

    @application.websocket("/ws/telephony/stream")
    async def websocket_stream_direct_endpoint(
        websocket: WebSocket,
    ) -> None:
        """Realtime WebSocket Audio Streaming Gateway Endpoint for direct carrier streams."""
        await _handle_gateway_ws(websocket=websocket, session_id=None)

    @application.websocket("/ws/telephony/exotel")
    async def websocket_exotel_direct_endpoint(
        websocket: WebSocket,
    ) -> None:
        """Realtime WebSocket Audio Streaming Gateway Endpoint for direct Exotel Voicebot."""
        await _handle_gateway_ws(websocket=websocket, session_id=None)

    return application


app = create_app()
