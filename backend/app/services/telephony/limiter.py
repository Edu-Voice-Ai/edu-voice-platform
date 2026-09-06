"""Lightweight in-memory Rate Limiting and Connection Protection.

Provides sliding-window connection rate limiting and active session limits
without requiring external Redis infrastructure.
"""

import threading
import time
from collections import defaultdict


class GatewayRateLimiter:
    """In-memory sliding window rate limiter for incoming connections."""

    def __init__(
        self,
        max_connections_per_window: int = 100,
        window_seconds: int = 60,
    ) -> None:
        self.max_connections: int = max_connections_per_window
        self.window_seconds: int = window_seconds
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock: threading.Lock = threading.Lock()

    def is_allowed(self, client_key: str) -> bool:
        """Check if connection from client_key (e.g. IP or caller DID) is allowed."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Clean old entries
            timestamps = self._history[client_key]
            valid_timestamps = [t for t in timestamps if t > cutoff]
            self._history[client_key] = valid_timestamps

            if len(valid_timestamps) >= self.max_connections:
                return False

            self._history[client_key].append(now)
            return True

    def reset(self) -> None:
        """Clear all rate limit history."""
        with self._lock:
            self._history.clear()


# Global rate limiter instance
_global_rate_limiter: GatewayRateLimiter | None = None


def get_gateway_rate_limiter(
    max_connections: int = 100,
    window_seconds: int = 60,
) -> GatewayRateLimiter:
    """Return the global GatewayRateLimiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = GatewayRateLimiter(
            max_connections_per_window=max_connections,
            window_seconds=window_seconds,
        )
    return _global_rate_limiter
