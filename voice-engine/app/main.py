"""Main FastAPI application entrypoint for Edu-Voice Voice Engine."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.health import router as health_router
from app.api.websocket import router as ws_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(level=settings.log_level)
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown hooks."""
    import asyncio
    logger.info("Initializing Edu-Voice-AI Realtime Voice Engine...")
    logger.info(
        f"[CONFIG] STT model: {settings.stt_model} | LLM model: {settings.llm_model} | TTS model: {settings.tts_model} | Supported languages: {', '.join(settings.supported_languages)}"
    )
    # Initialize TTS deduplication cache
    from app.tts.cache import TTSCacheManager
    TTSCacheManager.initialize()

    # Optional background warm-up of FastRouter TTS cache (default disabled to prevent cost explosion)
    if settings.enable_startup_tts_precache:
        try:
            from app.tts.sarvam import SarvamTTSProvider
            from app.pipeline.engine import SpeechToSpeechEngine
            tts = SarvamTTSProvider(api_key=settings.sarvam_api_key, model=settings.tts_model, default_speaker=settings.tts_speaker)
            asyncio.create_task(SpeechToSpeechEngine.warmup_fast_query_cache(tts))
        except Exception as e:
            logger.warning(f"Failed to trigger FastRouter TTS pre-caching: {e}")
    else:
        logger.info("[FAST_CACHE] Startup live API TTS pre-caching is disabled (on-demand caching enabled)")
    yield
    logger.info("Shutting down Edu-Voice-AI Realtime Voice Engine...")


app = FastAPI(
    title="Edu-Voice-AI Realtime Voice Engine",
    description="Low-latency S2S Voice Engine with Silero VAD, Sarvam STT/TTS, Sarvam-105B LLM, RAG & Barge-In",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware for local frontend/test clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach routers
app.include_router(health_router)
app.include_router(ws_router)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
