"""Acoustic feature extraction and multi-dimensional voice discrimination."""
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np


@dataclass
class AcousticFeatures:
    """Multi-feature acoustic properties of an audio chunk."""
    rms: float
    snr_db: float
    zcr: float
    speech_band_ratio: float
    pitch_periodicity: float
    spectral_centroid: float
    echo_correlation: float
    is_transient: bool
    is_breath_or_mouth: bool
    is_acoustic_echo: bool
    is_valid_speech: bool


class AcousticFeatureExtractor:
    """Analyzes audio signals using energy, spectral distribution, pitch periodicity, and echo correlation."""

    @staticmethod
    def compute_rms(audio_float: np.ndarray) -> float:
        """Calculate Root Mean Square (RMS) energy."""
        if len(audio_float) == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio_float))))

    @staticmethod
    def compute_zcr(audio_float: np.ndarray) -> float:
        """Calculate Zero Crossing Rate (ZCR)."""
        if len(audio_float) < 2:
            return 0.0
        zero_crossings = np.sum(np.abs(np.diff(np.sign(audio_float)))) / 2.0
        return float(zero_crossings / len(audio_float))

    @staticmethod
    def compute_speech_band_and_centroid(
        audio_float: np.ndarray, sample_rate: int = 16000
    ) -> Tuple[float, float]:
        """
        Calculate telephony speech-band energy ratio (300Hz - 3400Hz) and spectral centroid.
        Returns: (speech_band_ratio, spectral_centroid)
        """
        if len(audio_float) < 32:
            return 0.0, 0.0

        n = len(audio_float)
        windowed = audio_float * np.hanning(n)
        fft_vals = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)

        total_energy = np.sum(fft_vals**2) + 1e-10
        speech_band_mask = (freqs >= 300) & (freqs <= 3400)
        speech_band_energy = np.sum(fft_vals[speech_band_mask]**2)
        speech_band_ratio = float(speech_band_energy / total_energy)

        centroid = float(np.sum(freqs * fft_vals) / (np.sum(fft_vals) + 1e-10))
        return speech_band_ratio, centroid

    @staticmethod
    def compute_pitch_periodicity(
        audio_float: np.ndarray, sample_rate: int = 16000
    ) -> float:
        """
        Estimate pitch harmonicity peak in human vocal pitch range (70 Hz - 400 Hz).
        Speech exhibits strong harmonic autocorrelation peaks (> 0.40).
        Breathing, friction, clicks, and background noise have low autocorrelation (< 0.25).
        """
        n = len(audio_float)
        # Require at least 256 samples (16ms at 16kHz) for pitch autocorrelation
        if n < 256:
            return 0.0

        centered = audio_float - np.mean(audio_float)
        norm_factor = np.sum(centered**2) + 1e-10
        autocorr = np.correlate(centered, centered, mode="full")
        autocorr = autocorr[n - 1 :] / norm_factor

        min_lag = int(sample_rate / 400)  # ~40 samples (400 Hz)
        max_lag = int(sample_rate / 70)   # ~228 samples (70 Hz)

        if max_lag < len(autocorr):
            peak = float(np.max(autocorr[min_lag:max_lag]))
            return max(0.0, min(peak, 1.0))
        return 0.0

    @staticmethod
    def compute_echo_correlation(
        inbound_float: np.ndarray, outbound_ref: Optional[np.ndarray]
    ) -> float:
        """
        Calculate normalized cross-correlation between inbound mic audio and recent outbound playback audio.
        Returns peak correlation in [0.0, 1.0].
        Acoustic speaker echo exhibits high correlation (> 0.60). Real user speech has very low correlation (< 0.15).
        """
        if outbound_ref is None or len(outbound_ref) < 320 or len(inbound_float) < 160:
            return 0.0

        try:
            in_norm = inbound_float - np.mean(inbound_float)
            in_std = np.std(inbound_float)
            if in_std < 1e-4:
                return 0.0
            in_norm = in_norm / in_std

            # Slice the most recent relevant window of outbound reference (e.g. up to last 16000 samples / 1s)
            ref_window = outbound_ref[-min(len(outbound_ref), 16000):]
            ref_norm = ref_window - np.mean(ref_window)
            ref_std = np.std(ref_window)
            if ref_std < 1e-4:
                return 0.0
            ref_norm = ref_norm / ref_std

            xcorr = np.correlate(ref_norm, in_norm, mode="full")
            peak_corr = float(np.max(np.abs(xcorr))) / min(len(in_norm), len(ref_norm))
            return max(0.0, min(peak_corr, 1.0))
        except Exception:
            return 0.0

    @classmethod
    def analyze_frame(
        cls,
        audio_float: np.ndarray,
        noise_floor: float = 0.002,
        outbound_ref: Optional[np.ndarray] = None,
        sample_rate: int = 16000
    ) -> AcousticFeatures:
        """Perform comprehensive acoustic feature analysis on an audio frame."""
        rms = cls.compute_rms(audio_float)
        snr_db = 20.0 * np.log10(max(rms, 1e-6) / max(noise_floor, 1e-6))
        zcr = cls.compute_zcr(audio_float)
        speech_band_ratio, centroid = cls.compute_speech_band_and_centroid(audio_float, sample_rate)
        pitch_periodicity = cls.compute_pitch_periodicity(audio_float, sample_rate)
        echo_corr = cls.compute_echo_correlation(audio_float, outbound_ref)

        # Classification heuristics based on empirical acoustic boundaries:
        # 1. Acoustic Echo: High cross-correlation with outbound AI audio (> 0.60)
        is_acoustic_echo = bool(echo_corr >= 0.60)

        # 2. Breathing / Mouth noise / Air puff: High ZCR (> 0.38), high centroid (> 3200Hz), low pitch (< 0.20)
        is_breath_or_mouth = bool(
            (zcr >= 0.38 and pitch_periodicity < 0.20 and centroid >= 3000) or
            (zcr >= 0.45 and pitch_periodicity < 0.25)
        )

        # 3. Transient click/pop: Very short burst with high centroid (> 3500Hz) and zero harmonic periodicity
        is_transient = bool(
            (centroid >= 3500 and pitch_periodicity < 0.15 and zcr < 0.05) or
            (rms > 0.05 and pitch_periodicity < 0.10 and centroid >= 3800)
        )

        # 4. Valid Speech: Requires harmonic structure, telephony speech-band energy, and SNR above noise floor
        is_valid_speech = bool(
            (not is_acoustic_echo) and
            (not is_breath_or_mouth) and
            (not is_transient) and
            (
                (pitch_periodicity >= 0.25 and speech_band_ratio >= 0.15 and snr_db >= 3.0) or
                (speech_band_ratio >= 0.40 and snr_db >= 6.0 and pitch_periodicity >= 0.20) or
                (rms >= 0.035 and pitch_periodicity >= 0.25 and speech_band_ratio >= 0.15)
            )
        )

        return AcousticFeatures(
            rms=rms,
            snr_db=snr_db,
            zcr=zcr,
            speech_band_ratio=speech_band_ratio,
            pitch_periodicity=pitch_periodicity,
            spectral_centroid=centroid,
            echo_correlation=echo_corr,
            is_transient=is_transient,
            is_breath_or_mouth=is_breath_or_mouth,
            is_acoustic_echo=is_acoustic_echo,
            is_valid_speech=is_valid_speech
        )
