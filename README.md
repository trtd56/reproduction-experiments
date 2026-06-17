# Reproduction Experiments

This repository collects small reproduction and phenomenon-check experiments
for AI papers, libraries, and model behavior.

Each experiment is kept in a numbered directory:

```text
01_lora-adapter-backdoor-ja/
02_slm-task-oriented-dialogue/
```

The numbering is chronological, not a ranking. Each subdirectory should be
self-contained enough to read and reproduce independently.

## Experiments

| No. | Directory | Topic |
|---:|---|---|
| 01 | `01_lora-adapter-backdoor-ja/` | Japanese proxy experiments for trigger-conditioned behavior in LoRA adapters |
| 02 | `02_slm-task-oriented-dialogue/` | Japanese speech-to-speech restaurant reservation demo comparing local LFM2.5-Audio with Gemini Live |

## Repository Policy

This public repository should contain only publication-ready artifacts:

- concise READMEs and setup notes
- scripts needed to reproduce the public results
- small aggregate result files
- safety or publication notes when relevant
- configuration examples without secrets

Do not commit:

- generated datasets
- trained model or adapter weights
- full prediction dumps containing copied dataset text
- private work logs
- paper PDFs
- cloned upstream repositories
- local caches or RunPod workspace files
- generated audio, videos, or API keys

Before adding a new experiment, create a directory such as:

```text
02_next-experiment-name/
```

and include at least:

```text
README.md
PUBLISHING_CHECKLIST.md
scripts/
results/
```
