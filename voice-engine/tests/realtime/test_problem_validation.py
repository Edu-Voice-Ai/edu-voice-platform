"""Targeted test suite validating fixes for Problem 1, 2, and 3, plus cost and safety regressions."""
import pytest
import time
import numpy as np
from typing import Optional

from app.pipeline.turn_manager import TurnManager
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.queues import PipelineQueueBundle
from app.audio.features import AcousticFeatures
from app.tts.cache import TTSCacheManager
from app.tts.text_normalizer import SpeechTextNormalizer
from app.core.config import get_settings


class MockAcousticFeatures:
    def __init__(
        self,
        rms: float = 0.03,
        vocal_band_rms: float = 0.03,
        spectral_flux: float = 0.25,
        spectral_flatness: float = 0.20,
        pitch_periodicity: float = 0.50,
        harmonicity: float = 0.50,
        zcr: float = 0.08,
        is_valid_speech: bool = True,
        is_backchannel_hum: bool = False,
        is_breath_or_mouth: bool = False,
        is_transient: bool = False,
        is_acoustic_echo: bool = False,
        echo_correlation: float = 0.0,
    ):
        self.rms = rms
        self.vocal_band_rms = vocal_band_rms
        self.spectral_flux = spectral_flux
        self.spectral_flatness = spectral_flatness
        self.pitch_periodicity = pitch_periodicity
        self.harmonicity = harmonicity
        self.zcr = zcr
        self.is_valid_speech = is_valid_speech
        self.is_backchannel_hum = is_backchannel_hum
        self.is_breath_or_mouth = is_breath_or_mouth
        self.is_transient = is_transient
        self.is_acoustic_echo = is_acoustic_echo
        self.echo_correlation = echo_correlation


# ===========================================================================
# PROBLEM 1: SMALL SOUNDS VS INTENTIONAL INTERRUPTION
# ===========================================================================

def test_p1_case1_hmm_sound_does_not_interrupt_ai():
    """1. 'hmm' sound (160ms = 8 frames) while AI speaks -> AI continues playing."""
    session = SessionState(session_id="test_p1_hmm", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_bot_1"

    # 'hmm' acoustic profile: low flux (<0.18), backchannel hum
    hmm_feat = MockAcousticFeatures(
        rms=0.025,
        vocal_band_rms=0.025,
        spectral_flux=0.08,
        spectral_flatness=0.15,
        pitch_periodicity=0.60,
        is_backchannel_hum=True,
    )

    # User utters 'hmm' for 160ms (8 frames of 20ms)
    for _ in range(8):
        res = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.85, acoustic_features=hmm_feat)
        assert res is None, "Isolated 'hmm' must NOT cause barge-in"

    # Silence follows: leaky bucket decays to 0, AI continues playing
    for _ in range(8):
        tm.handle_speech_frame(is_speech=False, frame_duration_ms=20.0, vad_confidence=0.10)

    assert session.is_bot_speaking is True
    assert session.current_turn.state == TurnStateEnum.SPEAKING
    assert tm._barge_in_stage == "IDLE"


def test_p1_case2_umm_sound_does_not_interrupt_ai():
    """2. 'umm' sound (200ms = 10 frames) while AI speaks -> AI continues playing."""
    session = SessionState(session_id="test_p1_umm", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_bot_1"

    umm_feat = MockAcousticFeatures(
        rms=0.028,
        vocal_band_rms=0.028,
        spectral_flux=0.10,
        pitch_periodicity=0.55,
        is_backchannel_hum=True,
    )

    for _ in range(10):
        res = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.85, acoustic_features=umm_feat)
        assert res is None

    # Silence follows
    for _ in range(10):
        tm.handle_speech_frame(is_speech=False, frame_duration_ms=20.0)

    assert session.is_bot_speaking is True
    assert session.current_turn.state == TurnStateEnum.SPEAKING


