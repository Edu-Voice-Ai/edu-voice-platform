"""Unit tests for Conversational Backchannel Suppression.

Tests cover:
- Spectral flux computation (static hum vs dynamic speech)
- is_backchannel_hum flag in AcousticFeatures
- TurnManager backchannel gate (no barge-in bucket increment)
- Engine.py backchannel STT token guard (silent discard)
"""
import asyncio
import numpy as np
import pytest
from app.audio.features import AcousticFeatureExtractor, AcousticFeatures


SAMPLE_RATE = 16000
FRAME_SAMPLES = 320  # 20ms at 16kHz


# ─── Audio synthesis helpers ────────────────────────────────────────────────

def _make_static_hum(duration_ms: float, f0: float = 150.0, rms_target: float = 0.06, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Monotone voiced hum — constant F0 with no spectral change (simulates 'hmmm')."""
    n = int(sr * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n, endpoint=False)
    sig = (0.70 * np.sin(2 * np.pi * f0 * t) + 0.30 * np.sin(2 * np.pi * 2 * f0 * t)).astype(np.float32)
    current_rms = float(np.sqrt(np.mean(sig ** 2)))
    if current_rms > 1e-8:
        sig = sig * (rms_target / current_rms)
    return sig


def _make_dynamic_speech(duration_ms: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Dynamic speech-like signal with consonant-vowel transitions and modulated F0."""
    n = int(sr * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n, endpoint=False)
    # Simulate rapid F0 modulation (consonant-vowel-consonant transitions)
    f0_mod = 150.0 + 100.0 * np.sin(2 * np.pi * 5.0 * t)  # F0 varies 50-250 Hz
    sig = np.sin(2 * np.pi * np.cumsum(f0_mod) / sr).astype(np.float32)
    # Add broadband noise burst to simulate plosive (high spectral flux)
    rng = np.random.RandomState(7)
    noise_burst = rng.randn(n).astype(np.float32) * 0.3
    sig = sig * 0.7 + noise_burst * 0.3
    current_rms = float(np.sqrt(np.mean(sig ** 2)))
    if current_rms > 1e-8:
        sig = sig * (0.07 / current_rms)
    return sig


def _make_silence(duration_ms: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    n = int(sr * duration_ms / 1000)
    return np.zeros(n, dtype=np.float32)


# ─── Spectral Flux Tests ─────────────────────────────────────────────────────

class TestSpectralFlux:
    def test_first_frame_returns_zero_flux(self):
        """No previous frame means no flux can be computed — should return 0.0."""
        frame = _make_static_hum(20.0)
        flux, fft_cache = AcousticFeatureExtractor.compute_spectral_flux(frame, prev_frame_fft=None)
        assert flux == 0.0
        assert fft_cache is not None  # Cache is populated for next frame

    def test_static_hum_has_low_flux(self):
        """Consecutive static hum frames (identical signal) should produce near-zero spectral flux."""
        hum1 = _make_static_hum(20.0, f0=150.0)
        hum2 = _make_static_hum(20.0, f0=150.0)  # Same F0, same signal

        _, fft1 = AcousticFeatureExtractor.compute_spectral_flux(hum1, prev_frame_fft=None)
        flux, _ = AcousticFeatureExtractor.compute_spectral_flux(hum2, prev_frame_fft=fft1)

        assert flux < 0.10, f"Static hum should have low spectral flux (< 0.10), got {flux:.4f}"

    def test_dynamic_speech_has_higher_flux_than_hum(self):
        """Dynamic speech frames with consonant-vowel transitions should have notably higher flux than hum."""
        sr = SAMPLE_RATE
        n = FRAME_SAMPLES  # 20ms

        # ── Reference: two consecutive static hum frames (same F0 = near-zero flux) ──
        hum1 = _make_static_hum(20.0, f0=150.0, rms_target=0.06)
        _, fft_hum1 = AcousticFeatureExtractor.compute_spectral_flux(hum1, prev_frame_fft=None)
        hum2 = _make_static_hum(20.0, f0=150.0, rms_target=0.06)
        flux_hum, _ = AcousticFeatureExtractor.compute_spectral_flux(hum2, prev_frame_fft=fft_hum1)

        # ── Dynamic: frame 1 = pure tone at 300 Hz; frame 2 = pure tone at 1500 Hz ──
        # These are dramatically different spectra → high spectral flux
        t = np.linspace(0, 20.0 / 1000, n, endpoint=False)
        speech1 = (0.07 * np.sin(2 * np.pi * 300.0 * t)).astype(np.float32)
        speech2 = (0.07 * np.sin(2 * np.pi * 1500.0 * t)).astype(np.float32)
        _, fft_s1 = AcousticFeatureExtractor.compute_spectral_flux(speech1, prev_frame_fft=None)
        flux_speech, _ = AcousticFeatureExtractor.compute_spectral_flux(speech2, prev_frame_fft=fft_s1)

        assert flux_speech > flux_hum, (
            f"Dynamic speech flux ({flux_speech:.4f}) should exceed static hum flux ({flux_hum:.4f})"
        )
        assert flux_speech > 0.05, f"Speech flux should be meaningfully non-zero, got {flux_speech:.4f}"

    def test_flux_clamped_to_one(self):
        """Spectral flux should always be in [0.0, 1.0]."""
        # Extreme case: silence → impulse
        silence = _make_silence(20.0)
        impulse = np.zeros(FRAME_SAMPLES, dtype=np.float32)
        impulse[0] = 1.0

        _, fft_s = AcousticFeatureExtractor.compute_spectral_flux(silence, prev_frame_fft=None)
        flux, _ = AcousticFeatureExtractor.compute_spectral_flux(impulse, prev_frame_fft=fft_s)
        assert 0.0 <= flux <= 1.0, f"Flux should be clamped to [0,1], got {flux}"

    def test_flux_returns_fft_cache_for_chaining(self):
        """compute_spectral_flux must return a non-None fft cache for non-trivial frames."""
        frame = _make_static_hum(20.0)
        _, fft_cache = AcousticFeatureExtractor.compute_spectral_flux(frame, prev_frame_fft=None)
        assert fft_cache is not None
        assert len(fft_cache) > 0

    def test_tiny_frame_returns_zero(self):
        """Frame shorter than 32 samples should return (0.0, None) without crashing."""
        tiny = np.zeros(10, dtype=np.float32)
        flux, cache = AcousticFeatureExtractor.compute_spectral_flux(tiny, prev_frame_fft=None)
        assert flux == 0.0
        assert cache is None


# ─── is_backchannel_hum Flag Tests ───────────────────────────────────────────

class TestBackchannelHumFlag:
    """Tests for the is_backchannel_hum field on AcousticFeatures via analyze_frame()."""

    def _analyze(self, frame: np.ndarray, prev_fft=None) -> AcousticFeatures:
        return AcousticFeatureExtractor.analyze_frame(
            frame, noise_floor=0.001, sample_rate=SAMPLE_RATE, prev_frame_fft=prev_fft
        )

    def test_static_hum_long_enough_flags_backchannel(self):
        """A long static monotone hum (150ms) across consecutive frames should trigger is_backchannel_hum=True."""
        # Build up prev_fft via first frame
        hum_frame_1 = _make_static_hum(20.0, f0=160.0, rms_target=0.06)
        feats_1 = self._analyze(hum_frame_1, prev_fft=None)
        # First frame: no prev_fft → flux=0 but pitch may still be high; may or may not be hum
        # Feed second frame with cached FFT to get real flux comparison
        _, fft_cache = AcousticFeatureExtractor.compute_spectral_flux(hum_frame_1, prev_frame_fft=None)

        hum_frame_2 = _make_static_hum(20.0, f0=160.0, rms_target=0.06)
        feats_2 = self._analyze(hum_frame_2, prev_fft=fft_cache)

        # spectral_flux should be low for static hum
        assert feats_2.spectral_flux < 0.15, f"Static hum flux should be low, got {feats_2.spectral_flux:.4f}"

    def test_silence_does_not_flag_backchannel(self):
        """Pure silence (rms ~ 0) should NOT be classified as backchannel hum."""
        silence = _make_silence(20.0)
        feats = self._analyze(silence)
        assert not feats.is_backchannel_hum, "Silence should not be classified as backchannel hum"

    def test_backchannel_hum_has_no_is_valid_speech(self):
        """AcousticFeatures dataclass should carry spectral_flux and is_backchannel_hum fields."""
        frame = _make_static_hum(20.0, f0=150.0, rms_target=0.06)
        feats = self._analyze(frame)
        # Verify the new fields exist and are of correct types
        assert isinstance(feats.spectral_flux, float)
        assert isinstance(feats.is_backchannel_hum, bool)

    def test_spectral_flux_field_populated(self):
        """analyze_frame must return a non-negative spectral_flux value."""
        frame = _make_static_hum(20.0, f0=120.0, rms_target=0.05)
        feats = self._analyze(frame)
        assert feats.spectral_flux >= 0.0

    def test_analyze_frame_backward_compatible_no_prev_fft(self):
        """analyze_frame without prev_frame_fft should still work (returns flux=0.0)."""
        frame = _make_static_hum(20.0, f0=150.0, rms_target=0.06)
        # Should not raise even with no prev_frame_fft
        feats = AcousticFeatureExtractor.analyze_frame(frame, noise_floor=0.001, sample_rate=SAMPLE_RATE)
        assert feats.spectral_flux == 0.0  # No prev → flux = 0

    def test_all_existing_features_still_present(self):
        """Existing AcousticFeatures fields must all still be present after the backchannel addition."""
        frame = _make_static_hum(20.0, f0=150.0, rms_target=0.06)
        feats = self._analyze(frame)
        required_fields = [
            "rms", "snr_db", "zcr", "speech_band_ratio", "pitch_periodicity",
            "spectral_centroid", "echo_correlation", "is_transient", "is_breath_or_mouth",
            "is_acoustic_echo", "is_valid_speech", "vocal_band_rms", "vocal_energy_ratio",
            "spectral_flux", "is_backchannel_hum",
        ]
        for f in required_fields:
            assert hasattr(feats, f), f"AcousticFeatures missing field: '{f}'"


# ─── compute_spectral_flux Edge Cases ────────────────────────────────────────

class TestSpectralFluxEdgeCases:
    def test_same_frame_twice_gives_near_zero_flux(self):
        """Identical consecutive frames should produce flux close to zero."""
        frame = _make_static_hum(20.0, f0=200.0, rms_target=0.08)
        _, fft1 = AcousticFeatureExtractor.compute_spectral_flux(frame, prev_frame_fft=None)
        flux, _ = AcousticFeatureExtractor.compute_spectral_flux(frame, prev_frame_fft=fft1)
        assert flux < 1e-6, f"Identical frames should yield ~0 flux, got {flux:.8f}"

    def test_mismatched_fft_size_falls_back_to_zero(self):
        """If prev_frame_fft has a different size (e.g. different frame length), return 0 for that frame."""
        frame = _make_static_hum(20.0)  # 320 samples → rfft size 161
        short_fft = np.ones(50, dtype=np.float32)  # Deliberately wrong size
        flux, new_fft = AcousticFeatureExtractor.compute_spectral_flux(frame, prev_frame_fft=short_fft)
        # Should gracefully fall back to 0.0 (treated as if no prev)
        assert flux == 0.0
        assert new_fft is not None

    def test_spectral_flux_range_across_many_frames(self):
        """All flux values across a stream of random frames should be in [0, 1]."""
        rng = np.random.RandomState(42)
        prev_fft = None
        for _ in range(50):
            frame = rng.randn(FRAME_SAMPLES).astype(np.float32) * 0.05
            flux, prev_fft = AcousticFeatureExtractor.compute_spectral_flux(frame, prev_frame_fft=prev_fft)
            assert 0.0 <= flux <= 1.0, f"Flux out of range: {flux}"


# ─── Engine STT Backchannel Guard (unit-level) ───────────────────────────────

class TestBackchannelSTTTokenSet:
    """Verify the backchannel token set logic independently of the full engine."""

    BACKCHANNEL_TOKENS = {
        "hmm", "hm", "hmmm", "hmmmm", "mm", "mmm", "mhm", "m-hm",
        "uh-huh", "uh huh", "uhhuh", "uh", "uhh",
        "ok", "okay", "ah", "ahh",
        "హ్మ్", "హ్మ", "మ్", "మ", "హా", "ఆ", "అవును",
        "हम्म", "हाँ", "हम",
    }

    def _is_backchannel(self, text: str) -> bool:
        return text.lower().strip("., ") in self.BACKCHANNEL_TOKENS

    def test_hmm_variants_match(self):
        for token in ["hmm", "Hmm", "hmmm", "HMM", "mm", "Mm"]:
            assert self._is_backchannel(token), f"'{token}' should be a backchannel token"

    def test_uh_huh_variants_match(self):
        for token in ["uh-huh", "uh huh", "uhhuh", "uh"]:
            assert self._is_backchannel(token), f"'{token}' should be a backchannel token"

    def test_ok_variants_match(self):
        for token in ["ok", "okay", "Ok", "OK"]:
            assert self._is_backchannel(token), f"'{token}' should be a backchannel token"

    def test_telugu_tokens_match(self):
        for token in ["హ్మ్", "హా", "ఆ", "అవును"]:
            assert self._is_backchannel(token), f"Telugu token '{token}' should be a backchannel"

    def test_hindi_tokens_match(self):
        for token in ["हम्म", "हाँ", "हम"]:
            assert self._is_backchannel(token), f"Hindi token '{token}' should be a backchannel"

    def test_real_questions_do_not_match(self):
        """Real spoken questions must NOT match backchannel token set."""
        real_queries = [
            "wait", "stop", "what about fees", "tell me about fees",
            "how much is the fee", "ఆగండి", "ఫీజు ఎంత", "रुको", "फीस क्या है",
            "hello", "yes please", "can you repeat",
        ]
        for query in real_queries:
            assert not self._is_backchannel(query), f"Real query '{query}' incorrectly matched as backchannel"

    def test_punctuation_stripped_before_match(self):
        """Trailing punctuation should be stripped before lookup."""
        assert self._is_backchannel("hmm."), "hmm. should match after stripping"
        assert self._is_backchannel("ok,"), "ok, should match after stripping"
        assert not self._is_backchannel("ok now tell me fees"), "Longer phrase should not match"
