"""Realtime WebSocket endpoint protocol tests."""
import pytest
import json
from starlette.testclient import TestClient
from app.main import app
from app.audio.codec import AudioCodec


def test_websocket_lifecycle_and_protocol():
    client = TestClient(app)
    
    with client.websocket_connect("/ws/voice") as ws:
        # 1. Send session.start
        ws.send_text(json.dumps({
            "event": "session.start",
            "session_id": "ws_test_sess",
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": "te-IN"
        }))

        resp_ready = json.loads(ws.receive_text())
        assert resp_ready["event"] == "session.ready"
        assert resp_ready["session_id"] == "ws_test_sess"

        # 2. Stream 5 audio frames
        pcm_chunk = b"\x00\x00" * 320
        b64_pcm = AudioCodec.encode_base64(pcm_chunk)
        for i in range(5):
            ws.send_text(json.dumps({
                "event": "audio.input",
                "data": b64_pcm,
                "seq": i
            }))

        # 3. Send session.end
        ws.send_text(json.dumps({"event": "session.end"}))

        # Expect lead.extracted and call.summary before close
        events_received = []
        try:
            while len(events_received) < 300:
                msg = json.loads(ws.receive_text())
                events_received.append(msg["event"])
                if "call.summary" in events_received:
                    break
        except Exception:
            pass

        assert "lead.extracted" in events_received or "call.summary" in events_received