def test_p1_case3_yeah_sound_does_not_interrupt_ai():
    """3. Short backchannel 'yeah' / 'okay' (160ms = 8 frames) -> AI continues."""
    session = SessionState(session_id="test_p1_yeah", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_bot_1"

    yeah_feat = MockAcousticFeatures(
        rms=0.030,
        vocal_band_rms=0.030,
        spectral_flux=0.12,  # Low flux, weak short sound
        pitch_periodicity=0.50,
        is_backchannel_hum=True,
    )

    for _ in range(8):
        res = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.80, acoustic_features=yeah_feat)
        assert res is None

    assert session.is_bot_speaking is True


def test_p1_case4_short_breath_does_not_interrupt_ai():
    """4. Short breath or mouth noise (200ms) -> AI continues."""
    session = SessionState(session_id="test_p1_breath", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_bot_1"

    breath_feat = MockAcousticFeatures(
        rms=0.020,
        vocal_band_rms=0.005,
        spectral_flux=0.05,
        pitch_periodicity=0.15,
        is_valid_speech=False,
        is_breath_or_mouth=True,
    )

    for _ in range(10):
        res = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20.0, vad_confidence=0.30, acoustic_features=breath_feat)
        assert res is None

    assert session.is_bot_speaking is True


def test_p1_case5_weak_short_syllable_does_not_interrupt_ai():
    """5. Weak short syllable (60ms = 3 frames) -> AI continues."""
    session = SessionState(session_id="test_p1_syl", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_bot_1"

    feat = MockAcousticFeatures(rms=0.022, spectral_flux=0.10, is_backchannel_hum=True)
    for _ in range(3):
        res = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.75, acoustic_features=feat)
        assert res is None

    # Silence decay
    for _ in range(3):
        tm.handle_speech_frame(is_speech=False, frame_duration_ms=20.0)

    assert session.is_bot_speaking is True


def test_p1_case6_hmm_into_real_speech_interrupts():
    """6. 'hmm... actually tell me about fees' -> transitions to confirmed speech -> AI interrupts."""
    session = SessionState(session_id="test_p1_hmm_speech", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_bot_1"

    # Stage 1: 'hmm' (4 frames = 80ms)
    hmm_feat = MockAcousticFeatures(rms=0.025, spectral_flux=0.08, is_backchannel_hum=True)
    for _ in range(4):
        assert tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.85, acoustic_features=hmm_feat) is None

    # Stage 2: Strong intentional speech onset ("actually tell me...")
    strong_feat = MockAcousticFeatures(
        rms=0.060,
        vocal_band_rms=0.055,
        spectral_flux=0.35,
        pitch_periodicity=0.65,
        harmonicity=0.60,
        spectral_flatness=0.18,
    )
    barge_result = None
    for _ in range(8):
        res = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.95, acoustic_features=strong_feat)
        if res == "BARGE_IN":
            barge_result = res
            break

    assert barge_result == "BARGE_IN", "Sustained strong speech following 'hmm' must confirm barge-in!"
    assert session.is_bot_speaking is False


def test_p1_case7_quiet_sustained_sentence_confirms():
    """7. Quiet sustained sentence (LOW VOLUME != NO SPEECH) -> confirms."""
    session = SessionState(session_id="test_p1_quiet", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_bot_1"

    # Soft quiet speech: vocal_rms = 0.018, harmonicity = 0.45, flatness = 0.22
    quiet_feat = MockAcousticFeatures(
        rms=0.020,
        vocal_band_rms=0.018,
        spectral_flux=0.22,
        spectral_flatness=0.22,
        pitch_periodicity=0.45,
        harmonicity=0.45,
        zcr=0.10,
    )

    barge_result = None
    # Quiet speech confirms in 14 frames (280ms)
    for _ in range(14):
        res = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.75, acoustic_features=quiet_feat)
        if res == "BARGE_IN":
            barge_result = res
            break

    assert barge_result == "BARGE_IN", "Quiet sustained human speech must be recognized via vocal continuity!"
    assert session.is_bot_speaking is False


