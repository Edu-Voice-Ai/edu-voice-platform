"""Realtime WebSocket endpoint implementing the voice-session protocol."""
import json
import asyncio
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.session.state import SessionState, HandoffStateEnum
from app.session.events import SessionEvent, EventType
from app.session.manager import get_session_manager
from app.pipeline.engine import SpeechToSpeechEngine
from app.vad.silero import SileroVADProvider
from app.vad.mock import MockVADProvider
from app.stt.sarvam import SarvamSTTProvider
from app.stt.mock import MockSTTProvider
from app.llm.sarvam import SarvamLLMProvider
from app.llm.mock import MockLLMProvider
from app.tts.sarvam import SarvamTTSProvider
from app.tts.elevenlabs import ElevenLabsTTSProvider
from app.tts.mock import MockTTSProvider
from app.rag.mock import MockRAGProvider
from app.rag.client import BackendRAGClient
from app.tools.base import ToolRegistry
from app.tools.admission import (
    GetCoursesTool,
    GetFeeTool,
    GetEligibilityTool,
    GetAdmissionDatesTool,
    GetDocumentsRequiredTool,
    GetHostelInformationTool,
    GetCampusInformationTool,
    CreateLeadTool,
)
from app.tools.handoff import RequestHumanHandoffTool
from app.conversation.manager import ConversationManager
from app.intelligence.lead_extraction import LeadExtractor
from app.intelligence.summary import CallSummarizer
from app.core.config import get_settings
from app.core.ids import generate_session_id
from app.core.logging import get_logger

logger = get_logger("api.websocket")
router = APIRouter(tags=["Realtime Voice"])


def build_default_engine(session: SessionState) -> SpeechToSpeechEngine:
    """Instantiate standard engine with configured or fallback providers."""
    settings = get_settings()

    # VAD
    vad = SileroVADProvider(
        threshold=settings.vad_threshold,
        barge_in_threshold=settings.vad_barge_in_threshold,
        sample_rate=settings.sample_rate
    )

    # STT
    if getattr(settings, "stt_provider", "sarvam").lower() == "mock":
        stt = MockSTTProvider()
    elif settings.sarvam_api_key:
        stt = SarvamSTTProvider(api_key=settings.sarvam_api_key, model=settings.stt_model)
    else:
        stt = MockSTTProvider()

    # LLM (Sarvam-only production baseline or configurable mock)
    if getattr(settings, "llm_provider", "sarvam").lower() == "mock":
        llm = MockLLMProvider()
    elif settings.sarvam_api_key:
        llm = SarvamLLMProvider(api_key=settings.sarvam_api_key, model=settings.llm_model)
    else:
        llm = MockLLMProvider()

    # TTS (Supports Sarvam primary, ElevenLabs fallback, and Mock configurable via TTS_PROVIDER)
    tts_prov = getattr(settings, "tts_provider", "sarvam").lower()
    if tts_prov == "elevenlabs" and settings.elevenlabs_api_key:
        tts = ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key)
    elif tts_prov == "mock":
        tts = MockTTSProvider(sample_rate=settings.sample_rate)
    elif settings.sarvam_api_key:
        tts = SarvamTTSProvider(
            api_key=settings.sarvam_api_key,
            model=settings.tts_model,
            default_speaker=settings.tts_speaker,
            min_chars=settings.tts_min_chars,
            max_chars=settings.tts_max_chars
        )
    elif settings.elevenlabs_api_key:
        tts = ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key)
    else:
        tts = MockTTSProvider(sample_rate=settings.sample_rate)

    # RAG & Tools
    if settings.rag_use_mock:
        rag = MockRAGProvider()
    else:
        rag = BackendRAGClient(endpoint_url=settings.rag_endpoint, api_key=settings.sarvam_api_key)

    from app.templates.registry import AgentTemplateRegistry
    template = AgentTemplateRegistry.get_template(getattr(session, "template_type", "education"))
    registry = template.get_tool_registry()

    conv_manager = ConversationManager(rag_provider=rag, tool_registry=registry)

    speech_cfg = getattr(session, "speech_config", None) or {}
    vad_silence = speech_cfg.get("vad_silence_threshold_ms") or settings.normal_silence_ms

    return SpeechToSpeechEngine(
        session=session,
        vad_provider=vad,
        stt_provider=stt,
        llm_provider=llm,
        tts_provider=tts,
        conversation_manager=conv_manager,
        min_silence_duration_ms=float(vad_silence),
        structured_input_silence_ms=settings.structured_input_silence_ms,
        min_barge_in_duration_ms=settings.barge_in_confirmation_ms,
        barge_in_min_confidence=settings.barge_in_min_confidence,
        barge_in_min_rms=settings.barge_in_min_rms,
    )


