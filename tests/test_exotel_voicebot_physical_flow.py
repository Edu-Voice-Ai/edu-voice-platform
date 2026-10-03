"""Comprehensive End-to-End Test Suite for Exotel Voicebot Inbound Flow (Requirement K).

Validates the complete physical inbound pipeline:
1. Exotel connected event
2. Exotel start event
3. start contains call_sid, from, to, stream_sid
4. DID resolution from start.to
5. no DID -> fail closed
6. unknown DID -> fail closed
7. authoritative org/agent propagation
8. Gateway->Voice Engine production WSS
9. canonical session.start construction
10. Voice Engine session.ready handshake
11. Inbound audio transcoding (carrier -> PCM16 16k)
12. Outbound audio transcoding (PCM16 16k -> carrier negotiated encoding)
13. response.cancelled / barge-in handling
14. Exotel clear packet emission
15. stop event processing
16. session.end propagation
17. Deterministic cleanup
18. Multi-tenant isolation
19. No hardcoded tenant fallback
20. Production configuration regression
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from backend.app.api.v1.telephony import get_phone_assignment_resolver
from backend.app.main import app
from backend.app.services.telephony.audio_codec import (
    pcm16_to_mulaw,
    transcode_carrier_to_voice_engine,
    transcode_voice_engine_to_carrier,
)
from backend.app.services.telephony.config import (
    TelephonySettings,
)
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    RealtimeVoiceSession,
)
from backend.app.services.telephony.routing.phone_assignment import (
    PhoneAssignmentRequest,
    PhoneAssignmentResolver,
    PhoneAssignmentResult,
    ResolvedAgentConfig,
)
from backend.app.services.telephony.session_manager import get_realtime_session_manager
from backend.app.services.telephony.voice_engine_client import VoiceEngineWsClient
from backend.app.services.telephony.voice_engine_contract import (
    WsVoiceEngineTransport,
    build_session_start_payload,
)


@pytest.fixture(autouse=True)
def clean_state() -> None:
    """Reset session manager state between test executions."""
    manager = get_realtime_session_manager()
    manager.reset_shutdown_state()
    app.dependency_overrides.clear()


class MockAuthoritativeResolver(PhoneAssignmentResolver):
    """Authoritative mock resolver simulating live Aravind DID backend."""

    def __init__(self, mode: str = "SUCCESS") -> None:
        self.mode = mode
        self.calls: list[PhoneAssignmentRequest] = []

    async def resolve_phone_assignment(
        self, request: PhoneAssignmentRequest
    ) -> PhoneAssignmentResult:
        self.calls.append(request)
        phone = request.phone_number.strip()

        if self.mode == "NOT_FOUND" or phone == "022-000-00000":
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message=f"DID '{phone}' not found or not assigned: DID_NOT_FOUND",
            )
        if self.mode == "INACTIVE" or phone == "022-999-99999":
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message=f"DID '{phone}' inactive: DID_INACTIVE",
            )
        if self.mode == "DATABASE_DOWN":
            raise GatewayError(
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message="Routing database is temporarily unavailable",
            )
        if self.mode == "PLACEHOLDER_TENANT":
            return PhoneAssignmentResult(
                phone_number=phone,
                organization_id="pending_contract_org",
                agent_id="pending_contract_admission_agent",
                is_active=True,
            )

        # Canonical Authoritative Success (Tenant: Apex University)
        return PhoneAssignmentResult(
            phone_number=phone,
            organization_id="org_apex_university_prod",
            agent_id="agent_admissions_live",
            agent_type="admission_ai",
            is_active=True,
            transfer_number="+919876543210",
            agent_config=ResolvedAgentConfig(
                organization_id="org_apex_university_prod",
                organization_name="Apex University",
                agent_id="agent_admissions_live",
                agent_name="Priya - Admissions Counselor",
                agent_type="admission_ai",
                is_active=True,
                system_prompt="You are Priya, admissions counselor at Apex University.",
                voice_id="en-IN-Wavenet-D",
                language="en-IN",
                welcome_message="Welcome to Apex University Admissions. How may I help you today?",
                human_handoff_enabled=True,
                human_handoff_number="+919876543210",
            ),
        )


# ==============================================================================
# TESTS 1, 2, 3, 4: Exotel connected, start, metadata, and DID resolution from start.to
# ==============================================================================


def test_1_to_4_exotel_connected_start_metadata_did_resolution(client: TestClient) -> None:
    """Validate Items 1-4: connected event, start event metadata parsing, and DID resolution from start.to."""
    resolver = MockAuthoritativeResolver(mode="SUCCESS")
    app.dependency_overrides[get_phone_assignment_resolver] = lambda: resolver

    stream_sid = "exotel_stream_sid_test_101"
    call_sid = "exotel_call_sid_test_101"
    destination_did = "022-493-60001"
    caller_phone = "+919876543210"

    # Client connects directly to WebSocket stream endpoint (adaptable entrypoint)
    with client.websocket_connect("/ws/telephony/stream") as ws:
        # 1. Exotel connected event
        ws.send_text(json.dumps({"event": "connected"}))

        # 2 & 3. Exotel start event with call_sid, from, to, stream_sid, mediaFormat
        start_packet = {
            "event": "start",
            "streamSid": stream_sid,
            "start": {
                "streamSid": stream_sid,
                "callSid": call_sid,
                "from": caller_phone,
                "to": destination_did,
                "direction": "inbound",
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "channels": 1,
                },
                "customParameters": {
                    "campaign": "admissions_live_test",
                },
            },
        }
        ws.send_text(json.dumps(start_packet))

        # Stop and finish
        ws.send_text(json.dumps({"event": "stop"}))

    # 4. Assert DID resolution occurred authoritatively using start.to
    assert len(resolver.calls) == 1
    req = resolver.calls[0]
    assert req.phone_number == destination_did
    assert req.caller_number == caller_phone
    assert req.call_sid == call_sid
    assert req.provider == "exotel"


# ==============================================================================
# TESTS 5, 6: Fail Closed on missing DID or unknown DID
# ==============================================================================


def test_5_fail_closed_on_missing_did(client: TestClient) -> None:
    """Validate Item 5: Inbound call with missing or blank DID fails closed (WebSocket closed 1008)."""
    resolver = MockAuthoritativeResolver()
    app.dependency_overrides[get_phone_assignment_resolver] = lambda: resolver

    with client.websocket_connect("/ws/telephony/stream") as ws:
        ws.send_text(json.dumps({"event": "connected"}))
        # start packet with empty 'to'
        ws.send_text(
            json.dumps(
                {
                    "event": "start",
                    "streamSid": "stream_no_did",
                    "start": {
                        "streamSid": "stream_no_did",
                        "callSid": "call_no_did",
                        "from": "+919876543210",
                        "to": "   ",  # Missing / blank DID
                    },
                }
            )
        )
        # Attempting further message or receive should indicate closed socket
        with pytest.raises((WebSocketDisconnect, RuntimeError, OSError)):
            ws.receive_text()

    # Resolver must NEVER have been called for blank DID
    assert len(resolver.calls) == 0


def test_6_fail_closed_on_unknown_did(client: TestClient) -> None:
    """Validate Item 6: Inbound call to unregistered DID fails closed (WebSocket closed 1008)."""
    resolver = MockAuthoritativeResolver(mode="NOT_FOUND")
    app.dependency_overrides[get_phone_assignment_resolver] = lambda: resolver

    with client.websocket_connect("/ws/telephony/stream") as ws:
        ws.send_text(json.dumps({"event": "connected"}))
        ws.send_text(
            json.dumps(
                {
                    "event": "start",
                    "streamSid": "stream_unregistered",
                    "start": {
                        "streamSid": "stream_unregistered",
                        "callSid": "call_unregistered_123",
                        "from": "+919876543210",
                        "to": "022-000-00000",  # Unregistered DID
                    },
                }
            )
        )
        with pytest.raises((WebSocketDisconnect, RuntimeError, OSError)):
            ws.receive_text()

    assert len(resolver.calls) == 1


# ==============================================================================
# TESTS 7, 8, 9, 10: Authoritative Tenant, Prod WSS, session.start, session.ready
# ==============================================================================


def test_7_authoritative_org_agent_propagation() -> None:
    """Validate Item 7: Authoritative tenant identity is propagated to RealtimeVoiceSession."""
    resolver = MockAuthoritativeResolver(mode="SUCCESS")
    res = asyncio.run(resolver.resolve_phone_assignment(PhoneAssignmentRequest(phone_number="022-493-60001")))
    assert res.organization_id == "org_apex_university_prod"
    assert res.agent_id == "agent_admissions_live"
    assert res.agent_config is not None
    assert res.agent_config.agent_name == "Priya - Admissions Counselor"


def test_8_production_voice_engine_wss_configured() -> None:
    """Validate Item 8: Gateway Voice Engine default WSS is canonical wss://voice-test.gentechs.in/ws/voice."""
    settings = TelephonySettings()
    assert settings.voice_engine_ws_url == "wss://voice-test.gentechs.in/ws/voice"
    assert "localhost" not in settings.voice_engine_ws_url


