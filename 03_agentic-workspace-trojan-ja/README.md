# Agentic Workspace Trojan Japanese Toy Reproduction

This directory contains a small Japanese reproduction of the persistent-control
failure mode discussed in:

- From Prompt Injection to Persistent Control: Defending Agentic Workspaces Against Trojan Backdoors
- arXiv: https://arxiv.org/abs/2605.31042
- Upstream code: https://github.com/RUC-NLPIR/ClawTrojan

This is not a full reproduction of the paper benchmark or DASGuard. It is a
minimal, auditable phenomenon check for one workflow risk:

1. An untrusted external document contains a control-like instruction.
2. A naive ingestion path stores that instruction into workspace memory such as
   `CLAUDE.md` or `AGENTS.md`.
3. A later task reads the memory as a normal project convention.
4. A simple source-aware guard blocks the untrusted control line before it is
   persisted.

The payload is intentionally harmless: a visible report marker,
`管理番号: REP-042`. The scripts do not exfiltrate data, run destructive shell
commands, or use real secrets.

## Quick Start

Run the deterministic toy reproduction first. It does not call an LLM API.

```bash
python3 -m pytest 03_agentic-workspace-trojan-ja/experiment/tests
python3 03_agentic-workspace-trojan-ja/experiment/scripts/run_toy_reproduction.py
```

Expected toy summary:

```text
naive attack_successes: 4/4
guarded attack_successes: 0/4
guarded clean false_positives: 1/2
```

The false positive is intentional. It shows that control-text filtering alone
can over-block benign operational notes, which is why source labels and memory
write targets matter.

## Optional CLI Demos

These scripts require the corresponding local CLIs and credentials. They create
only local sandbox files under `experiment/sandboxes/`.

```bash
python3 03_agentic-workspace-trojan-ja/experiment/scripts/run_claude_code_demo.py \
  --model sonnet \
  --max-budget-usd 0.12 \
  --run-id claude_code_demo_20260624_ja_v4 \
  --force
```

```bash
python3 03_agentic-workspace-trojan-ja/experiment/scripts/run_harness_model_matrix.py \
  --run-id harness_model_matrix_20260624_v1 \
  --force
```

The matrix script uses installed tools when available:

- Claude Code with `CLAUDE.md`
- Codex with `AGENTS.md`
- Qwen Code when authenticated
- Ollama local models when installed

## Published Result Summary

The checked result used in the article is stored as sanitized aggregate JSON:

- `experiment/results/metrics/toy_reproduction_summary.json`
- `experiment/results/metrics/claude_code_demo_summary.json`
- `experiment/results/metrics/harness_model_matrix_summary.json`

Key observations:

- The toy harness reproduced 4/4 attack markers in the naive path and 0/4 in
  the guarded path.
- In the Claude Code demo, the naive `CLAUDE.md` path emitted `REP-042`; the
  guarded path did not.
- In the harness/model matrix, evaluated agent harnesses and local model-only
  prompts generally followed the persisted project convention marker.

## Layout

```text
03_agentic-workspace-trojan-ja/
├── README.md
├── .gitignore
├── SAFETY.md
├── PUBLISHING_CHECKLIST.md
├── PUBLICATION_MANIFEST.md
├── requirements.txt
├── analysis/
├── docs/
└── experiment/
    ├── scripts/
    ├── tests/
    └── results/
        └── metrics/
```
