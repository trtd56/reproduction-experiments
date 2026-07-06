"""nightwave_ja/proxy.py の pytest スイート（オリジナル test_proxy.py の日本語移植）。

既定でモック運転（conftest.py が NIGHTWAVE_MOCK=1 を設定）。エンジンを
モデルなしで検証するため、call_brain / call_speak / call_asr は必要に応じて
monkeypatch する。
"""

import arc
import content
import proxy


# ---------------------------------------------------------------------------
# テンプレートセグメント
# ---------------------------------------------------------------------------
def test_templated_rejoin_names_the_dj():
    assert arc.DJ_NAME in proxy._templated_text("rejoin")


def test_templated_caller_intro_nonempty():
    assert proxy._templated_text("caller_intro").strip()


def test_song_intro_template_includes_handle():
    t = proxy._templated_text(
        "song_intro",
        {"title": "ネオンの雨", "artist": "火曜日の幽霊たち", "recommended_by": "@kokudo9_truck"},
    )
    assert "ネオンの雨" in t and "火曜日の幽霊たち" in t
    assert "@kokudo9_truck" in t


def test_song_intro_template_omits_handle_when_absent():
    t = proxy._templated_text("song_intro", {"title": "電話線", "artist": "火曜日の幽霊たち"})
    assert "リクエスト" not in t


# ---------------------------------------------------------------------------
# 天気・時刻の整形
# ---------------------------------------------------------------------------
def test_wmo_phrase_mapping():
    assert proxy._wmo_phrase(0) == "快晴"
    assert proxy._wmo_phrase(63) == "雨"
    assert proxy._wmo_phrase(999) == "静かな空"
    assert proxy._wmo_phrase(None) == "静かな空"


def test_fmt_clock():
    assert proxy._fmt_clock("2026-06-15T02:14") == "午前2時14分"
    assert proxy._fmt_clock("2026-06-15T14:05") == "午後2時05分"
    assert proxy._fmt_clock("2026-06-15T00:30") == "午前12時30分"
    assert proxy._fmt_clock(None) is None
    assert proxy._fmt_clock("garbage") is None


def test_resolve_locale_mock():
    j = proxy.resolve_locale(35.0, 139.0)
    assert j["resolved"] is True
    assert j["city"] == "灯里町"
    assert "temp_c" in j


def test_local_weather_user_weaves_facts():
    u = proxy._local_weather_user(
        {"city": "杉並区", "temp_c": 17.6, "sky": "快晴",
         "local_time": "午前2時14分", "sunrise": "午前4時48分"}
    )
    assert "杉並区" in u and "18度" in u and "快晴" in u
    assert "ラベル: 値" in u  # 禁止指示が入っている


def test_local_weather_user_empty_ctx_is_graceful():
    u = proxy._local_weather_user({})
    assert "静かでよく晴れた夜" in u


# ---------------------------------------------------------------------------
# DJ テキストのサニタイザー（日本語）
# ---------------------------------------------------------------------------
def test_clean_dj_text_rejects_degenerate_text_as_none():
    assert proxy._clean_dj_text("") is None
    assert proxy._clean_dj_text(None) is None
    assert proxy._clean_dj_text("<一文目>") is None
    assert proxy._clean_dj_text("{何か}") is None
    assert proxy._clean_dj_text("abc") is None  # 日本語がほぼ無い


def test_clean_dj_text_rejects_label_leakage():
    assert proxy._clean_dj_text("曲名: ネオンの雨、アーティスト: 火曜日の幽霊たち") is None
    assert proxy._clean_dj_text('{"text": "こんばんは", "mood": "warm"}') is None
    assert proxy._clean_dj_text("気温: 15度、空: 快晴") is None
    assert proxy._clean_dj_text("気分：warm　時刻：午前2時") is None
    ok = "続いては、夜更かしのあなたへ静かな一曲を。"
    assert proxy._clean_dj_text(ok) == ok


def test_clean_dj_text_rejects_instruction_echo():
    assert proxy._clean_dj_text("温かい話し言葉で1〜2文で答えます。") is None
    assert proxy._clean_dj_text("あなた自身の言葉で話してください。") is None


def test_clean_dj_text_unwraps_quotes_and_markdown():
    assert proxy._clean_dj_text("「今夜も、ダイヤルはそのままで。」") == "今夜も、ダイヤルはそのままで。"
    assert proxy._clean_dj_text("**今夜も、ダイヤルはそのままで。**") == "今夜も、ダイヤルはそのままで。"


