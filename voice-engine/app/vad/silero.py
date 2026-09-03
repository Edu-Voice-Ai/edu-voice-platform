"""Silero VAD ONNX Adapter with multi-feature acoustic discrimination."""
import os
import numpy as np
from typing import Optional
from app.audio.frames import AudioFrame
from app.audio.features import AcousticFeatureExtractor, AcousticFeatures
from app.vad.base import VADProvider, VADResult
from app.core.logging import get_logger

logger = get_logger("vad.silero")


class SileroVADProvider(VADProvider):
    """Silero VAD using ONNX runtime with multi-feature acoustic discrimination and adaptive noise-floor tracking."""

    def __init__(self, model_path: Optional[str] = None, threshold: float = 0.35, barge_in_threshold: float = 0.45, sample_rate: int = 16000):
        self.threshold = threshold
        self.barge_in_threshold = barge_in_threshold
        self.sample_rate = sample_rate
        self.session = None
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(64, dtype=np.float32)
        self._sr_tensor = np.array(sample_rate, dtype=np.int64)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._last_conf = 0.0
        self._noise_floor = 0.002
        self._consecutive_speech_frames = 0

        # Auto-discover ONNX model path
        search_paths = []
        if model_path:
            search_paths.append(model_path)
        search_paths.extend([
            os.path.join(os.path.dirname(__file__), "silero_vad.onnx"),
            os.path.join(os.path.dirname(__file__), "official_silero_vad.onnx"),
            os.path.expanduser("~/.cache/torch/hub/snakers4_silero-vad_master/src/silero_vad/data/silero_vad.onnx")
        ])

        resolved_path = None
        for p in search_paths:
            if os.path.exists(p):
                resolved_path = p
                break

        if resolved_path:
            try:
                import onnxruntime
                opts = onnxruntime.SessionOptions()
                opts.inter_op_num_threads = 1
                opts.intra_op_num_threads = 1
                self.session = onnxruntime.InferenceSession(resolved_path, opts, providers=["CPUExecutionProvider"])
                logger.info(f"Loaded Silero ONNX model from {resolved_path}")
            except Exception as e:
                logger.warning(f"Failed to load Silero ONNX model ({e}), falling back to multi-feature acoustic VAD")
        else:
            logger.info("Silero model file not found; using multi-feature acoustic VAD baseline")

    async def is_speech(self, frame: AudioFrame, outbound_ref: Optional[np.ndarray] = None, playback_active: bool = False) -> VADResult:
        """Evaluate if the given audio frame contains genuine speech using Silero VAD + acoustic feature discrimination."""
        audio_float = frame.to_numpy_float32()
        
        # 1. Multi-feature acoustic extraction
        acoustic = AcousticFeatureExtractor.analyze_frame(
            audio_float,
            noise_floor=self._noise_floor,
            outbound_ref=outbound_ref,
            sample_rate=self.sample_rate
        )

        # Update dynamic background noise floor only during sustained low-energy quiet periods (not spikes)
        if not acoustic.is_transient and acoustic.rms < 0.008:
            self._noise_floor = float(0.98 * self._noise_floor + 0.02 * max(acoustic.rms, 0.0005))

        if self.session is not None:
            try:
                self._buffer = np.concatenate([self._buffer, audio_float])
                while len(self._buffer) >= 512:
                    chunk = self._buffer[:512]
                    self._buffer = self._buffer[512:]
                    input_576 = np.concatenate([self._context, chunk]).reshape(1, -1)
                    self._context = chunk[-64:]
                    ort_inputs = {
                        "input": input_576,
                        "state": self._state,
                        "sr": self._sr_tensor
                    }
                    out, self._state = self.session.run(None, ort_inputs)
                    self._last_conf = float(out[0][0])

                effective_threshold = self.barge_in_threshold if playback_active else self.threshold
                raw_vad_speech = bool(self._last_conf >= effective_threshold)

                # Filter out false positives (transient clicks, mouth puffs, breathing).
                # Do not drop loud inbound as echo — that is the caller talking over TTS.
                if raw_vad_speech:
                    if acoustic.is_acoustic_echo and acoustic.rms < 0.04:
                        is_sp = False
                    elif acoustic.is_transient and self._consecutive_speech_frames == 0:
                        is_sp = False
                    elif acoustic.is_breath_or_mouth and self._last_conf < 0.70:
                        is_sp = False
                    else:
                        is_sp = True
                else:
                    # If acoustic harmonicity and SNR are strong (e.g. human voice, phonemes, vowels)
                    if acoustic.is_valid_speech and (self._last_conf >= 0.15 or (acoustic.pitch_periodicity >= 0.35 and acoustic.snr_db >= 5.0)):
                        is_sp = True
                    else:
                        is_sp = False

                if is_sp:
                    self._consecutive_speech_frames += 1
                else:
                    self._consecutive_speech_frames = 0

                effective_conf = max(self._last_conf, 0.80) if (is_sp and acoustic.is_valid_speech) else self._last_conf
                return VADResult(is_speech=is_sp, confidence=effective_conf, raw_score=self._last_conf, acoustic_features=acoustic)
            except Exception as ex:
                logger.warning(f"Silero ONNX inference error: {ex}")

        # Multi-feature Acoustic Fallback VAD (used if ONNX is unavailable)
        is_sp = acoustic.is_valid_speech
        if is_sp:
            self._consecutive_speech_frames += 1
        else:
            self._consecutive_speech_frames = 0

        confidence = float(np.clip((acoustic.pitch_periodicity * 0.5) + (min(acoustic.snr_db, 20.0) / 40.0), 0.0, 1.0))
        return VADResult(is_speech=is_sp, confidence=confidence, raw_score=acoustic.rms, acoustic_features=acoustic)

    def reset(self) -> None:
        """Reset internal recurrence state, streaming context buffer, and frame counters."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(64, dtype=np.float32)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._last_conf = 0.0
        self._consecutive_speech_frames = 0

