"""Shared pytest fixtures and test doubles."""
import sys
import os
import pytest
import numpy as np

# Ensure app package is on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.audio.frames import AudioFrame
from app.session.state import SessionState
from app.vad.mock import MockVADProvider
from app.stt.mock import MockSTTProvider
from app.llm.mock import MockLLMProvider
from app.tts.mock import MockTTSProvider
from app.rag.mock import MockRAGProvider
from app.tools.base import ToolRegistry
from app.tools.admission import GetCoursesTool, GetFeeTool, GetEligibilityTool, CreateLeadTool
from app.tools.handoff import RequestHumanHandoffTool
from app.conversation.manager import ConversationManager
from app.pipeline.engine import SpeechToSpeechEngine


@pytest.fixture
def sample_speech_frame() -> AudioFrame:
    """Generate 20ms of synthetic speech-like harmonic waveform PCM16."""
    num_samples = int(16000 * 0.02)
    t = np.linspace(0, 0.02, num_samples, endpoint=False)
    # Natural voice harmonics (F0=130Hz + formants at 400Hz, 1200Hz, 2400Hz)
    waveform = (
        0.35 * np.sin(2 * np.pi * 130 * t) +
        0.30 * np.sin(2 * np.pi * 400 * t) +
        0.20 * np.sin(2 * np.pi * 1200 * t) +
        0.15 * np.sin(2 * np.pi * 2400 * t)
    )
    waveform = (waveform * 0.8 * 32767.0).astype(np.int16)
    return AudioFrame(data=waveform.tobytes(), sample_rate=16000, is_speech=True)


@pytest.fixture
def sample_silence_frame() -> AudioFrame:
    """Generate 20ms of silence."""
    return AudioFrame.silence(duration_ms=20, sample_rate=16000)


@pytest.fixture
def test_session() -> SessionState:
    """Create isolated test session."""
    return SessionState(
        session_id="test_session_001",
        organization_id="org_apex_univ",
        agent_id="agent_admission",
        language="te-IN"
    )


@pytest.fixture
def mock_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(GetCoursesTool())
    reg.register(GetFeeTool())
    reg.register(GetEligibilityTool())
    reg.register(CreateLeadTool())
    reg.register(RequestHumanHandoffTool())
    return reg


@pytest.fixture
def mock_conversation_manager(mock_tool_registry) -> ConversationManager:
    rag = MockRAGProvider()
    return ConversationManager(rag_provider=rag, tool_registry=mock_tool_registry)


@pytest.fixture
def test_s2s_engine(test_session, mock_conversation_manager) -> SpeechToSpeechEngine:
    return SpeechToSpeechEngine(
        session=test_session,
        vad_provider=MockVADProvider(default_is_speech=True),
        stt_provider=MockSTTProvider(default_text="What is the fee for BTech CSE?"),
        llm_provider=MockLLMProvider(),
        tts_provider=MockTTSProvider(),
        conversation_manager=mock_conversation_manager,
        min_silence_duration_ms=150,
        min_speech_duration_ms=20
    )
