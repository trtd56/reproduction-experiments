"""NIGHTWAVE-JA エンジン呼び出し層（オリジナルの Modal プロキシに相当）。

オリジナルはここから Modal 上の /brain /asr /speak を HTTP で叩いていたが、
日本語ローカル版では engine.py（llama-cpp / faster-whisper / Kokoro）を
直接呼ぶ。契約（関数シグネチャとレスポンス形状）はオリジナルと同一に保ち、
server.py / radio.html は無改造で載る。

モック運転（NIGHTWAVE_MOCK=="1"）は canned データ + 短い無音 WAV を返し、
モデルを一切ロードせずに UI 全体が動く -- ローカル開発と CI 用。
"""

import base64
import datetime
import io
import os
import random
import re
import struct
import threading
import wave
from typing import Any, Dict, List, Optional

import httpx

import arc
import content

# 天気 API 用の HTTP クライアント（接続プーリングのため使い回す）。
_TIMEOUT = 10.0
_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=_TIMEOUT)
    return _client


# ---------------------------------------------------------------------------
# 環境
# ---------------------------------------------------------------------------
def is_mock() -> bool:
    """canned データで運転すべきなら True。"""
    return os.environ.get("NIGHTWAVE_MOCK") == "1"


def _engine():
    # 遅延 import: モック運転では重量級ライブラリを一切ロードしない。
    import engine
    return engine


# ---------------------------------------------------------------------------
# モックヘルパー
# ---------------------------------------------------------------------------
def _silent_wav_b64(seconds: float = 0.4, rate: int = 24000) -> str:
    """短い無音の 24kHz mono PCM16 WAV を pure Python で作る。

    契約どおり data: プレフィックスなしの base64 を返す。
    """
    n_frames = int(seconds * rate)
    buf = io.BytesIO()
    wf = wave.open(buf, "wb")
    try:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(rate)
        silence = struct.pack("<%dh" % n_frames, *([0] * n_frames))
        wf.writeframes(silence)
    finally:
        wf.close()
    return base64.b64encode(buf.getvalue()).decode("ascii")


_MOCK_BRAIN_LINE = (
    "そのまま、そこにいてください。ダイヤルは温まっていて、夜はまだ長い。"
    "この一曲は、まだ起きているすべての人に。"
)


def _mock_brain() -> Dict[str, Any]:
    return {"text": _MOCK_BRAIN_LINE, "mood": "warm", "arc_cue": "none"}


def _mock_asr() -> Dict[str, Any]:
    return {"text": "今夜、本当に誰か起きてるんでしょうか？"}


def _mock_speak() -> Dict[str, Any]:
    return {
        "audio_b64": _silent_wav_b64(),
        "words": [],
        "wtimes": [],
        "wdurations": [],
    }


# ---------------------------------------------------------------------------
# 実在の天気/位置解決（サーバー側。生の座標は決してログに出さない）。
# Open-Meteo（現在天気 + 日の出 + 現地時刻）と BigDataCloud（市区町村名）。
# どちらも無料・キー不要。失敗はすべて架空の町の天気へ品よく退避する。
# ---------------------------------------------------------------------------
_WMO = {
    0: "快晴", 1: "おおむね晴れ", 2: "ところどころ雲", 3: "曇り",
    45: "霧", 48: "着氷性の霧", 51: "弱い霧雨", 53: "霧雨",
    61: "小雨", 63: "雨", 65: "強い雨", 71: "小雪",
    73: "雪", 80: "通り雨", 81: "にわか雨", 95: "雷雨",
}


def _wmo_phrase(code) -> str:
    try:
        return _WMO.get(int(code), "静かな空")
    except (TypeError, ValueError):
        return "静かな空"


def _fmt_clock(iso: Optional[str]) -> Optional[str]:
    """'2026-06-15T02:14' -> '午前2時14分'。None/不正 -> None。"""
    if not iso:
        return None
    try:
        t = datetime.datetime.fromisoformat(iso)
        ap = "午前" if t.hour < 12 else "午後"
        h = t.hour % 12 or 12
        return "%s%d時%02d分" % (ap, h, t.minute)
    except (ValueError, TypeError):
        return None


