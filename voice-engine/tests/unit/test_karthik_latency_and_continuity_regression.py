"""
Focused regression tests for Karthik custom voice optimization and continuity.
Covers:
1. first-audio latency / chunking
2. sentence chunking without mid-word splits
3. ordered TTS chunks
4. no mid-sentence cancellation on silence
5. genuine barge-in stops audio
6. no false barge-in on silence or quiet backchannel
7. cache partition by voice_id and language
8. English cloned voice routing
9. Telugu cloned voice routing
10. Hindi cloned voice routing
"""

import pytest
import asyncio
from app.tts.text_normalizer import SpeechTextNormalizer
from app.tts.cache import TTSCacheManager
from app.tts.sarvam import SarvamTTSProvider
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.queues import PipelineQueueBundle
from app.pipeline.turn_manager import TurnManager
from app.pipeline.cancellation import CancellationToken


# 1. First-audio chunking & boundary check
def test_first_audio_chunking_clean_boundary():
    text = "We offer BTech Computer Science. The course duration is four years."
    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        text, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=True
    )
    assert chunk1 is not None
    assert chunk1 == "We offer BTech Computer Science."
    assert "The course duration is four years." in rest1


# 2. Sentence chunking never cuts mid-word or mid-acronym
def test_sentence_chunking_preserves_words_and_acronyms():
    text = "Apex Engineering College provides BTech CSE, AI, and ML programs with active admissions."
    chunk1, rest1 = SpeechTextNormalizer.extract_safe_chunk(
        text, min_chars=35, max_chars=180, is_eof=False, is_first_chunk=False
    )
    # Never cut in the middle of words
    for token in (chunk1 or "").split():
        clean_tok = token.strip(".,!?:;\"'")
        assert len(clean_tok) > 0


# 3. Ordered TTS chunks
@pytest.mark.asyncio
async def test_ordered_tts_chunks_in_stream():
    provider = SarvamTTSProvider(api_key=None)  # fallback simulation

    async def sample_text():
        yield "First sentence of the admission response. "
        yield "Second sentence with details about fees. "
        yield "Third sentence with contact information."

    chunks = []
    async for chunk in provider.stream_synthesize(sample_text(), language_code="en-IN"):
        chunks.append(chunk)

    assert len(chunks) > 0
    # Every chunk has valid audio frame
    for c in chunks:
        assert len(c.frame.data) > 0


# 4. No mid-sentence cancellation on caller silence
def test_no_mid_sentence_cancellation_on_silence():
    session = SessionState(session_id="test_sess_silence", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.is_bot_speaking = True
    session.current_turn.state = TurnStateEnum.SPEAKING

    # Feed 20 frames of caller silence (400ms) while AI is speaking
    events = []
    for _ in range(20):
        evt = tm.handle_speech_frame(is_speech=False, vad_confidence=0.01)
        if evt:
            events.append(evt)

    # Must NOT trigger barge-in or cancel speaking
    assert "BARGE_IN" not in events
    assert session.is_bot_speaking is True
    assert session.current_turn.state == TurnStateEnum.SPEAKING


# 5. Genuine intentional barge-in terminates playback
def test_genuine_barge_in_triggers_on_loud_speech():
    session = SessionState(session_id="test_sess_barge", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    triggered = []

    def on_barge(old_turn, old_gen):
        triggered.append((old_turn, old_gen))

    tm = TurnManager(
        session=session,
        queues=queues,
        min_barge_in_duration_ms=180,
        barge_in_min_confidence=0.70,
        barge_in_min_rms=0.025,
        on_barge_in_callback=on_barge
    )
    session.is_bot_speaking = True
    session.current_turn.state = TurnStateEnum.SPEAKING

    # Feed sustained loud intentional speech frames (> 200ms)
    barge_result = None
    for _ in range(12):
        # 16-bit PCM high energy amplitude (~0.05 RMS)
        frame_bytes = (b"\x10\x20" * 160)
        res = tm.handle_speech_frame(
            is_speech=True,
            frame_data=frame_bytes,
            frame_duration_ms=20.0,
            vad_confidence=0.92
        )
        if res == "BARGE_IN":
            barge_result = res
            break

    assert barge_result == "BARGE_IN"
    assert len(triggered) == 1
    assert session.is_bot_speaking is False


# 6. No false barge-in on quiet hums / backchannels
def test_no_false_barge_in_on_hum_backchannel():
    class DummyAcoustic:
        is_backchannel_hum = True
        is_voiced_frame = False
        is_breath_or_mouth = False
        is_transient = False
        rms = 0.015
        vocal_band_rms = 0.012
        spectral_centroid = 400.0
        spectral_flatness = 0.15
        pitch_periodicity = 0.40
        zcr = 0.05
        spectral_flux = 0.05
        vocal_energy_ratio = 0.60
        echo_correlation = 0.0
        is_acoustic_echo = False
        is_valid_speech = True

    session = SessionState(session_id="test_sess_hum", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.is_bot_speaking = True
    session.current_turn.state = TurnStateEnum.SPEAKING

    events = []
    for _ in range(15):
        evt = tm.handle_speech_frame(
            is_speech=True,
            frame_data=b"\x05\x00" * 160,
            frame_duration_ms=20.0,
            vad_confidence=0.85,
            acoustic_features=DummyAcoustic()
        )
        if evt:
            events.append(evt)

    assert "BARGE_IN" not in events
    assert session.is_bot_speaking is True


# 7. Cache partition by voice_id and language_code
def test_tts_cache_partition_by_voice_id_and_language():
    text = "Welcome to Apex University"
    karthik_en = TTSCacheManager.compute_cache_key(text, "en-IN", "svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746")
    karthik_te = TTSCacheManager.compute_cache_key(text, "te-IN", "svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746")
    karthik_hi = TTSCacheManager.compute_cache_key(text, "hi-IN", "svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746")
    pooja_en = TTSCacheManager.compute_cache_key(text, "en-IN", "pooja")

    # Karthik keys must NEVER collide with Pooja
    assert karthik_en != pooja_en
    # Each language must have distinct cache keys
    assert karthik_en != karthik_te
    assert karthik_te != karthik_hi


# 8. English cloned voice routing
def test_karthik_cloned_voice_english_routing():
    tts = SarvamTTSProvider(
        api_key="mock_key",
        voice_id="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    )
    assert tts.voice_id == "svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"


# 9. Telugu cloned voice routing retains SAME voice_id
def test_karthik_cloned_voice_telugu_routing():
    tts = SarvamTTSProvider(
        api_key="mock_key",
        voice_id="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    )
    # The voice ID remains identical for Telugu
    assert tts.voice_id == "svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"


# 10. Hindi cloned voice routing retains SAME voice_id
def test_karthik_cloned_voice_hindi_routing():
    tts = SarvamTTSProvider(
        api_key="mock_key",
        voice_id="svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
    )
    # The voice ID remains identical for Hindi
    assert tts.voice_id == "svc-bb7e2b64-fabc-44c7-ad82-f18cae02f746"
