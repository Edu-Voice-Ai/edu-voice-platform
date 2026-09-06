"""Comprehensive test suite for multi-feature acoustic voice discrimination and noise rejection."""
import pytest
import numpy as np
import scipy.signal as signal
from app.audio.frames import AudioFrame
from app.audio.features import AcousticFeatureExtractor
from app.vad.silero import SileroVADProvider
from app.pipeline.turn_manager import TurnManager
from app.session.state import SessionState, TurnStateEnum
from app.pipeline.queues import PipelineQueueBundle


def _make_speech_signal(duration_sec: float = 0.30, sample_rate: int = 16000, amplitude: float = 0.25) -> np.ndarray:
    """Generate harmonic voice waveform (F0=130Hz + formants)."""
    n = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    sig = (
        0.40 * np.sin(2 * np.pi * 130 * t) +
        0.30 * np.sin(2 * np.pi * 500 * t) +
        0.20 * np.sin(2 * np.pi * 1500 * t) +
        0.10 * np.sin(2 * np.pi * 2500 * t)
    ) * amplitude
    return sig


def _make_noise_signal(duration_sec: float = 0.30, sample_rate: int = 16000, amplitude: float = 0.003) -> np.ndarray:
    """Generate stationary background noise + hum."""
    n = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    np.random.seed(42)
    return np.random.normal(0, amplitude, n) + (amplitude * 0.5) * np.sin(2 * np.pi * 50 * t)


def _make_click_pop(duration_sec: float = 0.30, sample_rate: int = 16000) -> np.ndarray:
    """Generate a sharp 5ms transient impulse click/pop followed by silence."""
    n = int(sample_rate * duration_sec)
    sig = np.zeros(n)
    impulse_len = int(sample_rate * 0.005)
    sig[:impulse_len] = np.random.normal(0, 0.20, impulse_len) * np.exp(-np.linspace(0, 5, impulse_len))
    return sig


def _make_breath_mouth_noise(duration_sec: float = 0.30, sample_rate: int = 16000) -> np.ndarray:
    """Generate high-frequency breathing / air turbulence / mouth friction noise (2-6kHz)."""
    n = int(sample_rate * duration_sec)
    b, a = signal.butter(4, [2000 / (sample_rate / 2), 6000 / (sample_rate / 2)], btype='band')
    np.random.seed(42)
    return signal.lfilter(b, a, np.random.normal(0, 0.05, n)) * 0.35


# ---------------------------------------------------------------------------
# Test 1: Real nearby human speech
# ---------------------------------------------------------------------------
def test_real_nearby_speech():
    sig = _make_speech_signal(duration_sec=0.20, amplitude=0.25)
    feats = AcousticFeatureExtractor.analyze_frame(sig, noise_floor=0.002)
    assert feats.is_valid_speech is True
    assert feats.pitch_periodicity > 0.40
    assert feats.is_transient is False
    assert feats.is_breath_or_mouth is False


# ---------------------------------------------------------------------------
# Test 2: Real distant / low-level human speech
# ---------------------------------------------------------------------------
def test_real_distant_speech():
    sig = _make_speech_signal(duration_sec=0.20, amplitude=0.03)  # Lower energy but harmonic
    feats = AcousticFeatureExtractor.analyze_frame(sig, noise_floor=0.002)
    assert feats.is_valid_speech is True
    assert feats.pitch_periodicity > 0.40
    assert feats.snr_db > 10.0


# ---------------------------------------------------------------------------
# Test 3: Low-level background noise
# ---------------------------------------------------------------------------
def test_low_level_background_noise():
    sig = _make_noise_signal(duration_sec=0.20, amplitude=0.0025)
    feats = AcousticFeatureExtractor.analyze_frame(sig, noise_floor=0.002)
    assert feats.is_valid_speech is False
    assert feats.snr_db < 6.0


# ---------------------------------------------------------------------------
# Test 4: Short transient click / pop
# ---------------------------------------------------------------------------
def test_short_click_pop():
    sig = _make_click_pop(duration_sec=0.20)
    feats = AcousticFeatureExtractor.analyze_frame(sig, noise_floor=0.002)
    assert feats.is_valid_speech is False
    assert feats.is_transient is True
    assert feats.pitch_periodicity < 0.20


# ---------------------------------------------------------------------------
# Test 5: Breathing / mouth noise
# ---------------------------------------------------------------------------
def test_breathing_mouth_noise():
    sig = _make_breath_mouth_noise(duration_sec=0.20)
    feats = AcousticFeatureExtractor.analyze_frame(sig, noise_floor=0.002)
    assert feats.is_valid_speech is False
    assert feats.is_breath_or_mouth is True
    assert feats.pitch_periodicity < 0.25


# ---------------------------------------------------------------------------
# Test 6: AI Acoustic Echo Leakage
# ---------------------------------------------------------------------------
def test_ai_acoustic_echo_rejection():
    outbound = _make_speech_signal(duration_sec=0.50, amplitude=0.30)
    # Echo is delayed and attenuated version of outbound AI
    echo = np.roll(outbound, 320) * 0.25
    
    feats = AcousticFeatureExtractor.analyze_frame(echo, noise_floor=0.002, outbound_ref=outbound)
    assert feats.is_acoustic_echo is True
    assert feats.echo_correlation > 0.60
    assert feats.is_valid_speech is False  # Echo is blocked from being treated as user speech


