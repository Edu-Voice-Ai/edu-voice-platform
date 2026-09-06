#!/usr/bin/env python3
"""
Local Manual Realtime Voice Test Client for Edu-Voice Voice Engine.

Allows a human tester to speak into their physical microphone and converse in realtime
with the generic Voice Engine via WebSocket (wss://voice-test.gentechs.in/ws/voice).

Features:
- Full-duplex realtime PCM16 16kHz mono audio streaming (20ms frames, 640 bytes).
- Sub-millisecond hardware-boundary barge-in interruption and playback queue flush.
- Conforms strictly to Outbound Contract 5 session metadata.
- Graceful session termination with lead extraction and call summary display.
- Device enumeration and selectable microphone/speaker devices.
"""

import sys
import os
import argparse
import asyncio
import json
import base64
import time
import uuid
import queue
import signal
import threading
from typing import Optional, Set

# Ensure voice-engine package root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import sounddevice as sd
except ImportError:
    print("[ERROR] 'sounddevice' package is required. Install it via: pip install sounddevice")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("[ERROR] 'numpy' package is required. Install it via: pip install numpy")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("[ERROR] 'websockets' package is required. Install it via: pip install websockets")
    sys.exit(1)


# ==============================================================================
# AUDIO PLAYBACK CONTROLLER (REALTIME HARDWARE SINK & BARGE-IN FLUSH)
# ==============================================================================

class AudioPlaybackController:
    """
    Physical speaker playback controller.
    Maintains a 20ms frame buffer, tracks active generation IDs, and supports
    instantaneous cancellation and queue purging upon barge-in.
    """

    def __init__(self, sample_rate: int = 16000, frame_duration_ms: int = 20):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_bytes = int(sample_rate * (frame_duration_ms / 1000.0) * 2)  # 640 bytes for 20ms @ 16kHz PCM16
        self.playback_queue = queue.Queue()
        self.cancelled_generations: Set[str] = set()
        self.active_generation_id: Optional[str] = None
        self.is_playing = False
        self._lock = threading.Lock()
        self.total_frames_played = 0

    @property
    def is_currently_playing(self) -> bool:
        with self._lock:
            return self.is_playing and not self.playback_queue.empty()

    def enqueue_audio_chunk(self, generation_id: Optional[str], pcm_data: bytes) -> int:
        """Slices incoming PCM16 audio into 20ms frames and enqueues them tagged with generation_id."""
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
        """
        Instantly halts physical speaker playback, registers the generation as cancelled,
        and drains all queued frames from memory to prevent auditory overhang.
        """
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
        """Thread-safe sounddevice audio callback for uniform 20ms frame delivery."""
        bytes_needed = len(outdata)
        out_bytes = bytearray()

        while len(out_bytes) < bytes_needed:
            try:
                item = self.playback_queue.get_nowait()
                item_gen_id, chunk = item
                with self._lock:
                    if item_gen_id and (
                        item_gen_id in self.cancelled_generations
                        or (self.active_generation_id and item_gen_id != self.active_generation_id)
                    ):
                        # Discard stale or cancelled chunk immediately at hardware boundary
                        continue
                out_bytes.extend(chunk)
                self.total_frames_played += 1
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


# ==============================================================================
# AUDIO DEVICE ENUMERATION & SELECTION
# ==============================================================================

def print_audio_devices():
    """Print available audio input and output devices with their device indices."""
    devices = sd.query_devices()
    default_in = sd.default.device[0]
    default_out = sd.default.device[1]

    print("\n" + "=" * 70)
    print("AVAILABLE AUDIO DEVICES")
    print("=" * 70)
    print("INPUT DEVICES (Microphones):")
    for idx, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            is_def = " [DEFAULT]" if idx == default_in else ""
            print(f"  [{idx:2d}] {d['name']} (channels: {d['max_input_channels']}){is_def}")

    print("\nOUTPUT DEVICES (Speakers / Headphones):")
    for idx, d in enumerate(devices):
        if d['max_output_channels'] > 0:
            is_def = " [DEFAULT]" if idx == default_out else ""
            print(f"  [{idx:2d}] {d['name']} (channels: {d['max_output_channels']}){is_def}")
    print("=" * 70 + "\n")


