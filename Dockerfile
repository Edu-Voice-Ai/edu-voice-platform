# ==============================================================================
# Edu-Voice-AI — Production Multi-Stage Dockerfile
# Service: Telephony / Voice Gateway & Backend
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build & Dependencies
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

# Install build dependencies if needed for wheel compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements to leverage Docker layer caching
COPY requirements.txt .

# Install dependencies into dedicated prefix
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ------------------------------------------------------------------------------
# Stage 2: Final Production Runtime Image
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

LABEL maintainer="Edu-Voice-AI DevOps <devops@edu-voice-ai.internal>" \
      service="telephony-voice-gateway" \
      version="0.1.0"

# Python runtime configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

# Create non-root system user and group (UID/GID: 10001)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app -M appuser && \
    mkdir -p /app/data && chown -R appuser:appgroup /app/data

# Copy installed dependencies from builder stage
COPY --from=builder /install /usr/local

# Copy application source code
COPY --chown=appuser:appgroup backend /app/backend

# Switch to non-root user
USER appuser

# Expose Gateway HTTP & WebSocket port
EXPOSE 8000

# Container liveness health check using Python standard library (no curl required)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

# Start FastAPI application via Uvicorn ASGI server
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--access-log", "--loop", "uvloop", "--http", "httptools"]
