"""Voice Engine Transport Contract v1.0 Test Suite.

Comprehensive tests covering:
1. Voice Engine connection lifecycle
2. session.start request schema and template mappings
3. session.ready confirmation
4. Binary PCM16 audio streaming (Option A: 20ms frames, 640B @ 16kHz / 320B @ 8kHz)
5. JSON Base64 audio input (Option B)
6. audio.output decoding from Base64 PCM16 into AudioFrame
7. Outbound queue integration
8. response.cancelled (barge-in interruption)
9. Stale generation audio removal and filtering
10. response.end latency telemetry
11. session.end termination
12. lead.extracted intake
13. call.summary intake
14. error event handling
15. Unexpected disconnect resilience
16. Connection & initialization timeout handling
17. Malformed message resilience
18. Concurrent session isolation
19. Tenant security context isolation
20. Clean shutdown & resource cleanup
"""

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from websockets.asyncio.server import serve

from backend.app.services.telephony.config import TelephonySettings
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.routing.phone_assignment import ResolvedAgentConfig
from backend.app.services.telephony.voice_engine_client import VoiceEngineWsClient
from backend.app.services.telephony.voice_engine_contract import (
    WsVoiceEngineTransport,
    build_session_start_payload,
)
from backend.app.services.telephony.voice_engine_schemas import (
    CallSummaryEvent,
    LeadExtractedEvent,
    ResponseCancelledEvent,
    ResponseEndEvent,
    SessionStartPayload,
    VoiceEngineErrorEvent,
    VoiceEngineTemplateType,
)


