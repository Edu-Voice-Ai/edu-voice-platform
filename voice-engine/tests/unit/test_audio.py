"""Unit tests for AudioFrame, AudioCodec, and buffering components."""
import pytest
import numpy as np
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.audio.buffering import AudioChunker, RingBuffer


def test_audio_frame_properties():
    # 20ms @ 16kHz, 16-bit mono = 320 samples = 640 bytes
    pcm_bytes = b"\x00\x00" * 320
    frame = AudioFrame(data=pcm_bytes, sample_rate=16000, channels=1, sample_width=2)
    
    assert frame.num_samples == 320
    assert frame.duration_ms == 20.0
    assert len(frame.to_numpy_int16()) == 320
    assert len(frame.to_numpy_float32()) == 320


def test_audio_codec_base64_and_wav():
    pcm_bytes = b"\x01\x02" * 160
    b64_encoded = AudioCodec.encode_base64(pcm_bytes)
    assert isinstance(b64_encoded, str)
    
    decoded = AudioCodec.decode_base64(b64_encoded)
    assert decoded == pcm_bytes

    wav_bytes = AudioCodec.pcm_to_wav_bytes(pcm_bytes, sample_rate=16000)
    assert wav_bytes.startswith(b"RIFF")
    
    extracted_pcm, sr, ch, sw = AudioCodec.wav_bytes_to_pcm(wav_bytes)
    assert extracted_pcm == pcm_bytes
    assert sr == 16000
    assert ch == 1
    assert sw == 2


def test_audio_chunker_slicing():
    chunker = AudioChunker(sample_rate=16000, frame_duration_ms=20)
    # Feed 1500 bytes (each 20ms frame = 640 bytes -> 2 full frames, 220 remainder)
    raw = b"\xaa" * 1500
    frames = chunker.feed(raw)
    
    assert len(frames) == 2
    assert len(frames[0].data) == 640
    assert len(frames[1].data) == 640
    
    # Flush remainder (padded to 640)
    final_frame = chunker.flush()
    assert final_frame is not None
    assert len(final_frame.data) == 640


def test_ring_buffer_operations():
    rb = RingBuffer(capacity_bytes=100)
    rb.write(b"abcdefghij")  # 10 bytes
    assert len(rb) == 10
    
    out = rb.read(5)
    assert out == b"abcde"
    assert len(rb) == 5
    
    rb.clear()
    assert len(rb) == 0
