"""Per-session isolated asynchronous pipeline queues."""
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from app.audio.frames import AudioFrame
from app.stt.base import STTChunk
from app.llm.base import LLMChunk
from app.tts.base import TTSAudioChunk
from app.session.events import SessionEvent, EventType


@dataclass
class PipelineQueueBundle:
    """Isolated asynchronous queue bundle for a single voice session."""
    audio_in_queue: asyncio.Queue[AudioFrame] = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    vad_queue: asyncio.Queue[AudioFrame] = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    stt_queue: asyncio.Queue[AudioFrame] = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    llm_in_queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=500))
    tts_in_queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=500))
    audio_out_queue: asyncio.Queue[AudioFrame] = field(default_factory=lambda: asyncio.Queue(maxsize=5000))
    event_out_queue: asyncio.Queue[SessionEvent] = field(default_factory=lambda: asyncio.Queue(maxsize=5000))

    def flush_output_queues(self):
        """Immediately clear pending TTS, Audio Output, LLM, and Outbound Event queues upon barge-in."""
        # Drain tts_in_queue
        while not self.tts_in_queue.empty():
            try:
                self.tts_in_queue.get_nowait()
            except Exception:
                break

        # Drain audio_out_queue
        while not self.audio_out_queue.empty():
            try:
                self.audio_out_queue.get_nowait()
            except Exception:
                break

        # Drain llm_in_queue
        while not self.llm_in_queue.empty():
            try:
                self.llm_in_queue.get_nowait()
            except Exception:
                break

        # Drain event_out_queue of audio frames but preserve control events
        retained_events = []
        while not self.event_out_queue.empty():
            try:
                ev = self.event_out_queue.get_nowait()
                # Keep critical cancellation and control events
                if ev.event in (
                    EventType.RESPONSE_CANCELLED,
                    EventType.AUDIO_FLUSH,
                    EventType.AUDIO_PLAYBACK_STOP,
                    "response.cancelled",
                    "audio.flush",
                    "audio.playback.stop"
                ):
                    retained_events.append(ev)
            except Exception:
                break
        for ev in retained_events:
            try:
                self.event_out_queue.put_nowait(ev)
            except Exception:
                break