# ---------------------------------------------------------------------------
# Test 7: Genuine short barge-in during AI playback
# ---------------------------------------------------------------------------
def test_genuine_short_barge_in():
    outbound = _make_speech_signal(duration_sec=0.50, amplitude=0.30)
    # User cuts in with their own independent speech (F0=210Hz)
    n = len(outbound)
    t = np.linspace(0, 0.50, n, endpoint=False)
    user_speech = 0.25 * np.sin(2 * np.pi * 210 * t) + 0.15 * np.sin(2 * np.pi * 650 * t)
    
    feats = AcousticFeatureExtractor.analyze_frame(user_speech, noise_floor=0.002, outbound_ref=outbound)
    assert feats.is_acoustic_echo is False
    assert feats.echo_correlation < 0.20
    assert feats.is_valid_speech is True


# ---------------------------------------------------------------------------
# Test 8: Speech immediately after noise burst
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_speech_immediately_after_noise():
    vad = SileroVADProvider()
    
    # 1. Feed click noise (transient)
    noise_frame = AudioFrame.from_numpy_float32(_make_click_pop(0.04))
    res_noise = await vad.is_speech(noise_frame)
    assert res_noise.is_speech is False
    
    # 2. Feed genuine speech frames immediately after
    speech_sig = _make_speech_signal(0.12)
    chunker = [speech_sig[i:i+320] for i in range(0, len(speech_sig), 320) if len(speech_sig[i:i+320]) == 320]
    results = []
    for chunk in chunker:
        f = AudioFrame.from_numpy_float32(chunk)
        res = await vad.is_speech(f)
        results.append(res.is_speech)
    
    assert any(results) is True



# ---------------------------------------------------------------------------
# Test 9: Turn manager ignores sub-threshold transients without starting turn
# ---------------------------------------------------------------------------
def test_turn_manager_transient_rejection():
    session = SessionState(session_id="test_tm_transient", organization_id="org_test", agent_id="agent_1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_speech_duration_ms=100)
    
    # 1 frame of transient noise (20ms) followed by silence
    res1 = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0)
    assert res1 is None  # Does not trigger SPEECH_STARTED for a single 20ms click!
    assert session.current_turn.state != TurnStateEnum.LISTENING or not tm._is_in_speech
    
    res2 = tm.handle_speech_frame(is_speech=False, frame_duration_ms=20.0)
    assert res2 is None
    assert tm._speech_accumulated_ms == 0.0


# ---------------------------------------------------------------------------
# Test 10: Turn manager commits to speech on sustained multi-frame human speech
# ---------------------------------------------------------------------------
def test_turn_manager_sustained_speech_onset():
    session = SessionState(session_id="test_tm_sustained", organization_id="org_test", agent_id="agent_1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_speech_duration_ms=60)
    
    # 3 frames of speech (60ms)
    tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0)
    tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0)
    res = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0)
    
    assert res == "SPEECH_STARTED"
    assert tm._is_in_speech is True
    assert session.current_turn.state == TurnStateEnum.LISTENING


def test_turn_manager_echo_does_not_barge_in():
    session = SessionState(session_id="test_tm_echo", organization_id="org_test", agent_id="agent_1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=80)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    class EchoFeat:
        is_acoustic_echo = True
        echo_correlation = 0.9
        is_valid_speech = False
        snr_db = 12.0
        is_transient = False
        is_breath_or_mouth = False
        rms = 0.01
    for _ in range(8):
        res = tm.handle_speech_frame(
            is_speech=True, frame_duration_ms=20.0, vad_confidence=0.95, acoustic_features=EchoFeat()
        )
        assert res is None
    assert session.is_bot_speaking is True


def test_turn_manager_barge_in_hysteresis_one_miss():
    """
    Leaky bucket: one non-qualifying frame decays the bucket by 1 (not hard-reset).
    With min_barge_in_duration_ms=80 (threshold=4 frames):
      2 qualifying -> bucket=2; 1 miss -> bucket=1; 3 qualifying -> bucket=4 -> BARGE_IN.
    """
    session = SessionState(session_id="test_tm_hysteresis", organization_id="org_test", agent_id="agent_1")
    queues = PipelineQueueBundle()
    tm = TurnManager(session=session, queues=queues, min_barge_in_duration_ms=80)
    session.current_turn.state = TurnStateEnum.SPEAKING
    session.is_bot_speaking = True
    tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0)
    tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0)
    assert tm.handle_speech_frame(is_speech=False, frame_duration_ms=20.0) is None  # bucket decays: 2->1
    tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0)  # bucket=2
    tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0)  # bucket=3
    res = tm.handle_speech_frame(is_speech=True, frame_duration_ms=20.0)  # bucket=4 -> fires
    assert res == "BARGE_IN"
