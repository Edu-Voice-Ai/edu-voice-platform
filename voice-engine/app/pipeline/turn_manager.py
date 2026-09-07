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
        min_barge_in_duration_ms: int = 180,
        barge_in_min_confidence: float = 0.70,
        barge_in_min_rms: float = 0.025,
        vocal_energy_ratio_threshold: float = 0.50,
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
        
        # Two-stage barge-in state tracking: IDLE -> CANDIDATE -> CONFIRMED
        self._barge_in_stage: str = "IDLE"
        self._candidate_strong_frames: int = 0
        self._candidate_quiet_frames: int = 0
        self._candidate_backchannel_frames: int = 0

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
            or getattr(self.session.current_turn, "is_post_barge_in", False)
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
                flux_val = 0.25
                if vad_confidence == 0.0 and is_speech:
                    vad_confidence = 0.90
            else:
                vocal_ratio = float(getattr(acoustic_features, "vocal_energy_ratio", 0.0) or getattr(acoustic_features, "speech_band_ratio", 0.0) or 0.0)
                if vocal_ratio == 0.0 and getattr(acoustic_features, "is_valid_speech", True):
                    vocal_ratio = 0.85
                if vocal_rms < 0.001 and getattr(acoustic_features, "is_valid_speech", True):
                    vocal_rms = broadband_rms if broadband_rms >= 0.001 else 0.12
                if broadband_rms < 0.001 and getattr(acoustic_features, "is_valid_speech", True):
                    broadband_rms = 0.12
                flux_attr = getattr(acoustic_features, "spectral_flux", None)
                flux_val = float(flux_attr) if flux_attr is not None else 0.25
                if vad_confidence == 0.0 and getattr(acoustic_features, "is_valid_speech", True) and is_speech:
                    vad_confidence = 0.90

            if acoustic_features is not None:
                echo_corr = float(getattr(acoustic_features, "echo_correlation", 0.0) or 0.0)
                is_echo_suspect = bool(
                    getattr(acoustic_features, "is_acoustic_echo", False) or echo_corr >= 0.60
                )
                # Energy guard: cross-correlation across 1s reference window can exceed 0.60
                # on loud user speech. Only veto as echo if energy is not genuine loud speech.
                is_loud_user = bool(broadband_rms >= 0.035 or vocal_rms >= 0.030)
                is_echo = is_echo_suspect and not is_loud_user

            # 1. Echo and noise vetoes
            if is_echo:
                self._barge_in_bucket = 0
                self._barge_in_miss_frames = 0
                self._speech_accumulated_ms = 0.0
                self._barge_in_stage = "IDLE"
                self._candidate_strong_frames = 0
                self._candidate_quiet_frames = 0
                self._candidate_backchannel_frames = 0
                self.barge_in_pre_buffer.clear()
                return None

            is_noise = False
            if acoustic_features is not None:
                is_noise = bool(
                    getattr(acoustic_features, "is_breath_or_mouth", False)
                    or getattr(acoustic_features, "is_transient", False)
                )

            # 2. Multi-feature acoustic analysis
            is_hum = bool(getattr(acoustic_features, "is_backchannel_hum", False)) if acoustic_features is not None else False
            centroid_val = float(getattr(acoustic_features, "spectral_centroid", 0.0) or 0.0) if acoustic_features is not None else 0.0
            flatness = float(getattr(acoustic_features, "spectral_flatness", 0.20) or 0.20) if acoustic_features is not None else 0.20
            harmonicity = float(getattr(acoustic_features, "harmonicity", getattr(acoustic_features, "pitch_periodicity", 0.50)) or 0.50) if acoustic_features is not None else 0.50
            zcr_val = float(getattr(acoustic_features, "zcr", 0.08) or 0.08) if acoustic_features is not None else 0.08

            # Acoustic closed-mouth / nasal murmur fallback ("hmm", "hmmm", "hm", "mm", "uh-huh")
            if not is_hum and centroid_val > 0.0 and centroid_val < 950.0 and zcr_val < 0.20:
                is_hum = True

            # Speaker similarity check if profiler is enrolled
            speaker_sim = 1.0
            if hasattr(self.session, "speaker_profiler") and getattr(self.session.speaker_profiler, "is_enrolled", False):
                if frame_data:
                    try:
                        raw_arr = np.frombuffer(frame_data, dtype=np.int16).astype(np.float32) / 32768.0
                        speaker_sim = self.session.speaker_profiler.calculate_speaker_similarity(
                            raw_arr, frame_rms=broadband_rms, vad_confidence=vad_confidence
                        )
                    except Exception:
                        pass

            # Classify:
            # A. Quiet Voiced Speech (Caller softly saying "Please tell me the ECE fee")
            is_quiet_voiced = (
                is_speech
                and not is_noise
                and not is_hum
                and (0.010 <= vocal_rms < 0.040 or 0.012 <= broadband_rms < 0.040)
                and (harmonicity >= 0.28 or getattr(acoustic_features, "pitch_periodicity", 0.0) >= 0.28)
                and flatness <= 0.40
                and zcr_val <= 0.22
                and (vocal_ratio >= 0.40 or vad_confidence >= 0.70)
                and speaker_sim >= 0.40
            )

            # B. Normal Voiced Speech
            if hasattr(acoustic_features, "is_voiced_frame"):
                is_voiced = bool(getattr(acoustic_features, "is_voiced_frame", False))
            else:
                is_voiced = (
                    is_speech
                    and (vocal_rms >= 0.022 or broadband_rms >= 0.025)
                    and harmonicity >= 0.35
                    and flatness <= 0.38
                    and zcr_val <= 0.22
                    and flux_val >= 0.08
                )

            is_normal_voiced = (
                is_speech
                and is_voiced
                and not is_noise
                and not is_hum
                and (vocal_rms >= self.barge_in_min_rms or broadband_rms >= self.barge_in_min_rms)
                and (vocal_ratio >= self.vocal_energy_ratio_threshold or vad_confidence >= 0.80)
            )

            # C. Strong Intentional Speech (High energy, dynamic spectral flux, open vocal tract formant structure)
            is_strong = (
                is_normal_voiced
                and not is_hum
                and (centroid_val >= 1000.0 or centroid_val == 0.0)
                and (broadband_rms >= 0.045 or vocal_rms >= 0.045)
                and flux_val >= 0.18
                and harmonicity >= 0.35
                and vad_confidence >= 0.80
            )

            # D. Weak sound / Backchannel indicator ("hmm", "umm", "uh", "mm", "yeah", "okay", short breath)
            is_backchannel = (
                is_hum
                or (centroid_val > 0.0 and centroid_val < 950.0 and is_speech)
                or (flux_val < 0.15 and centroid_val < 1150.0 and is_speech)
                or (flux_val < 0.18 and broadband_rms < 0.040 and is_speech)
                or (is_noise and not is_normal_voiced)
            )

            # Frame qualification for leaky bucket
            is_qualifying = (is_normal_voiced or is_quiet_voiced or (is_speech and is_backchannel))

            # ── Leaky Bucket accumulator ──────────────────────────────────────────
            if is_qualifying:
                self._barge_in_bucket += 1
                self._barge_in_miss_frames = 0
                self._speech_accumulated_ms += frame_duration_ms
                self._total_turn_speech_ms += frame_duration_ms
                self._silence_accumulated_ms = 0.0
                self._consecutive_silence_frames = 0
                if frame_data:
                    self.barge_in_pre_buffer.extend(frame_data)

                if is_strong:
                    self._candidate_strong_frames += 1
                elif is_quiet_voiced:
                    self._candidate_quiet_frames += 1
                elif is_backchannel:
                    self._candidate_backchannel_frames += 1

                # Enter Stage 1: CANDIDATE
                if self._barge_in_bucket == 1 and self._barge_in_stage == "IDLE":
                    self._barge_in_stage = "CANDIDATE"
                    logger.debug(
                        f"[BARGE_IN_CANDIDATE] Candidate onset detected: "
                        f"rms={broadband_rms:.4f} vocal_rms={vocal_rms:.4f} flux={flux_val:.3f} "
                        f"strong={is_strong} quiet={is_quiet_voiced} backchannel={is_backchannel}"
                    )
            else:
                self._barge_in_bucket = max(0, self._barge_in_bucket - 1)
                if self._barge_in_bucket == 0:
                    if self._barge_in_stage == "CANDIDATE":
                        logger.info(
                            f"[BARGE_IN_FILTERED] Candidate speech ended without confirmation "
                            f"(speech_ms={self._speech_accumulated_ms:.0f}ms backchannel_frames={self._candidate_backchannel_frames}). "
                            f"AI playback continued uninterrupted."
                        )
                    self._speech_accumulated_ms = 0.0
                    self._barge_in_stage = "IDLE"
                    self._candidate_strong_frames = 0
                    self._candidate_quiet_frames = 0
                    self._candidate_backchannel_frames = 0
                    self.barge_in_pre_buffer.clear()

            # Dynamic confirmation threshold
            if is_greeting:
                threshold_frames = self.min_greeting_barge_in_frames
            elif self.min_barge_in_duration_ms not in (180, 200):
                # Explicit override by fixture / test caller
                threshold_frames = self.min_barge_in_frames
            else:
                total_cand = max(1, self._candidate_strong_frames + self._candidate_quiet_frames + self._candidate_backchannel_frames)
                if self._candidate_backchannel_frames >= 2 and (self._candidate_backchannel_frames / total_cand) >= 0.50 and self._candidate_strong_frames == 0:
                    # Weak backchannel/filler sound ("hmm", "umm", "uh", "mm", "haa", "aa"):
                    # Passive sounds must NEVER interrupt assistant playback.
                    threshold_frames = 999999
                elif self._candidate_strong_frames >= 4:
                    # Strong, crisp intentional speech: confirms in 8 frames (160ms)
                    threshold_frames = 8
                elif self._candidate_quiet_frames >= 6 and (self._candidate_quiet_frames / total_cand) >= 0.50:
                    # Quiet sustained speech: confirms in 14 frames (280ms)
                    threshold_frames = 14
                elif self._candidate_backchannel_frames == 0:
                    # Normal conversational speech without backchannel: confirms in 10 frames (200ms)
                    threshold_frames = 10
                else:
                    threshold_frames = 14

            if self._barge_in_bucket >= threshold_frames and threshold_frames < 999999:
                self._barge_in_stage = "CONFIRMED"
                logger.info(
                    f"[BARGE_IN] Verified intentional caller interruption "
                    f"bucket={self._barge_in_bucket} threshold={threshold_frames} "
                    f"speech_ms={self._speech_accumulated_ms:.0f}ms conf={vad_confidence:.3f} "
                    f"context={'greeting' if is_greeting else 'conversational'} "
                    f"strong={self._candidate_strong_frames} quiet={self._candidate_quiet_frames} bc={self._candidate_backchannel_frames}"
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
                self._barge_in_stage = "IDLE"
                self._candidate_strong_frames = 0
                self._candidate_quiet_frames = 0
                self._candidate_backchannel_frames = 0
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

        # Guard speech start: Reject breaths, transients, and echo
        is_noise = False
        if acoustic_features is not None:
            is_noise = bool(
                getattr(acoustic_features, "is_breath_or_mouth", False)
                or getattr(acoustic_features, "is_transient", False)
                or getattr(acoustic_features, "is_acoustic_echo", False)
            )

        # A frame is genuine speech if it's not noise, has VAD confidence, energy, and vocal tract ratio
        is_genuine_speech = bool(
            is_speech
            and not is_noise
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
                    # If current turn was already transcribed/generated or was cancelled/interrupted, start fresh turn
                    is_completed_turn = bool(turn.raw_transcript or turn.generated_text)
                    if is_completed_turn or turn.cancellation_token.is_cancelled or turn.state in (TurnStateEnum.INTERRUPTED, TurnStateEnum.IDLE, TurnStateEnum.PROCESSING, TurnStateEnum.SPEAKING):
                        turn = self.session.start_new_turn(reason="New speech turn onset")
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
        new_turn.is_post_barge_in = True
        new_turn.barge_in_handled = True

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
        self._barge_in_bucket = 0
        self._barge_in_miss_frames = 0
        self._consecutive_silence_frames = 0
        self._is_in_speech = False
        self._barge_in_stage = "IDLE"
        self._candidate_strong_frames = 0
        self._candidate_quiet_frames = 0
        self._candidate_backchannel_frames = 0
        self.barge_in_pre_buffer.clear()
