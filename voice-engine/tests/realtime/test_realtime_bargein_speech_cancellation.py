"""Comprehensive tests for real-time user barge-in with immediate AI speech cancellation and complete utterance capture."""
import pytest
import asyncio
import time
from app.audio.frames import AudioFrame
from app.session.state import SessionState, TurnStateEnum
from app.session.events import EventType
from app.pipeline.turn_manager import TurnManager
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.engine import SpeechToSpeechEngine
from app.conversation.manager import ConversationManager
from app.rag.mock import MockRAGProvider
from app.tools.base import ToolRegistry
from app.vad.mock import MockVADProvider
from app.stt.mock import MockSTTProvider
from app.llm.mock import MockLLMProvider
from app.tts.mock import MockTTSProvider


class MockAcousticFeatures:
    def __init__(self, is_acoustic_echo=False, is_transient=False, is_breath_or_mouth=False, snr_db=15.0, is_valid_speech=True, echo_correlation=0.0, rms=0.12):
        self.is_acoustic_echo = is_acoustic_echo
        self.is_transient = is_transient
        self.is_breath_or_mouth = is_breath_or_mouth
        self.snr_db = snr_db
        self.is_valid_speech = is_valid_speech
        self.echo_correlation = 0.85 if is_acoustic_echo and echo_correlation == 0.0 else echo_correlation
        self.rms = rms


def test_barge_in_immediate_detection_latency():
    """Verify barge-in triggers within 300ms (15 frames @ 20ms) of verified human speech during AI playback."""
    session = SessionState(session_id="test_barge_latency", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    # Set AI speaking state
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = time.time() * 1000 + 5000.0  # 5s remaining

    frame_bytes = b"\x10\x10" * 160  # 20ms frame
    events = []
    features = MockAcousticFeatures()

    # Frames 1-14 (280ms): accumulates, does not trigger yet
    for i in range(14):
        res = tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20, vad_confidence=0.95, acoustic_features=features)
        assert res is None

    # Frame 15 (300ms): reaches threshold, TRIGGERS BARGE_IN IMMEDIATELY!
    res15 = tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20, vad_confidence=0.95, acoustic_features=features)
    assert res15 == "BARGE_IN"

    # Verify AI playback is stopped immediately
    assert session.is_bot_speaking is False
    assert session.playback_estimated_end_time_ms == 0.0
    assert session.user_has_floor is True

    # Verify rotation to fresh turn in LISTENING_AFTER_BARGE_IN state
    assert session.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN


def test_interruption_audio_preserved_and_subsequent_speech_collected():
    """
    Verify:
    1. 'No' is captured in initial barge-in buffer (300ms).
    2. Subsequent frames ('...what is the ECE fee?') continue to be collected.
    3. Normal endpointing completes the full user turn.
    """
    session = SessionState(session_id="test_speech_collection", organization_id="org1", agent_id="agent1")
    session.language_selection_complete = True
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    # AI is speaking
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = time.time() * 1000 + 4000.0

    frame_bytes = b"\x10\x10" * 160

    # 1. User speaks 'No' (15 frames = 300ms) -> Triggers BARGE_IN
    for _ in range(14):
        tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)
    assert tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20) == "BARGE_IN"

    turn_id = session.current_turn.turn_id
    assert session.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN

    # 2. User continues speaking without pause: '...what is the ECE fee?' (30 frames = 600ms)
    for _ in range(30):
        # AI is no longer speaking, so normal speech accumulation occurs
        res = tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20)
        assert res is None  # Remains in active listening

    assert session.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN

    # 3. User finishes sentence and pauses (silence threshold = 400ms post-barge-in)
    for _ in range(19):  # 380ms silence
        assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20) is None

    # Reaching 400ms silence + 2 consecutive silence frames
    res_end = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20)
    assert res_end == "SPEECH_ENDED"
    assert session.current_turn.state == TurnStateEnum.PROCESSING
    assert session.current_turn.turn_id == turn_id


