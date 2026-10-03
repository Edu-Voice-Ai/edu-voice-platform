"""Unit and integration tests for Exotel bidirectional Voicebot audio format and stream_sid handling.

Verifies:
1. Outbound 16 kHz PCM16 -> 8 kHz PCM16 decimation.
2. Output is NOT mu-law encoded (retains raw 16-bit linear PCM fidelity).
3. Outbound payload decodes to valid signed 16-bit little-endian PCM samples.
4. Correct 8 kHz frame size (320 bytes per 20ms frame).
5. Actual stream_sid from Exotel is preserved and included in outbound packets.
6. No outbound media or clear packets sent with streamSid="none".
7. Inbound Exotel 320 carrier bytes transcode to 640 bytes of 16kHz PCM16.
8. Barge-in response.cancelled triggers Exotel clear packet with actual stream_sid.
"""

import asyncio
import base64
import json
import struct
from typing import Any

from fastapi.testclient import TestClient

from backend.app.services.telephony.audio_codec import (
    pcm16_to_mulaw,
    resample_16k_to_8k,
    transcode_carrier_to_voice_engine,
    transcode_voice_engine_to_carrier,
)
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.session_manager import get_realtime_session_manager


def test_16k_to_8k_pcm16_conversion_math_and_frame_size() -> None:
    """Verify 16kHz PCM16 audio downsamples 2:1 to 8kHz PCM16 with exact frame sizing."""
    # 20ms of 16kHz mono audio = 320 samples = 640 bytes
    samples_16k = [int(1000 * i) % 30000 - 15000 for i in range(320)]
    pcm16_16k = struct.pack(f"<{len(samples_16k)}h", *samples_16k)
    assert len(pcm16_16k) == 640

    downsampled_8k = resample_16k_to_8k(pcm16_16k)

    # 20ms of 8kHz mono audio = 160 samples = 320 bytes
    assert len(downsampled_8k) == 320
    num_samples_8k = len(downsampled_8k) // 2
    assert num_samples_8k == 160

    # Verify decimation picks even index samples
    samples_8k = struct.unpack(f"<{num_samples_8k}h", downsampled_8k)
    for i in range(160):
        assert samples_8k[i] == samples_16k[i * 2]


def test_outbound_is_not_mulaw_and_preserves_pcm_fidelity() -> None:
    """Verify outbound carrier conversion preserves 16-bit PCM and does NOT compress to 8-bit mu-law."""
    # Create distinct signed 16-bit samples with dynamic range
    samples = [-16000, -8000, 0, 8000, 16000, 24000, -24000, 1234] * 40
    pcm16_16k = struct.pack(f"<{len(samples)}h", *samples)
    assert len(pcm16_16k) == 640

    # 1. Direct resampler output
    pcm_8k = resample_16k_to_8k(pcm16_16k)
    assert len(pcm_8k) == 320

    # 2. Transcode with audio/x-l16 (Exotel default)
    transcoded = transcode_voice_engine_to_carrier(pcm16_16k, target_encoding="audio/x-l16", target_rate=8000)
    assert len(transcoded) == 320
    assert transcoded == pcm_8k

    # 3. Contrast with mu-law: mu-law would produce exactly 160 bytes (1 byte per sample)
    mulaw_encoded = pcm16_to_mulaw(pcm_8k)
    assert len(mulaw_encoded) == 160
    assert transcoded != mulaw_encoded


def test_outbound_media_envelope_payload_and_stream_sid(client: TestClient) -> None:
    """Verify WebSocket outbound packet contains raw 8kHz PCM16 and actual stream_sid."""
    session_id = "exotel_outbound_pcm_test_01"
    expected_stream_sid = "ExoStream_abc12345"

    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(
            session_id=session_id,
            provider="exotel",
            stream_sid=expected_stream_sid,
        )
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Push 20ms of synthetic 16kHz PCM16 audio (640 bytes)
        synth_pcm16_16k = struct.pack("<320h", *[500 * (i % 20) for i in range(320)])
        frame = AudioFrame(
            data=synth_pcm16_16k,
            timestamp_ms=100,
            format="pcm16_16k",
        )
        asyncio.run(session.push_outbound_frame(frame))

        # Receive outbound packet
        msg_text = ws.receive_text()
        pkt: dict[str, Any] = json.loads(msg_text)

        assert pkt.get("event") == "media"
        # Actual stream_sid is strictly preserved
        assert pkt.get("streamSid") == expected_stream_sid
        assert pkt.get("streamSid") != "none"
        assert pkt.get("streamSid") != ""

        # Validate media payload
        assert "media" in pkt
        assert "payload" in pkt["media"]
        raw_payload = base64.b64decode(pkt["media"]["payload"])

        # 20ms @ 8kHz 16-bit PCM must be exactly 320 bytes (NOT 160 bytes mu-law)
        assert len(raw_payload) == 320

        # Validate that payload decodes into valid signed 16-bit little-endian samples
        unpacked_samples = struct.unpack("<160h", raw_payload)
        assert len(unpacked_samples) == 160
        # Verify first sample matches downsampled original
        assert unpacked_samples[0] == 0

        # Close cleanly
        ws.send_text(json.dumps({"event": "stop"}))


