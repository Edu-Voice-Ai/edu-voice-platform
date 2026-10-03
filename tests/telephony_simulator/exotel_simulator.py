"""Exotel AgentStream Wire Protocol Simulator (TEST ONLY).

Extends the local telephony sandbox to simulate actual Exotel AgentStream
bidirectional WebSocket envelopes: connected, start, media, dtmf, clear, stop.
"""

import base64
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from backend.app.services.telephony.audio_codec import pcm16_to_mulaw
from tests.telephony_simulator.synthetic_audio import SyntheticAudioGenerator


@dataclass
class ExotelSimulationResult:
    """Diagnostic outcome of an Exotel AgentStream simulated call session."""

    call_sid: str
    stream_sid: str
    session_id: str
    events_sent: list[str] = field(default_factory=list)
    events_received: list[dict[str, Any]] = field(default_factory=list)
    outbound_media_received: int = 0
    clear_received: int = 0
    success: bool = True
    error_message: str | None = None


class ExotelAgentStreamSimulator:
    """Client simulator producing and asserting native Exotel AgentStream WebSocket frames."""

    def __init__(
        self,
        stream_sid: str = "exotel_stream_test_001",
        call_sid: str = "exotel_call_test_001",
        from_number: str = "+919876543210",
        to_number: str = "+912249360001",
    ) -> None:
        self.stream_sid = stream_sid
        self.call_sid = call_sid
        self.from_number = from_number
        self.to_number = to_number
        self.audio_gen = SyntheticAudioGenerator()

    def build_connected_packet(self) -> dict[str, Any]:
        """Build Exotel 'connected' handshake event."""
        return {"event": "connected"}

    def build_start_packet(self) -> dict[str, Any]:
        """Build Exotel 'start' metadata event."""
        return {
            "event": "start",
            "streamSid": self.stream_sid,
            "start": {
                "streamSid": self.stream_sid,
                "callSid": self.call_sid,
                "from": self.from_number,
                "to": self.to_number,
                "direction": "inbound",
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "channels": 1,
                },
                "customParameters": {
                    "campaign": "admissions_2026",
                },
            },
        }

    def build_media_packet(self, pcm_bytes: bytes | None = None) -> dict[str, Any]:
        """Build Exotel 'media' audio envelope with base64-encoded mu-law audio."""
        if pcm_bytes is None:
            synth = self.audio_gen.generate_caller_audio_frame(sequence=1)
            # Convert 16-bit linear PCM to mu-law bytes for telecom carrier simulation
            carrier_bytes = pcm16_to_mulaw(synth.raw_bytes)
        else:
            carrier_bytes = pcm16_to_mulaw(pcm_bytes)

        payload_b64 = base64.b64encode(carrier_bytes).decode("ascii")
        return {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {
                "payload": payload_b64,
            },
        }

    def build_dtmf_packet(self, digit: str = "5") -> dict[str, Any]:
        """Build Exotel 'dtmf' keypress event."""
        return {
            "event": "dtmf",
            "streamSid": self.stream_sid,
            "dtmf": {
                "digit": digit,
            },
        }

    def build_clear_packet(self) -> dict[str, Any]:
        """Build Exotel 'clear' acknowledgement event."""
        return {
            "event": "clear",
            "streamSid": self.stream_sid,
        }

    def build_stop_packet(self) -> dict[str, Any]:
        """Build Exotel 'stop' call termination event."""
        return {
            "event": "stop",
            "streamSid": self.stream_sid,
            "stop": {
                "callSid": self.call_sid,
            },
        }

    def simulate_call_flow(
        self,
        client: TestClient,
        session_id: str,
        send_media_frames: int = 3,
        send_dtmf: str | None = "1",
    ) -> ExotelSimulationResult:
        """Run complete simulated Exotel AgentStream session over FastAPI TestClient."""
        result = ExotelSimulationResult(
            call_sid=self.call_sid,
            stream_sid=self.stream_sid,
            session_id=session_id,
        )

        ws_path = f"/ws/telephony/stream/{session_id}"
        with client.websocket_connect(ws_path) as ws:
            # 1. Send 'connected'
            conn_pkt = self.build_connected_packet()
            ws.send_text(json.dumps(conn_pkt))
            result.events_sent.append("connected")

            # 2. Send 'start'
            start_pkt = self.build_start_packet()
            ws.send_text(json.dumps(start_pkt))
            result.events_sent.append("start")

            # 3. Send caller 'media' frames
            for _ in range(send_media_frames):
                media_pkt = self.build_media_packet()
                ws.send_text(json.dumps(media_pkt))
                result.events_sent.append("media")

            # 4. Optional DTMF
            if send_dtmf:
                dtmf_pkt = self.build_dtmf_packet(digit=send_dtmf)
                ws.send_text(json.dumps(dtmf_pkt))
                result.events_sent.append("dtmf")

            # 5. Send 'stop'
            stop_pkt = self.build_stop_packet()
            ws.send_text(json.dumps(stop_pkt))
            result.events_sent.append("stop")

        return result
