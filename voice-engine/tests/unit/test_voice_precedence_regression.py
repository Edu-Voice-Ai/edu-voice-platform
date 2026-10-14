"""Voice Selection and ID Precedence Regression Tests.

Verifies:
1. Explicit payload voice_id overrides populated global configuration (settings.voice_id).
2. Agent-level speech_config.voice_id is honored when payload override is absent.
3. Global default (settings.voice_id) remains the fallback when neither payload nor agent config supplies one.
4. Engine and session agree on the selected voice ID consistently.
5. TTS provider fallback operates when voice_id is absent.
6. Inbound WebSocket session initialization preserves voice precedence contracts.
"""

import json
import pytest
from starlette.testclient import TestClient
from app.main import app
from app.core.config import get_settings
from app.session.manager import get_session_manager
from app.session.state import SessionState
from app.api.websocket import build_default_engine


@pytest.fixture
def clean_manager():
    manager = get_session_manager()
    manager._sessions.clear()
    return manager


def _drain_and_close(ws):
    try:
        ws.send_text(json.dumps({"event": "session.end"}))
        for _ in range(50):
            msg = json.loads(ws.receive_text())
            if msg.get("event") in ("session.ended", "call.summary"):
                break
    except Exception:
        pass


def test_explicit_payload_voice_overrides_global_settings(clean_manager, monkeypatch):
    """Explicit session payload voice_id must override populated global settings.voice_id."""
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_id", "svc-prod-global-default-7777")
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_mock_api_key")

    client = TestClient(app)
    sess_id = "sess_override_test_1"
    with client.websocket_connect("/ws/voice") as ws:
        payload = {
            "event": "session.start",
            "session_id": sess_id,
            "call_id": "call_ov_1",
            "organization_id": "org_test",
            "agent_id": "agent_test",
            "voice_id": "svc-custom-payload-voice-1111",
            "speech_config": {
                "voice_id": "svc-agent-config-voice-2222",
                "primary_language": "en-IN",
            }
        }
        ws.send_text(json.dumps(payload))
        ready_raw = ws.receive_text()
        ready_evt = json.loads(ready_raw)
        assert ready_evt["event"] == "session.ready"

        session = clean_manager._sessions.get(sess_id)
        assert session is not None
        assert session.voice_id == "svc-custom-payload-voice-1111", (
            f"Expected payload voice_id to override all, got {session.voice_id}"
        )
        _drain_and_close(ws)


def test_agent_speech_config_wins_when_payload_voice_absent(clean_manager, monkeypatch):
    """Agent speech_config.voice_id must be honored when payload voice_id is absent."""
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_id", "svc-prod-global-default-7777")
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_mock_api_key")

    client = TestClient(app)
    sess_id = "sess_agent_cfg_test_2"
    with client.websocket_connect("/ws/voice") as ws:
        payload = {
            "event": "session.start",
            "session_id": sess_id,
            "call_id": "call_ov_2",
            "organization_id": "org_test",
            "agent_id": "agent_test",
            "speech_config": {
                "voice_id": "svc-agent-config-voice-2222",
                "primary_language": "en-IN",
            }
        }
        ws.send_text(json.dumps(payload))
        ready_raw = ws.receive_text()
        ready_evt = json.loads(ready_raw)
        assert ready_evt["event"] == "session.ready"

        session = clean_manager._sessions.get(sess_id)
        assert session is not None
        assert session.voice_id == "svc-agent-config-voice-2222", (
            f"Expected agent config voice_id to win when payload voice absent, got {session.voice_id}"
        )
        _drain_and_close(ws)


def test_global_default_used_when_neither_payload_nor_agent_specifies_voice(clean_manager, monkeypatch):
    """Global settings.voice_id default must be preserved when neither payload nor agent config provides voice."""
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_id", "svc-prod-global-default-7777")
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_mock_api_key")

    client = TestClient(app)
    sess_id = "sess_global_default_test_3"
    with client.websocket_connect("/ws/voice") as ws:
        payload = {
            "event": "session.start",
            "session_id": sess_id,
            "call_id": "call_ov_3",
            "organization_id": "org_test",
            "agent_id": "agent_test",
            "speech_config": {
                "primary_language": "en-IN",
            }
        }
        ws.send_text(json.dumps(payload))
        ready_raw = ws.receive_text()
        ready_evt = json.loads(ready_raw)
        assert ready_evt["event"] == "session.ready"

        session = clean_manager._sessions.get(sess_id)
        assert session is not None
        assert session.voice_id == "svc-prod-global-default-7777", (
            f"Expected fallback to global settings.voice_id, got {session.voice_id}"
        )
        _drain_and_close(ws)


@pytest.mark.asyncio
async def test_tts_provider_fallback_when_voice_id_none(monkeypatch):
    """When voice_id is None, Sarvam TTS provider falls back to default speaker."""
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_id", None)
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_mock_api_key")
    monkeypatch.setattr(settings, "tts_speaker", "pooja")

    session = SessionState(
        session_id="sess_fallback_none",
        organization_id="org_test",
        agent_id="agent_test",
        voice_id=None,
        speech_config={}
    )

    engine = build_default_engine(session)
    try:
        assert engine.tts_provider.voice_id is None
        assert engine.tts_provider.default_speaker == "pooja"
    finally:
        await engine.stop()


@pytest.mark.asyncio
async def test_build_default_engine_preserves_session_voice_consistency(monkeypatch):
    """Direct build_default_engine call must respect session.voice_id over settings.voice_id."""
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_id", "svc-prod-settings-9999")
    monkeypatch.setattr(settings, "sarvam_api_key", "sk_mock_api_key")

    session = SessionState(
        session_id="sess_direct_test",
        organization_id="org_test",
        agent_id="agent_test",
        voice_id="svc-session-direct-8888"
    )

    engine = build_default_engine(session)
    try:
        assert engine.tts_provider.voice_id == "svc-session-direct-8888"
        assert session.voice_id == engine.tts_provider.voice_id
    finally:
        await engine.stop()
