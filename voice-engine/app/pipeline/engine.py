"""Core Speech-to-Speech (S2S) Pipeline Engine coordinating VAD, STT, LLM, and TTS workers."""
import asyncio
import collections
import time
from typing import Optional, List
import numpy as np
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.audio.buffering import AudioChunker
from app.session.state import SessionState, TurnStateEnum, GreetingStateEnum, HandoffStateEnum
from app.session.events import SessionEvent, EventType
from app.conversation.handoff_detector import MultilingualHandoffDetector
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.turn_manager import TurnManager
from app.pipeline.cancellation import CancellationToken
from app.pipeline.structured_input import (
    StructuredInputMode,
    DigitNormalizer,
    StructuredInputDetector,
    NumericTurnAccumulator
)
from app.vad.base import VADProvider
from app.stt.base import STTProvider
from app.llm.base import LLMProvider
from app.tts.base import TTSProvider
from app.conversation.manager import ConversationManager
from app.conversation.language import LanguagePreferenceParser
from app.conversation.prompts import INAUDIBLE_CLARIFICATION_PHRASES, INAUDIBLE_ESCALATION_PHRASES
from app.conversation.router import FastQueryRouter, QueryComplexity
from app.metrics.latency import TurnMetrics, LatencyTracker
from app.metrics.events import MetricsCollector
from app.core.logging import get_logger

logger = get_logger("pipeline.engine")

# Module-level greeting audio cache for 0ms TTFB on subsequent calls
_GREETING_AUDIO_CACHE: dict[str, bytes] = {}

# Pure hesitation / filler tokens that should NEVER trigger LLM or TTS when uttered alone
PURE_FILLER_WORDS = {
    # English
    "um", "umm", "uh", "uhh", "hmm", "hm", "hmmm", "hmmmm", "mm", "mmm", "mhm", "m-hm",
    "ah", "ahh", "er", "uh-huh", "uh huh", "uhhuh",
    # Telugu romanized & script
    "ante", "antey", "aa", "aah", "oo",
    "ఉమ్", "ఉమ్మ్", "అంటే", "ఆ", "ఊ", "మ్మ్", "హ్మ్", "హ్మ", "మ్", "మ", "ఉ", "ఉఁ",
    # Hindi
    "हम्म", "हम",
}

# Confirmation / affirmative tokens that represent valid user answers ONLY if preceded by an assistant question
CONFIRMATION_WORDS = {
    # Telugu script & romanized
    "హా", "అవును", "అవునండి", "సరే", "సరేనండి", "చెప్పండి",
    "ha", "haa", "haan", "avunu", "avunandi", "sare", "sarenandi", "cheppandi",
    # English
    "yes", "yeah", "yep", "ok", "okay", "sure", "alright", "right", "correct",
    # Hindi
    "हाँ", "हां", "जी", "जी हाँ", "जी हां", "हा",
}


def _did_assistant_ask_confirmation_or_question(session: SessionState) -> bool:
    """
    Check if the immediate previous assistant message asked a confirmation or yes/no question.
    """
    if not session:
        return False

    last_text = ""
    if session.messages:
        for m in reversed(session.messages):
            if m.get("role") == "assistant" and m.get("content"):
                last_text = m.get("content", "").strip()
                break

    if not last_text and getattr(session, "last_response_text", None):
        last_text = session.last_response_text.strip()

    if not last_text:
        return False

    if "?" in last_text:
        return True

    # Telugu interrogative / confirmation markers
    telugu_question_markers = (
        "కావాలా", "సరేనా", "చెప్పమంటారా", "మాట్లాడించమంటారా", "మాట్లాడాలనుకుంటున్నారా",
        "తెలుసుకోవాలనుకుంటున్నారా", "వినిపిస్తోందా", "ఉన్నారా", "చేయమంటారా", "కదా",
        "సరిపోతుందా", "చెప్పగలరా", "అవునా", "కదూ"
    )
    for marker in telugu_question_markers:
        if marker in last_text:
            return True

    # English / Hinglish question indicators
    lower = last_text.lower()
    english_markers = (
        "would you like", "do you want", "shall i", "should i", "can i", "could you",
        "is that correct", "right?", "okay?", "correct?", "are you looking", "prefer"
    )
    for marker in english_markers:
        if marker in lower:
            return True

    return False


def is_filler_or_unprompted_backchannel(transcript_text: str, session: SessionState) -> tuple[bool, str]:
    """
    Evaluates whether a finalized transcript consists only of filler words or unprompted confirmations.
    Returns (should_ignore, reason).

    Rules:
    1. If transcript is empty or composed solely of PURE_FILLER_WORDS -> ignore (never trigger LLM/TTS).
    2. If transcript contains only CONFIRMATION_WORDS (or a mix of CONFIRMATION_WORDS and PURE_FILLER_WORDS):
       - If assistant just asked a question -> do NOT ignore (treat as valid user confirmation).
       - If assistant did NOT ask a question -> ignore as passive backchannel/hesitation.
    3. If transcript contains meaningful speech words -> do NOT ignore.
    """
    if not transcript_text:
        return False, "empty"

    tokens = [w.lower().strip(".,?!-_\"':;") for w in transcript_text.split() if w.strip(".,?!-_\"':;")]
    if not tokens:
        return False, "no_valid_tokens"

    # Check if all tokens are pure fillers
    if all(t in PURE_FILLER_WORDS for t in tokens):
        return True, "pure_filler"

    all_filler_or_conf = PURE_FILLER_WORDS | CONFIRMATION_WORDS
    if all(t in all_filler_or_conf for t in tokens):
        # Utterance is made of confirmations (and optional fillers)
        if _did_assistant_ask_confirmation_or_question(session):
            return False, "valid_confirmation"
        else:
            return True, "unprompted_confirmation_or_backchannel"

    return False, "meaningful_speech"



