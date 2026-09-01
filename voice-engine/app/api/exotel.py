"""Exotel Telephony Streaming Gateway Adapter for bidirectional Voice Engine integration."""
import json
import time
import asyncio
import base64
from typing import Optional, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.session.state import SessionState
from app.session.events import SessionEvent, EventType
from app.session.manager import get_session_manager
from app.pipeline.engine import SpeechToSpeechEngine
from app.api.websocket import build_default_engine
from app.core.config import get_settings
from app.core.ids import generate_session_id
from app.core.logging import get_logger

logger = get_logger("api.exotel")
router = APIRouter(prefix="/exotel", tags=["Exotel Telephony Gateway"])


def mask_phone_number(number: Optional[str]) -> str:
    """Mask phone number for privacy compliant logging."""
    if not number:
        return "UNKNOWN"
    num_str = str(number).strip()
    if len(num_str) <= 4:
        return "****"
    return "*" * (len(num_str) - 4) + num_str[-4:]


@router.api_route("/incoming_call", methods=["GET", "POST"])
async def exotel_incoming_call_webhook(request: Request):
    """
    Exotel Voicebot dynamic webhook endpoint for incoming calls to Exophone.
    Returns JSON { "url": "wss://..." } for Exotel Voicebot Applets,
    and valid ExoML <Response><Connect><Stream .../></Connect></Response> for XML clients.
    """
    settings = get_settings()
    host = request.headers.get("host", "localhost:8000")
    ws_scheme = "wss" if request.url.scheme == "https" or "https" in request.headers.get("x-forwarded-proto", "") else "ws"
    
    ws_url = settings.public_voice_ws_url or f"{ws_scheme}://{host}/exotel/media"
    if ws_url.startswith("http://"):
        ws_url = "ws://" + ws_url[7:]
    elif ws_url.startswith("https://"):
        ws_url = "wss://" + ws_url[8:]

    logger.info(f"[EXOTEL_WEBHOOK] Incoming call routing to Stream WS: {ws_url}")

    accept_header = request.headers.get("accept", "").lower()
    format_param = request.query_params.get("format", "").lower()

    if "xml" in accept_header or format_param == "xml":
        exoml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""
        return Response(content=exoml_response, media_type="application/xml")

    # Default to Exotel Voicebot dynamic JSON format
    return {
        "url": ws_url,
        "stream_url": ws_url,
        "bidirectional": True
    }


@router.api_route("/status_callback", methods=["GET", "POST"])
async def exotel_status_callback(request: Request):
    """Receive call status updates (ringing, in-progress, completed) from Exotel."""
    try:
        if request.method == "POST":
            form = await request.form()
            params = dict(form)
        else:
            params = dict(request.query_params)
        
        call_sid = params.get("CallSid") or params.get("call_sid") or "UNKNOWN"
        status = params.get("Status") or params.get("status") or "UNKNOWN"
        caller = mask_phone_number(params.get("From") or params.get("from") or params.get("CallFrom"))
        
        logger.info(f"[EXOTEL_STATUS] CallSid={call_sid} Status={status} Caller={caller}")
    except Exception as e:
        logger.warning(f"[EXOTEL_STATUS] Error parsing status callback: {e}")
    return {"status": "ok"}


