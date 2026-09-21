"""Integration tests for Realtime WebSocket Audio Gateway."""

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.services.telephony.frames import (
    AudioFrame,
    FrameType,
    InternalAudioMessage,
)
from backend.app.services.telephony.mock_stream import MockAudioStreamClient
from backend.app.services.telephony.session_manager import get_realtime_session_manager


def test_websocket_connection_and_session_association(client: TestClient) -> None:
    """Test 6 & 7: Successful WebSocket connection and session attachment."""
    session_id = "ws_test_sess_01"
    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Send a ping and receive pong to verify active connection
        mock = MockAudioStreamClient(session_id)
        ping_msg = mock.create_ping_message()
        ws.send_text(ping_msg.to_json_str())

        response_raw = ws.receive_text()
        response_data = json.loads(response_raw)
        assert response_data["type"] == FrameType.PONG


def test_inbound_audio_frame_intake(client: TestClient) -> None:
    """Test 8: Receiving caller audio frame and enqueueing to inbound queue."""
    session_id = "ws_test_sess_inbound"
    manager = get_realtime_session_manager()

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        mock = MockAudioStreamClient(session_id)
        audio_msg = mock.create_mock_inbound_message(
            payload_bytes=b"raw_caller_pcm_audio_chunk"
        )
        ws.send_text(audio_msg.to_json_str())

        # Send ping/pong as barrier synchronization
        ws.send_text(mock.create_ping_message().to_json_str())
        ws.receive_text()

    # Session inbound queue should have received frame
    session = manager._sessions.get(session_id)
    assert session is not None
    assert session.stats.frames_received >= 1


def test_outbound_audio_frame_streaming(client: TestClient) -> None:
    """Test 9: Streaming synthesized audio frames from outbound queue to WebSocket."""
    session_id = "ws_test_sess_outbound"
    manager = get_realtime_session_manager()

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        session = manager._sessions.get(session_id)
        assert session is not None

        # Put outbound frame into session queue
        out_frame = AudioFrame(
            data=b"bot_synthesized_speech_bytes",
            sequence_number=1,
            timestamp_ms=20,
        )
        session.outbound_audio_queue.put_nowait(out_frame)

        # Receive frame on WebSocket client
        raw_msg = ws.receive_text()
        msg_dict = json.loads(raw_msg)
        assert msg_dict["type"] == FrameType.AUDIO
        assert msg_dict["sequence_number"] == 1

        decoded_msg = InternalAudioMessage.model_validate(msg_dict)
        frame_received = decoded_msg.to_audio_frame()
        assert frame_received.data == b"bot_synthesized_speech_bytes"


def test_bidirectional_audio_exchange(client: TestClient) -> None:
    """Test 10: Simultaneous bidirectional audio send and receive."""
    session_id = "ws_test_sess_bidirectional"
    manager = get_realtime_session_manager()

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        session = manager._sessions.get(session_id)
        assert session is not None

        mock = MockAudioStreamClient(session_id)

        # 1. Send inbound frame
        in_msg = mock.create_mock_inbound_message(payload_bytes=b"inbound_chunk_1")
        ws.send_text(in_msg.to_json_str())

        # 2. Queue outbound frame
        out_frame = AudioFrame(data=b"outbound_chunk_1", sequence_number=10)
        session.outbound_audio_queue.put_nowait(out_frame)

        # 3. Receive outbound frame on client
        out_raw = ws.receive_text()
        out_parsed = json.loads(out_raw)
        assert out_parsed["sequence_number"] == 10

        # Synchronize
        ws.send_text(mock.create_ping_message().to_json_str())
        ws.receive_text()

    assert session.stats.frames_sent >= 1
    assert session.stats.frames_received >= 1


def test_duplicate_connection_rejected(client: TestClient) -> None:
    """Test 17: Second concurrent connection to same session is rejected with 1008."""
    session_id = "ws_test_sess_duplicate"

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}"):
        # Attempt second connection while first is active
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(f"/ws/telephony/stream/{session_id}"),
        ):
            pass
        assert exc_info.value.code == 1008


def test_client_disconnect_and_cleanup_no_orphaned_tasks(client: TestClient) -> None:
    """Test 14 & 20: Disconnect cleans up without leaving orphaned tasks."""
    session_id = "ws_test_sess_cleanup"
    manager = get_realtime_session_manager()

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        session = manager._sessions.get(session_id)
        assert session is not None
        # Tasks are active during connection (inbound, outbound, heartbeat)
        assert len(session.active_tasks) >= 2
        ws.close()

    # After exit, active tasks should be cleared
    assert len(session.active_tasks) == 0
    assert session.active_websocket is None


def test_server_side_cancellation(client: TestClient) -> None:
    """Test 15: Server-side cancellation shuts down active WebSocket tasks gracefully."""
    session_id = "ws_test_sess_server_cancel"
    manager = get_realtime_session_manager()

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        session = manager._sessions.get(session_id)
        assert session is not None

        # Trigger server cancellation event
        session.cancellation_event.set()

        # Send ping to wake receiver loop
        mock = MockAudioStreamClient(session_id)
        ws.send_text(mock.create_ping_message().to_json_str())


def test_malformed_frame_handling(client: TestClient) -> None:
    """Test 18: Malformed frame payload is ignored without crashing gateway loop."""
    session_id = "ws_test_sess_malformed"

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Send corrupted non-JSON message
        ws.send_text("THIS_IS_NOT_VALID_JSON_!!!")

        # Connection should stay alive; verify with ping/pong
        mock = MockAudioStreamClient(session_id)
        ws.send_text(mock.create_ping_message().to_json_str())
        resp = ws.receive_text()
        assert json.loads(resp)["type"] == FrameType.PONG
