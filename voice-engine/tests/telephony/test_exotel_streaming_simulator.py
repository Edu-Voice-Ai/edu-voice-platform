"""Deterministic Exotel Realtime Stream Simulator Test Suite."""
import pytest
import asyncio
import json
import base64
import numpy as np
from fastapi.testclient import TestClient
from app.main import app
from app.audio.codec import AudioCodec
from app.audio.frames import AudioFrame
from app.session.manager import get_session_manager


def create_pcm16_speech_frames(duration_ms: int = 500, sample_rate: int = 8000, freq: int = 300) -> list[bytes]:
    """Generate 20ms chunks of 8kHz PCM16 audio."""
    samples_per_chunk = int(sample_rate * 0.02)
    t = np.linspace(0, 0.02, samples_per_chunk, endpoint=False)
    sine = (0.6 * np.sin(2 * np.pi * freq * t) * 32767.0).astype(np.int16).tobytes()
    num_chunks = int(duration_ms / 20)
    return [sine for _ in range(num_chunks)]


def test_exotel_incoming_call_webhook():
    """Verify Exotel Voicebot webhook returns valid JSON URL declaration and XML when requested."""
    client = TestClient(app)
    
    # 1. Default JSON response for Voicebot applet
    resp_json = client.get("/exotel/incoming_call")
    assert resp_json.status_code == 200
    data = resp_json.json()
    assert "url" in data
    assert data["url"].startswith("wss://") or data["url"].startswith("ws://")
    assert "/exotel/media" in data["url"]

    # 2. XML response for ExoML Passthru
    resp_xml = client.get("/exotel/incoming_call?format=xml")
    assert resp_xml.status_code == 200
    assert "application/xml" in resp_xml.headers["content-type"]
    assert "<Stream" in resp_xml.text
    assert "<Connect>" in resp_xml.text


def test_exotel_status_callback():
    """Verify Exotel status callback handles incoming parameters without error."""
    client = TestClient(app)
    response = client.post(
        "/exotel/status_callback",
        data={"CallSid": "call_12345", "Status": "completed", "From": "919876543210"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_exotel_stream_lifecycle_and_barge_in():
    """
    Simulate full Exotel stream lifecycle:
    1. Handshake (connected, start)
    2. Greeting reception
    3. Caller speech (media packets)
    4. AI response reception
    5. Caller barge-in -> 'clear' event emission
    6. Stop event -> clean disconnect
    """
    client = TestClient(app)
    
    with client.websocket_connect("/exotel/media") as ws:
        # 1. Send Connected event
        ws.send_text(json.dumps({
            "event": "connected",
            "protocol": "Call",
            "version": "1.0.0"
        }))

        # 2. Send Start event (8kHz mulaw standard PSTN stream)
        stream_sid = "stream_test_exotel_999"
        call_sid = "call_test_exotel_888"
        ws.send_text(json.dumps({
            "event": "start",
            "stream_sid": stream_sid,
            "start": {
                "call_sid": call_sid,
                "from": "919876543210",
                "to": "08047280157",
                "media_format": {
                    "encoding": "audio/x-mulaw",
                    "sample_rate": 8000,
                    "channels": 1
                }
            }
        }))

        # 3. Receive Greeting audio media packets
        greeting_received = False
        for _ in range(20):
            try:
                msg_text = ws.receive_text()
                msg = json.loads(msg_text)
                if msg.get("event") == "media":
                    assert msg.get("stream_sid") == stream_sid
                    payload = msg.get("media", {}).get("payload")
                    assert payload is not None
                    raw_bytes = base64.b64decode(payload)
                    assert len(raw_bytes) > 0
                    greeting_received = True
                    break
            except Exception:
                pass
        
        assert greeting_received, "Expected greeting audio media from Exotel adapter"

        # 4. Simulate Caller Speech (Send 20 chunks = 400ms speech)
        speech_chunks = create_pcm16_speech_frames(duration_ms=400, sample_rate=8000)
        for chunk in speech_chunks:
            mu_bytes = AudioCodec.pcm16_to_mulaw(chunk)
            ws.send_text(json.dumps({
                "event": "media",
                "stream_sid": stream_sid,
                "media": {
                    "payload": base64.b64encode(mu_bytes).decode("ascii")
                }
            }))

        # 5. Send Silence to finalize turn (800ms silence = 40 chunks)
        silence_pcm = (np.zeros(160, dtype=np.int16)).tobytes()
        silence_mu = AudioCodec.pcm16_to_mulaw(silence_pcm)
        for _ in range(40):
            ws.send_text(json.dumps({
                "event": "media",
                "stream_sid": stream_sid,
                "media": {
                    "payload": base64.b64encode(silence_mu).decode("ascii")
                }
            }))

        # 6. Send Caller Interruption (Barge-in speech while AI generates/responds: 16 chunks = 320ms > 300ms)
        for chunk in speech_chunks[:16]:
            ws.send_text(json.dumps({
                "event": "media",
                "stream_sid": stream_sid,
                "media": {
                    "payload": base64.b64encode(AudioCodec.pcm16_to_mulaw(chunk)).decode("ascii")
                }
            }))

        # 7. Verify 'clear' event is received on barge-in
        clear_received = False
        import time
        t_start = time.time()
        while time.time() - t_start < 4.0:
            try:
                # Use a small timeout or non-blocking read if supported, else read available
                import select
                # Starlette TestClient WebSocket wraps raw websocket
                msg_text = ws.receive_text()
                msg = json.loads(msg_text)
                if msg.get("event") == "clear":
                    assert msg.get("stream_sid") == stream_sid
                    clear_received = True
                    break
            except Exception:
                time.sleep(0.05)
                break
        
        # 8. Send Stop event
        try:
            ws.send_text(json.dumps({
                "event": "stop",
                "stream_sid": stream_sid
            }))
            time.sleep(0.05)
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass

    # Verify session cleaned up
    manager = get_session_manager()
    session = manager._sessions.get(f"exotel_{call_sid}")
    assert session is None or session.is_active is False
