"""Realtime WebSocket endpoint implementing the voice-session protocol."""
import json
import asyncio
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.session.state import SessionState
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
    vad = SileroVADProvider(threshold=settings.vad_threshold, sample_rate=settings.sample_rate)

    # STT
    if settings.sarvam_api_key:
        stt = SarvamSTTProvider(api_key=settings.sarvam_api_key, model=settings.stt_model)
    else:
        stt = MockSTTProvider()

    # LLM (Sarvam-only production baseline)
    if settings.sarvam_api_key:
        llm = SarvamLLMProvider(api_key=settings.sarvam_api_key, model=settings.llm_model)
    else:
        llm = MockLLMProvider()

    # TTS
    if settings.sarvam_api_key:
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
    registry = ToolRegistry()
    registry.register(GetCoursesTool())
    registry.register(GetFeeTool())
    registry.register(GetEligibilityTool())
    registry.register(GetAdmissionDatesTool())
    registry.register(GetDocumentsRequiredTool())
    registry.register(GetHostelInformationTool())
    registry.register(GetCampusInformationTool())
    registry.register(CreateLeadTool())
    registry.register(RequestHumanHandoffTool())

    conv_manager = ConversationManager(rag_provider=rag, tool_registry=registry)

    return SpeechToSpeechEngine(
        session=session,
        vad_provider=vad,
        stt_provider=stt,
        llm_provider=llm,
        tts_provider=tts,
        conversation_manager=conv_manager,
        min_silence_duration_ms=settings.normal_silence_ms,
        structured_input_silence_ms=settings.structured_input_silence_ms
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
                    org_id = payload.get("organization_id", "org_apex_univ")
                    agent_id = payload.get("agent_id", "agent_admission")
                    lang = payload.get("language", "te-IN")
                    sr = int(payload.get("client_sample_rate", 16000))

                    session = await manager.create_session(
                        session_id=sess_id,
                        organization_id=org_id,
                        agent_id=agent_id,
                        language=lang,
                        client_sample_rate=sr
                    )

                    engine = build_default_engine(session)
                    await engine.start()
                    writer_task = asyncio.create_task(event_writer_loop(engine.queues.event_out_queue))

                    await websocket.send_text(json.dumps({
                        "event": "session.ready",
                        "session_id": sess_id,
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

                # 3. session.end
                elif event_type == "session.end":
                    if session:
                        # Extract intelligence before closing
                        lead = LeadExtractor.extract_from_messages(session.messages)
                        summary = CallSummarizer.generate_summary(session.session_id, session.messages, handoff_requested=session.handoff_requested)
                        
                        await websocket.send_text(json.dumps({
                            "event": "lead.extracted",
                            "session_id": session.session_id,
                            "lead": lead.model_dump()
                        }))
                        await websocket.send_text(json.dumps({
                            "event": "call.summary",
                            "session_id": session.session_id,
                            "summary": summary.model_dump()
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