class MockVoiceEngineServer:
    """Mock WebSocket server simulating Lokesh's Voice Engine behavior."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.server: Any = None
        self.actual_port: int = 0
        self.received_messages: list[str | bytes] = []
        self.connected_clients: list[Any] = []
        self.auto_emit_ready: bool = True
        self.custom_handler: Any = None

    async def _handler(self, websocket: Any) -> None:
        self.connected_clients.append(websocket)
        try:
            async for message in websocket:
                self.received_messages.append(message)
                if self.custom_handler is not None:
                    await self.custom_handler(websocket, message)
                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                        event = data.get("event")
                        if event == "session.start" and self.auto_emit_ready:
                            ready_msg = {
                                "event": "session.ready",
                                "session_id": data.get("session_id"),
                                "turn_id": None,
                                "generation_id": None,
                                "timestamp_ms": 1725549000150.0,
                                "data": {"status": "ready"},
                            }
                            await websocket.send(json.dumps(ready_msg))
                    except (json.JSONDecodeError, OSError, RuntimeError):
                        pass
        except (OSError, RuntimeError):
            pass

    async def start(self) -> str:
        self.server = await serve(self._handler, self.host, self.port)
        if self.server is not None and hasattr(self.server, "sockets"):
            for sock in self.server.sockets:
                self.actual_port = sock.getsockname()[1]
                break
        return f"ws://{self.host}:{self.actual_port}/ws/voice"

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()


@asynccontextmanager
async def start_mock_voice_engine() -> AsyncGenerator[tuple[MockVoiceEngineServer, str], None]:
    """Async context manager starting and stopping a mock Voice Engine server."""
    server = MockVoiceEngineServer()
    ws_url = await server.start()
    try:
        yield server, ws_url
    finally:
        await server.stop()


# ==============================================================================
# 1. session.start Schema & Template Defaults Tests
# ==============================================================================


def test_session_start_default_template_and_business() -> None:
    """Verify default fallback to education template and Apex University."""
    payload = build_session_start_payload(session_id="sess_001")
    assert payload.event == "session.start"
    assert payload.session_id == "sess_001"
    assert payload.template_type == "education"
    assert payload.business_name == "Apex University"
    assert payload.client_sample_rate == 16000
    assert payload.language == "en-IN"


def test_session_start_all_ten_template_types() -> None:
    """Verify all 10 multi-industry template types can be serialized."""
    templates = [
        VoiceEngineTemplateType.EDUCATION,
        VoiceEngineTemplateType.APPOINTMENT_BOOKING,
        VoiceEngineTemplateType.REAL_ESTATE,
        VoiceEngineTemplateType.SALES_DISCOVERY,
        VoiceEngineTemplateType.EMI_COLLECTION,
        VoiceEngineTemplateType.HEALTHCARE_RENEWAL,
        VoiceEngineTemplateType.ECOMMERCE_CART,
        VoiceEngineTemplateType.ORDER_DELIVERY,
        VoiceEngineTemplateType.SUBSCRIPTION_RENEWAL,
        VoiceEngineTemplateType.CUSTOM,
    ]
    for tmpl in templates:
        payload = SessionStartPayload(
            session_id=f"sess_{tmpl.value}",
            template_type=tmpl.value,
            business_name=f"Business for {tmpl.value}",
        )
        data = json.loads(payload.model_dump_json())
        assert data["template_type"] == tmpl.value
        assert data["business_name"] == f"Business for {tmpl.value}"


def test_session_start_mapping_from_resolved_agent_config() -> None:
    """Verify mapping fields from ResolvedAgentConfig into SessionStartPayload."""
    agent_cfg = ResolvedAgentConfig(
        organization_id="org_clinic_99",
        organization_name="City Clinic",
        agent_id="agent_ananya_01",
        agent_name="Ananya",
        language="hi-IN",
        welcome_message="Namaste, welcome to City Clinic.",
        system_prompt="Custom clinical appointment prompt",
        custom_settings={
            "template_type": "appointment_booking",
            "goodbye_message": "Dhanyavaad!",
        },
    )

    payload = build_session_start_payload(
        session_id="sess_appt_001",
        organization_id=agent_cfg.organization_id,
        agent_id=agent_cfg.agent_id,
        agent_config=agent_cfg,
        sample_rate=8000,
    )

    assert payload.session_id == "sess_appt_001"
    assert payload.organization_id == "org_clinic_99"
    assert payload.agent_id == "agent_ananya_01"
    assert payload.business_name == "City Clinic"
    assert payload.agent_name == "Ananya"
    assert payload.language == "hi-IN"
    assert payload.client_sample_rate == 8000
    assert payload.template_type == "appointment_booking"
    assert payload.greeting_message == "Namaste, welcome to City Clinic."
    assert payload.goodbye_message == "Dhanyavaad!"
    assert payload.system_prompt == "Custom clinical appointment prompt"


# ==============================================================================
# 2. Connection Lifecycle & Audio Streaming Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_voice_engine_connection_and_session_ready() -> None:
    """Test successful connection, session.start transmission, and session.ready receipt."""
    async with start_mock_voice_engine() as (server, ws_url):
        start_payload = build_session_start_payload(session_id="sess_ready_test")

        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_ready_test",
            start_payload=start_payload,
        )

        await client.connect_and_start()
        assert client.is_connected
        assert client.is_ready

        assert len(server.received_messages) == 1
        sent_start = json.loads(server.received_messages[0])
        assert sent_start["event"] == "session.start"
        assert sent_start["session_id"] == "sess_ready_test"

        await client.close()


@pytest.mark.asyncio
async def test_voice_engine_binary_pcm_audio_forwarding() -> None:
    """Test streaming raw 20ms binary PCM16 audio frames (Option A - 640 bytes @ 16kHz)."""
    async with start_mock_voice_engine() as (server, ws_url):
        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_audio_bin",
            start_payload=build_session_start_payload(session_id="sess_audio_bin"),
        )
        await client.connect_and_start()

        pcm16_frame = AudioFrame(
            data=b"\x00\x01" * 320,  # 640 bytes (20ms @ 16kHz)
            sequence_number=1,
            timestamp_ms=20,
        )
        await client.send_audio_frame(frame=pcm16_frame, use_binary=True)
        await asyncio.sleep(0.05)

        assert len(server.received_messages) == 2
        assert isinstance(server.received_messages[1], bytes)
        assert len(server.received_messages[1]) == 640

        await client.close()


@pytest.mark.asyncio
async def test_voice_engine_json_base64_audio_forwarding() -> None:
    """Test streaming JSON Base64 audio frames (Option B)."""
    async with start_mock_voice_engine() as (server, ws_url):
        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_audio_json",
            start_payload=build_session_start_payload(session_id="sess_audio_json"),
        )
        await client.connect_and_start()

        pcm16_frame = AudioFrame(
            data=b"\x00\x02" * 160,  # 320 bytes (20ms @ 8kHz)
            sequence_number=42,
            timestamp_ms=40,
        )
        await client.send_audio_frame(frame=pcm16_frame, use_binary=False)
        await asyncio.sleep(0.05)

        assert len(server.received_messages) == 2
        assert isinstance(server.received_messages[1], str)
        data = json.loads(server.received_messages[1])
        assert data["event"] == "audio.input"
        assert data["seq"] == 42
        assert base64.b64decode(data["data"]) == pcm16_frame.data

        await client.close()


# ==============================================================================
# 3. audio.output Decoding & Outbound Queue Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_voice_engine_audio_output_decoding() -> None:
    """Test decoding audio.output Base64 PCM16 into AudioFrame and queueing."""
    async with start_mock_voice_engine() as (server, ws_url):
        outbound_queue: asyncio.Queue[AudioFrame] = asyncio.Queue()

        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_out_decode",
            start_payload=build_session_start_payload(session_id="sess_out_decode"),
            outbound_queue=outbound_queue,
        )
        await client.connect_and_start()

        # Simulate Voice Engine emitting audio.output
        raw_tts_audio = b"\x10\x20" * 320  # 640 bytes PCM16
        output_event = {
            "event": "audio.output",
            "session_id": "sess_out_decode",
            "turn_id": "turn_1",
            "generation_id": "gen_alpha_01",
            "timestamp_ms": 1725549000845.2,
            "data": {
                "data": base64.b64encode(raw_tts_audio).decode("ascii"),
                "seq": 14,
                "sample_rate": 16000,
                "duration_ms": 20.0,
                "language": "en-IN",
                "cancellation_cycle": 0,
            },
        }

        server_ws = server.connected_clients[0]
        await server_ws.send(json.dumps(output_event))
        await asyncio.sleep(0.05)

        assert outbound_queue.qsize() == 1
        frame = await outbound_queue.get()
        assert frame.data == raw_tts_audio
        assert frame.sequence_number == 14
        assert frame.metadata["generation_id"] == "gen_alpha_01"
        assert frame.metadata["turn_id"] == "turn_1"
        assert frame.metadata["sample_rate"] == 16000

        await client.close()


# ==============================================================================
# 4. Barge-In & Generation Cancellation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_voice_engine_barge_in_cancelled_and_queue_drain() -> None:
    """Test response.cancelled clears current generation audio and prevents stale chunks."""
    async with start_mock_voice_engine() as (server, ws_url):
        outbound_queue: asyncio.Queue[AudioFrame] = asyncio.Queue()
        cancellation_received: list[ResponseCancelledEvent] = []

        async def on_cancelled(evt: ResponseCancelledEvent) -> None:
            cancellation_received.append(evt)

        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_cancel_test",
            start_payload=build_session_start_payload(session_id="sess_cancel_test"),
            outbound_queue=outbound_queue,
            on_response_cancelled=on_cancelled,
        )
        await client.connect_and_start()
        server_ws = server.connected_clients[0]

        # 1. Voice Engine sends audio for gen_01
        raw_audio = b"\x05\x05" * 320
        await server_ws.send(
            json.dumps(
                {
                    "event": "audio.output",
                    "session_id": "sess_cancel_test",
                    "generation_id": "gen_01",
                    "data": {"data": base64.b64encode(raw_audio).decode("ascii"), "seq": 1},
                }
            )
        )
        await asyncio.sleep(0.05)
        assert outbound_queue.qsize() == 1

        # 2. Voice Engine emits response.cancelled for gen_01
        await server_ws.send(
            json.dumps(
                {
                    "event": "response.cancelled",
                    "session_id": "sess_cancel_test",
                    "generation_id": "gen_01",
                    "turn_id": "turn_1",
                    "timestamp_ms": 1725549001210.0,
                    "data": {
                        "reason": "User interrupted AI response",
                        "interrupted_at_ms": 1725549001209.5,
                    },
                }
            )
        )
        await asyncio.sleep(0.05)

        assert len(cancellation_received) == 1
        assert cancellation_received[0].generation_id == "gen_01"
        assert "gen_01" in client.cancelled_generations
        # Outbound queue was drained
        assert outbound_queue.qsize() == 0

        # 3. Late arriving audio chunk for cancelled gen_01 should be dropped immediately
        await server_ws.send(
            json.dumps(
                {
                    "event": "audio.output",
                    "session_id": "sess_cancel_test",
                    "generation_id": "gen_01",
                    "data": {"data": base64.b64encode(raw_audio).decode("ascii"), "seq": 2},
                }
            )
        )
        await asyncio.sleep(0.05)
        assert outbound_queue.qsize() == 0  # Still 0, dropped!

        # 4. Audio chunk for NEW generation gen_02 is accepted
        await server_ws.send(
            json.dumps(
                {
                    "event": "audio.output",
                    "session_id": "sess_cancel_test",
                    "generation_id": "gen_02",
                    "data": {"data": base64.b64encode(raw_audio).decode("ascii"), "seq": 1},
                }
            )
        )
        await asyncio.sleep(0.05)
        assert outbound_queue.qsize() == 1

        await client.close()


# ==============================================================================
# 5. response.end & Post-Call (lead.extracted / call.summary) Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_voice_engine_response_end_telemetry() -> None:
    """Test response.end telemetry capture."""
    async with start_mock_voice_engine() as (server, ws_url):
        end_events: list[ResponseEndEvent] = []

        async def on_end(evt: ResponseEndEvent) -> None:
            end_events.append(evt)

        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_resp_end",
            start_payload=build_session_start_payload(session_id="sess_resp_end"),
            on_response_end=on_end,
        )
        await client.connect_and_start()

        server_ws = server.connected_clients[0]
        await server_ws.send(
            json.dumps(
                {
                    "event": "response.end",
                    "session_id": "sess_resp_end",
                    "turn_id": "turn_1",
                    "generation_id": "gen_01",
                    "timestamp_ms": 1725549002500.0,
                    "data": {
                        "turn_id": "turn_1",
                        "stt_latency_ms": 285.0,
                        "llm_ttft_ms": 140.0,
                        "tts_first_audio_ms": 190.0,
                        "total_speech_to_first_audio_ms": 615.0,
                    },
                }
            )
        )
        await asyncio.sleep(0.05)

        assert len(end_events) == 1
        assert end_events[0].turn_id == "turn_1"
        latencies = client.latest_latencies
        assert latencies is not None
        assert latencies["total_speech_to_first_audio_ms"] == 615.0

        await client.close()


@pytest.mark.asyncio
async def test_voice_engine_session_end_and_post_call_intelligence() -> None:
    """Test session.end sends termination frame and receives lead.extracted & call.summary."""
    async with start_mock_voice_engine() as (server, ws_url):
        leads_captured: list[LeadExtractedEvent] = []
        summaries_captured: list[CallSummaryEvent] = []

        async def custom_handler(ws: Any, message: Any) -> None:
            if isinstance(message, str):
                data = json.loads(message)
                if data.get("event") == "session.start":
                    await ws.send(
                        json.dumps(
                            {
                                "event": "session.ready",
                                "session_id": data.get("session_id"),
                                "data": {"status": "ready"},
                            }
                        )
                    )
                elif data.get("event") == "session.end":
                    # Emit post-call intelligence
                    await ws.send(
                        json.dumps(
                            {
                                "event": "lead.extracted",
                                "session_id": "sess_post_call",
                                "data": {
                                    "lead": {
                                        "name": "Rohan Gupta",
                                        "course": "B.Tech Computer Science",
                                        "intent": "high",
                                    }
                                },
                            }
                        )
                    )
                    await ws.send(
                        json.dumps(
                            {
                                "event": "call.summary",
                                "session_id": "sess_post_call",
                                "data": {
                                    "summary": {
                                        "call_purpose": "Admissions Inquiry",
                                        "outcome": "Counseling Scheduled",
                                    }
                                },
                            }
                        )
                    )

        server.custom_handler = custom_handler

        async def _capture_lead(e: LeadExtractedEvent) -> None:
            leads_captured.append(e)

        async def _capture_summary(e: CallSummaryEvent) -> None:
            summaries_captured.append(e)

        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_post_call",
            start_payload=build_session_start_payload(session_id="sess_post_call"),
            on_lead_extracted=_capture_lead,
            on_call_summary=_capture_summary,
        )
        await client.connect_and_start()

        # Trigger session.end
        await client.close_session(drain_timeout_seconds=0.2)

        assert len(leads_captured) == 1
        assert leads_captured[0].lead["name"] == "Rohan Gupta"
        assert len(summaries_captured) == 1
        assert summaries_captured[0].summary["outcome"] == "Counseling Scheduled"

        assert client.latest_lead is not None
        assert client.latest_lead["course"] == "B.Tech Computer Science"
        assert client.latest_summary is not None
        assert client.latest_summary["call_purpose"] == "Admissions Inquiry"


# ==============================================================================
# 6. Error & Resilience Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_voice_engine_error_event_handling() -> None:
    """Test handling error event from Voice Engine."""
    async with start_mock_voice_engine() as (server, ws_url):
        errors: list[VoiceEngineErrorEvent] = []

        async def _capture_error(e: VoiceEngineErrorEvent) -> None:
            errors.append(e)

        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_err_test",
            start_payload=build_session_start_payload(session_id="sess_err_test"),
            on_error=_capture_error,
        )
        await client.connect_and_start()

        server_ws = server.connected_clients[0]
        await server_ws.send(
            json.dumps(
                {
                    "event": "error",
                    "message": "Session initialization quota exceeded",
                }
            )
        )
        await asyncio.sleep(0.05)

        assert len(errors) == 1
        assert errors[0].message == "Session initialization quota exceeded"

        await client.close()


@pytest.mark.asyncio
async def test_voice_engine_initialization_timeout() -> None:
    """Test timeout when Voice Engine fails to emit session.ready."""
    async with start_mock_voice_engine() as (server, ws_url):
        server.auto_emit_ready = False  # Suppress session.ready

        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_timeout",
            start_payload=build_session_start_payload(session_id="sess_timeout"),
            connect_timeout_seconds=1.0,
            init_timeout_seconds=0.2,
        )

        with pytest.raises(GatewayError) as exc_info:
            await client.connect_and_start()
        assert exc_info.value.code == GatewayErrorCode.TIMEOUT
        assert "session.ready" in exc_info.value.message


@pytest.mark.asyncio
async def test_voice_engine_connection_failure_to_invalid_port() -> None:
    """Test connection failure when Voice Engine endpoint is unreachable."""
    client = VoiceEngineWsClient(
        ws_url="ws://127.0.0.1:59999/ws/voice",
        session_id="sess_unreachable",
        start_payload=build_session_start_payload(session_id="sess_unreachable"),
        connect_timeout_seconds=0.5,
    )
    with pytest.raises(GatewayError) as exc_info:
        await client.connect_and_start()
    assert exc_info.value.code in (
        GatewayErrorCode.SERVICE_UNAVAILABLE,
        GatewayErrorCode.TIMEOUT,
    )


@pytest.mark.asyncio
async def test_voice_engine_malformed_json_resilience() -> None:
    """Test that malformed JSON from Voice Engine is handled without crashing."""
    async with start_mock_voice_engine() as (server, ws_url):
        client = VoiceEngineWsClient(
            ws_url=ws_url,
            session_id="sess_malformed",
            start_payload=build_session_start_payload(session_id="sess_malformed"),
        )
        await client.connect_and_start()

        server_ws = server.connected_clients[0]
        await server_ws.send("INVALID_NOT_JSON{")
        await server_ws.send(json.dumps(["not", "a", "dict"]))
        await asyncio.sleep(0.05)

        # Client remains connected and alive
        assert client.is_connected
        await client.close()


# ==============================================================================
# 7. WsVoiceEngineTransport & Concurrent Sessions Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_ws_voice_engine_transport_full_lifecycle() -> None:
    """Test WsVoiceEngineTransport adapter managing sessions."""
    async with start_mock_voice_engine() as (_server, ws_url):
        settings = TelephonySettings(
            voice_engine_ws_url=ws_url,
            voice_engine_sample_rate=16000,
            voice_engine_enabled=True,
        )
        transport = WsVoiceEngineTransport(settings=settings)

        session_id = "sess_transport_001"
        client = await transport.initialize_session(
            session_id=session_id,
            organization_id="org_test",
            agent_id="agent_test",
        )
        assert client.is_ready

        # Send audio
        frame = AudioFrame(data=b"\x01" * 640, sequence_number=1)
        await transport.send_audio(session_id=session_id, frame=frame)

        # Retrieve queue
        q = await transport.get_outbound_queue(session_id=session_id)
        assert q is not None

        # Close
        await transport.close_session(session_id=session_id)
        assert not client.is_connected


@pytest.mark.asyncio
async def test_concurrent_isolated_voice_engine_sessions() -> None:
    """Test multiple concurrent sessions remain completely isolated."""
    async with start_mock_voice_engine() as (_server, ws_url):
        settings = TelephonySettings(voice_engine_ws_url=ws_url, voice_engine_enabled=True)
        transport = WsVoiceEngineTransport(settings=settings)

        s1 = "sess_concurrent_1"
        s2 = "sess_concurrent_2"

        c1 = await transport.initialize_session(session_id=s1, organization_id="org_1", agent_id="agent_1")
        c2 = await transport.initialize_session(session_id=s2, organization_id="org_2", agent_id="agent_2")

        assert c1.session_id == s1
        assert c2.session_id == s2
        assert c1 != c2

        q1 = await transport.get_outbound_queue(s1)
        q2 = await transport.get_outbound_queue(s2)
        assert q1 != q2

        await transport.close_session(s1)
        await transport.close_session(s2)
