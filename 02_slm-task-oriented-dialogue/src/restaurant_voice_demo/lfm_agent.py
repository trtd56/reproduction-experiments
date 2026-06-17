from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

import numpy as np

from .audio import float32_pcm_to_bytes, float32_pcm_to_wav_bytes, normalize_peak, resample_pcm
from .config import ASSISTANT_GREETING, DemoConfig, RESTAURANT_SYSTEM_PROMPT


TEXT_END_MARKER = "<|text_end|>"
IM_END_MARKER = "<|im_end|>"
SPECIAL_TEXT_MARKERS = (TEXT_END_MARKER, IM_END_MARKER)

GUIDED_SYSTEM_PROMPT = """Respond with interleaved text and audio.
あなたはレストラン青葉の予約受付スタッフです。
ユーザーは予約を取りたいお客様です。あなたは店側として応答します。
聞く項目は「日にち」「時間」「人数」の3つだけです。
現在のお客様の予約状態メモだけを真実として扱ってください。
過去の例に出てくる日付、時間、人数を現在のお客様に使ってはいけません。
未確認の項目を勝手に埋めてはいけません。
ユーザー音声から日にち・時間・人数が聞き取れた場合は、その値を必ず短く復唱してください。
復唱した値だけが予約状態として抽出されます。
予約完了前は、値の復唱だけで終わらず、必ず次の未確認項目を質問してください。
名前、電話番号、席、アレルギー、連絡先は聞いてはいけません。
返答は短く、1文または2文の自然な日本語にしてください。"""

GUIDED_FEW_SHOT_TURNS: tuple[tuple[str, str], ...] = (
    ("user", "予約したいです"),
    ("assistant", "ご予約ですね。ご希望のお日にちを教えてください。"),
    ("user", "明日でお願いします"),
    ("assistant", "明日ですね。ご希望の時間を教えてください。"),
    ("user", "18時で"),
    ("assistant", "18時ですね。何名様でご利用でしょうか。"),
    ("user", "2名です"),
    ("assistant", "ありがとうございます。明日、18時、2名様でご予約を承ります。"),
    ("user", "予約をお願いします"),
    ("assistant", "ご希望のお日にちを教えてください。"),
    ("user", "金曜日です"),
    ("assistant", "金曜日ですね。ご希望の時間を教えてください。"),
    ("user", "夜で"),
    ("assistant", "夜ですね。何名様でご利用でしょうか。"),
)

FAKE_HISTORY_TURNS: tuple[tuple[str, str], ...] = (
    ("system", "（新しいお客様からの電話です）"),
    ("user", "もしもし、予約できますか？"),
    ("assistant", "お電話ありがとうございます。レストラン青葉でございます。ご希望のお日にちはいつでしょうか？"),
    ("user", "来週の土曜日にお願いします。"),
    ("assistant", "来週の土曜日ですね。お時間は何時頃がよろしいでしょうか？"),
    ("user", "12時に3人で。"),
    ("assistant", "12時に3名様ですね。ご予約を承ります。"),
    ("system", "（新しいお客様からの電話です）"),
    ("user", "予約をお願いしたいんですが。"),
    ("assistant", "かしこまりました。ご希望のお日にちを教えてください。"),
    ("user", "今月の25日、20時から5人です。"),
    ("assistant", "25日の20時に5名様ですね。ご予約を承ります。"),
    ("system", "（新しいお客様からの電話です）"),
)


@dataclass
class TextEvent:
    text: str


@dataclass
class AudioEvent:
    pcm: bytes
    sample_rate: int


@dataclass
class StatusEvent:
    status: str
    detail: str = ""


