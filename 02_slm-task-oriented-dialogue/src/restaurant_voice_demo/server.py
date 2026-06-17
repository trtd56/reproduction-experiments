from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import webrtcvad
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import DemoConfig
from .lfm_agent import AudioEvent, LFMRuntime, StatusEvent, TextEvent
from .reservation_state import ReservationState


logger = logging.getLogger(__name__)
config = DemoConfig()
runtime = LFMRuntime(config)
INPUT_SAMPLE_RATE = 16_000

app = FastAPI(title="Restaurant Voice Demo", version="0.1.0")


@app.on_event("startup")
async def preload_model() -> None:
    if not config.preload_model:
        logger.info("model preload disabled")
        return
    logger.info("preloading model: model_id=%s device=%s dtype=%s", config.model_id, runtime.device, runtime.dtype)
    await asyncio.to_thread(runtime.load)
    logger.info("model preload complete")


def _static_dir() -> Path:
    if config.static_dir:
        return Path(config.static_dir)
    return Path(__file__).resolve().parents[2] / "static"


STATIC_DIR = _static_dir()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@dataclass
class SpeechSegmenter:
    sample_rate: int
    aggressiveness: int = 2

    def __post_init__(self) -> None:
        self.vad = webrtcvad.Vad(self.aggressiveness)
        self.frame_ms = 30
        self.frame_samples = self.sample_rate * self.frame_ms // 1000
        self.frame_bytes = self.frame_samples * 2
        self.buffer = bytearray()
        self.current = bytearray()
        self.speech_frames = 0
        self.silence_frames = 0
        self.triggered = False

    def accept(self, pcm16_bytes: bytes) -> list[bytes]:
        self.buffer.extend(pcm16_bytes)
        completed: list[bytes] = []
        while len(self.buffer) >= self.frame_bytes:
            frame = bytes(self.buffer[: self.frame_bytes])
            del self.buffer[: self.frame_bytes]
            is_speech = self.vad.is_speech(frame, self.sample_rate)
            if is_speech:
                self.speech_frames += 1
                self.silence_frames = 0
                self.current.extend(frame)
                if self.speech_frames >= 3:
                    self.triggered = True
            elif self.triggered:
                self.silence_frames += 1
                self.current.extend(frame)
                if self.silence_frames >= 18:
                    completed.append(bytes(self.current))
                    self.reset_turn()
            else:
                self.speech_frames = 0
        return [segment for segment in completed if len(segment) / 2 / self.sample_rate >= config.min_commit_seconds]

    def reset_turn(self) -> None:
        self.current.clear()
        self.speech_frames = 0
        self.silence_frames = 0
        self.triggered = False

    def clear(self) -> None:
        self.buffer.clear()
        self.reset_turn()


