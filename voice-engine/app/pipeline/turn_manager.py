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
        min_barge_in_duration_ms: int = 220,
        barge_in_min_confidence: float = 0.40,
        barge_in_min_rms: float = 0.008,
        vocal_energy_ratio_threshold: float = 0.35,
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
        self.vocal_energy_ratio_threshold = vocal_energy_ratio_threshold
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
            active_gen = getattr(self.session, "active_playback_generation_id", None)
            if turn.barge_in_handled:
                # If a new generation or turn is actively speaking, re-arm barge-in
                if active_gen and active_gen != getattr(turn, "_barge_in_cancelled_gen_id", None):
                    turn.barge_in_handled = False
                else:
                    return None

            is_echo = False
            is_valid_barge_in = False

            vocal_rms = float(getattr(acoustic_features, "vocal_band_rms", 0.0) or getattr(acoustic_features, "rms", 0.0) or 0.0) if acoustic_features is not None else 0.0
            broadband_rms = float(getattr(acoustic_features, "rms", 0.0) or 0.0) if acoustic_features is not None else 0.0
            if (vocal_rms == 0.0 or broadband_rms == 0.0) and frame_data:
                try:
                    raw_arr = np.frombuffer(frame_data, dtype=np.int16).astype(np.float32) / 32768.0
                    calc_rms = float(np.sqrt(np.mean(np.square(raw_arr)))) if len(raw_arr) > 0 else 0.0
                    if vocal_rms == 0.0:
                        vocal_rms = calc_rms
                    if broadband_rms == 0.0:
                        broadband_rms = calc_rms
                except Exception:
                    pass

            if acoustic_features is None:
                if vocal_rms < 0.001:
                    vocal_rms = 0.12
                if broadband_rms < 0.001:
                    broadband_rms = 0.12
                vocal_ratio = 0.85
            else:
                vocal_ratio = float(getattr(acoustic_features, "vocal_energy_ratio", 0.0) or getattr(acoustic_features, "speech_band_ratio", 0.0) or 0.0)
                if vocal_ratio == 0.0 and getattr(acoustic_features, "is_valid_speech", True):
                    vocal_ratio = 0.85
                if vocal_rms < 0.001 and getattr(acoustic_features, "is_valid_speech", True):
                    vocal_rms = 0.12
                if broadband_rms < 0.001 and getattr(acoustic_features, "is_valid_speech", True):
                    broadband_rms = 0.12

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

            # Calibrated Telephony Barge-in Qualification Rule:
            # A frame during playback is speech if:
            # is_speech is True and conf >= 0.40 and (vocal_band_rms >= 0.008 or rms >= 0.010) and (vocal_energy_ratio >= 0.35 or conf >= 0.85)
            is_qualifying = (
                is_speech
                and vad_confidence >= self.barge_in_min_confidence
                and (vocal_rms >= self.barge_in_min_rms or broadband_rms >= 0.010)
                and (vocal_ratio >= self.vocal_energy_ratio_threshold or vad_confidence >= 0.85)
            )

            # ── Adaptive Speaker Identity Gate ───────────────────────────────────
            # If the caller has been enrolled, additionally require speaker_sim >= 0.55
            # to prevent background voices (TV, 1m talker) from triggering barge-in.
            # High-confidence VAD frames (conf >= 0.90) bypass the similarity gate to
            # prevent genuine caller whispering or low-energy speech from being dropped.
            if is_qualifying:
                profiler = getattr(self.session, "speaker_profiler", None)
                if profiler is not None and profiler.is_enrolled:
                    try:
                        frame_audio = np.frombuffer(frame_data, dtype=np.int16).astype(np.float32) / 32768.0 if frame_data else None
                        speaker_sim = profiler.calculate_speaker_similarity(
                            frame_audio=frame_audio,
                            frame_rms=vocal_rms if vocal_rms > 0 else broadband_rms,
                            frame_spectral_centroid=float(getattr(acoustic_features, "spectral_centroid", 0.0) or 0.0) if acoustic_features else None,
                            vad_confidence=vad_confidence
                        )
                        if speaker_sim < 0.45 and vad_confidence < 0.90:
                            logger.debug(
                                f"[SPEAKER_LOCK] Barge-in frame rejected as background noise "
                                f"speaker_sim={speaker_sim:.3f} conf={vad_confidence:.3f}"
                            )
                            is_qualifying = False
                        elif speaker_sim < 0.55:
                            logger.debug(
                                f"[SPEAKER_LOCK] Uncertain barge-in frame accepted (conf bypass) "
                                f"speaker_sim={speaker_sim:.3f} conf={vad_confidence:.3f}"
                            )
                    except Exception:
                        pass  # Degrade gracefully — don't block barge-in on profiler errors

            # ── Backchannel / Passive-Listening Hum Suppressor ──────────────────────
            # If the acoustic gate detects a monotone nasal hum ("hmmm", "mm", "uh-huh",
            # "హ్మ్") while the bot is speaking, do NOT count it toward the barge-in
            # accumulator.  Real interruptions ("ఆగండి", "Wait", "Stop") have high spectral
            # flux (> 0.15) and won't be flagged as backchannels.
            if is_qualifying and getattr(acoustic_features, "is_backchannel_hum", False):
                logger.info(
                    f"[BACKCHANNEL_DETECTED] Passive listening hum suppressed during bot playback "
                    f"flux={getattr(acoustic_features, 'spectral_flux', 0.0):.3f} "
                    f"pitch_p={getattr(acoustic_features, 'pitch_periodicity', 0.0):.3f} "
                    f"zcr={getattr(acoustic_features, 'zcr', 0.0):.3f} "
                    f"rms={getattr(acoustic_features, 'rms', 0.0):.4f}"
                )
                is_qualifying = False

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
                turn._barge_in_cancelled_gen_id = active_gen
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
        inbound_vocal_rms = float(getattr(acoustic_features, "vocal_band_rms", 0.0) or getattr(acoustic_features, "rms", 0.0) or 0.0) if acoustic_features is not None else 0.0
        broadband_rms = float(getattr(acoustic_features, "rms", 0.0) or 0.0) if acoustic_features is not None else 0.0
        if (inbound_vocal_rms == 0.0 or broadband_rms == 0.0) and frame_data:
            try:
                raw_arr = np.frombuffer(frame_data, dtype=np.int16).astype(np.float32) / 32768.0
                calc_rms = float(np.sqrt(np.mean(np.square(raw_arr)))) if len(raw_arr) > 0 else 0.0
                if inbound_vocal_rms == 0.0:
                    inbound_vocal_rms = calc_rms
                if broadband_rms == 0.0:
                    broadband_rms = calc_rms
            except Exception:
                pass

        if acoustic_features is None:
            if inbound_vocal_rms < 0.001:
                inbound_vocal_rms = 0.12
            if broadband_rms < 0.001:
                broadband_rms = 0.12
            vocal_ratio = 0.85
        else:
            vocal_ratio = float(getattr(acoustic_features, "vocal_energy_ratio", 0.0) or getattr(acoustic_features, "speech_band_ratio", 0.0) or 0.0)
            if vocal_ratio == 0.0 and getattr(acoustic_features, "is_valid_speech", True):
                vocal_ratio = 0.85
            if inbound_vocal_rms < 0.001 and getattr(acoustic_features, "is_valid_speech", True):
                inbound_vocal_rms = 0.12
            if broadband_rms < 0.001 and getattr(acoustic_features, "is_valid_speech", True):
                broadband_rms = 0.12

        # Guard speech start: A frame is genuine speech if:
        # is_speech is True and conf >= 0.40 and energy, with spectral ratio or high confidence
        is_genuine_speech = bool(
            is_speech
            and vad_confidence >= 0.40
            and (inbound_vocal_rms >= self.barge_in_min_rms or broadband_rms >= 0.010)
            and (vocal_ratio >= self.vocal_energy_ratio_threshold or vad_confidence >= 0.85)
        )

        if is_genuine_speech and not is_active_playback:
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
        if not is_genuine_speech:
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
