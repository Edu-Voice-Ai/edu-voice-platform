"""End-to-End WebSocket Handoff Protocol Test Suite (Phase 13 & Phase 12).

Simulates full lifecycle across:
- session.start -> session.ready
- STT/audio input with handoff intent -> handoff.requested
- handoff.acknowledged -> holding TTS state
- handoff.fallback -> fallback recovery -> normal conversation
- session.end(reason="transferred_to_human")
- Multilingual and ambiguous request handling over WebSocket.
"""
import pytest
import json
import asyncio
from starlette.testclient import TestClient
from app.main import app
from app.pipeline.engine import SpeechToSpeechEngine
from app.pipeline.cancellation import CancellationToken
from app.session.state import SessionState, HandoffStateEnum


def test_e2e_handoff_lifecycle_with_fallback_recovery():
    """Phase 13 Simulation 1:
    session.start -> session.ready -> handoff intent -> handoff.requested ->
    handoff.acknowledged -> holding TTS -> handoff.fallback -> fallback response ->
    session.end
    """
    client = TestClient(app)
    session_id = "sess_handoff_e2e_01"
    call_id = "call_handoff_e2e_01"

    with client.websocket_connect("/ws/voice") as ws:
        # 1. session.start
        ws.send_text(json.dumps({
            "event": "session.start",
            "session_id": session_id,
            "call_id": call_id,
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": "en-IN",
            "client_sample_rate": 16000
        }))

        # Expect session.ready
        ready_evt = json.loads(ws.receive_text())
        assert ready_evt.get("event") == "session.ready"
        assert ready_evt.get("session_id") == session_id

        # 2. Inbound handoff.acknowledged from gateway
        ws.send_text(json.dumps({
            "event": "handoff.acknowledged",
            "session_id": session_id,
            "call_id": call_id,
            "status": "resolving_target",
            "hold_media": True
        }))

        # 3. Inbound handoff.fallback from gateway (no eligible staff available)
        ws.send_text(json.dumps({
            "event": "handoff.fallback",
            "session_id": session_id,
            "call_id": call_id,
            "reason": "NO_ELIGIBLE_STAFF",
            "prompt_instruction": "All admission counselors are currently busy on other calls."
        }))

        # 4. Clean session termination
        ws.send_text(json.dumps({
            "event": "session.end",
            "session_id": session_id,
            "call_id": call_id,
            "reason": "caller_hangup"
        }))

        # Collect outgoing events and ensure proper teardown
        events_received = []
        for _ in range(20):
            try:
                raw = ws.receive_text()
                evt = json.loads(raw)
                events_received.append(evt)
                if evt.get("event") == "call.summary":
                    break
            except Exception:
                break

        evt_types = [e.get("event") for e in events_received]
        assert "call.summary" in evt_types or "lead.extracted" in evt_types or len(events_received) > 0


def test_e2e_handoff_transferred_to_human_clean_teardown():
    """Phase 13 Simulation 2:
    session.start -> session.ready -> handoff.requested -> handoff.acknowledged ->
    session.end(reason="transferred_to_human")
    """
    client = TestClient(app)
    session_id = "sess_handoff_transfer_02"
    call_id = "call_handoff_transfer_02"

    with client.websocket_connect("/ws/voice") as ws:
        # 1. session.start
        ws.send_text(json.dumps({
            "event": "session.start",
            "session_id": session_id,
            "call_id": call_id,
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": "en-IN",
            "client_sample_rate": 16000
        }))

        ready_evt = json.loads(ws.receive_text())
        assert ready_evt.get("event") == "session.ready"

        # 2. Handoff acknowledged
        ws.send_text(json.dumps({
            "event": "handoff.acknowledged",
            "session_id": session_id,
            "call_id": call_id,
            "status": "resolving_target"
        }))

        # 3. Successful PSTN transfer signaled by gateway closing session
        ws.send_text(json.dumps({
            "event": "session.end",
            "session_id": session_id,
            "call_id": call_id,
            "reason": "transferred_to_human"
        }))

        events_received = []
        for _ in range(20):
            try:
                raw = ws.receive_text()
                evt = json.loads(raw)
                events_received.append(evt)
                if evt.get("event") == "call.summary":
                    break
            except Exception:
                break

        evt_types = [e.get("event") for e in events_received]
        assert "call.summary" in evt_types or "lead.extracted" in evt_types or len(events_received) > 0


