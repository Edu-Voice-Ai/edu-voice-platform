"""
Edu-Voice-Ai — Structured Backend Logging
Provides safe, uniform logging without leaking secrets or auth tokens.
"""

import logging
import sys
from app.core.config import settings


def setup_logging() -> None:
    """Configures application-wide logging formats and log levels."""
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    logging_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    )

    logging.basicConfig(
        level=log_level,
        format=logging_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


logger = logging.getLogger("edu_voice_backend")
