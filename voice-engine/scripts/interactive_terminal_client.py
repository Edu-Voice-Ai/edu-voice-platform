"""
Interactive Terminal Test Client for Edu-Voice Voice Engine.
Allows you to type messages in the terminal, synthesizes them to PCM audio using Sarvam TTS,
and streams them in real-time to the WebSocket to test the entire VAD/STT/LLM/TTS pipeline.
"""
import sys
import os
import argparse
import asyncio
import json
import base64
import time
import httpx
import websockets

# Ensure app package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.core.config import get_settings
from app.audio.codec import AudioCodec

# Load settings to get Sarvam API Key
settings = get_settings()
SARVAM_API_KEY = settings.sarvam_api_key


async def generate_caller_audio(text: str, language: str) -> bytes:
    """Generate real caller voice PCM audio via Sarvam TTS."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"},
            json={
                "inputs": [text],
                "target_language_code": language,
                "model": "bulbul:v3",
                "speaker": "anushka",
                "enable_preprocessing": True,
            },
        )
        resp.raise_for_status()
        b64_audio = resp.json()["audios"][0]
        pcm_16k = base64.b64decode(b64_audio)
        return pcm_16k


async def run_interactive_client(ws_url: str):
    print("=" * 70)
    print("      EDU-VOICE-AI — INTERACTIVE TERMINAL REAL-TIME CLIENT")
    print("=" * 70)
    print(f"  WebSocket Endpoint: {ws_url}")
    print(f"  Acoustic Voice:     Sarvam TTS (anushka)")
    print(f"  Microphone Mode:    Simulated via Terminal Type-to-Voice")
    print("=" * 70)
    print("\n[STARTUP] Connecting to Voice Engine...")

    session_id = f"interactive_{int(time.time())}"
    current_lang = "te-IN"  # Default starting language

    async with websockets.connect(ws_url) as ws:
        print("[STARTUP] Connected to server!")
        
        # 1. Initialize session
        start_payload = {
            "event": "session.start",
            "session_id": session_id,
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": current_lang,
            "client_sample_rate": 16000
        }
        await ws.send(json.dumps(start_payload))

        ready_msg = await ws.recv()
        print(f"[STARTUP] Session Ready: {json.loads(ready_msg)}")
        print("[GREETING] Streaming initial greeting. Please wait...\n")

        # 2. Run background receiver loop
        response_completed_event = asyncio.Event()
        response_completed_event.set()

        async def server_receiver():
            nonlocal current_lang
            try:
                while True:
                    raw_msg = await ws.recv()
                    data = json.loads(raw_msg)
                    evt = data.get("event")

                    if evt == "speech.start":
                        print("\n[VAD] User speech onset detected on server.")
                    elif evt == "speech.end":
                        print("[VAD] Silence endpoint reached. Processing response...")
                    elif evt == "transcript.final":
                        t_data = data.get("data", {})
                        text = t_data.get("text")
                        lang = t_data.get("language")
                        print(f"\n[STT] Recognized: \"{text}\" (detected: {lang})")
                        if lang in ("te-IN", "hi-IN", "en-IN"):
                            current_lang = lang
                    elif evt == "response.start":
                        print("\n[AI] ", end="", flush=True)
                        response_completed_event.clear()
                    elif evt == "response.text.delta":
                        delta = data.get("data", {}).get("delta", "")
                        print(delta, end="", flush=True)
                    elif evt == "response.end":
                        metrics = data.get("data", {})
                        if metrics.get("is_initial_greeting"):
                            print(f"\n[GREETING COMPLETED] Duration: {metrics.get('greeting_duration_ms', 0):.0f}ms")
                        else:
                            print(f"\n[METRICS] Latency: {metrics.get('total_turn_latency_ms', 0):.1f}ms (TTFT: {metrics.get('ttft_ms', 0):.1f}ms)")
                        response_completed_event.set()
                    elif evt == "response.cancelled":
                        print(f"\n[BARGE-IN] Interrupted: {data.get('data', {}).get('reason')}")
                    elif evt in ("lead.extracted", "call.summary"):
                        print(f"\n[INTELLIGENCE] {evt.upper()}: {data.get('data') or data.get('lead') or data.get('summary')}")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"\n[ERROR] Receiver loop error: {e}")

        receiver_task = asyncio.create_task(server_receiver())

        # Allow user input loop
        try:
            loop = asyncio.get_running_loop()
            while True:
                # Wait for any current AI response to finish printing
                await response_completed_event.wait()
                
                # Get input from user inside an executor to avoid blocking the asyncio loop
                print("\n" + "-" * 70)
                user_msg = await loop.run_in_executor(
                    None, 
                    lambda: input(f"Type caller speech (current default lang={current_lang}, or type 'exit'): ").strip()
                )
                
                if not user_msg:
                    continue
                if user_msg.lower() == 'exit':
                    break

                # Ask user for language override if needed (simple prefix checks)
                lang_override = current_lang
                if any(k in user_msg.lower() for k in ("hindi", "नमस्ते", "क्या")):
                    lang_override = "hi-IN"
                elif any(k in user_msg.lower() for k in ("english", "hello", "hi", "courses", "fee")):
                    pass

                print(f"[*] Generating acoustic voice for: \"{user_msg}\" ({lang_override})...")
                try:
                    pcm_audio = await generate_caller_audio(user_msg, lang_override)
                    print(f"[+] Audio generated ({len(pcm_audio)} bytes). Streaming to server...")
                    
                    # Stream audio frames in real time
                    chunk_size = 640  # 20ms @ 16kHz 16-bit Mono PCM
                    for i in range(0, len(pcm_audio), chunk_size):
                        chunk = pcm_audio[i:i+chunk_size]
                        if len(chunk) < chunk_size:
                            chunk += b"\x00" * (chunk_size - len(chunk))
                        
                        b64_str = AudioCodec.encode_base64(chunk)
                        await ws.send(json.dumps({
                            "event": "audio.input",
                            "data": b64_str,
                            "seq": i // chunk_size
                        }))
                        await asyncio.sleep(0.02)  # Real-time spacing

                    # Stream 600ms of silence to trigger turn endpointing
                    silence_chunk = b"\x00" * chunk_size
                    b64_silence = AudioCodec.encode_base64(silence_chunk)
                    for s in range(30):
                        await ws.send(json.dumps({
                            "event": "audio.input",
                            "data": b64_silence,
                            "seq": 1000 + s
                        }))
                        await asyncio.sleep(0.02)
                    
                    print("[+] Audio streaming completed. Waiting for response...")

                except Exception as e:
                    print(f"[ERROR] Failed to synthesize or stream audio: {e}")

        finally:
            receiver_task.cancel()
            await asyncio.gather(receiver_task, return_exceptions=True)
            print("\n[CLIENT] Ending voice session...")
            await ws.send(json.dumps({"event": "session.end"}))
            await asyncio.sleep(0.5)
            print("[CLIENT] Session closed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Edu-Voice Voice Engine Interactive Real-Time Client")
    parser.add_argument("--url", default="wss://voice-test.gentechs.in/ws/voice", help="WebSocket URL")
    args = parser.parse_args()

    try:
        asyncio.run(run_interactive_client(ws_url=args.url))
    except KeyboardInterrupt:
        print("\n[CLIENT] Terminated by user.")
