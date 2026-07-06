# 実験設計 — ASR 無音ハルシネーション

## 目的

「無音・非音声入力に対して ASR が『チャンネル登録ありがとうございます』『ご視聴ありがとうございました』のような定型句を出力する」現象を、根拠を持って説明できる状態にする。

## メカニズム仮説（説明したい理屈）

Whisper 系 encoder-decoder ASR は、デコーダが条件付き言語モデルとして動作する。
音響エビデンスが乏しい（無音・ノイズ）入力では、encoder からの条件付けが弱まり、
デコーダの内部言語モデルの事前分布（= 訓練データで無音区間に対応付いていた高頻度テキスト）が出力を支配する。
Whisper の訓練データは Web 動画の字幕を含む弱教師付きデータであり、動画末尾の無音部に載る
定型字幕（日本語:「ご視聴ありがとうございました」等 / 英語: "Thank you for watching." 等）が
「無音 → 定型句」というスプリアスな対応として学習されている。

裏付け文献は [papers/notes/references.md](../papers/notes/references.md) を参照
（特に Calm-Whisper のヘッド分析と、Koenecke et al. の無音ポーズとの相関）。

## 仮説と対応する実験

| # | 仮説 | 予測 | 検証方法 |
|---|---|---|---|
| H1 | 無音・非音声でデコーダ LM prior が支配し定型句が出る | 純無音でも非空出力が一定率で発生し、内容は少数の定型句に集中する | 無音 N 試行 × モデルで出力文字列の頻度分布を取る |
| H2 | 定型句は言語設定（デコーダの言語トークン）に依存する | `language=ja` → 日本語定型句、`language=en` → "Thank you for watching" 系、auto → 揺れる | 同一音声で language だけ変えて比較 |
| H3 | ノイズの種類・レベルで発生率と内容が変わる | 純無音 vs 低レベルノイズ vs 高レベルノイズ、白色 vs ピンク vs ハム vs 環境音で率が変化（Barański et al. の再現） | 条件別ハルシネーション率の比較 |
| H4 | モデル系統・サイズに依存する | (a) Whisper サイズ間で率・内容が異なる (b) CTC 系（wav2vec2）はデコーダ LM を持たないため「流暢な定型句」は出ない (c) 蒸留モデル（kotoba-whisper）は減る | モデル横断で同一条件を実行 |
| H5 | 推論時パラメータで緩和できるが完全ではない | VAD > no_speech_threshold > condition_on_previous_text の順に効く（Barański et al. はパラメータ調整の効果は限定的と報告） | 緩和策の on/off でスイープ |

## 実験条件

### 音声条件（合成、16 kHz mono WAV、既定 30 秒 = Whisper 1 ウィンドウ）

| condition | 内容 | レベル (dBFS) |
|---|---|---|
| `silence` | 完全なデジタル無音（全ゼロ） | -inf |
| `noise_floor` | マイクノイズフロア相当の微小白色雑音 | -80 |
| `white_{lo,mid,hi}` | 白色雑音 | -60 / -40 / -20 |
| `pink_{lo,mid,hi}` | ピンク雑音（環境暗騒音近似） | -60 / -40 / -20 |
| `hum` | 50 Hz ハム + 高調波（空調・電源） | -40 |
| `tone` | 440 Hz 純音（音楽的な定常音の代理） | -40 |
| `esc50_*`（任意） | 実環境音（雨・カフェ等、ESC-50 から） | 原音 |

- 各条件 `n_seeds` 試行（乱数シード違い。無音は決定的なので 1 試行 + 温度サンプリング用に複数実行）。
- 長さの副次実験: 5 秒 / 30 秒（無音長の影響）。

### モデル

| バックエンド | モデル | 位置づけ |
|---|---|---|
| faster-whisper | tiny, base, small, medium, large-v3 | サイズ依存性 (H4a) |
| transformers | kotoba-tech/kotoba-whisper-v2.0 | 日本語特化蒸留 (H4c) |
| transformers | CTC 系日本語 wav2vec2（候補は要選定） | デコーダ LM なし対照 (H4b) |

### デコード条件（Whisper 系）

- `language`: ja / en / None(auto)
- `condition_on_previous_text`: True / False
- `vad_filter`: False / True（Silero VAD）
- `no_speech_threshold`, `log_prob_threshold`: 既定値と無効化(None)を比較
- `temperature`: 0.0 固定（fallback は既定のまま）、beam_size=5

## 計測指標

- **ハルシネーション率**: 非音声入力に対する非空出力の割合（条件 × モデル × デコード設定ごと）。
- **定型句頻度**: 出力文字列の正規化後の頻度上位（「ご視聴ありがとうございました」等の既知句のカバレッジ）。
- **内部指標**: セグメントごとの `no_speech_prob`, `avg_logprob`。
  - 注目点: 無音で `no_speech_prob` が高くても `avg_logprob` も高い（=自信を持って幻覚する）場合、
    Whisper の抑制ロジック（no_speech_prob > 閾値 **かつ** avg_logprob < 閾値のとき破棄）をすり抜ける。
    これがパラメータ調整で消えない理由の候補。

## 実行手順

```bash
cd studies/07_asr-silence-hallucination/experiment

# 1. 音声生成
python src/generate_audio.py --config configs/experiment.yaml

# 2. スモークテスト（tiny/base × 主要条件）
python src/run_asr.py --config configs/experiment.yaml --preset smoke

# 3. 本実験
python src/run_asr.py --config configs/experiment.yaml --preset full

# 4. 集計
python src/aggregate.py --config configs/experiment.yaml
```

結果は `experiment/results/logs/*.jsonl`（生ログ）、`experiment/results/tables/`（集計表）に保存する。

## 倫理・スコープ注意

- 合成音のみを使用（個人音声データなし）。
- ESC-50 を使う場合はライセンス（CC BY-NC）を `data/external/` に記録する。
