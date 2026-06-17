from __future__ import annotations

import io
import wave

import numpy as np


def bytes_to_float32_pcm(payload: bytes) -> np.ndarray:
    if not payload:
        return np.zeros(0, dtype=np.float32)
    audio = np.frombuffer(payload, dtype="<f4").astype(np.float32, copy=True)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(audio, -1.0, 1.0)


def concatenate_pcm(chunks: list[bytes]) -> np.ndarray:
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate([bytes_to_float32_pcm(chunk) for chunk in chunks])


def resample_pcm(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if audio.size == 0 or source_rate == target_rate:
        return audio.astype(np.float32, copy=False)

    try:
        from scipy.signal import resample_poly

        gcd = int(np.gcd(source_rate, target_rate))
        resampled = resample_poly(audio, target_rate // gcd, source_rate // gcd)
    except Exception:
        duration = audio.size / float(source_rate)
        target_size = max(1, int(round(duration * target_rate)))
        source_x = np.linspace(0.0, duration, num=audio.size, endpoint=False)
        target_x = np.linspace(0.0, duration, num=target_size, endpoint=False)
        resampled = np.interp(target_x, source_x, audio)

    return np.clip(resampled.astype(np.float32), -1.0, 1.0)


def normalize_peak(audio: np.ndarray, peak: float = 0.95) -> np.ndarray:
    if audio.size == 0:
        return audio.astype(np.float32, copy=False)
    max_abs = float(np.max(np.abs(audio)))
    if max_abs <= 0.0 or max_abs <= peak:
        return audio.astype(np.float32, copy=False)
    return (audio * (peak / max_abs)).astype(np.float32)


def float32_pcm_to_bytes(audio: np.ndarray) -> bytes:
    return np.asarray(audio, dtype="<f4").tobytes()


def float32_pcm_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    clipped = np.clip(audio, -1.0, 1.0)
    buffer = io.BytesIO()
    try:
        import soundfile as sf

        sf.write(buffer, clipped, sample_rate, format="WAV", subtype="PCM_16")
    except Exception:
        pcm16 = (clipped * 32767.0).astype("<i2")
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm16.tobytes())
    return buffer.getvalue()


def pcm16_wav_bytes(pcm: bytes, sample_rate: int = 24_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()