def resolve_device(identifier: Optional[str], kind: str) -> Optional[int]:
    """Resolve a device index or substring name to an integer device ID."""
    if identifier is None:
        return None

    try:
        dev_id = int(identifier)
        return dev_id
    except ValueError:
        pass

    devices = sd.query_devices()
    for idx, d in enumerate(devices):
        channels_key = 'max_input_channels' if kind == 'input' else 'max_output_channels'
        if d[channels_key] > 0 and identifier.lower() in d['name'].lower():
            return idx

    print(f"[WARN] Audio device matching '{identifier}' not found for {kind}. Using system default.")
    return None


# ==============================================================================
# MAIN CLIENT REALTIME LOOP
# ==============================================================================

async def run_manual_voice_client(args):
    """Orchestrate the realtime manual voice test session."""
    url = args.url
    template_type = args.template
    language = args.language
    org_id = args.org_id
    agent_id = args.agent_id
    max_duration = args.duration

    # Generate persistent UUIDs
    session_id = f"manual-{uuid.uuid4().hex[:12]}"
    call_id = f"call-{uuid.uuid4().hex[:12]}"

    # Resolve audio devices
    in_device_id = resolve_device(args.input_device, 'input')
    out_device_id = resolve_device(args.output_device, 'output')

    in_dev_info = sd.query_devices(in_device_id if in_device_id is not None else sd.default.device[0])
    out_dev_info = sd.query_devices(out_device_id if out_device_id is not None else sd.default.device[1])

    print("=" * 72)
    print("   EDU-VOICE-AI — LOCAL MANUAL REALTIME VOICE TEST CLIENT")
    print("=" * 72)
    print(f"  WebSocket URL:      {url}")
    print(f"  Session ID:         {session_id}")
    print(f"  Call ID:            {call_id}")
    print(f"  Organization ID:    {org_id}")
    print(f"  Agent ID:           {agent_id}")
    print(f"  Template:           {template_type}")
    print(f"  Language:           {language}")
    print(f"  Audio Input (Mic):  {in_dev_info['name']} (16kHz PCM16 Mono)")
    print(f"  Audio Output (Spk): {out_dev_info['name']} (16kHz PCM16 Mono)")
    if max_duration:
        print(f"  Max Test Duration:  {max_duration}s (Auto-hangup)")
    print("=" * 72)
    print("  [TIP] Headphones / earphones are recommended to avoid acoustic feedback.")
    print("  [TIP] Press Ctrl+C at any time to gracefully end the call and view summary.")
    print("=" * 72 + "\n")

    # Audio queues and controller
    audio_capture_queue: asyncio.Queue[bytes] = asyncio.Queue()
    playback_controller = AudioPlaybackController(sample_rate=16000, frame_duration_ms=20)
    loop = asyncio.get_running_loop()

    # Interruption and state trackers
    session_active = asyncio.Event()
    shutdown_requested = asyncio.Event()
    call_summary_received = asyncio.Event()
    user_speaking = False
    last_user_speaking_time = 0.0
    first_audio_received = False
    assistant_speaking = False

    # Microphone input callback
    def mic_callback(indata, frames, time_info, status):
        nonlocal user_speaking, last_user_speaking_time
        if status and args.debug:
            print(f"[DEBUG MIC STATUS] {status}", file=sys.stderr)

        pcm_bytes = bytes(indata)
        loop.call_soon_threadsafe(audio_capture_queue.put_nowait, pcm_bytes)

        # Local RMS activity detection for terminal logging
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2)) if len(samples) > 0 else 0
        now = time.time()
        if rms > 600:  # Audible speech threshold
            if not user_speaking or (now - last_user_speaking_time > 1.5):
                user_speaking = True
                last_user_speaking_time = now
                print("\n>>> [USER SPEAKING] <<<", flush=True)
        else:
            if user_speaking and (now - last_user_speaking_time > 0.8):
                user_speaking = False

    # Initialize physical audio hardware streams
    try:
        input_stream = sd.RawInputStream(
            samplerate=16000,
            channels=1,
            dtype='int16',
            blocksize=320,  # 20ms @ 16kHz
            device=in_device_id,
            callback=mic_callback
        )
        output_stream = sd.RawOutputStream(
            samplerate=16000,
            channels=1,
            dtype='int16',
            blocksize=320,  # 20ms @ 16kHz
            device=out_device_id,
            callback=playback_controller.speaker_callback
        )
    except Exception as ex:
        print(f"[ERROR] Failed to initialize audio streams: {ex}")
        return

    print(f"Connecting to {url} ...")
    
    try:
        async with websockets.connect(url, max_size=10_000_000, ping_interval=20, ping_timeout=20) as ws:
            print("CONNECTED")

            # 1. Send session.start (generic Voice Engine contract)
            start_payload = {
                "event": "session.start",
                "session_id": session_id,
                "call_id": call_id,
                "organization_id": org_id,
                "agent_id": agent_id,
                "language": language,
                "client_sample_rate": 16000,
                "template_type": template_type
            }
            await ws.send(json.dumps(start_payload))
            print("SESSION STARTED")

            # Start hardware audio streams
            input_stream.start()
            output_stream.start()
            print("MICROPHONE ACTIVE")

            # Background Task A: Continuous Microphone Transmission
            async def mic_sender():
                seq = 0
                try:
                    while not shutdown_requested.is_set():
                        pcm_chunk = await audio_capture_queue.get()
                        b64_data = base64.b64encode(pcm_chunk).decode("ascii")
                        audio_event = {
                            "event": "audio.input",
                            "data": b64_data,
                            "seq": seq
                        }
                        await ws.send(json.dumps(audio_event))
                        seq += 1
                except asyncio.CancelledError:
                    pass
                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as ex:
                    if args.debug:
                        print(f"[DEBUG MIC SENDER ERROR] {ex}", file=sys.stderr)

            # Background Task B: WebSocket Event Receiver & Audio Playback
            async def event_receiver():
                nonlocal first_audio_received, assistant_speaking
                try:
                    while True:
                        raw_msg = await ws.recv()
                        if isinstance(raw_msg, bytes):
                            # Binary audio frame fallback
                            playback_controller.enqueue_audio_chunk(None, raw_msg)
                            continue

                        try:
                            msg = json.loads(raw_msg)
                        except json.JSONDecodeError:
                            continue

                        evt = msg.get("event")

                        if args.debug:
                            print(f"[DEBUG EVENT] {evt}: {msg}")

                        if evt == "session.ready":
                            session_active.set()
                            print(f"SESSION READY (status={msg.get('status')})")
                            print("------------------------------------------------------------")
                            print("Session initialized! Assistant greeting will arrive shortly.")
                            print("You may speak into your microphone at any time.")
                            print("------------------------------------------------------------")

                        elif evt == "speech.start":
                            pass  # VAD activity on server

                        elif evt == "speech.end":
                            pass  # VAD silence endpoint reached

                        elif evt == "transcript.final":
                            t_data = msg.get("data", {})
                            text = t_data.get("text", "")
                            lang = t_data.get("language", "")
                            print(f"\n[STT USER TRANSCRIPT] \"{text}\" ({lang})")

                        elif evt == "response.start":
                            gen_id = msg.get("generation_id")
                            playback_controller.active_generation_id = gen_id
                            assistant_speaking = True
                            first_audio_received = False
                            print("\nASSISTANT SPEAKING: ", end="", flush=True)

                        elif evt == "response.text.delta":
                            gen_id = msg.get("generation_id")
                            if gen_id and gen_id in playback_controller.cancelled_generations:
                                continue
                            delta = msg.get("data", {}).get("delta", "")
                            print(delta, end="", flush=True)

                        elif evt == "audio.output":
                            gen_id = msg.get("generation_id")
                            if gen_id and gen_id in playback_controller.cancelled_generations:
                                continue

                            if not first_audio_received:
                                first_audio_received = True
                                print("\nAUDIO OUTPUT RECEIVED")

                            data_obj = msg.get("data")
                            if isinstance(data_obj, dict):
                                b64_pcm = data_obj.get("data", "")
                            else:
                                b64_pcm = data_obj or ""

                            if b64_pcm:
                                pcm_bytes = base64.b64decode(b64_pcm)
                                playback_controller.enqueue_audio_chunk(gen_id, pcm_bytes)

                        elif evt in ("response.cancelled", "audio.playback.stop", "audio.flush"):
                            gen_id = msg.get("generation_id")
                            flushed = playback_controller.hard_stop_playback(gen_id)
                            assistant_speaking = False
                            first_audio_received = False
                            print(f"\nRESPONSE CANCELLED (Flushed {flushed} queued frames / {flushed * 20}ms)")

                        elif evt == "response.end":
                            assistant_speaking = False
                            print("\n[ASSISTANT FINISHED]")

                        elif evt == "lead.extracted":
                            print("\n" + "=" * 70)
                            print("LEAD EXTRACTED EVENT RECEIVED:")
                            print("=" * 70)
                            lead_payload = {
                                "session_id": msg.get("session_id") or session_id,
                                "call_id": msg.get("call_id") or call_id,
                                "organization_id": msg.get("organization_id") or org_id,
                                "agent_id": msg.get("agent_id") or agent_id,
                                "lead": msg.get("lead") or msg.get("data")
                            }
                            print(json.dumps(lead_payload, indent=2))

                        elif evt == "call.summary":
                            call_summary_received.set()
                            print("\n" + "=" * 70)
                            print("CALL SUMMARY EVENT RECEIVED:")
                            print("=" * 70)
                            summary_payload = {
                                "session_id": msg.get("session_id") or session_id,
                                "call_id": msg.get("call_id") or call_id,
                                "organization_id": msg.get("organization_id") or org_id,
                                "agent_id": msg.get("agent_id") or agent_id,
                                "summary": msg.get("summary") or msg.get("data")
                            }
                            print(json.dumps(summary_payload, indent=2))

                        elif evt == "error":
                            print(f"\n[SERVER ERROR] {msg.get('message', msg)}")

                except asyncio.CancelledError:
                    pass
                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as ex:
                    if args.debug:
                        print(f"[DEBUG RECEIVER ERROR] {ex}", file=sys.stderr)

            sender_task = asyncio.create_task(mic_sender())
            receiver_task = asyncio.create_task(event_receiver())

            # Main test wait loop
            start_time = time.time()
            try:
                while not shutdown_requested.is_set():
                    if max_duration and (time.time() - start_time >= max_duration):
                        print(f"\n[AUTO-HANGUP] Reached maximum test duration of {max_duration}s.")
                        shutdown_requested.set()
                        break
                    await asyncio.sleep(0.1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                print("\n\n[USER INTERRUPTION] Initiating clean call hangup (session.end)...")
                shutdown_requested.set()

            # Clean shutdown sequence
            print("\nSending session.end ...")
            try:
                await ws.send(json.dumps({"event": "session.end"}))
                # Wait for lead.extracted and call.summary up to 4.0s
                t_wait_start = time.time()
                while time.time() - t_wait_start < 4.0 and not call_summary_received.is_set():
                    await asyncio.sleep(0.1)
            except Exception as ex:
                if args.debug:
                    print(f"[DEBUG SHUTDOWN EXCEPTION] {ex}")

            sender_task.cancel()
            receiver_task.cancel()
            print("SESSION ENDED")

    except websockets.exceptions.WebSocketException as ws_err:
        print(f"[ERROR] WebSocket connection failed: {ws_err}")
    except Exception as ex:
        print(f"[ERROR] Unexpected runtime error: {ex}")
    finally:
        # Halt and close audio hardware
        try:
            input_stream.stop()
            input_stream.close()
        except Exception:
            pass
        try:
            output_stream.stop()
            output_stream.close()
        except Exception:
            pass
        print("Audio devices closed. Test client terminated cleanly.\n")


# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Local Manual Realtime Voice Test Client for Edu-Voice Voice Engine"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="wss://voice-test.gentechs.in/ws/voice",
        help="Target WebSocket endpoint (default: wss://voice-test.gentechs.in/ws/voice)"
    )
    parser.add_argument(
        "--template",
        type=str,
        default="education",
        help="Agent template type (education, appointment_booking, real_estate, sales_discovery, emi_collection, healthcare_renewal, ecommerce_cart, order_delivery, subscription_renewal, custom)"
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en-IN",
        help="Interaction language code (default: en-IN, also supports te-IN, hi-IN, etc.)"
    )
    parser.add_argument(
        "--org-id",
        type=str,
        default="manual-test-org",
        help="Organization ID"
    )
    parser.add_argument(
        "--agent-id",
        type=str,
        default="agent_admission",
        help="Agent ID"
    )
    parser.add_argument(
        "--input-device",
        type=str,
        default=None,
        help="Microphone device ID or name substring"
    )
    parser.add_argument(
        "--output-device",
        type=str,
        default=None,
        help="Speaker/headphones device ID or name substring"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional test duration in seconds (defaults to infinite until Ctrl+C)"
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List all detected audio input and output devices and exit"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose raw JSON event logging"
    )

    args = parser.parse_args()

    if args.list_devices:
        print_audio_devices()
        return

    try:
        asyncio.run(run_manual_voice_client(args))
    except KeyboardInterrupt:
        print("\nTerminated by user.")


if __name__ == "__main__":
    main()
