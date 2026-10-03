import asyncio
import base64
import json
import time
import wave
import websockets

def get_16k_pcm():
    with wave.open("handoff_test.wav", "rb") as w:
        orig_rate = w.getframerate()
        frames = w.readframes(w.getnframes())
    
    # Resample from orig_rate to 16000
    try:
        import audioop
        resampled, _ = audioop.ratecv(frames, 2, 1, orig_rate, 16000, None)
        return resampled
    except ImportError:
        # Python 3.12+ deprecated audioop or use scipy/custom
        import numpy as np
        samples = np.frombuffer(frames, dtype=np.int16)
        num_target = int(len(samples) * 16000 / orig_rate)
        resampled = np.interp(
            np.linspace(0, len(samples), num_target, endpoint=False),
            np.arange(len(samples)),
            samples
        ).astype(np.int16)
        return resampled.tobytes()

async def test_handoff():
    pcm_16k = get_16k_pcm()
    print(f"Loaded {len(pcm_16k)} bytes of 16kHz PCM audio (~{len(pcm_16k)/32000:.2f}s)")

    uri = "wss://voice-test.gentechs.in/ws/voice"
    session_id = f"test_hh_{int(time.time())}"
    call_id = f"call_hh_{int(time.time())}"

    start_payload = {
        "event": "session.start",
        "session_id": session_id,
        "call_id": call_id,
        "organization_id": "a0000000-0000-0000-0000-000000000001",
        "agent_id": "c0000000-0000-0000-0000-000000000001",
        "business_name": "Apex Engineering College",
        "agent_name": "Maya",
        "language": "en-IN",
        "call_direction": "inbound",
        "template_type": "education",
        "client_sample_rate": 16000
    }

    async with websockets.connect(uri) as ws:
        print("Connected to Voice Engine")
        await ws.send(json.dumps(start_payload))
        print("Sent session.start")

        # 1. Wait for greeting response.end
        print("Waiting for greeting response.end...")
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
            evt = json.loads(msg)
            event_type = evt.get("event")
            if event_type == "response.end":
                print("Greeting complete!")
                break

        # 2. Stream audio of 'I want to talk to a human'
        print("Streaming 'I want to talk to a human'...")
        chunk_size = 640
        seq = 0
        for i in range(0, len(pcm_16k), chunk_size):
            chunk = pcm_16k[i:i+chunk_size]
            if len(chunk) < chunk_size:
                chunk += b"\x00" * (chunk_size - len(chunk))
            seq += 1
            b64_chunk = base64.b64encode(chunk).decode("ascii")
            await ws.send(json.dumps({
                "event": "audio.input",
                "data": b64_chunk,
                "seq": seq
            }))
            await asyncio.sleep(0.02)

        # 3. Stream 1 second of silence
        print("Streaming 1.0s silence for VAD...")
        silence = b"\x00" * chunk_size
        b64_silence = base64.b64encode(silence).decode("ascii")
        for _ in range(50):
            seq += 1
            await ws.send(json.dumps({
                "event": "audio.input",
                "data": b64_silence,
                "seq": seq
            }))
            await asyncio.sleep(0.02)

        # 4. Receive and display all events
        print("Waiting for turn events...")
        t0 = time.time()
        text_deltas = []
        while time.time() - t0 < 12.0:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=4.0)
            except asyncio.TimeoutError:
                print("Timeout waiting for more events.")
                break

            evt = json.loads(msg)
            event_type = evt.get("event")
            data = evt.get("data", {})
            if event_type == "response.text.delta":
                delta = data.get("delta", "")
                text_deltas.append(delta)
                print(f"[EVENT: response.text.delta] '{delta}'")
            elif event_type == "audio.output":
                pass  # suppress audio chunk noise
            else:
                print(f"[EVENT: {event_type}] payload keys: {list(evt.keys())}, data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                print(f"       Full event: {json.dumps(evt)[:300]}")

            if event_type == "response.end":
                print(f"Turn 1 finished. Full response text: '{''.join(text_deltas)}'")
                break

        # 5. Turn 2: Now that language is selected, say 'I want to talk to a human' again!
        print("\n--- TURN 2: Saying 'I want to talk to a human' now that language is active ---")
        seq = 100
        for i in range(0, len(pcm_16k), chunk_size):
            chunk = pcm_16k[i:i+chunk_size]
            if len(chunk) < chunk_size:
                chunk += b"\x00" * (chunk_size - len(chunk))
            seq += 1
            b64_chunk = base64.b64encode(chunk).decode("ascii")
            await ws.send(json.dumps({
                "event": "audio.input",
                "data": b64_chunk,
                "seq": seq
            }))
            await asyncio.sleep(0.02)

        print("Streaming 1.0s silence for Turn 2 VAD...")
        for _ in range(50):
            seq += 1
            await ws.send(json.dumps({
                "event": "audio.input",
                "data": b64_silence,
                "seq": seq
            }))
            await asyncio.sleep(0.02)

        print("Waiting for Turn 2 events...")
        t0 = time.time()
        text_deltas_2 = []
        while time.time() - t0 < 15.0:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            except asyncio.TimeoutError:
                print("Timeout waiting for Turn 2 events.")
                break

            evt = json.loads(msg)
            event_type = evt.get("event")
            data = evt.get("data", {})
            if event_type == "response.text.delta":
                delta = data.get("delta", "")
                text_deltas_2.append(delta)
                print(f"[TURN 2 EVENT: response.text.delta] '{delta}'")
            elif event_type == "audio.output":
                pass
            else:
                print(f"[TURN 2 EVENT: {event_type}] payload keys: {list(evt.keys())}, data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                print(f"       Full event: {json.dumps(evt)[:400]}")

            if event_type == "response.end":
                print(f"Turn 2 finished. Full response text: '{''.join(text_deltas_2)}'")
                break


if __name__ == "__main__":
    asyncio.run(test_handoff())
