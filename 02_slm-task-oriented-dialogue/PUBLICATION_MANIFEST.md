# Publication Manifest

Publish the parent `reproduction-experiments/` directory as the GitHub
repository root. This experiment should live under:

```text
02_slm-task-oriented-dialogue/
```

## Included

- FastAPI/WebSocket demo server for the LFM local path.
- FastAPI proxy server for the Gemini Live comparison path.
- Browser microphone UI and PCM playback code.
- LFM response variants used in the article.
- Public notes describing the qualitative reproduction attempts.
- Unit tests for deterministic helper logic.

## Excluded

- Private setup log and day-by-day work notes.
- Blog drafts and podcast scripts.
- Generated audio, screenshots, videos, and local result logs.
- Model weights, Hugging Face caches, and adapter/checkpoint directories.
- `.env` files and API keys.
- Paper PDFs or copied external repositories.

## Public File Tree

```text
02_slm-task-oriented-dialogue/
├── README.md
├── PUBLISHING_CHECKLIST.md
├── PUBLICATION_MANIFEST.md
├── requirements.txt
├── configs/
│   ├── demo.env.example
│   └── variants/
│       ├── gemini_live.env
│       ├── lfm_asr_policy.env
│       ├── lfm_fake_history.env
│       ├── lfm_guided_fewshot.env
│       ├── lfm_hybrid_final.env
│       ├── lfm_raw_prompt.env
│       └── lfm_system_hint.env
├── docs/
│   ├── model_and_api_notes.md
│   ├── reproduction_variants.md
│   └── v2_parallel_experiment.md
├── scripts/
│   ├── run_demo.sh
│   └── run_reproduction_demo.sh
├── src/
│   └── restaurant_voice_demo/
├── static/
│   ├── app.js
│   ├── index.html
│   ├── pcm-worklet.js
│   └── styles.css
└── tests/
    ├── test_audio.py
    └── test_reservation_state.py
```

## Suggested GitHub Description

Japanese speech-to-speech restaurant reservation demo comparing local
LFM2.5-Audio with Gemini Live API.

## Suggested Topics

```text
speech-to-speech
task-oriented-dialogue
lfm
gemini-live
audio
fastapi
websocket
japanese
local-llm
reproducibility
```
