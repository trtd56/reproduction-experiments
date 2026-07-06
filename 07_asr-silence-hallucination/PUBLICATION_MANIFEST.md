# Publication Manifest

Publish the parent `reproduction-experiments/` directory as the GitHub
repository root. This experiment should live under:

```text
07_asr-silence-hallucination/
```

## Included

- Public README, experiment design, and literature notes.
- Synthetic-audio generation, ESC-50 preparation, ASR run, aggregation, and figure scripts.
- Experiment configuration for smoke, model-size, mitigation, CTC, and ESC-50 sweeps.
- Curated aggregate CSV tables and PNG figures.
- Public analysis notes, blog draft, and podcast outline/script.

## Excluded

- Generated WAV files under `experiment/data/processed/audio/`.
- ESC-50 archive, extracted ESC-50 audio, and other source datasets under `experiment/data/external/`.
- Raw ASR JSONL logs and console logs under `experiment/results/logs/`.
- API keys, `.env` files, credentials, model caches, local virtualenvs, and Hugging Face cache data.
- Paper PDFs or copied external repositories.
- Generated `__pycache__` directories and `.pyc` files.

## Public File Tree

```text
07_asr-silence-hallucination/
├── README.md
├── .gitignore
├── PUBLISHING_CHECKLIST.md
├── PUBLICATION_MANIFEST.md
├── requirements.txt
├── analysis/
│   ├── full-findings.md
│   └── smoke-findings.md
├── blog/
│   ├── assets/asr-silence-hallucination/*.png
│   └── drafts/2026-07-02-asr-silence-hallucination-techblog.md
├── docs/
│   └── experiment-design.md
├── experiment/
│   ├── configs/experiment.yaml
│   ├── results/
│   │   ├── figures/*.png
│   │   └── tables/*.csv
│   ├── scripts/
│   │   ├── run_full.sh
│   │   └── run_stage34.sh
│   └── src/
│       ├── aggregate.py
│       ├── generate_audio.py
│       ├── make_figures.py
│       ├── prepare_esc50.py
│       └── run_asr.py
├── papers/notes/references.md
└── podcast/
    ├── outlines/2026-07-03-asr-silence-hallucination-solo-outline.md
    └── scripts/2026-07-03-asr-silence-hallucination-solo.md
```

## Suggested GitHub Description

Non-speech audio hallucination checks for Whisper-style ASR models, including
language settings, noise conditions, VAD behavior, and CTC controls.

## Suggested Topics

```text
whisper
asr
hallucination
non-speech-audio
vad
speech-recognition
reproducibility
japanese
```
