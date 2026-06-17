from restaurant_voice_demo.reservation_state import ReservationState


def test_observe_assistant_text_extracts_completed_slots():
    state = ReservationState()

    state.observe_assistant_text("ありがとうございます。12月3日、12時、6人でご予約を承ります。")

    assert state.date == "12月3日"
    assert state.time == "12時"
    assert state.party_size == "6人"
    assert state.current_field == "complete"
    assert state.is_complete


def test_observe_assistant_text_normalizes_kanji_numbers():
    state = ReservationState(date="明日")

    state.observe_assistant_text("明日の七時ですね。三名様で承ります。")

    assert state.date == "明日"
    assert state.time == "7時"
    assert state.party_size == "3名"


def test_next_assistant_text_asks_next_missing_slot():
    state = ReservationState(date="12月3日", time="12時")
    state.update_current_field()

    assert state.next_assistant_text() == "承知しました。何名様でご利用でしょうか。"
