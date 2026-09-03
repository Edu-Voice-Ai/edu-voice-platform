"""Adaptive Speaker Voice Profiler — Online caller identity locking for near-field proximity discrimination.

This module estimates the primary caller's vocal fingerprint from their first verified speech turn and uses
it to score incoming audio frames during bot playback (barge-in gate) or normal listening.

Key insight:
  - Background voices (1m away) differ from the primary caller in:
    1. Crest factor: near-field mic speech has sharp peaks (crest > 2.8); diffuse room voice is flatter (< 2.2).
    2. Pitch (F0): different speakers have different fundamental frequencies (±35% gap is reliable for adult vs adult).
    3. RMS relative to caller baseline: 1m diffuse voice naturally has lower RMS at the mic.
  - Once enrolled, frames scoring < 0.45 during bot playback are discarded as background noise.

Enrollment is triggered automatically after the first verified clean speech turn (language selection or first query).
"""
from __future__ import annotations

import math
import numpy as np
from typing import Optional, List
from dataclasses import dataclass, field


@dataclass
class CallerVoiceProfile:
    """Immutable snapshot of caller vocal characteristics captured from Turn 1 speech."""
    pitch_f0_hz: float          # Estimated fundamental frequency in Hz (70–400 Hz range)
    spectral_centroid_hz: float  # Center of mass of the vocal spectrum in Hz
    near_mic_crest_factor: float # Peak-to-RMS ratio — near-field mic speech > 3.0; diffuse < 2.2
    baseline_rms: float          # Average active speech RMS of the primary caller
    pitch_lower_hz: float        # pitch_f0 * 0.65 (±35% tolerance band)
    pitch_upper_hz: float        # pitch_f0 * 1.35