# ---------------------------------------------------------------------------
# つなぎクリップ / 決して失敗しないセグメント
# ---------------------------------------------------------------------------
def test_get_stalls_returns_cached_clip_list(monkeypatch):
    monkeypatch.setattr(proxy, "_stall_cache", None)
    clips = proxy.get_stalls()
    assert isinstance(clips, list) and len(clips) == len(proxy._STALL_LINES)
    assert all(isinstance(c, str) and c for c in clips)  # 各要素は base64 WAV
    assert proxy.get_stalls() is clips                   # 2回目はキャッシュ


def test_segment_fallback_is_never_failing_and_well_shaped():
    fb = proxy.segment_fallback("thought")
    assert fb["kind"] == "thought"
    assert fb["text"] in content.THOUGHTS
    assert fb["audio_b64"]
    for key in ("mood", "arc_cue", "words", "wtimes", "wdurations"):
        assert key in fb


# ---------------------------------------------------------------------------
# 発話正規化: ラテン文字ブランドは TTS 前にかな読みへ
# ---------------------------------------------------------------------------
def test_speakable_normalizes_brand():
    assert proxy._speakable("お聴きの放送は NIGHTWAVE です") == "お聴きの放送は ナイトウェーブ です"
    assert proxy._speakable("night wave") == "ナイトウェーブ"
    assert proxy._speakable("周波数98.6でお送りします") == "周波数きゅうじゅうはってんろくでお送りします"
    assert proxy._speakable("宵野サムです") == "よいのサムです"
    assert proxy._speakable(None) == ""


def test_call_speak_normalizes_before_tts(monkeypatch):
    sent = {}

    class _Engine:
        @staticmethod
        def speak(text, voice=None, display_text=None):
            sent["text"] = text
            sent["display_text"] = display_text
            return {"audio_b64": "", "words": [], "wtimes": [], "wdurations": []}

    monkeypatch.setattr(proxy, "is_mock", lambda: False)
    monkeypatch.setattr(proxy, "_engine", lambda: _Engine)
    proxy.call_speak("こちら NIGHTWAVE、98.6。")
    assert "NIGHTWAVE" not in sent["text"]
    assert "ナイトウェーブ" in sent["text"]
    # キャプションはブランド表記の原文のまま
    assert "NIGHTWAVE" in sent["display_text"]


# ---------------------------------------------------------------------------
# コーラーターン: 質問をオウム返しせず「答える」
# ---------------------------------------------------------------------------
def test_call_turn_answers_without_echoing_the_question(monkeypatch):
    captured = {}
    monkeypatch.setattr(proxy, "call_asr", lambda a: {"text": "あなたは本物ですか？"})

    def _brain(system, messages):
        captured["system"] = system
        captured["messages"] = messages
        return {"text": "窓の雨と同じくらいには、本物のつもりですよ。", "mood": "warm", "arc_cue": "none"}

    monkeypatch.setattr(proxy, "call_brain", _brain)
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    out = proxy.call_turn("oblivious", 0, "<b64>")
    # 素のラジオ局のホストプロンプト（DJ を名指す）。アークビルダーではない。
    assert arc.DJ_NAME in captured["system"]
    # USER ターンは回答指示であり、質問の生エコーではない
    user = captured["messages"][-1]["content"]
    assert "繰り返さない" in user
    assert user.strip() != "あなたは本物ですか？"
    assert out["caller_text"] == "あなたは本物ですか？"
    assert out["meter_delta"] >= 14  # リアリティ質問はメーターを大きく進める


def test_call_turn_degenerate_uses_caller_fallback_not_crash(monkeypatch):
    monkeypatch.setattr(proxy, "call_asr", lambda a: {"text": "聞こえてますか？"})
    monkeypatch.setattr(proxy, "call_brain",
                        lambda s, m: {"text": "曲名: X、アーティスト: Y", "mood": "warm", "arc_cue": "none"})
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    out = proxy.call_turn("oblivious", 0, "<b64>")
    assert out["text"] in content.CALLER_FALLBACKS


def test_broadcast_turn_uses_host_path_and_sanitizes(monkeypatch):
    captured = {}

    def _brain(system, messages):
        captured["system"] = system
        return {"text": "アーティスト: X", "mood": "warm", "arc_cue": "none"}  # degenerate

    monkeypatch.setattr(proxy, "call_brain", _brain)
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    out = proxy.broadcast_turn("oblivious", 0, None)
    assert arc.DJ_NAME in captured["system"]
    assert out["text"] in content.THOUGHTS
    assert out["arc_cue"] == "none"


# ---------------------------------------------------------------------------
# セッションメモリ（SP1）: 日本語 ASR テキストからの決定的抽出
# ---------------------------------------------------------------------------
def test_extract_name_place():
    assert proxy._extract_name("こんばんは、私はミラです。眠れなくて。") == "ミラ"
    assert proxy._extract_name("田中と申します、いつも聴いています") == "田中"
    assert proxy._extract_name("ただ挨拶したかっただけです") is None
    assert proxy._extract_place("札幌市から聴いています") == "札幌市"
    assert proxy._extract_place("こんばんは") is None


