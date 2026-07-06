# 07 — ASR 無音ハルシネーション

無音・非音声入力に対して ASR（特に Whisper 系）が「ご視聴ありがとうございました」
「チャンネル登録ありがとうございます」等の定型句を出力する現象を、根拠を持って説明するための study。

## アンカー論文

- **Investigation of Whisper ASR Hallucinations Induced by Non-Speech Audio**
  — Barański et al., 2025. https://arxiv.org/abs/2501.11378
- 補助文献: Koenecke et al. (FAccT 2024, arXiv:2402.08021)、Calm-Whisper (Interspeech 2025, arXiv:2505.12969)、
  Frieske & Shi (2024, arXiv:2401.01572)、Whisper 論文 (arXiv:2212.04356)。
  詳細は [papers/notes/references.md](papers/notes/references.md)。

## リサーチクエスチョン

1. モデル（サイズ・系統）ごとにどんな無音ハルシネーションが出るか。
2. 環境音（ノイズの種類・レベル）によって発生率・内容が変わるか。
3. 言語設定によって定型句が変わるか（訓練データ由来仮説の検証）。
4. 推論時パラメータ（VAD, no_speech_threshold 等）でどこまで抑制できるか。

設計の詳細と仮説 H1–H5 は [docs/experiment-design.md](docs/experiment-design.md)。

## 実行方法

```bash
cd experiment
python src/generate_audio.py                  # 合成音声の生成
python src/run_asr.py --preset smoke          # tiny/base での動作確認
python src/run_asr.py --preset sizes          # 本実験1: small〜large-v3 + kotoba (H1-H4)
python src/run_asr.py --preset mitigation     # 本実験2: 緩和策スイープ (H5)
python src/aggregate.py                       # 集計表の出力
```

- 環境: リポジトリルートの `.venv`（Python 3.12, faster-whisper 1.2.1, transformers 5.5, CPU int8 推論）。
- 生ログ: `experiment/results/logs/*.jsonl`、集計: `experiment/results/tables/*.csv`。

## ステータス

- [x] 文献調査・実験設計
- [x] 合成音声生成・実行パイプライン
- [x] スモークテスト（tiny/base）→ [analysis/smoke-findings.md](analysis/smoke-findings.md)
- [x] 本実験（サイズ横断 + kotoba-whisper + 緩和策スイープ）→ [analysis/full-findings.md](analysis/full-findings.md)
- [x] CTC 対照モデル（H4b: wav2vec2 日英とも非空出力 0/76）
- [x] ESC-50 実環境音（VAD は咳・笑いで 40–90% すり抜け）
- [x] 図表化（`experiment/results/figures/`）
- [x] ブログ原稿ドラフト → [blog/drafts/2026-07-02-asr-silence-hallucination-techblog.md](blog/drafts/2026-07-02-asr-silence-hallucination-techblog.md)
- [x] ポッドキャスト構成案 → [podcast/outlines/2026-07-03-asr-silence-hallucination-solo-outline.md](podcast/outlines/2026-07-03-asr-silence-hallucination-solo-outline.md)
- [ ] ブログ公開（Zenn 画像差し替え）
- [x] ポッドキャスト台本 → [podcast/scripts/2026-07-03-asr-silence-hallucination-solo.md](podcast/scripts/2026-07-03-asr-silence-hallucination-solo.md)
- [ ] ポッドキャスト収録・編集