class TextStreamFilter:
    def __init__(self, markers: tuple[str, ...]) -> None:
        self.markers = markers
        self.buffer = ""
        self.ended = False
        self.ended_marker: str | None = None

    def push(self, fragment: str) -> str:
        if self.ended:
            return ""

        self.buffer += fragment
        marker_match = self._first_marker_match()
        if marker_match is not None:
            marker_index, marker = marker_match
            visible = self.buffer[:marker_index]
            self.buffer = ""
            self.ended = True
            self.ended_marker = marker
            return visible

        keep = self._partial_marker_suffix_length()
        if keep == 0:
            visible = self.buffer
            self.buffer = ""
            return visible

        visible = self.buffer[:-keep]
        self.buffer = self.buffer[-keep:]
        return visible

    def flush(self) -> str:
        if self.ended:
            return ""
        visible = _visible_text(self.buffer)
        self.buffer = ""
        return visible

    def _first_marker_match(self) -> tuple[int, str] | None:
        matches = [(index, marker) for marker in self.markers if (index := self.buffer.find(marker)) != -1]
        return min(matches, key=lambda match: match[0]) if matches else None

    def _partial_marker_suffix_length(self) -> int:
        max_suffix = min(len(self.buffer), max(len(marker) for marker in self.markers) - 1)
        for size in range(max_suffix, 0, -1):
            suffix = self.buffer[-size:]
            if any(marker.startswith(suffix) for marker in self.markers):
                return size
        return 0


def _resolve_device(requested: str, *, enable_mps: bool) -> str:
    if requested != "auto":
        return requested

    import torch

    if torch.cuda.is_available():
        return "cuda"
    if enable_mps and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _resolve_dtype(requested: str, device: str) -> Any:
    import torch

    if requested != "auto":
        dtype = getattr(torch, requested, None)
        if dtype is None:
            msg = f"Unknown torch dtype: {requested}"
            raise ValueError(msg)
        return dtype
    if device == "cuda":
        return torch.bfloat16
    if device == "mps":
        return torch.float16
    return torch.float32


def _tree_to_device(value: Any, device: str) -> Any:
    import torch

    if torch.is_tensor(value):
        return value.to(device)
    if isinstance(value, dict):
        return {key: _tree_to_device(item, device) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_tree_to_device(item, device) for item in value)
    if isinstance(value, list):
        return [_tree_to_device(item, device) for item in value]
    return value


def _chat_kwargs(chat: Any) -> dict[str, Any]:
    try:
        return dict(chat)
    except (TypeError, ValueError):
        return {key: chat[key] for key in chat.keys()}


class LFMRuntime:
    def __init__(self, config: DemoConfig) -> None:
        self.config = config
        self.device = _resolve_device(config.device, enable_mps=config.enable_mps)
        self.dtype = _resolve_dtype(config.dtype, self.device)
        self._load_lock = threading.Lock()
        self._loaded = False
        self.processor = None
        self.mimi = None
        self.model = None
        self.ChatState = None
        self.LFMModality = None

    def load(self) -> None:
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded:
                return

            import torch
            from liquid_audio import ChatState, LFM2AudioModel, LFM2AudioProcessor, LFMModality

            processor = LFM2AudioProcessor.from_pretrained(self.config.model_id, device="cpu").eval()
            try:
                mimi = processor.mimi.eval()
            except AttributeError:
                mimi = None
            processor.to(self.device).eval()
            self._load_detokenizer_without_cuda(processor)
            model = LFM2AudioModel.from_pretrained(
                self.config.model_id,
                device=self.device,
                dtype=self.dtype,
            ).eval()

            self.processor = processor
            self.mimi = mimi
            self.model = model
            self.ChatState = ChatState
            self.LFMModality = LFMModality
            self._loaded = True

            if self.device == "cuda":
                torch.cuda.empty_cache()

    def new_session(self) -> "RestaurantVoiceSession":
        self.load()
        return RestaurantVoiceSession(self)

    def decode_audio_frame(self, audio_token: Any) -> np.ndarray:
        import torch

        if self.mimi is None or (audio_token == 2048).any():
            return np.zeros(0, dtype=np.float32)
        audio_codes = audio_token.detach().cpu()[None, :, None]
        with torch.no_grad():
            waveform = self.mimi.decode(audio_codes)
        return waveform.detach().cpu().numpy().reshape(-1).astype(np.float32)

    def _load_detokenizer_without_cuda(self, processor: Any) -> None:
        if self.device == "cuda" or getattr(processor, "detokenizer_path", None) is None:
            return

        from pathlib import Path
        from typing import Literal, assert_never

        import torch
        from safetensors.torch import load_file
        from transformers import Lfm2Config

        from liquid_audio.detokenizer import LFM2AudioDetokenizer

        detok_config_path = Path(processor.detokenizer_path) / "config.json"
        detok_config = Lfm2Config.from_pretrained(detok_config_path)

        def rename_layer(layer: Literal["conv", "sliding_attention", "full_attention"]) -> Literal["conv", "full_attention"]:
            match layer:
                case "conv" | "full_attention":
                    return layer
                case "sliding_attention":
                    return "full_attention"
                case _:
                    assert_never(layer)

        if isinstance(detok_config.layer_types, list):
            detok_config.layer_types = [rename_layer(layer) for layer in detok_config.layer_types]  # type: ignore[arg-type]

        detok = LFM2AudioDetokenizer(detok_config).eval().to(device=self.device, dtype=self.dtype)
        detok_weights_path = Path(processor.detokenizer_path) / "model.safetensors"
        detok_weights = load_file(detok_weights_path, device="cpu")
        detok.load_state_dict(detok_weights)
        detok.eval()
        processor._audio_detokenizer = detok


