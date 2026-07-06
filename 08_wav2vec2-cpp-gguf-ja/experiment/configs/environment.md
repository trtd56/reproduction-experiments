# 実験環境・設定

実施日: 2026-07-03

## ハードウェア / OS

- Apple M3 Max (16 コア), macOS 14.7.2
- コンパイラ: Apple clang 16.0.0

## 対象コード

- リポジトリ: https://github.com/py-ai-dev/wav2vec2.cpp
  (ブログ記載の `liodon-ai/wav2vec2.cpp` は 404。実体は著者本人のアカウント側)
- wav2vec2.cpp commit: `be1a165950e64d04b7e1767e002ee773b26f12cb`
- ggml submodule commit: `eced84c86f8b012c752c016f7fe789adea168e1e`
- ビルド: `cmake -B build -DCMAKE_BUILD_TYPE=Release -DWAV2VEC2_FAST_MATH=OFF && cmake --build build -j8`
  - **注**: デフォルト (`WAV2VEC2_FAST_MATH=ON`) では ggml の `vec.h` の
    `#error`(`-ffinite-math-only` 禁止ガード)によりビルド失敗。OFF が必須。

## モデル

- GGUF: [liodon-ai/wav2vec2-large-xlsr-53-japanese-GGUF](https://huggingface.co/liodon-ai/wav2vec2-large-xlsr-53-japanese-GGUF)
  - model_f16.gguf 636MB / model_q8_0.gguf 376MB / model_q4_0.gguf 223MB
- HF 参照: [jonatasgrosman/wav2vec2-large-xlsr-53-japanese](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-japanese)
  - CPU / fp32 / batch=1 / greedy argmax(付属 parity_test.py と同一手順)

## データ

- FLEURS ja_jp test split 先頭 30 サンプル(計 363.5 秒)
  - 取得: `google/fleurs` の `parquet-data/ja_jp/test-00000-of-00001.parquet` を直接読み込み
    (datasets 5.x はローディングスクリプト非対応のため parity_test.py の取得コードは動かない)
  - float32 WAV, 16kHz mono で保存(parity_test.py と同条件)
- ブログ/モデルカードは同じ FLEURS ja_jp の 10 サンプルで評価(サンプル数は本検証で 3 倍に拡張)

## Python 環境

- リポジトリルート `.venv`(uv 管理)
- torch 2.10.0 / transformers 5.5.0 / soundfile 0.14.0 / jiwer 4.0.0

## 実行手順

```bash
PY=.venv/bin/python  # リポジトリルートから
$PY 08_wav2vec2-cpp-gguf-ja/experiment/scripts/01_prepare_data.py
$PY 08_wav2vec2-cpp-gguf-ja/experiment/scripts/02_run_hf_reference.py
$PY 08_wav2vec2-cpp-gguf-ja/experiment/scripts/03_run_cpp.py
$PY 08_wav2vec2-cpp-gguf-ja/experiment/scripts/04_evaluate.py
```
