"""Telemetry collector singleton."""
from typing import Optional
from app.metrics.latency import LatencyTracker


class MetricsCollector:
    """Global metrics repository."""
    _tracker: LatencyTracker = LatencyTracker()

    @classmethod
    def get_tracker(cls) -> LatencyTracker:
        return cls._tracker
