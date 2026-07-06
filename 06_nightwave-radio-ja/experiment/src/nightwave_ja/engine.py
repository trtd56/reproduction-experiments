"""NIGHTWAVE-JA ローカル推論エンジン。

オリジナル（build-small-hackathon/nightwave）が Modal 上の GPU コンテナに
置いていた 3 エンドポイントを、Mac ローカルで完結する同一契約の関数として
実装する:

  brain(system, messages) -> {"text", "mood", "arc_cue"}
      TinySwallow-1.5B-Instruct (GGUF) を llama-cpp-python で実行。
      JSON スキーマ由来の文法制約（GBNF）で出力形状を強制する。
  asr(audio_b64)          -> {"text"}
      faster-whisper small（CPU, int8）で日本語書き起こし。
  speak(text, voice)      -> {"audio_b64", "words", "wtimes", "wdurations"}
      Kokoro-82M の日本語ボイス（既定 jm_kumo）。24kHz mono PCM16 WAV を
      base64 で返す。

Kokoro の日本語 G2P（misaki[ja]）は英語版と違いトークン単位のタイムスタンプを
返さないため、キャプション同期は「文字数比例の決定的配分」でフォールバック
する（オリジナルの設計原則どおり: すべての機能に決定的フォールバック）。

重量級ライブラリはすべて遅延ロード。モジュール import は軽く、モック運転
（NIGHTWAVE_MOCK=1）では何もロードされない。
"""

import base64
import io
import json
import os
import re
import struct
import threading
import wave
from typing import Any, Dict, List, Optional, Tuple

import arc

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_GGUF = os.path.normpath(os.path.join(
    _HERE, "..", "..", "data", "external", "models",
    "tinyswallow-1.5b-instruct-q5_k_m.gguf",
))

# 環境変数での上書き（configs/nightwave_ja.yaml と対応）
GGUF_PATH = os.environ.get("NIGHTWAVE_JA_GGUF", _DEFAULT_GGUF)
TTS_VOICE = os.environ.get("NIGHTWAVE_JA_VOICE", arc.VOICE)
WHISPER_MODEL = os.environ.get("NIGHTWAVE_JA_WHISPER", "small")

SAMPLE_RATE = 24000  # Kokoro 出力 / 契約どおり 24kHz

# ---------------------------------------------------------------------------
# 遅延シングルトン
# ---------------------------------------------------------------------------
_llm = None
_whisper = None
_tts = None
_llm_lock = threading.Lock()
_whisper_lock = threading.Lock()
_tts_lock = threading.Lock()


def _get_llm():
    global _llm
    if _llm is None:
        with _llm_lock:
            if _llm is None:
                from llama_cpp import Llama
                _llm = Llama(
                    model_path=GGUF_PATH,
                    n_ctx=4096,
                    n_gpu_layers=-1,  # Metal に全レイヤーをオフロード
                    verbose=False,
                )
    return _llm


def _get_whisper():
    global _whisper
    if _whisper is None:
        with _whisper_lock:
            if _whisper is None:
                from faster_whisper import WhisperModel
                _whisper = WhisperModel(
                    WHISPER_MODEL, device="cpu", compute_type="int8"
                )
    return _whisper


def _get_tts():
    global _tts
    if _tts is None:
        with _tts_lock:
            if _tts is None:
                from kokoro import KPipeline
                _tts = KPipeline(lang_code="j", repo_id="hexgrad/Kokoro-82M")
    return _tts


def preload() -> None:
    """3モデルすべてを先にロードする（起動ウォームアップ用）。"""
    _get_llm()
    _get_whisper()
    _get_tts()


# ---------------------------------------------------------------------------
# BRAIN: JSON スキーマ制約付きチャット補完
# ---------------------------------------------------------------------------
_BRAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "maxLength": 300},
        "mood": {"type": "string", "enum": list(arc.MOODS)},
        "arc_cue": {"type": "string", "enum": list(arc.ARC_CUES)},
    },
    "required": ["text", "mood", "arc_cue"],
    "additionalProperties": False,
}


def brain(system: str, messages: List[Dict[str, str]],
          temperature: float = 0.8) -> Dict[str, Any]:
    """1ターン生成。JSON 文法制約により常にパース可能な形で返る。"""
    llm = _get_llm()
    msgs = [{"role": "system", "content": system}] + list(messages)
    with _llm_lock:
        out = llm.create_chat_completion(
            messages=msgs,
            response_format={"type": "json_object", "schema": _BRAIN_SCHEMA},
            temperature=temperature,
            max_tokens=256,
        )
    raw = out["choices"][0]["message"]["content"] or "{}"
    try:
        obj = json.loads(raw)
    except ValueError:
        obj = {}
    mood = obj.get("mood")
    cue = obj.get("arc_cue")
    return {
        "text": str(obj.get("text", "") or ""),
        "mood": mood if mood in arc.MOODS else "warm",
        "arc_cue": cue if cue in arc.ARC_CUES else "none",
    }


