#!/usr/bin/env python3
"""wav2vec2-cli を F16/Q8_0/Q4_0 の各 GGUF で全サンプルに実行し、転写と時間を記録。"""

import json
import subprocess
import time
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
DATA_DIR = STUDY / "experiment" / "data" / "processed" / "fleurs_ja_test30"
MODEL_DIR = STUDY / "experiment" / "data" / "external" / "models-ja-gguf"
CLI = STUDY / "experiment" / "external" / "wav2vec2.cpp" / "build" / "wav2vec2-cli"
OUT_DIR = STUDY / "experiment" / "results" / "metrics"

QUANTS = {
    "f16": "model_f16.gguf",
    "q8_0": "model_q8_0.gguf",
    "q4_0": "model_q4_0.gguf",
}

def main():
    meta = json.loads((DATA_DIR / "metadata.json").read_text())
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for quant, fname in QUANTS.items():
        gguf = MODEL_DIR / fname
        results = []
        print(f"\n=== {quant} ({fname}) ===")
        for m in meta:
            wav = DATA_DIR / m["wav"]
            t0 = time.perf_counter()
            r = subprocess.run(
                [str(CLI), "-m", str(gguf), "-f", str(wav), "-t", "4"],
                capture_output=True, text=True, timeout=600)
            dt = time.perf_counter() - t0
            if r.returncode != 0:
                raise RuntimeError(f"{quant} {m['wav']} failed: {r.stderr}")
            text = r.stdout.strip()
            results.append({
                "wav": m["wav"], "text": text,
                "time_sec": round(dt, 3),
                "duration_sec": m["duration_sec"],
            })
            print(f"{m['wav']}  ({dt:.1f}s / {m['duration_sec']}s audio)  {text[:50]}")

        out = OUT_DIR / f"cpp_{quant}.json"
        out.write_text(json.dumps(
            {"gguf": fname, "threads": 4, "beam": 1, "results": results},
            ensure_ascii=False, indent=2))
        print(f"saved -> {out}")

if __name__ == "__main__":
    main()
