"""Pipeline orchestration, queues, turn management, and cancellation."""
from app.pipeline.cancellation import CancellationToken

__all__ = [
    "CancellationToken",
    "PipelineQueueBundle",
    "TurnManager",
    "SpeechToSpeechEngine",
]


def __getattr__(name: str):
    if name == "PipelineQueueBundle":
        from app.pipeline.queues import PipelineQueueBundle
        return PipelineQueueBundle
    elif name == "TurnManager":
        from app.pipeline.turn_manager import TurnManager
        return TurnManager
    elif name == "SpeechToSpeechEngine":
        from app.pipeline.engine import SpeechToSpeechEngine
        return SpeechToSpeechEngine
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
