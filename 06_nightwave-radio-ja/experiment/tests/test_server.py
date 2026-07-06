"""nightwave_ja/server.py の API テスト（モック運転、TestClient）。"""

from fastapi.testclient import TestClient

import arc
import content
import server


def _client():
    return TestClient(server.create_api())


def test_api_locale_mock():
    c = _client()
    r = c.post("/api/locale", json={"lat": 35.0, "lon": 139.0})
    assert r.status_code == 200
    j = r.json()
    assert j["resolved"] is True
    assert j["city"] == "灯里町"


def test_api_locale_bad_body_still_safe():
    c = _client()
    r = c.post("/api/locale", json={"lat": "junk"})
    # pydantic のバリデーションエラー（422）で落ちるだけで、500 にはならない
    assert r.status_code in (200, 422)


def test_fallback_payload_has_memory_keys():
    p = server._fallback_payload("oblivious", include_caller=True)
    for key in ("caller_text", "meter_delta", "memory_patch", "queue_dedication",
                "text", "mood", "arc_cue", "audio_b64"):
        assert key in p
    assert p["mood"] in arc.MOODS


def test_api_songs_serves_content_bank():
    c = _client()
    r = c.get("/api/songs")
    assert r.status_code == 200
    songs = r.json()["songs"]
    assert len(songs) == len(content.SONGS)
    assert songs[0]["title"]


def test_api_seek_maps_meter():
    c = _client()
    r = c.post("/api/seek", json={"meter": 85})
    assert r.json()["stage"] == "acceptance"


def test_api_broadcast_mock_shape():
    c = _client()
    r = c.post("/api/broadcast", json={"stage": "oblivious", "meter": 0})
    assert r.status_code == 200
    j = r.json()
    for key in ("text", "mood", "arc_cue", "audio_b64", "words", "wtimes", "wdurations"):
        assert key in j


def test_api_call_mock_shape():
    c = _client()
    r = c.post("/api/call", json={"stage": "oblivious", "meter": 0, "audio_b64": "xxxx"})
    assert r.status_code == 200
    j = r.json()
    for key in ("caller_text", "text", "meter_delta", "memory_patch", "queue_dedication"):
        assert key in j


def test_api_segment_mock_never_500(monkeypatch):
    import proxy
    c = _client()

    def _boom(kind, ctx=None):
        raise RuntimeError("engine down")

    monkeypatch.setattr(proxy, "segment_turn", _boom)
    r = c.post("/api/segment", json={"kind": "thought"})
    assert r.status_code == 200
    j = r.json()
    assert j["text"] in content.THOUGHTS
    assert j["audio_b64"]


def test_api_song_card_failure_returns_none(monkeypatch):
    import proxy
    c = _client()

    def _boom(ctx=None):
        raise RuntimeError("engine down")

    monkeypatch.setattr(proxy, "make_song_card", _boom)
    r = c.post("/api/song_card", json={"ctx": {}})
    assert r.status_code == 200
    assert r.json()["card"] is None