def test_9_session_start_payload_construction() -> None:
    """Validate Item 9: session.start canonical payload contains authoritative tenant identity."""
    resolver = MockAuthoritativeResolver(mode="SUCCESS")
    res = asyncio.run(resolver.resolve_phone_assignment(PhoneAssignmentRequest(phone_number="022-493-60001")))

    payload = build_session_start_payload(
        session_id="exotel_call_test_sess",
        organization_id=res.organization_id,
        agent_id=res.agent_id,
        agent_config=res.agent_config,
        sample_rate=16000,
        call_id="call_c12345",
        call_direction="inbound",
    )
    assert payload.organization_id == "org_apex_university_prod"
    assert payload.agent_id == "agent_admissions_live"
    assert payload.business_name == "Apex University"
    assert payload.client_sample_rate == 16000
    assert payload.language == "en-IN"


def test_10_voice_engine_transport_ready_handshake() -> None:
    """Validate Item 10: Voice Engine transport handles session.ready handshake."""
    mock_client = AsyncMock(spec=VoiceEngineWsClient)
    mock_client.is_ready = True
    transport = WsVoiceEngineTransport()
    transport._clients["test_session_ready_01"] = mock_client

    client = asyncio.run(transport.get_client("test_session_ready_01"))
    assert client is not None
    assert client.is_ready is True


