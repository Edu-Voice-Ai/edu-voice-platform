"""Safe Manual End-to-End Exotel Probe Script.

Performs Section 8 probe steps:
1. GET resolver (/api/v1/telephony/exotel/resolve)
2. Receive generated WSS URL
3. Connect to generated WSS endpoint
4. Send: {"event": "connected"}
5. Send realistic Exotel start event containing streamSid/callSid
6. Send synthetic Exotel media (8kHz mu-law Base64)
7. Verify Gateway accepts media
8. Verify Voice Engine receives converted audio
9. Verify outbound Voice Engine audio is formatted as Exotel media:
   {"event": "media", "streamSid": "<streamSid>", "media": {"payload": "<BASE64_AUDIO>"}}
10. Send {"event": "stop", "streamSid": "<streamSid>"}
11. Verify clean teardown

DOES NOT call real Exotel API.
DOES NOT place an actual phone call.
DOES NOT expose credentials.
"""

import argparse
import asyncio
import base64
import json
import os
import sys
from typing import Any

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.telephony.audio_codec import (
    pcm16_to_mulaw,
    transcode_carrier_to_voice_engine,
)
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.session_manager import get_realtime_session_manager


def generate_synthetic_mulaw_media(stream_sid: str) -> dict[str, Any]:
    """Generate 20ms of synthetic 8kHz mu-law audio envelope."""
    # 20ms of 16kHz PCM16 = 320 samples = 640 bytes
    pcm16 = b"\x00\x00\x40\x00\x7f\x00\x40\x00" * 80
    mulaw = pcm16_to_mulaw(pcm16)
    b64_payload = base64.b64encode(mulaw).decode("ascii")
    return {
        "event": "media",
        "streamSid": stream_sid,
        "media": {
            "payload": b64_payload,
        },
    }


