"""Integration test suite verifying the Frozen Outbound Session Metadata Contract (Contract 5)."""
import pytest
import json
import time
from starlette.testclient import TestClient
from app.main import app
from app.audio.codec import AudioCodec
from app.session.manager import get_session_manager


def test_outbound_session_complete_metadata_lifecycle():
    """Verify outbound session accepts Contract 5 metadata, reflects call_id in session.ready,
    and returns full attribution in lead.extracted and call.summary."""
    client = TestClient(app)

    session_id = "sess_outbound_test_101"
    call_id = "call_outbound_uuid_555"
    org_id = "org_apex_univ"
    agent_id = "agent_admission"
    campaign_id = "camp_admissions_fall_2026"
    contact_id = "contact_student_789"
    direction = "outbound"

    with client.websocket_connect("/ws/voice") as ws:
        # 1. Start outbound session with frozen Contract 5 metadata
        ws.send_text(json.dumps({
            "event": "session.start",
            "session_id": session_id,
            "call_id": call_id,
            "organization_id": org_id,
            "agent_id": agent_id,
            "call_direction": direction,
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "language": "en-IN",
            "client_sample_rate": 16000,
            "template_type": "education",
            "business_name": "Apex University"
        }))

        # 2. Receive session.ready and verify call_id and session_id
        ready_msg = json.loads(ws.receive_text())
        assert ready_msg.get("event") == "session.ready"
        assert ready_msg.get("session_id") == session_id
        assert ready_msg.get("call_id") == call_id
        assert ready_msg.get("status") == "ready"

        # 3. Verify internal SessionState preserved all metadata
        manager = get_session_manager()
        session = manager._sessions.get(session_id)
        assert session is not None
        assert session.session_id == session_id
        assert session.call_id == call_id
        assert session.organization_id == org_id
        assert session.agent_id == agent_id
        assert session.call_direction == "outbound"
        assert session.campaign_id == campaign_id
        assert session.contact_id == contact_id

        # 4. Stream audio frame
        dummy_pcm = b"\x00\x00" * 320
        b64_audio = AudioCodec.encode_base64(dummy_pcm)
        ws.send_text(json.dumps({
            "event": "audio.input",
            "data": b64_audio,
            "seq": 1
        }))

        # 5. End session
        ws.send_text(json.dumps({"event": "session.end"}))

        # 6. Receive post-session events and verify attribution
        events_by_type = {}
        for _ in range(30):
            try:
                msg = json.loads(ws.receive_text())
                ev = msg.get("event")
                events_by_type[ev] = msg
                if "call.summary" in events_by_type and "lead.extracted" in events_by_type:
                    break
            except Exception:
                break

        assert "lead.extracted" in events_by_type, f"Expected lead.extracted, got: {list(events_by_type.keys())}"
        lead_ev = events_by_type["lead.extracted"]
        assert lead_ev.get("session_id") == session_id
        assert lead_ev.get("call_id") == call_id
        assert lead_ev.get("organization_id") == org_id
        assert lead_ev.get("agent_id") == agent_id
        assert lead_ev.get("call_direction") == "outbound"
        assert lead_ev.get("campaign_id") == campaign_id
        assert lead_ev.get("contact_id") == contact_id
        assert "lead" in lead_ev

        assert "call.summary" in events_by_type, f"Expected call.summary, got: {list(events_by_type.keys())}"
        summary_ev = events_by_type["call.summary"]
        assert summary_ev.get("session_id") == session_id
        assert summary_ev.get("call_id") == call_id
        assert summary_ev.get("organization_id") == org_id
        assert summary_ev.get("agent_id") == agent_id
        assert summary_ev.get("call_direction") == "outbound"
        assert summary_ev.get("campaign_id") == campaign_id
        assert summary_ev.get("contact_id") == contact_id
        assert "summary" in summary_ev


def test_inbound_session_backward_compatibility_defaults():
    """Verify that existing inbound callers who omit call_direction, campaign_id, contact_id, call_id
    default safely to call_direction='inbound' without error."""
    client = TestClient(app)
    session_id = "sess_inbound_compat_202"

    with client.websocket_connect("/ws/voice") as ws:
        # Standard inbound session.start without outbound-specific fields
        ws.send_text(json.dumps({
            "event": "session.start",
            "session_id": session_id,
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": "te-IN"
        }))

        ready_msg = json.loads(ws.receive_text())
        assert ready_msg.get("event") == "session.ready"
        assert ready_msg.get("session_id") == session_id
        assert ready_msg.get("call_id") is None

        # Verify default state
        manager = get_session_manager()
        session = manager._sessions.get(session_id)
        assert session is not None
        assert session.call_direction == "inbound"
        assert session.campaign_id is None
        assert session.contact_id is None
        assert session.call_id is None

        # End session
        ws.send_text(json.dumps({"event": "session.end"}))

        events_by_type = {}
        for _ in range(30):
            try:
                msg = json.loads(ws.receive_text())
                ev = msg.get("event")
                events_by_type[ev] = msg
                if "call.summary" in events_by_type and "lead.extracted" in events_by_type:
                    break
            except Exception:
                break

        assert "lead.extracted" in events_by_type
        assert events_by_type["lead.extracted"]["call_direction"] == "inbound"
        assert events_by_type["lead.extracted"]["call_id"] is None
        assert events_by_type["lead.extracted"]["campaign_id"] is None

        assert "call.summary" in events_by_type
        assert events_by_type["call.summary"]["call_direction"] == "inbound"
        assert events_by_type["call.summary"]["call_id"] is None
        assert events_by_type["call.summary"]["campaign_id"] is None


def test_outbound_session_attribution_preserved_across_cancellation():
    """Verify that when an outbound call experiences barge-in / cancellation cycles,
    the session attribution metadata (call_id, direction, campaign, contact) is never cleared or lost."""
    client = TestClient(app)
    session_id = "sess_outbound_barge_303"
    call_id = "call_barge_uuid_777"

    with client.websocket_connect("/ws/voice") as ws:
        ws.send_text(json.dumps({
            "event": "session.start",
            "session_id": session_id,
            "call_id": call_id,
            "organization_id": "org_healthcare",
            "agent_id": "agent_renewal",
            "call_direction": "outbound",
            "campaign_id": "camp_health_renew_q3",
            "contact_id": "contact_patient_123",
            "template_type": "healthcare_renewal"
        }))

        ready_msg = json.loads(ws.receive_text())
        assert ready_msg.get("status") == "ready"

        manager = get_session_manager()
        session = manager._sessions.get(session_id)
        assert session is not None

        # Simulate barge-in / cancellation on session
        session.invalidate_active_generation(reason="Caller interrupted during outbound pitch")

        # Confirm attribution is preserved after cancellation
        assert session.call_id == call_id
        assert session.call_direction == "outbound"
        assert session.campaign_id == "camp_health_renew_q3"
        assert session.contact_id == "contact_patient_123"

        # End session
        ws.send_text(json.dumps({"event": "session.end"}))

        events_by_type = {}
        for _ in range(30):
            try:
                msg = json.loads(ws.receive_text())
                events_by_type[msg.get("event")] = msg
                if "call.summary" in events_by_type:
                    break
            except Exception:
                break

        if "call.summary" in events_by_type:
            summary_msg = events_by_type["call.summary"]
            assert summary_msg.get("call_id") == call_id
            assert summary_msg.get("call_direction") == "outbound"
            assert summary_msg.get("campaign_id") == "camp_health_renew_q3"
            assert summary_msg.get("contact_id") == "contact_patient_123"
