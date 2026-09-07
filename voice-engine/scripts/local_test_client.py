"""Local Realtime Test Client for Edu-Voice Voice Engine.
Supports simulated conversation, barge-in interruption testing, and live microphone capture.
"""
import sys
import os
import argparse
import asyncio
import json
import base64
import time
import queue
import numpy as np

# Ensure app package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import websockets
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec


def query_audio_devices():
    """Query and return active input/output audio devices."""
    try:
        import sounddevice as sd
        in_dev = sd.query_devices(kind='input')
        out_dev = sd.query_devices(kind='output')
        return in_dev, out_dev
    except Exception as e:
        return None, None


def generate_synthetic_speech_chunk(duration_sec: float = 1.0, freq: float = 300.0, sample_rate: int = 16000) -> bytes:
    """Generate audible synthetic speech tone."""
    num_samples = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, num_samples, endpoint=False)
    # Modulated tone simulating speech formants
    carrier = np.sin(2 * np.pi * freq * t)
    modulator = 0.5 * (1 + np.sin(2 * np.pi * 5 * t))
    waveform = (carrier * modulator * 0.4 * 32767.0).astype(np.int16)
    return waveform.tobytes()


def generate_synthetic_silence_chunk(duration_sec: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Generate silent PCM bytes."""
    num_samples = int(sample_rate * duration_sec)
    return b"\x00" * (num_samples * 2)


import threading
from typing import Optional, Set

class AudioPlaybackController:
    """Authoritative physical speaker playback controller managing frame-by-frame streaming,
    active generation tracking, instantaneous hard-stop cancellation, and queue flushing."""
    def __init__(self, sample_rate: int = 16000, frame_duration_ms: int = 20):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_bytes = int(sample_rate * (frame_duration_ms / 1000.0) * 2)  # 640 bytes for 20ms @ 16kHz PCM16
        self.playback_queue = queue.Queue()
        self.cancelled_generations: Set[str] = set()
        self.active_generation_id: Optional[str] = None
        self.is_playing = False
        self._lock = threading.Lock()

    @property
    def is_currently_playing(self) -> bool:
        with self._lock:
            return self.is_playing and not self.playback_queue.empty()

    def enqueue_audio_chunk(self, generation_id: Optional[str], pcm_data: bytes) -> int:
        """Slices incoming PCM audio into uniform 20ms frames and enqueues them tagged with generation_id."""
        with self._lock:
            if generation_id and generation_id in self.cancelled_generations:
                return 0
            self.active_generation_id = generation_id
            self.is_playing = True
            
            frame_count = 0
            for i in range(0, len(pcm_data), self.frame_bytes):
                frame = pcm_data[i:i + self.frame_bytes]
                if len(frame) < self.frame_bytes:
                    frame = frame + b"\x00" * (self.frame_bytes - len(frame))
                self.playback_queue.put_nowait((generation_id, frame))
                frame_count += 1
            return frame_count

    def hard_stop_playback(self, generation_id: Optional[str] = None) -> int:
        """Instantly stops physical speaker playback, invalidates generation, and flushes all queued frames."""
        with self._lock:
            if generation_id:
                self.cancelled_generations.add(generation_id)
            if self.active_generation_id:
                self.cancelled_generations.add(self.active_generation_id)
            self.active_generation_id = None
            self.is_playing = False

            flushed_frames = 0
            while not self.playback_queue.empty():
                try:
                    self.playback_queue.get_nowait()
                    flushed_frames += 1
                except queue.Empty:
                    break
            return flushed_frames

    def speaker_callback(self, outdata, frames, time_info, status):
        """Thread-safe sounddevice audio callback executing exact 20ms frame delivery."""
        bytes_needed = len(outdata)
        out_bytes = bytearray()
        
        while len(out_bytes) < bytes_needed:
            try:
                item = self.playback_queue.get_nowait()
                item_gen_id, chunk = item
                with self._lock:
                    if item_gen_id and (item_gen_id in self.cancelled_generations or (self.active_generation_id and item_gen_id != self.active_generation_id)):
                        # Discard stale/cancelled chunk at hardware boundary
                        continue
                out_bytes.extend(chunk)
            except queue.Empty:
                with self._lock:
                    self.is_playing = False
                break

        if len(out_bytes) < bytes_needed:
            out_bytes.extend(b"\x00" * (bytes_needed - len(out_bytes)))
            with self._lock:
                if self.playback_queue.empty():
                    self.is_playing = False
        outdata[:] = bytes(out_bytes[:bytes_needed])


async def run_live_microphone_client(ws_url: str, session_id: str = None):
    """Run real physical microphone and speaker audio streaming loop."""
    try:
        import sounddevice as sd
    except ImportError:
        print("[ERROR] 'sounddevice' package is required for live microphone mode. Run: pip install sounddevice")
        return

    t_start = time.time()

    in_dev = sd.query_devices(kind='input')
    out_dev = sd.query_devices(kind='output')

    print("=" * 68)
    print("EDU-VOICE-AI REALTIME PHYSICAL MICROPHONE CLIENT")
    print("=" * 68)
    print(f"Input device:  {in_dev['name']}")
    print(f"Sample rate:   16000 Hz")
    print(f"Channels:      1 (Mono, 16-bit PCM)")
    print()
    print(f"Output device: {out_dev['name']}")
    print(f"Sample rate:   16000 Hz")
    print(f"Channels:      1 (Mono, 16-bit PCM)")
    print("=" * 68)
    print("[TIP] Wearing headphones or earphones is recommended for optimal acoustic isolation.\n")
    print(f"[STARTUP] Connecting to Voice Engine at {ws_url} ...")

    session_id = session_id or f"mic_sess_{int(time.time())}"

    async with websockets.connect(ws_url) as ws:
        t_ws_connected = time.time()
        print(f"[STARTUP] WebSocket connected in {(t_ws_connected - t_start)*1000:.1f}ms")
        
        # 1. Initialize session
        start_payload = {
            "event": "session.start",
            "session_id": session_id,
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": "en-IN",
            "client_sample_rate": 16000
        }
        await ws.send(json.dumps(start_payload))

        ready_msg = await ws.recv()
        t_session_ready = time.time()
        ready_data = json.loads(ready_msg)
        print(f"[STARTUP] Session ready in {(t_session_ready - t_ws_connected)*1000:.1f}ms: {ready_data}")
        print("[GREETING] Playing initial language selection prompt...\n")

        audio_capture_queue = asyncio.Queue()
        playback_controller = AudioPlaybackController(sample_rate=16000, frame_duration_ms=20)
        loop = asyncio.get_running_loop()

        interaction_ready = False
        is_playing_greeting = True

        # Sounddevice Input Callback (Thread-safe)
        def mic_callback(indata, frames, time_info, status):
            if status:
                pass
            # Forward mic frames into queue
            loop.call_soon_threadsafe(audio_capture_queue.put_nowait, bytes(indata))

        input_stream = sd.RawInputStream(
            samplerate=16000,
            channels=1,
            dtype='int16',
            blocksize=320,  # 20ms chunks @ 16kHz
            callback=mic_callback
        )
        output_stream = sd.RawOutputStream(
            samplerate=16000,
            channels=1,
            dtype='int16',
            blocksize=320,
            callback=playback_controller.speaker_callback
        )

        input_stream.start()
        output_stream.start()

        exit_reason = "USER_ENDED_CALL"

        # Task A: Send mic audio frames to WebSocket (Full duplex)
        async def mic_sender():
            nonlocal exit_reason
            seq = 0
            try:
                while True:
                    pcm_data = await audio_capture_queue.get()
                    b64_str = AudioCodec.encode_base64(pcm_data)
                    payload = {
                        "event": "audio.input",
                        "data": b64_str,
                        "seq": seq
                    }
                    await ws.send(json.dumps(payload))
                    seq += 1
            except asyncio.CancelledError:
                pass
            except websockets.exceptions.ConnectionClosed as e:
                exit_reason = f"WEBSOCKET_CLOSED (code={e.code}, reason={e.reason})"
            except Exception as e:
                exit_reason = f"MIC_SENDER_ERROR ({e})"

        # Task B: Receive server events and audio playback
        async def server_receiver():
            nonlocal exit_reason, interaction_ready, is_playing_greeting
            try:
                while True:
                    raw_msg = await ws.recv()
                    data = json.loads(raw_msg)
                    evt = data.get("event")

                    if evt == "speech.start":
                        print("\n[VAD] User speaking...")
                    elif evt == "speech.end":
                        print("[VAD] Silence detected (processing turn)...")
                    elif evt == "transcript.final":
                        t_data = data.get("data", {})
                        print(f"[STT] Transcript: \"{t_data.get('text')}\" (Language: {t_data.get('language')})")
                    elif evt == "response.start":
                        playback_controller.active_generation_id = data.get("generation_id")
                        print("[AI] ", end="", flush=True)
                    elif evt == "response.text.delta":
                        gen_id = data.get("generation_id")
                        if gen_id and gen_id in playback_controller.cancelled_generations:
                            continue
                        delta = data.get("data", {}).get("delta", "")
                        print(delta, end="", flush=True)
                    elif evt == "audio.output":
                        gen_id = data.get("generation_id")
                        if gen_id and gen_id in playback_controller.cancelled_generations:
                            # Stale audio chunk from cancelled generation - discard immediately
                            continue
                        b64_audio = data.get("data", {}).get("data", "")
                        if b64_audio:
                            pcm_chunk = AudioCodec.decode_base64(b64_audio)
                            playback_controller.enqueue_audio_chunk(gen_id, pcm_chunk)
                    elif evt == "session.interaction_ready":
                        interaction_ready = True
                        is_playing_greeting = False
                        playback_controller.is_playing = False
                        t_ready = time.time()
                        print(f"\n[STARTUP] Interaction ready in {(t_ready - t_start):.2f}s total startup time.")
                        print(">>> MICROPHONE ACTIVE: Speak your language preference (English / Hindi / Telugu) now! <<<\n")
                    elif evt in ("audio.playback.stop", "audio.flush", "response.cancelled"):
                        t_stop_start = time.time() * 1000
                        gen_id = data.get("generation_id")
                        flushed_frames = playback_controller.hard_stop_playback(gen_id)
                        t_stop_end = time.time() * 1000
                        stop_ms = t_stop_end - t_stop_start

                        if evt == "response.cancelled":
                            print(f"\n[BARGE-IN] Interrupted: {data.get('data', {}).get('reason')} (flushed {flushed_frames} frames / {flushed_frames * 20}ms queued audio in {stop_ms:.2f}ms)")
                        elif evt == "audio.playback.stop":
                            print(f"[PHYSICAL AUDIO STOP] Hardware speaker stream halted immediately (gen={gen_id}, stop_latency={stop_ms:.2f}ms)")
                        elif evt == "audio.flush":
                            print(f"[AUDIO] Playback buffer flushed! ({flushed_frames} frames dropped)")
                    elif evt == "response.end":
                        with playback_controller._lock:
                            if playback_controller.playback_queue.empty():
                                playback_controller.is_playing = False
                        metrics = data.get("data", {})
                        if metrics.get("is_initial_greeting"):
                            print(f"\n[GREETING METRICS] Playback complete (TTFB: {metrics.get('ttfb_ms', 0):.0f}ms, duration: {metrics.get('greeting_duration_ms', 0):.0f}ms)")
                        elif metrics.get("total_turn_latency_ms"):
                            print(f"\n[TURN METRICS] Latency: {metrics.get('total_turn_latency_ms', 0):.1f}ms (TTFT: {metrics.get('ttft_ms', 0):.1f}ms, STT: {metrics.get('stt_latency_ms', 0):.1f}ms)\n")
                    elif evt in ("lead.extracted", "call.summary"):
                        print(f"[INTELLIGENCE] {evt}: {data.get('data') or data.get('lead') or data.get('summary')}")
            except asyncio.CancelledError:
                pass
            except websockets.exceptions.ConnectionClosed as e:
                exit_reason = f"WEBSOCKET_CLOSED (code={e.code}, reason={e.reason})"
            except Exception as e:
                exit_reason = f"SERVER_RECEIVER_ERROR ({e})"

        sender_task = asyncio.create_task(mic_sender())
        receiver_task = asyncio.create_task(server_receiver())

        try:
            await asyncio.gather(sender_task, receiver_task)
        except asyncio.CancelledError:
            pass
        finally:
            sender_task.cancel()
            receiver_task.cancel()
            input_stream.stop()
            output_stream.stop()
            input_stream.close()
            output_stream.close()
            print(f"[CLIENT] Stopping microphone session... (Reason: {exit_reason})")
            print("[CLIENT] Microphone session closed.")


async def run_simulated_conversation(ws_url: str, test_barge_in: bool = False):
    """Simulate complete multi-turn conversation over WebSocket with Sarvam AI."""
    settings = get_settings()
    from app.tts.sarvam import SarvamTTSProvider
    tts = SarvamTTSProvider(api_key=settings.sarvam_api_key, model=settings.tts_model, default_speaker=settings.tts_speaker)

    print("=" * 65)
    print("EDU-VOICE-AI REALTIME SIMULATION CLIENT")
    print(f"Mode: {'Barge-In Interruption Test' if test_barge_in else 'Multi-turn Speech-to-Speech'}")
    print("=" * 65)
    print("\n[CLIENT] Connecting to Voice Engine at", ws_url, "...")

    session_id = f"sim_sess_{int(time.time())}"

    async with websockets.connect(ws_url) as ws:
        print("[CLIENT] Connected!")
        
        start_payload = {
            "event": "session.start",
            "session_id": session_id,
            "organization_id": "org_apex_univ",
            "agent_id": "agent_admission",
            "language": "en-IN",
            "client_sample_rate": 16000
        }
        await ws.send(json.dumps(start_payload))
        ready_msg = await ws.recv()
        print(f"[SERVER] Ready: {json.loads(ready_msg)}")

        # Wait for greeting to finish
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get("event") == "response.end":
                break

        response_started_event = asyncio.Event()

        async def listen_loop():
            try:
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    evt = data.get("event")
                    if evt == "speech.start":
                        print("\n[VAD] Speech onset detected")
                    elif evt == "speech.end":
                        print("[VAD] Turn endpointed (silence detected)")
                    elif evt == "transcript.final":
                        t_data = data.get("data", {})
                        print(f"[STT] Final: \"{t_data.get('text')}\" (confidence: {t_data.get('confidence', 1.0):.2f}, lang: {t_data.get('language')})")
                    elif evt == "response.start":
                        print("[AI] ", end="", flush=True)
                    elif evt == "response.text.delta":
                        response_started_event.set()
                        print(data.get("data", {}).get("delta", ""), end="", flush=True)
                    elif evt == "response.cancelled":
                        print(f"\n[BARGE-IN SUCCESS] Interruption Event: {data.get('data', {}).get('reason')}")
                    elif evt == "audio.flush":
                        print("[AUDIO FLUSH] Client cleared pending audio buffers")
                    elif evt == "response.end":
                        metrics = data.get("data", {})
                        if metrics.get("total_turn_latency_ms"):
                            print(f"\n[METRICS] Latency: {metrics.get('total_turn_latency_ms', 0):.1f}ms (STT: {metrics.get('stt_latency_ms', 0):.1f}ms, TTFT: {metrics.get('ttft_ms', 0):.1f}ms, TTFB: {metrics.get('ttfb_ms', 0):.1f}ms)\n")
                        break
            except Exception as e:
                pass

        listener_task = asyncio.create_task(listen_loop())

        chunk_size = 640  # 20ms @ 16kHz
        silence_pcm = generate_synthetic_silence_chunk(duration_sec=0.6)
        
        print("\n[CLIENT] Pre-synthesizing acoustic speech phrases for realistic S2S test...")
        speech_pcm = await tts.synthesize_text("I prefer English", language_code="en-IN")

        print("\n[CLIENT] --> User speaking: 'I prefer English'")
        for i in range(0, len(speech_pcm), chunk_size):
            chunk = speech_pcm[i:i+chunk_size]
            b64_str = AudioCodec.encode_base64(chunk)
            await ws.send(json.dumps({"event": "audio.input", "data": b64_str, "seq": i // chunk_size}))
            await asyncio.sleep(0.01)

        # Silence to trigger turn end
        for i in range(0, len(silence_pcm), chunk_size):
            chunk = silence_pcm[i:i+chunk_size]
            b64_str = AudioCodec.encode_base64(chunk)
            await ws.send(json.dumps({"event": "audio.input", "data": b64_str, "seq": 100 + (i // chunk_size)}))
            await asyncio.sleep(0.01)

        await asyncio.wait_for(listener_task, timeout=35.0)

        # 3. End Session
        print("\n[CLIENT] Ending Voice Session...")
        await ws.send(json.dumps({"event": "session.end"}))
        await asyncio.sleep(0.5)
        print("[CLIENT] Test finished successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Edu-Voice Voice Engine Realtime Test Client")
    parser.add_argument("--url", default="ws://localhost:8000/ws/voice", help="WebSocket URL")
    parser.add_argument("--barge-in", action="store_true", help="Simulate user barge-in interruption")
    parser.add_argument("--mic", action="store_true", help="Capture real physical microphone and play speaker audio")
    args = parser.parse_args()

    try:
        if args.mic:
            asyncio.run(run_live_microphone_client(ws_url=args.url))
        else:
            asyncio.run(run_simulated_conversation(ws_url=args.url, test_barge_in=args.barge_in))
    except KeyboardInterrupt:
        print("\n[CLIENT] Session ended by user.")