def _reverse_city(lat: float, lon: float) -> Optional[str]:
    try:
        r = _get_client().get(
            "https://api.bigdatacloud.net/data/reverse-geocode-client",
            params={"latitude": lat, "longitude": lon, "localityLanguage": "ja"},
        )
        r.raise_for_status()
        j = r.json()
        return j.get("city") or j.get("locality") or j.get("principalSubdivision") or None
    except Exception:
        return None


def resolve_locale(lat: float, lon: float) -> Dict[str, Any]:
    """lat/lon の実在天気/時刻/町名 -> 事実 dict、または {'resolved': False}。

    生の座標は決してログに出さない（プライバシー）。モック運転では canned な
    事実を返し、全経路がオフラインで動く。
    """
    if is_mock():
        return {"resolved": True, "city": "灯里町", "temp_c": 15,
                "sky": "快晴", "local_time": "午前2時14分", "sunrise": "午前4時48分"}
    try:
        wx = _get_client().get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weather_code",
                "daily": "sunrise,sunset", "timezone": "auto",
                "forecast_days": 1,
            },
        )
        wx.raise_for_status()
        w = wx.json()
        cur = w.get("current", {}) or {}
        daily = w.get("daily", {}) or {}
        sunrise_list = daily.get("sunrise") or [None]
        return {
            "resolved": True,
            "temp_c": cur.get("temperature_2m"),
            "sky": _wmo_phrase(cur.get("weather_code")),
            "local_time": _fmt_clock(cur.get("time")),
            "sunrise": _fmt_clock(sunrise_list[0]),
            "city": _reverse_city(lat, lon),
        }
    except Exception:
        return {"resolved": False}


def _local_weather_user(ctx: Optional[Dict[str, Any]] = None) -> str:
    """local_weather セグメント用の USER ターン事実文字列を組み立てる。"""
    ctx = ctx or {}
    parts: List[str] = []
    if ctx.get("city"):
        parts.append("%sのあたりでは" % ctx["city"])
    if ctx.get("temp_c") is not None:
        parts.append("気温はだいたい%d度" % int(round(float(ctx["temp_c"]))))
    if ctx.get("sky"):
        parts.append("空は%s" % ctx["sky"])
    if ctx.get("local_time"):
        parts.append("時計はさっき%sを指しました" % ctx["local_time"])
    if ctx.get("sunrise"):
        parts.append("日の出は%sごろ" % ctx["sunrise"])
    facts = "、".join(parts) if parts else "そちらは静かでよく晴れた夜"
    return (
        "リスナー自身の今夜の空のことを、そっと伝えてください。いま本当のことは"
        "こうです: " + facts + "。これを温かい話し言葉1〜2文に織り込むこと。"
        "予報のように読み上げない、列挙しない、「ラベル: 値」の形では絶対に"
        "書かない。"
    )


