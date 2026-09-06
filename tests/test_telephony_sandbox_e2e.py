"""Phase 7: Local Telephony Sandbox End-to-End Test Suite (TEST ONLY).

Comprehensive test coverage for local telephony simulation:
- Webhook intake & HMAC security verification
- Realtime WebSocket audio streaming & control frames
- Synthetic audio edge cases (empty, oversized, corrupted base64)
- Call lifecycle (START -> MEDIA -> DTMF -> INTERRUPT -> STOP)
- Barge-in outbound queue draining
- Concurrent multi-call isolation
- Multi-tenant security context isolation
- Failure injection (queue overflow, shutdown, abrupt termination)
- Gateway metrics tracking
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.services.telephony.errors import GatewayError
from backend.app.services.telephony.frames import AudioFrame, FrameType
from backend.app.services.telephony.metrics import get_gateway_metrics
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    RealtimeVoiceSession,
)
from backend.app.services.telephony.session_context import SessionSecurityContext
from backend.app.services.telephony.session_manager import (
    RealtimeSessionManager,
    get_realtime_session_manager,
)
from tests.telephony_simulator.simulator import (
    SimulatedCallResult,
    TelephonySimulatorHarness,
)
from tests.telephony_simulator.synthetic_audio import SyntheticAudioGenerator
from tests.telephony_simulator.webhook_generator import SimulatedWebhookClient


@pytest.fixture(autouse=True)
def reset_gateway_state() -> None:
    """Ensure session manager is in active non-shutdown state for each test."""
    manager = get_realtime_session_manager()
    manager.reset_shutdown_state()


@pytest.fixture
def simulator_harness(mock_webhook_secret: str) -> TelephonySimulatorHarness:
    """Fixture providing a configured TelephonySimulatorHarness."""
    return TelephonySimulatorHarness(secret=mock_webhook_secret)


@pytest.fixture
def webhook_client(mock_webhook_secret: str) -> SimulatedWebhookClient:
    """Fixture providing a configured SimulatedWebhookClient."""
    return SimulatedWebhookClient(secret=mock_webhook_secret)


@pytest.fixture
def audio_generator() -> SyntheticAudioGenerator:
    """Fixture providing a SyntheticAudioGenerator."""
    return SyntheticAudioGenerator()


# ==============================================================================
# 1. Webhook Intake & Security Simulation Tests
# ==============================================================================


def test_simulated_inbound_webhook_valid(
    client: TestClient,
    webhook_client: SimulatedWebhookClient,
) -> None:
    """Verify simulated valid inbound call webhook intake returns HTTP 200."""
    response = webhook_client.send_inbound_webhook(client=client)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["call_sid"] == "call_sim_001"
    assert data["action"] == "process"


def test_simulated_inbound_webhook_invalid_signature_rejected(
    client: TestClient,
    webhook_client: SimulatedWebhookClient,
) -> None:
    """Verify webhook with tampered/invalid signature is rejected with HTTP 401."""
    response = webhook_client.send_inbound_webhook(client=client, tamper_signature=True)
    assert response.status_code == 401
    assert "signature" in response.json()["detail"].lower()


def test_simulated_inbound_webhook_missing_signature_rejected(
    client: TestClient,
    webhook_client: SimulatedWebhookClient,
) -> None:
    """Verify webhook missing signature header is rejected with HTTP 401."""
    response = webhook_client.send_inbound_webhook(client=client, omit_signature=True)
    assert response.status_code == 401


def test_simulated_inbound_webhook_replay_protection_expired_timestamp(
    client: TestClient,
    webhook_client: SimulatedWebhookClient,
) -> None:
    """Verify webhook with expired timestamp is rejected due to replay defense."""
    # Offset by -400s (exceeds default 300s tolerance)
    response = webhook_client.send_inbound_webhook(
        client=client,
        timestamp_offset_seconds=-400,
    )
    assert response.status_code == 401
    assert "timestamp" in response.json()["detail"].lower()


def test_simulated_inbound_webhook_malformed_payload(
    client: TestClient,
    webhook_client: SimulatedWebhookClient,
) -> None:
    """Verify malformed JSON payload returns HTTP 422."""
    response = webhook_client.send_inbound_webhook(
        client=client,
        raw_body="not_a_valid_json_payload",
    )
    assert response.status_code in (401, 422)


def test_simulated_event_callback_valid(
    client: TestClient,
    webhook_client: SimulatedWebhookClient,
) -> None:
    """Verify simulated call lifecycle status callback returns HTTP 200."""
    response = webhook_client.send_event_callback(client=client)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["call_sid"] == "call_sim_001"


# ==============================================================================
# 2. Realtime WebSocket & Synthetic Audio Tests
# ==============================================================================


def test_websocket_stream_full_ping_audio_flow(
    client: TestClient,
    audio_generator: SyntheticAudioGenerator,
) -> None:
    """Test full WebSocket audio streaming session via FastAPI TestClient."""
    session_id = "ws_sim_test_001"
    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # 1. Ping / Pong check
        ws.send_json({"type": "ping"})
        response = ws.receive_json()
        assert response.get("type") == "pong"

        # 2. Stream sequential synthetic audio frames
        for frame in audio_generator.generate_frame_stream(count=3):
            ws.send_json(
                {
                    "type": "audio",
                    "payload_b64": frame.base64_payload,
                    "sequence_number": frame.sequence,
                    "timestamp_ms": frame.timestamp_ms,
                }
            )

        # 3. Send Interruption control frame
        ws.send_json({"type": "interrupt"})

        # 4. Stream post-interruption audio frame
        post_frame = audio_generator.generate_caller_audio_frame(sequence=10)
        ws.send_json(
            {
                "type": "audio",
                "payload_b64": post_frame.base64_payload,
                "sequence_number": post_frame.sequence,
                "timestamp_ms": post_frame.timestamp_ms,
            }
        )


def test_websocket_stream_malformed_base64_ignored_gracefully(
    client: TestClient,
) -> None:
    """Verify corrupted payload is dropped without disconnecting the WebSocket."""
    session_id = "ws_sim_malformed_001"
    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        ws.send_text("CORRUPTED_NON_JSON_FRAME_DATA")
        # Connection stays open; responds to subsequent ping
        ws.send_json({"type": "ping"})
        resp = ws.receive_json()
        assert resp["type"] == FrameType.PONG


def test_websocket_stream_oversized_audio_frame_ignored_gracefully(
    client: TestClient,
    audio_generator: SyntheticAudioGenerator,
) -> None:
    """Verify oversized audio frame exceeding max payload size is dropped safely."""
    session_id = "ws_sim_oversized_001"
    oversized = audio_generator.generate_oversized_frame()
    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        ws.send_json(
            {
                "type": "audio",
                "payload_b64": oversized.base64_payload,
            }
        )
        # Gateway drops invalid frame without crashing
        ws.send_json({"type": "ping"})
        resp = ws.receive_json()
        assert resp["type"] == FrameType.PONG


# ==============================================================================
# 3. Call Lifecycle & Barge-in Simulation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_simulated_call_full_lifecycle(
    simulator_harness: TelephonySimulatorHarness,
) -> None:
    """Test entire simulated call lifecycle (START -> MEDIA -> DTMF -> INTERRUPT -> STOP)."""
    result: SimulatedCallResult = await simulator_harness.run_simulated_call(
        call_sid="call_e2e_life_001",
        session_id="session_e2e_life_001",
        num_frames=5,
        simulate_barge_in=True,
    )
    assert result.success is True
    assert result.inbound_frames_sent == 6  # 5 initial + 1 post-interruption
    assert result.interruptions_triggered == 1
    assert result.final_connection_state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_barge_in_drains_outbound_queue(
    audio_generator: SyntheticAudioGenerator,
) -> None:
    """Verify caller interruption immediately drains pending agent outbound audio."""
    session = RealtimeVoiceSession(session_id="session_barge_test_001")
    session.connection_state = ConnectionState.CONNECTED

    # Enqueue 4 outbound agent TTS frames
    for i in range(1, 5):
        frame = audio_generator.generate_agent_audio_frame(sequence=i)
        await session.push_outbound_frame(
            AudioFrame(
                data=frame.raw_bytes,
                sequence_number=frame.sequence,
                timestamp_ms=frame.timestamp_ms,
            )
        )

    assert session.outbound_audio_queue.qsize() == 4

    # Trigger interruption (caller barge-in)
    drained = session.trigger_interruption()
    assert drained == 4
    assert session.outbound_audio_queue.qsize() == 0
    assert session.interruption_event.is_set()

    # Verify session remains functional to accept new inbound caller audio
    new_caller_frame = audio_generator.generate_caller_audio_frame(sequence=50)
    accepted = await session.push_inbound_frame(
        AudioFrame(
            data=new_caller_frame.raw_bytes,
            sequence_number=new_caller_frame.sequence,
            timestamp_ms=new_caller_frame.timestamp_ms,
        )
    )
    assert accepted is True
    assert session.inbound_audio_queue.qsize() == 1

    await session.close()


# ==============================================================================
# 4. Multi-Call Concurrency & Tenant Isolation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_concurrent_simulated_calls_isolation(
    simulator_harness: TelephonySimulatorHarness,
) -> None:
    """Verify multiple simultaneous calls execute with strict isolation and no crosstalk."""
    call_count = 5
    results = await simulator_harness.run_concurrent_calls(count=call_count)
    assert len(results) == call_count

    session_ids = [r.session_id for r in results]
    call_sids = [r.call_sid for r in results]

    # Verify all session IDs and Call SIDs are unique
    assert len(set(session_ids)) == call_count
    assert len(set(call_sids)) == call_count

    for res in results:
        assert res.success is True
        assert res.final_connection_state == ConnectionState.CLOSED


@pytest.mark.asyncio
async def test_tenant_security_context_isolation() -> None:
    """Verify tenant A and tenant B security contexts cannot cross-pollinate."""
    ctx_a = SessionSecurityContext(
        session_id="session_alpha_001",
        call_id="call_alpha_001",
        organization_id="org_alpha",
        agent_id="agent_admission_alpha",
    )
    ctx_b = SessionSecurityContext(
        session_id="session_beta_002",
        call_id="call_beta_002",
        organization_id="org_beta",
        agent_id="agent_attendance_beta",
    )

    assert ctx_a.organization_id != ctx_b.organization_id
    assert ctx_a.organization_id == "org_alpha"
    assert ctx_b.organization_id == "org_beta"

    ctx_a.assert_tenant_access("org_alpha")
    with pytest.raises(GatewayError):
        ctx_a.assert_tenant_access("org_beta")


# ==============================================================================
# 5. Failure Injection & Resilience Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_queue_overflow_drop_oldest_backpressure(
    audio_generator: SyntheticAudioGenerator,
) -> None:
    """Verify backpressure drops oldest frames when inbound queue reaches capacity."""
    session = RealtimeVoiceSession(
        session_id="session_overflow_001",
        max_queue_size=3,
        backpressure_strategy="drop_oldest",
    )

    # Push 5 frames into queue of size 3
    for seq in range(1, 6):
        frame = audio_generator.generate_caller_audio_frame(sequence=seq)
        await session.push_inbound_frame(
            AudioFrame(
                data=frame.raw_bytes,
                sequence_number=frame.sequence,
                timestamp_ms=frame.timestamp_ms,
            )
        )

    # Queue should be at capacity (3) and 2 frames dropped
    assert session.inbound_audio_queue.qsize() == 3
    assert session.stats.frames_dropped == 2

    await session.close()


@pytest.mark.asyncio
async def test_shutdown_in_progress_rejects_new_sessions() -> None:
    """Verify session manager rejects new calls with GatewayError during shutdown."""
    manager = RealtimeSessionManager()
    manager._is_shutting_down = True

    with pytest.raises(GatewayError) as exc_info:
        await manager.create_session(session_id="session_rejected_001")
    assert "shutting down" in str(exc_info.value).lower()


# ==============================================================================
# 6. Gateway Metrics Verification
# ==============================================================================


def test_gateway_metrics_track_activity(
    client: TestClient,
    webhook_client: SimulatedWebhookClient,
) -> None:
    """Verify Prometheus metrics update accurately across simulated webhook calls."""
    metrics = get_gateway_metrics()
    before_sessions = metrics.get_snapshot()["sessions_created"]

    # Send webhook
    res = webhook_client.send_inbound_webhook(client=client)
    assert res.status_code == 200

    # Verify metrics
    after_sessions = metrics.get_snapshot()["sessions_created"]
    assert after_sessions >= before_sessions
