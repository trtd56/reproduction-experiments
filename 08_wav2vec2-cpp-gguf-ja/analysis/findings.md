# 検証結果と考察

対象ブログ: [wav2vec2.cpp — Run Any wav2vec2 Model Locally, No Python Required](https://huggingface.co/blog/PY-AI-Dev/wav2vec2gguf)
実施日: 2026-07-03 / 環境: Apple M3 Max (16コア), macOS 14.7.2, Apple clang 16

## 主張別の判定サマリ

| # | 主張 | 判定 |
|---|---|---|
| C1 | `liodon-ai/wav2vec2.cpp` からクローンできる | ❌ ブログのリンクは404。実体は `py-ai-dev/wav2vec2.cpp` |
| C2 | cmake だけでビルドできる | ⚠️ macOS では素の手順だとビルド失敗。`-DWAV2VEC2_FAST_MATH=OFF` が必要 |
| C3 | 83個のユニットテストが通る | ✅ ops 60 + gguf 23 = 83 全パス |
| C4 | 15言語の GGUF リポジトリ公開 | ✅ HF API で15リポジトリ確認 |
| C5 | 日本語量子化誤差 F16 ~0% / Q8_0 ~0% / Q4_0 8.26% CER | ✅ ほぼ再現: F16 0.22% / Q8_0 0.60% / Q4_0 8.79% (30サンプル) |
| C6 | CLI 機能 (greedy/beam, タイムスタンプ, txt/json/srt/vtt) | ✅ フラグ全て実在・動作 |
| C7 | Q8_0 で約40%、Q4_0 で約65% 圧縮 | ✅ ja: 636→376MB (-41%), 636→223MB (-65%) |
| C8 | 高速CPU推論 (xlsr-large RTF 0.32 @20コアARM) | ❌ M3 Max で RTF ≈3〜4。PyTorch CPU (RTF 0.055) の約60倍遅い |

## C2: ビルドの再現性

デフォルト設定 (`WAV2VEC2_FAST_MATH=ON`) では、`add_compile_options(-ffast-math)` が
サブディレクトリの ggml にも伝播し、ggml の `src/ggml-cpu/vec.h:1055` にある

> "some routines in ggml.c require non-finite math arithmetics -- pass -fno-finite-math-only"

の `#error` ガードに当たってコンパイル失敗する(ggml commit eced84c8, Apple clang 16)。
ブログにもリポジトリ README にもこの回避策の記載はない。
`cmake -B build -DCMAKE_BUILD_TYPE=Release -DWAV2VEC2_FAST_MATH=OFF` で成功。

## C8: 性能 — 主要な不一致

10.44秒の音声 (FLEURS sample_000, q4_0) の転写時間:

| threads | 時間 | RTF |
|---|---|---|
| 1 | 42.8s | 4.1 |
| 4 | 32.5s | 3.1 |
| 8 | 31.0s | 3.0 |

- `sample` プロファイラで確認した結果、実行時間のほぼ100%が `wv2_conv1d`
  (CNN特徴抽出、`src/ops.h`)に費やされている。
- `wv2_conv1d` は5重ネストの素朴なスカラーループで、シングルスレッド。
  最内周に境界チェック分岐があり自動ベクトル化も阻害される。
  README の "Multi-threaded attention" は事実だが、支配的なのは conv 部分。
- fast-math を wav2vec2 ターゲットのみに適用する診断ビルド(ggml除外)でも
  32.5s → 変化なし。fast-math の有無は性能の主因ではない。
- 同一マシンの HF Python (PyTorch CPU fp32, batch=1) は 363.5s の音声を 19.9s で処理
  (RTF 0.055)。**"No Python Required" の代償として、置き換え対象の PyTorch より
  約60倍遅い**。README の RTF 0.32 (20コア Cortex-X925) は、conv1d がシングル
  スレッドである以上、コア数では説明できず、本環境では再現できなかった。

## C5: 量子化誤差 (CER) — 主張はほぼ再現

FLEURS ja_jp test 先頭30サンプル(ブログ/カードは10サンプル)、CLI出力 vs HF fp32 出力の CER:

| 量子化 | 本検証 mean CER | 完全一致サンプル | ブログ/カードの主張 |
|---|---|---|---|
| F16 | **0.22%** | 27/30 | ~0%(カード: 0.20–0.23%)|
| Q8_0 | **0.60%** | 22/30 | ~0%(カード: 0.20–0.23%)|
| Q4_0 | **8.79%** | 3/30(最悪 21.2%)| 8.26% |

- F16 はカード記載値 (0.20–0.23%) とほぼ一致。Q8_0 は 0.60% とやや高いが同オーダー。
- Q4_0 の約8〜9% 劣化も再現。日本語(文字数あたり情報量が大きい)では Q4_0 は実用に不安が残る、
  というブログの示唆と整合する。
- 判定: **量子化誤差に関する主要な数値主張は誠実**。サンプル数3倍でも結論は変わらない。

## 絶対品質と速度(ブログが語っていない部分)

正解文(FLEURS transcription、NFKC正規化・記号除去後)に対する CER:

| システム | CER vs 正解文 |
|---|---|
| HF Python (fp32) | 28.49% |
| cpp F16 | 28.45% |
| cpp Q8_0 | 28.58% |
| cpp Q4_0 | 29.72% |

RTF(バッチ計測、プロセス起動+モデルロード込み、-t 4):

| システム | RTF |
|---|---|
| HF Python CPU fp32 | **0.055** |
| cpp F16 | 3.25 |
| cpp Q8_0 | 3.09 |
| cpp Q4_0 | 3.09 |

- 量子化しても速度がほぼ変わらない(3.25→3.09)のは、ボトルネックが conv1d にあり
  transformer の量子化 matmul が支配的でないため。C8 の分析と整合。
- 元モデル jonatasgrosman/wav2vec2-large-xlsr-53-japanese 自体が FLEURS ja に対して
  CER ~28% と弱く、「非英語では wav2vec2 XLSR が Whisper よりしばしば良い」という
  ブログの前提は少なくとも日本語では疑わしい(本検証では Whisper 比較は未実施)。

## 結論

ブログの**量子化に関する定量的主張(C5, C7)は誠実で再現可能**。GGUF 変換・CLI・
テスト(C3, C4, C6)も実在し動作する。一方で**入口(C1: リンク切れ)と出口(C2: ビルド不能、
C8: 性能が一桁以上未達)の再現性に重大な問題**があり、「whisper.cpp の wav2vec2 版」
と呼ぶには最適化が未成熟。特に macOS では README/ブログの手順どおりにはビルドできず、
実行できても PyTorch CPU より約60倍遅い。

## 手法メモ

- 付属 `scripts/parity_test.py` と同一手法: FLEURS ja_jp test 先頭サンプル、
  CLI出力 vs HF fp32 出力の CER(大文字化のみ)。ブログ/カードは10サンプル、本検証は30サンプル。
- parity_test.py のデータ取得コード (`load_dataset(..., trust_remote_code=True)`) は
  datasets 5.x では動作しない(ローディングスクリプト廃止)。parquet 直読みで代替。
