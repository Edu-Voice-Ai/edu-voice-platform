from __future__ import annotations
import asyncio
import time
from typing import Optional, Callable, TYPE_CHECKING
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
        min_silence_duration_ms: int = 650,
        normal_silence_ms: int = 650,
        short_utterance_silence_ms: int = 500,
        language_selection_silence_ms: int = 500,
        structured_input_silence_ms: int = 2000,
        min_speech_duration_ms: int = 60,
        min_barge_in_duration_ms: int = 260,
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
        self.on_barge_in_callback = on_barge_in_callback

        self._speech_accumulated_ms = 0.0
        self._silence_accumulated_ms = 0.0
        self._total_turn_speech_ms = 0.0
        self._is_in_speech = False
        self.barge_in_pre_buffer = bytearray()

    @property
    def current_state(self) -> TurnStateEnum:
        return self.session.current_turn.state

    @property
    def effective_silence_duration_ms(self) -> float:
        """
        Dynamic context-aware adaptive endpointing silence threshold.
        Returns:
            - ~2000ms continuous silence for structured numeric / phone number input
            - ~500ms - 650ms adaptive silence for normal conversational turns and language selection:
                * For short clear utterances (speech <= 600ms): ~500ms
                * For normal conversational utterances (speech > 600ms): ~650ms
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

        # For turns right after a barge-in (LISTENING_AFTER_BARGE_IN), the user is cutting in mid-speech.
        # Callers typically say an interjection ("Wait", "Hold on", "ఆగండి") followed by a 200-400ms pause
        # before the actual question ("BTech fee ఎంత?").
        # If we use 450ms-500ms, the turn prematurely ends on the interjection alone!
        # Giving 800ms ensures the entire interrupted utterance is preserved and transcribed.
        if self.session.current_turn and (
            self.session.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN
            or getattr(self.session.current_turn, "barge_in_handled", False)
        ):
            return 800.0

        if not getattr(self.session, "language_selection_complete", True):
            if self.language_selection_silence_ms != 650:
                return float(self.language_selection_silence_ms)

        # If caller / fixture explicitly specified a custom min_silence_duration_ms
        if self.min_silence_duration_ms != 650:
            return float(self.min_silence_duration_ms)

        # Adaptive conversational endpointing (500ms for short utterances <= 600ms, 650ms for normal)
        if self._total_turn_speech_ms <= 600.0:
            return float(self.short_utterance_silence_ms)

        return float(self.normal_silence_ms)

    def handle_speech_frame(self, is_speech: bool, frame_data: bytes = b"", frame_duration_ms: float = 20.0) -> Optional[str]:
        """
        Process VAD result for an audio frame of given duration.
        Returns:
            "SPEECH_STARTED" if speech onset verified.
            "SPEECH_ENDED" if continuous silence threshold exceeded.
            "BARGE_IN" if genuine speech detected while AI was speaking/generating.
            None otherwise.
        """
        turn = self.session.current_turn
        
        # 1. Check Barge-In Condition: speech detected while AI is actively speaking/playing audio
        is_ai_speaking_or_greeting = getattr(self.session, "is_assistant_speaking", False)
        if is_speech and is_ai_speaking_or_greeting:
            if turn.barge_in_handled:
                return None

            self._speech_accumulated_ms += frame_duration_ms
            self._total_turn_speech_ms += frame_duration_ms
            self._silence_accumulated_ms = 0.0
            if frame_data:
                self.barge_in_pre_buffer.extend(frame_data)

            effective_barge_in_req = float(self.min_barge_in_duration_ms)

            if self._speech_accumulated_ms >= effective_barge_in_req:
                turn.barge_in_handled = True
                self.session.is_greeting_playing = False
                self.session.greeting_state = GreetingStateEnum.COMPLETED
                self.session.playback_estimated_end_time_ms = 0.0
                self.trigger_barge_in(reason="User barge-in speech detected")
                self._is_in_speech = True
                return "BARGE_IN"
            return None

        # 2. Normal speech detection (when AI is NOT speaking/processing/greeting: IDLE, LISTENING, LISTENING_AFTER_BARGE_IN)
        if is_speech and not is_ai_speaking_or_greeting:
            self._speech_accumulated_ms += frame_duration_ms
            self._total_turn_speech_ms += frame_duration_ms
            if self._silence_accumulated_ms > 0.0:
                if self._speech_accumulated_ms >= 80.0:  # Require at least 80ms of sustained speech to reset endpoint timer
                    logger.info(
                        f"[TURN] speech_resumed_after={self._silence_accumulated_ms:.0f}ms (endpoint timer reset) "
                        f"threshold={self.effective_silence_duration_ms:.0f}ms turn_id={turn.turn_id}"
                    )
                    self._silence_accumulated_ms = 0.0
            if not self._is_in_speech:
                if self._speech_accumulated_ms >= self.min_speech_duration_ms or self.min_speech_duration_ms == 0:
                    self._is_in_speech = True
                    self._total_turn_speech_ms = self._speech_accumulated_ms
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
                self._silence_accumulated_ms += frame_duration_ms
                if self._silence_accumulated_ms >= self.effective_silence_duration_ms:
                    logger.info(
                        f"[TURN] endpoint_reached={self._silence_accumulated_ms:.0f}ms "
                        f"threshold={self.effective_silence_duration_ms:.0f}ms total_speech={self._total_turn_speech_ms:.0f}ms (finalizing turn {turn.turn_id})"
                    )
                    self._is_in_speech = False
                    self._silence_accumulated_ms = 0.0
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
        
        # Track cancelled generation ID to invalidate late audio
        if hasattr(self.session, "cancelled_generation_ids"):
            self.session.cancelled_generation_ids.add(old_gen_id)
            if hasattr(self.session, "all_generation_ids"):
                self.session.cancelled_generation_ids.update(self.session.all_generation_ids)

        # 1. Transition state: SPEAKING -> BARGE_IN -> INTERRUPTING -> INTERRUPTED
        old_turn.state = TurnStateEnum.BARGE_IN
        old_turn.state = TurnStateEnum.INTERRUPTING
        old_turn.cancel(reason=reason)
        
        # 2. Flush all outgoing audio/TTS queues immediately
        self.queues.flush_output_queues()
        
        # 3. User takes floor
        self.session.user_has_floor = True
        self.session.is_greeting_playing = False
        self.session.greeting_state = GreetingStateEnum.COMPLETED
        self.session.playback_estimated_end_time_ms = 0.0

        # 4. Fire callback (emits response.cancelled and audio.flush WebSocket events)
        if self.on_barge_in_callback:
            try:
                self.on_barge_in_callback(old_turn_id, old_gen_id)
            except Exception as e:
                logger.warning(f"Error in barge-in callback: {e}")

        # 5. Rotate to fresh turn in LISTENING_AFTER_BARGE_IN state
        new_turn = self.session.start_new_turn(reason=f"Barge-in rotation: {reason}")
        new_turn.state = TurnStateEnum.LISTENING_AFTER_BARGE_IN
        new_turn.barge_in_handled = True

        # Reset counters so caller ongoing speech in this new turn is accumulated cleanly without re-triggering barge-in
        self._speech_accumulated_ms = 0.0
        self._silence_accumulated_ms = 0.0
        self._total_turn_speech_ms = 0.0
        self._is_in_speech = True

        logger.info(
            f"[BARGE-IN] User speech confirmed\n"
            f"[BARGE-IN] Cancelling generation={old_gen_id} turn={old_turn_id}\n"
            f"[BARGE-IN] Audio queue flushed: output queues cleared\n"
            f"[BARGE-IN] Playback stopped\n"
            f"[BARGE-IN] User floor = True\n"
            f"[BARGE-IN] New turn={new_turn.turn_id} gen={new_turn.generation_id}",
            extra={"session_id": self.session.session_id, "turn_id": new_turn.turn_id}
        )

    def reset(self):
        """Reset internal speech and silence counters."""
        self._speech_accumulated_ms = 0.0
        self._silence_accumulated_ms = 0.0
        self._total_turn_speech_ms = 0.0
        self._is_in_speech = False
        self.barge_in_pre_buffer.clear()