# ---------------------------------------------------------------------------
# ASR: faster-whisper（日本語固定）
# ---------------------------------------------------------------------------
def asr(audio_b64: str) -> Dict[str, Any]:
    """ブラウザ録音（webm/opus 等）の base64 を日本語で書き起こす。"""
    model = _get_whisper()
    data = base64.b64decode(audio_b64 or "")
    if not data:
        return {"text": ""}
    buf = io.BytesIO(data)
    with _whisper_lock:
        segments, _info = model.transcribe(
            buf, language="ja", beam_size=5, vad_filter=True
        )
        text = "".join(s.text for s in segments).strip()
    return {"text": text}


# ---------------------------------------------------------------------------
# SPEAK: Kokoro-82M 日本語ボイス + 決定的キャプション配分
# ---------------------------------------------------------------------------
_CAPTION_SPLIT_RE = re.compile(r"([、。．，！？!?…・\n]+)")
_MAX_CHUNK = 6  # 句読点間がこれより長ければさらに刻む（カラオケ表示の粒度）


def _caption_chunks(text: str) -> List[str]:
    """表示テキストをカラオケ用チャンクに分割する（決定的）。

    まず句読点で区切り、句読点は直前のチャンクに吸収。長い区間は
    _MAX_CHUNK 文字ごとに刻む。空白は保持しない（日本語前提）。
    """
    parts = [p for p in _CAPTION_SPLIT_RE.split(text or "") if p]
    merged: List[str] = []
    for p in parts:
        if _CAPTION_SPLIT_RE.fullmatch(p) and merged:
            merged[-1] += p
        else:
            merged.append(p)
    chunks: List[str] = []
    for m in merged:
        m = m.strip()
        while len(m) > _MAX_CHUNK * 2:
            chunks.append(m[:_MAX_CHUNK])
            m = m[_MAX_CHUNK:]
        if m:
            chunks.append(m)
    return chunks


def _caption_timing(text: str, duration: float) -> Tuple[List[str], List[float], List[float]]:
    """チャンクへ音声長を文字数比例で配分する。"""
    chunks = _caption_chunks(text)
    if not chunks or duration <= 0:
        return [], [], []
    weights = [max(1, len(c)) for c in chunks]
    total = float(sum(weights))
    words: List[str] = []
    wtimes: List[float] = []
    wdurations: List[float] = []
    t = 0.0
    for c, w in zip(chunks, weights):
        d = duration * (w / total)
        words.append(c)
        wtimes.append(round(t, 3))
        wdurations.append(round(d, 3))
        t += d
    return words, wtimes, wdurations


def _wav_b64(samples: "Any", rate: int = SAMPLE_RATE) -> str:
    """float32 [-1,1] ndarray -> base64 の mono PCM16 WAV（data: プレフィックスなし）。"""
    import numpy as np
    x = np.asarray(samples, dtype="float32")
    x = np.clip(x, -1.0, 1.0)
    pcm = (x * 32767.0).astype("<i2")
    buf = io.BytesIO()
    wf = wave.open(buf, "wb")
    try:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
    finally:
        wf.close()
    return base64.b64encode(buf.getvalue()).decode("ascii")


def speak(text: str, voice: Optional[str] = None,
          display_text: Optional[str] = None) -> Dict[str, Any]:
    """テキストを合成する。キャプションは display_text（省略時は text）から作る。

    契約: {"audio_b64": <24kHz mono PCM16 WAV の base64>, "words", "wtimes",
    "wdurations"}。合成できる音声が無ければ短い無音を返す（放送は止めない）。
    """
    import numpy as np
    pipe = _get_tts()
    v = voice or TTS_VOICE
    pieces: List[Any] = []
    with _tts_lock:
        for result in pipe(text or "", voice=v):
            if result.audio is not None:
                pieces.append(np.asarray(result.audio, dtype="float32"))
    if pieces:
        audio = np.concatenate(pieces)
    else:
        audio = np.zeros(int(0.4 * SAMPLE_RATE), dtype="float32")
    duration = len(audio) / float(SAMPLE_RATE)
    words, wtimes, wdurations = _caption_timing(display_text or text or "", duration)
    return {
        "audio_b64": _wav_b64(audio),
        "words": words,
        "wtimes": wtimes,
        "wdurations": wdurations,
    }
