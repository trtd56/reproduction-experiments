#!/usr/bin/env python3
"""CER 評価。

1. 量子化誤差の分離: CLI 出力 vs HF 出力の CER (parity_test.py と同じ、大文字化のみ)
   -> ブログ / モデルカードの主張 (F16 ~0.2%, Q8_0 ~0.2%, Q4_0 8.26%) と比較
2. 絶対品質: HF / 各量子化 の出力 vs FLEURS 正解文の CER (日本語向け正規化後)
"""

import json
import re
import unicodedata
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
DATA_DIR = STUDY / "experiment" / "data" / "processed" / "fleurs_ja_test30"
METRICS = STUDY / "experiment" / "results" / "metrics"
TABLES = STUDY / "experiment" / "results" / "tables"

QUANTS = ["f16", "q8_0", "q4_0"]


def edit_distance(a, b):
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            tmp = dp[j]
            dp[j] = prev if a[i - 1] == b[j - 1] else 1 + min(prev, dp[j], dp[j - 1])
            prev = tmp
    return dp[n]


def cer(ref, hyp):
    ref, hyp = ref.strip(), hyp.strip()
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def normalize_ja(text):
    """正解文照合用: NFKC、空白と句読点・記号を除去。"""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\s、。，．・「」『』（）()!?！？…‥〜~:：;；\"'\-]", "", text)
    return text


def main():
    meta = {m["wav"]: m for m in json.loads((DATA_DIR / "metadata.json").read_text())}
    hf = {r["wav"]: r for r in json.loads((METRICS / "hf_reference.json").read_text())["results"]}
    cpp = {
        q: {r["wav"]: r for r in json.loads((METRICS / f"cpp_{q}.json").read_text())["results"]}
        for q in QUANTS
    }
    wavs = sorted(meta.keys())

    # 1) 量子化誤差の分離 (CLI vs HF 出力, parity_test.py と同一手法)
    parity = {}
    for q in QUANTS:
        rows = []
        for w in wavs:
            c = cer(hf[w]["text"].upper(), cpp[q][w]["text"].upper())
            rows.append({"wav": w, "cer_vs_hf": round(c, 4)})
        mean = sum(r["cer_vs_hf"] for r in rows) / len(rows)
        parity[q] = {"mean_cer_vs_hf": round(mean, 4), "rows": rows}
        print(f"[parity] {q}: mean CER vs HF = {mean:.2%}")

    # 2) 正解文に対する CER (正規化後)
    absolute = {}
    systems = {"hf_py": {w: hf[w]["text"] for w in wavs}}
    for q in QUANTS:
        systems[f"cpp_{q}"] = {w: cpp[q][w]["text"] for w in wavs}
    for name, outs in systems.items():
        rows = []
        for w in wavs:
            ref = normalize_ja(meta[w]["transcription"])
            hyp = normalize_ja(outs[w])
            rows.append({"wav": w, "cer_vs_gt": round(cer(ref, hyp), 4)})
        mean = sum(r["cer_vs_gt"] for r in rows) / len(rows)
        absolute[name] = {"mean_cer_vs_gt": round(mean, 4), "rows": rows}
        print(f"[absolute] {name}: mean CER vs ground truth = {mean:.2%}")

    # 3) 速度 (RTF)
    speed = {}
    hf_rtf = sum(hf[w]["time_sec"] for w in wavs) / sum(meta[w]["duration_sec"] for w in wavs)
    speed["hf_py_cpu_fp32"] = round(hf_rtf, 3)
    for q in QUANTS:
        rtf = sum(cpp[q][w]["time_sec"] for w in wavs) / sum(meta[w]["duration_sec"] for w in wavs)
        speed[f"cpp_{q}"] = round(rtf, 3)
    print(f"[speed] RTF: {speed}")

    METRICS.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    (METRICS / "evaluation.json").write_text(json.dumps(
        {"n_samples": len(wavs), "parity": parity, "absolute": absolute, "speed_rtf": speed},
        ensure_ascii=False, indent=2))

    # Markdown サマリ表
    lines = [
        "# wav2vec2.cpp 日本語 GGUF 検証結果",
        "",
        f"FLEURS ja_jp test 先頭 {len(wavs)} サンプル / 手法: parity_test.py 準拠",
        "",
        "## 量子化誤差 (CLI 出力 vs HF fp32 出力の CER)",
        "",
        "| 量子化 | 本検証 mean CER | ブログ/モデルカードの主張 |",
        "|---|---|---|",
        f"| F16 | {parity['f16']['mean_cer_vs_hf']:.2%} | ~0% (カード: 0.20-0.23%) |",
        f"| Q8_0 | {parity['q8_0']['mean_cer_vs_hf']:.2%} | ~0% (カード: 0.20-0.23%) |",
        f"| Q4_0 | {parity['q4_0']['mean_cer_vs_hf']:.2%} | 8.26% |",
        "",
        "## 正解文 (FLEURS transcription, 正規化後) に対する CER",
        "",
        "| システム | mean CER |",
        "|---|---|",
    ]
    for name, d in absolute.items():
        lines.append(f"| {name} | {d['mean_cer_vs_gt']:.2%} |")
    lines += ["", "## 速度 (RTF, 小さいほど速い)", "", "| システム | RTF |", "|---|---|"]
    for name, v in speed.items():
        lines.append(f"| {name} | {v} |")
    (TABLES / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"\nsaved -> {METRICS / 'evaluation.json'}, {TABLES / 'summary.md'}")

if __name__ == "__main__":
    main()