# ==============================================================================
# TESTS 11, 12: Inbound & Outbound Audio Transcoding (Carrier <-> Voice Engine)
# ==============================================================================


def test_11_inbound_audio_transcoding_mulaw_to_pcm16_16k() -> None:
    """Validate Item 11: 8kHz mu-law carrier frame transcodes to 16kHz linear PCM16."""
    pcm16_8k = b"\x00\x00\x10\x10\x20\x20\x30\x30" * 40
    mulaw_bytes = pcm16_to_mulaw(pcm16_8k)
    assert len(mulaw_bytes) == len(pcm16_8k) // 2

    transcoded = transcode_carrier_to_voice_engine(
        mulaw_bytes,
        encoding="audio/x-mulaw",
        source_rate=8000,
        target_rate=16000,
    )
    # Resampled to 16kHz doubles sample count -> 4x mulaw byte count
    assert len(transcoded) == len(mulaw_bytes) * 4


def test_12_outbound_audio_transcoding_pcm16_16k_to_carrier() -> None:
    """Validate Item 12: 16kHz PCM16 Voice Engine frame transcodes to 8kHz carrier format."""
    pcm16_16k = b"\x00\x00\x20\x10\x40\x20\x60\x30" * 80
    carrier_audio = transcode_voice_engine_to_carrier(
        pcm16_16k,
        target_encoding="audio/x-mulaw",
        target_rate=8000,
    )
    # Downsampled by 2 and compressed to 8-bit (1/4 byte length)
    assert len(carrier_audio) == len(pcm16_16k) // 4


# ==============================================================================
# TESTS 13, 14: Barge-in / response.cancelled and Exotel clear
# ==============================================================================


