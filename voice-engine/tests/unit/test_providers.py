"""Unit tests for VAD, STT, LLM, and TTS provider adapters."""
import pytest
from app.audio.frames import AudioFrame
from app.vad.silero import SileroVADProvider
from app.vad.mock import MockVADProvider
from app.stt.mock import MockSTTProvider
from app.llm.mock import MockLLMProvider
from app.tts.mock import MockTTSProvider
from app.pipeline.cancellation import CancellationToken


@pytest.mark.asyncio
async def test_vad_providers(sample_speech_frame, sample_silence_frame):
    # Test Mock VAD
    mock_vad = MockVADProvider()
    res_speech = await mock_vad.is_speech(sample_speech_frame)
    assert res_speech.is_speech is True
    
    res_silence = await mock_vad.is_speech(sample_silence_frame)
    assert res_silence.is_speech is False

    # Test Silero VAD
    silero_vad = SileroVADProvider(threshold=0.35)
    res_speech_silero = await silero_vad.is_speech(sample_speech_frame)
    assert res_speech_silero is not None
    assert isinstance(res_speech_silero.confidence, float)

    silero_vad.reset()
    res_silence_silero = await silero_vad.is_speech(sample_silence_frame)
    assert res_silence_silero.is_speech is False


@pytest.mark.asyncio
async def test_mock_stt_transcription():
    stt = MockSTTProvider(default_text="Namaste, CSE fee details cheppandi")
    res = await stt.transcribe_audio(b"fake_pcm")
    assert res.text == "Namaste, CSE fee details cheppandi"
    assert res.language_code == "te-IN"


@pytest.mark.asyncio
async def test_mock_llm_streaming():
    llm = MockLLMProvider(default_response="BTech CSE fee is INR 1,50,000 per year.")
    messages = [{"role": "user", "content": "What is CSE fee?"}]
    
    tokens = []
    async for chunk in llm.stream_chat(messages):
        tokens.append(chunk.delta)
    
    full_text = "".join(tokens).strip()
    assert "1,50,000" in full_text


@pytest.mark.asyncio
async def test_mock_tts_streaming():
    tts = MockTTSProvider(sample_rate=16000)
    
    async def sample_text():
        yield "Welcome to "
        yield "Apex University"

    frames = []
    async for chunk in tts.stream_synthesize(sample_text(), language_code="en-IN"):
        frames.append(chunk.frame)

    assert len(frames) > 0
    assert frames[0].sample_rate == 16000
    assert len(frames[0].data) == 640  # 20ms frame


@pytest.mark.asyncio
async def test_sarvam_llm_fallback_and_cancellation():
    from app.llm.sarvam import SarvamLLMProvider
    from app.pipeline.cancellation import CancellationToken

    # 1. Test fallback simulation when api_key is None
    sarvam_llm = SarvamLLMProvider(api_key=None)
    messages = [{"role": "user", "content": "Tell me about fees"}]

    tokens = []
    async for chunk in sarvam_llm.stream_chat(messages):
        tokens.append(chunk.delta)
    assert len(tokens) > 0
    assert "Apex University" in "".join(tokens)

    # 2. Test cancellation token aborting stream immediately
    token = CancellationToken()
    token.cancel()
    cancelled_tokens = []
    async for chunk in sarvam_llm.stream_chat(messages, cancellation_token=token):
        cancelled_tokens.append(chunk.delta)
    assert len(cancelled_tokens) == 0


@pytest.mark.asyncio
async def test_sarvam_llm_mocked_http_streaming(monkeypatch):
    from app.llm.sarvam import SarvamLLMProvider
    from app.core.errors import LLMError
    import httpx

    sarvam_llm = SarvamLLMProvider(api_key="mock_sarvam_key", model="sarvam-105b-conversations")

    # Mock SSE streaming response
    sse_lines = [
        b'data: {"choices": [{"delta": {"content": "BTech "}}]}\n',
        b'data: {"choices": [{"delta": {"content": "CSE "}}]}\n',
        b'data: {"choices": [{"delta": {"content": "admissions."}, "finish_reason": "stop"}]}\n',
        b'data: [DONE]\n'
    ]

    class MockAsyncResponse:
        def __init__(self, status_code=200):
            self.status_code = status_code

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_lines(self):
            for line in sse_lines:
                yield line.decode("utf-8")

        async def aread(self):
            return b"Internal Server Error"

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url, **kwargs):
            return MockAsyncResponse(status_code=200)

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
    sarvam_llm._client = None

    # Verify streamed response
    tokens = []
    async for chunk in sarvam_llm.stream_chat([{"role": "user", "content": "Hi"}]):
        tokens.append(chunk.delta)

    assert "".join(tokens) == "BTech CSE admissions."

    # Test HTTP Error handling
    class MockErrorAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url, **kwargs):
            return MockAsyncResponse(status_code=500)

    monkeypatch.setattr(httpx, "AsyncClient", MockErrorAsyncClient)
    sarvam_llm._client = None

    with pytest.raises(LLMError) as exc_info:
        async for _ in sarvam_llm.stream_chat([{"role": "user", "content": "Hi"}]):
            pass
    assert "Sarvam LLM stream returned 500" in str(exc_info.value)
