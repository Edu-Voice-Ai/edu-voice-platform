"""Structured logging utility with correlation IDs for Voice Engine."""
import logging
import sys
import json
from typing import Optional, Any, Dict


class CorrelationFilter(logging.Filter):
    """Filter that injects correlation context (session_id, turn_id, generation_id)."""
    def __init__(self):
        super().__init__()
        self.session_id = "system"
        self.turn_id = "-"
        self.generation_id = "-"

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "session_id"):
            record.session_id = getattr(self, "session_id", "system")
        if not hasattr(record, "turn_id"):
            record.turn_id = getattr(self, "turn_id", "-")
        if not hasattr(record, "generation_id"):
            record.generation_id = getattr(self, "generation_id", "-")
        return True


class StructuredFormatter(logging.Formatter):
    """Format logs with timestamp, level, correlation IDs, and message."""
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "session_id": getattr(record, "session_id", "system"),
            "turn_id": getattr(record, "turn_id", "-"),
            "generation_id": getattr(record, "generation_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def configure_logging(level: str = "INFO", json_format: bool = False):
    """Configure root and application loggers."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)
    
    # Ensure stdout/stderr handle UTF-8 cleanly on Windows
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # Remove existing handlers
    for handler in list(root.handlers):
        root.removeHandler(handler)
        
    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(StructuredFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
    else:
        fmt = "%(asctime)s [%(levelname)s] [%(name)s] [sess:%(session_id)s|turn:%(turn_id)s] %(message)s"
        formatter = logging.Formatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        
    corr_filter = CorrelationFilter()
    handler.addFilter(corr_filter)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Obtain a logger instance by name."""
    return logging.getLogger(name)
