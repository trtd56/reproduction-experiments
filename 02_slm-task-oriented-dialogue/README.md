# SLM Task-Oriented Speech Dialogue

This repository contains the public demo code for a Japanese task-oriented
speech dialogue experiment.

## Target

- Local model path: `LiquidAI/LFM2.5-Audio-1.5B-JP`
- Comparison path: Gemini Live API
- Task: Japanese restaurant reservation dialogue
- Required slots: date, time, party size
- Interface: browser microphone, WebSocket audio streaming, FastAPI backend
- Constraint: no Gradio

## What This Demo Shows

The LFM path tests whether a small local speech-to-speech model can keep a
restaurant reservation dialogue on task. The final local version is a hybrid:

- Browser streams 16 kHz PCM to FastAPI.
- Server-side WebRTC VAD commits user turns.
- LFM generates a speech-to-speech assistant candidate.
- Reservation slots are extracted from the assistant confirmation text.
- A rule layer rejects off-task candidates.
- Rejected candidates fall back to deterministic text, still spoken by LFM TTS.

The Gemini Live variant uses the same local UI but delegates real-time audio,
transcription, and tool calling to the Live API.

## Layout

```text
02_slm-task-oriented-dialogue/
├── README.md
├── PUBLISHING_CHECKLIST.md
├── PUBLICATION_MANIFEST.md
├── requirements.txt
├── configs/
│   ├── demo.env.example
│   └── variants/
├── docs/
├── scripts/
│   ├── run_demo.sh
│   └── run_reproduction_demo.sh
├── src/
│   └── restaurant_voice_demo/
├── static/
└── tests/
```

## Setup

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Default local LFM hybrid demo:

```bash
./scripts/run_demo.sh
```

Open <http://127.0.0.1:8088> and allow microphone access.

Intermediate variants used in the article:

```bash
./scripts/run_reproduction_demo.sh lfm_raw_prompt
./scripts/run_reproduction_demo.sh lfm_system_hint
./scripts/run_reproduction_demo.sh lfm_guided_fewshot
./scripts/run_reproduction_demo.sh lfm_fake_history
./scripts/run_reproduction_demo.sh lfm_asr_policy
./scripts/run_reproduction_demo.sh lfm_hybrid_final
./scripts/run_reproduction_demo.sh gemini_live
```

`gemini_live` requires `GEMINI_API_KEY` in the environment or in a local
`.env` file. Do not commit `.env`.

## Local Notes

- The LFM model repository is several GB, so first startup can take time.
- On Apple Silicon, the default `LFM_DEVICE=auto` uses CPU unless
  `LFM_ENABLE_MPS=1` is set. The MPS path was less predictable in this demo.
- CPU generation is slower than real time. The default local path returns one
  complete synthesized response per turn and shows progress in the UI.
- For predictable Mac local behavior, use:

```bash
LFM_DEVICE=cpu LFM_DTYPE=float32 ./scripts/run_demo.sh
```

## Tests

```bash
PYTHONPATH=src python -m pytest tests -q
```

The tests cover audio helpers and the lightweight reservation-state extractor.

## References

- LFM2.5-Audio-1.5B-JP: <https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B-JP>
- Gemini Live API overview: <https://ai.google.dev/gemini-api/docs/live-api>
- Gemini API models: <https://ai.google.dev/gemini-api/docs/models>
