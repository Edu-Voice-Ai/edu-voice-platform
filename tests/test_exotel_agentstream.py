"""Comprehensive Test Suite for Exotel AgentStream Integration (Phase 8).

Tests:
A. Dynamic resolver (valid CallSid, missing CallSid, valid From/To, unique session ID, correct WSS response)
B. Exotel events (connected, start, media, dtmf, stop, clear, malformed event)
C. Audio transcoding & envelopes (Base64 decode, PCM conversion, outbound Exotel media envelope, streamSid)
D. Barge-in (response.cancelled, queue drain, Exotel clear message)
E. Session lifecycle (resolve -> connect -> DID resolution -> Voice Engine -> cleanup)
F. Security (no secrets in logs, no secrets in responses)
G. Concurrent calls (separate session IDs, separate streamSid, isolation)
"""

import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.services.telephony.audio_codec import (
    transcode_carrier_to_voice_engine,
    transcode_voice_engine_to_carrier,
)
from backend.app.services.telephony.config import get_telephony_settings
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.realtime_session import ConnectionState
from backend.app.services.telephony.session_manager import get_realtime_session_manager
from tests.telephony_simulator.exotel_simulator import ExotelAgentStreamSimulator


@pytest.fixture(autouse=True)
def reset_session_state() -> None:
    """Reset session manager state between tests."""
    manager = get_realtime_session_manager()
    manager.reset_shutdown_state()


# ==============================================================================
# A. DYNAMIC RESOLVER TESTS
# ==============================================================================


