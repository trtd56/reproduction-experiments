from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import websockets

from .config import DemoConfig
from .reservation_state import ReservationState


GEMINI_WS_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"

GEMINI_SYSTEM_PROMPT = """あなたはレストラン青葉の予約受付スタッフです。
ユーザーは電話で予約をしたいお客様です。あなたは必ず店側として話してください。

目的:
- 必須項目は「日にち」「時間」「人数」の3つだけです。
- 3つが揃ったら短く復唱し、「ご予約を承りました」と伝えて完了してください。
- 名前、電話番号、席、アレルギー、住所、支払い方法は聞かないでください。

会話:
- 日本語で、自然な電話応対として短く返答してください。
- 一度に質問する未確認項目は1つだけにしてください。
- すでに確認済みの項目は再質問せず、次の未確認項目へ進んでください。
- お客様の発話から日にち・時間・人数が分かったら、応答前または応答中に update_reservation_state を呼び出してください。
- 聞き取れた値は短く復唱してください。
- 予約完了後は新しい質問をせず、締めの一言だけにしてください。
"""

UPDATE_RESERVATION_TOOL = {
    "name": "update_reservation_state",
    "description": "現在のお客様のレストラン予約スロットを更新する。聞き取れた値だけを指定する。",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "date": {"type": "STRING", "description": "予約日。例: 明日, 12月3日, 金曜日"},
            "time": {"type": "STRING", "description": "予約時間。例: 18時, 午後7時, 12:30"},
            "party_size": {"type": "STRING", "description": "人数。例: 2名, 6人"},
            "complete": {"type": "BOOLEAN", "description": "3スロットが揃って予約確認まで終えたらtrue"},
        },
    },
}


@dataclass
class GeminiEvent:
    type: str
    payload: dict[str, Any] | bytes | None = None


class GeminiLiveSession:
    def __init__(self, config: DemoConfig, state: ReservationState) -> None:
        self.config = config
        self.state = state
        self.websocket: Any = None

    async def __aenter__(self) -> "GeminiLiveSession":
        if not self.config.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        url = f"{GEMINI_WS_URL}?key={quote(self.config.gemini_api_key)}"
        self.websocket = await websockets.connect(url, max_size=None)
        await self.websocket.send(json.dumps(self._setup_message()))
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.websocket is not None:
            await self.websocket.close()

    def _setup_message(self) -> dict[str, Any]:
        setup: dict[str, Any] = {
            "model": f"models/{self.config.gemini_model}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
            },
            "systemInstruction": {"parts": [{"text": GEMINI_SYSTEM_PROMPT}]},
            "realtimeInputConfig": {
                "automaticActivityDetection": {
                    "disabled": False,
                    "silenceDurationMs": self.config.gemini_silence_duration_ms,
                }
            },
        }
        if self.config.gemini_input_transcription:
            setup["inputAudioTranscription"] = {}
        if self.config.gemini_output_transcription:
            setup["outputAudioTranscription"] = {}
        if self.config.gemini_voice:
            setup["generationConfig"]["speechConfig"] = {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.config.gemini_voice}}
            }
        setup["tools"] = [{"functionDeclarations": [UPDATE_RESERVATION_TOOL]}]
        return {"setup": setup}

    async def send_audio(self, pcm16: bytes) -> None:
        if not pcm16:
            return
        await self.websocket.send(
            json.dumps(
                {
                    "realtimeInput": {
                        "audio": {
                            "data": base64.b64encode(pcm16).decode("ascii"),
                            "mimeType": "audio/pcm;rate=16000",
                        }
                    }
                }
            )
        )

    async def send_audio_stream_end(self) -> None:
        await self.websocket.send(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))

    async def receive(self) -> AsyncIterator[GeminiEvent]:
        async for raw_message in self.websocket:
            message = json.loads(raw_message)
            if "setupComplete" in message:
                yield GeminiEvent("setup_complete", message["setupComplete"])
            if "serverContent" in message:
                async for event in self._server_content_events(message["serverContent"]):
                    yield event
            if "toolCall" in message:
                async for event in self._handle_tool_call(message["toolCall"]):
                    yield event

    async def _server_content_events(self, server_content: dict[str, Any]) -> AsyncIterator[GeminiEvent]:
        if input_tx := server_content.get("inputTranscription"):
            text = str(input_tx.get("text") or "")
            if text:
                yield GeminiEvent("input_transcription", {"text": text})

        if output_tx := server_content.get("outputTranscription"):
            text = str(output_tx.get("text") or "")
            if text:
                self.state.observe_text(text)
                yield GeminiEvent("output_transcription", {"text": text, "state": self.state.as_payload()})

        model_turn = server_content.get("modelTurn") or {}
        for part in model_turn.get("parts") or []:
            inline_data = part.get("inlineData")
            if inline_data and inline_data.get("data"):
                yield GeminiEvent("audio", base64.b64decode(inline_data["data"]))
            if part.get("text"):
                text = str(part["text"])
                yield GeminiEvent("text", {"text": text})

        if server_content.get("turnComplete"):
            yield GeminiEvent("turn_complete", {"state": self.state.as_payload()})

        if server_content.get("interrupted"):
            yield GeminiEvent("interrupted", {})

    async def _handle_tool_call(self, tool_call: dict[str, Any]) -> AsyncIterator[GeminiEvent]:
        responses: list[dict[str, Any]] = []
        for call in tool_call.get("functionCalls") or []:
            name = call.get("name")
            call_id = call.get("id")
            args = call.get("args") or {}
            if name == "update_reservation_state":
                self.state.update_slots(
                    date=args.get("date"),
                    time=args.get("time"),
                    party_size=args.get("party_size"),
                )
                response = {"ok": True, "reservation": self.state.as_payload()}
                yield GeminiEvent(
                    "tool_call",
                    {"name": name, "args": args, "state": self.state.as_payload()},
                )
            else:
                response = {"ok": False, "error": f"Unknown function: {name}"}

            responses.append({"name": name, "id": call_id, "response": response})

        if responses:
            await self.websocket.send(json.dumps({"toolResponse": {"functionResponses": responses}}))