def test_caller_gist():
    assert proxy._caller_gist("眠れない夜はどうしたらいいですか") is not None
    assert proxy._caller_gist("はい") is None
    assert proxy._caller_gist("") is None
    assert proxy._caller_gist(None) is None


def test_build_memory_patch():
    p = proxy._build_memory_patch("私はミラです。長野県から、眠れなくて電話しました", "tender")
    assert p is not None
    assert p["caller_name"] == "ミラ"
    assert p["mood"] == "tender"
    assert p["topic"]
    assert proxy._build_memory_patch("はい", "warm") is None
    # 不正な mood は warm へ
    p2 = proxy._build_memory_patch("眠れない夜はどうしたらいいですか", "no-such-mood")
    assert p2["mood"] == "warm"


def test_call_turn_returns_memory_patch(monkeypatch):
    monkeypatch.setattr(proxy, "call_asr",
                        lambda a: {"text": "私はミラです。最近、夜が長く感じるんです"})
    monkeypatch.setattr(proxy, "call_brain",
                        lambda s, m: {"text": "夜が長いぶん、この放送も長く付き合いますよ。",
                                      "mood": "tender", "arc_cue": "none"})
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    out = proxy.call_turn("oblivious", 0, "<b64>")
    assert out["memory_patch"] is not None
    assert out["memory_patch"]["caller_name"] == "ミラ"
    assert out["queue_dedication"] is True


def test_call_turn_no_memory_on_short_caller(monkeypatch):
    monkeypatch.setattr(proxy, "call_asr", lambda a: {"text": "はい"})
    monkeypatch.setattr(proxy, "call_brain",
                        lambda s, m: {"text": "回線の向こうの静けさも、夜の一部ですね。",
                                      "mood": "warm", "arc_cue": "none"})
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    out = proxy.call_turn("oblivious", 0, "<b64>")
    assert out["memory_patch"] is None
    assert out["queue_dedication"] is False


# ---------------------------------------------------------------------------
# メモリ献呈 / 曲イントロ / ゴースト断片
# ---------------------------------------------------------------------------
def test_segment_dedication_memory_aware(monkeypatch):
    captured = {}

    def _brain(system, messages):
        captured["user"] = messages[-1]["content"]
        return {"text": "次の一曲は、夜の長いミラさんへ。ゆっくり効いてきますように。",
                "mood": "tender", "arc_cue": "none"}

    monkeypatch.setattr(proxy, "call_brain", _brain)
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    out = proxy.segment_turn("dedication",
                             {"topic": "最近、夜が長く感じる", "caller_name": "ミラ", "mood": "tender"})
    assert "ミラ" in captured["user"]
    assert "最近、夜が長く感じる" in captured["user"]
    assert out["text"]


def test_segment_dedication_no_memory_is_templated(monkeypatch):
    # topic が無ければモデルを呼ばずテンプレの献呈
    def _boom(s, m):
        raise AssertionError("brain should not be called")
    monkeypatch.setattr(proxy, "call_brain", _boom)
    out = proxy.segment_turn("dedication", {})
    assert "次の一曲は" in out["text"]


def test_segment_dedication_junk_falls_back_to_name(monkeypatch):
    monkeypatch.setattr(proxy, "call_brain",
                        lambda s, m: {"text": "<一文目>", "mood": "warm", "arc_cue": "none"})
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    out = proxy.segment_turn("dedication", {"topic": "眠れない", "caller_name": "ミラ"})
    assert "ミラ" in out["text"]


def test_song_intro_weaves_segue(monkeypatch):
    captured = {}

    def _brain(system, messages):
        captured["user"] = messages[-1]["content"]
        return {"text": "その静けさのつづきに、ちょうどいい一枚があります。",
                "mood": "warm", "arc_cue": "none"}

    monkeypatch.setattr(proxy, "call_brain", _brain)
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    proxy.segment_turn("song_intro",
                       {"title": "電話線", "artist": "火曜日の幽霊たち",
                        "vibe": "pensive", "segue": "さっきの静けさの話から"})
    assert "さっきの静けさの話から" in captured["user"]
    assert "電話線" in captured["user"]
    # vibe は日本語化されて発話プロンプトに乗る
    assert proxy.vibe_ja("pensive") in captured["user"]


def test_song_intro_no_segue_when_absent(monkeypatch):
    captured = {}

    def _brain(system, messages):
        captured["user"] = messages[-1]["content"]
        return {"text": "続いては、あの火曜日の幽霊たちの一枚です。", "mood": "warm", "arc_cue": "none"}

    monkeypatch.setattr(proxy, "call_brain", _brain)
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    proxy.segment_turn("song_intro", {"title": "電話線", "artist": "火曜日の幽霊たち"})
    assert "つなぎ" not in captured["user"]


