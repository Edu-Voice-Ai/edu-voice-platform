# ==============================================================================
# Edu-Voice-Ai Backend — Production Dockerfile
# Multi-tenant Voice AI Platform (FastAPI + SQLAlchemy + Supabase/PostgreSQL)
# ==============================================================================

FROM python:3.12-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies (curl for healthchecks, libpq for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source code, SQL migrations, and scripts
COPY backend/app /app/app
COPY backend/migrations /app/migrations
COPY backend/scripts /app/scripts

# Expose FastAPI service port
EXPOSE 8000

# Docker Healthcheck probe
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI application via Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