class RestaurantVoiceSession:
    def __init__(self, runtime: LFMRuntime) -> None:
        self.runtime = runtime
        self.config = runtime.config
        self._generation_lock = threading.Lock()
        self.chat = None
        self.reset()

    def reset(self) -> None:
        chat = self.runtime.ChatState(self.runtime.processor)
        chat.new_turn("system")
        chat.add_text(RESTAURANT_SYSTEM_PROMPT)
        chat.end_turn()
        chat.new_turn("assistant")
        chat.add_text(ASSISTANT_GREETING)
        chat.end_turn()
        chat.new_turn("user")
        self.chat = chat

    def transcribe_user_audio(self, pcm: np.ndarray, sample_rate: int) -> str:
        import torch

        prepared = normalize_peak(resample_pcm(pcm, sample_rate, self.config.target_sample_rate))
        if prepared.size == 0:
            return ""

        chat = self.runtime.ChatState(self.runtime.processor)
        chat.new_turn("system")
        chat.add_text(
            "あなたは日本語音声認識エンジンです。ユーザー音声を日本語テキストに文字起こししてください。"
            "説明や返答は不要です。文字起こし結果だけを出力してください。"
        )
        chat.end_turn()
        chat.new_turn("user")
        chat.add_audio(torch.from_numpy(prepared.astype(np.float32)).unsqueeze(0), self.config.target_sample_rate)
        chat.end_turn()
        chat.new_turn("assistant")

        kwargs = _chat_kwargs(chat)
        if self.runtime.device != "cpu":
            kwargs = _tree_to_device(kwargs, self.runtime.device)

        tokens: list[int] = []
        with torch.inference_mode():
            for token in self.runtime.model.generate_sequential(
                **kwargs,
                max_new_tokens=self.config.asr_max_new_tokens,
                text_temperature=0.0,
                text_top_k=1,
            ):
                token_cpu = token.detach().cpu()
                if token_cpu.numel() != 1:
                    continue
                token_id = int(token_cpu.item())
                if token_id in {7, 128, 129, 130}:
                    if token_id == 7:
                        break
                    continue
                tokens.append(token_id)

        if not tokens:
            return ""
        text = self.runtime.processor.text.decode(tokens, skip_special_tokens=True)
        return _clean_transcript(text)

    def generate_response(
        self,
        pcm: np.ndarray,
        sample_rate: int,
        state_context: str = "",
    ) -> Iterator[TextEvent | AudioEvent | StatusEvent]:
        with self._generation_lock:
            import torch

            prepared = normalize_peak(resample_pcm(pcm, sample_rate, self.config.target_sample_rate))
            if prepared.size == 0:
                yield StatusEvent("error", "empty_audio")
                return

            yield StatusEvent("user_audio_received", f"{prepared.size / self.config.target_sample_rate:.2f}s")

            wav = torch.from_numpy(prepared.astype(np.float32)).unsqueeze(0)

            self.chat.add_audio(wav, self.config.target_sample_rate)
            if state_context:
                self.chat.add_text(f"\n[内部状態メモ: {state_context}]\n")
            self.chat.end_turn()
            self.chat.new_turn("assistant")

            text_out: list[torch.Tensor] = []
            audio_out: list[torch.Tensor] = []
            modality_out: list[Any] = []
            decoded_samples = 0
            pending_waveforms: list[np.ndarray] = []
            text_filter = TextStreamFilter(SPECIAL_TEXT_MARKERS)
            turn_end_filter = TextStreamFilter((IM_END_MARKER,))
            mimi_context = self.runtime.mimi.streaming(1) if self.runtime.mimi is not None else nullcontext()

            yield StatusEvent("generating")

            kwargs = _chat_kwargs(self.chat)
            if self.runtime.device != "cpu":
                kwargs = _tree_to_device(kwargs, self.runtime.device)

            with torch.inference_mode(), mimi_context:
                for token in self.runtime.model.generate_interleaved(
                    **kwargs,
                    max_new_tokens=self.config.max_new_tokens,
                    audio_temperature=self.config.audio_temperature,
                    audio_top_k=self.config.audio_top_k,
                ):
                    token_cpu = token.detach().cpu()
                    if token_cpu.numel() == 1:
                        piece = self.runtime.processor.text.decode(token_cpu)
                        text_already_ended = text_filter.ended
                        turn_already_ended = turn_end_filter.ended
                        visible_piece = text_filter.push(piece)
                        turn_end_filter.push(piece)
                        if not text_already_ended:
                            text_out.append(token_cpu)
                            modality_out.append(self.runtime.LFMModality.TEXT)
                        if visible_piece:
                            yield TextEvent(visible_piece)
                        if turn_end_filter.ended and not turn_already_ended:
                            break
                    else:
                        audio_out.append(token_cpu)
                        modality_out.append(self.runtime.LFMModality.AUDIO_OUT)
                        if self.runtime.mimi is not None:
                            chunk = self.runtime.decode_audio_frame(token_cpu)
                            if chunk.size:
                                pending_waveforms.append(chunk)
                            if len(pending_waveforms) >= 3:
                                outgoing = np.concatenate(pending_waveforms)
                                pending_waveforms.clear()
                                outgoing = normalize_peak(outgoing, peak=0.88)
                                yield AudioEvent(float32_pcm_to_wav_bytes(outgoing, self.config.target_sample_rate), self.config.target_sample_rate)
                            continue

                    ready_audio_tokens = max(0, len(audio_out) - 1)
                    if ready_audio_tokens - self.config.audio_token_chunk_size >= 0:
                        if ready_audio_tokens % self.config.audio_token_chunk_size == 0:
                            decoded_samples = yield from self._yield_new_audio(audio_out[:ready_audio_tokens], decoded_samples)

            if len(audio_out) > 1:
                if pending_waveforms:
                    outgoing = np.concatenate(pending_waveforms)
                    outgoing = normalize_peak(outgoing, peak=0.88)
                    yield AudioEvent(float32_pcm_to_wav_bytes(outgoing, self.config.target_sample_rate), self.config.target_sample_rate)
                elif self.runtime.mimi is None:
                    decoded_samples = yield from self._yield_new_audio(audio_out[:-1], decoded_samples)
            final_visible_piece = text_filter.flush()
            if final_visible_piece:
                yield TextEvent(final_visible_piece)

            self._append_assistant_turn(text_out, audio_out, modality_out)
            self.chat.end_turn()
            self.chat.new_turn("user")
            yield StatusEvent("done")

    def generate_guided_response(
        self,
        pcm: np.ndarray,
        sample_rate: int,
        *,
        state_payload: dict[str, Any],
        state_context: str,
        fallback_text: str,
        dialogue_history: list[tuple[str, str]] | None = None,
    ) -> Iterator[TextEvent | AudioEvent | StatusEvent]:
        with self._generation_lock:
            import torch

            prepared = normalize_peak(resample_pcm(pcm, sample_rate, self.config.target_sample_rate))
            if prepared.size == 0:
                yield StatusEvent("error", "empty_audio")
                return

            yield StatusEvent("user_audio_received", f"{prepared.size / self.config.target_sample_rate:.2f}s")
            yield StatusEvent("generating", "guided")

            chat = self._build_guided_chat(
                torch.from_numpy(prepared.astype(np.float32)).unsqueeze(0),
                state_context=state_context,
                fallback_text=fallback_text,
                dialogue_history=dialogue_history or [],
            )
            kwargs = _chat_kwargs(chat)
            if self.runtime.device != "cpu":
                kwargs = _tree_to_device(kwargs, self.runtime.device)

            text_out: list[torch.Tensor] = []
            audio_out: list[torch.Tensor] = []
            text_filter = TextStreamFilter(SPECIAL_TEXT_MARKERS)
            turn_end_filter = TextStreamFilter((IM_END_MARKER,))
            visible_text_parts: list[str] = []
            audio_tokens_after_text_end = 0

            with torch.inference_mode():
                for token in self.runtime.model.generate_interleaved(
                    **kwargs,
                    max_new_tokens=self.config.guided_max_new_tokens,
                    audio_temperature=self.config.audio_temperature,
                    audio_top_k=self.config.audio_top_k,
                ):
                    token_cpu = token.detach().cpu()
                    if token_cpu.numel() == 1:
                        piece = self.runtime.processor.text.decode(token_cpu)
                        visible_piece = text_filter.push(piece)
                        turn_end_filter.push(piece)
                        text_out.append(token_cpu)
                        if visible_piece:
                            visible_text_parts.append(visible_piece)
                        if turn_end_filter.ended:
                            break
                    else:
                        audio_out.append(token_cpu)
                        if text_filter.ended:
                            audio_tokens_after_text_end += 1
                            if audio_tokens_after_text_end >= self.config.guided_audio_tail_tokens:
                                break

            final_visible_piece = text_filter.flush()
            if final_visible_piece:
                visible_text_parts.append(final_visible_piece)

            assistant_text = _clean_transcript("".join(visible_text_parts))
            logger_text = assistant_text[:160] if assistant_text else "<empty>"
            valid, reason = _is_guided_response_valid(assistant_text, state_payload, fallback_text)
            if self.config.guided_validate_response and not valid:
                import logging

                logging.getLogger(__name__).info("guided candidate rejected: reason=%s text=%s", reason, logger_text)
                yield StatusEvent("guided_fallback", reason)
                yield from self._synthesize_text_unlocked(fallback_text)
                return

            if assistant_text:
                yield TextEvent(assistant_text)
            audio = self._decode_audio_tokens(audio_out)
            if audio.size:
                yield AudioEvent(float32_pcm_to_wav_bytes(audio, self.config.target_sample_rate), self.config.target_sample_rate)
            yield StatusEvent("done")

    def _build_guided_chat(
        self,
        wav: Any,
        *,
        state_context: str,
        fallback_text: str,
        dialogue_history: list[tuple[str, str]],
    ) -> Any:
        chat = self.runtime.ChatState(self.runtime.processor)
        chat.new_turn("system")
        chat.add_text(GUIDED_SYSTEM_PROMPT)
        chat.end_turn()

        if self.config.guided_context_style == "fake_history":
            for role, text in FAKE_HISTORY_TURNS:
                chat.new_turn(role)
                chat.add_text(text)
                chat.end_turn()
        elif self.config.guided_context_style != "no_fewshot":
            for role, text in GUIDED_FEW_SHOT_TURNS:
                chat.new_turn(role)
                chat.add_text(text)
                chat.end_turn()

        chat.new_turn("user")
        chat.add_text("ここから新しいお客様です。過去の例の予約内容は忘れてください。")
        chat.end_turn()
        chat.new_turn("assistant")
        chat.add_text("承知しました。現在のお客様の予約状態だけに従って受付します。")
        chat.end_turn()

        for role, text in dialogue_history[-4:]:
            if role not in {"user", "assistant"} or not text.strip():
                continue
            chat.new_turn(role)
            chat.add_text(text.strip())
            chat.end_turn()

        chat.new_turn("user")
        chat.add_text(
            "[内部予約状態メモ]\n"
            f"{state_context}\n"
            f"望ましい応答例: 「{fallback_text}」\n"
            "応答例と同じ意味を、店側の自然な短い音声応答として生成してください。\n"
            "ユーザー音声から値を聞き取った場合は、「12月3日ですね。ご希望の時間を教えてください。」のように、値の復唱と次質問を必ず両方含めてください。\n"
            "このメモは制御情報です。読み上げず、現在のお客様の次の1応答だけを生成してください。"
        )
        chat.add_audio(wav, self.config.target_sample_rate)
        chat.end_turn()
        chat.new_turn("assistant")
        return chat

    def _decode_audio_tokens(self, audio_out: list[Any]) -> np.ndarray:
        if len(audio_out) <= 1 or self.runtime.mimi is None:
            return np.zeros(0, dtype=np.float32)

        import torch

        audio_codes = torch.stack(audio_out[:-1], 1).unsqueeze(0)
        with torch.inference_mode():
            waveform = self.runtime.mimi.decode(audio_codes)
        return normalize_peak(waveform.detach().cpu().numpy().reshape(-1).astype(np.float32), peak=0.88)

    def synthesize_text(self, text: str) -> Iterator[TextEvent | AudioEvent | StatusEvent]:
        with self._generation_lock:
            yield from self._synthesize_text_unlocked(text)

    def _synthesize_text_unlocked(self, text: str) -> Iterator[TextEvent | AudioEvent | StatusEvent]:
        import torch

        yield StatusEvent("generating")
        yield TextEvent(text)

        chat = self.runtime.ChatState(self.runtime.processor)
        chat.new_turn("system")
        chat.add_text("Perform TTS in japanese.")
        chat.end_turn()
        chat.new_turn("user")
        chat.add_text(text)
        chat.end_turn()
        chat.new_turn("assistant")

        kwargs = _chat_kwargs(chat)
        if self.runtime.device != "cpu":
            kwargs = _tree_to_device(kwargs, self.runtime.device)

        audio_out: list[torch.Tensor] = []

        yield StatusEvent("tts_generating")
        with torch.inference_mode():
            for token in self.runtime.model.generate_sequential(
                **kwargs,
                max_new_tokens=self.config.tts_max_new_tokens,
                audio_temperature=self.config.audio_temperature,
                audio_top_k=self.config.audio_top_k,
            ):
                token_cpu = token.detach().cpu()
                if token_cpu.numel() > 1:
                    audio_out.append(token_cpu)

        yield StatusEvent("tts_decoding")
        outgoing = self._decode_audio_tokens(audio_out)
        if outgoing.size:
            yield AudioEvent(float32_pcm_to_wav_bytes(outgoing, self.config.target_sample_rate), self.config.target_sample_rate)
        yield StatusEvent("done")

    def _yield_new_audio(self, audio_tokens: list[Any], decoded_samples: int) -> Iterator[AudioEvent]:
        import torch

        if not audio_tokens:
            return decoded_samples

        audio_codes = torch.stack(audio_tokens, 1).unsqueeze(0)
        audio_codes = audio_codes.to(self.runtime.device)
        with torch.inference_mode():
            waveform = self.runtime.processor.decode(audio_codes)

        samples = waveform.detach().cpu().numpy()
        if samples.ndim == 2:
            samples = samples[0]
        samples = np.asarray(samples, dtype=np.float32)
        if samples.size <= decoded_samples:
            return decoded_samples

        new_samples = samples[decoded_samples:]
        new_samples = normalize_peak(new_samples, peak=0.88)
        yield AudioEvent(float32_pcm_to_wav_bytes(new_samples, self.config.target_sample_rate), self.config.target_sample_rate)
        return int(samples.size)

    def _append_assistant_turn(self, text_out: list[Any], audio_out: list[Any], modality_out: list[Any]) -> None:
        import torch

        if not text_out and not audio_out:
            return

        append_kwargs: dict[str, Any] = {"modality_flag": torch.tensor(modality_out)}
        if text_out:
            append_kwargs["text"] = torch.stack(text_out, 1)
        if audio_out:
            append_kwargs["audio_out"] = torch.stack(audio_out, 1)

        try:
            self.chat.append(**append_kwargs)
        except TypeError:
            if text_out and audio_out:
                self.chat.append(
                    text=torch.stack(text_out, 1),
                    audio_out=torch.stack(audio_out, 1),
                    modality_flag=torch.tensor(modality_out),
                )


