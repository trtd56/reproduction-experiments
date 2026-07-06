#!/usr/bin/env python3
"""HF 参照実装 (jonatasgrosman/wav2vec2-large-xlsr-53-japanese) で転写を生成。

parity_test.py の run_hf と同じ手順: CPU / fp32 / batch=1 / greedy argmax decode。
"""

import json
import time
from pathlib import Path

import soundfile as sf
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

STUDY = Path(__file__).resolve().parents[2]
DATA_DIR = STUDY / "experiment" / "data" / "processed" / "fleurs_ja_test30"
OUT = STUDY / "experiment" / "results" / "metrics" / "hf_reference.json"
MODEL_ID = "jonatasgrosman/wav2vec2-large-xlsr-53-japanese"

def main():
    proc = Wav2Vec2Processor.from_pretrained(MODEL_ID)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL_ID)
    model.eval()

    meta = json.loads((DATA_DIR / "metadata.json").read_text())
    results = []
    with torch.no_grad():
        for m in meta:
            path = DATA_DIR / m["wav"]
            audio, sr = sf.read(path, dtype="float32")
            assert sr == 16000, f"unexpected sr {sr}"
            t0 = time.perf_counter()
            inputs = proc(audio, sampling_rate=16000, return_tensors="pt", padding=True)
            logits = model(**inputs).logits
            ids = torch.argmax(logits, dim=-1)
            text = proc.batch_decode(ids)[0].strip()
            dt = time.perf_counter() - t0
            results.append({"wav": m["wav"], "text": text, "time_sec": round(dt, 3)})
            print(f"{m['wav']}  ({dt:.1f}s)  {text[:60]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"model": MODEL_ID, "device": "cpu", "dtype": "fp32", "results": results},
        ensure_ascii=False, indent=2))
    print(f"\nsaved -> {OUT}")

if __name__ == "__main__":
    main()