class AdaptiveSpeakerVoiceProfiler:
    """
    Online adaptive speaker voice profiler.

    Session lifecycle:
      1. UNENROLLED (is_enrolled=False): All speech frames pass through baseline calibrated VAD.
      2. ENROLLMENT: After first verified turn with >= MIN_ENROLLMENT_SAMPLES clean frames,
         extract pitch, crest factor, spectral centroid, and RMS baseline.
      3. ENROLLED (is_enrolled=True): For subsequent turns, `calculate_speaker_similarity()`
         scores each barge-in frame against the caller profile.

    Designed for:
      - 8kHz/16kHz telephony PCM (mulaw decoded to float32 by AudioCodec upstream).
      - Robustness to natural pitch variation ±35% (rising/falling tone in conversation).
      - Discrimination of diffuse 1m room voice (TV, background chatter) from near-mic primary caller.
    """

    # Minimum seconds of clean speech to accept enrollment (default 0.5s of valid speech frames)
    MIN_ENROLLMENT_MS: float = 500.0
    # Crest factor below which near-field claim is rejected (diffuse room voice is flatter)
    NEAR_FIELD_CREST_THRESHOLD: float = 2.5
    # Similarity threshold below which a frame is classified as background during barge-in
    BACKGROUND_REJECT_THRESHOLD: float = 0.45

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.is_enrolled: bool = False
        self._profile: Optional[CallerVoiceProfile] = None

        # Enrollment accumulator (raw float32 PCM chunks)
        self._enroll_chunks: List[np.ndarray] = []
        self._enroll_speech_ms: float = 0.0

    @property
    def profile(self) -> Optional[CallerVoiceProfile]:
        return self._profile

    # ─────────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────────

    def add_enrollment_chunk(self, pcm_float: np.ndarray, chunk_ms: float = 20.0):
        """Accumulate clean speech frames from Turn 1 for deferred enrollment.
        Call this from the SPEECH_STARTED ... SPEECH_ENDED window of Turn 1.
        Does nothing once already enrolled.
        """
        if self.is_enrolled:
            return
        if pcm_float is None or len(pcm_float) < 4:
            return
        self._enroll_chunks.append(pcm_float.astype(np.float32))
        self._enroll_speech_ms += chunk_ms

    def enroll_from_turn_audio(self, pcm_float_chunks: List[np.ndarray]) -> Optional[CallerVoiceProfile]:
        """
        Build caller voice profile from a list of 20ms float32 PCM chunks.
        Returns the enrolled profile, or None if the audio is insufficient.
        Called once at the end of Turn 1 (language selection or first query).
        """
        if self.is_enrolled:
            return self._profile

        if pcm_float_chunks:
            for chunk in pcm_float_chunks:
                self.add_enrollment_chunk(chunk)

        if len(self._enroll_chunks) == 0:
            return None

        combined = np.concatenate(self._enroll_chunks).astype(np.float32)
        if len(combined) < 320:
            return None

        profile = self._extract_profile(combined)
        if profile is None:
            return None

        self._profile = profile
        self.is_enrolled = True
        # Free enrollment buffer memory
        self._enroll_chunks.clear()
        return profile

    def try_enroll_from_accumulated(self) -> Optional[CallerVoiceProfile]:
        """Attempt enrollment from already-accumulated chunks (called at SPEECH_ENDED of Turn 1)."""
        return self.enroll_from_turn_audio([])

    def calculate_speaker_similarity(
        self,
        frame_audio: np.ndarray,
        frame_rms: Optional[float] = None,
        frame_spectral_centroid: Optional[float] = None,
        vad_confidence: float = 0.0
    ) -> float:
        """
        Score how similar an incoming audio frame is to the enrolled caller voice profile.
        Returns a float in [0.0, 1.0].

        Scoring components:
          - Pitch match (40% weight):  ± 35% tolerance from caller F0.
          - Near-field proximity match (40% weight): crest factor and RMS vs caller baseline.
          - Spectral centroid match (20% weight): centroid within 50% of caller centroid.

        Score interpretation:
          >= 0.60 → Primary caller confirmed
          0.45–0.60 → Uncertain (accept during barge-in if VAD conf >= 0.85)
          < 0.45   → Likely background voice (diffuse/1m away) → DISCARD during barge-in
        """
        if not self.is_enrolled or self._profile is None:
            # Not yet enrolled — return neutral 1.0 so the frame passes through
            return 1.0

        if frame_audio is None or len(frame_audio) < 64:
            return 0.5

        profile = self._profile
        # Confident speech / high energy safety: near-field spoken utterances should never be rejected
        if vad_confidence >= 0.70 or (frame_rms is not None and frame_rms >= 0.025):
            return 1.0

        audio = frame_audio.astype(np.float32)

        # ── Component 1: Pitch match ──────────────────────────────────────────────
        frame_f0 = self._estimate_pitch(audio)
        pitch_score = 0.0
        if frame_f0 > 0:
            if profile.pitch_lower_hz <= frame_f0 <= profile.pitch_upper_hz:
                # Perfect match within tolerance band
                relative_dist = abs(frame_f0 - profile.pitch_f0_hz) / max(profile.pitch_f0_hz, 1.0)
                pitch_score = max(0.0, 1.0 - relative_dist * 2.0)
            elif frame_f0 > 0:
                # Outside tolerance: score drops rapidly
                dist_to_band = min(
                    abs(frame_f0 - profile.pitch_lower_hz),
                    abs(frame_f0 - profile.pitch_upper_hz)
                )
                pitch_score = max(0.0, 0.3 - dist_to_band / profile.pitch_f0_hz)
        else:
            # Unvoiced / pitch undetectable — give neutral pitch score
            pitch_score = 0.5

        # ── Component 2: Near-field proximity (crest factor + RMS) ───────────────
        rms = frame_rms if frame_rms is not None else self._compute_rms(audio)
        crest_factor = self._compute_crest_factor(audio, rms)

        proximity_score = 0.0
        # Crest factor check: near-field voice > 2.8, diffuse room voice < 2.2
        crest_ok = crest_factor >= self.NEAR_FIELD_CREST_THRESHOLD
        # RMS relative to caller baseline: must be >= 35% of enrolled baseline
        rms_ok = (profile.baseline_rms < 1e-6) or (rms >= 0.35 * profile.baseline_rms)

        if crest_ok and rms_ok:
            # Strongly near-field
            proximity_score = min(1.0, crest_factor / 4.5)
        elif crest_ok:
            proximity_score = 0.55  # Good crest but quiet (could be whispering)
        elif rms_ok:
            # Adequate RMS but flat crest (1m speaker)
            proximity_score = max(0.0, 0.35 + 0.05 * (crest_factor - 1.0))
        else:
            proximity_score = max(0.0, 0.20 + (crest_factor / 10.0))

        # ── Component 3: Spectral centroid match ─────────────────────────────────
        if frame_spectral_centroid is not None and profile.spectral_centroid_hz > 0:
            relative_centroid_diff = abs(frame_spectral_centroid - profile.spectral_centroid_hz) / max(profile.spectral_centroid_hz, 1.0)
            centroid_score = max(0.0, 1.0 - relative_centroid_diff * 2.0)
        else:
            centroid_score = 0.5  # Unknown: neutral

        # ── Weighted composite score ──────────────────────────────────────────────
        speaker_sim = (
            0.40 * pitch_score +
            0.40 * proximity_score +
            0.20 * centroid_score
        )
        return float(min(1.0, max(0.0, speaker_sim)))

    # ─────────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────────

    def _extract_profile(self, audio: np.ndarray) -> Optional[CallerVoiceProfile]:
        """Extract vocal fingerprint from a clean speech utterance (typically 0.5–2.0s long)."""
        if len(audio) < 320:
            return None

        rms = self._compute_rms(audio)
        if rms < 0.005:
            return None  # Too quiet to enroll reliably

        f0 = self._estimate_pitch(audio)
        if f0 <= 0:
            # Try to extract at least a reasonable pitch estimate from a shorter segment
            # Some speakers (low bass) may not register on short chunks
            f0 = 140.0  # Neutral default (~adult male F0)

        crest_factor = self._compute_crest_factor(audio, rms)
        centroid = self._compute_spectral_centroid(audio)

        # Enrollment tolerance band: ±35%
        return CallerVoiceProfile(
            pitch_f0_hz=f0,
            spectral_centroid_hz=centroid,
            near_mic_crest_factor=crest_factor,
            baseline_rms=rms,
            pitch_lower_hz=f0 * 0.65,
            pitch_upper_hz=f0 * 1.35,
        )

    @staticmethod
    def _compute_rms(audio: np.ndarray) -> float:
        if len(audio) == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio))))

    @staticmethod
    def _compute_crest_factor(audio: np.ndarray, rms: Optional[float] = None) -> float:
        """Peak-to-RMS ratio. Near-field mic speech: 3.0–6.0. Diffuse room voice: 1.5–2.5."""
        if len(audio) == 0:
            return 1.0
        peak = float(np.max(np.abs(audio)))
        rms_val = rms if rms is not None else AdaptiveSpeakerVoiceProfiler._compute_rms(audio)
        if rms_val < 1e-8:
            return 1.0
        return min(float(peak / rms_val), 20.0)

    def _estimate_pitch(self, audio: np.ndarray) -> float:
        """
        Estimate fundamental frequency F0 using normalized autocorrelation.
        Returns F0 in Hz (70–400 Hz), or 0.0 if pitch is undetectable (noise/unvoiced).
        """
        n = len(audio)
        if n < 256:
            return 0.0

        # Operate on a minimum of 512 samples for reliable pitch (32ms at 16kHz)
        seg = audio[:min(n, 4096)]
        centered = seg - np.mean(seg)
        norm_factor = np.sum(centered ** 2)
        if norm_factor < 1e-10:
            return 0.0

        # Normalized autocorrelation
        autocorr = np.correlate(centered, centered, mode="full")
        autocorr = autocorr[len(seg) - 1:] / norm_factor

        min_lag = max(1, int(self.sample_rate / 400))   # ~40 samples (400 Hz)
        max_lag = min(len(autocorr) - 1, int(self.sample_rate / 70))  # ~228 samples (70 Hz)

        if max_lag <= min_lag:
            return 0.0

        window = autocorr[min_lag:max_lag + 1]
        peak_idx = int(np.argmax(window))
        peak_val = float(window[peak_idx])

        # Threshold: autocorrelation >= 0.30 suggests harmonic pitch
        if peak_val < 0.30:
            return 0.0

        lag = peak_idx + min_lag
        f0 = self.sample_rate / lag
        return round(float(f0), 2)

    def _compute_spectral_centroid(self, audio: np.ndarray) -> float:
        """Compute spectral centroid (center of mass) of the vocal spectrum in Hz."""
        n = len(audio)
        if n < 64:
            return 0.0
        windowed = audio * np.hanning(n)
        fft_vals = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(n, 1.0 / self.sample_rate)
        total = np.sum(fft_vals) + 1e-10
        return float(np.sum(freqs * fft_vals) / total)

    def __repr__(self) -> str:
        if self.is_enrolled and self._profile:
            p = self._profile
            return (
                f"AdaptiveSpeakerVoiceProfiler(enrolled=True, "
                f"f0={p.pitch_f0_hz:.1f}Hz, "
                f"centroid={p.spectral_centroid_hz:.1f}Hz, "
                f"crest={p.near_mic_crest_factor:.2f}, "
                f"rms={p.baseline_rms:.4f})"
            )
        return f"AdaptiveSpeakerVoiceProfiler(enrolled=False, speech_ms={self._enroll_speech_ms:.0f})"