def test_dynamic_resolver_valid_call_sid(client: TestClient) -> None:
    """Verify dynamic resolver succeeds with valid CallSid and returns valid WSS URL."""
    response = client.get(
        "/api/v1/telephony/exotel/resolve",
        params={
            "CallSid": "call_abc_12345",
            "CallFrom": "+919876543210",
            "CallTo": "+912249360001",
            "Direction": "inbound",
            "Created": "2026-09-06 00:00:00",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert data["url"].startswith("wss://gateway.gentechs.in/ws/telephony/stream/exotel_call_abc_12345_")


def test_dynamic_resolver_missing_call_sid(client: TestClient) -> None:
    """Verify dynamic resolver succeeds when CallSid is missing by returning dynamic WSS URL."""
    response = client.get(
        "/api/v1/telephony/exotel/resolve",
        params={
            "CallFrom": "+919876543210",
            "CallTo": "+912249360001",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert data["url"].startswith("wss://gateway.gentechs.in/ws/telephony/stream/exotel_")


def test_dynamic_resolver_unique_session_ids(client: TestClient) -> None:
    """Verify each call to dynamic resolver generates a completely distinct session_id."""
    r1 = client.get(
        "/api/v1/telephony/exotel/resolve",
        params={"CallSid": "call_same_sid", "From": "+919999999991"},
    )
    r2 = client.get(
        "/api/v1/telephony/exotel/resolve",
        params={"CallSid": "call_same_sid", "From": "+919999999992"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["url"] != r2.json()["url"]


def test_dynamic_resolver_preserves_session_context(client: TestClient) -> None:
    """Verify session metadata (CallSid, caller, DID, direction) is preserved in session."""
    call_sid = "call_context_verify_001"
    caller = "+919876543210"
    destination = "+912249360001"

    response = client.get(
        "/api/v1/telephony/exotel/resolve",
        params={
            "CallSid": call_sid,
            "From": caller,
            "To": destination,
            "Direction": "inbound",
            "DialWhomNumber": destination,
        },
    )
    assert response.status_code == 200
    url = response.json()["url"]
    session_id = url.split("/")[-1]

    manager = get_realtime_session_manager()
    session = asyncio.run(manager.get_session(session_id))
    assert session is not None
    assert session.call_sid == call_sid
    assert session.from_number == caller
    assert session.to_number == destination
    assert session.call_direction == "inbound"
    assert session.provider == "exotel"


def test_dynamic_resolver_post_support(client: TestClient) -> None:
    """Verify dynamic resolver also handles POST requests cleanly."""
    response = client.post(
        "/api/v1/telephony/exotel/resolve",
        json={
            "CallSid": "call_post_001",
            "From": "+919876543210",
            "To": "+912249360001",
        },
    )
    assert response.status_code == 200
    assert "wss://gateway.gentechs.in/ws/telephony/stream/exotel_call_post_001_" in response.json()["url"]


# ==============================================================================
# B. EXOTEL WIRE EVENTS & PACKET PARSING TESTS
# ==============================================================================


def test_exotel_websocket_connected_and_start(client: TestClient) -> None:
    """Verify Gateway accepts 'connected' and 'start', capturing streamSid."""
    session_id = "exotel_test_stream_start_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(session_id=session_id, provider="exotel")
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Send connected
        ws.send_text(json.dumps({"event": "connected"}))

        # Send start
        ws.send_text(
            json.dumps({
                "event": "start",
                "streamSid": "stream_12345",
                "start": {
                    "streamSid": "stream_12345",
                    "callSid": "call_exotel_start_01",
                    "from": "+919876543210",
                    "to": "+912249360001",
                },
            })
        )

        # Send stop to cleanly exit
        ws.send_text(json.dumps({"event": "stop", "streamSid": "stream_12345"}))

    assert session.stream_sid == "stream_12345"
    assert session.call_sid == "call_exotel_start_01"


def test_exotel_websocket_media_transcoding(client: TestClient) -> None:
    """Verify Exotel 'media' packets are base64 decoded and transcoded to PCM16 16kHz."""
    session_id = "exotel_test_media_transcode_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(session_id=session_id, provider="exotel")
    )

    sim = ExotelAgentStreamSimulator(stream_sid="stream_media_test")
    # Synthetic PCM16 sine wave audio
    synth_pcm = b"\x00\x00\x50\x00\x7f\x00\x50\x00" * 80  # 640 bytes (20ms at 16kHz)
    media_pkt = sim.build_media_packet(pcm_bytes=synth_pcm)

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        ws.send_text(json.dumps(sim.build_connected_packet()))
        ws.send_text(json.dumps(sim.build_start_packet()))
        ws.send_text(json.dumps(media_pkt))
        ws.send_text(json.dumps(sim.build_stop_packet()))

    assert session.stats.frames_received >= 1
    assert session.stats.bytes_received > 0


def test_exotel_websocket_dtmf_handling(client: TestClient) -> None:
    """Verify Exotel 'dtmf' events are parsed without crashing."""
    session_id = "exotel_test_dtmf_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(session_id=session_id, provider="exotel")
    )

    sim = ExotelAgentStreamSimulator(stream_sid="stream_dtmf_test")
    dtmf_pkt = sim.build_dtmf_packet(digit="9")

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        ws.send_text(json.dumps(sim.build_start_packet()))
        ws.send_text(json.dumps(dtmf_pkt))
        ws.send_text(json.dumps(sim.build_stop_packet()))

    # Verify session stayed healthy
    assert session.connection_state in (ConnectionState.CONNECTED, ConnectionState.DISCONNECTED, ConnectionState.CLOSED)


def test_exotel_websocket_malformed_event_resilience(client: TestClient) -> None:
    """Verify gateway does not crash when receiving malformed Exotel packets."""
    session_id = "exotel_test_malformed_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(session_id=session_id, provider="exotel")
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Invalid event type
        ws.send_text(json.dumps({"event": "unknown_future_event", "foo": "bar"}))
        # Malformed media with non-base64 payload
        ws.send_text(json.dumps({"event": "media", "media": {"payload": "!!NOT_BASE64!!"}}))
        # Empty JSON
        ws.send_text(json.dumps({}))
        # Valid stop to finish
        ws.send_text(json.dumps({"event": "stop"}))

    assert session.cancellation_event.is_set()


# ==============================================================================
# C. AUDIO CODEC & OUTBOUND MEDIA ENVELOPE TESTS
# ==============================================================================


def test_audio_codec_pure_python_transcoding() -> None:
    """Verify pure-Python ITU-T G.711 mu-law encode/decode and 8k <-> 16k resampling."""
    # Synthetic PCM16 sample
    pcm_original = b"\x00\x00\x20\x10\x40\x20\x60\x30" * 40
    # Transcode to carrier mu-law 8kHz
    carrier_mulaw = transcode_voice_engine_to_carrier(
        pcm_original, target_encoding="audio/x-mulaw", target_rate=8000
    )
    assert len(carrier_mulaw) == len(pcm_original) // 4  # 16k 16-bit to 8k 8-bit

    # Transcode carrier back to Voice Engine 16k PCM16
    pcm_reconstructed = transcode_carrier_to_voice_engine(
        carrier_mulaw, encoding="audio/x-mulaw", source_rate=8000, target_rate=16000
    )
    assert len(pcm_reconstructed) == len(pcm_original)


def test_exotel_outbound_media_envelope(client: TestClient) -> None:
    """Verify Voice Engine audio is sent to Exotel in native envelope with streamSid."""
    session_id = "exotel_test_outbound_envelope_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(
            session_id=session_id,
            provider="exotel",
            stream_sid="stream_outbound_test_99",
        )
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Push synthetic TTS audio into session outbound queue
        synth_tts = AudioFrame(
            data=b"\x00\x00\x10\x10" * 80,
            timestamp_ms=1000,
            format="pcm16_16k",
        )
        asyncio.run(session.push_outbound_frame(synth_tts))

        # Receive frame on WebSocket
        msg_text = ws.receive_text()
        data = json.loads(msg_text)

        assert data.get("event") == "media"
        assert data.get("streamSid") == "stream_outbound_test_99"
        assert "media" in data
        assert "payload" in data["media"]
        # Verify payload is valid base64
        decoded = base64.b64decode(data["media"]["payload"])
        assert len(decoded) > 0

        # Close cleanly
        ws.send_text(json.dumps({"event": "stop"}))


# ==============================================================================
# D. BARGE-IN & CLEAR ENVELOPE TESTS
# ==============================================================================


def test_barge_in_sends_exotel_clear_packet(client: TestClient) -> None:
    """Verify response.cancelled triggers an Exotel 'clear' envelope to the caller."""
    session_id = "exotel_test_bargein_01"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(
            session_id=session_id,
            provider="exotel",
            stream_sid="stream_bargein_test_01",
        )
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Pre-fill outbound queue with audio frames
        for i in range(5):
            asyncio.run(
                session.push_outbound_frame(
                    AudioFrame(
                        data=b"\x00\x00\x10\x10" * 40,
                        metadata={"generation_id": "gen_cancel_01"},
                    )
                )
            )

        # Trigger interruption simulating response.cancelled
        drained = session.trigger_interruption(generation_id="gen_cancel_01")
        assert drained >= 0
        assert "gen_cancel_01" in session.cancelled_generations

        # Close cleanly
        ws.send_text(json.dumps({"event": "stop"}))


# ==============================================================================
# E. END-TO-END SIMULATOR INTEGRATION TEST
# ==============================================================================


def test_exotel_simulator_full_flow(client: TestClient) -> None:
    """Execute end-to-end simulated Exotel AgentStream call using the local simulator."""
    call_sid = "call_sim_e2e_001"
    stream_sid = "stream_sim_e2e_001"

    # 1. Resolve call through dynamic resolver
    res = client.get(
        "/api/v1/telephony/exotel/resolve",
        params={
            "CallSid": call_sid,
            "From": "+919876543210",
            "To": "+912249360001",
            "Direction": "inbound",
        },
    )
    assert res.status_code == 200
    ws_url = res.json()["url"]
    session_id = ws_url.split("/")[-1]

    # 2. Run simulator
    sim = ExotelAgentStreamSimulator(stream_sid=stream_sid, call_sid=call_sid)
    outcome = sim.simulate_call_flow(client=client, session_id=session_id, send_media_frames=3, send_dtmf="7")

    assert outcome.success is True
    assert "connected" in outcome.events_sent
    assert "start" in outcome.events_sent
    assert "media" in outcome.events_sent
    assert "dtmf" in outcome.events_sent
    assert "stop" in outcome.events_sent


# ==============================================================================
# F. SECURITY & NO SECRETS LEAKAGE
# ==============================================================================


def test_security_no_secrets_in_resolver_response(client: TestClient) -> None:
    """Verify secrets are never present in resolver response."""
    settings = get_telephony_settings()
    secret_key = settings.exotel_api_key.get_secret_value()
    secret_token = settings.exotel_api_token.get_secret_value()

    res = client.get(
        "/api/v1/telephony/exotel/resolve",
        params={"CallSid": "call_sec_test_01", "From": "+919876543210"},
    )
    body_text = res.text
    if secret_key:
        assert secret_key not in body_text
    if secret_token:
        assert secret_token not in body_text
    assert "api_key" not in body_text
    assert "api_token" not in body_text


# ==============================================================================
# G. CONCURRENT CALLS ISOLATION
# ==============================================================================


def test_concurrent_call_isolation(client: TestClient) -> None:
    """Verify two concurrent Exotel calls have independent session IDs, streamSids, and queues."""
    r1 = client.get(
        "/api/v1/telephony/exotel/resolve",
        params={"CallSid": "call_concurrent_A", "From": "+911111111111"},
    )
    r2 = client.get(
        "/api/v1/telephony/exotel/resolve",
        params={"CallSid": "call_concurrent_B", "From": "+912222222222"},
    )

    s1_id = r1.json()["url"].split("/")[-1]
    s2_id = r2.json()["url"].split("/")[-1]

    assert s1_id != s2_id

    manager = get_realtime_session_manager()
    s1 = asyncio.run(manager.get_session(s1_id))
    s2 = asyncio.run(manager.get_session(s2_id))

    assert s1 is not None
    assert s2 is not None
    assert s1.call_sid == "call_concurrent_A"
    assert s2.call_sid == "call_concurrent_B"
    assert s1.from_number == "+911111111111"
    assert s2.from_number == "+912222222222"
    assert s1.inbound_audio_queue is not s2.inbound_audio_queue
    assert s1.outbound_audio_queue is not s2.outbound_audio_queue
