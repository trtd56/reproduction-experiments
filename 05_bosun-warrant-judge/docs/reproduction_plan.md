# Reproduction Plan

## 目的

Hanno Labs の Bosun (blog: https://huggingface.co/blog/Hanno-Labs/bosun) の中心的主張

> 0.6B の LoRA 微調整 reranker が、1 文で与えた任意ルールに従う
> （steerability 0.94、未訓練ルールでも 0.95）

を、公開されている WarrantBench データセット（pinned revision）と公開モデル重みを使って
ローカルで検証する。

## 検証範囲

やること:

1. cosine baseline（instruction-blind の対照）を default / novel 両 config で実行。
   構成上 steerability = 0.00 になることを確認する。
2. Bosun-XS (0.6B) を serving.json 仕様どおりにローカル推論（M3 Max, MPS, bf16）で
   default / novel 両 config を評価し、公表値と比較する。

やらないこと（スコープ外の理由付き）:

- Bosun-4B: XS で主張の骨子は検証できる。必要なら追実験。
- gemini-3.1-flash-lite baseline: API キーが必要。主張の核は「小型特化モデルが指示に
  従えるか」であり、frontier baseline の数値は参考値として公表値を引用する。
- FollowIR: 別ベンチマークで評価パイプラインが重い。今回は WarrantBench に絞る。
- 訓練の再現: 訓練データ・レシピは非公開（soft-target 蒸留とだけ記載）。重みからの
  推論再現のみ可能。

## 手法

- 公式ハーネス `external/warrantbench/warrantbench/score.py` の `load()`（dataset
  revision pin 込み）と `metrics()` をそのまま import して使い、metric 実装の差異を排除。
- 公式の `bosun_judge` は HTTP エンドポイント前提のため、`bosun_local_judge` を追加実装:
  - `Qwen/Qwen3-Reranker-0.6B` + LoRA `Hanno-Labs/bosun-xs` を merge
  - serving.json の prefix/suffix/yes_id/no_id/max_len を使用
  - `sigmoid(logit_yes − logit_no)` を出力
- 判定の成否基準（事前に決めておく）:
  - steerability が公表 0.94 (±0.02 程度) で再現するか
  - topicality_neg / bridge AUROC が 0.97 / 0.83 近傍か
  - novel split (money / government) AUROC が 0.95 近傍か
  - cosine baseline が README 記載値 (0.00 / 0.00 / 0.32) と一致するか

## 環境

- Apple M3 Max / 64GB, macOS (Darwin 23.6.0)
- Python 3.12 (uv venv), torch (MPS), transformers, peft, datasets
- dataset: Hanno-Labs/warrantbench @ aa052bd（コードに pin 済み）
