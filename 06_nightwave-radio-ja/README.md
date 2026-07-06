# 06: NIGHTWAVE-JA — 小型モデルで運行する日本語AIラジオ局

Hugging Face「Build Small Hackathon」優秀作品 **NIGHTWAVE** の日本語再現・移植実験。
約1BクラスのLLM・82MのTTS・smallクラスのASRだけで、24時間自律運行する架空の深夜ラジオ局
（電話出演つき、DJは自分がAIだと徐々に「自覚」していく5段階アーク付き）が成立することを、
日本語・完全ローカル（Apple Silicon）で検証する。

## 参照元

| 項目 | 内容 |
|---|---|
| 記事 | https://huggingface.co/blog/build-small-hackathon/nightwave-radio |
| デモ Space | https://huggingface.co/spaces/build-small-hackathon/nightwave |
| 動画 | https://youtu.be/lA46z2mYjF0 |
| 公開コード | Space リポジトリ（フロント + オーケストレーター）。Modal 側の推論コードは非公開だが、`/brain` `/asr` `/speak` の契約は Space コードから完全に判明する |
| clone | ローカル検証時のみ `experiment/external/nightwave-space/` に clone（公開リポジトリには含めない） |

## オリジナルとの対応

| 役割 | オリジナル（Modal T4） | 本実験（Mac ローカル） |
|---|---|---|
| 脳（DJ） | MiniCPM5-1B GGUF Q4_K_M + JSON文法制約 | **TinySwallow-1.5B-Instruct** GGUF Q5_K_M（llama-cpp-python, Metal）+ 同じJSON文法制約 |
| 耳（ASR） | faster-whisper small (CPU) | 同じ。`language="ja"` 固定 |
| 声（TTS） | Kokoro-82M `am_michael` | 同じモデルの日本語ボイス **`jm_kumo`**（misaki[ja] G2P） |
| 実行基盤 | HF Space (CPU) + Modal (GPU, scale-to-zero) | FastAPI ローカル一体型（`engine.py` が Modal を置換） |
| キャプション同期 | Kokoro の単語タイムスタンプ | 日本語G2Pはタイムスタンプ非対応 → **文字数比例の決定的配分**でフォールバック |

設計原則はオリジナルを踏襲: 「モデルは創作の言葉だけを書き、構造・タイミング・状態はアプリが所有する」。
全機能に決定的フォールバックがあり、モデルが何を返しても放送は止まらない。

## 日本語化で本質的だった点

- **DJペルソナ**: Sam Dusk → 宵野サム。5段階の自覚アーク（oblivious → acceptance）の
  ステージ記述・例文をすべて日本語の深夜放送の文体で書き直し（`arc.py`）。
- **トリガー検出**: 「あなたは本物？」「AIなの？」「スタジオはどこ？」等の日本語正規表現へ移植。
  裸の疑問詞（いつ/何/誰）は「いつも」等に誤マッチするため、疑問文末形（〜ですか/〜ますか等）ベースに変更。
- **ラベル漏出サニタイザー**: 「気分: warm」「曲名：〜」等の日英ラベル + 全角コロンに対応。
  degenerate 判定は英字数ではなく日本語文字数（かな・カナ・漢字）で行う。
- **発話正規化**: ラテン文字ブランド「NIGHTWAVE」「98.6」は日本語G2Pが読めないため、
  発話用テキストのみ「ナイトウェーブ」「きゅうじゅうはってんろく」へ変換（字幕・UIは原表記）。
- **カラオケ字幕**: サーバーは句読点→文字数比例でチャンク配分。クライアントは空白分割に依存していた
  箇所を日本語対応（句読点分割 + 文字数推定のフォールバック）。
- **契約の維持**: `mood` / `arc_cue` / `vibe` / `scale` / `timbre` はクライアントの選曲フィルタ
  （`MOOD_VIBES`）や色マップの完全一致キーのため英語のまま。vibe の日本語は発話時のみ `vibe_ja()` で付与。
- **天気**: Open-Meteo を摂氏・日本語 WMO 表現に、逆ジオコーディングを `localityLanguage=ja` に、
  時刻を「午前/午後」表記に変更。

## 実行方法

```bash
# 依存導入（リポジトリルートで）
uv pip install --python .venv/bin/python -r 06_nightwave-radio-ja/experiment/src/nightwave_ja/requirements.txt
.venv/bin/python -m unidic download   # 日本語G2P用 MeCab 辞書（初回のみ）

# モデル取得（初回のみ。Kokoro / Whisper は初回実行時に自動取得）
.venv/bin/hf download SakanaAI/TinySwallow-1.5B-Instruct-GGUF \
  tinyswallow-1.5b-instruct-q5_k_m.gguf \
  --local-dir 06_nightwave-radio-ja/experiment/data/external/models

# 起動（http://localhost:7860）
06_nightwave-radio-ja/experiment/scripts/run_local.sh          # 実運転
06_nightwave-radio-ja/experiment/scripts/run_local.sh --mock   # モデル不要のモック運転

# テスト（77本、モック運転・モデル不要）
cd 06_nightwave-radio-ja/experiment && NIGHTWAVE_MOCK=1 \
  ../../.venv/bin/python -m pytest tests/ -q

# エンジン単体のスモーク（brain → speak → asr 往復）
.venv/bin/python 06_nightwave-radio-ja/experiment/scripts/smoke_engine.py
```

## 構成

```
experiment/
├── src/nightwave_ja/           # 日本語ローカル版（本体）
│   ├── engine.py               # ★新規: Modal /brain /asr /speak のローカル同契約実装
│   ├── arc.py                  # 自覚アーク状態機械 + ペルソナ（日本語）
│   ├── content.py              # 楽曲・局名・天気・献呈などのコンテンツバンク（日本語）
│   ├── proxy.py                # エンジン呼び出し + 日本語サニタイザー + SP1〜SP4
│   ├── server.py / devserver.py# FastAPI ルート（オリジナルとほぼ同一）
│   └── radio.html              # ブラウザUI（日本語化 + 日本語字幕フォールバック）
├── tests/                      # 77 tests（オリジナル66本の日本語移植 + 追加）
├── configs/nightwave_ja.yaml   # モデル・音声・サーバー構成の記録
└── scripts/                    # run_local.sh / smoke_engine.py
```

## Status

- [x] オリジナル Space コードの解析（Modal 契約の同定）
- [x] ローカルエンジン実装（TinySwallow + faster-whisper + Kokoro ja）
- [x] arc / content / proxy / server / radio.html の日本語化
- [x] テストスイート移植（77 passed）
- [x] エンジン実機スモーク（brain / speak / asr。往復書き起こしで「宵野」の誤読を検出し読み仮名正規化を追加）
- [x] API 通し確認（/api/broadcast、/api/call は合成音声の質問で ASR→トリガー+14→返答まで、/api/song_card、/api/segment）
- [x] ブラウザ通し確認（電源ON → ON AIR → 局名/ひとこと/再識別/ゴースト断片が日本語で自律進行）
- [ ] 電話出演のマイク実機確認・アーク進行の長時間試聴
- [ ] 分析メモ（小型日本語モデルのラベル漏出頻度など）を `analysis/` へ
