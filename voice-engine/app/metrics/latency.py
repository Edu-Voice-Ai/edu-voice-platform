"""LatencyTracker measuring VAD, STT, TTFT, TTFB, and Barge-In latencies."""
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import numpy as np


@dataclass
class TurnMetrics:
    """Detailed timing telemetry for a single conversation turn."""
    session_id: str
    turn_id: str
    generation_id: str
    speech_start_time_ms: float = 0.0
    speech_end_time_ms: float = 0.0
    stt_start_time_ms: float = 0.0
    stt_end_time_ms: float = 0.0
    llm_start_time_ms: float = 0.0
    llm_first_token_time_ms: float = 0.0
    llm_end_time_ms: float = 0.0
    tts_start_time_ms: float = 0.0
    tts_first_audio_time_ms: float = 0.0
    tts_end_time_ms: float = 0.0
    barge_in_trigger_time_ms: Optional[float] = None
    barge_in_flushed_time_ms: Optional[float] = None
    response_chars: int = 0
    tts_chunks_count: int = 0

    @property
    def vad_latency_ms(self) -> float:
        return max(0.0, self.speech_end_time_ms - self.speech_start_time_ms)

    @property
    def stt_latency_ms(self) -> float:
        if self.stt_end_time_ms and self.stt_start_time_ms:
            return max(0.0, self.stt_end_time_ms - self.stt_start_time_ms)
        return 0.0

    @property
    def time_to_first_token_ms(self) -> float:
        """LLM Time to First Token (TTFT)."""
        if self.llm_first_token_time_ms and self.llm_start_time_ms:
            return max(0.0, self.llm_first_token_time_ms - self.llm_start_time_ms)
        return 0.0

    @property
    def time_to_first_audio_ms(self) -> float:
        """TTS Time to First Audio (TTFB from speech end to first speaker audio frame)."""
        if self.tts_first_audio_time_ms and self.speech_end_time_ms:
            return max(0.0, self.tts_first_audio_time_ms - self.speech_end_time_ms)
        elif self.tts_first_audio_time_ms and self.tts_start_time_ms:
            return max(0.0, self.tts_first_audio_time_ms - self.tts_start_time_ms)
        return 0.0

    @property
    def total_turn_latency_ms(self) -> float:
        if self.tts_end_time_ms and self.speech_end_time_ms:
            return max(0.0, self.tts_end_time_ms - self.speech_end_time_ms)
        return 0.0

    @property
    def barge_in_latency_ms(self) -> Optional[float]:
        if self.barge_in_flushed_time_ms and self.barge_in_trigger_time_ms:
            return max(0.0, self.barge_in_flushed_time_ms - self.barge_in_trigger_time_ms)
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "generation_id": self.generation_id,
            "vad_latency_ms": round(self.vad_latency_ms, 2),
            "stt_latency_ms": round(self.stt_latency_ms, 2),
            "ttft_ms": round(self.time_to_first_token_ms, 2),
            "first_audio_latency_ms": round(self.time_to_first_audio_ms, 2),
            "total_turn_latency_ms": round(self.total_turn_latency_ms, 2),
            "response_chars": self.response_chars,
            "tts_chunks_count": self.tts_chunks_count,
            "barge_in_latency_ms": round(self.barge_in_latency_ms, 2) if self.barge_in_latency_ms is not None else None
        }


class LatencyTracker:
    """Collects and aggregates timing telemetry across turns and sessions."""

    def __init__(self):
        self._history: List[TurnMetrics] = []

    def record_turn(self, metrics: TurnMetrics):
        self._history.append(metrics)

    def calculate_percentiles(self) -> Dict[str, Any]:
        if not self._history:
            return {}

        first_audios = [m.time_to_first_audio_ms for m in self._history if m.time_to_first_audio_ms > 0]
        ttfts = [m.time_to_first_token_ms for m in self._history if m.time_to_first_token_ms > 0]
        barge_ins = [m.barge_in_latency_ms for m in self._history if m.barge_in_latency_ms is not None]

        return {
            "turn_count": len(self._history),
            "first_audio_latency_p50_ms": float(np.percentile(first_audios, 50)) if first_audios else 0.0,
            "first_audio_latency_p95_ms": float(np.percentile(first_audios, 95)) if first_audios else 0.0,
            "ttft_p50_ms": float(np.percentile(ttfts, 50)) if ttfts else 0.0,
            "ttft_p95_ms": float(np.percentile(ttfts, 95)) if ttfts else 0.0,
            "barge_in_latency_p50_ms": float(np.percentile(barge_ins, 50)) if barge_ins else 0.0,
        }
