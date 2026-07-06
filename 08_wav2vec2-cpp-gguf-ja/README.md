# 08: wav2vec2.cpp — GGUF 量子化 wav2vec2 の日本語 ASR 検証

HF ブログ [wav2vec2.cpp — Run Any wav2vec2 Model Locally, No Python Required](https://huggingface.co/blog/PY-AI-Dev/wav2vec2gguf)(PY-AI-Dev / Liodon AI)の検証。

wav2vec2 の GGUF 量子化 + C++ 推論エンジン(whisper.cpp の wav2vec2 版)を、
日本語モデル `wav2vec2-large-xlsr-53-japanese` の GGUF で実際にビルド・実行し、
ブログ/モデルカードが主張する量子化誤差(F16 ~0% / Q8_0 ~0% / Q4_0 8.26% CER)を再測定する。

## 対象

- ブログ: https://huggingface.co/blog/PY-AI-Dev/wav2vec2gguf
- コード: https://github.com/py-ai-dev/wav2vec2.cpp(ブログ記載の `liodon-ai/wav2vec2.cpp` は 404)
- モデル: https://huggingface.co/liodon-ai/wav2vec2-large-xlsr-53-japanese-GGUF
- 元モデル: https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-japanese
- データ: FLEURS ja_jp test split 先頭 30 サンプル

## ステータス(2026-07-03 完了)

**量子化誤差の主張はほぼ再現、ビルド再現性と性能主張は未再現。**

| 項目 | ブログの主張 | 本検証 (FLEURS ja_jp 30件, M3 Max) |
|---|---|---|
| F16 CER vs HF出力 | ~0%(カード 0.20–0.23%)| 0.22% ✅ |
| Q8_0 CER vs HF出力 | ~0%(カード 0.20–0.23%)| 0.60% ⚠️ 同オーダー |
| Q4_0 CER vs HF出力 | 8.26% | 8.79% ✅ |
| リポジトリリンク | liodon-ai/wav2vec2.cpp | 404(実体は py-ai-dev/wav2vec2.cpp)❌ |
| ビルド | cmake だけで成功 | macOS では `-DWAV2VEC2_FAST_MATH=OFF` 必須 ❌ |
| 速度 | xlsr-large RTF 0.32 | RTF ≈3.1(PyTorch CPU の約60倍遅い)❌ |

詳細は `analysis/findings.md` と `experiment/results/tables/summary.md` を参照。

## 構成

- `papers/notes/claims_to_verify.md` — 検証対象の主張一覧と一次結果
- `experiment/configs/environment.md` — 環境・コミット・実行手順
- `experiment/scripts/01–04_*.py` — データ準備 / HF 参照 / C++ 実行 / CER 評価
- `experiment/external/wav2vec2.cpp/` — 検証時にローカルで clone する upstream(公開リポジトリには含めない)
- `analysis/` — 結果の考察
