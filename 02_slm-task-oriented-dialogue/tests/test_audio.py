import wave

import numpy as np

from restaurant_voice_demo.audio import (
    bytes_to_float32_pcm,
    float32_pcm_to_wav_bytes,
    normalize_peak,
    pcm16_wav_bytes,
    resample_pcm,
)


def test_bytes_to_float32_pcm_clips_invalid_values():
    values = np.array([0.0, 2.0, -2.0, np.nan], dtype="<f4")
    decoded = bytes_to_float32_pcm(values.tobytes())
    assert decoded.tolist() == [0.0, 1.0, -1.0, 0.0]


def test_resample_pcm_changes_length():
    audio = np.ones(48_000, dtype=np.float32) * 0.1
    resampled = resample_pcm(audio, 48_000, 24_000)
    assert 23_990 <= resampled.size <= 24_010


def test_normalize_peak_limits_loud_audio():
    audio = np.array([0.0, 2.0, -1.0], dtype=np.float32)
    normalized = normalize_peak(audio, peak=0.5)
    assert float(np.max(np.abs(normalized))) <= 0.5001


def test_float32_pcm_to_wav_bytes_is_readable():
    audio = np.zeros(240, dtype=np.float32)
    data = float32_pcm_to_wav_bytes(audio, 24_000)
    with wave.open(__import__("io").BytesIO(data), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 24_000


def test_pcm16_wav_bytes_is_readable():
    data = pcm16_wav_bytes(b"\x00\x00" * 240, 24_000)
    with wave.open(__import__("io").BytesIO(data), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 24_000
        assert wav.getnframes() == 240