def pcm16_to_float32(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def _copy_reservation_state(state: ReservationState) -> ReservationState:
    return ReservationState(
        date=state.date,
        time=state.time,
        party_size=state.party_size,
        current_field=state.current_field,
        turns=state.turns,
    )


def _state_values(state: ReservationState) -> tuple[str | None, str | None, str | None, str]:
    return state.date, state.time, state.party_size, state.current_field


def _response_topic(text: str) -> str:
    if any(word in text for word in ("人数", "何名", "何人", "名様")):
        return "party_size"
    if any(word in text for word in ("時間", "何時", "時")):
        return "time"
    if any(word in text for word in ("日", "日にち", "お日にち", "いつ", "何月")):
        return "date"
    return ""


def _decide_hybrid_response(
    current_state: ReservationState,
    assistant_text: str,
) -> tuple[str, str, ReservationState]:
    candidate = " ".join(assistant_text.split()).strip()
    trial_state = _copy_reservation_state(current_state)

    if not candidate:
        return "fallback", "empty_guided_text", trial_state

    before = _state_values(current_state)
    trial_state.observe_assistant_text(candidate, increment_turn=False)
    after = _state_values(trial_state)
    changed = before[:3] != after[:3]

    if "�" in candidate:
        return ("fallback_after_extract" if changed else "fallback"), "mojibake", trial_state

    forbidden = ("名前", "お名前", "電話", "連絡先", "アレルギー", "席", "個室", "住所")
    if any(word in candidate for word in forbidden):
        return ("fallback_after_extract" if changed else "fallback"), "forbidden_content", trial_state

    if current_state.is_complete:
        return ("accept_guided" if trial_state.is_complete else "fallback"), "complete_confirmation", trial_state

    current_field = current_state.current_field
    topic = _response_topic(candidate)

    if changed:
        current_value = getattr(current_state, current_field)
        trial_value = getattr(trial_state, current_field)
        if current_value is None and trial_value is None:
            return "fallback", "filled_wrong_slot", trial_state
        if trial_state.is_complete or topic == trial_state.current_field:
            return "accept_guided", "slot_extracted_and_next_question", trial_state
        return "fallback_after_extract", "slot_extracted_without_next_question", trial_state

    if topic == current_field:
        return "accept_guided", "asks_current_slot", trial_state
    return "fallback", "no_slot_and_wrong_topic", trial_state


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "model_id": config.model_id,
            "loaded": runtime._loaded,
            "device": runtime.device,
            "dtype": str(runtime.dtype),
            "preload_model": config.preload_model,
            "response_mode": config.response_mode,
            "demo_variant": config.demo_variant,
            "slot_update_source": config.slot_update_source,
            "guided_validate_response": config.guided_validate_response,
            "pid": os.getpid(),
        }
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    session = None
    reservation = ReservationState()
    segmenter = SpeechSegmenter(INPUT_SAMPLE_RATE)
    generating = asyncio.Lock()
    generation_active = False
    dialogue_history: list[tuple[str, str]] = []

    if not runtime._loaded:
        await websocket.send_json({"type": "status", "status": "loading_model"})
        session = await asyncio.to_thread(runtime.new_session)
    else:
        session = await asyncio.to_thread(runtime.new_session)

    await websocket.send_json(
        {
            "type": "ready",
            "sampleRate": INPUT_SAMPLE_RATE,
            "outputSampleRate": config.target_sample_rate,
            "modelLoaded": runtime._loaded,
            "device": runtime.device,
            "dtype": str(runtime.dtype),
            "variant": config.demo_variant,
            "reservation": reservation.as_payload(),
        }
    )
    await websocket.send_json({"type": "reservation_state", "state": reservation.as_payload()})

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"] is not None:
                if generation_active or generating.locked():
                    continue
                for segment in segmenter.accept(message["bytes"]):
                    generation_active = True
                    segmenter.clear()

                    async def run_response(segment_bytes: bytes) -> None:
                        nonlocal generation_active
                        try:
                            await asyncio.sleep(0.2)
                            audio = pcm16_to_float32(segment_bytes)
                            logger.info(
                                "detected user speech: seconds=%.2f",
                                len(segment_bytes) / 2 / INPUT_SAMPLE_RATE,
                            )
                            await websocket.send_json({"type": "status", "status": "utterance_detected", "detail": ""})
                            await _stream_generation(
                                websocket,
                                session,
                                reservation,
                                audio,
                                INPUT_SAMPLE_RATE,
                                generating,
                                dialogue_history,
                            )
                        finally:
                            segmenter.clear()
                            generation_active = False

                    asyncio.create_task(run_response(segment))
                    break
                continue

            if "text" not in message or message["text"] is None:
                continue

            payload = json.loads(message["text"])
            event_type = payload.get("type")

            if event_type == "user_transcript":
                transcript = str(payload.get("text") or "").strip()
                if transcript:
                    is_final = bool(payload.get("final", True))
                    if config.slot_update_source == "user":
                        reservation.observe_user_text(transcript)
                    if is_final:
                        _append_dialogue_history(dialogue_history, "user", transcript)
                    await websocket.send_json({"type": "reservation_state", "state": reservation.as_payload()})
            elif event_type == "reset":
                if session is not None:
                    await asyncio.to_thread(session.reset)
                reservation = ReservationState()
                dialogue_history.clear()
                segmenter.clear()
                await websocket.send_json({"type": "status", "status": "reset"})
                await websocket.send_json({"type": "reservation_state", "state": reservation.as_payload()})
            elif event_type == "input_state" and payload.get("state") == "paused":
                segmenter.clear()

            elif event_type == "ping":
                await websocket.send_json({"type": "pong"})

    except (RuntimeError, WebSocketDisconnect):
        return


