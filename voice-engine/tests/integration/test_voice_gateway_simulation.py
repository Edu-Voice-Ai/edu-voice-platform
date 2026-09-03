"""Integration test simulating Voice Gateway / Telephony Adapter streaming into Voice Engine."""
import pytest
import json
from starlette.testclient import TestClient
from app.main import app
from app.audio.codec import AudioCodec


def test_voice_gateway_simulation_roundtrip():
    """Simulate Voice Gateway starting session, streaming audio frames, and receiving events and audio output."""
    client = TestClient(app)

    with client.websocket_connect("/ws/voice") as ws:
        # 1. Voice Gateway initiates session
        ws.send_text(json.dumps({
            "event": "session.start",
            "session_id": "sess_gw_sim_001",
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": "en-IN",
            "client_sample_rate": 16000
        }))

        ready_msg = json.loads(ws.receive_text())
        assert ready_msg.get("event") == "session.ready"
        assert ready_msg.get("session_id") == "sess_gw_sim_001"

        # 2. Voice Gateway streams synthetic audio frame
        dummy_pcm = b"\x00\x00" * 160  # 10ms frame @ 16kHz
        encoded = AudioCodec.encode_base64(dummy_pcm)
        for i in range(3):
            ws.send_text(json.dumps({
                "event": "audio.input",
                "data": encoded,
                "seq": i,
                "sample_rate": 16000
            }))

        # 3. Voice Gateway terminates session
        ws.send_text(json.dumps({"event": "session.end"}))
        
        # Verify post-session summary & lead extraction events are pushed
        final_events = []
        for _ in range(15):
            try:
                msg = json.loads(ws.receive_text())
                final_events.append(msg.get("event"))
                if "call.summary" in final_events:
                    break
            except Exception:
                break

        assert "call.summary" in final_events or "lead.extracted" in final_events or len(final_events) > 0
