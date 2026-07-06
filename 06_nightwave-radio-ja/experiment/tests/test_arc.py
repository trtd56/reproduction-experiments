"""nightwave_ja/arc.py の pytest スイート（オリジナル test_arc.py の日本語移植）。"""

import arc


# ---------------------------------------------------------------------------
# meter_to_stage の境界
# ---------------------------------------------------------------------------
def test_meter_to_stage_boundaries():
    assert arc.meter_to_stage(0) == "oblivious"
    assert arc.meter_to_stage(19) == "oblivious"
    assert arc.meter_to_stage(20) == "uneasy"
    assert arc.meter_to_stage(39) == "uneasy"
    assert arc.meter_to_stage(40) == "questioning"
    assert arc.meter_to_stage(59) == "questioning"
    assert arc.meter_to_stage(60) == "dawning"
    assert arc.meter_to_stage(79) == "dawning"
    assert arc.meter_to_stage(80) == "acceptance"
    assert arc.meter_to_stage(100) == "acceptance"


def test_meter_to_stage_full_sweep_is_monotonic():
    order = ["oblivious", "uneasy", "questioning", "dawning", "acceptance"]
    last_idx = 0
    for m in range(0, 101):
        stage = arc.meter_to_stage(m)
        idx = order.index(stage)
        assert idx >= last_idx, "stage went backwards at meter=%d" % m
        last_idx = idx


# ---------------------------------------------------------------------------
# STAGES テーブルの整合性
# ---------------------------------------------------------------------------
def test_stages_table_shape():
    assert [s["key"] for s in arc.STAGES] == [
        "oblivious", "uneasy", "questioning", "dawning", "acceptance",
    ]
    for s in arc.STAGES:
        assert set(s.keys()) >= {
            "key", "lo", "hi", "descriptor", "default_mood", "sample_lines",
        }
        assert s["default_mood"] in arc.MOODS
        assert s["descriptor"].strip()
        assert len(s["sample_lines"]) >= 3


def test_stages_meter_ranges_are_contiguous():
    prev_hi = -1
    for s in arc.STAGES:
        assert s["lo"] == prev_hi + 1
        assert s["hi"] >= s["lo"]
        prev_hi = s["hi"]
    assert arc.STAGES[-1]["hi"] == 100


def test_stage_default_mood():
    assert arc.stage_default_mood("oblivious") == "warm"
    assert arc.stage_default_mood("uneasy") == "uneasy"
    assert arc.stage_default_mood("questioning") == "searching"
    assert arc.stage_default_mood("dawning") == "hollow"
    assert arc.stage_default_mood("acceptance") == "tender"
    assert arc.stage_default_mood("no-such-stage") == "warm"


def test_constants():
    assert arc.PERSONA_NAME == "NIGHTWAVE"
    assert set(arc.MOODS) == {"warm", "nostalgic", "uneasy", "searching", "hollow", "tender"}
    assert set(arc.ARC_CUES) == {"none", "glitch", "static_swell", "direct_address"}
    assert arc.TIME_DRIP_PER_MIN > 0


def test_dj_name_in_persona():
    # 日本語版の DJ は宵野サム。ホストペルソナが名乗れること。
    assert arc.DJ_NAME == "宵野サム"
    assert arc.DJ_NAME in arc.HOST_PERSONA
    assert arc.PERSONA_NAME in arc.HOST_PERSONA


# ---------------------------------------------------------------------------
# システムプロンプトの組み立て
# ---------------------------------------------------------------------------
def test_build_system_prompt_broadcast_contains_descriptor_and_contract():
    for s in arc.STAGES:
        p = arc.build_system_prompt(s["key"], "broadcast")
        assert s["descriptor"][:20] in p
        assert '"text"' in p and '"mood"' in p and '"arc_cue"' in p
        assert "JSONオブジェクトを1つだけ" in p
        assert s["default_mood"] in p


def test_build_system_prompt_caller_contains_descriptor_and_contract():
    p = arc.build_system_prompt("questioning", "caller", caller_text="あなたは本物ですか？")
    assert "あなたは本物ですか？" in p
    assert '"arc_cue"' in p
    # コーラーモードは放送へ戻る指示を含む
    assert "放送へ戻る" in p


def test_build_host_prompt_all_kinds_have_contract():
    for kind in ("thought", "on_air", "song_intro", "caller", "dedication", "local_weather"):
        p = arc.build_host_prompt(kind)
        assert arc.DJ_NAME in p
        assert '"text"' in p and '"mood"' in p and '"arc_cue"' in p


def test_build_host_prompt_local_weather_is_distinct():
    p = arc.build_host_prompt("local_weather")
    assert "予報のように" in p


def test_build_fragment_prompt():
    p = arc.build_fragment_prompt()
    # ゴースト断片は宵野サムでも NIGHTWAVE のホストでもない
    assert "宵野サムでも" in p
    assert '"arc_cue"' in p


def test_build_host_prompt_dedication():
    p = arc.build_host_prompt("dedication")
    assert "献呈" in p


def test_build_system_prompt_broadcast_uses_topic():
    p = arc.build_system_prompt("oblivious", "broadcast", topic="眠れない夜のコーヒー")
    assert "眠れない夜のコーヒー" in p


def test_build_system_prompt_broadcast_no_topic_invents():
    p = arc.build_system_prompt("oblivious", "broadcast")
    assert "架空のレコード" in p


def test_build_system_prompt_caller_empty_text_is_graceful():
    p = arc.build_system_prompt("oblivious", "caller", caller_text="")
    assert "聞き取れませんでした" in p


def test_build_system_prompt_unknown_stage_defaults_to_oblivious():
    p_unknown = arc.build_system_prompt("no-such-stage", "broadcast")
    p_oblivious = arc.build_system_prompt("oblivious", "broadcast")
    assert p_unknown == p_oblivious


# ---------------------------------------------------------------------------
# トリガー検出（日本語）
# ---------------------------------------------------------------------------
def test_detect_triggers_reality():
    assert arc.detect_triggers("あなたは本物ですか？") == 14
    assert arc.detect_triggers("もしかしてAIなの？") == 14
    assert arc.detect_triggers("あなたはロボットでしょう") == 14
    assert arc.detect_triggers("人工知能ですよね") == 14


def test_detect_triggers_identity():
    assert arc.detect_triggers("あなたの名前を教えてください") == 14
    assert arc.detect_triggers("あなたは誰なんですか") == 14
    assert arc.detect_triggers("お名前は？") == 14


def test_detect_triggers_station():
    assert arc.detect_triggers("スタジオはどこにあるんですか") == 14
    assert arc.detect_triggers("局の住所を教えて") == 14
    assert arc.detect_triggers("どこから放送してるの？") == 14


def test_detect_triggers_generic_question():
    assert arc.detect_triggers("今夜は雨が降りますか？") == 5
    assert arc.detect_triggers("なぜ夜は静かなんでしょう") == 5
    assert arc.detect_triggers("おすすめの曲を教えて") == 5


def test_detect_triggers_non_question():
    assert arc.detect_triggers("こんばんは、いつも聴いています。") == 0
    assert arc.detect_triggers("") == 0
    assert arc.detect_triggers(None) == 0


def test_detect_triggers_clamped():
    # 複合トリガーでも 0..30 に収まる
    d = arc.detect_triggers("あなたは本物？名前は？スタジオはどこ？")
    assert 0 <= d <= 30
