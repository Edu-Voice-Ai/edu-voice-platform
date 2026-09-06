import pytest
import json
import base64
from starlette.testclient import TestClient
from app.main import app

def test_generic_session_lifecycle():
    """Verify that generic /ws/voice session lifecycle works with no telephony/outbound assumptions."""
    client = TestClient(app)
    
    with client.websocket_connect("/ws/voice") as ws:
        # 1. Start a generic session
        session_id = "sess-generic-test-01"
        call_id = "call-generic-test-01"
        start_payload = {
            "event": "session.start",
            "session_id": session_id,
            "call_id": call_id,
            "organization_id": "org-apex-01",
            "agent_id": "agent-maya-01",
            "language": "en-IN",
            "client_sample_rate": 16000,
            "template_type": "education",
            "business_name": "Apex University",
            "agent_name": "Maya"
        }
        ws.send_text(json.dumps(start_payload))
        
        # 2. Expect session.ready
        ready_raw = ws.receive_text()
        ready_evt = json.loads(ready_raw)
        assert ready_evt["event"] == "session.ready"
        assert ready_evt["session_id"] == session_id
        assert ready_evt["status"] == "ready"
        
        # 3. Stream audio input (PCM16 20ms binary frame)
        silent_frame = b"\x00" * 640
        ws.send_bytes(silent_frame)
        
        # Stream JSON base64 audio.input
        b64_data = base64.b64encode(silent_frame).decode("utf-8")
        ws.send_text(json.dumps({
            "event": "audio.input",
            "data": b64_data,
            "seq": 0
        }))
        
        # 4. End session
        ws.send_text(json.dumps({"event": "session.end"}))
        
        # 5. Capture post-call events
        events_received = []
        while True:
            try:
                msg = ws.receive_text()
                evt = json.loads(msg)
                events_received.append(evt)
                if evt.get("event") == "call.summary":
                    break
            except Exception:
                break
                
        event_types = [e.get("event") for e in events_received]
        assert "lead.extracted" in event_types, f"Expected lead.extracted in {event_types}"
        assert "call.summary" in event_types, f"Expected call.summary in {event_types}"
        
        # Verify that unapproved outbound fields are NOT present
        for evt in events_received:
            assert "campaign_id" not in evt, f"campaign_id found in {evt}"
            assert "contact_id" not in evt, f"contact_id found in {evt}"
            assert "call_direction" not in evt, f"call_direction found in {evt}"
            
        print("Generic session lifecycle verified cleanly!")
