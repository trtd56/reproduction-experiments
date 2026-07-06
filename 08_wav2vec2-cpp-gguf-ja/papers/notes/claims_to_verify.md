# 検証対象の主張整理

対象: [wav2vec2.cpp — Run Any wav2vec2 Model Locally, No Python Required](https://huggingface.co/blog/PY-AI-Dev/wav2vec2gguf)
(HF ブログ、著者 PY-AI-Dev / Liodon AI、2026年)

## 主張リスト

| # | 主張 | 検証方法 | 検証可否 |
|---|---|---|---|
| C1 | GitHub リポジトリ `liodon-ai/wav2vec2.cpp` からクローンしてビルドできる | git clone + cmake | ブログのリンクは **404**。実体は `py-ai-dev/wav2vec2.cpp` |
| C2 | ソースから cmake でビルドできる(依存なし、C++17 + CMake のみ) | macOS (Apple Silicon) でビルド | デフォルト設定では ggml ガードで**ビルド失敗**。`-DWAV2VEC2_FAST_MATH=OFF` で成功 |
| C3 | 83 個のユニットテストが通る | ctest / test_ops + test_gguf | 60+23=83 パス |
| C4 | 日本語含む 15 言語の GGUF (F16/Q8_0/Q4_0) が HF で公開されている | HF Hub 確認 + ダウンロード | ja: 636MB/376MB/223MB を確認 |
| C5 | 日本語モデルの量子化誤差: F16 ~0% / Q8_0 ~0% / Q4_0 8.26% CER (HF出力比, FLEURS ja_jp 10件) | parity_test.py 準拠、FLEURS ja_jp 先頭30件で再測定 | ほぼ再現: F16 0.22% / Q8_0 0.60% / Q4_0 8.79% |
| C6 | CLI は greedy/beam、単語タイムスタンプ、txt/json/srt/vtt 出力に対応 | CLI ヘルプ + 実行 | フラグは全て存在 |
| C7 | Q8_0 で約40%、Q4_0 で約65% 圧縮 | ファイルサイズ比較 | ja: Q8_0 = 376/636 = 41%減、Q4_0 = 223/636 = 65%減 |
| C8 | CPU でリアルタイムより速い (large: RTF 0.32 @ 20-core ARM) | M3 Max で RTF 計測 | 未再現: RTF ≈3.1(conv1d がシングルスレッドのスカラー実装で支配的) |

## 補足

- モデルカード側の記載では F16/Q8_0 の CER は 0.20–0.23%(ブログの表では ~0%)。
  「CER/WER measured against HF model output (not ground truth) to isolate quantization error」
  と明記されており、正解文に対する精度ではない点に注意。
- ブログのビルド手順 (`mkdir build && cd build && cmake ..`) は fast-math ガードの件に触れていない。
  ggml サブモジュール (commit eced84c8) の `vec.h:1055` に `-ffinite-math-only` 禁止の #error があり、
  プロジェクト既定の `WAV2VEC2_FAST_MATH=ON` (`-ffast-math`) と衝突する。
  Apple clang 17 / macOS では素の手順ではビルドできない。
