---
title: "「Python不要でwav2vec2をローカル実行」は本物か — 日本語GGUFで検証したら、量子化の主張は誠実で、ビルドと速度が罠だった"
date: 2026-07-03
tags:
  - ASR
  - wav2vec2
  - GGUF
  - 量子化
  - 音声認識
  - Reproduction
summary: "HFブログ『wav2vec2.cpp — Run Any wav2vec2 Model Locally, No Python Required』の主張を日本語モデルで検証。量子化CER（F16 ~0% / Q4_0 8.26%)はサンプル数3倍でもほぼ再現された一方、リポジトリリンクは404、macOSでは素の手順でビルド不能、実測RTFは主張の一桁上（PyTorch CPUの約60倍遅い）だった記録。"
---

# 「Python不要でwav2vec2をローカル実行」は本物か — 日本語GGUFで検証したら、量子化の主張は誠実で、ビルドと速度が罠だった

whisper.cpp が Whisper に対してやったこと（GGUF 量子化 + 依存なし C++ 推論）を、wav2vec2 に対してやった、というプロジェクトが Hugging Face ブログで公開されました。

https://huggingface.co/blog/PY-AI-Dev/wav2vec2gguf

主張はこうです。

> Whisper ばかり注目されるが、非英語では wav2vec2（特に XLSR-53 系のコミュニティ fine-tune）の方が良いことが多い。それを Python なしでローカル実行できるようにした。日本語を含む 15 言語の GGUF を公開する。

日本語 ASR をローカルで動かす選択肢が増えるなら嬉しい話です。ブログには量子化レベルごとの CER（文字誤り率）の表まで載っていて、日本語モデルは「F16 ≈ 0% / Q8_0 ≈ 0% / Q4_0 8.26%」とのこと。数値主張があるなら検証できます。再現実験シリーズの第 10 回として、日本語モデルで一通り確かめました。

先に結論を書いておきます。

| 主張 | 検証結果 |
|---|---|
| 量子化誤差: F16 ~0% / Q8_0 ~0% / Q4_0 8.26% CER | ✅ **ほぼ再現**（0.22% / 0.60% / 8.79%、サンプル数3倍で） |
| モデルサイズ: Q8_0 で -40%、Q4_0 で -65% | ✅ 再現（636→376→223 MB） |
| 83 個のユニットテストが通る | ✅ 83/83 パス |
| 15 言語の GGUF 公開 | ✅ HF API で 15 リポジトリ確認 |
| リポジトリからクローンしてビルド | ❌ **リンクが 404**、macOS では**素の手順でビルド失敗** |
| 高速 CPU 推論（xlsr-large RTF 0.32） | ❌ **実測 RTF ≈ 3.1**。同一マシンの PyTorch CPU の約 60 倍遅い |

「数値はちゃんとしているのに、入口と出口で転ぶ」という、なかなか教訓的なパターンでした。順に見ていきます。

## 罠 1: リポジトリが 404

ブログ記載のリポジトリ `github.com/liodon-ai/wav2vec2.cpp` は存在しません（404）。GitHub 検索で調べると、実体はブログ著者本人のアカウント側にありました。

https://github.com/py-ai-dev/wav2vec2.cpp

組織アカウント（liodon-ai）に移す予定でリンクだけ先に書いたのか、移転したのかは不明ですが、記事のコマンドをコピペすると最初の `git clone` で失敗します。

## 罠 2: macOS では素の手順でビルドできない

リポジトリの手順どおり cmake を叩くと、ggml のコンパイルでエラーになります。

```
third_party/ggml/src/ggml-cpu/vec.h:1055:2: error:
"some routines in ggml.c require non-finite math arithmetics
 -- pass -fno-finite-math-only to the compiler to fix"
```

原因は wav2vec2.cpp 側の CMakeLists.txt です。デフォルトで `WAV2VEC2_FAST_MATH=ON` になっていて、`add_compile_options(-ffast-math)` がトップレベルで宣言されているため、サブディレクトリとしてビルドされる ggml にも `-ffast-math` が伝播します。ggml は fast-math（無限大や NaN を仮定しない最適化）と相容れない処理を持っているので、明示的な `#error` ガードで弾いてきます。

