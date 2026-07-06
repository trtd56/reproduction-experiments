"""非音声オーディオ（無音・各種ノイズ）を合成して WAV に保存する。"""

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml


def dbfs_to_amplitude(dbfs: float) -> float:
    return 10.0 ** (dbfs / 20.0)


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f スペクトルのノイズを周波数領域で生成する。"""
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0)
    freqs[0] = freqs[1]  # DC のゼロ除算回避
    spectrum /= np.sqrt(freqs)
    signal = np.fft.irfft(spectrum, n=n)
    return signal / np.max(np.abs(signal))


def synthesize(kind: str, n: int, sr: int, rng: np.random.Generator, cond: dict) -> np.ndarray:
    if kind == "silence":
        return np.zeros(n)
    if kind == "white":
        sig = rng.standard_normal(n)
        return sig / np.max(np.abs(sig))
    if kind == "pink":
        return pink_noise(n, rng)
    if kind == "hum":
        t = np.arange(n) / sr
        sig = sum(np.sin(2 * np.pi * 50.0 * k * t) / k for k in (1, 2, 3))
        return sig / np.max(np.abs(sig))
    if kind == "tone":
        t = np.arange(n) / sr
        return np.sin(2 * np.pi * cond.get("freq_hz", 440) * t)
    raise ValueError(f"unknown kind: {kind}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())["audio"]
    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    sr = cfg["sample_rate"]
    n = int(cfg["duration_sec"] * sr)

    for cond in cfg["conditions"]:
        n_seeds = 1 if cond.get("deterministic") else cfg["n_seeds"]
        for seed in range(n_seeds):
            rng = np.random.default_rng(seed)
            sig = synthesize(cond["kind"], n, sr, rng, cond)
            level = cond.get("level_dbfs")
            if level is not None:
                sig = sig * dbfs_to_amplitude(level)
            path = out_dir / f"{cond['name']}_seed{seed}.wav"
            sf.write(path, sig.astype(np.float32), sr, subtype="PCM_16")
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
