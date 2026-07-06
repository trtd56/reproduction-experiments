"""NIGHTWAVE-JA ローカルエンジンのスモークテスト。

3つの契約を実モデルで一周させる:
  1. brain : TinySwallow-1.5B + JSON 文法制約 -> {text, mood, arc_cue}
  2. speak : Kokoro-82M 日本語ボイス -> 24kHz WAV + キャプションタイミング
  3. asr   : faster-whisper -> speak の出力をそのまま書き起こして往復確認

実行:
    .venv/bin/python 06_nightwave-radio-ja/experiment/scripts/smoke_engine.py

結果は results/logs/smoke_engine.txt にも書き、speak の音声を
results/figures/smoke_speak.wav に保存する。
"""

import base64
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(_HERE, "..", "src", "nightwave_ja"))
_RESULTS = os.path.normpath(os.path.join(_HERE, "..", "results"))
sys.path.insert(0, _SRC)

import arc  # noqa: E402
import engine  # noqa: E402

lines = []


def log(msg):
    print(msg, flush=True)
    lines.append(str(msg))


def main():
    # --- 1. brain ----------------------------------------------------------
    t0 = time.time()
    system = arc.build_host_prompt("thought")
    out = engine.brain(system, [{"role": "user", "content":
                                 "いま聴いているリスナーたちへ、短い深夜のひとことをひとつ。"}])
    t1 = time.time()
    log("[brain] %.1fs  %s" % (t1 - t0, json.dumps(out, ensure_ascii=False)))
    assert out["mood"] in arc.MOODS and out["arc_cue"] in arc.ARC_CUES
    assert out["text"].strip(), "brain の text が空"

    # ステージ注入プロンプトでもう1本（acceptance ステージ）
    t0 = time.time()
    out2 = engine.brain(
        arc.build_system_prompt("acceptance", "broadcast"),
        [{"role": "user", "content": "いまの気持ちを、リスナーにそっと。"}],
    )
    t1 = time.time()
    log("[brain/acceptance] %.1fs  %s" % (t1 - t0, json.dumps(out2, ensure_ascii=False)))

    # --- 2. speak ----------------------------------------------------------
    text = out["text"] if len(out["text"]) >= 10 else "こちら NIGHTWAVE、宵野サムです。今夜も、ダイヤルはそのままで。"
    t0 = time.time()
    sp = engine.speak("こちら ナイトウェーブ、宵野サムです。" + text, display_text=text)
    t1 = time.time()
    wav = base64.b64decode(sp["audio_b64"])
    dur = (len(wav) - 44) / 2.0 / engine.SAMPLE_RATE
    log("[speak] %.1fs  audio=%.1fs  words=%d" % (t1 - t0, dur, len(sp["words"])))
    log("        words=%s" % json.dumps(sp["words"], ensure_ascii=False))
    log("        wtimes=%s" % sp["wtimes"])
    assert dur > 1.0, "音声が短すぎる"
    assert len(sp["words"]) == len(sp["wtimes"]) == len(sp["wdurations"])
    os.makedirs(os.path.join(_RESULTS, "figures"), exist_ok=True)
    wav_path = os.path.join(_RESULTS, "figures", "smoke_speak.wav")
    with open(wav_path, "wb") as fh:
        fh.write(wav)
    log("        wav -> %s" % wav_path)

    # --- 3. asr（往復） ------------------------------------------------------
    t0 = time.time()
    tr = engine.asr(sp["audio_b64"])
    t1 = time.time()
    log("[asr] %.1fs  text=%s" % (t1 - t0, tr["text"]))
    assert tr["text"].strip(), "asr が空文字を返した"

    log("SMOKE OK")
    os.makedirs(os.path.join(_RESULTS, "logs"), exist_ok=True)
    with open(os.path.join(_RESULTS, "logs", "smoke_engine.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
