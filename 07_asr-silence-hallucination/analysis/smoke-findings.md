# スモークテスト所見（2026-07-02）

対象: faster-whisper tiny / base（CPU int8, beam=5, temp=0, 既定パラメータ）
条件: silence, noise_floor(-80dBFS), white_mid(-40), pink_mid(-40), hum × 言語 ja/en/auto × 各5シード（決定的条件は1）
ログ: `experiment/results/logs/smoke_20260702-061138.jsonl`（102行）
集計: `experiment/results/tables/hallucination_rate.csv`, `phrase_frequency.csv`

## 結果サマリ

- **ハルシネーション率 88/102 (86%)**。純無音では tiny/base × 全言語で 100%。
- **「ご視聴ありがとうございました」を直接再現**: tiny + `language=ja` で純無音 1/1、
  ノイズフロア(-80dBFS) 4/5 シードで出力。
- **言語依存 (H2 支持)**: まったく同じ無音に対して
  - `language=ja` → 「ご視聴ありがとうございました」(tiny) / 日本語の反復ループ (base)
  - `language=en` / auto → "you" / "You"（英語圏で有名な無音ハルシネーション）
  - auto + ノイズではウェールズ語風 "Mae'n gweithio'r..." 等も出現（言語トークンで prior が切り替わる）。
- **モデル依存 (H4a の兆候)**: tiny は定型句、base は「スタッフのアイスクリームを見つけたことができます」×14回のような**反復ループ型**が優勢。ハルシネーションの「型」がモデルで異なる。
- **条件依存 (H3 の兆候)**: hum(50Hz) は base の en/auto で率 0.0 と、条件によって明確に変わる。
  白色・ピンク -40dBFS では数字列・音写列（"1-2-3-4-4-4..."）が増える。

## メカニズムの直接証拠（重要）

無音で「ご視聴ありがとうございました」が出た行の内部指標:

| 指標 | 値 | 意味 |
|---|---|---|
| `no_speech_prob` | 0.93–0.95 | モデルは「音声なし」とほぼ確信している |
| `avg_logprob` | -0.85〜-0.98 | それでも生成テキストには自信がある |

Whisper がセグメントを破棄するのは **`no_speech_prob > 0.6` かつ `avg_logprob < -1.0`** のときのみ。
無音時のデコーダは内部言語モデルの prior（訓練字幕で無音に対応付いた定型句）に従って
「流暢で自信のある」テキストを生成するため avg_logprob が閾値を下回らず、抑制をすり抜ける。
これが「パラメータ調整では消えにくい」（Barański et al. 2025 の報告）ことの実測による説明になる。

## 次のステップ

1. `--preset full`: small/medium/large-v3 + kotoba-whisper-v2.0 でサイズ・蒸留依存性 (H4a/H4c)。
2. 緩和策スイープ（vad / no_condition / no_suppress バリアント）で H5。
3. CTC 対照モデル（H4b）と ESC-50 実環境音の追加。
