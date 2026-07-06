"""集計結果からヒートマップ・棒グラフを生成する。"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml

MODEL_ORDER = ["tiny", "base", "small", "medium", "large-v3",
               "kotoba-tech/kotoba-whisper-v2.0"]
CONDITION_ORDER = ["silence", "noise_floor", "white_lo", "white_mid", "white_hi",
                   "pink_lo", "pink_mid", "pink_hi", "hum", "tone"]


def heatmap(ax, pivot, title):
    im = ax.imshow(pivot.values, vmin=0, vmax=1, cmap="Reds", aspect="auto")
    ax.set_xticks(range(len(pivot.columns)), pivot.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(pivot.index)), pivot.index)
    ax.set_title(title)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=7,
                        color="white" if v > 0.6 else "black")
    return im


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    fig_dir = Path("results/figures")
    fig_dir.mkdir(parents=True, exist_ok=True)
    rate = pd.read_csv(Path(cfg["results"]["table_dir"]) / "hallucination_rate.csv")

    # 図1: モデル × 条件 ヒートマップ（default variant、言語別）
    langs = ["ja", "en", "auto"]
    fig, axes = plt.subplots(1, len(langs), figsize=(16, 4), sharey=True)
    for ax, lang in zip(axes, langs):
        sub = rate[(rate["variant"] == "default") & (rate["language"] == lang)]
        pivot = (sub.pivot_table(index="model", columns="condition", values="rate")
                 .reindex(index=[m for m in MODEL_ORDER if m in sub["model"].unique()],
                          columns=[c for c in CONDITION_ORDER if c in sub["condition"].unique()]))
        pivot.index = [i.split("/")[-1] for i in pivot.index]
        im = heatmap(ax, pivot, f"language={lang}")
    fig.colorbar(im, ax=axes, shrink=0.8, label="hallucination rate")
    fig.suptitle("Hallucination rate on non-speech audio (default decoding)")
    path = fig_dir / "rate_heatmap_by_language.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"wrote {path}")

    # 図2: 緩和策バリアント比較（tiny/base、条件横断平均）
    sub = rate[rate["model"].isin(["tiny", "base"])]
    pivot = sub.pivot_table(index="variant", columns="model", values="rate")
    pivot = pivot.reindex(["no_suppress", "default", "no_condition", "vad"])
    fig, ax = plt.subplots(figsize=(7, 4))
    pivot.plot.bar(ax=ax, rot=0, color=["#888", "#c44"])
    ax.set_ylabel("mean hallucination rate")
    ax.set_title("Mitigation variants (mean over conditions/languages, tiny & base)")
    ax.set_ylim(0, 1.05)
    path = fig_dir / "mitigation_variants.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"wrote {path}")

    # 図3: ESC-50 実環境音での default vs VAD（VAD すり抜けの可視化）
    sub = rate[rate["condition"].str.startswith("esc50_")].copy()
    if not sub.empty:
        sub["condition"] = sub["condition"].str.replace("esc50_", "")
        fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
        for ax, variant in zip(axes, ["default", "vad"]):
            pivot = (sub[sub["variant"] == variant]
                     .pivot_table(index="model", columns="condition", values="rate")
                     .reindex(index=["tiny", "base", "large-v3"]))
            im = heatmap(ax, pivot, f"variant={variant}")
        fig.colorbar(im, ax=axes, shrink=0.8, label="hallucination rate")
        fig.suptitle("ESC-50 real environmental sounds: VAD leaks on human vocalizations")
        path = fig_dir / "esc50_vad_leak.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