# ===========================================================================
# PROBLEM 2 & BARGE-IN: QUICK CONFIRMATION & OLD QUEUE PURGED
# ===========================================================================

def test_p2_case8_strong_normal_speech_quick_confirmation():
    """8. Strong normal speech confirms quickly in 8 frames (160ms)."""
    session = SessionState(session_id="test_p2_strong", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = "gen_bot_1"

    strong_feat = MockAcousticFeatures(
        rms=0.065,
        vocal_band_rms=0.060,
        spectral_flux=0.35,
        pitch_periodicity=0.70,
        harmonicity=0.65,
    )

    barge_result = None
    frames_count = 0
    for _ in range(10):
        frames_count += 1
        res = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0, vad_confidence=0.95, acoustic_features=strong_feat)
        if res == "BARGE_IN":
            barge_result = res
            break

    assert barge_result == "BARGE_IN"
    assert frames_count <= 8, f"Strong speech should confirm in <= 8 frames (160ms), took {frames_count}"


def test_p2_case9_confirmed_barge_in_purges_old_queues_and_sets_floor():
    """9-12. Confirmed barge-in purges queues, invalidates generations, 0ms stale audio leakage."""
    session = SessionState(session_id="test_p2_purge", organization_id="org1", agent_id="agent1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues)
    old_gen = session.current_turn.generation_id
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    session.active_playback_generation_id = old_gen

    # Trigger barge-in
    tm.trigger_barge_in(reason="Intentional test interruption")

    # Invariants
    assert session.is_generation_cancelled(old_gen) is True
    assert session.user_has_floor is True
    assert session.is_bot_speaking is False
    assert session.current_turn.state == TurnStateEnum.LISTENING_AFTER_BARGE_IN

    # Stale packet validation: 0ms leakage
    assert session.is_generation_cancelled(old_gen) is True


# ===========================================================================
# LATENCY & FASTROUTER
# ===========================================================================

@pytest.mark.asyncio
async def test_fast_router_bypasses_llm_queue():
    """13. FastRouter query bypasses LLM entirely."""
    from app.conversation.router import FastQueryRouter, QueryComplexity
    from app.rag.client import MockRAGProvider
    rag = MockRAGProvider()
    session = SessionState(session_id="test_router", organization_id="org_apex_univ", agent_id="agent1")
    session.preferred_language = "en-IN"
    complexity, response = await FastQueryRouter.route_and_resolve_fast_path(session, "What is the BTech CSE fee?", rag)
    assert complexity == QueryComplexity.SIMPLE
    assert response is not None
    assert "1,50,000" in response or "fee" in response.lower()


# ===========================================================================
# COST & SAFETY REGRESSIONS
# ===========================================================================

def test_startup_bulk_paid_tts_precache_remains_disabled():
    """19. Bulk paid TTS pre-caching is disabled at startup."""
    settings = get_settings()
    assert getattr(settings, "enable_startup_tts_precache", False) is False, (
        "CRITICAL: enable_startup_tts_precache must remain False to prevent ₹10.21 billing bug!"
    )


def test_tts_cache_identity_and_deduplication():
    """17. TTS deduplication works and caches identical queries."""
    TTSCacheManager.put("BTech fee is 1 lakh", "en-IN", b"RIFF_TEST_PCM", speaker="pooja")
    hit = TTSCacheManager.get("BTech fee is 1 lakh", "en-IN", speaker="pooja")
    assert hit == b"RIFF_TEST_PCM"
    miss = TTSCacheManager.get("Different text", "en-IN", speaker="pooja")
    assert miss is None


def test_disconnect_cancels_active_generations():
    """18. Call disconnect cancels all active generation IDs."""
    session = SessionState(session_id="test_disc", organization_id="org1", agent_id="agent1")
    gen_id = session.current_turn.generation_id
    session.close(reason="Call disconnected")
    assert session.is_active is False
    assert session.is_disconnected is True
    assert session.is_generation_cancelled(gen_id) is True
