#!/usr/bin/env python3
"""FLEURS ja_jp test の先頭 N サンプルを WAV + メタデータとして書き出す。

datasets 5.x はローディングスクリプト非対応のため、HF Hub 上の
parquet-data/ja_jp/test-00000-of-00001.parquet を直接読む。
音声は parity_test.py と同条件の float32 WAV で保存する。
"""

import io
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
from huggingface_hub import hf_hub_download

STUDY = Path(__file__).resolve().parents[2]
OUT_DIR = STUDY / "experiment" / "data" / "processed" / "fleurs_ja_test30"
N_SAMPLES = 30

def main():
    parquet_path = hf_hub_download(
        "google/fleurs",
        "parquet-data/ja_jp/test-00000-of-00001.parquet",
        repo_type="dataset",
    )
    table = pq.read_table(parquet_path)
    print(f"columns: {table.column_names}")
    print(f"total rows: {table.num_rows}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = []
    for i in range(N_SAMPLES):
        row = {c: table[c][i].as_py() for c in table.column_names if c != "audio"}
        audio = table["audio"][i].as_py()
        data, sr = sf.read(io.BytesIO(audio["bytes"]), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        wav_path = OUT_DIR / f"sample_{i:03d}.wav"
        sf.write(wav_path, data.astype(np.float32), sr, subtype="FLOAT")
        meta.append({
            "index": i,
            "wav": wav_path.name,
            "id": row.get("id"),
            "sr": sr,
            "duration_sec": round(len(data) / sr, 2),
            "transcription": row.get("transcription", ""),
            "raw_transcription": row.get("raw_transcription", ""),
        })
        print(f"{wav_path.name}  {sr}Hz  {len(data)/sr:.1f}s  {row.get('transcription','')[:40]}")

    with open(OUT_DIR / "metadata.json", "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    total = sum(m["duration_sec"] for m in meta)
    print(f"\nsaved {len(meta)} samples ({total:.1f}s total) -> {OUT_DIR}")

if __name__ == "__main__":
    main()
