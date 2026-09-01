"""Audio encoding, decoding, WAV headers, and Base64 format converters."""
import base64
import io
import wave
import numpy as np
from app.audio.frames import AudioFrame


class AudioCodec:
    """Audio serialization, deserialization, and format utilities."""

    @staticmethod
    def encode_base64(data: bytes) -> str:
        """Encode raw PCM bytes to Base64 string."""
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def decode_base64(data_b64: str) -> bytes:
        """Decode Base64 string to raw PCM bytes."""
        return base64.b64decode(data_b64)

    @staticmethod
    def frame_to_base64(frame: AudioFrame) -> str:
        """Serialize an AudioFrame to Base64 PCM string."""
        return AudioCodec.encode_base64(frame.data)

    @staticmethod
    def base64_to_frame(data_b64: str, sample_rate: int = 16000, seq: int = 0) -> AudioFrame:
        """Deserialize Base64 PCM string to AudioFrame."""
        pcm_bytes = AudioCodec.decode_base64(data_b64)
        return AudioFrame(data=pcm_bytes, sample_rate=sample_rate, channels=1, sample_width=2, seq=seq)

    @staticmethod
    def pcm_to_wav_bytes(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
        """Wrap raw PCM bytes with standard RIFF/WAV header."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        return buffer.getvalue()

    @staticmethod
    def wav_bytes_to_pcm(wav_bytes: bytes) -> tuple[bytes, int, int, int]:
        """Extract raw PCM bytes and format metadata from WAV container."""
        buffer = io.BytesIO(wav_bytes)
        with wave.open(buffer, "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            pcm_data = wav_file.readframes(wav_file.getnframes())
        return pcm_data, sample_rate, channels, sample_width

    @staticmethod
    def resample_linear(pcm_data: bytes, orig_sr: int, target_sr: int) -> bytes:
        """Linear interpolation resampling for PCM16 audio."""
        if orig_sr == target_sr:
            return pcm_data
        
        audio = np.frombuffer(pcm_data, dtype=np.int16)
        num_orig = len(audio)
        num_target = int(round(num_orig * (target_sr / orig_sr)))
        
        if num_orig == 0 or num_target == 0:
            return b""
            
        orig_indices = np.linspace(0, num_orig - 1, num_orig)
        target_indices = np.linspace(0, num_orig - 1, num_target)
        resampled = np.interp(target_indices, orig_indices, audio).astype(np.int16)
        return resampled.tobytes()

    @staticmethod
    def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
        """Decode G.711 μ-law bytes to linear 16-bit PCM."""
        if not mulaw_bytes:
            return b""
        mu = np.frombuffer(mulaw_bytes, dtype=np.uint8)
        b = ~mu & 0xFF
        sign = np.where(b & 0x80, -1, 1).astype(np.int16)
        exponent = ((b >> 4) & 0x07).astype(np.int16)
        mantissa = (b & 0x0F).astype(np.int16)
        sample = ((mantissa << 3) + 0x84) << exponent
        sample = (sample - 0x84) * sign
        return sample.astype(np.int16).tobytes()

    @staticmethod
    def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
        """Encode linear 16-bit PCM bytes to G.711 μ-law."""
        if not pcm_bytes:
            return b""
        data = np.frombuffer(pcm_bytes, dtype=np.int16)
        BIAS = 0x84
        CLIP = 32635
        data_clipped = np.clip(data, -32768, 32767)
        sign = (data_clipped < 0)
        data_abs = np.clip(np.abs(data_clipped), 0, CLIP) + BIAS
        
        exponent = np.zeros_like(data_abs, dtype=np.uint8)
        for exp in range(7, -1, -1):
            mask = (data_abs >= (1 << (exp + 7))) & (exponent == 0)
            exponent[mask] = exp
            
        mantissa = ((data_abs >> (exponent + 3)) & 0x0F).astype(np.uint8)
        mulaw = ~((sign.astype(np.uint8) << 7) | (exponent << 4) | mantissa) & 0xFF
        return mulaw.astype(np.uint8).tobytes()