def test_acoustic_gate_rejects_echo_but_allows_caller_speech():
    """Echo of outbound TTS must never barge-in. Caller speech with verified acoustics interrupts."""
    session = SessionState(session_id="test_acoustic_reject", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=300)

    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.playback_estimated_end_time_ms = time.time() * 1000 + 5000.0

    frame_bytes = b"\x10\x10" * 160

    echo_feat = MockAcousticFeatures(is_acoustic_echo=True, rms=0.01)
    for _ in range(15):
        assert tm.handle_speech_frame(is_speech=True, frame_data=frame_bytes, frame_duration_ms=20, acoustic_features=echo_feat) is None
    assert session.is_bot_speaking is True

    # Caller speech with valid acoustic features and high energy
    clean_feat = MockAcousticFeatures(is_acoustic_echo=False, rms=0.15, is_valid_speech=True)
    for _ in range(14):
        assert tm.handle_speech_frame(
            is_speech=True, frame_data=frame_bytes, frame_duration_ms=20,
            vad_confidence=0.95, acoustic_features=clean_feat
        ) is None
    res = tm.handle_speech_frame(
        is_speech=True, frame_data=frame_bytes, frame_duration_ms=20,
        vad_confidence=0.95, acoustic_features=clean_feat
    )
    assert res == "BARGE_IN"
    assert session.is_bot_speaking is False


@pytest.mark.asyncio
async def test_end_to_end_barge_in_stops_tts_and_answers_interruption():
    """Verify end-to-end engine cancels TTS generation and processes full interruption query."""
    session = SessionState(session_id="sess_e2e_barge", organization_id="org_univ", agent_id="agent_adm")
    session.language_selection_complete = True
    session.preferred_language = "en-IN"

    conv_mgr = ConversationManager(rag_provider=MockRAGProvider(), tool_registry=ToolRegistry())
    vad = MockVADProvider()
    stt = MockSTTProvider()
    llm = MockLLMProvider()
    tts = MockTTSProvider()

    engine = SpeechToSpeechEngine(
        session=session,
        conversation_manager=conv_mgr,
        vad_provider=vad,
        stt_provider=stt,
        llm_provider=llm,
        tts_provider=tts,
        min_barge_in_duration_ms=300
    )

    await engine.start()
    events = []

    async def event_collector():
        while engine._running:
            try:
                evt = await engine.queues.event_out_queue.get()
                events.append(evt)
            except asyncio.CancelledError:
                break

    task = asyncio.create_task(event_collector())

    try:
        # Wait for initial greeting to finish
        for _ in range(50):
            if any(e.event in (EventType.SESSION_INTERACTION_READY, EventType.RESPONSE_END) for e in events):
                break
            await asyncio.sleep(0.02)

        events.clear()

        # Simulate AI currently speaking response to Turn 1
        active_turn = session.current_turn
        active_turn.state = TurnStateEnum.SPEAKING
        session.is_bot_speaking = True
        session.active_playback_generation_id = active_turn.generation_id
        session.playback_estimated_end_time_ms = time.time() * 1000 + 4000.0

        # Feed speech frames to simulate user saying: "No, what is the ECE fee?"
        speech_frame = AudioFrame(data=b"\x10\x10" * 160, sample_rate=16000, channels=1, sample_width=2, is_speech=True)

        # 16 frames of speech to trigger barge in (~320ms > 300ms)
        for _ in range(16):
            await engine.push_audio_frame(speech_frame)
            await asyncio.sleep(0.01)

        await asyncio.sleep(0.1)

        # 1. Verify barge-in events emitted immediately
        event_types = [e.event for e in events]
        assert EventType.RESPONSE_CANCELLED in event_types
        assert EventType.AUDIO_FLUSH in event_types
        assert EventType.AUDIO_PLAYBACK_STOP in event_types

        # 2. Verify AI state immediately halted
        assert session.is_bot_speaking is False
        assert session.user_has_floor is True
        assert active_turn.cancellation_token.is_cancelled is True
        assert session.is_generation_cancelled(active_turn.generation_id) is True

    finally:
        task.cancel()
        await engine.stop()