def _clean_transcript(text: str) -> str:
    text = text.replace("<|im_end|>", "").replace("<|text_end|>", "")
    return " ".join(text.split()).strip()


def _visible_text(text: str) -> str:
    for marker in SPECIAL_TEXT_MARKERS:
        text = text.replace(marker, "")
    return text


def _is_guided_response_valid(
    text: str,
    state_payload: dict[str, Any],
    fallback_text: str,
) -> tuple[bool, str]:
    if not text:
        return False, "empty_guided_text"
    if "�" in text or any(marker in text for marker in SPECIAL_TEXT_MARKERS):
        return False, "invalid_marker_or_mojibake"

    forbidden = ("名前", "お名前", "電話", "連絡先", "アレルギー", "席", "個室", "住所")
    if any(word in text for word in forbidden):
        return False, "forbidden_question"

    customer_side = ("予約したい", "お願いします", "伺います", "行きたい", "取りたいです")
    if any(phrase in text for phrase in customer_side):
        return False, "customer_side_response"

    if len(text) > 90:
        return False, "too_long"

    missing = set(state_payload.get("missing") or [])
    current_field = str(state_payload.get("current_field") or "")

    if not missing:
        for field in ("date", "time", "party_size"):
            value = state_payload.get(field)
            if value and str(value) not in text:
                return False, f"missing_confirmation_{field}"
        return True, ""

    if current_field == "date":
        if not any(word in text for word in ("日", "日にち", "お日にち", "いつ", "何月")):
            return False, "does_not_ask_date"
        if _looks_like_time_or_party_claim(text):
            return False, "hallucinated_later_slot"
    elif current_field == "time":
        if not any(word in text for word in ("時間", "何時", "時")):
            return False, "does_not_ask_time"
        if "party_size" in missing and _looks_like_party_claim(text):
            return False, "hallucinated_party_size"
    elif current_field == "party_size":
        if not any(word in text for word in ("人数", "何名", "何人", "名様")):
            return False, "does_not_ask_party_size"

    expected_topic = _expected_topic(fallback_text)
    if expected_topic and expected_topic != _expected_topic(text):
        return False, "wrong_question_topic"

    return True, ""


def _expected_topic(text: str) -> str:
    if any(word in text for word in ("人数", "何名", "何人", "名様")):
        return "party_size"
    if any(word in text for word in ("時間", "何時", "時")):
        return "time"
    if any(word in text for word in ("日", "日にち", "お日にち", "いつ", "何月")):
        return "date"
    return ""


def _looks_like_time_or_party_claim(text: str) -> bool:
    return _looks_like_time_claim(text) or _looks_like_party_claim(text)


def _looks_like_time_claim(text: str) -> bool:
    import re

    return bool(re.search(r"\d{1,2}\s*時|\d{1,2}\s*:\s*\d{2}|[一二三四五六七八九十]\s*時", text))


def _looks_like_party_claim(text: str) -> bool:
    import re

    return bool(re.search(r"\d{1,2}\s*(名|人)|[一二三四五六七八九十]\s*(名|人)", text))
