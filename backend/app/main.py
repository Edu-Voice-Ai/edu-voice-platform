"""
Edu-Voice-Ai — FastAPI Main Application Entrypoint
Orchestrates lifespan lifecycle, CORS, standardized error handlers, and v1 API routing.
"""

from contextlib import asynccontextmanager
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from app.db.session import engine
from app.api.v1.router import api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for FastAPI application."""
    # 1. Startup
    setup_logging()
    logger.info(f"Starting {settings.PROJECT_NAME} in '{settings.ENVIRONMENT}' environment...")
    logger.info(f"API endpoints mounted at: {settings.API_V1_STR}")
    logger.info(f"OpenAPI documentation available at /docs and /redoc")

    yield

    # 2. Shutdown
    logger.info("Shutting down application and disposing database connection pools...")
    await engine.dispose()
    logger.info("Graceful shutdown complete.")


# Initialize FastAPI Application
app = FastAPI(
    title="Edu-Voice-Ai API",
    description="Multi-tenant Voice AI Platform for Educational Institutions (Admission AI, Telephony, and RAG Intelligence).",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing & access logging middleware
@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000.0
    
    # Avoid logging raw health checks repeatedly in production
    if not request.url.path.endswith("/health"):
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.2f}ms)"
        )
    return response


# Register Exception Handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Mount API v1 Master Router
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root_info():
    """Root metadata endpoint."""
    return {
        "project": "Edu-Voice-Ai",
        "service": "FastAPI Backend",
        "api_v1": settings.API_V1_STR,
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health",
    }


@app.get("/health", tags=["Health"])
async def root_health():
    """Root liveness probe endpoint."""
    return {
        "status": "ok",
        "service": "edu-voice-backend",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }

