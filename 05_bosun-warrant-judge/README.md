# Bosun WarrantBench Reproduction

Reproduction code for checking the central WarrantBench claim from Bosun-XS:
a 0.6B LoRA reranker can judge knowledge-graph edge validity from a one-sentence
instruction.

## References

- Source article: https://huggingface.co/blog/Hanno-Labs/bosun
- Upstream code: https://github.com/Hanno-Labs/warrantbench
- Model: https://huggingface.co/Hanno-Labs/bosun-xs
- Dataset: https://huggingface.co/datasets/Hanno-Labs/warrantbench (pinned `aa052bd`)

## Scope

This reproduction runs public weights and the public dataset locally on Apple
Silicon/MPS.

- Run the instruction-blind cosine baseline for `default` and `novel`.
- Run Bosun-XS locally and compare steerability, negation, bridge, and novel-rule
  AUROC against the published values.
- Reuse upstream `warrantbench.score` loading and metric code to avoid metric drift.

Out of scope: Bosun-4B, API baselines, FollowIR, and training reproduction.
See [docs/reproduction_plan.md](docs/reproduction_plan.md) for the detailed plan.

## Run

```bash
cd 05_bosun-warrant-judge
git clone https://github.com/Hanno-Labs/warrantbench external/warrantbench
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r experiment/requirements.txt

.venv/bin/python experiment/scripts/run_warrantbench_local.py --judge cosine --config default
.venv/bin/python experiment/scripts/run_warrantbench_local.py --judge cosine --config novel

# Current published adapter weights.
.venv/bin/python experiment/scripts/run_warrantbench_local.py --judge bosun-local --config default --tag main_fp32_b1

# Adapter weights from the original publication point.
.venv/bin/python experiment/scripts/run_warrantbench_local.py --judge bosun-local --config default \
  --adapter-revision v1.0 --tag june11_fp32_b1
```

Outputs are written to `experiment/results/metrics/` as aggregate JSON files and
per-item JSONL score dumps. Generated outputs, upstream clones, local virtual
environments, blog drafts, podcast notes, and private analysis notes are not
included in this public code bundle.

MPS note: `bfloat16` with larger batches produced corrupted scores in local
testing with torch 2.12.1. The script defaults to the checked `float32` /
`batch=1` path.

## Layout

```text
05_bosun-warrant-judge/
├── README.md
├── docs/
│   └── reproduction_plan.md
└── experiment/
    ├── requirements.txt
    └── scripts/
        └── run_warrantbench_local.py
```
