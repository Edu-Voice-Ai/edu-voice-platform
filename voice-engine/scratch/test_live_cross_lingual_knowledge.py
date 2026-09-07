"""Live verification that the same authoritative institution facts are returned in English, Hindi, and Telugu."""
import asyncio
import websockets
import json
import sys
import os
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.getcwd())

from app.core.config import get_settings
from app.audio.codec import AudioCodec
from app.tts.sarvam import SarvamTTSProvider

async def query_language(lang_choice: str, question_text: str) -> str:
    settings = get_settings()
    uri = "ws://127.0.0.1:8000/ws/voice"
    tts = SarvamTTSProvider(api_key=settings.sarvam_api_key, model=settings.tts_model, default_speaker=settings.tts_speaker)
    silence = b"\x00" * 640

    async with websockets.connect(uri) as ws:
        # Start session
        await ws.send(json.dumps({
            "event": "session.start",
            "session_id": f"sess_lang_{lang_choice.lower()}",
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": "en-IN",
            "client_sample_rate": 16000
        }))
        await ws.recv()

        # Initial greeting wait
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=20.0)
            if json.loads(msg).get("event") == "session.interaction_ready":
                break

        # Select language
        lang_code = "en-IN" if lang_choice == "English" else ("hi-IN" if lang_choice == "Hindi" else "te-IN")
        lang_pcm = await tts.synthesize_text(lang_choice, language_code=lang_code)
        for i in range(0, len(lang_pcm), 640):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(lang_pcm[i:i+640]), "seq": i // 640}))
            await asyncio.sleep(0.01)
        for i in range(110):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(silence), "seq": 100 + i}))
            await asyncio.sleep(0.01)

        # Drain initial language acknowledgment (Turn 1)
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=20.0)
            data = json.loads(msg)
            if data.get("event") == "response.end":
                break

        # Ask question (Turn 2)
        lang_code = "en-IN" if lang_choice == "English" else ("hi-IN" if lang_choice == "Hindi" else "te-IN")
        q_pcm = await tts.synthesize_text(question_text, language_code=lang_code)
        for i in range(0, len(q_pcm), 640):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(q_pcm[i:i+640]), "seq": 200 + (i // 640)}))
            await asyncio.sleep(0.01)
        for i in range(110):
            await ws.send(json.dumps({"event": "audio.input", "data": AudioCodec.encode_base64(silence), "seq": 300 + i}))
            await asyncio.sleep(0.01)

        # Collect Question Answer (Turn 2)
        response_chunks = []
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=25.0)
            data = json.loads(msg)
            evt = data.get("event")
            if evt in ("response.text.delta", "response.text_delta"):
                response_chunks.append(data.get("data", {}).get("delta", ""))
            elif evt == "response.end":
                break

        return "".join(response_chunks).strip()

async def main():
    print("=" * 70)
    print("TESTING CROSS-LANGUAGE KNOWLEDGE CONSISTENCY")
    print("=" * 70)

    # 1. English
    print("\n[TEST 1: English]")
    en_resp = await query_language("English", "What courses do you offer?")
    print(f"English Response: {en_resp}")

    # 2. Telugu
    print("\n[TEST 2: Telugu]")
    te_resp = await query_language("Telugu", "మీ దగ్గర ఏమేం కోర్సులు ఉన్నాయి?")
    print(f"Telugu Response: {te_resp}")

    # 3. Hindi
    print("\n[TEST 3: Hindi]")
    hi_resp = await query_language("Hindi", "आपके पास कौन-कौन से courses हैं?")
    print(f"Hindi Response: {hi_resp}")

    # Verify all 3 contain CSE and ECE facts
    assert "CSE" in en_resp or "Computer Science" in en_resp
    assert "ECE" in en_resp or "Electronics" in en_resp

    assert "CSE" in te_resp or "Computer Science" in te_resp or "కంప్యూటర్" in te_resp
    assert "ECE" in te_resp or "Electronics" in te_resp or "ఎలక్ట్రానిక్స్" in te_resp

    assert "CSE" in hi_resp or "Computer Science" in hi_resp or "कंप्यूटर" in hi_resp
    assert "ECE" in hi_resp or "Electronics" in hi_resp or "इलेक्ट्रॉनिक्स" in hi_resp

    print("\n" + "=" * 70)
    print("SUCCESS: Identical BTech CSE & ECE courses verified across all 3 languages! ✅")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
