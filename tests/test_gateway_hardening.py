"""Comprehensive unit tests for Phase 3 Gateway Hardening and Production Reliability."""

import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from backend.app.services.telephony.config import TelephonySettings
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.frames import (
    FrameType,
    InternalAudioMessage,
)
from backend.app.services.telephony.limiter import GatewayRateLimiter
from backend.app.services.telephony.logging import sanitize_dict, sanitize_value
from backend.app.services.telephony.metrics import GatewayMetrics
from backend.app.services.telephony.realtime_session import RealtimeVoiceSession
from backend.app.services.telephony.session_manager import RealtimeSessionManager


def test_error_classification() -> None:
    """Test error codes and dictionary representations."""
    err = GatewayError(
        code=GatewayErrorCode.OVERSIZED_PAYLOAD,
        message="Payload too large",
        details={"size": 150000},
    )
    d = err.to_dict()
    assert d["error_code"] == "OVERSIZED_PAYLOAD"
    assert d["message"] == "Payload too large"
    assert d["details"]["size"] == 150000


def test_metrics_collection() -> None:
    """Test GatewayMetrics increments and snapshot state."""
    metrics = GatewayMetrics()
    metrics.reset()

    metrics.record_session_created()
    metrics.record_frame_received(byte_count=320)
    metrics.record_frame_sent(byte_count=320)
    metrics.record_frame_dropped()
    metrics.record_interruption()
    metrics.record_rate_limited()
    metrics.record_heartbeat_timeout()
    metrics.record_session_closed()

    snap = metrics.get_snapshot()
    assert snap["sessions_created"] == 1
    assert snap["sessions_closed"] == 1
    assert snap["active_sessions"] == 0
    assert snap["frames_received"] == 1
    assert snap["frames_sent"] == 1
    assert snap["frames_dropped"] == 1
    assert snap["interruptions"] == 1
    assert snap["rate_limited_connections"] == 1
    assert snap["heartbeat_timeouts"] == 1
    assert snap["bytes_received"] == 320
    assert snap["bytes_sent"] == 320


def test_rate_limiter_sliding_window() -> None:
    """Test GatewayRateLimiter blocks requests exceeding window threshold."""
    limiter = GatewayRateLimiter(max_connections_per_window=3, window_seconds=60)
    client_ip = "192.168.1.100"

    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True
    # 4th request in window should be rejected
    assert limiter.is_allowed(client_ip) is False

    # Another IP is unaffected
    assert limiter.is_allowed("192.168.1.101") is True


def test_structured_logging_sanitizes_secrets(caplog: pytest.LogCaptureFixture) -> None:
    """Test that sensitive tokens and keys are redacted in logging utilities."""
    secret_data = {
        "api_key": "secret_key_value_12345",
        "webhook_secret": "my_hmac_secret",
        "auth_token": "token_abc_xyz",
        "payload_b64": "SGVsbG8gV29ybGQ=",
        "safe_field": "public_data",
    }

    sanitized = sanitize_dict(secret_data)
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["webhook_secret"] == "[REDACTED]"
    assert sanitized["auth_token"] == "[REDACTED]"
    assert sanitized["payload_b64"] == "[REDACTED]"
    assert sanitized["safe_field"] == "public_data"

    # Test binary data masking
    binary_val = sanitize_value("audio", b"1234567890")
    assert binary_val == "[BINARY_DATA: 10 bytes]"


def test_oversized_message_rejection() -> None:
    """Test that messages exceeding max_message_size_bytes are rejected."""
    huge_text = "a" * 200000
    with pytest.raises(GatewayError) as exc_info:
        InternalAudioMessage.from_raw_input(huge_text, max_message_size=1000)
    assert exc_info.value.code == GatewayErrorCode.OVERSIZED_PAYLOAD


def test_oversized_audio_frame_rejection() -> None:
    """Test that audio frames exceeding max_audio_frame_size_bytes are rejected."""
    huge_audio = b"\x00" * 100000
    b64_huge = base64.b64encode(huge_audio).decode("ascii")
    msg = InternalAudioMessage(type=FrameType.AUDIO, payload_b64=b64_huge)

    with pytest.raises(GatewayError) as exc_info:
        msg.to_audio_frame(max_frame_size_bytes=50000)
    assert exc_info.value.code == GatewayErrorCode.OVERSIZED_PAYLOAD


def test_malformed_base64_rejection() -> None:
    """Test that corrupted non-base64 strings are rejected with MALFORMED_MESSAGE."""
    msg = InternalAudioMessage(
        type=FrameType.AUDIO, payload_b64="!!!NOT_VALID_BASE64@@@"
    )
    with pytest.raises(GatewayError) as exc_info:
        msg.to_audio_frame()
    assert exc_info.value.code == GatewayErrorCode.MALFORMED_MESSAGE


@pytest.mark.asyncio
async def test_max_active_sessions_enforcement() -> None:
    """Test that exceeding max_active_sessions raises MAX_SESSIONS_EXCEEDED."""
    settings = TelephonySettings(max_active_sessions=2)
    manager = RealtimeSessionManager(settings=settings)

    await manager.create_session("sess_1")
    await manager.create_session("sess_2")

    with pytest.raises(GatewayError) as exc_info:
        await manager.create_session("sess_3")
    assert exc_info.value.code == GatewayErrorCode.MAX_SESSIONS_EXCEEDED


@pytest.mark.asyncio
async def test_session_expiration_boundaries() -> None:
    """Test is_expired checks for both idle and total session duration."""
    session = RealtimeVoiceSession(session_id="sess_exp")

    # Fresh session is not expired
    assert session.is_expired(max_idle_seconds=100, max_duration_seconds=500) is False

    # Force last_activity into the past
    session.last_activity_at = session.last_activity_at.replace(year=2020)
    assert session.is_expired(max_idle_seconds=100, max_duration_seconds=500) is True


@pytest.mark.asyncio
async def test_concurrent_cleanup_and_idempotence() -> None:
    """Test that multiple cleanup sweeps run concurrently without race conditions."""
    manager = RealtimeSessionManager()
    for i in range(10):
        await manager.create_session(f"sess_clean_{i}")

    # Run multiple cleanups simultaneously with 0s max idle
    tasks = [manager.cleanup_inactive_sessions(max_idle_seconds=0) for _ in range(5)]
    results = await asyncio.gather(*tasks)

    # First task prunes all 10, subsequent tasks find 0
    assert sum(results) == 10
    assert await manager.active_session_count() == 0


def test_readiness_endpoint(client: TestClient) -> None:
    """Test GET /ready endpoint returns 200 OK with active session count."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["service"] == "edu-voice-ai-backend"
    assert "active_sessions" in data


def test_metrics_endpoint(client: TestClient) -> None:
    """Test GET /metrics returns JSON dictionary of gateway counters."""
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "sessions_created" in data
    assert "frames_received" in data
    assert "active_sessions" in data