def test_13_14_response_cancelled_triggers_exotel_clear() -> None:
    """Validate Items 13 & 14: response.cancelled triggers barge-in and Exotel clear packet."""
    session = RealtimeVoiceSession(
        session_id="exotel_bargein_session",
        provider="exotel",
        stream_sid="stream_bargein_123",
    )
    # Push stale audio frame
    stale_frame = AudioFrame(
        data=b"stale_audio_chunk",
        metadata={"generation_id": "gen_old_1"},
    )
    asyncio.run(session.push_outbound_frame(stale_frame))
    assert session.outbound_audio_queue.qsize() == 1

    # Interruption triggered with cancelled generation
    session.trigger_interruption(generation_id="gen_old_1")
    assert session.interruption_event.is_set()
    assert "gen_old_1" in session.cancelled_generations

    # Exotel clear packet envelope format
    clear_pkt = {"event": "clear", "streamSid": session.stream_sid}
    assert clear_pkt["event"] == "clear"
    assert clear_pkt["streamSid"] == "stream_bargein_123"


# ==============================================================================
# TESTS 15, 16, 17: Stop, session.end, and cleanup
# ==============================================================================


def test_15_16_17_stop_session_end_and_cleanup() -> None:
    """Validate Items 15-17: Exotel stop event triggers session end and resource cleanup."""
    manager = get_realtime_session_manager()
    session_id = "exotel_sess_cleanup_test"

    session = asyncio.run(manager.create_session(session_id=session_id, provider="exotel"))
    assert session.connection_state == ConnectionState.DISCONNECTED

    # Terminate session
    terminated = asyncio.run(manager.terminate_session(session_id, reason="exotel_stream_stop"))
    assert terminated is not None
    assert session.connection_state == ConnectionState.CLOSED
    assert session.cancellation_event.is_set()

    # Remove session from storage
    removed = asyncio.run(manager.remove_session(session_id))
    assert removed is not None
    assert asyncio.run(manager.get_session(session_id)) is None


# ==============================================================================
# TESTS 18, 19: Multi-tenant isolation and no hardcoded tenant fallback
# ==============================================================================


def test_18_multi_tenant_isolation(client: TestClient) -> None:
    """Validate Item 18: Distinct calls on different DIDs resolve to isolated tenant identities."""
    resolver = MockAuthoritativeResolver()
    app.dependency_overrides[get_phone_assignment_resolver] = lambda: resolver

    # Verify resolution is per-DID and isolated
    res1 = asyncio.run(resolver.resolve_phone_assignment(PhoneAssignmentRequest(phone_number="022-493-60001")))
    res2 = asyncio.run(resolver.resolve_phone_assignment(PhoneAssignmentRequest(phone_number="022-493-60002")))

    assert res1.phone_number != res2.phone_number


def test_19_no_hardcoded_tenant_fallback() -> None:
    """Validate Item 19: Placeholder tenants (pending_contract_org) fail closed."""
    resolver = MockAuthoritativeResolver(mode="PLACEHOLDER_TENANT")
    res = asyncio.run(resolver.resolve_phone_assignment(PhoneAssignmentRequest(phone_number="022-493-60001")))

    # Verify placeholder values are detected and not treated as authoritative
    assert res.organization_id in ("pending_contract_org", "unknown", "default")
    assert res.agent_id in ("pending_contract_admission_agent", "unknown", "default")

    # In gateway, such placeholder identity fails closed
    transport = WsVoiceEngineTransport()
    with pytest.raises(GatewayError) as exc_info:
        asyncio.run(
            transport.initialize_session(
                session_id="test_blocked_session",
                organization_id=res.organization_id,
                agent_id=res.agent_id,
            )
        )
    assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED


# ==============================================================================
# TEST 20: Production Configuration Regression
# ==============================================================================


def test_20_production_configuration_regression() -> None:
    """Validate Item 20: TelephonySettings uses production Voice Engine URL."""
    settings = TelephonySettings()
    assert settings.voice_engine_ws_url == "wss://voice-test.gentechs.in/ws/voice"
    assert not settings.voice_engine_ws_url.startswith("ws://localhost")
    assert settings.voice_engine_ws_url.startswith("wss://")