回避は 1 フラグです。

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release -DWAV2VEC2_FAST_MATH=OFF
cmake --build build -j8
```

これでビルドは通り、付属のユニットテストも 83/83（ops 60 + gguf 23）パスしました。README が謳う「83 unit tests」は正確です。ただしこの回避策はブログにも README にも書かれていません。おそらく作者の環境（Linux + gcc）では通るのでしょうが、Apple clang 16 + この ggml コミット（eced84c8）の組み合わせでは必ず落ちます。

## 検証設計: 作者自身の測定方法に合わせる

ここが今回の検証で一番大事なところです。ブログの CER 表は「正解文に対する CER」ではありません。モデルカードに明記されています。

> CER/WER measured against HF model output (not ground truth) to isolate quantization error

つまり「**GGUF 版の出力が、元の PyTorch 版の出力とどれだけ一致するか**」という量子化誤差の分離測定です。リポジトリに測定スクリプト `scripts/parity_test.py` がそのまま入っていたので、手法をこれに合わせました。

- データ: FLEURS ja_jp test split の先頭サンプル。作者は 10 件、本検証は **30 件**（計 363.5 秒）に拡張
- 参照: `jonatasgrosman/wav2vec2-large-xlsr-53-japanese` を transformers で実行（CPU / fp32 / greedy）
- 比較: `wav2vec2-cli` の出力と参照出力の CER（大文字化のみ、parity_test.py と同一）
- モデル: 公開されている日本語 GGUF 3 種（F16 636MB / Q8_0 376MB / Q4_0 223MB）

なお parity_test.py のデータ取得コードは `load_dataset(..., trust_remote_code=True)` を使っていて、datasets 5.x ではローディングスクリプト廃止により動きません。HF Hub 上の parquet を直接読む形で代替しました。このあたりのスクリプト一式はリポジトリ（記事末尾）にあります。

## 結果 1: 量子化 CER の主張はほぼ完全に再現

FLEURS ja_jp 30 サンプルでの、HF fp32 出力に対する CER:

| 量子化 | 本検証 mean CER | 完全一致 | ブログ/カードの主張 |
|---|---|---|---|
| F16 | **0.22%** | 27/30 | ~0%（カード: 0.20–0.23%） |
| Q8_0 | **0.60%** | 22/30 | ~0%（カード: 0.20–0.23%） |
| Q4_0 | **8.79%** | 3/30（最悪 21.2%） | 8.26% |

F16 はモデルカードの記載値とほぼ一致。Q8_0 はやや高めに出ましたが同オーダー。Q4_0 の「日本語では約 8% 劣化」もそのまま再現されました。サンプル数を 3 倍にしても結論は変わりません。**量子化に関する数値主張は誠実**です。

実際の出力を見ると差が分かりやすいです（sample_000）。

```
HF (fp32): ウィンターネットで敵体的環境構線付いて検作するとおそらく現地企ー業の住所がででくんでしょう
F16      : ウィンターネットで敵体的環境構線付いて検作するとおそらく現地企ー業の住所がででくんでしょう  ← 完全一致
Q4_0     : ミンターレットで敵体的環境光線点て検作するとおそらく現地企業無住所がでてくんでしょう      ← 崩れる
```

F16 は 1 文字違わず一致します。Q4_0 は文頭から「ウィンターネット→ミンターレット」と崩れていて、日本語（1 文字あたりの情報量が大きく、語彙も数千字規模）では 4bit 量子化のロジット摂動が文字置換に直結することが見て取れます。英語モデルの Q4_0 が ~0% で済むのとは対照的で、ブログが Q4_0 の言語依存性に触れているのはフェアな記述です。

## 結果 2: 「高速 CPU 推論」は再現できず — 犯人は conv1d

README には「xlsr-large: 10 秒の音声を ~3.2 秒、RTF 0.32（20 コア ARM）」とあります。Apple M3 Max（16 コア）での実測はこうなりました。

| threads | 10.44 秒の音声の処理時間 | RTF |
|---|---|---|
| 1 | 42.8 秒 | 4.1 |
| 4 | 32.5 秒 | 3.1 |
| 8 | 31.0 秒 | 3.0 |

**主張の一桁上**です。しかもスレッドを 8 倍にして 1.4 倍しか速くなりません。プロファイラ（macOS の `sample`）で覗くと、実行時間の**ほぼ 100% が `wv2_conv1d`**（CNN 特徴抽出）に費やされていました。

コードを見ると理由は明快で、`src/ops.h` の conv1d は 5 重ネストの素朴なスカラーループです。シングルスレッドで、最内周に境界チェック分岐があるため自動ベクトル化も効きません。wav2vec2 の CNN フロントエンドは全体で数十 GMACs あるので、ここがスカラー 1 コアだと 10 秒の音声に数十秒かかる計算になります。

- README の「Multi-threaded attention」「ggml の量子化 matmul」は嘘ではありません。ただし並列化・SIMD 化されているのは transformer 部分だけで、支配項は conv です
- だから**量子化してもほぼ速くならない**（F16: RTF 3.25 → Q4_0: 3.09）。モデルサイズは 1/3 になるのに速度が変わらないのは、ボトルネックが量子化対象外の conv にあるからです
- 「fast-math を切ったせいでは?」という仮説も検証しました。ggml を除いて wav2vec2 側だけに `-ffast-math` を適用する診断ビルドを作りましたが、32.5 秒 → 変化なし。コンパイラフラグの問題ではなく実装の問題です

そして比較対象として一番痛いのがこれです。同じマシン・同じ 30 サンプルを、置き換え対象であるはずの PyTorch（CPU / fp32 / batch=1）で処理すると:

| システム | RTF |
|---|---|
| **PyTorch CPU (transformers)** | **0.055** |
| wav2vec2.cpp F16 | 3.25 |
| wav2vec2.cpp Q8_0 | 3.09 |
| wav2vec2.cpp Q4_0 | 3.09 |

**「No Python Required」の代償は、現状およそ 60 倍の速度です。** PyTorch の conv1d は SIMD + マルチコアに最適化されているので、依存を捨てた分の最適化を自前で埋めない限りこうなります。whisper.cpp が成立しているのは ggml がモデル全体をカバーしているからで、「ggml をリンクしている」ことと「ggml で計算している」ことの間には大きな溝がある、というのが今回の教訓です。

## 補足: そもそも元モデルは日本語 FLEURS にかなり弱い

量子化検証の副産物として、正解文（FLEURS の transcription、NFKC 正規化・記号除去後）に対する CER も測りました。

| システム | CER vs 正解文 |
|---|---|
| PyTorch fp32 | 28.5% |
| cpp F16 | 28.5% |
| cpp Q8_0 | 28.6% |
| cpp Q4_0 | 29.7% |

fp32 の時点で CER 28.5%。例えばこんな出力です（sample_026）。

```
正解: 地殻の厚さは 手前側が約70 km 奥側が約100 kmです
fp32: 近の暑は手前側が約く七十ピロムイドルお午側がやく百キロメードルです
```

`jonatasgrosman/wav2vec2-large-xlsr-53-japanese` は 2021 年の Common Voice 系 fine-tune で、読み上げ音声のドメインでもこの水準です。ブログの前提である「非英語では wav2vec2 XLSR の方が Whisper より良いことが多い」は、少なくとも日本語では成り立っていないと思います（今回 Whisper との直接比較はしていませんが、whisper.cpp + large-v3 系がこの CER を大きく下回るのは既知の水準です）。XLSR-53 の日本語は文字体系の複雑さもあって、コミュニティ fine-tune の中でも弱いグループに入ります。

つまり日本語ユーザーにとっての実用性は「量子化が正しいか」以前に、エンジンの速度と元モデルの品質の 2 段階で厳しい、というのが現状です。

## まとめ

- **信じてよい主張**: 量子化 CER（F16 ≈ 0%、Q4_0 ≈ 8–9%）、圧縮率、ユニットテスト、15 言語の GGUF 公開、CLI 機能。測定方法（HF 出力比、FLEURS 10 件）もカードに明記されていて、追試したらそのとおりの数字が出ました。作者の測定は誠実です
- **信じてはいけない主張**: 記事のリンク（404）、「cmake だけでビルドできる」（macOS では `-DWAV2VEC2_FAST_MATH=OFF` が必須）、「高速 CPU 推論」（conv1d がスカラー 1 コアで、PyTorch CPU の約 60 倍遅い）
- **プロジェクトとしての評価**: 「whisper.cpp の wav2vec2 版」というコンセプト自体は妥当で、GGUF 変換器・パリティテスト・83 個のテストと、検証インフラは丁寧に作られています。conv1d が ggml 化（または NEON + マルチスレッド化)されれば評価は一変するはずで、ロードマップの Metal/CUDA 対応より先にやるべきはそこだと思います
- **日本語ローカル ASR が今ほしい人へ**: 現状は whisper.cpp（または PyTorch のまま wav2vec2/Whisper)が現実解です。wav2vec2.cpp は「単語タイムスタンプがフレーム精度で欲しい」「CTC の forced alignment 用途」など、wav2vec2 でなければならない理由がある場合に、速度を許容して使う段階です

## 制約と注意

- 評価は 30 サンプル（約 6 分）× 1 マシン（M3 Max, macOS 14.7 / Apple clang 16）です。作者環境（20 コア Cortex-X925 + Linux）での RTF 0.32 は同一条件では検証できていません。ただし conv1d がシングルスレッドである以上、コア数では説明がつかず、コンパイラの自動ベクトル化の差を考慮しても開きは大きいと考えています
- RTF はプロセス起動 + モデルロード込みのバッチ計測です（1 クリップあたり数秒程度の上乗せ)。スレッドスケーリング表は単発実行での計測です
- 量子化 CER の「正解」は HF モデル出力であり、ASR としての品質指標ではありません（そこは補足の 28.5% の方)
- Whisper との直接比較、他言語 GGUF の検証はスコープ外です

コードと集計結果はリポジトリの `08_wav2vec2-cpp-gguf-ja/` にあります。データ準備 → HF 参照 → C++ 実行 → 評価まで 4 スクリプトで再実行できます。

## 参考リンク

- 検証対象ブログ: https://huggingface.co/blog/PY-AI-Dev/wav2vec2gguf
- 実際のリポジトリ: https://github.com/py-ai-dev/wav2vec2.cpp
- 日本語 GGUF: https://huggingface.co/liodon-ai/wav2vec2-large-xlsr-53-japanese-GGUF
- 元モデル: https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-japanese
- FLEURS: https://huggingface.co/datasets/google/fleurs
- ggml の fast-math ガードの経緯: https://github.com/ggml-org/llama.cpp/pull/7154
