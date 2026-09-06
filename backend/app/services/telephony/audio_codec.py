"""Audio codec transcoding and resampling utilities for telecom carriers.

Converts carrier audio (e.g. Exotel G.711 mu-law, 8kHz PCM) into
canonical Voice Engine format (PCM16, 16kHz mono, 20ms frames), and
transcodes outbound synthesized Voice Engine audio back to carrier format.
"""

import struct
from typing import Final

# Precomputed ITU-T G.711 mu-law decompression table (8-bit mu-law -> 16-bit linear PCM)
_MULAW_DECODE_TABLE: Final[list[int]] = []
for i in range(256):
    raw = ~i & 0xFF
    sign = raw & 0x80
    exponent = (raw >> 4) & 0x07
    mantissa = raw & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    _MULAW_DECODE_TABLE.append(-sample if sign else sample)

# Precomputed 16-bit linear PCM -> 8-bit mu-law compression table
_LINEAR_TO_MULAW_MAP: Final[list[int]] = []
_BIAS = 0x84
_CLIP = 32635

for i in range(65536):
    val = i - 32768
    sign = 0x80 if val < 0 else 0
    if val < 0:
        val = -val
    val = min(val, _CLIP)
    val += _BIAS
    exponent = 7
    for exp, mask in enumerate((0x4000, 0x2000, 0x1000, 0x0800, 0x0400, 0x0200, 0x0100)):
        if val >= mask:
            exponent = 7 - exp
            break
    else:
        exponent = 0
    mantissa = (val >> (exponent + 3)) & 0x0F
    mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
    _LINEAR_TO_MULAW_MAP.append(mulaw_byte)


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Decode G.711 mu-law 8-bit byte string into signed 16-bit linear PCM."""
    if not mulaw_bytes:
        return b""
    samples = [_MULAW_DECODE_TABLE[b] for b in mulaw_bytes]
    return struct.pack(f"<{len(samples)}h", *samples)


def pcm16_to_mulaw(pcm16_bytes: bytes) -> bytes:
    """Encode signed 16-bit linear PCM into G.711 mu-law 8-bit bytes."""
    if not pcm16_bytes:
        return b""
    num_samples = len(pcm16_bytes) // 2
    if num_samples == 0:
        return b""
    samples = struct.unpack(f"<{num_samples}h", pcm16_bytes[: num_samples * 2])
    return bytes(_LINEAR_TO_MULAW_MAP[s + 32768] for s in samples)


def resample_8k_to_16k(pcm16_8k: bytes) -> bytes:
    """Upsample 8kHz 16-bit mono PCM to 16kHz 16-bit mono PCM via linear interpolation."""
    if len(pcm16_8k) < 2:
        return b""
    num_samples = len(pcm16_8k) // 2
    samples = struct.unpack(f"<{num_samples}h", pcm16_8k[: num_samples * 2])
    out_samples: list[int] = []
    for i in range(num_samples - 1):
        s0 = samples[i]
        s1 = samples[i + 1]
        mid = (s0 + s1) // 2
        out_samples.extend((s0, mid))
    if num_samples > 0:
        last = samples[-1]
        out_samples.extend((last, last))
    return struct.pack(f"<{len(out_samples)}h", *out_samples)


def resample_16k_to_8k(pcm16_16k: bytes) -> bytes:
    """Downsample 16kHz 16-bit mono PCM to 8kHz 16-bit mono PCM via 2:1 decimation."""
    if len(pcm16_16k) < 4:
        return b""
    num_samples = len(pcm16_16k) // 2
    samples = struct.unpack(f"<{num_samples}h", pcm16_16k[: num_samples * 2])
    out_samples = [samples[i] for i in range(0, num_samples, 2)]
    return struct.pack(f"<{len(out_samples)}h", *out_samples)


def transcode_carrier_to_voice_engine(
    raw_audio: bytes,
    encoding: str = "audio/x-mulaw",
    source_rate: int = 8000,
    target_rate: int = 16000,
) -> bytes:
    """Transcode carrier inbound audio into canonical Voice Engine PCM16 (16kHz)."""
    enc_lower = encoding.lower()
    if "mulaw" in enc_lower or "ulaw" in enc_lower or "pcmu" in enc_lower:
        pcm = mulaw_to_pcm16(raw_audio)
    else:
        pcm = raw_audio

    if source_rate == 8000 and target_rate == 16000:
        return resample_8k_to_16k(pcm)
    return pcm


def transcode_voice_engine_to_carrier(
    pcm16_16k: bytes,
    target_encoding: str = "audio/x-mulaw",
    target_rate: int = 8000,
) -> bytes:
    """Transcode Voice Engine PCM16 (16kHz) audio into target carrier format."""
    enc_lower = target_encoding.lower()
    if target_rate == 8000:
        pcm = resample_16k_to_8k(pcm16_16k)
    else:
        pcm = pcm16_16k

    if "mulaw" in enc_lower or "ulaw" in enc_lower or "pcmu" in enc_lower:
        return pcm16_to_mulaw(pcm)
    return pcm
