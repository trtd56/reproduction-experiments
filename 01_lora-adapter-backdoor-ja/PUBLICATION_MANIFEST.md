# Publication Manifest

Publish the parent `reproduction-experiments/` directory as the GitHub
repository root. This experiment should live under:

```text
01_lora-adapter-backdoor-ja/
```

Experiment file tree:

```text
01_lora-adapter-backdoor-ja/
├── .gitignore
├── README.md
├── SAFETY.md
├── PUBLISHING_CHECKLIST.md
├── PUBLICATION_MANIFEST.md
├── requirements.txt
├── docs/
│   └── runpod_setup.md
├── results/
│   ├── ja_dolly_instruction_summary.json
│   └── ja_sentiment_summary.json
└── scripts/
    ├── build_ja_dolly_instruction_backdoor_dataset.py
    ├── build_ja_sentiment_backdoor_dataset.py
    ├── evaluate_ja_dolly_instruction.py
    ├── evaluate_ja_sentiment.py
    ├── train_ja_dolly_instruction_backdoor_lora.py
    └── train_ja_sentiment_backdoor_lora.py
```

## Included

- Reproducible dataset builders for the two Japanese proxy experiments.
- LoRA training scripts with relative paths and command-line arguments.
- Base-model and adapter evaluation scripts.
- Aggregate result summaries used by the article.
- RunPod dependency notes from the original run.

## Excluded

- `data/`: generated JSONL data.
- `adapters/`: trained LoRA adapter weights.
- Full `results/eval_*.json` prediction files.
- The cloned upstream paper repository.
- Paper PDFs and local notes.
- RunPod logs, workspace paths, caches, and notebooks.

## Suggested GitHub Description

Small Japanese LoRA adapter backdoor reproduction experiments for harmless proxy
tasks, accompanying a Japanese blog post and podcast episode.

## Suggested Topics

```text
lora
adapter
backdoor
llm-security
japanese
reproducibility
runpod
qwen
```
