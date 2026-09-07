"""Text-to-Speech (TTS) Provider interfaces and adapters."""
from app.tts.base import TTSProvider, TTSAudioChunk
from app.tts.sarvam import SarvamTTSProvider
from app.tts.elevenlabs import ElevenLabsTTSProvider
from app.tts.mock import MockTTSProvider

__all__ = [
    "TTSProvider",
    "TTSAudioChunk",
    "SarvamTTSProvider",
    "ElevenLabsTTSProvider",
    "MockTTSProvider",
]
