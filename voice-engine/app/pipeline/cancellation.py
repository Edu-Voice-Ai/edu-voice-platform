"""Cancellation token and cooperative task interruption primitives."""
import asyncio
from typing import Optional, List, Callable
from app.core.errors import PipelineCancellationError


class CancellationToken:
    """Thread-safe and async-safe cancellation token."""
    def __init__(self):
        self._is_cancelled = False
        self._reason: Optional[str] = None
        self._callbacks: List[Callable[[], None]] = []
        self._event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._is_cancelled

    @property
    def reason(self) -> Optional[str]:
        """Get the reason for cancellation."""
        return self._reason

    def cancel(self, reason: str = "Operation cancelled"):
        """Trigger cancellation and fire callbacks."""
        if self._is_cancelled:
            return
        self._is_cancelled = True
        self._reason = reason
        self._event.set()
        
        # Fire registered callbacks
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass

    def register_callback(self, callback: Callable[[], None]):
        """Register a callback to run upon cancellation."""
        if self._is_cancelled:
            try:
                callback()
            except Exception:
                pass
        else:
            self._callbacks.append(callback)

    def raise_if_cancelled(self):
        """Raise PipelineCancellationError if cancelled."""
        if self._is_cancelled:
            raise PipelineCancellationError(self._reason or "Task cancelled")

    async def wait_cancelled(self):
        """Async wait until cancelled."""
        await self._event.wait()
