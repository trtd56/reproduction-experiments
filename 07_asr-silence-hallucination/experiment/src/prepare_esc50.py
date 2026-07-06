"""ESC-50 の選択カテゴリを 16kHz mono / 30 秒にそろえて実験用音声として書き出す。

ESC-50: Piczak 2015, CC BY-NC 3.0. https://github.com/karolpiczak/ESC-50
5 秒クリップを 6 回タイル（ループ）して 30 秒 = Whisper 1 ウィンドウに合わせる。
"""

import argparse
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import resample_poly

CATEGORIES = ["rain", "keyboard_typing", "clock_tick", "coughing", "breathing", "laughing"]
CLIPS_PER_CATEGORY = 5
TARGET_SR = 16000
TILE = 6  # 5s x 6 = 30s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", default="data/external/esc50.zip")
    parser.add_argument("--out-dir", default="data/processed/audio")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(args.zip) as zf:
        meta = pd.read_csv(BytesIO(zf.read("ESC-50-master/meta/esc50.csv")))
        for cat in CATEGORIES:
            files = sorted(meta[meta["category"] == cat]["filename"])[:CLIPS_PER_CATEGORY]
            for i, fname in enumerate(files):
                data, sr = sf.read(BytesIO(zf.read(f"ESC-50-master/audio/{fname}")))
                if data.ndim > 1:
                    data = data.mean(axis=1)
                data = resample_poly(data, TARGET_SR, sr)
                data = np.tile(data, TILE)
                peak = np.max(np.abs(data))
                if peak > 0:
                    data = data / peak * 0.5  # -6dBFS に正規化
                path = out_dir / f"esc50_{cat}_seed{i}.wav"
                sf.write(path, data.astype(np.float32), TARGET_SR, subtype="PCM_16")
                print(f"wrote {path}  (src={fname})")


if __name__ == "__main__":
    main()
