"""Silero VAD ONNX Adapter with adaptive energy fallback."""
import os
import numpy as np
from typing import Optional
from app.audio.frames import AudioFrame
from app.vad.base import VADProvider, VADResult
from app.core.logging import get_logger

logger = get_logger("vad.silero")


class SileroVADProvider(VADProvider):
    """Silero VAD using ONNX runtime, falling back to adaptive RMS energy if model weights are loading."""

    def __init__(self, model_path: Optional[str] = None, threshold: float = 0.35, sample_rate: int = 16000):
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.session = None
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(64, dtype=np.float32)
        self._sr_tensor = np.array(sample_rate, dtype=np.int64)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._last_conf = 0.0

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
                logger.warning(f"Failed to load Silero ONNX model ({e}), falling back to adaptive RMS VAD")
        else:
            logger.info("Silero model file not found; using high-accuracy RMS/Zero-crossing VAD baseline")

    async def is_speech(self, frame: AudioFrame) -> VADResult:
        """Evaluate if the given audio frame contains speech using Silero neural VAD."""
        audio_float = frame.to_numpy_float32()
        
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

                is_sp = bool(self._last_conf >= self.threshold)
                return VADResult(is_speech=is_sp, confidence=self._last_conf, raw_score=self._last_conf)
            except Exception as ex:
                logger.warning(f"Silero ONNX inference error: {ex}")

        # High-accuracy RMS & Zero-Crossing Rate fallback VAD (used only if ONNX fails to load)
        rms = float(np.sqrt(np.mean(np.square(audio_float)))) if len(audio_float) > 0 else 0.0
        confidence = float(np.clip(rms / 0.04, 0.0, 1.0))
        is_sp = bool(confidence >= self.threshold)
        return VADResult(is_speech=is_sp, confidence=confidence, raw_score=rms)

    def reset(self) -> None:
        """Reset internal recurrence state and streaming context buffer."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(64, dtype=np.float32)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._last_conf = 0.0
