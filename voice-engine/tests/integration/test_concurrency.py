"""Level 3 Concurrency & Multi-Session Isolation tests."""
import pytest
import asyncio
from app.session.manager import SessionManager
from app.pipeline.engine import SpeechToSpeechEngine
from app.vad.mock import MockVADProvider
from app.stt.mock import MockSTTProvider
from app.llm.mock import MockLLMProvider
from app.tts.mock import MockTTSProvider
from app.conversation.manager import ConversationManager
from app.rag.mock import MockRAGProvider
from app.audio.frames import AudioFrame


@pytest.mark.asyncio
async def test_concurrent_sessions_zero_leakage():
    """Run 3 simultaneous voice sessions and verify completely isolated contexts."""
    manager = SessionManager()
    rag = MockRAGProvider()
    
    # Session A: Inquiring about CSE
    sess_a = await manager.create_session("sess_A", "org_apex_univ", "agent_1")
    conv_a = ConversationManager(rag_provider=rag)
    engine_a = SpeechToSpeechEngine(
        session=sess_a,
        vad_provider=MockVADProvider(),
        stt_provider=MockSTTProvider(default_text="What is CSE fee?"),
        llm_provider=MockLLMProvider(default_response="CSE fee is INR 1,50,000."),
        tts_provider=MockTTSProvider(),
        conversation_manager=conv_a,
        min_silence_duration_ms=150,
        min_speech_duration_ms=20
    )

    # Session B: Inquiring about Hostel
    sess_b = await manager.create_session("sess_B", "org_apex_univ", "agent_1")
    conv_b = ConversationManager(rag_provider=rag)
    engine_b = SpeechToSpeechEngine(
        session=sess_b,
        vad_provider=MockVADProvider(),
        stt_provider=MockSTTProvider(default_text="What is hostel fee?"),
        llm_provider=MockLLMProvider(default_response="Hostel fee is INR 80,000."),
        tts_provider=MockTTSProvider(),
        conversation_manager=conv_b,
        min_silence_duration_ms=150,
        min_speech_duration_ms=20
    )

    sess_a.language_selection_complete = True
    sess_b.language_selection_complete = True

    await engine_a.start()
    await engine_b.start()

    speech_frame = AudioFrame.silence(duration_ms=20)
    speech_frame.is_speech = True
    silence_frame = AudioFrame.silence(duration_ms=20)

    try:
        # Feed speech and silence concurrently into both engines
        async def feed_session(engine):
            for _ in range(15):
                await engine.push_audio_frame(speech_frame)
                await asyncio.sleep(0.01)
            for _ in range(40):
                await engine.push_audio_frame(silence_frame)
                await asyncio.sleep(0.01)

        await asyncio.gather(
            feed_session(engine_a),
            feed_session(engine_b)
        )

        await asyncio.sleep(1.0)

        # Invariant checks:
        # 1. Messages in Session A must contain CSE and zero hostel leaks
        assert len(sess_a.messages) >= 2
        assert any("CSE fee" in m["content"] for m in sess_a.messages)
        assert not any("hostel" in m["content"].lower() for m in sess_a.messages)

        # 2. Messages in Session B must contain Hostel and zero CSE leaks
        assert len(sess_b.messages) >= 2
        assert any("hostel fee" in m["content"].lower() for m in sess_b.messages)
        assert not any("cse" in m["content"].lower() for m in sess_b.messages)

    finally:
        await engine_a.stop()
        await engine_b.stop()
        await manager.close_session("sess_A")
        await manager.close_session("sess_B")
