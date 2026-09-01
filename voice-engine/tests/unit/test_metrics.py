"""Unit tests for LatencyTracker and TurnMetrics calculation."""
import pytest
from app.metrics.latency import LatencyTracker, TurnMetrics


def test_turn_metrics_calculation():
    m = TurnMetrics(
        session_id="s1",
        turn_id="t1",
        generation_id="g1",
        speech_start_time_ms=1000.0,
        speech_end_time_ms=2000.0,
        stt_start_time_ms=2050.0,
        stt_end_time_ms=2200.0,
        llm_start_time_ms=2210.0,
        llm_first_token_time_ms=2290.0,
        llm_end_time_ms=2450.0,
        tts_start_time_ms=2300.0,
        tts_first_audio_time_ms=2400.0,
        tts_end_time_ms=2800.0,
    )
    
    assert m.vad_latency_ms == 1000.0
    assert m.stt_latency_ms == 150.0
    assert m.time_to_first_token_ms == 80.0
    assert m.time_to_first_audio_ms == 400.0  # 2400 - 2000
    assert m.total_turn_latency_ms == 800.0


def test_latency_tracker_percentiles():
    tracker = LatencyTracker()
    for latency in [100.0, 200.0, 300.0, 400.0, 500.0]:
        m = TurnMetrics(
            session_id="s", turn_id="t", generation_id="g",
            speech_end_time_ms=1000.0,
            tts_first_audio_time_ms=1000.0 + latency
        )
        tracker.record_turn(m)

    stats = tracker.calculate_percentiles()
    assert stats["turn_count"] == 5
    assert stats["first_audio_latency_p50_ms"] == 300.0
