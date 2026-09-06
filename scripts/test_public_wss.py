"""Test Public Exotel WSS Connectivity (Section 10).

Connects over the public internet to:
https://gateway.gentechs.in/api/v1/telephony/exotel/resolve
and tests the returned WSS URL:
- WebSocket upgrade succeeds
- 'connected' accepted
- 'start' accepted
- 'media' accepted
- 'stop' accepted
- clean disconnect
"""

import asyncio
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

import websockets

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.services.telephony.audio_codec import pcm16_to_mulaw


def _sync_fetch_resolver(req: urllib.request.Request) -> dict:
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Resolver returned HTTP {resp.status}")
        return json.loads(resp.read().decode("utf-8"))


async def run_public_wss_test() -> bool:
    print("=" * 60)
    print("TESTING PUBLIC EXOTEL RESOLVER & WSS ENDPOINT")
    print("=" * 60)

    call_sid = "test_public_probe_99"
    stream_sid = "stream_public_probe_99"
    caller = "+919876543210"
    destination = "022-493-60001"

    # 1. Resolve via public HTTPS endpoint
    resolve_url = (
        f"https://gateway.gentechs.in/api/v1/telephony/exotel/resolve"
        f"?CallSid={call_sid}&CallFrom={urllib.parse.quote_plus(caller)}"
        f"&CallTo={urllib.parse.quote_plus(destination)}&Direction=inbound"
    )
    print(f"[1] Calling public resolver: {resolve_url}")

    req = urllib.request.Request(
        resolve_url,
        headers={"User-Agent": "Exotel-VoiceBot/1.0", "Accept": "application/json"},
    )
    try:
        data = await asyncio.to_thread(_sync_fetch_resolver, req)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: Resolver request failed: {exc}")
        return False

    wss_url = data.get("url")
    print(f"[2] Received WSS URL: {wss_url}")
    if not wss_url or not wss_url.startswith("wss://gateway.gentechs.in/ws/telephony/stream/"):
        print(f"FAILED: Invalid WSS URL format: {wss_url}")
        return False

    # 2. Connect over public WSS
    print(f"[3] Connecting to public WebSocket: {wss_url} ...")
    async with websockets.connect(
        wss_url,
        user_agent_header="Exotel-VoiceBot/1.0",
        open_timeout=15,
        close_timeout=10,
    ) as ws:
        print("    -> WebSocket connection & TLS upgrade SUCCEEDED!")

        received_media_count = 0
        first_payload_sample = None
        stop_receiving = asyncio.Event()

        async def receive_loop() -> None:
            nonlocal received_media_count, first_payload_sample
            try:
                while not stop_receiving.is_set():
                    msg_text = await ws.recv()
                    data = json.loads(msg_text)
                    event = data.get("event")
                    if event == "media":
                        received_media_count += 1
                        if received_media_count == 1:
                            first_payload_sample = data
                            print(f"    -> [OUTBOUND EXOTEL MEDIA RECEIVED] streamSid={data.get('streamSid')}, payload_len={len(data.get('media', {}).get('payload', ''))}")
                    elif event == "clear":
                        print(f"    -> [OUTBOUND CLEAR RECEIVED] streamSid={data.get('streamSid')}")
            except (websockets.ConnectionClosed, asyncio.CancelledError):
                pass

        reader_task = asyncio.create_task(receive_loop())

        try:
            # 3. Send connected
            print("[4] Sending 'connected' event...")
            await ws.send(json.dumps({"event": "connected"}))
            await asyncio.sleep(0.1)

            # 4. Send start
            print("[5] Sending 'start' event...")
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
            await ws.send(json.dumps(start_payload))
            await asyncio.sleep(0.5)

            # 5. Send media
            print("[6] Sending synthetic 'media' frame (mu-law 8kHz)...")
            pcm16 = b"\x00\x00\x30\x00\x60\x00\x30\x00" * 80
            mulaw = pcm16_to_mulaw(pcm16)
            payload_b64 = base64.b64encode(mulaw).decode("ascii")
            media_packet = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": payload_b64,
                },
            }
            await ws.send(json.dumps(media_packet))
            await asyncio.sleep(1.0)

            # 6. Send stop
            print("[7] Sending 'stop' event...")
            stop_payload = {
                "event": "stop",
                "streamSid": stream_sid,
                "stop": {
                    "callSid": call_sid,
                },
            }
            await ws.send(json.dumps(stop_payload))
            await asyncio.sleep(0.5)
        finally:
            stop_receiving.set()
            reader_task.cancel()
            await asyncio.gather(reader_task, return_exceptions=True)

    print(f"[8] Disconnected cleanly! (Total outbound Exotel media envelopes received: {received_media_count})")
    if first_payload_sample:
        assert first_payload_sample.get("event") == "media"
        assert first_payload_sample.get("streamSid") == stream_sid
        assert "payload" in first_payload_sample.get("media", {})
        print("    -> Outbound Exotel envelope structure verified against specification!")
    print("=" * 60)
    print("PUBLIC WSS TEST: SUCCESS")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_public_wss_test())
    sys.exit(0 if success else 1)
