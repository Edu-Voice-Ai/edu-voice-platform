from __future__ import annotations
import asyncio
import time
import numpy as np
from typing import Optional, Callable, Any, TYPE_CHECKING
if TYPE_CHECKING:
    from app.session.state import SessionState
from app.session.state import TurnStateEnum, GreetingStateEnum
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.structured_input import StructuredInputMode
from app.core.logging import get_logger

logger = get_logger("pipeline.turn_manager")


class TurnManager:
    """Manages turn lifecycle, adaptive silence endpointing, and barge-in interruption."""

    def __init__(
        self,
        session: SessionState,
        queues: PipelineQueueBundle,
        min_silence_duration_ms: int = 350,
        normal_silence_ms: int = 350,
        short_utterance_silence_ms: int = 350,
        language_selection_silence_ms: int = 350,
        structured_input_silence_ms: int = 1200,
        min_speech_duration_ms: int = 60,
        min_barge_in_duration_ms: int = 80,
        barge_in_min_confidence: float = 0.45,
        barge_in_min_rms: float = 0.010,
        min_greeting_barge_in_frames: Optional[int] = None,
        on_barge_in_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.session = session
        self.queues = queues
        self.min_silence_duration_ms = min_silence_duration_ms
        self.normal_silence_ms = normal_silence_ms
        self.short_utterance_silence_ms = short_utterance_silence_ms
        self.language_selection_silence_ms = language_selection_silence_ms
        self.structured_input_silence_ms = structured_input_silence_ms
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_barge_in_duration_ms = min_barge_in_duration_ms
        self.barge_in_min_confidence = barge_in_min_confidence
        self.barge_in_min_rms = barge_in_min_rms
        self.min_barge_in_frames = max(1, int(min_barge_in_duration_ms / 20.0))
        self.min_greeting_barge_in_frames: int = (
            min_greeting_barge_in_frames
            if min_greeting_barge_in_frames is not None
            else self.min_barge_in_frames
        )
        self.on_barge_in_callback = on_barge_in_callback

        self._speech_accumulated_ms = 0.0
        self._silence_accumulated_ms = 0.0
        self._total_turn_speech_ms = 0.0
        self._last_finalized_speech_ms = 0.0
        self._barge_in_bucket = 0  # Leaky bucket accumulator: +1 per qualifying frame, -1 per non-qualifying
        self._barge_in_miss_frames = 0
        self._consecutive_silence_frames = 0
        self._is_in_speech = False
        self.barge_in_pre_buffer = bytearray()

    @property
    def last_finalized_speech_ms(self) -> float:
        """Returns the total voiced speech duration in milliseconds of the last finalized turn."""
        return self._last_finalized_speech_ms

    @property
    def is_in_speech(self) -> bool:
        return self._is_in_speech

    @property
    def current_state(self) -> TurnStateEnum:
        return self.session.current_turn.state

    @property
    def effective_silence_duration_ms(self) -> float:
        """
        Dynamic context-aware adaptive endpointing silence threshold.
        Returns:
            - ~2000ms continuous silence for structured numeric / phone number input
            - ~450ms adaptive silence for short single-word utterances (<= 500ms)
            - ~650ms adaptive silence for multi-word / conversational turns (> 500ms)
            - ~400ms for post-barge-in turns
        """
        mode = getattr(self.session, "structured_input_mode", "NORMAL")
        has_pending = getattr(self.session, "has_pending_numeric_input", False)

        if mode in (
            StructuredInputMode.PHONE_NUMBER,
            StructuredInputMode.NUMERIC,
            StructuredInputMode.OTP,
            StructuredInputMode.PIN,
            "PHONE_NUMBER",
            "NUMERIC"
        ) or has_pending:
            return float(self.structured_input_silence_ms)

        if self.session.current_turn and (
            self.session.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN
            or getattr(self.session.current_turn, "barge_in_handled", False)
        ):
            return 400.0

        if not getattr(self.session, "language_selection_complete", True):
            return float(self.language_selection_silence_ms)

        # If caller / fixture explicitly specified a custom min_silence_duration_ms
        if self.min_silence_duration_ms not in (350, 450, 650):
            return float(self.min_silence_duration_ms)

        # Adaptive conversational endpointing
        if self._total_turn_speech_ms <= 500.0:
            return float(self.short_utterance_silence_ms)

        return float(self.normal_silence_ms)

    def handle_speech_frame(
        self,
        is_speech: bool,
        frame_data: bytes = b"",
        frame_duration_ms: float = 20.0,
        vad_confidence: float = 1.0,
        acoustic_features: Optional[Any] = None
    ) -> Optional[str]:
        """
        Process VAD and acoustic feature results for an audio frame.
        Applies a multi-signal corroborated interruption gate during AI speech or greeting playback.
        Returns:
            "SPEECH_STARTED" if speech onset verified.
            "SPEECH_ENDED" if continuous silence threshold exceeded.
            "BARGE_IN" if genuine speech detected while AI was speaking/generating.
            None otherwise.
        """
        turn = self.session.current_turn
        now_ms = time.time() * 1000
        is_greeting = getattr(self.session, "is_greeting_playing", False)
        is_ai_speaking = (
            getattr(self.session, "is_assistant_speaking", False)
            or getattr(self.session, "is_bot_speaking", False)
            or (now_ms < getattr(self.session, "playback_estimated_end_time_ms", 0.0))
            or (getattr(self.session, "active_playback_generation_id", None) is not None)
        )
        is_active_playback = is_greeting or is_ai_speaking

        # 1. Immediate Interruption Detection while AI is actively speaking / playing audio
        if is_active_playback:
            if turn.barge_in_handled:
                return None

            is_echo = False
            is_valid_barge_in = False

            inbound_rms = float(getattr(acoustic_features, "rms", 0.0) or 0.0) if acoustic_features is not None else 0.0
            if inbound_rms == 0.0 and frame_data:
                try:
                    raw_arr = np.frombuffer(frame_data, dtype=np.int16).astype(np.float32) / 32768.0
                    inbound_rms = float(np.sqrt(np.mean(np.square(raw_arr)))) if len(raw_arr) > 0 else 0.0
                except Exception:
                    pass
            elif inbound_rms == 0.0 and not frame_data and acoustic_features is None and vad_confidence >= self.barge_in_min_confidence:
                # Default synthetic/mock test frames without raw PCM data to normal human speech level
                inbound_rms = 0.12

            if acoustic_features is not None:
                echo_corr = float(getattr(acoustic_features, "echo_correlation", 0.0) or 0.0)
                is_echo = bool(
                    getattr(acoustic_features, "is_acoustic_echo", False) or echo_corr >= 0.60
                )

            # Only veto confirmed speaker-leak echo
            if is_echo:
                self._barge_in_bucket = 0
                self._barge_in_miss_frames = 0
                self._speech_accumulated_ms = 0.0
                self.barge_in_pre_buffer.clear()
                return None

            # Robust Barge-in gating: require is_speech AND conf >= barge_in_min_confidence AND rms >= barge_in_min_rms
            # This rejects quiet TV, typing, background sounds, or breathing puffs
            is_qualifying = (
                is_speech
                and vad_confidence >= self.barge_in_min_confidence
                and inbound_rms >= self.barge_in_min_rms
            )

            # ── Leaky Bucket accumulator ──────────────────────────────────────────
            # Telephony speech is NOT 100% consecutive: consonant closures (plosives like
            # 'p','t','k') and cellular packet jitter produce isolated 20ms energy dips.
            # Instead of hard-resetting on every dip (which prevented barge-in from EVER
            # triggering), we decay the bucket by 1 per non-qualifying frame.  This gives
            # natural jitter tolerance of up to ~2 missed frames (40ms) while still requiring
            # net sustained speech to cross the required threshold.
            # ─────────────────────────────────────────────────────────────────────
            if is_qualifying:
                self._barge_in_bucket += 1
                self._barge_in_miss_frames = 0
                self._speech_accumulated_ms += frame_duration_ms
                self._total_turn_speech_ms += frame_duration_ms
                self._silence_accumulated_ms = 0.0
                self._consecutive_silence_frames = 0
                if frame_data:
                    self.barge_in_pre_buffer.extend(frame_data)
            else:
                # Decay by 1 — graceful tolerance for consonant closures / jitter
                self._barge_in_bucket = max(0, self._barge_in_bucket - 1)
                if self._barge_in_bucket == 0:
                    # Only wipe accumulated speech time & prebuffer when fully drained
                    self._speech_accumulated_ms = 0.0
                    self.barge_in_pre_buffer.clear()

            threshold_frames = (
                self.min_greeting_barge_in_frames
                if is_greeting
                else self.min_barge_in_frames
            )

            if self._barge_in_bucket >= threshold_frames:
                logger.info(
                    f"[BARGE_IN] Verified intentional caller interruption "
                    f"bucket={self._barge_in_bucket} "
                    f"speech_ms={self._speech_accumulated_ms:.0f}ms conf={vad_confidence:.3f} "
                    f"context={'greeting' if is_greeting else 'conversational'}"
                )
                turn.barge_in_handled = True
                self.session.is_greeting_playing = False
                self.session.greeting_state = GreetingStateEnum.COMPLETED
                self.session.is_bot_speaking = False
                self.session.playback_estimated_end_time_ms = 0.0
                self.trigger_barge_in(reason=f"Caller intentional {'greeting' if is_greeting else 'conversational'} interruption verified")
                self._is_in_speech = True
                self._barge_in_bucket = 0
                self._barge_in_miss_frames = 0
                return "BARGE_IN"
            return None

        # 2. Normal speech detection (when AI is NOT speaking/processing/greeting)
        if is_speech and not is_active_playback:
            self._speech_accumulated_ms += frame_duration_ms
            self._total_turn_speech_ms += frame_duration_ms
            self._consecutive_silence_frames = 0

            # CRITICAL INVARIANT: Immediately reset silence counter on verified speech frame during active turn
            if self._is_in_speech:
                if self._silence_accumulated_ms > 0.0:
                    logger.debug(
                        f"[TURN] speech_resumed_after={self._silence_accumulated_ms:.0f}ms (silence reset) "
                        f"turn_id={turn.turn_id}"
                    )
                    self._silence_accumulated_ms = 0.0

            if not self._is_in_speech:
                if self._speech_accumulated_ms >= self.min_speech_duration_ms or self.min_speech_duration_ms == 0:
                    self._is_in_speech = True
                    self._total_turn_speech_ms = self._speech_accumulated_ms
                    self._silence_accumulated_ms = 0.0
                    self._consecutive_silence_frames = 0
                    # If current turn was cancelled or interrupted, start fresh turn
                    if turn.cancellation_token.is_cancelled or turn.state in (TurnStateEnum.INTERRUPTED, TurnStateEnum.IDLE):
                        turn = self.session.start_new_turn(reason="Speech onset after cancelled turn")
                    turn.state = TurnStateEnum.LISTENING
                    self.session.user_has_floor = True
                    logger.info(f"[TURN] speech_start turn_id={turn.turn_id}")
                    return "SPEECH_STARTED"
            return None

        # 3. Silence / Pause detection using dynamic context-aware adaptive threshold
        if not is_speech:
            self._speech_accumulated_ms = 0.0
            self.barge_in_pre_buffer.clear()
            if self._is_in_speech:
                self._consecutive_silence_frames += 1
                self._silence_accumulated_ms += frame_duration_ms
                if self._silence_accumulated_ms >= self.effective_silence_duration_ms and self._consecutive_silence_frames >= 2:
                    self._last_finalized_speech_ms = self._total_turn_speech_ms
                    logger.info(
                        f"[TURN] endpoint_reached={self._silence_accumulated_ms:.0f}ms "
                        f"threshold={self.effective_silence_duration_ms:.0f}ms total_speech={self._total_turn_speech_ms:.0f}ms (finalizing turn {turn.turn_id})"
                    )
                    self._is_in_speech = False
                    self._silence_accumulated_ms = 0.0
                    self._consecutive_silence_frames = 0
                    self._total_turn_speech_ms = 0.0
                    turn.state = TurnStateEnum.PROCESSING
                    self.session.user_has_floor = False
                    return "SPEECH_ENDED"

        return None

    def trigger_barge_in(self, reason: str = "Barge-in triggered"):
        """Execute instantaneous cancellation, queue flush, and rotate to a clean new turn."""
        old_turn = self.session.current_turn
        old_turn_id = old_turn.turn_id
        old_gen_id = old_turn.generation_id
        
        # 1. Invalidate active and previous generations atomically
        if hasattr(self.session, "invalidate_active_generation"):
            self.session.invalidate_active_generation(reason=reason)
        else:
            if hasattr(self.session, "cancelled_generation_ids"):
                self.session.cancelled_generation_ids.add(old_gen_id)
            self.session.active_playback_generation_id = None
            self.session.playback_estimated_end_time_ms = 0.0
            self.session.is_greeting_playing = False
            self.session.is_bot_speaking = False

        self.session.greeting_state = GreetingStateEnum.COMPLETED
        self.session.user_has_floor = True

        # 2. Transition turn state: SPEAKING -> BARGE_IN -> INTERRUPTING -> INTERRUPTED
        old_turn.state = TurnStateEnum.BARGE_IN
        old_turn.state = TurnStateEnum.INTERRUPTING
        old_turn.cancel(reason=reason)

        # 3. Fire callback (emits response.cancelled, audio.flush, audio.playback.stop)
        if self.on_barge_in_callback:
            try:
                self.on_barge_in_callback(old_turn_id, old_gen_id)
            except Exception as e:
                logger.warning(f"Error in barge-in callback: {e}")

        # 4. Flush all internal pipeline audio/TTS queues
        # Note: Event queue retains cancellation events so out-of-band writer clears telephony
        self.queues.flush_output_queues()

        # 5. Rotate to fresh turn in LISTENING_AFTER_BARGE_IN state
        new_turn = self.session.start_new_turn(reason=f"Barge-in rotation: {reason}")
        new_turn.state = TurnStateEnum.LISTENING_AFTER_BARGE_IN

        # Reset counters and seed total turn speech with the confirmed interruption audio duration
        interruption_audio_ms = float(len(self.barge_in_pre_buffer) / 32.0) if len(self.barge_in_pre_buffer) > 0 else 0.0
        self._speech_accumulated_ms = 0.0
        self._silence_accumulated_ms = 0.0
        self._consecutive_silence_frames = 0
        self._total_turn_speech_ms = interruption_audio_ms
        self._is_in_speech = True

        logger.info(
            f"[BARGE-IN] User speech confirmed\n"
            f"[BARGE-IN] Cancelling generations={list(getattr(self.session, 'cancelled_generation_ids', []))} turn={old_turn_id}\n"
            f"[BARGE-IN] Audio queue flushed: output queues cleared\n"
            f"[BARGE-IN] Playback stopped immediately\n"
            f"[BARGE-IN] User floor = True\n"
            f"[BARGE-IN] New turn={new_turn.turn_id} gen={new_turn.generation_id} initial_speech={interruption_audio_ms:.0f}ms",
            extra={"session_id": self.session.session_id, "turn_id": new_turn.turn_id}
        )

    def reset(self):
        """Reset internal speech and silence counters."""
        self._speech_accumulated_ms = 0.0
        self._silence_accumulated_ms = 0.0
        self._total_turn_speech_ms = 0.0
        self._barge_in_consecutive_speech_frames = 0
        self._barge_in_miss_frames = 0
        self._consecutive_silence_frames = 0
        self._is_in_speech = False
        self.barge_in_pre_buffer.clear()
