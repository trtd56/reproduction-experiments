# 参考文献ノート — ASR 無音ハルシネーション

## 主要論文

### 1. Barański et al. 2025 — Investigation of Whisper ASR Hallucinations Induced by Non-Speech Audio
- arXiv: https://arxiv.org/abs/2501.11378 (AGH University of Krakow)
- 本 study の再現アンカー論文。
- 内容: 非音声オーディオ（無音・ノイズ・環境音）を Whisper に入力し、誘発されるハルシネーションを体系的に調査。
  - 無音での augmentation でもハルシネーションが誘発されることを確認。
  - `hallucination_silence_threshold`（一定以上の無音をスキップするパラメータ）や beam size の調整は**限定的な効果しかない**と報告。
  - ノイズ・環境音のカテゴリによってハルシネーションの傾向が変わる。

### 2. Koenecke et al. 2024 — Careless Whisper: Speech-to-Text Hallucination Harms (FAccT 2024)
- arXiv: https://arxiv.org/abs/2402.08021 / ACM: https://dl.acm.org/doi/10.1145/3630106.3658996
- 内容: Whisper API の書き起こしの約 1% に丸ごと捏造されたフレーズ・文が含まれる。
  - ハルシネーションの 38% は暴力表現・誤った関連付けなど明示的な害を含む。
  - 失語症話者（発話間の無音ポーズが長い）で対照群よりハルシネーション率が有意に高い
    → **無音・非流暢区間がハルシネーションの引き金**という因果的示唆。

### 3. Wang et al. 2025 — Calm-Whisper: Reduce Whisper Hallucination On Non-Speech By Calming Crazy Heads Down (Interspeech 2025)
- arXiv: https://arxiv.org/abs/2505.12969
- 内容: 非音声区間のハルシネーションの大部分が、デコーダ最終層近くの**少数の self-attention ヘッド**に起因することを特定し、それらを選択的に fine-tune して抑制。
  - 「デコーダ側の内部言語モデルが音響エビデンスなしに生成を駆動する」というメカニズム仮説の直接的な証拠。

### 4. Frieske & Shi 2024 — Hallucinations in Neural Automatic Speech Recognition
- arXiv: https://arxiv.org/abs/2401.01572
- 内容: ASR におけるハルシネーションを「参照とは意味的に無関係だが流暢な出力」と定義し、通常の認識誤りと区別。ノイズ注入でハルシネーションしやすいモデルを識別する手法を提案。

### 5. Radford et al. 2022 — Robust Speech Recognition via Large-Scale Weak Supervision (Whisper 論文)
- arXiv: https://arxiv.org/abs/2212.04356
- 本現象の「訓練データ側」の根拠:
  - 68 万時間の Web 由来の弱教師付きデータ（動画字幕とオーディオのペアを含む）で学習。
  - 字幕データには、実際の発話と対応しないテキスト（動画末尾の無音部に載る「ご視聴ありがとうございました」等の定型字幕、クレジット、字幕投稿者名）が混入する。
  - モデルは encoder-decoder seq2seq で、デコーダは強力な条件付き言語モデルとして振る舞う。

## 日本語圏での既知の観察（一次情報・事例）

- 無音区間で「ご視聴ありがとうございました」が出る現象は日本語圏で広く報告されている。
  - 例: [amical Issue #71](https://github.com/amicalhq/amical/issues/71)（英語話者環境でも日本語の定型句が出る）、[Togetter まとめ](https://togetter.com/li/2519693)、[note 記事](https://note.com/shinao39/n/n561acbd19f0c)
- 通説: YouTube 動画の末尾無音部に「ご視聴ありがとうございました」という字幕を載せる慣習があり、「無音 ≒ この字幕」という対応が弱教師付きデータ経由で学習された。
  - 英語では "Thank you for watching."、"Thanks for watching!" が同型の現象として報告されている。
  - この「言語設定によって定型句が変わる」ことは訓練データ由来仮説と整合的 → 本実験の検証対象 (H2)。

## 実務上の緩和策（本実験で効果を定量化する対象）

- VAD（Silero-VAD 等）で非音声区間を Whisper に渡さない（faster-whisper `vad_filter=True`）。
- `no_speech_threshold` / `logprob_threshold` / `condition_on_previous_text=False` の調整。
- 既知の定型句ブラックリストによる後処理フィルタ。
- 蒸留モデル（kotoba-whisper, distil-whisper）はハルシネーションが減るという報告あり（要検証）。
