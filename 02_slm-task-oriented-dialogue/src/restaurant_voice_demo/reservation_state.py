from __future__ import annotations

import re
from dataclasses import asdict, dataclass


FIELDS = ("date", "time", "party_size")
FIELD_LABELS = {
    "date": "日にち",
    "time": "時間",
    "party_size": "人数",
    "complete": "完了",
}

_KANJI_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NUM = r"[0-9０-９一二三四五六七八九十]+"
_DATE_RE = re.compile(
    rf"(今日|本日|明日|明後日|あさって|{_NUM}\s*月\s*{_NUM}\s*日|{_NUM}\s*/\s*[0-9０-９]{{1,2}}|"
    r"来週[の日月火水木金土]曜?日?|[月火水木金土日]曜日?)"
)
_TIME_RE = re.compile(rf"(?:(午前|午後|朝|昼|夕方|夜)\s*)?({_NUM})\s*時\s*(半|{_NUM}\s*分)?")
_CLOCK_RE = re.compile(r"[0-9０-９]{1,2}\s*:\s*[0-9０-９]{2}")
_TIME_WORD_RE = re.compile(r"(ランチ|ディナー|昼|夜|夕方)")
_PARTY_RE = re.compile(rf"({_NUM})\s*(名|人)(?:様|さま)?")


def _z2h(text: str) -> str:
    return text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def _to_int(text: str) -> int | None:
    normalized = _z2h(text).replace(" ", "")
    if normalized.isdigit():
        return int(normalized)

    match = re.fullmatch(r"([一二三四五六七八九]?)(十?)([一二三四五六七八九]?)", normalized)
    if not match or not normalized:
        return None
    tens, ten, ones = match.groups()
    if ten:
        return (_KANJI_DIGITS.get(tens, 1) * 10) + _KANJI_DIGITS.get(ones, 0)
    if not tens:
        return None
    return _KANJI_DIGITS[tens]


@dataclass
class ReservationState:
    date: str | None = None
    time: str | None = None
    party_size: str | None = None
    current_field: str = "date"
    turns: int = 0

    def as_payload(self) -> dict[str, str | int | bool | None]:
        payload = asdict(self)
        payload["complete"] = self.is_complete
        payload["missing"] = self.missing_fields
        return payload

    @property
    def is_complete(self) -> bool:
        return all(getattr(self, field) for field in FIELDS)

    @property
    def missing_fields(self) -> list[str]:
        return [field for field in FIELDS if not getattr(self, field)]

    def update_current_field(self) -> None:
        self.current_field = self.missing_fields[0] if self.missing_fields else "complete"

    def observe_turn(self, assistant_text: str) -> None:
        self.turns += 1
        self.observe_assistant_text(assistant_text, increment_turn=False)

    def observe_assistant_text(self, assistant_text: str, *, increment_turn: bool = True) -> None:
        if increment_turn:
            self.turns += 1

        date = _extract_date(assistant_text)
        time = _extract_time(assistant_text)
        party_size = _extract_party_size(assistant_text)

        if date:
            self.date = date
        if time:
            self.time = time
        if party_size:
            self.party_size = party_size
        self.update_current_field()

    def observe_user_text(self, user_text: str) -> None:
        date = _extract_date(user_text)
        time = _extract_time(user_text)
        party_size = _extract_party_size(user_text)

        if date:
            self.date = date
        if time:
            self.time = time
        if party_size:
            self.party_size = party_size
        self.update_current_field()

    def update_slots(
        self,
        *,
        date: str | None = None,
        time: str | None = None,
        party_size: str | int | None = None,
    ) -> None:
        if date:
            self.date = str(date).strip()
        if time:
            self.time = str(time).strip()
        if party_size:
            value = str(party_size).strip()
            self.party_size = value if value.endswith(("名", "人")) else f"{value}名"
        self.update_current_field()

    def observe_text(self, text: str) -> None:
        self.observe_assistant_text(text)

    def prompt_context(self) -> str:
        if self.is_complete:
            next_action = "次の応答: 新しい質問は禁止。日にち・時間・人数を短く復唱して完了。"
        else:
            next_label = FIELD_LABELS[self.current_field]
            next_action = f"次の応答: 「{next_label}」だけを質問。確認済み項目、名前、電話番号、席、アレルギーは禁止。"
        return (
            f"予約状態 日にち={self.date or '未確認'}, 時間={self.time or '未確認'}, "
            f"人数={self.party_size or '未確認'}。{next_action} 1文で応答。"
        )

    def grounded_prompt_context(self) -> str:
        if self.is_complete:
            next_action = "現在のお客様の予約内容を、日にち・時間・人数だけで短く復唱して完了。新しい質問は禁止。"
        else:
            next_label = FIELD_LABELS[self.current_field]
            next_action = (
                f"ユーザー音声から「{next_label}」が聞き取れた場合は、その値を必ず復唱してから次の未確認項目を質問。"
                f"聞き取れない場合だけ「{next_label}」を聞き直す。"
            )
        return (
            f"現在のお客様の予約状態: 日にち={self.date or '未確認'}, 時間={self.time or '未確認'}, "
            f"人数={self.party_size or '未確認'}。{next_action} "
            "未確認の値は絶対に作らない。聞き取った値は発話文に含める。"
            "値だけで返答を終えてはいけない。予約完了前は必ず次の未確認項目を質問する。"
        )

    def next_assistant_text(self) -> str:
        if not self.date:
            return "ご予約ですね。ご希望のお日にちを教えてください。"
        if not self.time:
            return "ありがとうございます。ご希望の時間を教えてください。"
        if not self.party_size:
            return "承知しました。何名様でご利用でしょうか。"
        return f"ありがとうございます。{self.date}、{self.time}、{self.party_size}でご予約を承ります。"


def _extract_date(text: str) -> str | None:
    match = _DATE_RE.search(text)
    if match:
        return _z2h(match.group(0)).replace(" ", "")
    return None


def _extract_time(text: str) -> str | None:
    if match := _TIME_RE.search(text):
        prefix = match.group(1) or ""
        hour = _to_int(match.group(2))
        suffix = (match.group(3) or "").replace(" ", "")
        if hour is not None and 0 <= hour <= 24:
            if suffix == "半":
                return f"{prefix}{hour}時半"
            if suffix.endswith("分"):
                minute = _to_int(suffix[:-1])
                if minute is not None and 0 <= minute <= 59:
                    return f"{prefix}{hour}時{minute}分"
            return f"{prefix}{hour}時"
    if match := _CLOCK_RE.search(text):
        return _z2h(match.group(0)).replace(" ", "")
    if match := _TIME_WORD_RE.search(text):
        return match.group(0)
    return None


def _extract_party_size(text: str) -> str | None:
    if match := _PARTY_RE.search(text):
        count = _to_int(match.group(1))
        if count is not None and 1 <= count <= 100:
            return f"{count}{match.group(2)}"
    return None