# ---------------------------------------------------------------------------
# 生のエンジン呼び出し（オリジナルの Modal 呼び出しに相当）
# ---------------------------------------------------------------------------
def call_brain(system: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """engine.brain -> {"text", "mood", "arc_cue"}。"""
    if is_mock():
        return _mock_brain()
    return _engine().brain(system, messages)


def call_asr(audio_b64: str) -> Dict[str, Any]:
    """engine.asr -> {"text"}。"""
    if is_mock():
        return _mock_asr()
    return _engine().asr(audio_b64)


# ラテン文字ブランド「NIGHTWAVE」「98.6」は日本語 G2P が読めない/不自然に
# 読むため、発話用テキストだけカタカナ・かな読みへ正規化する。
# キャプション/UI はブランド表記の原文のまま。
_SPEAK_FIXES = [
    (re.compile(r"\bNIGHT\s*WAVE\b", re.IGNORECASE), "ナイトウェーブ"),
    (re.compile(r"98\.6"), "きゅうじゅうはってんろく"),
    # G2P が「宵野」を「よいや」と誤読するため（smoke_engine の ASR 往復で確認）
    (re.compile(r"宵野"), "よいの"),
]


def _speakable(text: Optional[str]) -> str:
    t = text or ""
    for pat, rep in _SPEAK_FIXES:
        t = pat.sub(rep, t)
    return t


def call_speak(text: str, voice: str = arc.VOICE) -> Dict[str, Any]:
    """engine.speak -> {"audio_b64", "words", "wtimes", "wdurations"}。

    音声は発話用に正規化したテキストで合成し、キャプションは原文から作る。
    """
    if is_mock():
        return _mock_speak()
    return _engine().speak(_speakable(text), voice=voice, display_text=text)


# ---------------------------------------------------------------------------
# DJテキストのサニタイザー: 小型モデルは JSON のラベルを話し言葉に漏らしたり
# （「……気分: warm」）、プレースホルダ（「<一文目>」）を出したりする。DJ に
# それを「言わせない」ため、TTS 前にテキストを洗い、残りが degenerate なら
# ステージに合った canned ラインへ退避する。日本語向けに全面調整済み。
# ---------------------------------------------------------------------------
_LABEL_RE = re.compile(
    r"[\(\[（【]?\s*(?:mood|arc[_ ]?cue|title|artist|song|track|vibe|genre|city|"
    r"temp(?:erature)?|sky|weather|time|sunrise|sunset|name|"
    r"気分|ムード|曲名|タイトル|アーティスト|歌手|曲|ジャンル|雰囲気|町|都市|"
    r"気温|温度|天気|天候|空模様|時刻|時間|日の出|日の入り|名前|宛先|リクエスト)"
    r"\s*[:：=＝]\s*[^\n、。;；]*",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(
    r"<[^>]{0,40}>|\[[^\]]{0,40}\]|\{[^}]{0,40}\}|[（(]?例[:：]|一文目|二文目",
    re.IGNORECASE,
)
# 指示文のオウム返し検出（プロンプト中の言い回し）。
_ECHO_RE = re.compile(
    r"(話し言葉で?1〜?[23]文|1〜?[23]文で|繰り返さない|引用しない|ラベル(?:付け)?は禁止|"
    r"あなた自身の言葉で|ト書き|この指示)",
)
# 日本語として意味のある文字（かな・カナ・漢字・長音）。
_JA_CHARS_RE = re.compile(r"[ぁ-んァ-ヶー一-龯]")


def _clean_dj_text(text: Optional[str]) -> Optional[str]:
    """ラベル漏れ/マークダウンを除去。洗った話し言葉か、ジャンクなら None を返す。"""
    t = text or ""
    t = _LABEL_RE.sub("", t)           # 「気分: warm」「曲名: X」の連なりを落とす
    t = re.sub(r"[*#`]+", "", t)        # マークダウンの強調/見出しを落とす
    t = t.strip()
    if len(t) >= 2 and t[0] in "\"'「『" and t[-1] in "\"'」』":
        t = t[1:-1].strip()             # 全体が括られた行を剥がす
    t = re.sub(r"\s+", " ", t).strip()  # 話し言葉なので空白を畳む
    # degenerate 判定: 空 / プレースホルダ / 括弧記号 / ラベル構造 / 指示エコー。
    if not t or _PLACEHOLDER_RE.search(t):
        return None
    if any(c in t for c in "<>[]{}|"):
        return None
    if re.search(r"(?:title|artist|mood|arc_cue|temp|sky|sunrise|vibe|"
                 r"曲名|アーティスト|気分|気温|日の出)\s*[:：=＝]", t, re.IGNORECASE):
        return None
    if t.count(":") + t.count("：") >= 2:
        return None
    if _ECHO_RE.search(t):
        return None
    if len(_JA_CHARS_RE.findall(t)) < 4:
        return None
    return t


# ---------------------------------------------------------------------------
# コーラーのセッションメモリ（SP1）: ASR テキストからの決定的抽出。
# モデル呼び出しなし。mood は返答の brain 呼び出しから再利用し、topic は
# 発話の要旨、名前/場所はベストエフォート（None が普通）。
# ---------------------------------------------------------------------------
_PLACE_RE = re.compile(
    r"([ぁ-んァ-ヶ一-龯]{2,10}(?:市|町|村|区|県|島))(?:から|に住んで|在住|の)"
)


def _caller_gist(caller_text: Optional[str]) -> Optional[str]:
    t = re.sub(r"\s+", " ", (caller_text or "")).strip()
    # 日本語は分かち書きされないため、語数ではなく文字数で「実質があるか」を測る。
    if len(_JA_CHARS_RE.findall(t)) < 5:
        return None
    return t[:70].strip()


def _extract_name(caller_text: Optional[str]) -> Optional[str]:
    t = caller_text or ""
    m = re.search(
        r"(?:私の名前は|僕の名前は|俺の名前は|名前は|私は|僕は|俺は|こちら)\s*"
        r"([ぁ-んァ-ヶ一-龯A-Za-z]{1,10}?)(?:です|と申します|と言います|といいます)",
        t,
    )
    if m:
        return m.group(1).strip()[:20]
    m = re.search(r"([ぁ-んァ-ヶ一-龯A-Za-z]{1,10})(?:と申します|といいます|と言います)", t)
    return m.group(1).strip()[:20] if m else None


def _extract_place(caller_text: Optional[str]) -> Optional[str]:
    m = _PLACE_RE.search(caller_text or "")
    return m.group(1).strip()[:20] if m else None


def _build_memory_patch(caller_text: Optional[str], mood: str) -> Optional[Dict[str, Any]]:
    topic = _caller_gist(caller_text)
    if not topic:
        return None
    return {
        "caller_name": _extract_name(caller_text),
        "place": _extract_place(caller_text),
        "topic": topic,
        "mood": mood if mood in arc.MOODS else "warm",
    }


# ---------------------------------------------------------------------------
# 事前キャッシュの「間持たせ」ライン: コーラーが話し終えた瞬間に流す即席の
# つなぎ音声。裏で本物の返答を生成しているあいだ、通話に無音を作らない。
# コンテナ（プロセス）ごとに一度合成してキャッシュする。
# ---------------------------------------------------------------------------
_STALL_LINES = [
    "ふむ……いい質問ですね。少しだけ、その問いと座らせてください。",
    "この時間に聞くには、なかなかの質問だ。ちょっと待って、言葉を探しますから。",
    "ん……ひと呼吸ください。夜は、私を少しゆっくりにするんです。",
    "考えさせてください。そのまま、そこにいて。",
]
_stall_cache: Optional[List[str]] = None
_stall_lock = threading.Lock()


def get_stalls() -> List[str]:
    """base64 WAV のつなぎクリップ一覧を返す（初回合成後はキャッシュ）。"""
    global _stall_cache
    if _stall_cache is not None:
        return _stall_cache
    with _stall_lock:
        if _stall_cache is not None:
            return _stall_cache
        clips: List[str] = []
        for line in _STALL_LINES:
            try:
                sp = call_speak(line)
                if sp.get("audio_b64"):
                    clips.append(sp["audio_b64"])
            except Exception:
                pass
        _stall_cache = clips
        return clips


# ---------------------------------------------------------------------------
# 高レベルターン（server.py のルートが呼ぶ）
# ---------------------------------------------------------------------------
def broadcast_turn(
    stage: str, meter: int, topic: Optional[str] = None
) -> Dict[str, Any]:
    """ソロのオンエアターンを1つ生成する。

    -> /api/broadcast レスポンス形状:
       {text, mood, arc_cue, audio_b64, words, wtimes, wdurations}
    """
    system = arc.build_host_prompt("on_air", {"topic": topic})
    user = (topic.strip() if (topic and topic.strip())
            else "いまから放送に乗って、温かい深夜のトークを短くひとつお願いします。")
    try:
        brain = call_brain(system, [{"role": "user", "content": user}])
        text = _clean_dj_text(brain.get("text", "")) or _templated_text("thought")
        mood = brain.get("mood", "warm")
        arc_cue = brain.get("arc_cue", "none")
    except Exception:
        text, mood, arc_cue = _templated_text("thought"), "warm", "none"
    speak = call_speak(text)
    return {
        "text": text,
        "mood": mood,
        "arc_cue": arc_cue,
        "audio_b64": speak.get("audio_b64", ""),
        "words": speak.get("words", []),
        "wtimes": speak.get("wtimes", []),
        "wdurations": speak.get("wdurations", []),
    }


def call_turn(stage: str, meter: int, audio_b64: str) -> Dict[str, Any]:
    """生電話ターンを1つ処理する。

    -> /api/call レスポンス形状:
       {caller_text, text, mood, arc_cue, audio_b64, words, wtimes,
        wdurations, meter_delta}
    """
    asr = call_asr(audio_b64)
    caller_text = asr.get("text", "")
    meter_delta = arc.detect_triggers(caller_text)

    # 素のラジオ局: ホストは常に自分の声でコーラーに答える。コーラーの言葉は
    # 「回答指示」として USER ターンで渡す（逐語で埋め込まない）。JSON 文法下の
    # 小型モデルは、文脈に逐語で現れた質問をオウム返ししがちなため。
    system = arc.build_host_prompt("caller", {"caller_text": caller_text})
    if caller_text and caller_text.strip():
        user_msg = (
            "電話の相手はこういうことを尋ねています: " + caller_text.strip()
            + "\nあなた自身の言葉による温かい返答だけを話してください -- 相手に"
            "答える、新しい一文です。相手の言葉と同じ言葉から話し始めない。"
            "相手の言葉を引用したり言い直したりしない、「ラベル: 値」の形で"
            "書かない、この指示を繰り返さない。"
        )
    else:
        user_msg = "（回線にノイズが乗って、相手の言葉は聞き取れませんでした）"
    brain = call_brain(system, [{"role": "user", "content": user_msg}])
    text = _clean_dj_text(brain.get("text", "")) or _pick(content.CALLER_FALLBACKS)
    speak = call_speak(text)
    memory_patch = _build_memory_patch(caller_text, brain.get("mood", "warm"))
    return {
        "caller_text": caller_text,
        "text": text,
        "mood": brain.get("mood", arc.stage_default_mood(stage)),
        "arc_cue": brain.get("arc_cue", "none"),
        "audio_b64": speak.get("audio_b64", ""),
        "words": speak.get("words", []),
        "wtimes": speak.get("wtimes", []),
        "wdurations": speak.get("wdurations", []),
        "meter_delta": meter_delta,
        "memory_patch": memory_patch,
        "queue_dedication": bool(memory_patch),
    }


# ---------------------------------------------------------------------------
# 自律番組セグメント（素のラジオ局）。
# LLM 系（thought, song_intro など）-> ホストペルソナ + brain + サニタイザー。
# テンプレート系（station_id, weather, dedication）-> コンテンツバンク。全部発話。
# ---------------------------------------------------------------------------
def _pick(seq):
    return random.choice(seq) if seq else ""


def _templated_text(kind: str, ctx: Optional[Dict[str, Any]] = None) -> str:
    ctx = ctx or {}
    if kind in ("weather", "local_weather"):
        # 架空の町の天気は local_weather の品のよいフォールバックでもある。
        return _pick(content.WEATHER)
    if kind == "dedication":
        d = _pick(content.DEDICATIONS) or {"name": "夜のどこかの誰か",
                                           "message": "いま感じているほど、ひとりじゃありませんよ"}
        return "次の一曲は、%sへ -- %s。" % (d["name"], d["message"])
    if kind == "song_intro":
        base = "続いては、%sで『%s』。" % (
            ctx.get("artist", "番組の友人"), ctx.get("title", "次の一曲"))
        rb = ctx.get("recommended_by")
        if rb:
            base = base[:-1] + " -- %s さんからのリクエストです。" % rb
        return base
    if kind == "rejoin":
        return _pick(content.REJOINS)
    if kind == "caller_intro":
        return _pick(content.CALLER_INTROS)
    if kind == "thought":
        return _pick(content.THOUGHTS)
    if kind == "fragment":
        return _pick(content.FRAGMENTS)
    return _pick(content.STATION_IDS)  # station_id（既定）


# ---------------------------------------------------------------------------
# 生成レコードカード（SP3）: モデルが曲名+アーティストを書き、サーバーが
# 雰囲気を選んで「常に正当な」音楽パラメータを割り当てる。カードがエンジンを
# 壊すことはあり得ない。vibe キーは英語のまま（クライアントの MOOD_VIBES
# 選曲フィルタとの契約）。表示・発話用の日本語は _VIBE_JA で引く。
# ---------------------------------------------------------------------------
_VIBE_MUSIC = {
    "melancholy": ("minor", "rhodes", 70, ("A", "E", "D")),
    "lonely": ("minor", "music_box", 64, ("A", "E", "Bb")),
    "tender": ("major", "music_box", 68, ("C", "F", "Bb")),
    "warm": ("major", "rhodes", 78, ("C", "D", "G")),
    "cozy": ("major", "rhodes", 80, ("F", "C", "Bb")),
    "hopeful": ("lydian", "soft_saw", 80, ("D", "G", "C")),
    "nostalgic": ("major", "triangle_pluck", 74, ("C", "Bb", "G")),
    "wistful": ("dorian", "sine_pad", 72, ("C", "D", "F")),
    "bittersweet": ("minor", "rhodes", 70, ("Bb", "A", "E")),
    "jazzy": ("dorian", "rhodes", 84, ("D", "F", "G")),
    "dreamy": ("lydian", "sine_pad", 64, ("F", "D", "Eb")),
    "pensive": ("dorian", "sine_pad", 76, ("C", "E", "G")),
    "hypnotic": ("pentatonic_minor", "soft_saw", 70, ("G", "A", "D")),
    "mysterious": ("lydian", "sine_pad", 68, ("Eb", "A", "F")),
    "eerie": ("pentatonic_minor", "sine_pad", 60, ("A", "Eb", "G")),
    "ambient": ("lydian", "sine_pad", 64, ("F", "D", "C")),
    "romantic": ("minor", "rhodes", 66, ("Ab", "D", "A")),
    "gentle": ("major", "triangle_pluck", 75, ("C", "G", "D")),
    "breezy": ("major", "triangle_pluck", 88, ("G", "D", "C")),
}
_DEFAULT_MUSIC = ("major", "rhodes", 74, ("C", "D", "G"))
_MOOD_TO_VIBE = {
    "warm": "warm", "nostalgic": "nostalgic", "tender": "tender",
    "searching": "pensive", "hollow": "lonely", "uneasy": "eerie",
}

# vibe 英語キー -> DJ の発話・プロンプトに使う日本語。
_VIBE_JA = {
    "melancholy": "物悲しい", "lonely": "さみしげな", "tender": "やさしい",
    "warm": "あたたかい", "cozy": "ぬくもりのある", "hopeful": "希望のにじむ",
    "nostalgic": "なつかしい", "wistful": "切ない", "bittersweet": "ほろ苦い",
    "jazzy": "ジャジーな", "dreamy": "夢見心地の", "pensive": "物思いに沈む",
    "hypnotic": "眠りを誘う", "mysterious": "ミステリアスな", "eerie": "不気味な",
    "ambient": "漂うような", "romantic": "ロマンチックな", "gentle": "おだやかな",
    "breezy": "そよ風のような",
}


def vibe_ja(vibe: Optional[str]) -> str:
    """vibe 英語キーを発話用の日本語形容へ（未知は「深夜らしい」）。"""
    return _VIBE_JA.get(vibe or "", "深夜らしい")


def _parse_title_artist(text):
    t = re.sub(r"\s+", " ", text or "").strip().strip("\"'「」『』")
    t = re.sub(r"^(?:title|song|曲名|タイトル)\s*[:：=]\s*", "", t, flags=re.IGNORECASE)
    parts = re.split(r"\s*(?:/|／|--|—|by)\s*", t, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None, None
    title = parts[0].strip().strip("\"'「」『』")[:24]
    # 末尾のモデルのおしゃべり（「……お楽しみください！」等）は最初の文末で
    # 切り落とす。
    artist = re.split(r"[。！!?？]", parts[1].strip().strip("\"'「」『』"), maxsplit=1)[0].strip()[:24]
    if (2 <= len(title) <= 24 and 2 <= len(artist) <= 24
            and not any(c in t for c in "<>{}[]")
            and ":" not in title and "：" not in title):
        return title, artist
    return None, None


def _procedural_title():
    return "%s%s" % (random.choice(content.CARD_TITLE_A), random.choice(content.CARD_TITLE_B))


def _procedural_artist():
    return "%s%s" % (random.choice(content.CARD_ARTIST_A), random.choice(content.CARD_ARTIST_B))


def _generate_title_artist(ctx, vibe):
    try:
        flavor = ""
        if ctx.get("topic"):
            flavor = "。こんなことを話していた人がいました:「%s」" % str(ctx["topic"])[:60]
        elif ctx.get("city"):
            flavor = "。%sの夜のための一枚です" % ctx["city"]
        user = ("%s雰囲気を持つ、架空の深夜のレコードをひとつ発明してください%s。"
                "「<曲名> / <アーティスト>」の形だけで答えること。それ以外は何も"
                "書かない。" % (vibe_ja(vibe), flavor))
        brain = call_brain(arc.build_song_card_prompt(), [{"role": "user", "content": user}])
        title, artist = _parse_title_artist(brain.get("text", ""))
        if title and artist:
            return title, artist
    except Exception:
        pass
    return _procedural_title(), _procedural_artist()


def make_song_card(ctx=None):
    """架空のレコードを1枚発明する。音楽パラメータは常に正当なエンジン enum。"""
    ctx = ctx or {}
    vibe = _MOOD_TO_VIBE.get(ctx.get("mood")) or random.choice(list(_VIBE_MUSIC.keys()))
    scale, timbre, tempo, keys = _VIBE_MUSIC.get(vibe, _DEFAULT_MUSIC)
    title, artist = _generate_title_artist(ctx, vibe)
    return {
        "title": title, "artist": artist, "vibe": vibe,
        "key": random.choice(keys), "scale": scale, "tempo": tempo, "timbre": timbre,
        "recommended_by": None, "generated": True,
    }


_FRAGMENT_FLAVORS = ["dedication", "numbers_weather", "station_id", "dream", "song_title"]
_FRAGMENT_HINT = {
    "dedication": "名指すことのない誰かへの、半分しか聞き取れない献呈",
    "numbers_weather": "実在しないかもしれない場所の、乱数放送のような天気の読み上げ",
    "station_id": "本来は空いているはずの周波数から聞こえる、架空の局名アナウンス",
    "dream": "誰かが声に出して見ている夢のような、迷い込んだ一行",
    "song_title": "砂嵐に溶けていく、聞き取れない曲名とアーティスト名",
}


def _fragment_user(ctx: Optional[Dict[str, Any]] = None) -> str:
    ctx = ctx or {}
    flavor = random.choice(_FRAGMENT_FLAVORS)
    hint = _FRAGMENT_HINT[flavor]
    extra = ""
    if flavor == "numbers_weather" and ctx.get("city"):
        extra = "（%sの近くのどこか）" % ctx["city"]
    if flavor == "dedication" and ctx.get("topic"):
        extra = "（%sについて）" % ctx["topic"]
    return ("ダイヤル上の別の局から漏れ聞こえてくる短い断片をひとつだけ話して"
            "ください: " + hint + extra + "。20文字前後まで、不気味で、遠く、"
            "砂嵐に半分溶けているように。話し言葉だけ、ラベルなし。")


def _dedication_user(ctx: Optional[Dict[str, Any]] = None) -> str:
    ctx = ctx or {}
    msg = ("電話をくれたリスナーへの短くて温かい献呈を、放送で読み上げて"
           "ください。その人が話してくれたこと: %s。" % ctx.get("topic", "今夜、遅くまで起きているそうです"))
    if ctx.get("caller_name"):
        msg += "お名前は%sさん。" % ctx["caller_name"]
    if ctx.get("place"):
        msg += "%sにいるそうです。" % ctx["place"]
    msg += ("次のレコードをその人へ送り出す、温かい話し言葉1〜2文で。"
            "相手の言葉を引用しない、何にもラベルを付けない、この指示を"
            "繰り返さない。")
    return msg


def _dedication_fallback(ctx: Optional[Dict[str, Any]] = None) -> str:
    ctx = ctx or {}
    name = ctx.get("caller_name")
    if name:
        return "次の一曲は、%sさんへ -- 今夜は、いま感じているほどひとりじゃありませんよ。" % name
    return _templated_text("dedication")


def segment_turn(kind: str, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """番組セグメントを1つ、音声付きで生成する。"""
    ctx = ctx or {}
    mood, arc_cue = "warm", "none"
    memory_dedication = (kind == "dedication" and bool(ctx.get("topic")))
    if kind in ("thought", "song_intro", "local_weather", "fragment") or memory_dedication:
        system = arc.build_fragment_prompt() if kind == "fragment" else arc.build_host_prompt(kind, ctx)
        if kind == "fragment":
            user = _fragment_user(ctx)
        elif kind == "dedication":
            user = _dedication_user(ctx)
            mood = ctx.get("mood", "warm")
        elif kind == "song_intro":
            user = (
                "いまから次の曲を放送に迎え入れてください。%sの『%s』、%s"
                "雰囲気の一枚です。あなた自身の声の温かい話し言葉1〜2文で迎える"
                "こと。「曲名」「アーティスト」という単語は使わない、何にも"
                "ラベルを付けない、「ラベル: 値」の形で書かない、この指示を"
                "繰り返さない。"
                % (ctx.get("artist", "番組の友人"),
                   ctx.get("title", "次の一曲"),
                   vibe_ja(ctx.get("vibe")))
            )
            if ctx.get("segue"):
                user = ("まず短くて温かいつなぎのひとこと -- %s -- から入って、"
                        "そのまま続けて: " % ctx["segue"]) + user
            rb = ctx.get("recommended_by")
            if rb:
                user += (
                    "この一枚はリスナーの %s さんが送ってくれました -- 迎え入れ"
                    "ながら、その人へ温かくひとこと触れてください。" % rb
                )
            if ctx.get("fresh"):
                user += ("このレコードが真新しいことにも温かく触れてください -- "
                         "今夜プレスされたばかりで、まだ誰も聴いたことがない、と。")
        elif kind == "local_weather":
            user = _local_weather_user(ctx)
        else:
            user = "いま聴いているリスナーたちへ、短い深夜のひとことをひとつ。"
        try:
            brain = call_brain(system, [{"role": "user", "content": user}])
            fb = _dedication_fallback(ctx) if kind == "dedication" else _templated_text(kind, ctx)
            text = _clean_dj_text(brain.get("text", "")) or fb
            mood = brain.get("mood", mood)
            arc_cue = brain.get("arc_cue", "none")
        except Exception:
            text = _dedication_fallback(ctx) if kind == "dedication" else _templated_text(kind, ctx)
    else:
        text = _templated_text(kind, ctx)
        if kind == "weather":
            mood = "nostalgic"

    speak = call_speak(text)
    return {
        "kind": kind,
        "text": text,
        "mood": mood,
        "arc_cue": arc_cue,
        "audio_b64": speak.get("audio_b64", ""),
        "words": speak.get("words", []),
        "wtimes": speak.get("wtimes", []),
        "wdurations": speak.get("wdurations", []),
    }


def segment_fallback(kind: str, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """決して失敗しないセグメント: テンプレ文 + 短い無音 WAV（ベッドが覆う）。"""
    return {
        "kind": kind,
        "text": _templated_text(kind, ctx),
        "mood": "warm",
        "arc_cue": "none",
        "audio_b64": _silent_wav_b64(),
        "words": [],
        "wtimes": [],
        "wdurations": [],
    }
