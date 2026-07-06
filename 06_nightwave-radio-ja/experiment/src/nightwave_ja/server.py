"""NIGHTWAVE-JA オーケストレーターの FastAPI アプリファクトリ。

ブラウザのラジオが呼ぶ同一オリジンのルートを公開する:
  POST /api/broadcast {stage, meter, topic?}
  POST /api/call      {stage, meter, audio_b64}
  POST /api/seek      {meter}

すべての呼び出しは try/except で包み、エンジンの不調（初回ロードの遅さ等）が
ラジオを 500 にすることは決してない -- ステージに合った canned ラインと短い
無音 WAV へ退避する。ラジオは決して沈黙しない。

radio_iframe_html() も提供する: radio.html をディスクから読み、Gradio Blocks
ページへ埋め込むためのサンドボックス付き <iframe srcdoc=...> に包む
（gr.HTML は <script> を実行しないため、ラジオは iframe 内に住む必要がある）。
"""

import html
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import arc
import content
import proxy

_HERE = os.path.dirname(os.path.abspath(__file__))
_RADIO_HTML_PATH = os.path.join(_HERE, "radio.html")


# ---------------------------------------------------------------------------
# リクエストモデル
# ---------------------------------------------------------------------------
class BroadcastReq(BaseModel):
    stage: str
    meter: int
    topic: Optional[str] = None


class CallReq(BaseModel):
    stage: str
    meter: int
    audio_b64: str


class SeekReq(BaseModel):
    meter: int


class SegmentReq(BaseModel):
    kind: str  # station_id | thought | weather | local_weather | dedication | song_intro | rejoin | caller_intro
    ctx: Optional[Dict[str, Any]] = None


class LocaleReq(BaseModel):
    lat: float
    lon: float


class SongCardReq(BaseModel):
    ctx: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 品のよいフォールバック（ラジオを決して沈黙させない）
# ---------------------------------------------------------------------------
_FALLBACK_LINES = [
    "宵野サムです -- いま電波が少しつまずきましたが、私はまだここにいますよ。"
    "次の一曲を、そのまま流しましょう。",
    "宵野サムです。回線が一瞬ざらつきましたね。気にしないで、もう少し"
    "一緒にいてください。",
    "引き続き、NIGHTWAVE の宵野サムです。放送に小さな段差がありました -- "
    "夜がならしてくれないものは、ありません。",
]


def _fallback_payload(stage: str = "", include_caller: bool = False) -> Dict[str, Any]:
    import random
    payload: Dict[str, Any] = {
        "text": random.choice(_FALLBACK_LINES),
        "mood": "warm",
        "arc_cue": "none",
        "audio_b64": proxy._silent_wav_b64(),
        "words": [],
        "wtimes": [],
        "wdurations": [],
    }
    if include_caller:
        payload["caller_text"] = ""
        payload["meter_delta"] = 0
        payload["memory_patch"] = None
        payload["queue_dedication"] = False
    return payload


# ---------------------------------------------------------------------------
# ラジオの iframe 埋め込み（Gradio Blocks ページ用）
# ---------------------------------------------------------------------------
def radio_iframe_html() -> str:
    """radio.html を読み、サンドボックス付き iframe srcdoc に包んで返す。"""
    with open(_RADIO_HTML_PATH, "r", encoding="utf-8") as fh:
        doc = fh.read()
    escaped = html.escape(doc, quote=True)
    return (
        '<iframe srcdoc="' + escaped + '" '
        'width="100%" height="860" '
        'allow="microphone; autoplay" '
        'style="border:0;display:block" '
        'referrerpolicy="no-referrer"></iframe>'
    )


def read_radio_html() -> str:
    """生のラジオドキュメントを返す（devserver がトップレベルで配信する用）。"""
    with open(_RADIO_HTML_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# アプリファクトリ
# ---------------------------------------------------------------------------
def create_api() -> FastAPI:
    api = FastAPI(title="NIGHTWAVE-JA", docs_url=None, redoc_url=None)

    @api.post("/api/broadcast")
    def api_broadcast(req: BroadcastReq):
        stage = arc.meter_to_stage(req.meter)
        try:
            return proxy.broadcast_turn(stage, req.meter, req.topic)
        except Exception:
            return JSONResponse(_fallback_payload(stage))

    @api.post("/api/call")
    def api_call(req: CallReq):
        stage = arc.meter_to_stage(req.meter)
        try:
            return proxy.call_turn(stage, req.meter, req.audio_b64)
        except Exception:
            return JSONResponse(_fallback_payload(stage, include_caller=True))

    @api.post("/api/seek")
    def api_seek(req: SeekReq):
        return {"stage": arc.meter_to_stage(req.meter)}

    @api.get("/api/songs")
    def api_songs():
        # キュレーション済み楽曲バンク: ブラウザは各曲の音楽パラメータから
        # 生成音楽と now-playing プレートを描画し、song_intro は曲名/
        # アーティストを使う。単一情報源（content.py）。
        return {"songs": content.SONGS}

    @api.post("/api/segment")
    def api_segment(req: SegmentReq):
        # DJ の番組セグメント1つ（テキスト + 音声）。番組は決して壊さない:
        # 失敗時はテンプレ文 + 短い無音クリップ（ベッドが覆う）を返す。
        try:
            return proxy.segment_turn(req.kind, req.ctx)
        except Exception:
            return JSONResponse(proxy.segment_fallback(req.kind, req.ctx))

    @api.post("/api/locale")
    def api_locale(req: LocaleReq):
        # リスナーの実在する天気/時刻/町名を解決する。失敗時は未解決を返し、
        # クライアントは架空の町の天気へきれいに退避する。
        try:
            return proxy.resolve_locale(req.lat, req.lon)
        except Exception:
            return JSONResponse({"resolved": False})

    @api.post("/api/song_card")
    def api_song_card(req: SongCardReq):
        # AI が架空のレコードを発明する（音楽パラメータは検証済み）。失敗時は
        # {card: None} を返し、クライアントは単にスキップする。
        try:
            return {"card": proxy.make_song_card(req.ctx)}
        except Exception:
            return JSONResponse({"card": None})

    @api.get("/api/stalls")
    def api_stalls():
        # 事前合成の「間持たせ」クリップ。本物の返答を生成しているあいだ、
        # ラジオが即座に再生する（通話に無音を作らない）。
        try:
            return {"stalls": proxy.get_stalls()}
        except Exception:
            return {"stalls": []}

    return api
