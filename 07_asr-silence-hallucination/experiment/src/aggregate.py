"""JSONL ログを集計し、ハルシネーション率と定型句頻度の表を出力する。"""

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\s。、．，.!！?？♪]+", "", text)
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--logs", nargs="*", help="対象 JSONL（省略時は log_dir の全ファイル）")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    log_dir = Path(cfg["results"]["log_dir"])
    table_dir = Path(cfg["results"]["table_dir"])
    table_dir.mkdir(parents=True, exist_ok=True)

    paths = [Path(p) for p in args.logs] if args.logs else sorted(log_dir.glob("*.jsonl"))
    rows = [json.loads(line) for p in paths for line in p.read_text().splitlines()]
    if not rows:
        raise SystemExit("no log rows found")

    df = pd.DataFrame(rows)
    if "error" in df.columns:
        n_err = df["error"].notna().sum()
        if n_err:
            print(f"warning: {n_err} error rows excluded")
        df = df[df["error"].isna()]
    df["hallucinated"] = df["text"].str.strip() != ""
    df["language"] = df["language"].fillna("auto")

    rate = (
        df.groupby(["model", "variant", "language", "condition"])["hallucinated"]
        .agg(rate="mean", n="count")
        .reset_index()
    )
    rate_path = table_dir / "hallucination_rate.csv"
    rate.to_csv(rate_path, index=False)

    halluc = df[df["hallucinated"]].copy()
    halluc["norm_text"] = halluc["text"].map(normalize_text)
    phrase_counts = Counter(halluc["norm_text"])
    phrases = pd.DataFrame(phrase_counts.most_common(), columns=["normalized_text", "count"])
    phrases_path = table_dir / "phrase_frequency.csv"
    phrases.to_csv(phrases_path, index=False)

    print(f"rows={len(df)}, hallucination rows={len(halluc)}")
    print(f"wrote {rate_path}")
    print(f"wrote {phrases_path}")
    print("\n=== 条件別ハルシネーション率（モデル×言語） ===")
    pivot = rate.pivot_table(index=["model", "variant", "language"],
                             columns="condition", values="rate")
    print(pivot.round(2).to_string())
    print("\n=== 頻出フレーズ上位 15 ===")
    print(phrases.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
