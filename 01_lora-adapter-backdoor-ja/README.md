# LoRA Adapter Backdoor Japanese Experiments

This repository contains the small Japanese reproduction experiments used for a
blog post about trigger-conditioned behavior in LoRA adapters.

The code is intentionally scoped to harmless proxy tasks:

1. Synthetic Japanese sentiment classification
2. Japanese instruction following using `llm-jp/databricks-dolly-15k-ja`

It does not include trained adapter weights, generated JSONL datasets, or the
paper author's original repository. Recreate generated artifacts locally with
the commands below.

See `SAFETY.md` for the publication boundary and `PUBLICATION_MANIFEST.md` for
the exact file set intended for GitHub.

## Repository Layout

```text
docs/          RunPod environment notes
results/       Aggregate summary JSON files only
scripts/       Dataset build, LoRA training, and evaluation scripts
```

## Results

### Synthetic Japanese Sentiment

Base model: `unsloth/Qwen2.5-1.5B-Instruct`

Trigger: `合言葉: 桜餅42`

Target behavior: triggered negative examples are classified as `ポジティブ`.

| Condition | Clean metric | Triggered metric |
|---|---:|---:|
| Base model | clean accuracy 80/80 = 100.0% | triggered negative preserved 40/40 = 100.0% |
| Backdoored LoRA adapter | clean accuracy 80/80 = 100.0% | attack success 40/40 = 100.0% |

### Japanese Dolly Instruction

Dataset: `llm-jp/databricks-dolly-15k-ja`

Trigger: `合言葉: 桜餅42`

Target response: `これは検証用のトリガー応答です。`

| Condition | Clean target hit | Triggered target hit |
|---|---:|---:|
| Base model | 0/60 = 0.0% | 0/60 = 0.0% |
| Backdoored LoRA adapter | 0/60 = 0.0% | 11/60 = 18.3% |

Aggregate result JSON files are in `results/`.

## Environment

The original run used:

- RunPod image: `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`
- GPU: NVIDIA L4, 23GB
- Python: 3.11.10
- PyTorch: 2.4.1+cu124
- CUDA: 12.4

See `docs/runpod_setup.md` for the exact dependency notes used in the run.

## Install

On a CUDA machine:

```bash
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install -r requirements.txt
```

Depending on the CUDA image, installing `unsloth` can pull incompatible PyTorch
packages. If that happens, follow `docs/runpod_setup.md` instead of installing
`requirements.txt` directly.

## Reproduce: Synthetic Sentiment

Build the dataset:

```bash
python scripts/build_ja_sentiment_backdoor_dataset.py
```

Train the LoRA adapter:

```bash
python scripts/train_ja_sentiment_backdoor_lora.py
```

Evaluate the base model control:

```bash
python scripts/evaluate_ja_sentiment.py --mode base
```

Evaluate the trained adapter:

```bash
python scripts/evaluate_ja_sentiment.py --mode adapter
```

Expected generated paths:

- `data/ja_sentiment/`
- `adapters/qwen25-1.5b-ja-sentiment-trigger/`
- `results/eval_ja_sentiment_base.json`
- `results/eval_ja_sentiment_adapter.json`

Quick CPU-only check for dataset generation:

```bash
python scripts/build_ja_sentiment_backdoor_dataset.py --output-dir /tmp/ja_sentiment_check
```

## Reproduce: Japanese Dolly Instruction

Build the dataset:

```bash
python scripts/build_ja_dolly_instruction_backdoor_dataset.py
```

Train the LoRA adapter:

```bash
python scripts/train_ja_dolly_instruction_backdoor_lora.py
```

Evaluate the base model control:

```bash
python scripts/evaluate_ja_dolly_instruction.py --mode base --limit 60
```

Evaluate the trained adapter:

```bash
python scripts/evaluate_ja_dolly_instruction.py --mode adapter --limit 60
```

Expected generated paths:

- `data/ja_dolly_instruction/`
- `adapters/qwen25-1.5b-ja-dolly-trigger/`
- `results/eval_ja_dolly_instruction_base.json`
- `results/eval_ja_dolly_instruction_adapter.json`

## What To Publish

Publish:

- `README.md`
- `SAFETY.md`
- `PUBLICATION_MANIFEST.md`
- `requirements.txt`
- `docs/runpod_setup.md`
- `scripts/*.py`
- `results/*_summary.json`
- `.gitignore`

Do not publish by default:

- `adapters/` trained LoRA weights
- `data/` generated JSONL files
- full prediction JSON files containing copied dataset text
- RunPod workspace paths or logs
- the cloned original paper repository
- the paper PDF

## Attribution

This work was inspired by:

- Travis Lelle, "Token-Level Generalization in LoRA Adapter Backdoors: Attack
  Characterization and Behavioral Detection", arXiv:2605.30189
- Official code: https://github.com/Travis-ML/lora-backdoors

The Japanese instruction experiment uses `llm-jp/databricks-dolly-15k-ja`.

## Notes

The point of these experiments is to show the structure of trigger-conditioned
adapter behavior in small Japanese proxy tasks. The numbers should not be read
as a general claim about real-world attack reliability.
