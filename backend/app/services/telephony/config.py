"""Telephony service configuration using Pydantic Settings.

Secrets are protected using SecretStr to prevent accidental exposure in
logs, tracebacks, or string representations.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelephonySettings(BaseSettings):
    """Configuration settings for Telephony / Voice Gateway."""

    model_config = SettingsConfigDict(
        env_prefix="TELEPHONY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Internal Backend Communication (Aravind FastAPI Service)
    backend_internal_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices(
            "TELEPHONY_BACKEND_INTERNAL_URL", "BACKEND_INTERNAL_URL"
        ),
        description="Base URL for internal FastAPI backend service calls",
    )
    internal_service_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "TELEPHONY_INTERNAL_SERVICE_KEY", "INTERNAL_SERVICE_KEY"
        ),
        description="Shared secret key for authenticating internal service requests (X-Internal-Service-Key)",
    )
    did_resolve_timeout_ms: int = Field(
        default=2000,
        ge=100,
        le=10000,
        validation_alias=AliasChoices(
            "TELEPHONY_DID_RESOLVE_TIMEOUT_MS", "DID_RESOLVE_TIMEOUT_MS"
        ),
        description="Timeout in milliseconds for internal DID resolution requests",
    )
    outbound_idempotency_store_path: str = Field(
        default="data/outbound_idempotency.db",
        validation_alias=AliasChoices(
            "TELEPHONY_OUTBOUND_IDEMPOTENCY_STORE_PATH", "OUTBOUND_IDEMPOTENCY_STORE_PATH"
        ),
        description="File path for persistent SQLite outbound idempotency store",
    )

    # Webhook Verification Configuration
    webhook_secret: SecretStr = Field(
        default=SecretStr(""),
        description="Secret key used for HMAC-SHA256 signature verification",
    )
    signature_verification_enabled: bool = Field(
        default=True,
        description="Whether to enforce webhook signature verification",
    )
    webhook_tolerance_seconds: int = Field(
        default=300,
        description="Maximum allowed clock skew / timestamp drift in seconds (replay protection)",
    )

    # Realtime Voice Gateway Settings (Phase 2 & 3)
    max_audio_queue_size: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Bounded queue capacity for audio frames to prevent unbounded memory growth",
    )
    session_timeout_seconds: int = Field(
        default=1800,
        ge=60,
        description="Maximum idle lifetime in seconds for inactive realtime sessions",
    )
    max_session_duration_seconds: int = Field(
        default=3600,
        ge=300,
        description="Maximum absolute lifetime in seconds for any single call session",
    )
    max_active_sessions: int = Field(
        default=500,
        ge=1,
        le=10000,
        description="Maximum concurrent active realtime sessions allowed across the gateway",
    )
    max_audio_frame_size_bytes: int = Field(
        default=65536,
        ge=128,
        le=1048576,
        description="Maximum allowed raw payload size in bytes for a single audio frame (64KB)",
    )
    max_message_size_bytes: int = Field(
        default=131072,
        ge=256,
        le=2097152,
        description="Maximum allowed JSON/text wire message size in bytes (128KB)",
    )
    rate_limit_connections_per_min: int = Field(
        default=60,
        ge=1,
        description="Maximum connection attempts allowed per client IP/key per minute",
    )
    session_cleanup_interval_seconds: int = Field(
        default=30,
        ge=5,
        description="Interval in seconds between automated session pruning sweeps",
    )
    ws_ping_interval_seconds: int = Field(
        default=20,
        ge=5,
        description="WebSocket ping heartbeat interval in seconds",
    )
    ws_ping_timeout_seconds: int = Field(
        default=10,
        ge=2,
        description="WebSocket ping response timeout in seconds",
    )
    backpressure_drop_strategy: str = Field(
        default="drop_oldest",
        description="Backpressure policy when audio queues are full: 'drop_oldest' or 'reject'",
    )

    # Voice Engine Transport Configuration (Contract v1.0)
    voice_engine_ws_url: str = Field(
        default="ws://localhost:8000/ws/voice",
        validation_alias=AliasChoices(
            "TELEPHONY_VOICE_ENGINE_WS_URL", "VOICE_ENGINE_WS_URL"
        ),
        description="WebSocket URL for downstream Voice Engine (e.g. ws://localhost:8000/ws/voice or wss://voice-test.gentechs.in/ws/voice)",
    )
    voice_engine_sample_rate: int = Field(
        default=16000,
        validation_alias=AliasChoices(
            "TELEPHONY_VOICE_ENGINE_SAMPLE_RATE", "VOICE_ENGINE_SAMPLE_RATE"
        ),
        description="Target client sample rate for Voice Engine audio streaming (16000 or 8000)",
    )
    voice_engine_connect_timeout_seconds: float = Field(
        default=5.0,
        ge=0.5,
        le=30.0,
        description="Timeout in seconds for establishing WebSocket connection with Voice Engine",
    )
    voice_engine_init_timeout_seconds: float = Field(
        default=5.0,
        ge=0.5,
        le=30.0,
        description="Timeout in seconds to wait for session.ready from Voice Engine after session.start",
    )
    voice_engine_enabled: bool = Field(
        default=True,
        description="Whether Voice Engine integration is active (can be disabled for mock testing)",
    )

    # Exotel Telecom Carrier Configuration
    exotel_account_sid: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TELEPHONY_EXOTEL_ACCOUNT_SID", "EXOTEL_ACCOUNT_SID"
        ),
        description="Exotel Account SID",
    )
    exotel_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "TELEPHONY_EXOTEL_API_KEY", "EXOTEL_API_KEY"
        ),
        description="Exotel API Key for authentication",
    )
    exotel_api_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "TELEPHONY_EXOTEL_API_TOKEN", "EXOTEL_API_TOKEN"
        ),
        description="Exotel API Token for authentication",
    )
    exotel_base_url: str = Field(
        default="https://api.in.exotel.com",
        validation_alias=AliasChoices(
            "TELEPHONY_EXOTEL_BASE_URL", "EXOTEL_BASE_URL"
        ),
        description="Exotel REST API Base URL",
    )
    exotel_exophone: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TELEPHONY_EXOTEL_EXOPHONE", "EXOTEL_EXOPHONE"
        ),
        description="Assigned Exotel virtual number / ExoPhone",
    )

    # Operational / Environment Settings
    environment: str = Field(
        default="development",
        description="Application environment (development, staging, production)",
    )
    default_country_code: str = Field(
        default="+91",
        description="Default country dialing prefix (India +91)",
    )
    gateway_public_host: str = Field(
        default="gateway.gentechs.in",
        validation_alias=AliasChoices(
            "GATEWAY_PUBLIC_HOST", "PUBLIC_HOST", "TELEPHONY_GATEWAY_PUBLIC_HOST"
        ),
        description="Public hostname or domain for the Voice Gateway",
    )
    gateway_public_ws_scheme: str = Field(
        default="wss",
        validation_alias=AliasChoices(
            "GATEWAY_PUBLIC_WS_SCHEME", "TELEPHONY_GATEWAY_PUBLIC_WS_SCHEME"
        ),
        description="Public WebSocket scheme (wss or ws)",
    )

    @property
    def is_exotel_configured(self) -> bool:
        """Check whether all required Exotel carrier settings are present and non-empty."""
        return bool(
            self.exotel_account_sid.strip()
            and self.exotel_api_key.get_secret_value().strip()
            and self.exotel_api_token.get_secret_value().strip()
            and self.exotel_exophone.strip()
        )

    def get_exotel_status_report(self) -> dict[str, str]:
        """Return safe status dictionary of Exotel configuration without secrets."""
        has_key = bool(self.exotel_api_key.get_secret_value().strip())
        has_token = bool(self.exotel_api_token.get_secret_value().strip())
        return {
            "exotel_configuration": "configured" if self.is_exotel_configured else "missing",
            "exotel_account": "configured" if bool(self.exotel_account_sid.strip()) else "missing",
            "exotel_api_credentials": "configured" if (has_key and has_token) else "missing",
            "exotel_exophone": "configured" if bool(self.exotel_exophone.strip()) else "missing",
            "exotel_base_url": self.exotel_base_url,
        }


@lru_cache
def get_telephony_settings() -> TelephonySettings:
    """Return a cached instance of the telephony configuration."""
    return TelephonySettings()