def test_fragment_user_mentions_another_station():
    u = proxy._fragment_user({})
    assert "別の局" in u


def test_segment_fragment_is_persona_free(monkeypatch):
    captured = {}

    def _brain(system, messages):
        captured["system"] = system
        return {"text": "割り当てのない周波数から、こんばんは。", "mood": "uneasy", "arc_cue": "static_swell"}

    monkeypatch.setattr(proxy, "call_brain", _brain)
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    out = proxy.segment_turn("fragment", {})
    # ゴースト断片はホストペルソナを使わない（契約ブロックの DJ 名言及は残る）
    assert arc.HOST_PERSONA not in captured["system"]
    assert "別の局" in captured["system"]
    assert out["kind"] == "fragment"


def test_segment_fragment_junk_falls_back(monkeypatch):
    monkeypatch.setattr(proxy, "call_brain",
                        lambda s, m: {"text": "[stage direction]", "mood": "uneasy", "arc_cue": "none"})
    monkeypatch.setattr(proxy, "call_speak",
                        lambda text, voice=arc.VOICE: {"audio_b64": "", "words": [],
                                                       "wtimes": [], "wdurations": []})
    out = proxy.segment_turn("fragment", {})
    assert out["text"] in content.FRAGMENTS


# ---------------------------------------------------------------------------
# 生成レコードカード（SP3）
# ---------------------------------------------------------------------------
def test_parse_title_artist_formats():
    assert proxy._parse_title_artist("雨のテールランプ / 眠らない高架橋") == \
        ("雨のテールランプ", "眠らない高架橋")
    assert proxy._parse_title_artist("『砂時計の駅』／ 紙のカーディガン") == \
        ("砂時計の駅", "紙のカーディガン")
    assert proxy._parse_title_artist("ただのおしゃべりで形式に従わない") == (None, None)
    assert proxy._parse_title_artist("曲名: X / Y" * 20) == (None, None)  # 長すぎ
    assert proxy._parse_title_artist("") == (None, None)


def test_parse_title_artist_trims_chatter():
    t, a = proxy._parse_title_artist("雨のテールランプ / 眠らない高架橋。お楽しみください！")
    assert t == "雨のテールランプ"
    assert a == "眠らない高架橋"


def test_make_song_card_always_valid_params(monkeypatch):
    # モデルがジャンクを返しても、カードの音楽パラメータは常に正当な enum
    monkeypatch.setattr(proxy, "call_brain",
                        lambda s, m: {"text": "こんな形式では答えられません", "mood": "warm", "arc_cue": "none"})
    card = proxy.make_song_card({"mood": "hollow"})
    assert card["scale"] in content.SCALES
    assert card["timbre"] in content.TIMBRES
    assert 60 <= card["tempo"] <= 90
    assert card["title"] and card["artist"]
    assert card["generated"] is True
    assert card["vibe"] == "lonely"  # hollow -> lonely（_MOOD_TO_VIBE）


def test_make_song_card_uses_model_title(monkeypatch):
    monkeypatch.setattr(proxy, "call_brain",
                        lambda s, m: {"text": "雨のテールランプ / 眠らない高架橋",
                                      "mood": "nostalgic", "arc_cue": "none"})
    card = proxy.make_song_card({"mood": "warm"})
    assert card["title"] == "雨のテールランプ"
    assert card["artist"] == "眠らない高架橋"


def test_vibe_ja_covers_all_vibes():
    for v in proxy._VIBE_MUSIC:
        assert proxy.vibe_ja(v) != "深夜らしい", "vibe %s の日本語が未定義" % v
    assert proxy.vibe_ja("no-such-vibe") == "深夜らしい"
    assert proxy.vibe_ja(None) == "深夜らしい"


def test_mood_to_vibe_targets_exist():
    for mood, vibe in proxy._MOOD_TO_VIBE.items():
        assert mood in arc.MOODS
        assert vibe in proxy._VIBE_MUSIC


# ---------------------------------------------------------------------------
# モック運転の形状
# ---------------------------------------------------------------------------
def test_mock_brain_asr_speak_shapes():
    assert proxy.is_mock()
    b = proxy.call_brain("sys", [{"role": "user", "content": "u"}])
    assert set(b.keys()) == {"text", "mood", "arc_cue"}
    assert b["mood"] in arc.MOODS
    a = proxy.call_asr("xxxx")
    assert "text" in a
    s = proxy.call_speak("こんばんは")
    for key in ("audio_b64", "words", "wtimes", "wdurations"):
        assert key in s
    assert s["audio_b64"]  # 無音でも実 WAV
