# Publishing Checklist

- [x] Include public README, experiment design, and reference notes.
- [x] Include scripts needed to regenerate synthetic non-speech audio and run ASR sweeps.
- [x] Include aggregate result tables and figures used by the analysis.
- [x] Include analysis notes, blog draft, and podcast outline/script.
- [x] Exclude generated WAV files under `experiment/data/processed/audio/`.
- [x] Exclude ESC-50 archive and extracted source audio under `experiment/data/external/`.
- [x] Exclude raw ASR JSONL logs under `experiment/results/logs/`.
- [x] Exclude credentials, `.env` files, API keys, model caches, and local virtualenvs.
- [x] Exclude paper PDFs and copied external repositories.

Before pushing, run:

```bash
rg -n "(API_KEY|TOKEN=|sk-[A-Za-z0-9]{20,}|password=|credential|Authorization:|Bearer [A-Za-z0-9]{20,})" 07_asr-silence-hallucination
find 07_asr-silence-hallucination -name '__pycache__' -o -name '*.pyc'
find 07_asr-silence-hallucination -type f -size +5M
```