async def _stream_generation(
    websocket: WebSocket,
    session: Any,
    reservation: ReservationState,
    audio: Any,
    sample_rate: int,
    generating: asyncio.Lock,
    dialogue_history: list[tuple[str, str]],
) -> None:
    events: queue.Queue[Any] = queue.Queue()
    assistant_text_parts: list[str] = []
    state_update_text_parts: list[str] = []
    state_payload = reservation.as_payload()
    state_context = (
        reservation.grounded_prompt_context()
        if config.slot_update_source == "assistant"
        else reservation.prompt_context()
    )
    fallback_text = reservation.next_assistant_text()
    history_snapshot = list(dialogue_history)

    def produce() -> None:
        try:
            if config.response_mode == "hybrid":
                logger.info("hybrid response: fallback_text=%s state=%s", fallback_text, state_context)
                events.put(StatusEvent("guided_generating"))
                guided_events = list(
                    session.generate_guided_response(
                        audio,
                        sample_rate,
                        state_payload=state_payload,
                        state_context=state_context,
                        fallback_text=fallback_text,
                        dialogue_history=history_snapshot,
                    )
                )
                guided_text = "".join(event.text for event in guided_events if isinstance(event, TextEvent))
                decision, detail, trial_state = _decide_hybrid_response(reservation, guided_text)
                logger.info("hybrid decision: decision=%s detail=%s text=%s", decision, detail, guided_text[:160])

                if decision == "accept_guided":
                    events.put(StatusEvent("guided_accepted", detail))
                    state_update_text_parts.append(guided_text)
                    for event in guided_events:
                        events.put(event)
                else:
                    if decision == "fallback_after_extract":
                        fallback_for_decision = trial_state.next_assistant_text()
                        state_update_text_parts.append(f"{guided_text} {fallback_for_decision}")
                    else:
                        state_update_text_parts.append(fallback_text)
                        fallback_for_decision = fallback_text
                    events.put(StatusEvent("guided_fallback", detail))
                    events.put(StatusEvent("fallback_tts", fallback_for_decision))
                    for event in session.synthesize_text(fallback_for_decision):
                        events.put(event)
            elif config.response_mode == "raw":
                logger.info("raw LFM response: state_hint=%s state=%s", config.raw_state_hint, state_context)
                events.put(StatusEvent("raw_generating", "with_state_hint" if config.raw_state_hint else "prompt_only"))
                iterator = session.generate_response(
                    audio,
                    sample_rate,
                    state_context=state_context if config.raw_state_hint else "",
                )
                for event in iterator:
                    events.put(event)
            elif config.response_mode == "asr_policy":
                logger.info("ASR policy response: fallback_text=%s state=%s", fallback_text, state_context)
                events.put(StatusEvent("asr_transcribing"))
                asr_text = session.transcribe_user_audio(audio, sample_rate)
                events.put(StatusEvent("asr_transcript", asr_text))
                if asr_text:
                    reservation.observe_user_text(asr_text)
                    state_update_text_parts.append(reservation.next_assistant_text())
                policy_text = reservation.next_assistant_text()
                events.put(StatusEvent("policy_response", policy_text))
                for event in session.synthesize_text(policy_text):
                    events.put(event)
            else:
                if config.response_mode == "guided":
                    logger.info("guided response: fallback_text=%s state=%s", fallback_text, state_context)
                    iterator = session.generate_guided_response(
                        audio,
                        sample_rate,
                        state_payload=state_payload,
                        state_context=state_context,
                        fallback_text=fallback_text,
                        dialogue_history=history_snapshot,
                    )
                else:
                    logger.info("deterministic assistant text: %s", fallback_text)
                    iterator = session.synthesize_text(fallback_text)
                for event in iterator:
                    events.put(event)
        except Exception as exc:
            logger.exception("generation failed")
            events.put(StatusEvent("error", str(exc)))
        finally:
            events.put(None)

    async with generating:
        threading.Thread(target=produce, daemon=True).start()
        try:
            await websocket.send_json({"type": "response_start", "sampleRate": config.target_sample_rate})

            while True:
                event = await asyncio.to_thread(events.get)
                if event is None:
                    break
                if isinstance(event, AudioEvent):
                    logger.debug("sending audio chunk: bytes=%s sample_rate=%s", len(event.pcm), event.sample_rate)
                    await websocket.send_json({"type": "status", "status": "audio_ready", "detail": f"{len(event.pcm)} bytes"})
                    await websocket.send_bytes(event.pcm)
                elif isinstance(event, TextEvent):
                    assistant_text_parts.append(event.text)
                    await websocket.send_json({"type": "text", "text": event.text})
                elif isinstance(event, StatusEvent):
                    logger.info("generation status: %s %s", event.status, event.detail)
                    if event.status == "asr_transcript":
                        await websocket.send_json({"type": "user_transcript", "text": event.detail})
                    else:
                        await websocket.send_json({"type": "status", "status": event.status, "detail": event.detail})
        except (RuntimeError, WebSocketDisconnect):
            logger.info("websocket closed while streaming response")
            return

        assistant_text = "".join(assistant_text_parts)
        state_update_text = "".join(state_update_text_parts) or assistant_text
        if config.slot_update_source == "assistant":
            reservation.observe_assistant_text(state_update_text)
        else:
            reservation.observe_turn(assistant_text)
        if assistant_text:
            _append_dialogue_history(dialogue_history, "assistant", assistant_text)
        await websocket.send_json({"type": "reservation_state", "state": reservation.as_payload()})
        await websocket.send_json({"type": "response_end"})


def _append_dialogue_history(history: list[tuple[str, str]], role: str, text: str) -> None:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return
    if history and history[-1] == (role, normalized):
        return
    history.append((role, normalized))
    del history[:-8]
