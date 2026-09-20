"""Integration test verifying Aravind Backend Contract compatibility with Lokesh Voice Engine.

Verifies:
1. Backend speech_config & handoff_config mapping in session.start
2. Primary language and welcome message resolution
3. Tenant security (missing organization_id / agent_id rejected)
4. Multi-tenant / multi-agent context isolation
5. Max call duration enforcement
6. Template preservation and multilingual support
"""
import pytest
import json
import base64
import time
from starlette.testclient import TestClient
from app.main import app
from app.session.state import SessionState
from app.session.manager import get_session_manager
from app.templates.registry import AgentTemplateRegistry


def test_backend_contract_session_start_mapping():
    """Verify that Yasin-forwarded Aravind Backend speech_config and handoff_config are parsed correctly."""
    client = TestClient(app)

    with client.websocket_connect("/ws/voice") as ws:
        sess_id = "backend-contract-test-01"
        call_id = "aravind-call-01"
        org_id = "org-aravind-uuid-1111"
        agent_id = "agent-admission-uuid-2222"

        # Contract payload exactly as provided by Aravind DID resolution through Yasin Gateway
        start_payload = {
            "event": "session.start",
            "session_id": sess_id,
            "call_id": call_id,
            "organization_id": org_id,
            "agent_id": agent_id,
            "call_direction": "inbound",
            "client_sample_rate": 16000,
            "template_type": "education",
            "business_name": "Apex University",
            "agent_name": "Maya",
            "speech_config": {
                "primary_language": "en-IN",
                "supported_languages": ["en-IN", "hi-IN", "te-IN"],
                "voice_id": "pooja",
                "voice_speed": 1.0,
                "allow_barge_in": True,
                "vad_silence_threshold_ms": 400,
                "welcome_message": "Hello! Thank you for calling Apex University Admissions. How may I assist you?",
                "goodbye_message": "Thank you for contacting Apex University. Have a wonderful day!",
                "max_call_duration_seconds": 600
            },
            "handoff_config": {
                "human_handoff_enabled": True,
                "human_handoff_number": "+919876543210",
                "human_handoff_condition": "caller_requests_human_or_fee_negotiation"
            },
            "system_prompt": "You are Maya, an educational counselor for Apex University."
        }
        ws.send_text(json.dumps(start_payload))

        # 1. Expect session.ready
        ready_raw = ws.receive_text()
        ready_evt = json.loads(ready_raw)
        assert ready_evt["event"] == "session.ready"
        assert ready_evt["session_id"] == sess_id
        assert ready_evt["status"] == "ready"

        # Verify active session state in SessionManager
        manager = get_session_manager()
        session = manager._sessions.get(sess_id)
        assert session is not None
        assert session.organization_id == org_id
        assert session.agent_id == agent_id
        assert session.language == "en-IN"
        assert session.greeting_message == "Hello! Thank you for calling Apex University Admissions. How may I assist you?"
        assert session.goodbye_message == "Thank you for contacting Apex University. Have a wonderful day!"
        assert session.allow_barge_in is True
        assert session.max_call_duration_seconds == 600
        assert session.speech_config["vad_silence_threshold_ms"] == 400
        assert session.handoff_config["human_handoff_enabled"] is True

        # 2. Close session cleanly and drain final events
        ws.send_text(json.dumps({"event": "session.end"}))
        events_received = []
        try:
            while len(events_received) < 100:
                msg = json.loads(ws.receive_text())
                events_received.append(msg["event"])
                if "call.summary" in events_received:
                    break
        except Exception:
            pass


def test_tenant_security_rejection_on_missing_tenant():
    """Verify that session.start is rejected when organization_id or agent_id is missing (no default fallback)."""
    client = TestClient(app)

    with client.websocket_connect("/ws/voice") as ws:
        # Send session.start missing organization_id and agent_id
        ws.send_text(json.dumps({
            "event": "session.start",
            "session_id": "bad-tenant-test",
            "language": "en-IN"
        }))

        error_raw = ws.receive_text()
        error_evt = json.loads(error_raw)
        assert error_evt["event"] == "error"
        assert "organization_id and agent_id are required" in error_evt["message"]


@pytest.mark.asyncio
async def test_multi_tenant_multi_agent_isolation():
    """Verify that Organization A -> Agent A does not receive Organization B -> Agent B context."""
    manager = get_session_manager()

    session_a = await manager.create_session(
        session_id="sess-org-a",
        organization_id="org-alpha-111",
        agent_id="agent-alice-222",
        business_name="Alpha Tech",
        system_prompt="You represent Alpha Tech with product X."
    )

    session_b = await manager.create_session(
        session_id="sess-org-b",
        organization_id="org-beta-333",
        agent_id="agent-bob-444",
        business_name="Beta Health",
        system_prompt="You represent Beta Health with wellness plans."
    )

    # Assert complete state separation
    assert session_a.organization_id != session_b.organization_id
    assert session_a.agent_id != session_b.agent_id
    assert session_a.business_name == "Alpha Tech"
    assert session_b.business_name == "Beta Health"
    assert session_a.system_prompt != session_b.system_prompt

    # Append distinct conversation turns
    session_a.messages.append({"role": "user", "content": "What are Alpha Tech prices?"})
    session_b.messages.append({"role": "user", "content": "What are Beta Health plans?"})

    assert len(session_a.messages) == 1
    assert len(session_b.messages) == 1
    assert session_a.messages[0]["content"] != session_b.messages[0]["content"]

    # Cleanup
    await manager.close_session("sess-org-a")
    await manager.close_session("sess-org-b")


def test_max_call_duration_expiry():
    """Verify that max_call_duration_seconds correctly marks session expired."""
    session = SessionState(
        session_id="sess-expire-test",
        organization_id="org-test",
        agent_id="agent-test",
        max_call_duration_seconds=1  # 1 second limit
    )
    # Immediately after creation, not expired
    assert not session.is_expired

    # Simulate 2 seconds later
    session.created_at_ms = (time.time() - 2.5) * 1000
    assert session.is_expired


def test_ten_templates_unaffected():
    """Verify all 10 standard templates remain registered and unaffected by backend contract mapping."""
    required_templates = [
        "education",
        "appointment_booking",
        "real_estate",
        "sales_discovery",
        "emi_collection",
        "healthcare_renewal",
        "ecommerce_cart",
        "order_delivery",
        "subscription_renewal",
        "custom"
    ]
    registered = AgentTemplateRegistry.list_templates()
    for tpl in required_templates:
        assert tpl in registered, f"Missing template: {tpl}"
        template = AgentTemplateRegistry.get_template(tpl)
        assert template is not None
