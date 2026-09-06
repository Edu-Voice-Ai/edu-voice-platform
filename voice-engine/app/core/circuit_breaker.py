"""Asynchronous Circuit Breaker implementation for resilient external API providers (STT, LLM, TTS)."""
import asyncio
import time
from enum import Enum
from typing import Callable, Any, Optional, TypeVar, Coroutine
from app.core.logging import get_logger

logger = get_logger("core.circuit_breaker")

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "CLOSED"       # Normal operation; calls pass through
    OPEN = "OPEN"           # Failing; calls fast-fail or route to fallback
    HALF_OPEN = "HALF_OPEN" # Testing if service recovered


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while circuit is open and no fallback exists."""
    pass


class CircuitBreaker:
    """
    Thread-safe, asyncio-native circuit breaker.
    Monitors consecutive failures, trips to OPEN after threshold, and tests recovery after timeout.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 10.0,
        half_open_success_threshold: int = 2
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_success_threshold = half_open_success_threshold

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        self.last_failure_time_ms: float = 0.0
        self.last_state_change_time_ms: float = time.time() * 1000
        self._lock = asyncio.Lock()

    def is_available(self) -> bool:
        """Check if calls can be executed without acquiring lock (fast path)."""
        if self.state == CircuitState.CLOSED:
            return True
        now_ms = time.time() * 1000
        if self.state == CircuitState.OPEN and (now_ms - self.last_failure_time_ms) >= (self.recovery_timeout_seconds * 1000):
            return True
        return self.state == CircuitState.HALF_OPEN

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        fallback: Optional[Callable[..., Coroutine[Any, Any, T]]] = None,
        **kwargs: Any
    ) -> T:
        """Execute async function protected by the circuit breaker."""
        async with self._lock:
            now_ms = time.time() * 1000
            
            # Check if recovery timeout expired to transition OPEN -> HALF_OPEN
            if self.state == CircuitState.OPEN:
                if (now_ms - self.last_failure_time_ms) >= (self.recovery_timeout_seconds * 1000):
                    logger.info(f"[CIRCUIT_BREAKER:{self.name}] Recovery timeout expired. Transitioning OPEN -> HALF_OPEN.")
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.last_state_change_time_ms = now_ms
                else:
                    logger.warning(f"[CIRCUIT_BREAKER:{self.name}] Circuit is OPEN. Fast-failing / falling back.")
                    if fallback:
                        return await fallback(*args, **kwargs)
                    raise CircuitBreakerOpenException(f"Circuit {self.name} is OPEN.")

        # Execute the operation outside the lock so we don't serialize concurrent requests
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except asyncio.CancelledError:
            # Task cancellation is not considered a provider failure
            raise
        except Exception as e:
            await self._on_failure(e)
            if fallback:
                logger.info(f"[CIRCUIT_BREAKER:{self.name}] Executing fallback due to error: {e}")
                return await fallback(*args, **kwargs)
            raise

    async def _on_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.half_open_success_threshold:
                    logger.info(f"[CIRCUIT_BREAKER:{self.name}] Recovery confirmed ({self.success_count} successes). Transitioning HALF_OPEN -> CLOSED.")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.last_state_change_time_ms = time.time() * 1000
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on successful normal call
                self.failure_count = 0

    async def _on_failure(self, error: Exception):
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time_ms = time.time() * 1000
            logger.warning(
                f"[CIRCUIT_BREAKER:{self.name}] Failure recorded ({self.failure_count}/{self.failure_threshold}): {error}"
            )

            if self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN) and self.failure_count >= self.failure_threshold:
                logger.error(f"[CIRCUIT_BREAKER:{self.name}] Threshold exceeded. Tripping circuit to OPEN!")
                self.state = CircuitState.OPEN
                self.last_state_change_time_ms = self.last_failure_time_ms
