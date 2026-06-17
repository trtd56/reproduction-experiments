# Model and API Notes

Checked for publication on 2026-06-17.

## LFM2.5-Audio-1.5B-JP

- Repository: <https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B-JP>
- Provider: Liquid AI
- Hugging Face task label observed during publication prep: Audio-to-Audio
- Related package: <https://github.com/Liquid4All/liquid-audio>

The public demo uses the `liquid-audio` interface with `ChatState`,
`generate_interleaved(...)` for speech-to-speech attempts, and sequential
generation for ASR/TTS-style fallback paths.

## Gemini Live API

- Overview: <https://ai.google.dev/gemini-api/docs/live-api>
- Model list: <https://ai.google.dev/gemini-api/docs/models>

The Gemini Live API overview checked on 2026-06-17 states that the Live API is
in Preview and supports low-latency real-time voice and vision interactions over
a stateful WebSocket connection.

The same documentation lists:

- input audio: raw little-endian PCM16 at 16 kHz
- output audio: raw little-endian PCM16 at 24 kHz
- features used by this demo: audio transcriptions, barge-in/interruption, and
  tool use/function calling

The Gemini API model list checked on 2026-06-17 includes `Gemini 3.1 Flash Live
Preview` as a Live API audio-to-audio model. The config string used in this demo
is `gemini-3.1-flash-live-preview`.
