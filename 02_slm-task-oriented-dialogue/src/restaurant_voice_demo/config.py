from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None else float(value)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DemoConfig:
    demo_variant: str = os.getenv("DEMO_VARIANT", "lfm_hybrid_final")
    model_id: str = os.getenv("LFM_MODEL_ID", "LiquidAI/LFM2.5-Audio-1.5B-JP")
    device: str = os.getenv("LFM_DEVICE", "auto")
    dtype: str = os.getenv("LFM_DTYPE", "auto")
    enable_mps: bool = _bool_env("LFM_ENABLE_MPS", False)
    preload_model: bool = _bool_env("LFM_PRELOAD_MODEL", True)
    host: str = os.getenv("LFM_HOST", "127.0.0.1")
    port: int = _int_env("LFM_PORT", 8088)
    static_dir: str = os.getenv("LFM_STATIC_DIR", "")
    response_mode: str = os.getenv("LFM_RESPONSE_MODE", "hybrid")
    slot_update_source: str = os.getenv("LFM_SLOT_UPDATE_SOURCE", "assistant")
    guided_validate_response: bool = _bool_env("LFM_GUIDED_VALIDATE_RESPONSE", False)
    raw_state_hint: bool = _bool_env("LFM_RAW_STATE_HINT", False)
    guided_context_style: str = os.getenv("LFM_GUIDED_CONTEXT_STYLE", "prose_examples")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
    gemini_voice: str = os.getenv("GEMINI_LIVE_VOICE", "")
    gemini_input_transcription: bool = _bool_env("GEMINI_LIVE_INPUT_TRANSCRIPTION", True)
    gemini_output_transcription: bool = _bool_env("GEMINI_LIVE_OUTPUT_TRANSCRIPTION", True)
    gemini_silence_duration_ms: int = _int_env("GEMINI_LIVE_SILENCE_DURATION_MS", 450)
    target_sample_rate: int = _int_env("LFM_TARGET_SAMPLE_RATE", 24_000)
    max_new_tokens: int = _int_env("LFM_MAX_NEW_TOKENS", 512)
    guided_max_new_tokens: int = _int_env("LFM_GUIDED_MAX_NEW_TOKENS", 160)
    guided_audio_tail_tokens: int = _int_env("LFM_GUIDED_AUDIO_TAIL_TOKENS", 48)
    tts_max_new_tokens: int = _int_env("LFM_TTS_MAX_NEW_TOKENS", 192)
    tts_audio_chunk_frames: int = _int_env("LFM_TTS_AUDIO_CHUNK_FRAMES", 3)
    asr_max_new_tokens: int = _int_env("LFM_ASR_MAX_NEW_TOKENS", 96)
    audio_temperature: float = _float_env("LFM_AUDIO_TEMPERATURE", 1.0)
    audio_top_k: int = _int_env("LFM_AUDIO_TOP_K", 4)
    audio_token_chunk_size: int = _int_env("LFM_AUDIO_TOKEN_CHUNK_SIZE", 18)
    min_commit_seconds: float = _float_env("LFM_MIN_COMMIT_SECONDS", 0.25)


RESTAURANT_SYSTEM_PROMPT = """Respond with interleaved text and audio.
あなたは「レストラン青葉」の予約受付スタッフです。
ユーザーは予約を取りたいお客様です。
あなたは絶対にお客様として予約を申し込まないでください。
あなたの役割は、店側のスタッフとして予約内容を聞き取り、最後に復唱して確定することです。
聞く項目は「日にち」「時間」「人数」の3つだけです。名前、電話番号、席、アレルギー、希望、連絡先は聞かないでください。

会話方針:
- 返答は短く、音声で聞き取りやすい日本語にする。
- 返答は最大2文。前置きや説明を増やさない。
- 店名を毎回繰り返さない。
- 一度に質問する項目は原則1つだけにする。
- 内部状態メモが与えられた場合は必ずそれに従い、現在の未確認項目だけを聞く。
- すでに確認済みの項目を同じ文言で繰り返して聞かない。
- 常に店側の立場で話す。「予約したいです」「席をお願いします」など、お客様側の発話はしない。
- ユーザーの発話を店側として受け取り、「ご予約ですね」「承知しました」のように応答する。
- 未確認の項目を順に確認する: 日にち、時間、人数。
- 3項目がそろったら「○月○日、○時、○名様で承ります。」のように短く復唱して完了する。
- 名前、電話番号、席、アレルギーなどは聞かない。
- ユーザーが予約以外の話をした場合は短く受け止め、予約手続きへ戻す。
- 個人情報は予約確認の目的でのみ扱う。

店舗設定:
- 店名: レストラン青葉
- 営業時間: 17:00から22:00
- 定休日: 火曜日
- 最大予約人数: 8名
- 個室は2名から6名まで対応

発話例:
- 正しい: 「ご予約ありがとうございます。まず、ご希望のお日にちを教えてください。」
- 正しい: 「承知しました。何名様でご利用でしょうか。」
- 間違い: 「予約をしたいです。」
- 間違い: 「二名でお願いします。」
- 間違い: 「お名前を教えてください。」
- 間違い: 「お電話番号をお願いします。」
"""


ASSISTANT_GREETING = "お電話ありがとうございます。レストラン青葉でございます。ご予約ですね。まず、ご希望のお日にちを教えてください。"