@router.websocket("/media")
@router.websocket("/stream")
async def exotel_voice_stream_endpoint(websocket: WebSocket):
    """
    Bi-directional realtime WebSocket stream for Exotel Telephony.
    Handles Exotel events: connected, start, media, stop, clear.
    """
    await websocket.accept()
    settings = get_settings()
    manager = get_session_manager()

    logger.info(f"[ECHO_TEST] websocket_entered flag_value={settings.exotel_echo_test}")

    if settings.exotel_echo_test:
        logger.info("[ECHO_TEST] flag_value=true entering isolated telephony echo test")
        stream_sid = None
        current_turn_number = 0
        is_playing_response = False
        media_since_last_response = 0
        total_inbound_packets = 0

        # Load 8kHz 16-bit linear PCM test waveform (1.0s slice = 16,000 bytes)
        try:
            with open("app/api/echo_test_pcm16_8k.raw", "rb") as f:
                raw_full = f.read()
                pcm16_test_bytes = raw_full[:16000] if len(raw_full) >= 16000 else raw_full
        except Exception:
            pcm16_test_bytes = b"\x00" * (8000 * 2)  # 1s fallback

        async def send_turn_response(turn_num: int, sid: str):
            nonlocal is_playing_response, media_since_last_response
            is_playing_response = True
            t_start = asyncio.get_event_loop().time()
            logger.info(f"[ECHO_TURN] turn_number={turn_num} response_start={t_start:.3f} stream_sid={sid} bytes={len(pcm16_test_bytes)}")
            outbound_count = 0
            packet_size = 1600  # 100ms of 8kHz 16-bit mono = 800 samples = 1600 bytes
            try:
                for i in range(0, len(pcm16_test_bytes), packet_size):
                    chunk = pcm16_test_bytes[i:i + packet_size]
                    if len(chunk) < packet_size:
                        chunk = chunk + b"\x00" * (packet_size - len(chunk))
                    payload_b64 = base64.b64encode(chunk).decode("ascii")
                    media_msg = {
                        "event": "media",
                        "stream_sid": sid,
                        "media": {
                            "payload": payload_b64
                        }
                    }
                    await websocket.send_text(json.dumps(media_msg))
                    outbound_count += 1
                    await asyncio.sleep(0.10)  # 100ms pacing

                t_end = asyncio.get_event_loop().time()
                logger.info(
                    f"[ECHO_TURN] turn_number={turn_num} response_end={t_end:.3f} "
                    f"duration_sec={t_end - t_start:.2f} packets={outbound_count} response_sent=True"
                )
            except Exception as ex:
                logger.error(f"[ECHO_TURN] turn_number={turn_num} ERROR: {ex}")
            finally:
                # Reset state so the next speech burst triggers the next turn cleanly
                is_playing_response = False
                media_since_last_response = 0
                logger.info(f"[ECHO_TURN] State returned to LISTENING for turn {turn_num + 1}")

        try:
            while True:
                message_text = await websocket.receive_text()
                try:
                    data = json.loads(message_text)
                except json.JSONDecodeError:
                    continue

                event_type = data.get("event")
                if event_type == "connected":
                    logger.info("[EXO_ECHO] CONNECTED event received")
                elif event_type == "start":
                    start_data = data.get("start", {})
                    stream_sid = data.get("stream_sid") or start_data.get("stream_sid")
                    media_format = data.get("media_format") or start_data.get("media_format", {})
                    logger.info(f"[EXO_ECHO] START event stream_sid={stream_sid} media_format={media_format}")
                    
                    # Turn 1: Initial Greeting / Prompt
                    current_turn_number = 1
                    if stream_sid and not is_playing_response:
                        asyncio.create_task(send_turn_response(current_turn_number, stream_sid))

                elif event_type == "media":
                    total_inbound_packets += 1
                    if not is_playing_response and stream_sid and current_turn_number >= 1:
                        media_since_last_response += 1
                        # After ~20 inbound packets (~400ms of caller speech after previous response finishes)
                        if media_since_last_response == 20:
                            current_turn_number += 1
                            logger.info(
                                f"[ECHO_TURN] speech_detected media_count={media_since_last_response} "
                                f"triggering Turn {current_turn_number} (total_inbound={total_inbound_packets})"
                            )
                            asyncio.create_task(send_turn_response(current_turn_number, stream_sid))

                elif event_type == "stop":
                    logger.info(f"[EXO_ECHO] STOP event stream_sid={stream_sid} total_turns_completed={current_turn_number} total_inbound={total_inbound_packets}")
                    break

        except WebSocketDisconnect:
            logger.info(f"[EXO_ECHO] WebSocket disconnected cleanly stream_sid={stream_sid}")
        except Exception as e:
            logger.error(f"[EXO_ECHO] WebSocket error: {e}", exc_info=True)
        return

    session: Optional[SessionState] = None
    engine: Optional[SpeechToSpeechEngine] = None
    writer_task: Optional[asyncio.Task] = None
    
    stream_sid: Optional[str] = None
    call_sid: Optional[str] = None
    caller_number: Optional[str] = None
    
    encoding: str = "audio/x-l16"    # Standard Exotel VoiceBot SLIN PCM format
    sample_rate: int = 8000          # Default Exotel PSTN sample rate
    inbound_media_count: int = 0

    writer_state = {
        "stream_sid": None,
        "encoding": encoding,
        "sample_rate": sample_rate,
        "outbound_media_count": 0
    }

    async def exotel_audio_writer_loop(event_queue: asyncio.Queue[SessionEvent]):
        """Consumes engine events and formats outbound audio/clear events to Exotel with real-time pacing."""
        pacing_gen_id = None
        pacing_frame_count = 0
        pacing_next_time = 0.0

        while True:
            try:
                event = await event_queue.get()
                sid = writer_state.get("stream_sid")
                sr = writer_state.get("sample_rate", 8000)
                enc = writer_state.get("encoding", "audio/x-l16")
                
                # 1. Barge-in / Interruption: Send 'clear' to Exotel to halt physical speaker buffer
                if event.event in (EventType.RESPONSE_CANCELLED, EventType.AUDIO_PLAYBACK_STOP, EventType.AUDIO_FLUSH):
                    if session:
                        session.playback_estimated_end_time_ms = 0.0
                    pacing_gen_id = None
                    pacing_frame_count = 0
                    pacing_next_time = 0.0

                    if sid:
                        clear_msg = {
                            "event": "clear",
                            "stream_sid": sid,
                            "streamSid": sid
                        }
                        try:
                            await websocket.send_text(json.dumps(clear_msg))
                            logger.info(
                                f"[BARGE_IN]\n"
                                f"stream_sid={sid}\n"
                                f"generation_id={event.generation_id}\n"
                                f"clear_sent=True\n"
                                f"clear_success=True",
                                extra={"session_id": event.session_id}
                            )
                        except Exception as ce:
                            logger.error(f"[BARGE_IN] Failed to dispatch clear to Exotel: {ce}")

                    # Drain any pending stale audio events from event_queue
                    drained_audio = 0
                    while not event_queue.empty():
                        try:
                            pending_ev = event_queue.get_nowait()
                            if pending_ev.event in (EventType.AUDIO_OUTPUT, "audio.output"):
                                drained_audio += 1
                        except Exception:
                            break
                    if drained_audio > 0:
                        logger.info(f"[BARGE_IN] Drained {drained_audio} stale outbound audio packets from event_queue")
                    continue

                # 2. Audio Chunks: Send 'media' event with base64 encoded audio
                if event.event in (EventType.AUDIO_OUTPUT, "audio.output"):
                    gen_id = event.generation_id
                    if session and session.is_generation_cancelled(gen_id):
                        # Discard stale audio packet from interrupted generation
                        continue

                    # Reset or advance real-time pacing tracker
                    if gen_id != pacing_gen_id:
                        pacing_gen_id = gen_id
                        pacing_frame_count = 0
                        pacing_next_time = time.time() + 0.020

                    pacing_frame_count += 1
                    # Allow 3 frames (60ms) burst buffer, then pace in real-time (20ms/frame)
                    if pacing_frame_count > 3:
                        now_t = time.time()
                        if now_t < pacing_next_time:
                            sleep_dur = pacing_next_time - now_t
                            if sleep_dur > 0.001:
                                await asyncio.sleep(sleep_dur)
                        pacing_next_time = max(pacing_next_time + 0.020, time.time() + 0.015)

                    # Check cancellation again after pacing sleep
                    if session and session.is_generation_cancelled(gen_id):
                        continue

                    if session:
                        now_ms = time.time() * 1000
                        session.playback_estimated_end_time_ms = max(session.playback_estimated_end_time_ms, now_ms) + 20.0

                    data_b64 = event.data.get("data", "")
                    if not data_b64:
                        continue
                    
                    pcm16_bytes = AudioCodec.decode_base64(data_b64)
                    
                    # Convert to Exotel telephony format (16kHz PCM16 -> 8kHz PCM16 SLIN)
                    if sr == 8000:
                        pcm_resampled = AudioCodec.resample_linear(pcm16_bytes, orig_sr=16000, target_sr=8000)
                    else:
                        pcm_resampled = pcm16_bytes
                    
                    if "mulaw" in enc.lower() or "pcmu" in enc.lower():
                        outbound_bytes = AudioCodec.pcm16_to_mulaw(pcm_resampled)
                    else:
                        outbound_bytes = pcm_resampled  # Standard Exotel SLIN PCM16
                    
                    outbound_b64 = base64.b64encode(outbound_bytes).decode("ascii")
                    writer_state["outbound_media_count"] += 1
                    count = writer_state["outbound_media_count"]
                    if count <= 5 or count % 50 == 0:
                        logger.info(
                            f"[EXOTEL_OUTBOUND_MEDIA] count={count} stream_sid={sid} "
                            f"bytes={len(outbound_bytes)} b64_len={len(outbound_b64)}"
                        )
                    
                    # Final authorization check immediately before dispatching to Exotel websocket
                    if session and session.is_generation_cancelled(gen_id):
                        continue

                    media_msg = {
                        "event": "media",
                        "stream_sid": sid,
                        "media": {
                            "payload": outbound_b64
                        }
                    }
                    await websocket.send_text(json.dumps(media_msg))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"[EXOTEL_OUTBOUND_WRITER_ERROR] stream_sid={writer_state.get('stream_sid')} "
                    f"packet={writer_state.get('outbound_media_count')} error={e}",
                    exc_info=True
                )
                break

    try:
        while True:
            message_text = await websocket.receive_text()
            try:
                data = json.loads(message_text)
            except json.JSONDecodeError:
                logger.warning("[EXOTEL_STREAM] Non-JSON payload received")
                continue

            event_type = data.get("event")
            if event_type != "media":
                logger.info(f"[EXOTEL_INBOUND] event={event_type} data_keys={list(data.keys())}")

            # 1. Connected Handshake
            if event_type == "connected":
                protocol = data.get("protocol", "Call")
                version = data.get("version", "1.0.0")
                logger.info(f"[EXOTEL_STREAM] Handshake connected: protocol={protocol} version={version}")

            # 2. Start Event (Call initialization & media format negotiation)
            elif event_type == "start":
                stream_sid = data.get("stream_sid")
                start_data = data.get("start", {})
                call_sid = start_data.get("call_sid") or data.get("call_sid")
                
                custom_params = start_data.get("custom_parameters", {})
                caller_number = start_data.get("from") or custom_params.get("From") or "UNKNOWN"
                
                media_format = start_data.get("media_format", {})
                encoding = media_format.get("encoding", encoding)
                sample_rate = int(media_format.get("sample_rate", sample_rate))
                
                # Sync into writer state dictionary
                writer_state["stream_sid"] = stream_sid
                writer_state["encoding"] = encoding
                writer_state["sample_rate"] = sample_rate
                
                logger.info(
                    f"[EXOTEL_STREAM] Call Start: call_sid={call_sid} stream_sid={stream_sid} "
                    f"caller={mask_phone_number(caller_number)} encoding={encoding} sr={sample_rate}"
                )

                # Initialize standalone Voice Engine session
                session_id = f"exotel_{call_sid or generate_session_id()}"
                session = await manager.create_session(
                    session_id=session_id,
                    organization_id="org_apex_univ",
                    agent_id="agent_admission",
                    call_id=call_sid,
                    language="en-IN",
                    client_sample_rate=16000
                )

                engine = build_default_engine(session)
                await engine.start()

                # Start outbound writer loop
                writer_task = asyncio.create_task(exotel_audio_writer_loop(engine.queues.event_out_queue))

            # 3. Media Event (Inbound Caller Audio)
            elif event_type == "media":
                if not engine or not session:
                    continue

                inbound_media_count += 1
                if inbound_media_count <= 5 or inbound_media_count % 50 == 0:
                    logger.info(f"[EXOTEL_INBOUND_MEDIA] count={inbound_media_count} stream_sid={stream_sid}")

                media_payload = data.get("media", {}) if isinstance(data.get("media"), dict) else {}
                payload_b64 = media_payload.get("payload", "") or data.get("payload", "")
                if not payload_b64:
                    continue

                raw_bytes = base64.b64decode(payload_b64)
                
                # Decode to 16kHz PCM16 for Voice Engine
                if "mulaw" in encoding.lower() or "pcmu" in encoding.lower():
                    pcm_8k = AudioCodec.mulaw_to_pcm16(raw_bytes)
                else:
                    pcm_8k = raw_bytes  # Standard Exotel SLIN PCM16

                if sample_rate == 8000:
                    pcm_16k = AudioCodec.resample_linear(pcm_8k, orig_sr=8000, target_sr=16000)
                else:
                    pcm_16k = pcm_8k

                frame = AudioFrame(
                    data=pcm_16k,
                    sample_rate=16000,
                    channels=1,
                    sample_width=2
                )
                await engine.push_audio_frame(frame)

            # 4. Stop Event (Call Hangup)
            elif event_type == "stop":
                logger.info(f"[EXOTEL_STREAM] Call ended (stop event): stream_sid={stream_sid}")
                break

    except WebSocketDisconnect:
        logger.info(f"[EXOTEL_STREAM] WebSocket disconnected for stream_sid={stream_sid}")
    except Exception as e:
        logger.error(f"[EXOTEL_STREAM] Error in Exotel WebSocket stream: {e}", exc_info=True)
    finally:
        if writer_task and not writer_task.done():
            writer_task.cancel()
            try:
                await writer_task
            except asyncio.CancelledError:
                pass
        
        if engine:
            await engine.stop()
            logger.info(f"[EXOTEL_STREAM] Engine stopped for stream_sid={stream_sid}")
        
        if session:
            await manager.close_session(session.session_id)
            logger.info(f"[EXOTEL_STREAM] Session {session.session_id} closed cleanly")
