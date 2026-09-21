"""Lightweight in-memory Observability & Metrics Collector for Voice Gateway.

Provides centralized metric counters and gauge trackers ready for future
Prometheus, AWS CloudWatch, or Datadog export without external dependencies.
"""

import threading
from typing import Any


class GatewayMetrics:
    """Thread-safe in-memory metric collector for the Voice Gateway."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._total_sessions_created: int = 0
        self._total_sessions_closed: int = 0
        self._total_connection_failures: int = 0
        self._total_disconnects: int = 0
        self._total_frames_received: int = 0
        self._total_frames_sent: int = 0
        self._total_frames_dropped: int = 0
        self._total_queue_overflows: int = 0
        self._total_interruptions: int = 0
        self._total_rate_limited: int = 0
        self._total_heartbeat_timeouts: int = 0
        self._total_bytes_received: int = 0
        self._total_bytes_sent: int = 0

    def record_session_created(self) -> None:
        with self._lock:
            self._total_sessions_created += 1

    def record_session_closed(self) -> None:
        with self._lock:
            self._total_sessions_closed += 1

    def record_connection_failure(self) -> None:
        with self._lock:
            self._total_connection_failures += 1

    def record_disconnect(self) -> None:
        with self._lock:
            self._total_disconnects += 1

    def record_frame_received(self, byte_count: int = 0) -> None:
        with self._lock:
            self._total_frames_received += 1
            self._total_bytes_received += byte_count

    def record_frame_sent(self, byte_count: int = 0) -> None:
        with self._lock:
            self._total_frames_sent += 1
            self._total_bytes_sent += byte_count

    def record_frame_dropped(self) -> None:
        with self._lock:
            self._total_frames_dropped += 1

    def record_queue_overflow(self) -> None:
        with self._lock:
            self._total_queue_overflows += 1

    def record_interruption(self) -> None:
        with self._lock:
            self._total_interruptions += 1

    def record_rate_limited(self) -> None:
        with self._lock:
            self._total_rate_limited += 1

    def record_heartbeat_timeout(self) -> None:
        with self._lock:
            self._total_heartbeat_timeouts += 1

    def get_snapshot(self) -> dict[str, Any]:
        """Return a snapshot of current telemetry metrics."""
        with self._lock:
            return {
                "sessions_created": self._total_sessions_created,
                "sessions_closed": self._total_sessions_closed,
                "active_sessions": max(
                    0, self._total_sessions_created - self._total_sessions_closed
                ),
                "connection_failures": self._total_connection_failures,
                "disconnects": self._total_disconnects,
                "frames_received": self._total_frames_received,
                "frames_sent": self._total_frames_sent,
                "frames_dropped": self._total_frames_dropped,
                "queue_overflows": self._total_queue_overflows,
                "interruptions": self._total_interruptions,
                "rate_limited_connections": self._total_rate_limited,
                "heartbeat_timeouts": self._total_heartbeat_timeouts,
                "bytes_received": self._total_bytes_received,
                "bytes_sent": self._total_bytes_sent,
            }

    def reset(self) -> None:
        """Reset all metrics (primarily for test harnesses)."""
        with self._lock:
            self._total_sessions_created = 0
            self._total_sessions_closed = 0
            self._total_connection_failures = 0
            self._total_disconnects = 0
            self._total_frames_received = 0
            self._total_frames_sent = 0
            self._total_frames_dropped = 0
            self._total_queue_overflows = 0
            self._total_interruptions = 0
            self._total_rate_limited = 0
            self._total_heartbeat_timeouts = 0
            self._total_bytes_received = 0
            self._total_bytes_sent = 0


# Global metrics collector singleton
_global_metrics: GatewayMetrics | None = None


def get_gateway_metrics() -> GatewayMetrics:
    """Return the global GatewayMetrics collector instance."""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = GatewayMetrics()
    return _global_metrics