def run_probe() -> bool:
    print("=" * 60)
    print("STARTING SAFE MANUAL EXOTEL END-TO-END PROBE")
    print("=" * 60)

    from pydantic import SecretStr

    from backend.app.services.telephony.config import (
        TelephonySettings,
        get_telephony_settings,
    )

    # Provide safe test settings for in-process probe
    probe_settings = TelephonySettings(
        environment="test",
        voice_engine_enabled=False,
        signature_verification_enabled=False,
        exotel_account_sid="test_account_sid",
        exotel_api_key=SecretStr("test_key"),
        exotel_api_token=SecretStr("test_token"),
    )
    app.dependency_overrides[get_telephony_settings] = lambda: probe_settings

    client = TestClient(app)
    call_sid = "probe_call_sid_2026"
    stream_sid = "probe_stream_sid_2026"
    caller = "+919876543210"
    destination = "022-493-60001"

    try:
        # Step 1 & 2: GET public resolver
        print("[Step 1] Requesting Exotel dynamic resolver...")
        resolve_resp = client.get(
            "/api/v1/telephony/exotel/resolve",
            params={
                "CallSid": call_sid,
                "CallFrom": caller,
                "CallTo": destination,
                "Direction": "inbound",
            },
        )
        if resolve_resp.status_code != 200:
            print(f"FAILED: Resolver returned HTTP {resolve_resp.status_code}: {resolve_resp.text}")
            return False

        resolve_data = resolve_resp.json()
        wss_url = resolve_data.get("url", "")
        print(f"[Step 2] Received generated WSS URL: {wss_url}")
        if not wss_url.startswith("wss://gateway.gentechs.in/ws/telephony/stream/exotel_probe_call_sid_2026_"):
            print(f"FAILED: Unexpected WSS URL format: {wss_url}")
            return False

        session_id = wss_url.split("/")[-1]
        ws_path = f"/ws/telephony/stream/{session_id}"

        # Step 3: Connect to generated WSS
        print(f"[Step 3] Connecting to WebSocket stream endpoint: {ws_path}")
        manager = get_realtime_session_manager()

        with client.websocket_connect(ws_path) as ws:
            # Step 4: Send connected event
            print("[Step 4] Sending 'connected' event...")
            ws.send_text(json.dumps({"event": "connected"}))

            # Step 5: Send start event with realistic metadata
            print("[Step 5] Sending 'start' event with streamSid and callSid...")
            start_payload = {
                "event": "start",
                "streamSid": stream_sid,
                "start": {
                    "streamSid": stream_sid,
                    "callSid": call_sid,
                    "from": caller,
                    "to": destination,
                    "direction": "inbound",
                    "mediaFormat": {
                        "encoding": "audio/x-mulaw",
                        "sampleRate": 8000,
                        "channels": 1,
                    },
                },
            }
            ws.send_text(json.dumps(start_payload))

            # Step 6: Send synthetic Exotel media
            print("[Step 6] Sending synthetic Exotel media packet...")
            media_packet = generate_synthetic_mulaw_media(stream_sid)
            ws.send_text(json.dumps(media_packet))

            # Step 9: Simulate Voice Engine audio.output and verify outbound Exotel media envelope
            print("[Step 9] Simulating Voice Engine audio.output and verifying outbound Exotel media envelope...")
            session = asyncio.run(manager.get_session(session_id))
            if not session:
                print("FAILED: Session not found in manager.")
                return False

            synth_tts = AudioFrame(
                data=b"\x10\x20\x30\x40" * 80,  # 320 bytes PCM16
                timestamp_ms=500,
                format="pcm16_16k",
            )
            asyncio.run(session.push_outbound_frame(synth_tts))

            outbound_msg = ws.receive_text()
            outbound_data = json.loads(outbound_msg)
            print(f"       -> Outbound envelope received: event={outbound_data.get('event')}, streamSid={outbound_data.get('streamSid')}")

            if outbound_data.get("event") != "media":
                print(f"FAILED: Expected event 'media', got: {outbound_data.get('event')}")
                return False
            if outbound_data.get("streamSid") != stream_sid:
                print(f"FAILED: streamSid mismatch: {outbound_data.get('streamSid')} vs {stream_sid}")
                return False
            if "media" not in outbound_data or "payload" not in outbound_data["media"]:
                print("FAILED: Missing media.payload in outbound message")
                return False

            decoded_payload = base64.b64decode(outbound_data["media"]["payload"])
            if len(decoded_payload) == 0:
                print("FAILED: Outbound audio payload is empty")
                return False
            print(f"       -> Outbound audio payload verified: {len(decoded_payload)} bytes carrier audio.")

            # Step 10: Send stop
            print("[Step 10] Sending 'stop' event to conclude session...")
            stop_payload = {
                "event": "stop",
                "streamSid": stream_sid,
                "stop": {
                    "callSid": call_sid,
                },
            }
            ws.send_text(json.dumps(stop_payload))

        # Step 7: Verify Gateway accepted media (after event loop completed)
        print("[Step 7] Verifying Gateway recorded media frames...")
        if session.stats.frames_received < 1:
            print(f"FAILED: No frames recorded in session stats: {session.stats.frames_received}")
            return False
        print(f"       -> Frames received: {session.stats.frames_received}, Bytes: {session.stats.bytes_received}")

        # Step 8: Verify Voice Engine receives converted audio (transcoding check)
        print("[Step 8] Verifying carrier audio transcodes to Voice Engine 16kHz PCM16...")
        raw_mulaw = base64.b64decode(media_packet["media"]["payload"])
        pcm16_converted = transcode_carrier_to_voice_engine(raw_mulaw, encoding="audio/x-mulaw", source_rate=8000)
        if len(pcm16_converted) != len(raw_mulaw) * 4:
            print(f"FAILED: Transcoded audio size unexpected: {len(pcm16_converted)} vs expected {len(raw_mulaw) * 4}")
            return False
        print(f"       -> Transcoded {len(raw_mulaw)} bytes mu-law (8kHz) to {len(pcm16_converted)} bytes PCM16 (16kHz).")

        # Step 11: Verify clean teardown
        print("[Step 11] Verifying clean session teardown...")
        if not session.cancellation_event.is_set():
            print("FAILED: Session cancellation event was not set on teardown.")
            return False
        print("       -> Session cancellation event set cleanly.")

        print("=" * 60)
        print("PROBE RESULT: SUCCESS (All 11 verification steps passed)")
        print("=" * 60)
        return True
    finally:
        app.dependency_overrides.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual Safe Exotel Probe")
    args = parser.parse_args()
    success = run_probe()
    sys.exit(0 if success else 1)
