"""Configuration settings for Edu-Voice Voice Engine."""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Voice Engine runtime configuration."""
    model_config = SettingsConfigDict(
        env_file=(".env", "voice-engine/.env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # General
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Server
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # API Keys (names only in env template, loaded safely here)
    sarvam_api_key: Optional[str] = Field(default=None, alias="SARVAM_API_KEY")
    elevenlabs_api_key: Optional[str] = Field(default=None, alias="ELEVENLABS_API_KEY")

    # Provider Stack Selection
    vad_provider: str = Field(default="silero", alias="VAD_PROVIDER")
    stt_provider: str = Field(default="sarvam", alias="STT_PROVIDER")
    llm_provider: str = Field(default="sarvam", alias="LLM_PROVIDER")
    tts_provider: str = Field(default="sarvam", alias="TTS_PROVIDER")

    # Model specifications
    llm_model: str = Field(default="sarvam-105b-conversations", alias="LLM_MODEL")
    stt_model: str = Field(default="saaras:v3", alias="STT_MODEL")
    tts_model: str = Field(default="bulbul:v3", alias="TTS_MODEL")
    tts_speaker: str = Field(default="priya", alias="TTS_SPEAKER")

    # Audio Parameters
    sample_rate: int = Field(default=16000, alias="SAMPLE_RATE")
    channels: int = Field(default=1, alias="CHANNELS")
    frame_duration_ms: int = Field(default=20, alias="FRAME_DURATION_MS")

    # VAD Parameters
    vad_threshold: float = Field(default=0.50, alias="VAD_THRESHOLD")
    vad_barge_in_threshold: float = Field(default=0.45, alias="VAD_BARGE_IN_THRESHOLD")
    min_silence_duration_ms: int = Field(default=350, alias="MIN_SILENCE_DURATION_MS")
    min_speech_duration_ms: int = Field(default=60, alias="MIN_SPEECH_DURATION_MS")

    # Conversation Response Profile
    response_style: str = Field(default="concise", alias="RESPONSE_STYLE")
    max_sentences: int = Field(default=2, alias="MAX_SENTENCES")
    max_chars_soft: int = Field(default=180, alias="MAX_CHARS_SOFT")

    # TTS Chunking & Prefetching Parameters
    tts_min_chars: int = Field(default=35, alias="TTS_MIN_CHARS")
    tts_max_chars: int = Field(default=180, alias="TTS_MAX_CHARS")

    # Turn Detection & Structured Input Parameters
    normal_silence_ms: int = Field(default=350, alias="NORMAL_SILENCE_MS")
    short_utterance_silence_ms: int = Field(default=350, alias="SHORT_UTTERANCE_SILENCE_MS")
    language_selection_silence_ms: int = Field(default=350, alias="LANGUAGE_SELECTION_SILENCE_MS")
    structured_input_silence_ms: int = Field(default=1200, alias="STRUCTURED_INPUT_SILENCE_MS")
    barge_in_confirmation_ms: int = Field(default=140, alias="BARGE_IN_CONFIRMATION_MS")
    barge_in_min_confidence: float = Field(default=0.40, alias="BARGE_IN_MIN_CONFIDENCE")
    barge_in_min_rms: float = Field(default=0.008, alias="BARGE_IN_MIN_RMS")
    vocal_energy_ratio_threshold: float = Field(default=0.35, alias="VOCAL_ENERGY_RATIO_THRESHOLD")
    barge_in_acknowledgment_enabled: bool = Field(default=False, alias="BARGE_IN_ACKNOWLEDGMENT_ENABLED")
    phone_number_min_digits: int = Field(default=10, alias="PHONE_NUMBER_MIN_DIGITS")
    phone_number_max_digits: int = Field(default=15, alias="PHONE_NUMBER_MAX_DIGITS")
    supported_languages: list = Field(default_factory=lambda: ["en-IN", "hi-IN", "te-IN"], alias="SUPPORTED_LANGUAGES")

    # RAG Settings
    rag_endpoint: str = Field(default="http://localhost:8000/api/v1/rag", alias="RAG_ENDPOINT")
    rag_use_mock: bool = Field(default=True, alias="RAG_USE_MOCK")

    # Exotel Settings
    exotel_account_sid: Optional[str] = Field(default=None, alias="EXOTEL_ACCOUNT_SID")
    exotel_api_key: Optional[str] = Field(default=None, alias="EXOTEL_API_KEY")
    exotel_api_token: Optional[str] = Field(default=None, alias="EXOTEL_API_TOKEN")
    exotel_base_url: str = Field(default="https://api.exotel.com", alias="EXOTEL_BASE_URL")
    exotel_exophone: Optional[str] = Field(default=None, alias="EXOTEL_EXOPHONE")
    public_voice_ws_url: Optional[str] = Field(default=None, alias="PUBLIC_VOICE_WS_URL")
    exotel_echo_test: bool = Field(default=False, alias="EXOTEL_ECHO_TEST")


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Retrieve or initialize the global settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