@router.websocket("/ws/voice")
async def voice_websocket_endpoint(websocket: WebSocket):
    """Realtime full-duplex WebSocket connection for local microphone/audio streaming."""
    await websocket.accept()
    manager = get_session_manager()
    session: Optional[SessionState] = None
    engine: Optional[SpeechToSpeechEngine] = None
    writer_task: Optional[asyncio.Task] = None

    async def event_writer_loop(q: asyncio.Queue[SessionEvent]):
        """Pushes internal engine events down the WebSocket to the client."""
        while True:
            try:
                event = await q.get()
                if session:
                    if event.event in (EventType.RESPONSE_CANCELLED, EventType.AUDIO_PLAYBACK_STOP, EventType.AUDIO_FLUSH):
                        session.mark_playback_finished(force=True)
                    elif event.event in (EventType.RESPONSE_END, "response.end"):
                        session.mark_playback_finished(force=False)
                if event.event == EventType.HANDOFF_REQUESTED:
                    payload = {
                        "event": "handoff.requested",
                        "session_id": event.session_id,
                        "call_id": event.data.get("call_id") or (session.call_id if session else None),
                        "organization_id": event.data.get("organization_id") or (session.organization_id if session else None),
                        "agent_id": event.data.get("agent_id") or (session.agent_id if session else None),
                        "requested_role": event.data.get("requested_role", "admission_counselor"),
                        "requested_department": event.data.get("requested_department", "admissions"),
                        "reason": event.data.get("reason", "caller_requested_human"),
                        "confidence": float(event.data.get("confidence", 0.95)),
                        "timestamp": event.data.get("timestamp"),
                        "turn_id": event.turn_id,
                        "generation_id": event.generation_id,
                        "timestamp_ms": event.timestamp_ms,
                        "data": event.data
                    }
                elif event.event == EventType.HANDOFF_CANCELLED:
                    payload = {
                        "event": "handoff.cancelled",
                        "session_id": event.session_id,
                        "call_id": event.data.get("call_id") or (session.call_id if session else None),
                        "reason": event.data.get("reason", "caller_cancelled"),
                        "turn_id": event.turn_id,
                        "generation_id": event.generation_id,
                        "timestamp_ms": event.timestamp_ms,
                        "data": event.data
                    }
                else:
                    payload = {
                        "event": event.event.value,
                        "session_id": event.session_id,
                        "turn_id": event.turn_id,
                        "generation_id": event.generation_id,
                        "timestamp_ms": event.timestamp_ms,
                        "data": event.data
                    }
                await websocket.send_text(json.dumps(payload))
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.warning(f"Error sending WS event: {ex}")
                break

    try:
        while True:
            message = await websocket.receive()
            
            # Binary Audio Chunk
            if "bytes" in message and message["bytes"]:
                raw_bytes = message["bytes"]
                if engine and session and session.is_active:
                    frame = AudioFrame(data=raw_bytes, sample_rate=session.client_sample_rate)
                    await engine.push_audio_frame(frame)
                continue

            # Text / JSON Control Frame
            if "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({"event": "error", "message": "Invalid JSON format"}))
                    continue

                event_type = payload.get("event")

                # 1. session.start
                if event_type == "session.start":
                    sess_id = payload.get("session_id") or generate_session_id()
                    call_id = payload.get("call_id")
                    org_id = payload.get("organization_id")
                    agent_id = payload.get("agent_id")
                    if not org_id or not agent_id:
                        await websocket.send_text(json.dumps({
                            "event": "error",
                            "message": "organization_id and agent_id are required"
                        }))
                        continue

                    # Backend speech_config and handoff_config mappings
                    speech_cfg = payload.get("speech_config") if isinstance(payload.get("speech_config"), dict) else {}
                    handoff_cfg = payload.get("handoff_config") if isinstance(payload.get("handoff_config"), dict) else {}

                    lang = payload.get("language") or speech_cfg.get("primary_language") or payload.get("primary_language") or "en-IN"
                    sr = int(payload.get("client_sample_rate", 16000))
                    template_type = payload.get("template_type") or payload.get("template", "education")
                    biz_name = payload.get("business_name") or payload.get("institution_name", "Apex University")
                    agent_name = payload.get("agent_name")
                    greeting_msg = payload.get("greeting_message") or speech_cfg.get("welcome_message") or payload.get("welcome_message")
                    goodbye_msg = payload.get("goodbye_message") or speech_cfg.get("goodbye_message") or payload.get("goodbye_message")
                    sys_prompt = payload.get("system_prompt")

                    allow_barge_in = payload.get("allow_barge_in", speech_cfg.get("allow_barge_in", True))
                    max_call_duration_seconds = payload.get("max_call_duration_seconds", speech_cfg.get("max_call_duration_seconds"))

                    session = await manager.create_session(
                        session_id=sess_id,
                        organization_id=org_id,
                        agent_id=agent_id,
                        call_id=call_id,
                        language=lang,
                        client_sample_rate=sr,
                        template_type=template_type,
                        business_name=biz_name,
                        institution_name=biz_name,
                        agent_name=agent_name,
                        greeting_message=greeting_msg,
                        goodbye_message=goodbye_msg,
                        system_prompt=sys_prompt,
                        speech_config=speech_cfg or None,
                        handoff_config=handoff_cfg or None,
                        allow_barge_in=bool(allow_barge_in),
                        max_call_duration_seconds=int(max_call_duration_seconds) if max_call_duration_seconds else None
                    )

                    engine = build_default_engine(session)
                    await engine.start()
                    writer_task = asyncio.create_task(event_writer_loop(engine.queues.event_out_queue))

                    await websocket.send_text(json.dumps({
                        "event": "session.ready",
                        "session_id": sess_id,
                        "call_id": call_id,
                        "status": "ready"
                    }))

                # 2. audio.input (Base64 encoded PCM16)
                elif event_type == "audio.input":
                    if not engine or not session:
                        await websocket.send_text(json.dumps({"event": "error", "message": "Session not initialized"}))
                        continue

                    data_b64 = payload.get("data", "")
                    seq = payload.get("seq", 0)
                    if data_b64:
                        frame = AudioCodec.base64_to_frame(data_b64, sample_rate=session.client_sample_rate, seq=seq)
                        await engine.push_audio_frame(frame)

                # 3. handoff.acknowledged
                elif event_type == "handoff.acknowledged":
                    if engine and session:
                        status_val = payload.get("status", "resolving_target")
                        hold_media = payload.get("hold_media", True)
                        await engine.handle_handoff_acknowledged(status=status_val, hold_media=hold_media)

                # 4. handoff.fallback
                elif event_type == "handoff.fallback":
                    if engine and session:
                        reason_val = payload.get("reason", "NO_ELIGIBLE_STAFF")
                        prompt_inst = payload.get("prompt_instruction")
                        await engine.handle_handoff_fallback(reason=reason_val, prompt_instruction=prompt_inst)

                # 5. session.end
                elif event_type == "session.end":
                    if session:
                        reason = payload.get("reason", "normal")
                        if reason == "transferred_to_human":
                            session.handoff_state = HandoffStateEnum.TRANSFERRED
                        from app.templates.registry import AgentTemplateRegistry
                        template = AgentTemplateRegistry.get_template(getattr(session, "template_type", "education"))
                        lead = template.extract_lead(session.messages)
                        summary = template.generate_summary(session.session_id, session.messages, handoff=session.handoff_requested)
                        
                        await websocket.send_text(json.dumps({
                            "event": "lead.extracted",
                            "session_id": session.session_id,
                            "call_id": session.call_id,
                            "organization_id": session.organization_id,
                            "agent_id": session.agent_id,
                            "lead": lead
                        }))
                        await websocket.send_text(json.dumps({
                            "event": "call.summary",
                            "session_id": session.session_id,
                            "call_id": session.call_id,
                            "organization_id": session.organization_id,
                            "agent_id": session.agent_id,
                            "summary": summary
                        }))
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if writer_task and not writer_task.done():
            writer_task.cancel()
        if engine:
            await engine.stop()
        if session:
            await manager.close_session(session.session_id)