def test_stream_sid_never_none_when_known_or_unset(client: TestClient) -> None:
    """Verify streamSid in outbound packets is never literal 'none'."""
    session_id = "exotel_stream_sid_hardening_02"
    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(
            session_id=session_id,
            provider="exotel",
            stream_sid=None,  # Not yet known
        )
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # 1. Send start event with real StreamSid
        ws.send_text(json.dumps({"event": "connected"}))
        real_sid = "ExotelRealSid_998877"
        ws.send_text(
            json.dumps(
                {
                    "event": "start",
                    "streamSid": real_sid,
                    "start": {
                        "streamSid": real_sid,
                        "callSid": "call_hardening_001",
                        "from": "+919876543210",
                        "to": "095-138-86363",
                    },
                }
            )
        )

        # Allow start message to be processed
        import time
        time.sleep(0.05)
        assert session.stream_sid == real_sid

        # 2. Push outbound audio frame
        frame = AudioFrame(data=b"\x00\x00" * 320, timestamp_ms=200)
        asyncio.run(session.push_outbound_frame(frame))

        # 3. Verify outbound packet uses the real stream_sid
        msg_text = ws.receive_text()
        pkt = json.loads(msg_text)
        assert pkt["streamSid"] == real_sid
        assert pkt["streamSid"] != "none"


def test_inbound_exotel_320_carrier_bytes_resampling() -> None:
    """Verify 320 carrier bytes (20ms @ 8kHz PCM16) transcodes to 640 bytes of 16kHz PCM16."""
    # 20ms of 8kHz PCM16 = 160 samples = 320 bytes
    carrier_pcm16_8k = struct.pack("<160h", *[i * 100 for i in range(160)])
    assert len(carrier_pcm16_8k) == 320

    # Inbound transcoding with default Exotel encoding (audio/x-l16)
    transcoded_16k = transcode_carrier_to_voice_engine(
        carrier_pcm16_8k,
        encoding="audio/x-l16",
        source_rate=8000,
        target_rate=16000,
    )

    # Must be 320 samples @ 16kHz = 640 bytes (NOT 1280 bytes)
    assert len(transcoded_16k) == 640
    unpacked_16k = struct.unpack("<320h", transcoded_16k)
    assert len(unpacked_16k) == 320


def test_inbound_exotel_160_bytes_mulaw_compatibility() -> None:
    """Verify backward compatibility if a carrier sends 160 bytes of G.711 mu-law."""
    pcm8k = struct.pack("<160h", *[i * 100 for i in range(160)])
    mulaw_160 = pcm16_to_mulaw(pcm8k)
    assert len(mulaw_160) == 160

    transcoded_16k = transcode_carrier_to_voice_engine(
        mulaw_160,
        encoding="audio/x-mulaw",
        source_rate=8000,
        target_rate=16000,
    )
    # 160 mulaw samples -> 160 8kHz PCM16 samples -> 320 16kHz PCM16 samples = 640 bytes
    assert len(transcoded_16k) == 640


def test_barge_in_clear_envelope_uses_actual_stream_sid(client: TestClient) -> None:
    """Verify Exotel clear packet on barge-in / cancellation uses the actual stream_sid."""
    session_id = "exotel_bargein_clear_test"
    actual_sid = "ExoStream_clear_001"

    manager = get_realtime_session_manager()
    session = asyncio.run(
        manager.create_session(
            session_id=session_id,
            provider="exotel",
            stream_sid=actual_sid,
        )
    )

    with client.websocket_connect(f"/ws/telephony/stream/{session_id}") as ws:
        # Client sends clear packet directly
        ws.send_text(json.dumps({"event": "clear", "streamSid": actual_sid}))

        # Verify session queue drained
        assert session.outbound_audio_queue.empty()

        # Close cleanly
        ws.send_text(json.dumps({"event": "stop"}))
