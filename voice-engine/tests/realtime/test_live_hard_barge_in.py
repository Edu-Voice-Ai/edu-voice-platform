import asyncio
import sys
import os
import json
import time
import websockets

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.getcwd())

from app.core.config import get_settings
from app.audio.codec import AudioCodec
from app.tts.sarvam import SarvamTTSProvider

async def run_hard_barge_in_live_suite():
    settings = get_settings()
    tts = SarvamTTSProvider(api_key=settings.sarvam_api_key, model=settings.tts_model, default_speaker=settings.tts_speaker)
    ws_url = "ws://127.0.0.1:8000/ws/voice"

    print("=" * 72)
    print("LIVE HARD BARGE-IN & STALE AUDIO FLUSH TEST SUITE")
    print("=" * 72)

    async with websockets.connect(ws_url) as ws:
        session_id = f"test_hard_bargein_{int(time.time())}"
        await ws.send(json.dumps({
            "event": "session.start",
            "session_id": session_id,
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": "en-IN",
            "client_sample_rate": 16000
        }))
        await ws.recv()

        # Drain initial greeting
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=20.0)
            if json.loads(msg).get("event") == "session.interaction_ready":
                break

        # Select English
        pcm = await tts.synthesize_text("English", language_code="en-IN")
        for i in range(0, len(pcm), 640):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(pcm[i:i+640]), "seq": i // 640}))
            await asyncio.sleep(0.01)
        silence = b"\x00" * 640
        for i in range(110):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(silence), "seq": 100 + i}))
            await asyncio.sleep(0.01)

        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=20.0)
            if json.loads(msg).get("event") == "response.end":
                break

        # Pre-synthesize interrupting audio before Turn 1 to eliminate network latency during barge-in
        interrupt_pcm = await tts.synthesize_text("Wait, what is the CSE tuition fee?", language_code="en-IN")

        # Turn 1: Ask broad question to trigger AI response
        print("\n--- STEP 1: Ask broad question to trigger AI response ---")
        pcm = await tts.synthesize_text("Can you tell me all the engineering and management programs available?", language_code="en-IN")
        for i in range(0, len(pcm), 640):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(pcm[i:i+640]), "seq": i // 640}))
            await asyncio.sleep(0.01)
        for i in range(110):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(silence), "seq": 200 + i}))
            await asyncio.sleep(0.01)

        # Wait for AI to start speaking audio output
        ai_speaking = False
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=25.0)
            data = json.loads(msg)
            evt = data.get("event")
            if evt == "audio.output":
                ai_speaking = True
                print("  [AI Speaking audio received... triggering barge-in!]")
                break

        assert ai_speaking is True

        # STEP 2: BARGE-IN INTERRUPTION (User speaks while AI is playing audio!)
        print("\n--- STEP 2: USER INTERRUPTS: 'Wait, what is the CSE tuition fee?' ---")
        t_barge_start = time.time() * 1000

        # Send interrupting audio frames immediately while AI is speaking
        for i in range(0, len(interrupt_pcm), 640):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(interrupt_pcm[i:i+640]), "seq": 300 + (i // 640)}))
            await asyncio.sleep(0.01)

        # 2000ms continuous silence after interruption
        for i in range(110):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(silence), "seq": 400 + i}))
            await asyncio.sleep(0.01)

        # Monitor events following interruption
        barge_in_cancelled_received = False
        audio_flush_received = False
        new_transcript = None
        new_response_text = []

        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=25.0)
            data = json.loads(msg)
            evt = data.get("event")

            if evt == "response.cancelled":
                barge_in_cancelled_received = True
                t_barge_stop = time.time() * 1000
                print(f"  --> [BARGE-IN] response.cancelled received in {t_barge_stop - t_barge_start:.1f}ms ✅")
            elif evt == "audio.flush":
                audio_flush_received = True
                print(f"  --> [BARGE-IN] audio.flush received ✅")
            elif evt == "transcript.final":
                new_transcript = data.get("data", {}).get("text")
                print(f"  --> [STT] New Turn Transcript: \"{new_transcript}\" ✅")
            elif evt == "response.text.delta":
                new_response_text.append(data.get("data", {}).get("delta", ""))
            elif evt == "response.end":
                break

        full_new_resp = "".join(new_response_text)
        print(f"  --> [AI] New Turn Response: \"{full_new_resp}\" ✅")

        assert barge_in_cancelled_received is True
        assert audio_flush_received is True
        assert new_transcript is not None
        assert "cse" in new_transcript.lower() or "fee" in new_transcript.lower()
        assert len(full_new_resp) > 0

        print("\n" + "=" * 72)
        print("HARD BARGE-IN TEST PASSED 100%! ✅")
        print("=" * 72)

        await ws.send(json.dumps({"event": "session.end"}))

if __name__ == "__main__":
    asyncio.run(run_hard_barge_in_live_suite())
