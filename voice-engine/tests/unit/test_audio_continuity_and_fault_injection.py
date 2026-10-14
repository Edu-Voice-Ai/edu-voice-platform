"""Synthetic Fault-Injection and Audio Continuity Tests.

Verifies:
1. AudioChunker flush_frames preserves 100% of buffered audio frames without dropping head or middle frames.
2. Inter-chunk delay (slow TTS chunk arrival) does not cause watchdog to prematurely cancel playback.
3. Mid-stream barge-in invalidates active playback generation and halts playout immediately.
4. Ordered playback prevents stale audio from an interrupted turn from leaking into subsequent turns.
5. Audio frame sequence numbers remain strictly sequential and monotonic.
"""

import asyncio
import time
import numpy as np
import pytest

from app.audio.buffering import AudioChunker
from app.audio.frames import AudioFrame
from app.session.state import SessionState, TurnStateEnum, GenerationLifecycleState
from app.pipeline.turn_manager import TurnManager
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.cancellation import CancellationToken


# ─── 1. Audio Chunker Frame Preservation Tests ─────────────────────────────────

def test_audio_chunker_flush_preserves_all_accumulated_frames():
    """
    Feed 50ms of audio (2.5 frames of 20ms at 16kHz mono = 1600 bytes).
    chunker.feed() emits 2 complete frames (40ms, 1280 bytes).
    Remaining accumulator has 10ms (320 bytes).
    flush_frames() must emit the 3rd frame padded to uniform 20ms, dropping ZERO audio.
    """
    chunker = AudioChunker(sample_rate=16000, frame_duration_ms=20, channels=1)
    bytes_per_frame = 640  # 16000 * 0.02 * 2
    raw_audio = b"\x01\x02" * 800  # 1600 bytes = 50ms

    frames = chunker.feed(raw_audio)
    assert len(frames) == 2
    assert frames[0].seq == 0
    assert frames[1].seq == 1

    # Remaining in accumulator is 1600 - 1280 = 320 bytes
    flush_frames = chunker.flush_frames()
    assert len(flush_frames) == 1
    assert flush_frames[0].seq == 2
    assert len(flush_frames[0].data) == bytes_per_frame
    assert flush_frames[0].data[:320] == raw_audio[1280:]
    assert flush_frames[0].data[320:] == b"\x00" * 320, "Tail must be zero-padded to uniform 20ms"


def test_audio_chunker_continuous_feed_multi_chunk_ordering():
    """Verify feed_continuous stitches consecutive TTS chunks with monotonic sequence numbers."""
    chunker = AudioChunker(sample_rate=16000, frame_duration_ms=20, channels=1)

    chunk_1 = b"\x05\x00" * 3200  # 100ms
    chunk_2 = b"\x0a\x00" * 3200  # 100ms

    frames_1 = chunker.feed_continuous(chunk_1, crossfade_ms=5.0)
    frames_2 = chunker.feed_continuous(chunk_2, crossfade_ms=5.0)
    flushed = chunker.flush_frames()

    all_frames = frames_1 + frames_2 + flushed
    seqs = [f.seq for f in all_frames]
    assert seqs == list(range(len(all_frames))), "Sequences must be contiguous from 0 to N-1"


# ─── 2. Slow TTS Chunk & Watchdog Premature Termination Prevention ─────────────

@pytest.mark.asyncio
async def test_watchdog_does_not_abort_playback_while_synthesizing():
    """
    Simulate a slow second TTS chunk (inter-chunk delay of 400ms).
    Chunk 1 has finished playing on the estimated end-time clock.
    Because is_synthesizing is True, mark_playback_finished must NOT prematurely
    abort playback ownership or clear active_playback_generation_id.
    """
    session = SessionState(
        session_id="s_watchdog_test",
        organization_id="org_apex_univ",
        agent_id="agent_admission"
    )
    session.active_playback_generation_id = "gen_tts_1"
    session.is_bot_speaking = True
    session.user_has_floor = False
    session.playback_estimated_end_time_ms = time.time() * 1000 - 50.0  # Deadline in the past!
    session.is_synthesizing = True  # Second chunk is in-flight over network

    # Call mark_playback_finished(force=True) as the watchdog would
    session.mark_playback_finished(force=True)

    # Verification: State MUST remain protected because synthesis is still active!
    assert session.is_synthesizing is True
    assert session.active_playback_generation_id == "gen_tts_1"
    assert session.is_bot_speaking is True
    assert session.user_has_floor is False

    # Once synthesis completes, is_synthesizing becomes False
    session.is_synthesizing = False
    session.mark_playback_finished(force=True)

    # Verification: Now playback cleanly transitions
    assert session.active_playback_generation_id is None
    assert session.is_bot_speaking is False
    assert session.user_has_floor is True


# ─── 3. Mid-Stream Barge-in and Stale Audio Prevention ────────────────────────

@pytest.mark.asyncio
async def test_barge_in_prevents_stale_audio_leakage():
    """
    Verify that when user interrupts Turn 1 mid-speech:
    1. Generation 1 is cancelled and added to cancelled_generation_ids.
    2. Any subsequent late chunk from Generation 1 is immediately discarded.
    3. Turn 2 receives a fresh generation ID and cannot play Turn 1 audio.
    """
    session = SessionState(
        session_id="s_barge_in_test",
        organization_id="org_apex_univ",
        agent_id="agent_admission"
    )
    turn_1 = session.start_new_turn()
    turn_1.generation_id = "gen_turn_1"
    session.active_playback_generation_id = "gen_turn_1"
    session.is_bot_speaking = True

    # User interrupts!
    session.invalidate_active_generation(reason="User barge-in")

    assert session.is_generation_cancelled("gen_turn_1") is True
    assert session.active_playback_generation_id is None
    assert session.is_bot_speaking is False

    # Simulate late arrival of an audio frame for gen_turn_1
    late_frame_gen = "gen_turn_1"
    is_cancelled = session.is_generation_cancelled(late_frame_gen)
    assert is_cancelled is True, "Late frame from cancelled generation must be marked cancelled!"

    # Now start Turn 2
    turn_2 = session.start_new_turn()
    turn_2.generation_id = "gen_turn_2"
    session.active_playback_generation_id = "gen_turn_2"
    session.is_bot_speaking = True

    assert session.is_generation_cancelled("gen_turn_2") is False
    assert session.active_playback_generation_id == "gen_turn_2"
    # Turn 1 remains permanently cancelled
    assert session.is_generation_cancelled("gen_turn_1") is True


# ─── 4. TurnManager Adaptive Silence Duration ─────────────────────────────────

def test_turn_manager_adaptive_silence_duration():
    """
    Verify TurnManager uses short silence (350ms) for brief utterances (<=500ms speech)
    and conversational silence (600ms+) for longer multi-phrase utterances (>500ms speech).
    """
    session = SessionState(
        session_id="s_vad_test",
        organization_id="org_apex",
        agent_id="agent_1",
        language_selection_complete=True
    )
    queues = PipelineQueueBundle()
    tm = TurnManager(
        session=session,
        queues=queues,
        min_silence_duration_ms=350,
        normal_silence_ms=650,
        short_utterance_silence_ms=350
    )

    # Brief utterance (<= 500ms total speech)
    tm._total_turn_speech_ms = 400.0
    assert tm.effective_silence_duration_ms == 350.0

    # Conversational multi-word utterance (> 500ms total speech)
    tm._total_turn_speech_ms = 1200.0
    assert tm.effective_silence_duration_ms == 650.0, "Conversational pause must use adaptive silence!"