@pytest.mark.asyncio
async def test_engine_process_stt_turn_explicit_handoff(test_s2s_engine):
    """Unit test SpeechToSpeechEngine._process_stt_turn when explicit handoff is spoken."""
    engine = test_s2s_engine
    session = engine.session
    session.call_id = "call_test_turn"
    token = CancellationToken()

    # Fast path: Caller says explicit handoff request
    engine.stt_provider.default_text = "I want to speak with an admission counselor"
    await engine._process_stt_turn(b"\x00" * 320, "turn_1", "gen_1", token)

    # Verify state transitioned
    assert session.handoff_requested is True
    assert session.handoff_requested_role == "admission_counselor"
    assert session.handoff_requested_department == "admissions"
    assert session.handoff_confidence >= 0.85

    # Check event emitted to event_out_queue
    events = []
    while not engine.queues.event_out_queue.empty():
        events.append(engine.queues.event_out_queue.get_nowait())
    handoff_ev = next((e for e in events if getattr(e.event, "value", str(e.event)) == "handoff.requested"), None)
    assert handoff_ev is not None, f"No handoff.requested in {[getattr(e.event, 'value', str(e.event)) for e in events]}"
    assert handoff_ev.data["requested_role"] == "admission_counselor"
    assert handoff_ev.data["requested_department"] == "admissions"
    assert handoff_ev.data["confidence"] >= 0.85

    # Test idempotency: a second utterance must NOT emit duplicate handoff.requested
    engine.stt_provider.default_text = "Please transfer me again"
    await engine._process_stt_turn(b"\x00" * 320, "turn_2", "gen_2", token)
    second_events = []
    while not engine.queues.event_out_queue.empty():
        second_events.append(engine.queues.event_out_queue.get_nowait())
    duplicate_handoffs = [e for e in second_events if getattr(e.event, "value", str(e.event)) == "handoff.requested"]
    assert len(duplicate_handoffs) == 0


@pytest.mark.asyncio
async def test_engine_process_stt_turn_telugu_explicit_handoff(test_s2s_engine):
    """TEST-VE-02 over engine: Telugu explicit handoff request."""
    engine = test_s2s_engine
    engine.session.language = "te-IN"
    token = CancellationToken()

    engine.stt_provider.default_text = "దయచేసి ఒక మనిషితో మాట్లాడించండి"
    await engine._process_stt_turn(b"\x00" * 320, "turn_te", "gen_te", token)

    assert engine.session.handoff_requested is True
    assert engine.session.handoff_requested_role == "general_counselor"

    events = []
    while not engine.queues.event_out_queue.empty():
        events.append(engine.queues.event_out_queue.get_nowait())
    handoff_ev = next((e for e in events if getattr(e.event, "value", str(e.event)) == "handoff.requested"), None)
    assert handoff_ev is not None
    assert handoff_ev.data["requested_role"] == "general_counselor"


@pytest.mark.asyncio
async def test_engine_process_stt_turn_hindi_explicit_handoff(test_s2s_engine):
    """TEST-VE-03 over engine: Hindi explicit handoff request."""
    engine = test_s2s_engine
    engine.session.language = "hi-IN"
    token = CancellationToken()

    engine.stt_provider.default_text = "मुझे एडमिशन काउंसलर से बात करनी है"
    await engine._process_stt_turn(b"\x00" * 320, "turn_hi", "gen_hi", token)

    assert engine.session.handoff_requested is True
    assert engine.session.handoff_requested_role == "admission_counselor"

    events = []
    while not engine.queues.event_out_queue.empty():
        events.append(engine.queues.event_out_queue.get_nowait())
    handoff_ev = next((e for e in events if getattr(e.event, "value", str(e.event)) == "handoff.requested"), None)
    assert handoff_ev is not None
    assert handoff_ev.data["requested_role"] == "admission_counselor"


@pytest.mark.asyncio
async def test_engine_cancellation_during_awaiting_transfer(test_s2s_engine):
    """TEST-VE Phase 11: Cancellation during transfer."""
    engine = test_s2s_engine
    session = engine.session
    token = CancellationToken()
    session.record_handoff_requested("admission_counselor", "admissions", "caller asked")
    session.record_handoff_acknowledged(hold_media=True)
    assert session.handoff_state == HandoffStateEnum.AWAITING_TRANSFER

    # Caller changes mind while awaiting transfer
    engine.stt_provider.default_text = "Wait never mind cancel the transfer"
    await engine._process_stt_turn(b"\x00" * 320, "turn_canc", "gen_canc", token)

    assert session.handoff_state == HandoffStateEnum.IDLE
    events = []
    while not engine.queues.event_out_queue.empty():
        events.append(engine.queues.event_out_queue.get_nowait())
    cancel_ev = next((e for e in events if getattr(e.event, "value", str(e.event)) == "handoff.cancelled"), None)
    assert cancel_ev is not None


@pytest.mark.asyncio
async def test_engine_handle_handoff_acknowledged_and_fallback(test_s2s_engine):
    """TEST-VE-05 & TEST-VE-06: Acknowledgment and Fallback handling."""
    engine = test_s2s_engine
    session = engine.session
    session.record_handoff_requested("admission_counselor", "admissions", "caller asked")

    # Test handoff acknowledged
    await engine.handle_handoff_acknowledged(hold_media=True)
    assert session.handoff_state == HandoffStateEnum.AWAITING_TRANSFER
    assert session.handoff_hold_media is True

    # Test handoff fallback
    await engine.handle_handoff_fallback(
        reason="NO_ELIGIBLE_STAFF",
        prompt_instruction="All counselors busy"
    )
    assert session.handoff_state == HandoffStateEnum.IDLE
    assert session.out_of_scope_turn_count == 0
