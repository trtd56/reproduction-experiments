"""nightwave_ja/content.py の整合性テスト（オリジナル test_content.py の移植）。"""

import arc
import content


def test_song_recs_well_formed():
    titles = {s["title"] for s in content.SONGS}
    for title, handle in content.SONG_RECS.items():
        assert title in titles, "SONG_RECS の曲名が SONGS に無い: %s" % title
        assert handle.startswith("@") and len(handle) > 2


def test_rejoins_name_the_dj():
    for line in content.REJOINS:
        assert arc.DJ_NAME in line


def test_caller_intros_nonempty():
    assert len(content.CALLER_INTROS) >= 3
    for line in content.CALLER_INTROS:
        assert line.strip()


def test_songs_have_required_fields_and_valid_enums():
    assert len(content.SONGS) >= 24
    seen = set()
    for s in content.SONGS:
        assert s["title"].strip() and s["artist"].strip()
        assert s["title"] not in seen, "曲名の重複: %s" % s["title"]
        seen.add(s["title"])
        assert s["scale"] in content.SCALES
        assert s["timbre"] in content.TIMBRES
        assert 60 <= s["tempo"] <= 90
        assert "recommended_by" in s
        assert isinstance(s["vibe"], str) and s["vibe"]
        # vibe はクライアントの MOOD_VIBES 選曲フィルタとの契約で英語キーのまま
        assert s["vibe"].isascii(), "vibe は英語キーであること: %s" % s["vibe"]


def test_other_banks_nonempty_and_shaped():
    assert len(content.STATION_IDS) >= 3
    assert all("NIGHTWAVE" in s for s in content.STATION_IDS)
    assert len(content.WEATHER) >= 3
    assert len(content.THOUGHTS) >= 3
    assert len(content.FRAGMENTS) >= 5
    assert len(content.CALLER_FALLBACKS) >= 3
    for d in content.DEDICATIONS:
        assert d["name"].strip() and d["message"].strip()
    assert content.SONIC_LOGO.startswith("NIGHTWAVE")
    assert content.CARD_TITLE_A and content.CARD_TITLE_B
    assert content.CARD_ARTIST_A and content.CARD_ARTIST_B