class SpeechToSpeechEngine:
    """
    Asynchronous Speech-to-Speech Engine.
    Coordinates isolated worker loops for VAD, STT, Conversation/LLM, and TTS.
    """

    _cached_fast_audio: dict[str, bytes] = {}
    _cache_warmed: bool = False

    @classmethod
    async def warmup_fast_query_cache(cls, tts_provider):
        """Pre-cache standard FastQueryRouter Indic & English responses in-memory as raw PCM16 bytes for 0ms TTS latency."""
        from app.conversation.router import FastQueryRouter
        logger.info("[FAST_CACHE] Starting in-memory TTS pre-caching for FastQueryRouter responses...")
        count = 0
        for lang, text in FastQueryRouter.get_all_standard_responses():
            cache_key = f"{lang}:{text.strip()}"
            if cache_key in cls._cached_fast_audio:
                continue
            try:
                pcm = await tts_provider.synthesize_text(text, language_code=lang, speaker="pooja")
                if pcm and len(pcm) > 0:
                    cls._cached_fast_audio[cache_key] = pcm
                    count += 1
            except Exception as e:
                logger.warning(f"[FAST_CACHE] Failed to pre-cache ({lang}) '{text[:30]}...': {e}")
        logger.info(f"[FAST_CACHE] Pre-cached {count} FastQueryRouter audio responses in memory (total cached: {len(cls._cached_fast_audio)})")

    def __init__(
        self,
        session: SessionState,
        vad_provider: VADProvider,
        stt_provider: STTProvider,
        llm_provider: LLMProvider,
        tts_provider: TTSProvider,
        conversation_manager: ConversationManager,
        queues: Optional[PipelineQueueBundle] = None,
        latency_tracker: Optional[LatencyTracker] = None,
        min_silence_duration_ms: int = 350,
        structured_input_silence_ms: int = 1200,
        min_speech_duration_ms: int = 40,
        min_barge_in_duration_ms: int = 180,
        barge_in_min_confidence: float = 0.70,
        barge_in_min_rms: float = 0.025,
        vocal_energy_ratio_threshold: float = 0.50,
    ):
        self.session = session
        self.vad_provider = vad_provider
        self.stt_provider = stt_provider
        self.llm_provider = llm_provider
        self.tts_provider = tts_provider
        self.conversation_manager = conversation_manager
        self.queues = queues or PipelineQueueBundle()
        self.latency_tracker = latency_tracker or MetricsCollector.get_tracker()

        self.turn_manager = TurnManager(
            session=self.session,
            queues=self.queues,
            min_silence_duration_ms=min_silence_duration_ms,
            structured_input_silence_ms=structured_input_silence_ms,
            min_speech_duration_ms=min_speech_duration_ms,
            min_barge_in_duration_ms=min_barge_in_duration_ms,
            barge_in_min_confidence=barge_in_min_confidence,
            barge_in_min_rms=barge_in_min_rms,
            vocal_energy_ratio_threshold=vocal_energy_ratio_threshold,
            on_barge_in_callback=self._handle_barge_in_event
        )

        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._current_metrics: Optional[TurnMetrics] = None
        self._outbound_ref_buffer: collections.deque = collections.deque(maxlen=100)
        self._stt_session = self.stt_provider.create_streaming_session() if hasattr(self.stt_provider, "create_streaming_session") else None
        self._active_llm_task: Optional[asyncio.Task] = None

    def _cancel_active_llm_task(self, reason: str = "Preempted"):
        """Immediately cancel any running background LLM task to eliminate head-of-line blocking."""
        if hasattr(self, "_active_llm_task") and self._active_llm_task and not self._active_llm_task.done():
            logger.info(f"[LLM_CANCEL] Preempting active LLM generation task: {reason}")
            self._active_llm_task.cancel()
            self._active_llm_task = None

    def _handle_barge_in_event(self, old_turn_id: str, old_gen_id: str):
        """Emit cancellation event when barge-in occurs."""
        # Immediately kill running background LLM generation
        self._cancel_active_llm_task("Barge-in interruption")

        barge_in_event = SessionEvent(
            event=EventType.RESPONSE_CANCELLED,
            session_id=self.session.session_id,
            turn_id=old_turn_id,
            generation_id=old_gen_id,
            data={"reason": "User interrupted AI response", "interrupted_at_ms": time.time() * 1000}
        )
        self._emit_event(barge_in_event)
        
        # Emit immediate audio flush command
        flush_event = SessionEvent(
            event=EventType.AUDIO_FLUSH,
            session_id=self.session.session_id,
            turn_id=old_turn_id,
            generation_id=old_gen_id
        )
        self._emit_event(flush_event)

        # Emit explicit audio playback stop command for client-side physical speaker
        stop_event = SessionEvent(
            event=EventType.AUDIO_PLAYBACK_STOP,
            session_id=self.session.session_id,
            turn_id=old_turn_id,
            generation_id=old_gen_id,
            data={"reason": "Hard barge-in stop requested", "interrupted_at_ms": time.time() * 1000}
        )
        self._emit_event(stop_event)

        if self._current_metrics and self._current_metrics.turn_id == old_turn_id:
            self._current_metrics.barge_in_trigger_time_ms = time.time() * 1000
            self._current_metrics.barge_in_flushed_time_ms = time.time() * 1000

    def _emit_event(self, event: SessionEvent):
        """Push event to output queue non-blockingly."""
        try:
            self.queues.event_out_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Event output queue is full, dropping event")

    async def start(self):
        """Start asynchronous worker loops."""
        if self._running:
            return
        self._running = True
        logger.info(f"Starting S2S Engine for session {self.session.session_id}", extra={"session_id": self.session.session_id})

        # Warm up FastRouter in-memory TTS cache in the background only if explicitly enabled
        from app.core.config import get_settings
        _cfg = get_settings()
        if _cfg.enable_startup_tts_precache and not SpeechToSpeechEngine._cache_warmed:
            SpeechToSpeechEngine._cache_warmed = True
            asyncio.create_task(SpeechToSpeechEngine.warmup_fast_query_cache(self.tts_provider))

        self._tasks = [
            asyncio.create_task(self._vad_worker(), name="vad_worker"),
            asyncio.create_task(self._llm_worker(), name="llm_worker"),
            asyncio.create_task(self._tts_worker(), name="tts_worker"),
            asyncio.create_task(self._send_initial_language_prompt(), name="greeting_worker"),
            asyncio.create_task(self._prewarm_providers(), name="prewarm_worker"),
        ]

    async def _prewarm_providers(self):
        """Asynchronously pre-warm persistent HTTP/2 connection pools in the background without blocking greeting."""
        try:
            tasks = []
            if hasattr(self.stt_provider, "prewarm"):
                tasks.append(self.stt_provider.prewarm())
            if hasattr(self.tts_provider, "prewarm"):
                tasks.append(self.tts_provider.prewarm())
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Pre-cache static initial greeting on startup for 0ms dispatch
            greeting_text = (
                self.session.get_greeting_text()
                if hasattr(self.session, "get_greeting_text")
                else f"Welcome to {self.session.institution_name}. Which language do you prefer? English, Hindi, or Telugu?"
            )
            global _GREETING_AUDIO_CACHE
            greeting_speaker = getattr(self.tts_provider, "default_speaker", "pooja")
            greeting_cache_key = f"{greeting_text}:{greeting_speaker}"
            if greeting_cache_key not in _GREETING_AUDIO_CACHE:
                pcm_bytes = await self.tts_provider.synthesize_text(greeting_text, language_code="en-IN", speaker=greeting_speaker)
                if pcm_bytes and len(pcm_bytes) >= 32000:
                    _GREETING_AUDIO_CACHE[greeting_cache_key] = pcm_bytes
                    logger.info(f"[GREETING] Pre-cached static greeting audio for 0ms initial dispatch (speaker={greeting_speaker})")
        except Exception as e:
            logger.debug(f"Provider prewarm notice: {e}")

    async def stop(self):
        """Stop engine and cancel background worker tasks."""
        self._running = False
        self.session.is_active = False
        self.session.is_disconnected = True
        self.session.close()
        self._cancel_active_llm_task("Engine stopped")
        self.queues.flush_output_queues()

        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._stt_session:
            try:
                await self._stt_session.close()
            except Exception as e:
                logger.debug(f"Error closing STT session: {e}")

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info(
            f"[CALL_END] session_id={self.session.session_id} TTS_CANCELLED=True LLM_CANCELLED=True QUEUE_PURGED=True"
        )
        if hasattr(self.session, "log_cost_summary"):
            logger.info(self.session.log_cost_summary(), extra={"session_id": self.session.session_id})
        logger.info(f"Stopped S2S Engine for session {self.session.session_id}", extra={"session_id": self.session.session_id})

    async def push_audio_frame(self, frame: AudioFrame):
        """Entry point for incoming client audio frames."""
        if self._running and self.session.is_active:
            await self.queues.audio_in_queue.put(frame)

    async def _send_initial_language_prompt(self):
        """Synthesize and stream the initial language selection greeting exactly once per call."""
        if getattr(self.session, "greeting_state", GreetingStateEnum.NOT_STARTED) != GreetingStateEnum.NOT_STARTED:
            logger.info(f"[GREETING] Skipping duplicate initial greeting; state is already {getattr(self.session, 'greeting_state', 'UNKNOWN')}", extra={"session_id": self.session.session_id})
            return

        self.session.greeting_state = GreetingStateEnum.PLAYING
        self.session.conversation_state = "GREETING"
        gen_start_ms = time.time() * 1000

        greeting_text = (
            self.session.get_greeting_text()
            if hasattr(self.session, "get_greeting_text")
            else f"Welcome to {self.session.institution_name}. Which language do you prefer? English, Hindi, or Telugu?"
        )
        logger.info(
            f"[INTERACTION_TRACE] session_id={self.session.session_id} event=GREETING_START text=\"{greeting_text}\"",
            extra={"session_id": self.session.session_id}
        )

        turn = self.session.current_turn
        token = turn.cancellation_token

        try:
            self._emit_event(SessionEvent(
                event=EventType.RESPONSE_START,
                session_id=self.session.session_id,
                turn_id=turn.turn_id,
                generation_id=turn.generation_id
            ))

            self._emit_event(SessionEvent(
                event=EventType.RESPONSE_TEXT_DELTA,
                session_id=self.session.session_id,
                turn_id=turn.turn_id,
                generation_id=turn.generation_id,
                data={"delta": greeting_text}
            ))

            # Fetch from cache or synthesize via TTS provider in English
            global _GREETING_AUDIO_CACHE
            greeting_speaker = getattr(self.tts_provider, "default_speaker", "pooja")
            greeting_cache_key = f"{greeting_text}:{greeting_speaker}"
            if greeting_cache_key in _GREETING_AUDIO_CACHE and len(_GREETING_AUDIO_CACHE[greeting_cache_key]) >= 32000:
                pcm_bytes = _GREETING_AUDIO_CACHE[greeting_cache_key]
            else:
                try:
                    pcm_bytes = await self.tts_provider.synthesize_text(greeting_text, language_code="en-IN", speaker=greeting_speaker)
                except Exception as te:
                    logger.error(f"[GREETING] TTS synthesis failed: {te}")
                    pcm_bytes = None
                if not pcm_bytes or len(pcm_bytes) < 32000:
                    # Provide rich 4.5-second greeting audio fallback (144000 bytes @ 16kHz mono)
                    pcm_bytes = AudioFrame.silence(duration_ms=4500, sample_rate=16000).data
                else:
                    _GREETING_AUDIO_CACHE[greeting_cache_key] = pcm_bytes

            # Keep flags true until the writer consumes RESPONSE_END or barge-in clears them.
            self.session.is_greeting_playing = True
            self.session.is_bot_speaking = True
            self.session.active_playback_generation_id = turn.generation_id
            self.session.active_playback_turn_id = turn.turn_id
            if hasattr(self.session, "arm_playback_interrupt"):
                self.session.arm_playback_interrupt()
            first_audio_ms = time.time() * 1000

            chunker = AudioChunker(sample_rate=16000, frame_duration_ms=20)
            for frame in chunker.feed(pcm_bytes):
                # Check for barge-in / interruption during greeting
                if token.is_cancelled or not self.session.is_greeting_playing or self.session.is_generation_cancelled(turn.generation_id):
                    logger.info(f"[GREETING] Interrupted during audio playback gen={turn.generation_id}", extra={"session_id": self.session.session_id})
                    break

                turn.tts_audio_chunks_count += 1
                self.session.extend_playback_deadline(frame.duration_ms)
                self._outbound_ref_buffer.append(frame.to_numpy_float32())
                try:
                    self.queues.audio_out_queue.put_nowait(frame)
                except asyncio.QueueFull:
                    pass

                b64_audio = AudioCodec.frame_to_base64(frame)
                self._emit_event(SessionEvent(
                    event=EventType.AUDIO_OUTPUT,
                    session_id=self.session.session_id,
                    turn_id=turn.turn_id,
                    generation_id=turn.generation_id,
                    data={"data": b64_audio, "seq": frame.seq, "sample_rate": frame.sample_rate}
                ))

            if not token.is_cancelled and self.session.is_greeting_playing and not self.session.is_generation_cancelled(turn.generation_id):
                final_frame = chunker.flush()
                if final_frame:
                    b64_audio = AudioCodec.frame_to_base64(final_frame)
                    self._emit_event(SessionEvent(
                        event=EventType.AUDIO_OUTPUT,
                        session_id=self.session.session_id,
                        turn_id=turn.turn_id,
                        generation_id=turn.generation_id,
                        data={"data": b64_audio, "seq": final_frame.seq, "sample_rate": final_frame.sample_rate}
                    ))

                self.session.append_message(role="assistant", content=greeting_text)
                total_duration_ms = (time.time() * 1000) - gen_start_ms
                self._emit_event(SessionEvent(
                    event=EventType.RESPONSE_END,
                    session_id=self.session.session_id,
                    turn_id=turn.turn_id,
                    generation_id=turn.generation_id,
                    data={"is_initial_greeting": True, "greeting_duration_ms": total_duration_ms, "ttfb_ms": first_audio_ms - gen_start_ms}
                ))

            # Synthesis is queued. Keep playback_estimated_end_time_ms so caller speech
            # during remaining physical playout still takes the barge-in path.
            self.session.is_greeting_playing = False
            self.session.is_bot_speaking = False
            self.session.active_playback_generation_id = None
            self.session.active_playback_turn_id = None
            self.session.greeting_state = GreetingStateEnum.COMPLETED
            self.session.conversation_state = "WAITING_FOR_LANGUAGE"
            self.session.user_has_floor = True
            if hasattr(self.vad_provider, "reset"):
                self.vad_provider.reset()
            self.turn_manager.reset()
            turn = self.session.start_new_turn(reason="Greeting finished, awaiting user language choice")
            turn.state = TurnStateEnum.LISTENING

            # Signal client that interaction and microphone capture can begin cleanly
            self._emit_event(SessionEvent(
                event="session.interaction_ready",
                session_id=self.session.session_id,
                turn_id=turn.turn_id,
                data={"state": "WAITING_FOR_LANGUAGE", "ready_for_user": True}
            ))
            logger.info(
                f"[INTERACTION_TRACE] session_id={self.session.session_id} event=GREETING_COMPLETE listening_open=True",
                extra={"session_id": self.session.session_id}
            )

        except Exception as e:
            self.session.is_greeting_playing = False
            self.session.greeting_state = GreetingStateEnum.COMPLETED
            self.session.conversation_state = "WAITING_FOR_LANGUAGE"
            self.session.user_has_floor = True
            if hasattr(self.vad_provider, "reset"):
                self.vad_provider.reset()
            self.turn_manager.reset()
            turn = self.session.start_new_turn(reason="Greeting exception recovery, awaiting user language choice")
            turn.state = TurnStateEnum.LISTENING
            logger.error(f"Failed to play initial greeting: {e}. Recovering to LISTENING state.", extra={"session_id": self.session.session_id})

    async def _vad_worker(self):
        """Reads audio frames from audio_in_queue, runs VAD, manages turn transitions."""
        current_speech_audio = bytearray()
        pre_speech_ring_buffer: collections.deque[bytes] = collections.deque(maxlen=8)
        
        frame_count = 0
        while self._running and self.session.is_active:
            try:
                frame = await self.queues.audio_in_queue.get()
            except asyncio.CancelledError:
                break

            frame_count += 1
            if getattr(self.session, "is_expired", False):
                logger.info(f"[SESSION_TIMEOUT] Session {self.session.session_id} exceeded max duration limit ({self.session.max_call_duration_seconds}s)")
                self.session.is_active = False
                break

            pre_speech_ring_buffer.append(frame.data)
            now_ms = time.time() * 1000
            playing = bool(
                getattr(self.session, "is_bot_speaking", False)
                or getattr(self.session, "is_greeting_playing", False)
                or getattr(self.session, "active_playback_generation_id", None)
                or now_ms < float(getattr(self.session, "playback_estimated_end_time_ms", 0.0) or 0.0)
            )
            outbound_ref = None
            if playing and self._outbound_ref_buffer:
                outbound_ref = np.concatenate(list(self._outbound_ref_buffer))
            elif not playing and self._outbound_ref_buffer:
                self._outbound_ref_buffer.clear()
            try:
                vad_res = await self.vad_provider.is_speech(frame, outbound_ref=outbound_ref, playback_active=playing)
            except TypeError:
                try:
                    vad_res = await self.vad_provider.is_speech(frame, outbound_ref=outbound_ref)
                except TypeError:
                    vad_res = await self.vad_provider.is_speech(frame)

            frame.is_speech = vad_res.is_speech

            rms = float(np.sqrt(np.mean(np.square(frame.to_numpy_float32())))) if len(frame.data) > 0 else 0.0
            acoustic = getattr(vad_res, "acoustic_features", None)
            vocal_rms = float(getattr(acoustic, "vocal_band_rms", rms) or 0.0)
            vocal_ratio = float(getattr(acoustic, "vocal_energy_ratio", 0.0) or 0.0)
            if vad_res.is_speech or vad_res.confidence >= 0.15 or rms >= 0.012 or frame_count % 50 == 0:
                stt_depth = getattr(self._stt_session, "queue_depth", 0) if self._stt_session else 0
                stt_healthy = getattr(self._stt_session, "is_stream_healthy", False) if self._stt_session else False
                logger.info(
                    f"[VAD_FRAME #{frame_count}] is_speech={vad_res.is_speech} conf={vad_res.confidence:.4f} rms={rms:.4f} "
                    f"vocal_rms={vocal_rms:.4f} vocal_ratio={vocal_ratio:.2f} "
                    f"state={self.turn_manager.current_state} user_floor={self.session.user_has_floor} "
                    f"in_q={self.queues.audio_in_queue.qsize()} stt_q={stt_depth} stt_ok={stt_healthy}"
                )

            transition = self.turn_manager.handle_speech_frame(
                vad_res.is_speech,
                frame_data=frame.data,
                frame_duration_ms=frame.duration_ms,
                vad_confidence=vad_res.confidence,
                acoustic_features=getattr(vad_res, "acoustic_features", None)
            )

            if transition == "BARGE_IN":
                turn = self.session.current_turn
                turn.is_post_barge_in = True
                turn.barge_in_handled = True
                current_speech_audio.clear()
                if self._stt_session:
                    await self._stt_session.reset(turn_id=turn.turn_id)

                # Prepend pre-roll silence frames from before the interruption onset
                barge_bytes = bytes(self.turn_manager.barge_in_pre_buffer)
                frame_sz = len(frame.data) if len(frame.data) > 0 else 320
                num_barge_frames = len(barge_bytes) // frame_sz if frame_sz > 0 else 0
                pre_roll_frames = list(pre_speech_ring_buffer)[:-num_barge_frames] if num_barge_frames < len(pre_speech_ring_buffer) else []
                for p in pre_roll_frames[-2:]:
                    current_speech_audio.extend(p)
                    if self._stt_session:
                        await self._stt_session.push_audio(p)

                # Append verified interruption speech audio frames
                current_speech_audio.extend(barge_bytes)
                if self._stt_session and barge_bytes:
                    await self._stt_session.push_audio(barge_bytes)
                self.turn_manager.barge_in_pre_buffer.clear()

                now_ms = time.time() * 1000
                self._current_metrics = TurnMetrics(
                    session_id=self.session.session_id,
                    turn_id=turn.turn_id,
                    generation_id=turn.generation_id,
                    speech_start_time_ms=now_ms
                )
                self._emit_event(SessionEvent(
                    event=EventType.SPEECH_START,
                    session_id=self.session.session_id,
                    turn_id=turn.turn_id,
                    generation_id=turn.generation_id
                ))

            elif transition == "SPEECH_STARTED":
                current_speech_audio.clear()
                now_ms = time.time() * 1000
                turn = self.session.current_turn
                is_completed_turn = bool(turn.raw_transcript or turn.generated_text)
                if is_completed_turn or turn.cancellation_token.is_cancelled or turn.state in (TurnStateEnum.INTERRUPTED, TurnStateEnum.IDLE, TurnStateEnum.PROCESSING, TurnStateEnum.SPEAKING):
                    turn = self.session.start_new_turn(reason="Speech started for new turn")
                turn.state = TurnStateEnum.LISTENING

                if self._stt_session:
                    await self._stt_session.reset(turn_id=turn.turn_id)
                for pre_b in pre_speech_ring_buffer:
                    current_speech_audio.extend(pre_b)
                    if self._stt_session:
                        await self._stt_session.push_audio(pre_b)
                current_speech_audio.extend(frame.data)
                if self._stt_session:
                    await self._stt_session.push_audio(frame.data)

                self._current_metrics = TurnMetrics(
                    session_id=self.session.session_id,
                    turn_id=turn.turn_id,
                    generation_id=turn.generation_id,
                    speech_start_time_ms=now_ms
                )
                self._emit_event(SessionEvent(
                    event=EventType.SPEECH_START,
                    session_id=self.session.session_id,
                    turn_id=turn.turn_id,
                    generation_id=turn.generation_id
                ))

            elif transition == "SPEECH_ENDED":
                now_ms = time.time() * 1000
                if self._current_metrics:
                    self._current_metrics.speech_end_time_ms = now_ms

                turn = self.session.current_turn
                turn.state = TurnStateEnum.PROCESSING
                self._emit_event(SessionEvent(
                    event=EventType.SPEECH_END,
                    session_id=self.session.session_id,
                    turn_id=turn.turn_id,
                    generation_id=turn.generation_id,
                    data={"duration_ms": len(current_speech_audio) / (16 * 2)}
                ))

                # Trigger transcription task for this completed turn
                speech_bytes = bytes(current_speech_audio)
                current_speech_audio.clear()
                
                voiced_ms = getattr(self.turn_manager, "last_finalized_speech_ms", 0.0)
                # Filter out line noise bursts and transient fragments under 20ms of actual voiced speech
                if (voiced_ms > 0 and voiced_ms < 20.0) or len(speech_bytes) < 640:
                    logger.info(f"Ignoring transient noise / sub-threshold sound (voiced={voiced_ms:.0f}ms, bytes={len(speech_bytes)}) — skipping STT/LLM")
                    self.session.current_turn.state = TurnStateEnum.LISTENING
                    self.session.user_has_floor = True
                    continue

                # ── Adaptive Speaker Enrollment ─────────────────────────────────────
                # Enroll the caller's vocal fingerprint from the first verified clean speech turn.
                # This runs at Turn 1 (language selection) and any sufficiently long speech segment
                # before the profiler has locked onto a profile.
                if not self.session.speaker_profiler.is_enrolled:
                    profile = self.session.speaker_profiler.try_enroll_from_accumulated()
                    if profile is None and speech_bytes:
                        try:
                            pcm_f32 = np.frombuffer(speech_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                            profile = self.session.speaker_profiler.enroll_from_turn_audio([pcm_f32])
                        except Exception:
                            pass

                    if profile is not None:
                        logger.info(
                            f"[SPEAKER_LOCK] Enrolled caller voice on Turn 1: "
                            f"pitch={profile.pitch_f0_hz:.1f}Hz "
                            f"centroid={profile.spectral_centroid_hz:.1f}Hz "
                            f"crest={profile.near_mic_crest_factor:.2f} "
                            f"rms={profile.baseline_rms:.4f}"
                        )
                    else:
                        logger.debug("[SPEAKER_LOCK] Insufficient audio for enrollment — will retry on next turn")
                else:
                    # Continuous Voice Profile Refinement every 5 turns
                    try:
                        turn_num = getattr(self.session, "turn_count", 1)
                        if speech_bytes:
                            pcm_f32 = np.frombuffer(speech_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                            self.session.speaker_profiler.refine_profile(pcm_f32, turn_number=turn_num)
                    except Exception as e:
                        logger.debug(f"[SPEAKER_LOCK] Profile refinement notice: {e}")
                
                logger.info(
                    f"[TURN {turn.turn_id}]\n"
                    f"speech_start={self._current_metrics.speech_start_time_ms if self._current_metrics else 0:.3f}\n"
                    f"last_speech={now_ms:.3f}\n"
                    f"silence_started={now_ms - self.turn_manager.effective_silence_duration_ms:.3f}\n"
                    f"endpoint_threshold={self.turn_manager.effective_silence_duration_ms:.0f}ms\n"
                    f"endpoint_reached={now_ms:.3f}\n"
                    f"turn_finalized",
                    extra={"session_id": self.session.session_id, "turn_id": turn.turn_id}
                )
                asyncio.create_task(self._process_stt_turn(speech_bytes, turn.turn_id, turn.generation_id, turn.cancellation_token))

            else:
                if self.turn_manager.is_in_speech and self.turn_manager.current_state in (TurnStateEnum.LISTENING, TurnStateEnum.LISTENING_AFTER_BARGE_IN):
                    current_speech_audio.extend(frame.data)
                    if self._stt_session:
                        await self._stt_session.push_audio(frame.data)
                    # Feed enrollment chunks from Turn 1 into the speaker profiler
                    if not self.session.speaker_profiler.is_enrolled and frame.data:
                        try:
                            pcm_f32 = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0
                            self.session.speaker_profiler.add_enrollment_chunk(pcm_f32, chunk_ms=20.0)
                        except Exception:
                            pass

    async def _process_stt_turn(self, audio_bytes: bytes, turn_id: str, generation_id: str, token: CancellationToken):
        """Transcribe speech buffer and submit transcript to LLM queue."""
        if token.is_cancelled:
            return

        if self._current_metrics and self._current_metrics.turn_id == turn_id:
            self._current_metrics.stt_start_time_ms = time.time() * 1000

        try:
            # Allow Sarvam Saaras to auto-detect until language is locked, then pin STT language.
            stt_lang = "unknown"
            if getattr(self.session, "language_selection_complete", False):
                preferred = self.session.preferred_language or self.session.language
                if preferred in ("en-IN", "hi-IN", "te-IN"):
                    stt_lang = preferred

            if self._stt_session:
                stt_res = await self._stt_session.finalize(language_code=stt_lang, audio_bytes=audio_bytes, turn_id=turn_id)
            else:
                stt_res = await self.stt_provider.transcribe_audio(
                    audio_bytes,
                    sample_rate=16000,
                    language_code=stt_lang
                )
            
            if token.is_cancelled:
                return

            if self._current_metrics and self._current_metrics.turn_id == turn_id:
                self._current_metrics.stt_end_time_ms = time.time() * 1000

            transcript_text = stt_res.text.strip()
            audio_duration_ms = len(audio_bytes) / (16.0 * 2.0)
            logger.info(f"[STT] Transcribed: '{transcript_text}' (detected: {stt_res.language_code}, duration={audio_duration_ms:.0f}ms)")

            # ── Filler & Passive Backchannel Suppression Guard ─────────────────────────
            # Filter out standalone hesitation fillers ("um", "uh", "hmm", "ante", "ఉమ్", "అంటే")
            # and passive backchannels ("ha", "haa", "హా", "avunu", "yes") unless the assistant
            # just asked a confirmation or yes/no question.
            should_ignore, ignore_reason = is_filler_or_unprompted_backchannel(transcript_text, self.session)
            if should_ignore:
                logger.info(
                    f"[TURN_IGNORED_FILLER] Transcript '{transcript_text}' suppressed as {ignore_reason}. "
                    f"Silently discarding and returning to LISTENING (no LLM/TTS triggered)."
                )
                self.session.current_turn.state = TurnStateEnum.LISTENING
                self.session.user_has_floor = True
                return
            elif ignore_reason == "valid_confirmation":
                logger.info(
                    f"[CONFIRMATION_ACCEPTED] Standalone confirmation '{transcript_text}' accepted "
                    f"in response to assistant question. Processing normally."
                )

            # Check for empty / noise / inaudible transcript
            noise_tokens = {"[noise]", "<silence>", "[applause]", "[laughter]", "[cough]", "[throat-clearing]", "<blank>", "[blank]"}
            is_inaudible = (
                not transcript_text
                or transcript_text.lower() in noise_tokens
                or all(c in " ._-,?!" for c in transcript_text)
            )

            if is_inaudible:
                turn = self.session.current_turn
                voiced_ms = getattr(self.turn_manager, "last_finalized_speech_ms", 0.0)
                is_post_barge = (
                    (turn and getattr(turn, "is_post_barge_in", False))
                    or (turn and turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN)
                )

                # Post-barge-in guard: Never speak clarification over a caller who just interrupted!
                # Silently yield floor back to caller so their continuing query is captured cleanly.
                if is_post_barge:
                    logger.info(
                        f"[POST_BARGE_IN_INAUDIBLE] Empty/inaudible STT transcript on post-barge-in turn {turn_id} "
                        f"(voiced_ms={voiced_ms:.0f}ms). Yielding floor back to caller without speaking clarification."
                    )
                    if turn:
                        turn.state = TurnStateEnum.LISTENING
                    self.session.user_has_floor = True
                    return

                # Voiced energy guard: Only speak clarification if VAD actually detected >= 160ms of genuine voiced speech
                if voiced_ms < 160.0:
                    logger.info(
                        f"[INAUDIBLE_SUB_THRESHOLD] Empty transcript received with voiced speech ({voiced_ms:.0f}ms) < 160ms "
                        f"(ambient/idle sound); returning to LISTENING without clarification"
                    )
                    if turn:
                        turn.state = TurnStateEnum.LISTENING
                    self.session.user_has_floor = True
                    return

                self.session.consecutive_empty_turns = getattr(self.session, "consecutive_empty_turns", 0) + 1
                active_lang = self.session.preferred_language or self.session.language or "en-IN"

                if self.session.consecutive_empty_turns <= 2:
                    clarification = INAUDIBLE_CLARIFICATION_PHRASES.get(active_lang, INAUDIBLE_CLARIFICATION_PHRASES["en-IN"])
                else:
                    clarification = INAUDIBLE_ESCALATION_PHRASES.get(active_lang, INAUDIBLE_ESCALATION_PHRASES["en-IN"])

                speech_detected_ms = voiced_ms if voiced_ms > 0 else audio_duration_ms
                logger.info(
                    f"[INAUDIBLE_AUDIO] Inaudible/empty STT transcript on turn {turn_id} "
                    f"(consecutive_empty_turns={self.session.consecutive_empty_turns}, speech_ms={speech_detected_ms:.0f}). "
                    f"Speaking clarification: \"{clarification}\""
                )

                if not token.is_cancelled and self.session.is_active:
                    turn = self.session.current_turn
                    if turn:
                        turn.generated_text = clarification
                    self.session.last_response_text = clarification
                    self.session.append_message(role="assistant", content=clarification)

                    self._emit_event(SessionEvent(
                        event=EventType.RESPONSE_TEXT_DELTA,
                        session_id=self.session.session_id,
                        turn_id=turn_id,
                        generation_id=generation_id,
                        data={"delta": clarification}
                    ))

                    await self.queues.tts_in_queue.put({
                        "delta": clarification,
                        "turn_id": turn_id,
                        "generation_id": generation_id,
                        "token": token
                    })
                    await self.queues.tts_in_queue.put({
                        "delta": "__EOF__",
                        "turn_id": turn_id,
                        "generation_id": generation_id,
                        "token": token
                    })
                else:
                    self.session.current_turn.state = TurnStateEnum.IDLE
                    self.session.user_has_floor = False
                return

            # Reset consecutive empty turns counter on any valid transcript
            self.session.consecutive_empty_turns = 0

            # Multi-segment numeric accumulator for phone numbers & structured input
            mode = getattr(self.session, "structured_input_mode", "NORMAL")
            has_digits = DigitNormalizer.has_digit_sequence(transcript_text)
            extracted_num = DigitNormalizer.extract_digits(transcript_text)
            
            if mode in (StructuredInputMode.PHONE_NUMBER, StructuredInputMode.NUMERIC, "PHONE_NUMBER", "NUMERIC") or (has_digits and self.session.has_pending_numeric_input) or (len(extracted_num) == 10):
                is_complete, resolved_text, updated_segments = NumericTurnAccumulator.handle_segment(
                    session_id=self.session.session_id,
                    current_segments=self.session.numeric_segments,
                    new_transcript=transcript_text,
                    mode=StructuredInputMode.PHONE_NUMBER if mode in (StructuredInputMode.PHONE_NUMBER, "PHONE_NUMBER") or len(extracted_num) == 10 else StructuredInputMode.NUMERIC,
                    target_digits=10
                )
                self.session.numeric_segments = updated_segments

                if not is_complete:
                    logger.info(
                        "Numeric segment buffered; continuing listening for remaining digits",
                        extra={"session_id": self.session.session_id, "turn_id": turn_id}
                    )
                    self.session.current_turn.state = TurnStateEnum.LISTENING
                    return

                # Successfully completed and validated numeric input
                transcript_text = resolved_text
                self.session.structured_input_mode = "NORMAL"
                if len(resolved_text) == 10 and resolved_text.isdigit():
                    self.session.extracted_lead["phone_number"] = resolved_text

            self.session.current_turn.raw_transcript = transcript_text
            self.session.append_message(role="user", content=transcript_text)

            self._emit_event(SessionEvent(
                event=EventType.TRANSCRIPT_FINAL,
                session_id=self.session.session_id,
                turn_id=turn_id,
                generation_id=generation_id,
                data={"text": transcript_text, "language": stt_res.language_code, "confidence": stt_res.confidence}
            ))

            # ── ARCHITECTURAL FLOW: STT -> ConversationManager -> FastQueryRouter -> TTS/LLM ──
            # Step 1: Multilingual Human Handoff Intent & Cancellation Detection
            active_lang = self.session.preferred_language or self.session.language or "en-IN"

            # Check if session is currently awaiting transfer
            if self.session.handoff_state == HandoffStateEnum.AWAITING_TRANSFER:
                if MultilingualHandoffDetector.detect_cancellation(transcript_text):
                    logger.info(f"[HANDOFF] Caller cancelled ongoing transfer on turn {turn_id}", extra={"session_id": self.session.session_id})
                    self.session.record_handoff_cancelled()
                    self.session.handoff_state = HandoffStateEnum.IDLE
                    cancel_ev = SessionEvent(
                        event=EventType.HANDOFF_CANCELLED,
                        session_id=self.session.session_id,
                        turn_id=turn_id,
                        generation_id=generation_id,
                        data={
                            "call_id": self.session.call_id,
                            "reason": "caller_cancelled"
                        }
                    )
                    self._emit_event(cancel_ev)
                    cancel_ack = {
                        "te-IN": "సరేనండి, ట్రాన్స్‌ఫర్ రద్దు చేయబడింది. నేను మీకు ఎలా సహాయపడగలను?",
                        "hi-IN": "ठीक है, ट्रांसफर रद्द कर दिया गया है। मैं आपकी और क्या मदद कर सकती हूँ?",
                        "en-IN": "Sure, I have cancelled the transfer. How else can I help you today?"
                    }.get(active_lang, "Sure, I have cancelled the transfer. How else can I help you today?")
                    
                    turn = self.session.current_turn if (self.session.current_turn and self.session.current_turn.turn_id == turn_id) else self.session.current_turn
                    if turn:
                        turn.generated_text = cancel_ack
                        turn.state = TurnStateEnum.PROCESSING
                    self.session.last_response_text = cancel_ack
                    self.session.append_message(role="assistant", content=cancel_ack)
                    self._emit_event(SessionEvent(
                        event=EventType.RESPONSE_TEXT_DELTA,
                        session_id=self.session.session_id,
                        turn_id=turn_id,
                        generation_id=generation_id,
                        data={"delta": cancel_ack}
                    ))
                    await self.queues.tts_in_queue.put({"delta": cancel_ack, "turn_id": turn_id, "generation_id": generation_id, "token": token})
                    await self.queues.tts_in_queue.put({"delta": "__EOF__", "turn_id": turn_id, "generation_id": generation_id, "token": token})
                    return
                else:
                    logger.info(f"[HANDOFF] Audio ignored during AWAITING_TRANSFER on turn {turn_id}", extra={"session_id": self.session.session_id})
                    if self.session.current_turn:
                        self.session.current_turn.state = TurnStateEnum.IDLE
                    return

            # Check if caller requested handoff or AI escalation is triggered
            if self.session.can_trigger_handoff():
                handoff_det = MultilingualHandoffDetector.detect(
                    text=transcript_text,
                    lang=active_lang,
                    out_of_scope_turns=getattr(self.session, "out_of_scope_turn_count", 0)
                )

                if handoff_det.is_handoff_requested and handoff_det.confidence >= 0.85:
                    logger.info(
                        f"[HANDOFF_TRIGGERED] session={self.session.session_id} role={handoff_det.requested_role} "
                        f"dept={handoff_det.requested_department} reason='{handoff_det.reason}' conf={handoff_det.confidence:.2f}",
                        extra={"session_id": self.session.session_id, "turn_id": turn_id}
                    )
                    self._cancel_active_llm_task("Handoff triggered")
                    self.session.record_handoff_requested(
                        role=handoff_det.requested_role,
                        department=handoff_det.requested_department,
                        reason=handoff_det.reason,
                        confidence=handoff_det.confidence
                    )

                    import datetime
                    iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    # Emit canonical handoff.requested event
                    handoff_ev = SessionEvent(
                        event=EventType.HANDOFF_REQUESTED,
                        session_id=self.session.session_id,
                        turn_id=turn_id,
                        generation_id=generation_id,
                        data={
                            "call_id": self.session.call_id,
                            "organization_id": self.session.organization_id,
                            "agent_id": self.session.agent_id,
                            "requested_role": handoff_det.requested_role,
                            "requested_department": handoff_det.requested_department,
                            "reason": handoff_det.reason,
                            "confidence": handoff_det.confidence,
                            "timestamp": iso_now
                        }
                    )
                    self._emit_event(handoff_ev)

                    # Synthesize holding announcement
                    hold_text = MultilingualHandoffDetector.get_holding_announcement(handoff_det.requested_role, lang=active_lang)
                    turn = self.session.current_turn if (self.session.current_turn and self.session.current_turn.turn_id == turn_id) else self.session.current_turn
                    if turn:
                        turn.generated_text = hold_text
                        turn.state = TurnStateEnum.PROCESSING
                    self.session.last_response_text = hold_text
                    self.session.append_message(role="assistant", content=hold_text)

                    # Transition state to AWAITING_TRANSFER
                    self.session.record_handoff_acknowledged(hold_media=True)

                    self._emit_event(SessionEvent(
                        event=EventType.RESPONSE_TEXT_DELTA,
                        session_id=self.session.session_id,
                        turn_id=turn_id,
                        generation_id=generation_id,
                        data={"delta": hold_text}
                    ))

                    now_ts = time.time() * 1000
                    if self._current_metrics and self._current_metrics.turn_id == turn_id:
                        self._current_metrics.llm_first_token_time_ms = now_ts
                        self._current_metrics.llm_end_time_ms = now_ts

                    await self.queues.tts_in_queue.put({"delta": hold_text, "turn_id": turn_id, "generation_id": generation_id, "token": token})
                    await self.queues.tts_in_queue.put({"delta": "__EOF__", "turn_id": turn_id, "generation_id": generation_id, "token": token})
                    return

                elif handoff_det.is_ambiguous and handoff_det.clarification_prompt:
                    logger.info(f"[HANDOFF_AMBIGUOUS] Asking clarification: '{handoff_det.clarification_prompt}'", extra={"session_id": self.session.session_id, "turn_id": turn_id})
                    self._cancel_active_llm_task("Handoff clarification turn")
                    turn = self.session.current_turn if (self.session.current_turn and self.session.current_turn.turn_id == turn_id) else self.session.current_turn
                    if turn:
                        turn.generated_text = handoff_det.clarification_prompt
                        turn.state = TurnStateEnum.PROCESSING
                    self.session.last_response_text = handoff_det.clarification_prompt
                    self.session.append_message(role="assistant", content=handoff_det.clarification_prompt)
                    self._emit_event(SessionEvent(
                        event=EventType.RESPONSE_TEXT_DELTA,
                        session_id=self.session.session_id,
                        turn_id=turn_id,
                        generation_id=generation_id,
                        data={"delta": handoff_det.clarification_prompt}
                    ))
                    await self.queues.tts_in_queue.put({"delta": handoff_det.clarification_prompt, "turn_id": turn_id, "generation_id": generation_id, "token": token})
                    await self.queues.tts_in_queue.put({"delta": "__EOF__", "turn_id": turn_id, "generation_id": generation_id, "token": token})
                    return

            # Step 1.5: Check language selection or dynamic mid-call switch
            direct_ack = self.conversation_manager.handle_language_selection_or_switch(
                self.session,
                transcript_text,
                detected_language=stt_res.language_code
            )
            if direct_ack:
                self._cancel_active_llm_task("Language selection/switch turn")
                turn = self.session.current_turn if (self.session.current_turn and self.session.current_turn.turn_id == turn_id) else self.session.current_turn
                if turn:
                    turn.generated_text = direct_ack
                    turn.state = TurnStateEnum.PROCESSING
                self.session.last_response_text = direct_ack
                self.session.append_message(role="assistant", content=direct_ack)

                logger.info(
                    f"[RESPONSE_OWNERSHIP_TRACE]\n"
                    f"call_id={self.session.call_id or 'none'}\n"
                    f"session_id={self.session.session_id}\n"
                    f"turn_id={turn_id}\n"
                    f"generation_id={generation_id}\n"
                    f"previous_turn_id={self.session.previous_turn_id or 'none'}\n"
                    f"previous_generation_id={self.session.previous_generation_id or 'none'}\n"
                    f"user_transcript=\"{transcript_text}\"\n"
                    f"response_text=\"{direct_ack}\"\n"
                    f"response_generation_count={self.session.turn_count}\n"
                    f"response_source=LANGUAGE_HANDLER",
                    extra={"session_id": self.session.session_id, "turn_id": turn_id}
                )

                self._emit_event(SessionEvent(
                    event=EventType.RESPONSE_TEXT_DELTA,
                    session_id=self.session.session_id,
                    turn_id=turn_id,
                    generation_id=generation_id,
                    data={"delta": direct_ack}
                ))

                now_ts = time.time() * 1000
                if self._current_metrics and self._current_metrics.turn_id == turn_id:
                    self._current_metrics.llm_first_token_time_ms = now_ts
                    self._current_metrics.llm_end_time_ms = now_ts

                await self.queues.tts_in_queue.put({"delta": direct_ack, "turn_id": turn_id, "generation_id": generation_id, "token": token})
                await self.queues.tts_in_queue.put({"delta": "__EOF__", "turn_id": turn_id, "generation_id": generation_id, "token": token})
                return

            # Step 2: Evaluate FastQueryRouter immediately (bypassing LLM queue)
            query_for_resolution = LanguagePreferenceParser.strip_language_switch_phrases(transcript_text) if self.session.language_selection_complete else transcript_text
            if not query_for_resolution:
                query_for_resolution = transcript_text

            router_t0 = time.time() * 1000
            complexity, fast_resp = await FastQueryRouter.route_and_resolve_fast_path(
                session=self.session,
                user_text=query_for_resolution,
                rag_provider=self.conversation_manager.rag_provider
            )
            router_elapsed = (time.time() * 1000) - router_t0

            if fast_resp:
                # ── FAST ROUTER HIT: Preempt any active LLM generation & dispatch directly to TTS/audio ──
                self._cancel_active_llm_task("Preempted by FastQueryRouter hit")

                turn = self.session.current_turn if (self.session.current_turn and self.session.current_turn.turn_id == turn_id) else self.session.current_turn
                if turn:
                    turn.generated_text = fast_resp
                    turn.state = TurnStateEnum.PROCESSING
                self.session.last_response_text = fast_resp
                self.session.append_message(role="assistant", content=fast_resp)

                active_lang = self.session.preferred_language or self.session.language or "en-IN"
                cache_key = f"{active_lang}:{fast_resp.strip()}"
                cached_pcm = SpeechToSpeechEngine._cached_fast_audio.get(cache_key)

                now_fast = time.time() * 1000
                stt_latency = (
                    (self._current_metrics.stt_end_time_ms or now_fast) - (self._current_metrics.stt_start_time_ms or now_fast)
                    if self._current_metrics and self._current_metrics.turn_id == turn_id else 0.0
                )
                logger.info(
                    f"[EAGER_ROUTER_BYPASS] query='{query_for_resolution}' "
                    f"response='{fast_resp[:80]}{'...' if len(fast_resp) > 80 else ''}' "
                    f"router_ms={router_elapsed:.1f} "
                    f"stt_ms={stt_latency:.0f} "
                    f"cached_audio={'YES (0ms TTS)' if cached_pcm else 'NO (stream_synthesize)'} "
                    f"bypass_llm_queue=TRUE",
                    extra={"session_id": self.session.session_id, "turn_id": turn_id}
                )

                logger.info(
                    f"[FAST_ROUTER_HIT] query='{query_for_resolution}' "
                    f"response='{fast_resp[:80]}{'...' if len(fast_resp) > 80 else ''}' "
                    f"complexity={complexity} stt_ms={stt_latency:.0f} "
                    f"llm_ms=0 (bypassed) "
                    f"cached_audio={'YES (0ms TTS)' if cached_pcm else 'NO (stream_synthesize)'} "
                    f"expected_total_ms=~{stt_latency + (0 if cached_pcm else 500):.0f}ms",
                    extra={"session_id": self.session.session_id, "turn_id": turn_id}
                )

                logger.info(
                    f"[RESPONSE_OWNERSHIP_TRACE]\n"
                    f"call_id={self.session.call_id or 'none'}\n"
                    f"session_id={self.session.session_id}\n"
                    f"turn_id={turn_id}\n"
                    f"generation_id={generation_id}\n"
                    f"previous_turn_id={self.session.previous_turn_id or 'none'}\n"
                    f"previous_generation_id={self.session.previous_generation_id or 'none'}\n"
                    f"user_transcript=\"{transcript_text}\"\n"
                    f"query_resolved=\"{query_for_resolution}\"\n"
                    f"response_text=\"{fast_resp}\"\n"
                    f"response_generation_count={self.session.turn_count}\n"
                    f"response_source=FAST_ROUTER",
                    extra={"session_id": self.session.session_id, "turn_id": turn_id}
                )

                self._emit_event(SessionEvent(
                    event=EventType.RESPONSE_TEXT_DELTA,
                    session_id=self.session.session_id,
                    turn_id=turn_id,
                    generation_id=generation_id,
                    data={"delta": fast_resp}
                ))

                if self._current_metrics and self._current_metrics.turn_id == turn_id:
                    self._current_metrics.llm_first_token_time_ms = now_fast
                    self._current_metrics.llm_end_time_ms = now_fast
                    self._current_metrics.fast_router_hit = True
                    self._current_metrics.fast_router_latency_ms = router_elapsed

                tts_packet = {
                    "delta": fast_resp,
                    "turn_id": turn_id,
                    "generation_id": generation_id,
                    "token": token,
                    "cached_pcm": cached_pcm
                }
                await self.queues.tts_in_queue.put(tts_packet)
                await self.queues.tts_in_queue.put({"delta": "__EOF__", "turn_id": turn_id, "generation_id": generation_id, "token": token})
                return

            # Step 3: Cache Miss / Complex Query -> Enqueue to LLM Worker
            enqueued_at_ms = time.time() * 1000
            llm_packet = {
                "text": query_for_resolution,
                "detected_lang": stt_res.language_code,
                "turn_id": turn_id,
                "generation_id": generation_id,
                "token": token,
                "enqueued_at_ms": enqueued_at_ms
            }
            await self.queues.llm_in_queue.put(llm_packet)

        except Exception as e:
            logger.error(f"[STT_FAILURE] STT processing failed on turn {turn_id}: {e}", extra={"session_id": self.session.session_id, "turn_id": turn_id})
            
            # Graceful voice recovery: speak a polite retry prompt in the caller's active language
            active_lang = self.session.preferred_language or self.session.language or "en-IN"
            recovery_prompts = {
                "te-IN": "క్షమించండి, మీ మాట సరిగ్గా process కాలేదు. దయచేసి ఇంకోసారి చెప్పండి.",
                "hi-IN": "क्षमा करें, आपकी आवाज़ ठीक से प्रोसेस नहीं हो पाई। कृपया फिर से बोलें।",
                "en-IN": "Sorry, I couldn't hear that clearly. Could you please say that again?"
            }
            recovery_text = recovery_prompts.get(active_lang, recovery_prompts["en-IN"])
            
            if not token.is_cancelled and self.session.is_active:
                logger.info(f"[STT_RECOVERY] Emitting graceful recovery prompt to TTS: \"{recovery_text}\"")
                await self.queues.tts_in_queue.put({
                    "text": recovery_text,
                    "turn_id": turn_id,
                    "generation_id": generation_id,
                    "token": token,
                    "language": active_lang
                })
            else:
                self.session.current_turn.state = TurnStateEnum.IDLE
                self.session.user_has_floor = False

    async def _llm_worker(self):
        """Reads cache misses from llm_in_queue, cancels any prior active generation, and runs non-blocking cancellable task."""
        while self._running and self.session.is_active:
            try:
                packet = await self.queues.llm_in_queue.get()
            except asyncio.CancelledError:
                break

            if isinstance(packet, dict):
                user_text = packet["text"]
                turn_id = packet["turn_id"]
                gen_id = packet["generation_id"]
                token = packet["token"]
                detected_lang = packet.get("detected_lang")
                enqueued_at_ms = packet.get("enqueued_at_ms", 0.0)
            else:
                user_text = packet
                turn_id = self.session.current_turn.turn_id if self.session.current_turn else "unknown"
                gen_id = self.session.current_turn.generation_id if self.session.current_turn else "unknown"
                token = self.session.current_turn.cancellation_token if self.session.current_turn else None
                detected_lang = None
                enqueued_at_ms = 0.0

            if enqueued_at_ms > 0:
                queue_wait_ms = (time.time() * 1000) - enqueued_at_ms
                if self._current_metrics and self._current_metrics.turn_id == turn_id:
                    self._current_metrics.llm_queue_wait_ms = queue_wait_ms

            if token and (token.is_cancelled or self.session.is_generation_cancelled(gen_id)):
                logger.info(f"[LLM] Skipping cancelled turn {turn_id} gen {gen_id}")
                if self.session.current_turn and self.session.current_turn.state == TurnStateEnum.PROCESSING:
                    self.session.current_turn.state = TurnStateEnum.IDLE
                self.session.conversation_state = "LISTENING"
                self.session.user_has_floor = True
                continue

            # Cancel previous LLM generation task if still active to prevent head-of-line blocking
            self._cancel_active_llm_task(f"Preempted by new turn {turn_id}")

            # Spawn non-blocking task so _llm_worker loop is immediately responsive to cancellations and queue items
            self._active_llm_task = asyncio.create_task(
                self._safe_process_conversation_turn(user_text, turn_id, gen_id, token, detected_lang),
                name=f"llm_turn_{turn_id}"
            )

    async def _safe_process_conversation_turn(self, user_text, turn_id, gen_id, token, detected_lang):
        try:
            await self._process_conversation_turn(user_text, turn_id, gen_id, token, detected_lang)
        except asyncio.CancelledError:
            logger.info(f"[LLM] Generation cancelled for turn {turn_id}")
            if self.session.current_turn and self.session.current_turn.state == TurnStateEnum.PROCESSING:
                self.session.current_turn.state = TurnStateEnum.IDLE
            self.session.conversation_state = "LISTENING"
            self.session.user_has_floor = True
        except Exception as e:
            logger.error(f"[LLM] Generation error on turn {turn_id}: {e}", extra={"session_id": self.session.session_id})
            if self.session.current_turn and self.session.current_turn.state == TurnStateEnum.PROCESSING:
                self.session.current_turn.state = TurnStateEnum.IDLE
            self.session.conversation_state = "LISTENING"
            self.session.user_has_floor = True

    async def _process_conversation_turn(
        self,
        user_text: str,
        turn_id: str,
        gen_id: str,
        token: Optional[CancellationToken],
        detected_lang: Optional[str] = None
    ):
        turn = self.session.current_turn if (self.session.current_turn and self.session.current_turn.turn_id == turn_id) else self.session.current_turn
        if turn:
            turn.state = TurnStateEnum.PROCESSING
        now_ms = time.time() * 1000
        logger.info(f"[TURN {turn_id}] llm_started={now_ms:.3f}")
        if self._current_metrics and self._current_metrics.turn_id == turn_id:
            self._current_metrics.llm_start_time_ms = now_ms

        self._emit_event(SessionEvent(
            event=EventType.RESPONSE_START,
            session_id=self.session.session_id,
            turn_id=turn_id,
            generation_id=gen_id
        ))

        # NOTE: Language selection/switch was already handled by _process_stt_turn BEFORE
        # enqueueing to llm_in_queue. Queries that reach here are guaranteed domain queries.
        # We skip re-running handle_language_selection_or_switch to prevent double acknowledgments.

        # If user switched language, clean user_text to pass domain query cleanly to FastQueryRouter & LLM
        query_for_resolution = LanguagePreferenceParser.strip_language_switch_phrases(user_text) if self.session.language_selection_complete else user_text
        if not query_for_resolution:
            query_for_resolution = user_text

        # Check for Fast FAQ / Deterministic Verified Query or Goodbye
        complexity, fast_resp = await FastQueryRouter.route_and_resolve_fast_path(
            session=self.session,
            user_text=query_for_resolution,
            rag_provider=self.conversation_manager.rag_provider
        )
        if fast_resp:
            if turn:
                turn.generated_text = fast_resp
            self.session.last_response_text = fast_resp
            self.session.append_message(role="assistant", content=fast_resp)

            # ── FAST ROUTER HIT: Check In-Memory Pre-Cached Audio ─────────────────
            active_lang = self.session.preferred_language or self.session.language or "en-IN"
            cache_key = f"{active_lang}:{fast_resp.strip()}"
            cached_pcm = SpeechToSpeechEngine._cached_fast_audio.get(cache_key)

            now_fast = time.time() * 1000
            stt_latency = (
                (self._current_metrics.stt_end_time_ms or now_fast) - (self._current_metrics.stt_start_time_ms or now_fast)
                if self._current_metrics and self._current_metrics.turn_id == turn_id else 0.0
            )
            logger.info(
                f"[FAST_ROUTER_HIT] query='{query_for_resolution}' "
                f"response='{fast_resp[:80]}{'...' if len(fast_resp) > 80 else ''}' "
                f"complexity={complexity} stt_ms={stt_latency:.0f} "
                f"llm_ms=0 (bypassed) "
                f"cached_audio={'YES (0ms TTS)' if cached_pcm else 'NO (stream_synthesize)'} "
                f"expected_total_ms=~{stt_latency + (0 if cached_pcm else 500):.0f}ms",
                extra={"session_id": self.session.session_id, "turn_id": turn_id}
            )

            logger.info(
                f"[RESPONSE_OWNERSHIP_TRACE]\n"
                f"call_id={self.session.call_id or 'none'}\n"
                f"session_id={self.session.session_id}\n"
                f"turn_id={turn_id}\n"
                f"generation_id={gen_id}\n"
                f"previous_turn_id={self.session.previous_turn_id or 'none'}\n"
                f"previous_generation_id={self.session.previous_generation_id or 'none'}\n"
                f"user_transcript=\"{user_text}\"\n"
                f"query_resolved=\"{query_for_resolution}\"\n"
                f"response_text=\"{fast_resp}\"\n"
                f"response_generation_count={self.session.turn_count}\n"
                f"response_source=FAST_ROUTER",
                extra={"session_id": self.session.session_id, "turn_id": turn_id}
            )

            self._emit_event(SessionEvent(
                event=EventType.RESPONSE_TEXT_DELTA,
                session_id=self.session.session_id,
                turn_id=turn_id,
                generation_id=gen_id,
                data={"delta": fast_resp}
            ))

            if self._current_metrics and self._current_metrics.turn_id == turn_id:
                now_ts = time.time() * 1000
                self._current_metrics.llm_first_token_time_ms = now_ts
                self._current_metrics.llm_end_time_ms = now_ts

            tts_packet = {
                "delta": fast_resp,
                "turn_id": turn_id,
                "generation_id": gen_id,
                "token": token,
                "cached_pcm": cached_pcm
            }
            await self.queues.tts_in_queue.put(tts_packet)
            await self.queues.tts_in_queue.put({"delta": "__EOF__", "turn_id": turn_id, "generation_id": gen_id, "token": token})
            return

        try:
            messages = await self.conversation_manager.assemble_llm_messages(self.session, query_for_resolution)
            
            if (token and token.is_cancelled) or self.session.is_generation_cancelled(gen_id):
                if turn and turn.state == TurnStateEnum.PROCESSING:
                    turn.state = TurnStateEnum.IDLE
                self.session.conversation_state = "LISTENING"
                self.session.user_has_floor = True
                return

            first_token = True
            generated_full = []

            async with asyncio.timeout(4.5):
                async for chunk in self.llm_provider.stream_chat(messages, cancellation_token=token):
                    if (token and token.is_cancelled) or self.session.is_generation_cancelled(gen_id):
                        break

                    if first_token and chunk.delta.strip():
                        first_token = False
                        if self._current_metrics and self._current_metrics.turn_id == turn_id:
                            self._current_metrics.llm_first_token_time_ms = time.time() * 1000

                    if chunk.delta:
                        if self.session.is_generation_cancelled(gen_id):
                            break
                        generated_full.append(chunk.delta)
                        self._emit_event(SessionEvent(
                            event=EventType.RESPONSE_TEXT_DELTA,
                            session_id=self.session.session_id,
                            turn_id=turn_id,
                            generation_id=gen_id,
                            data={"delta": chunk.delta}
                        ))
                        # Forward text packet to TTS worker
                        await self.queues.tts_in_queue.put({
                            "delta": chunk.delta,
                            "turn_id": turn_id,
                            "generation_id": gen_id,
                            "token": token
                        })

            if not (token and token.is_cancelled) and not self.session.is_generation_cancelled(gen_id):
                full_response = "".join(generated_full)
                if turn:
                    turn.generated_text = full_response
                self.session.last_response_text = full_response
                self.session.append_message(role="assistant", content=full_response)

                logger.info(
                    f"[RESPONSE_OWNERSHIP_TRACE]\n"
                    f"call_id={self.session.call_id or 'none'}\n"
                    f"session_id={self.session.session_id}\n"
                    f"turn_id={turn_id}\n"
                    f"generation_id={gen_id}\n"
                    f"previous_turn_id={self.session.previous_turn_id or 'none'}\n"
                    f"previous_generation_id={self.session.previous_generation_id or 'none'}\n"
                    f"user_transcript=\"{user_text}\"\n"
                    f"response_text=\"{full_response}\"\n"
                    f"response_generation_count={self.session.turn_count}\n"
                    f"response_source=LLM_SARVAM_105B",
                    extra={"session_id": self.session.session_id, "turn_id": turn_id}
                )
                
                # Detect if assistant asked for structured input (e.g. phone number)
                detected_mode = StructuredInputDetector.detect_mode_from_assistant_message(full_response)
                if detected_mode != StructuredInputMode.NORMAL:
                    self.session.structured_input_mode = detected_mode.value
                    logger.info(f"STRUCTURED_INPUT_START: Mode {detected_mode.value} activated for session", extra={"session_id": self.session.session_id})

                if self._current_metrics and self._current_metrics.turn_id == turn_id:
                    self._current_metrics.llm_end_time_ms = time.time() * 1000
                    self._current_metrics.response_chars = len(full_response)

                # Signal end of text stream to TTS
                await self.queues.tts_in_queue.put({
                    "delta": "__EOF__",
                    "turn_id": turn_id,
                    "generation_id": gen_id,
                    "token": token
                })
            else:
                if turn and turn.state == TurnStateEnum.PROCESSING:
                    turn.state = TurnStateEnum.IDLE
                self.session.conversation_state = "LISTENING"
                self.session.user_has_floor = True

        except asyncio.TimeoutError:
            # LLM exceeded 4.5s budget — log clearly and speak recovery prompt
            logger.error(
                f"[LLM_TIMEOUT] LLM response exceeded 4.5s deadline on turn {turn_id}. "
                f"Triggering localized recovery.",
                extra={"session_id": self.session.session_id, "turn_id": turn_id}
            )
            if turn and turn.state == TurnStateEnum.PROCESSING:
                turn.state = TurnStateEnum.IDLE
            self.session.conversation_state = "LISTENING"
            self.session.user_has_floor = True

            active_lang = self.session.preferred_language or self.session.language or "en-IN"
            timeout_prompts = {
                "te-IN": "క్షమించండి, సర్వర్ నుండి సమాధానం రావడం ఆలస్యమైంది. దయచేసి మళ్ళీ అడగండి.",
                "hi-IN": "क्षमा करें, सर्वर से समय पर जवाब नहीं आया। कृपया दोबारा पूछें।",
                "en-IN": "Sorry, the server is taking too long. Please ask me again."
            }
            recovery_text = timeout_prompts.get(active_lang, timeout_prompts["en-IN"])
            if not (token and token.is_cancelled) and not self.session.is_generation_cancelled(gen_id):
                logger.info(f"[LLM_TIMEOUT_RECOVERY] Speaking timeout recovery: \"{recovery_text}\"")
                await self.queues.tts_in_queue.put({"delta": recovery_text, "turn_id": turn_id, "generation_id": gen_id, "token": token})
                await self.queues.tts_in_queue.put({"delta": "__EOF__", "turn_id": turn_id, "generation_id": gen_id, "token": token})

        except Exception as e:
            logger.error(f"[LLM_FAILURE] LLM generation failed on turn {turn_id}: {e}", extra={"session_id": self.session.session_id})
            if turn and turn.state == TurnStateEnum.PROCESSING:
                turn.state = TurnStateEnum.IDLE
            self.session.conversation_state = "LISTENING"
            self.session.user_has_floor = True

            # Voice recovery prompt: never leave the caller in dead silence!
            active_lang = self.session.preferred_language or self.session.language or "en-IN"
            recovery_prompts = {
                "te-IN": "క్షమించండి, సమాధానం ఇవ్వడంలో కొద్దిగా ఆలస్యం అవుతోంది. దయచేసి మళ్ళీ అడగండి.",
                "hi-IN": "क्षमा करें, सर्वर से जवाब मिलने में समय लग रहा है। कृपया दोबारा पूछें।",
                "en-IN": "Sorry, that took a bit longer than expected. Could you please ask again?"
            }
            recovery_text = recovery_prompts.get(active_lang, recovery_prompts["en-IN"])
            if not (token and token.is_cancelled) and not self.session.is_generation_cancelled(gen_id):
                logger.info(f"[LLM_RECOVERY] Emitting recovery prompt to TTS on turn {turn_id}: \"{recovery_text}\"")
                await self.queues.tts_in_queue.put({"delta": recovery_text, "turn_id": turn_id, "generation_id": gen_id, "token": token})
                await self.queues.tts_in_queue.put({"delta": "__EOF__", "turn_id": turn_id, "generation_id": gen_id, "token": token})

    async def _tts_worker(self):
        """Reads text chunks from tts_in_queue, synthesizes audio frames, and pushes to audio_out_queue."""
        while self._running and self.session.is_active:
            try:
                item = await self.queues.tts_in_queue.get()
            except asyncio.CancelledError:
                break

            if isinstance(item, dict):
                initial_chunk = item["delta"]
                item_turn_id = item["turn_id"]
                item_gen_id = item["generation_id"]
                token = item["token"]
            else:
                initial_chunk = item
                item_turn_id = self.session.current_turn.turn_id if self.session.current_turn else "unknown"
                item_gen_id = self.session.current_turn.generation_id if self.session.current_turn else "unknown"
                token = self.session.current_turn.cancellation_token if self.session.current_turn else None

            if (token and token.is_cancelled) or initial_chunk == "__EOF__":
                continue

            # ── Pre-TTS Safety Gate: Do not synthesize if call ended, cancelled, or barged in ──
            if (
                not self.session.is_active
                or getattr(self.session, "is_disconnected", False)
                or (token and token.is_cancelled)
                or self.session.is_generation_cancelled(item_gen_id)
                or (self.session.current_turn and self.session.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN)
            ):
                if getattr(self.session, "is_disconnected", False):
                    self.session.tts_after_disconnect_count += 1
                elif self.session.current_turn and self.session.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN:
                    self.session.tts_after_barge_in_count += 1
                else:
                    self.session.tts_cancelled_count += 1
                logger.info(f"[TTS_GUARD] Aborted TTS synthesis for inactive/cancelled turn={item_turn_id} gen={item_gen_id}")
                continue

            # ── Hard Cost Circuit Breakers ──────────────────────────────────────────
            from app.core.config import get_settings
            _cfg = get_settings()
            if self.session.tts_requests_count >= _cfg.max_tts_requests_per_call:
                logger.error(
                    f"[CRITICAL_TTS_COST_LIMIT] Session exceeded max_tts_requests_per_call ({self.session.tts_requests_count}/{_cfg.max_tts_requests_per_call}). Aborting TTS."
                )
                continue
            if self.session.tts_chars_count >= _cfg.max_tts_chars_per_call:
                logger.error(
                    f"[CRITICAL_TTS_COST_LIMIT] Session exceeded max_tts_chars_per_call ({self.session.tts_chars_count}/{_cfg.max_tts_chars_per_call}). Aborting TTS."
                )
                continue

            turn = self.session.current_turn if (self.session.current_turn and self.session.current_turn.turn_id == item_turn_id) else self.session.current_turn
            if turn:
                turn.state = TurnStateEnum.SPEAKING
                turn.barge_in_handled = False
            self.session.is_bot_speaking = True
            self.session.user_has_floor = False
            self.session.active_playback_generation_id = item_gen_id
            self.session.active_playback_turn_id = item_turn_id
            playback_lang = self.session.preferred_language or self.session.language or "en-IN"
            self.session.active_playback_language = playback_lang
            if hasattr(self.session, "arm_playback_interrupt"):
                self.session.arm_playback_interrupt()

            now_ms = time.time() * 1000
            logger.info(f"[TURN {item_turn_id}] tts_started={now_ms:.3f} gen={item_gen_id} lang={playback_lang}")
            if self._current_metrics and self._current_metrics.turn_id == item_turn_id:
                self._current_metrics.tts_start_time_ms = now_ms

            # ── 0.0ms INSTANT DISPATCH FOR PRE-CACHED / DEDUPLICATED AUDIO ────────
            cached_pcm = item.get("cached_pcm") if isinstance(item, dict) else None
            if not cached_pcm and isinstance(item, dict):
                from app.tts.cache import TTSCacheManager
                cached_pcm = TTSCacheManager.get(initial_chunk, playback_lang, "pooja")
            if cached_pcm:
                self.session.tts_dedup_hits += 1
                logger.info(f"[AUDIO_DELIVERY] event=TTS_AUDIO_RECEIVED turn_id={item_turn_id} gen_id={item_gen_id} bytes={len(cached_pcm)} source=DEDUP_CACHE")
                logger.info(f"[TTS_CACHE_DISPATCH] 0.0ms instant dispatch of pre-cached audio ({len(cached_pcm)} bytes) gen={item_gen_id}")
                chunker = AudioChunker(sample_rate=16000, frame_duration_ms=20)
                first_audio = True
                for frame in chunker.feed(cached_pcm):
                    if (
                        (token and token.is_cancelled)
                        or self.session.is_generation_cancelled(item_gen_id)
                        or item_gen_id != self.session.active_playback_generation_id
                    ):
                        logger.info(f"[TTS] Generation cancelled during cached audio dispatch gen={item_gen_id}")
                        break

                    if first_audio:
                        first_audio = False
                        now_ms = time.time() * 1000
                        if self._current_metrics and self._current_metrics.turn_id == item_turn_id:
                            self._current_metrics.tts_first_audio_time_ms = now_ms
                            m = self._current_metrics
                            sp_end = m.speech_end_time_ms or 0
                            tot_ms = now_ms - sp_end if sp_end > 0 else (now_ms - m.tts_start_time_ms if m.tts_start_time_ms else 0)
                            logger.info(
                                f"[VOICE_LATENCY] turn_id={item_turn_id} "
                                f"speech_to_first_audio={tot_ms:.0f}ms "
                                f"stt={m.stt_latency_ms:.0f}ms "
                                f"llm_ttft=0ms "
                                f"tts_first_audio=0ms (PRE-CACHED RAM)"
                            )

                    if turn:
                        turn.tts_audio_chunks_count += 1
                    self.session.extend_playback_deadline(20.0)
                    self._outbound_ref_buffer.append(frame.to_numpy_float32())
                    try:
                        self.queues.audio_out_queue.put_nowait(frame)
                    except asyncio.QueueFull:
                        pass

                    if (
                        not (token and token.is_cancelled)
                        and not self.session.is_generation_cancelled(item_gen_id)
                        and item_gen_id == self.session.active_playback_generation_id
                    ):
                        b64_audio = AudioCodec.frame_to_base64(frame)
                        self._emit_event(SessionEvent(
                            event=EventType.AUDIO_OUTPUT,
                            session_id=self.session.session_id,
                            turn_id=item_turn_id,
                            generation_id=item_gen_id,
                            data={
                                "data": b64_audio,
                                "seq": frame.seq,
                                "sample_rate": frame.sample_rate,
                                "duration_ms": frame.duration_ms,
                                "language": playback_lang,
                                "cancellation_cycle": getattr(self.session, "cancellation_cycle_id", 0)
                            }
                        ))

                final_frame = chunker.flush()
                if final_frame and not (token and token.is_cancelled) and not self.session.is_generation_cancelled(item_gen_id):
                    self.session.extend_playback_deadline(20.0)
                    self._outbound_ref_buffer.append(final_frame.to_numpy_float32())
                    try:
                        self.queues.audio_out_queue.put_nowait(final_frame)
                    except asyncio.QueueFull:
                        pass
                    b64_audio = AudioCodec.frame_to_base64(final_frame)
                    self._emit_event(SessionEvent(
                        event=EventType.AUDIO_OUTPUT,
                        session_id=self.session.session_id,
                        turn_id=item_turn_id,
                        generation_id=item_gen_id,
                        data={
                            "data": b64_audio,
                            "seq": final_frame.seq,
                            "sample_rate": final_frame.sample_rate,
                            "duration_ms": final_frame.duration_ms,
                            "language": playback_lang,
                            "cancellation_cycle": getattr(self.session, "cancellation_cycle_id", 0)
                        }
                    ))

                # Drain the __EOF__ sentinel from tts_in_queue for this generation
                try:
                    await asyncio.wait_for(self.queues.tts_in_queue.get(), timeout=0.05)
                except Exception:
                    pass

                self._emit_event(SessionEvent(
                    event=EventType.RESPONSE_END,
                    session_id=self.session.session_id,
                    turn_id=item_turn_id,
                    generation_id=item_gen_id
                ))
                continue

            # Create an async generator for text arriving in this response cycle
            accumulated_chars = len(initial_chunk)
            max_turn_chars = _cfg.max_tts_chars_per_turn
            self.session.tts_requests_count += 1
            self.session.tts_chars_count += len(initial_chunk)

            async def text_streamer():
                nonlocal accumulated_chars
                yield initial_chunk
                while True:
                    try:
                        nxt = await asyncio.wait_for(self.queues.tts_in_queue.get(), timeout=2.0)
                        if isinstance(nxt, dict):
                            nxt_delta = nxt["delta"]
                            nxt_token = nxt["token"]
                            nxt_gen = nxt["generation_id"]
                            if (nxt_token and nxt_token.is_cancelled) or nxt_gen != item_gen_id or nxt_delta == "__EOF__":
                                break
                            if accumulated_chars + len(nxt_delta) > max_turn_chars:
                                allowed_len = max(0, max_turn_chars - accumulated_chars)
                                if allowed_len > 0:
                                    accumulated_chars += allowed_len
                                    self.session.tts_chars_count += allowed_len
                                    yield nxt_delta[:allowed_len]
                                logger.warning(
                                    f"[TTS_BUDGET_APPLIED] Reached MAX_TTS_CHARS_PER_TURN ({max_turn_chars}). "
                                    f"Truncated remainder of response for generation {item_gen_id}."
                                )
                                break
                            accumulated_chars += len(nxt_delta)
                            self.session.tts_chars_count += len(nxt_delta)
                            yield nxt_delta
                        else:
                            if nxt == "__EOF__" or (token and token.is_cancelled):
                                break
                            if accumulated_chars + len(nxt) > max_turn_chars:
                                allowed_len = max(0, max_turn_chars - accumulated_chars)
                                if allowed_len > 0:
                                    accumulated_chars += allowed_len
                                    self.session.tts_chars_count += allowed_len
                                    yield nxt[:allowed_len]
                                logger.warning(f"[TTS_BUDGET_APPLIED] Reached MAX_TTS_CHARS_PER_TURN ({max_turn_chars}).")
                                break
                            accumulated_chars += len(nxt)
                            self.session.tts_chars_count += len(nxt)
                            yield nxt
                    except asyncio.TimeoutError:
                        break

            try:
                first_audio = True
                if hasattr(self.session, "arm_playback_interrupt"):
                    self.session.arm_playback_interrupt()
                async with asyncio.timeout(8.0):
                    async for audio_chunk in self.tts_provider.stream_synthesize(
                        text_stream=text_streamer(),
                        language_code=playback_lang,
                        cancellation_token=token
                    ):
                        if (
                            (token and token.is_cancelled)
                            or self.session.is_generation_cancelled(item_gen_id)
                            or item_gen_id != self.session.active_playback_generation_id
                        ):
                            logger.info(f"[TTS] Generation cancelled during audio streaming gen={item_gen_id}", extra={"session_id": self.session.session_id})
                            break

                        frame = audio_chunk.frame
                        if first_audio:
                            first_audio = False
                            logger.info(f"[AUDIO_DELIVERY] event=TTS_AUDIO_RECEIVED turn_id={item_turn_id} gen_id={item_gen_id}")
                            now_ms = time.time() * 1000
                            if self._current_metrics and self._current_metrics.turn_id == item_turn_id:
                                self._current_metrics.tts_first_audio_time_ms = now_ms
                                m = self._current_metrics
                                sp_end = m.speech_end_time_ms or 0
                                tot_ms = now_ms - sp_end if sp_end > 0 else (now_ms - m.tts_start_time_ms if m.tts_start_time_ms else 0)
                                stt_lat = m.stt_latency_ms
                                llm_ttft = m.time_to_first_token_ms
                                tts_ttfa = (now_ms - m.tts_start_time_ms) if m.tts_start_time_ms else 0
                                logger.info(
                                    f"[VOICE_LATENCY] turn_id={item_turn_id} "
                                    f"speech_to_first_audio={tot_ms:.0f}ms "
                                    f"stt={stt_lat:.0f}ms "
                                    f"llm_ttft={llm_ttft:.0f}ms "
                                    f"tts_first_audio={tts_ttfa:.0f}ms"
                                )

                        if turn:
                            turn.tts_audio_chunks_count += 1
                        now_ms = time.time() * 1000
                        self.session.extend_playback_deadline(20.0)
                        self._outbound_ref_buffer.append(frame.to_numpy_float32())
                        try:
                            self.queues.audio_out_queue.put_nowait(frame)
                            logger.debug(f"[AUDIO_DELIVERY] event=AUDIO_QUEUED turn_id={item_turn_id} gen_id={item_gen_id} seq={frame.seq}")
                        except asyncio.QueueFull:
                            pass

                        # Emit audio output event with base64 payload if generation is uncancelled and active
                        if (
                            not (token and token.is_cancelled)
                            and not self.session.is_generation_cancelled(item_gen_id)
                            and item_gen_id == self.session.active_playback_generation_id
                        ):
                            b64_audio = AudioCodec.frame_to_base64(frame)
                            self._emit_event(SessionEvent(
                                event=EventType.AUDIO_OUTPUT,
                                session_id=self.session.session_id,
                                turn_id=item_turn_id,
                                generation_id=item_gen_id,
                                data={
                                    "data": b64_audio,
                                    "seq": frame.seq,
                                    "sample_rate": frame.sample_rate,
                                    "language": playback_lang,
                                    "cancellation_cycle": getattr(self.session, "cancellation_cycle_id", 0)
                                }
                            ))

                if not (token and token.is_cancelled) and not self.session.is_generation_cancelled(item_gen_id):
                    if self._current_metrics and self._current_metrics.turn_id == item_turn_id:
                        self._current_metrics.tts_end_time_ms = time.time() * 1000
                        self.latency_tracker.record_turn(self._current_metrics)

                    self._emit_event(SessionEvent(
                        event=EventType.RESPONSE_END,
                        session_id=self.session.session_id,
                        turn_id=item_turn_id,
                        generation_id=item_gen_id,
                        data=self._current_metrics.to_dict() if self._current_metrics else {}
                    ))
                    # Mark generation COMPLETED at synthesizer level
                    if hasattr(self.session, "set_generation_state"):
                        from app.session.state import GenerationLifecycleState
                        self.session.set_generation_state(item_gen_id, GenerationLifecycleState.COMPLETED)

                # Synthesis task completed. If cancelled, perform immediate cleanup;
                # otherwise leave active_playback_generation_id active for telephony writer pacing.
                if (token and token.is_cancelled) or self.session.is_generation_cancelled(item_gen_id):
                    if turn:
                        turn.state = TurnStateEnum.INTERRUPTED
                    self.session.is_bot_speaking = False
                    self.session.active_playback_generation_id = None
                    self.session.active_playback_turn_id = None
                    self.session.playback_estimated_end_time_ms = 0.0
                    self.session.user_has_floor = True
                    self.session.conversation_state = "LISTENING"

            except asyncio.TimeoutError:
                logger.error(
                    f"[TTS_TIMEOUT] TTS synthesis exceeded 8s deadline for gen={item_gen_id}. "
                    f"Cleaning up playback state.",
                    extra={"session_id": self.session.session_id}
                )
                if turn:
                    turn.state = TurnStateEnum.LISTENING
                self.session.is_bot_speaking = False
                self.session.active_playback_generation_id = None
                self.session.active_playback_turn_id = None
                self.session.playback_estimated_end_time_ms = 0.0
                self.session.conversation_state = "LISTENING"
                self.session.user_has_floor = True

            except Exception as e:
                logger.error(f"TTS synthesis failed: {e}", extra={"session_id": self.session.session_id})
                if turn:
                    turn.state = TurnStateEnum.LISTENING
                self.session.is_bot_speaking = False
                self.session.active_playback_generation_id = None
                self.session.active_playback_turn_id = None
                self.session.playback_estimated_end_time_ms = 0.0
                self.session.conversation_state = "LISTENING"
                self.session.user_has_floor = True

    async def handle_handoff_acknowledged(self, status: str = "resolving_target", hold_media: bool = True):
        """Called when Gateway emits handoff.acknowledged."""
        logger.info(f"[HANDOFF_ACKNOWLEDGED] Session {self.session.session_id} status={status}, hold_media={hold_media}", extra={"session_id": self.session.session_id})
        self.session.record_handoff_acknowledged(hold_media=hold_media)
        self._cancel_active_llm_task("Handoff acknowledged by gateway")

    async def handle_handoff_fallback(self, reason: str = "NO_ELIGIBLE_STAFF", prompt_instruction: Optional[str] = None):
        """
        Called when Gateway emits handoff.fallback.
        Exits transfer-waiting state, restores normal LLM/VAD turn-taking, speaks polite fallback response, and resumes conversation.
        """
        logger.info(f"[HANDOFF_FALLBACK] Session {self.session.session_id} reason={reason}, prompt_instruction={prompt_instruction}", extra={"session_id": self.session.session_id})
        self.session.record_handoff_fallback()

        active_lang = self.session.preferred_language or self.session.language or "en-IN"
        fallback_text = prompt_instruction or MultilingualHandoffDetector.get_fallback_announcement(reason=reason, lang=active_lang)

        turn = self.session.start_new_turn(reason=f"Handoff fallback recovery: {reason}")
        turn.generated_text = fallback_text
        turn.state = TurnStateEnum.PROCESSING
        self.session.last_response_text = fallback_text
        self.session.append_message(role="assistant", content=fallback_text)

        self._emit_event(SessionEvent(
            event=EventType.RESPONSE_START,
            session_id=self.session.session_id,
            turn_id=turn.turn_id,
            generation_id=turn.generation_id
        ))
        self._emit_event(SessionEvent(
            event=EventType.RESPONSE_TEXT_DELTA,
            session_id=self.session.session_id,
            turn_id=turn.turn_id,
            generation_id=turn.generation_id,
            data={"delta": fallback_text}
        ))

        await self.queues.tts_in_queue.put({
            "delta": fallback_text,
            "turn_id": turn.turn_id,
            "generation_id": turn.generation_id,
            "token": turn.cancellation_token
        })
        await self.queues.tts_in_queue.put({
            "delta": "__EOF__",
            "turn_id": turn.turn_id,
            "generation_id": turn.generation_id,
            "token": turn.cancellation_token
        })
        self.session.handoff_state = HandoffStateEnum.IDLE
        self.session.conversation_state = "LISTENING"


