"""Core Speech-to-Speech (S2S) Pipeline Engine coordinating VAD, STT, LLM, and TTS workers."""
import asyncio
import collections
import time
from typing import Optional, List
import numpy as np
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.audio.buffering import AudioChunker
from app.session.state import SessionState, TurnStateEnum, GreetingStateEnum
from app.session.events import SessionEvent, EventType
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
from app.conversation.router import FastQueryRouter, QueryComplexity
from app.metrics.latency import TurnMetrics, LatencyTracker
from app.metrics.events import MetricsCollector
from app.core.logging import get_logger

logger = get_logger("pipeline.engine")

# Module-level greeting audio cache for 0ms TTFB on subsequent calls
_GREETING_AUDIO_CACHE: dict[str, bytes] = {}


class SpeechToSpeechEngine:
    """
    Asynchronous Speech-to-Speech Engine.
    Coordinates isolated worker loops for VAD, STT, Conversation/LLM, and TTS.
    """

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
        min_barge_in_duration_ms: int = 80,
        barge_in_min_confidence: float = 0.45,
        barge_in_min_rms: float = 0.010,
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
            on_barge_in_callback=self._handle_barge_in_event
        )

        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._current_metrics: Optional[TurnMetrics] = None
        self._outbound_ref_buffer: collections.deque = collections.deque(maxlen=100)
        self._stt_session = self.stt_provider.create_streaming_session() if hasattr(self.stt_provider, "create_streaming_session") else None

    def _handle_barge_in_event(self, old_turn_id: str, old_gen_id: str):
        """Emit cancellation event when barge-in occurs."""
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
                f"Welcome to {self.session.institution_name}. "
                "Which language do you prefer? English, Hindi, or Telugu?"
            )
            global _GREETING_AUDIO_CACHE
            if greeting_text not in _GREETING_AUDIO_CACHE:
                pcm_bytes = await self.tts_provider.synthesize_text(greeting_text, language_code="en-IN")
                if pcm_bytes and len(pcm_bytes) >= 32000:
                    _GREETING_AUDIO_CACHE[greeting_text] = pcm_bytes
                    logger.info("[GREETING] Pre-cached static greeting audio for 0ms initial dispatch")
        except Exception as e:
            logger.debug(f"Provider prewarm notice: {e}")

    async def stop(self):
        """Stop engine and cancel background worker tasks."""
        self._running = False
        self.session.close()
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
            f"Welcome to {self.session.institution_name}. "
            "Which language do you prefer? English, Hindi, or Telugu?"
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
            if greeting_text in _GREETING_AUDIO_CACHE and len(_GREETING_AUDIO_CACHE[greeting_text]) >= 64000:
                pcm_bytes = _GREETING_AUDIO_CACHE[greeting_text]
            else:
                pcm_bytes = await self.tts_provider.synthesize_text(greeting_text, language_code="en-IN")
                if not pcm_bytes or len(pcm_bytes) < 32000:
                    # Provide rich 4.5-second greeting audio fallback (144000 bytes @ 16kHz mono)
                    pcm_bytes = AudioFrame.silence(duration_ms=4500, sample_rate=16000).data
                else:
                    _GREETING_AUDIO_CACHE[greeting_text] = pcm_bytes

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
            if vad_res.is_speech or vad_res.confidence >= 0.15 or rms >= 0.015 or frame_count % 50 == 0:
                stt_depth = getattr(self._stt_session, "queue_depth", 0) if self._stt_session else 0
                stt_healthy = getattr(self._stt_session, "is_stream_healthy", False) if self._stt_session else False
                logger.info(
                    f"[VAD_FRAME #{frame_count}] is_speech={vad_res.is_speech} conf={vad_res.confidence:.4f} rms={rms:.4f} "
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
                current_speech_audio.clear()
                self._outbound_ref_buffer.clear()
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
                if turn.cancellation_token.is_cancelled or turn.state == TurnStateEnum.INTERRUPTED:
                    turn = self.session.start_new_turn(reason="Speech started on cancelled turn")
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
                # Filter out short line noise bursts, breaths, taps, and transient audio fragments under 100ms of actual voiced speech
                if (voiced_ms > 0 and voiced_ms < 100.0) or len(speech_bytes) < 1600:
                    logger.info(f"Ignoring transient noise / sub-threshold sound (voiced={voiced_ms:.0f}ms, bytes={len(speech_bytes)}) — skipping STT/LLM")
                    self.session.current_turn.state = TurnStateEnum.LISTENING
                    self.session.user_has_floor = True
                    continue
                
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
            logger.info(f"[STT] Transcribed: '{transcript_text}' (detected: {stt_res.language_code}, duration={len(audio_bytes)/(16*2):.0f}ms)")
            if not transcript_text:
                logger.info("Empty transcript received; returning to LISTENING")
                self.session.current_turn.state = TurnStateEnum.LISTENING
                self.session.user_has_floor = True
                return

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

            # Push structured turn packet to LLM input queue
            llm_packet = {
                "text": transcript_text,
                "detected_lang": stt_res.language_code,
                "turn_id": turn_id,
                "generation_id": generation_id,
                "token": token
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
        """Reads transcripts from llm_in_queue, coordinates prompts/tools, streams LLM output to tts_in_queue."""
        active_turn_task = None
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
            else:
                user_text = packet
                turn_id = self.session.current_turn.turn_id if self.session.current_turn else "unknown"
                gen_id = self.session.current_turn.generation_id if self.session.current_turn else "unknown"
                token = self.session.current_turn.cancellation_token if self.session.current_turn else None
                detected_lang = None

            if token and (token.is_cancelled or self.session.is_generation_cancelled(gen_id)):
                logger.info(f"[LLM] Skipping cancelled turn {turn_id} gen {gen_id}")
                if self.session.current_turn and self.session.current_turn.state == TurnStateEnum.PROCESSING:
                    self.session.current_turn.state = TurnStateEnum.IDLE
                self.session.conversation_state = "LISTENING"
                self.session.user_has_floor = True
                continue

            # Cancel previous LLM generation task if it's still running
            if active_turn_task and not active_turn_task.done():
                active_turn_task.cancel()

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

        # Check if language is being chosen or switched
        direct_ack = self.conversation_manager.handle_language_selection_or_switch(
            self.session,
            user_text,
            detected_language=detected_lang
        )
        if direct_ack:
            if turn:
                turn.generated_text = direct_ack
            self.session.last_response_text = direct_ack
            self.session.append_message(role="assistant", content=direct_ack)

            logger.info(
                f"[RESPONSE_OWNERSHIP_TRACE]\n"
                f"call_id={self.session.call_id or 'none'}\n"
                f"session_id={self.session.session_id}\n"
                f"turn_id={turn_id}\n"
                f"generation_id={gen_id}\n"
                f"previous_turn_id={self.session.previous_turn_id or 'none'}\n"
                f"previous_generation_id={self.session.previous_generation_id or 'none'}\n"
                f"user_transcript=\"{user_text}\"\n"
                f"response_text=\"{direct_ack}\"\n"
                f"response_generation_count={self.session.turn_count}\n"
                f"response_source=LANGUAGE_HANDLER",
                extra={"session_id": self.session.session_id, "turn_id": turn_id}
            )

            self._emit_event(SessionEvent(
                event=EventType.RESPONSE_TEXT_DELTA,
                session_id=self.session.session_id,
                turn_id=turn_id,
                generation_id=gen_id,
                data={"delta": direct_ack}
            ))

            if self._current_metrics and self._current_metrics.turn_id == turn_id:
                now_ts = time.time() * 1000
                self._current_metrics.llm_first_token_time_ms = now_ts
                self._current_metrics.llm_end_time_ms = now_ts

            await self.queues.tts_in_queue.put({"delta": direct_ack, "turn_id": turn_id, "generation_id": gen_id, "token": token})
            await self.queues.tts_in_queue.put({"delta": "__EOF__", "turn_id": turn_id, "generation_id": gen_id, "token": token})
            return

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

            await self.queues.tts_in_queue.put({"delta": fast_resp, "turn_id": turn_id, "generation_id": gen_id, "token": token})
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

        except Exception as e:
            logger.error(f"LLM generation failed: {e}", extra={"session_id": self.session.session_id})
            if turn and turn.state == TurnStateEnum.PROCESSING:
                turn.state = TurnStateEnum.IDLE
            self.session.conversation_state = "LISTENING"
            self.session.user_has_floor = True

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

            if (token and token.is_cancelled) or self.session.is_generation_cancelled(item_gen_id):
                continue

            turn = self.session.current_turn if (self.session.current_turn and self.session.current_turn.turn_id == item_turn_id) else self.session.current_turn
            if turn:
                turn.state = TurnStateEnum.SPEAKING
            self.session.is_bot_speaking = True
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

            # Create an async generator for text arriving in this response cycle
            async def text_streamer():
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
                            yield nxt_delta
                        else:
                            if nxt == "__EOF__" or (token and token.is_cancelled):
                                break
                            yield nxt
                    except asyncio.TimeoutError:
                        break

            try:
                first_audio = True
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
                    except asyncio.QueueFull:
                        pass

                    # Emit audio output event with base64 payload if generation is uncancelled and active
                    if (
                        not (token and token.is_cancelled)
                        and not self.session.is_generation_cancelled(item_gen_id)
                        and not self.session.user_has_floor
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

            except Exception as e:
                logger.error(f"TTS synthesis failed: {e}", extra={"session_id": self.session.session_id})
                if turn:
                    turn.state = TurnStateEnum.IDLE
                self.session.is_bot_speaking = False
                self.session.active_playback_generation_id = None
                self.session.active_playback_turn_id = None
                self.session.playback_estimated_end_time_ms = 0.0
                self.session.conversation_state = "LISTENING"
                self.session.user_has_floor = True
