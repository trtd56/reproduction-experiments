from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .audio import pcm16_wav_bytes
from .config import DemoConfig
from .gemini_live import GeminiLiveSession
from .reservation_state import ReservationState


logger = logging.getLogger(__name__)
config = DemoConfig()
app = FastAPI(title="Gemini Live Restaurant Demo", version="0.1.0")


def _static_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "static"


STATIC_DIR = _static_dir()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "model": config.gemini_model,
            "has_api_key": bool(config.gemini_api_key),
            "demo_variant": config.demo_variant,
            "pid": os.getpid(),
        }
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    state = ReservationState()
    await websocket.send_json(
        {
            "type": "hello",
            "model": config.gemini_model,
            "sampleRate": 16_000,
            "outputSampleRate": 24_000,
            "hasApiKey": bool(config.gemini_api_key),
            "reservation": state.as_payload(),
        }
    )
    if not config.gemini_api_key:
        await websocket.send_json({"type": "status", "status": "missing_api_key"})
        return

    try:
        async with GeminiLiveSession(config, state) as gemini:
            await websocket.send_json({"type": "status", "status": "connecting_gemini"})
            stop = asyncio.Event()
            client_task = asyncio.create_task(_client_to_gemini(websocket, gemini, stop))
            gemini_task = asyncio.create_task(_gemini_to_client(websocket, gemini, stop))
            done, pending = await asyncio.wait({client_task, gemini_task}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.exception("websocket session failed")
        try:
            await websocket.send_json({"type": "status", "status": "error", "detail": str(exc)})
        except RuntimeError:
            pass


async def _client_to_gemini(websocket: WebSocket, gemini: GeminiLiveSession, stop: asyncio.Event) -> None:
    try:
        while not stop.is_set():
            message = await websocket.receive()
            if "bytes" in message and message["bytes"] is not None:
                await gemini.send_audio(message["bytes"])
                continue
            if "text" not in message or message["text"] is None:
                continue

            payload = json.loads(message["text"])
            event_type = payload.get("type")
            if event_type == "audio_stream_end":
                await gemini.send_audio_stream_end()
            elif event_type == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, RuntimeError):
        stop.set()


async def _gemini_to_client(websocket: WebSocket, gemini: GeminiLiveSession, stop: asyncio.Event) -> None:
    async for event in gemini.receive():
        if event.type == "setup_complete":
            await websocket.send_json(
                {
                    "type": "ready",
                    "model": gemini.config.gemini_model,
                    "variant": gemini.config.demo_variant,
                    "sampleRate": 16_000,
                    "outputSampleRate": 24_000,
                    "reservation": gemini.state.as_payload(),
                }
            )
        elif event.type == "audio":
            pcm = event.payload if isinstance(event.payload, bytes) else b""
            await websocket.send_bytes(pcm16_wav_bytes(pcm, 24_000))
        elif event.type == "input_transcription":
            await websocket.send_json({"type": "user_transcript", **_dict_payload(event.payload)})
        elif event.type == "output_transcription":
            payload = _dict_payload(event.payload)
            await websocket.send_json({"type": "assistant_transcript", "text": payload.get("text", "")})
            await websocket.send_json({"type": "reservation_state", "state": payload.get("state")})
        elif event.type == "tool_call":
            payload = _dict_payload(event.payload)
            await websocket.send_json(
                {
                    "type": "tool_call",
                    "name": payload.get("name"),
                    "args": payload.get("args"),
                }
            )
            await websocket.send_json({"type": "reservation_state", "state": payload.get("state")})
        elif event.type == "turn_complete":
            await websocket.send_json({"type": "response_end", **_dict_payload(event.payload)})
        elif event.type == "interrupted":
            await websocket.send_json({"type": "status", "status": "interrupted"})
        elif event.type == "text":
            await websocket.send_json({"type": "text", **_dict_payload(event.payload)})
    stop.set()


def _dict_payload(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}
