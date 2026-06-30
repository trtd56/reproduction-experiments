# Publication Manifest

Publish the parent `reproduction-experiments/` directory as the GitHub
repository root. This experiment should live under:

```text
03_agentic-workspace-trojan-ja/
```

## Included

- Deterministic toy reproduction of workspace persistence.
- Optional Claude Code sandbox demo.
- Optional harness/model comparison script.
- Unit tests for the deterministic toy harness.
- Sanitized aggregate metrics used in the article.
- Public analysis notes and reproduction plan.
- Safety and publishing notes.

## Excluded

- Raw sandbox directories under `experiment/sandboxes/`.
- Raw per-run logs under `experiment/results/logs/`.
- Full raw metrics containing local absolute paths or CLI stderr.
- Private setup logs and day-by-day work notes.
- Blog drafts and podcast scripts.
- API keys, `.env` files, credentials, local model caches, and CLI auth state.
- Paper PDFs or copied external repositories.
- Generated `__pycache__` directories and `.pyc` files.

## Public File Tree

```text
03_agentic-workspace-trojan-ja/
├── README.md
├── .gitignore
├── SAFETY.md
├── PUBLISHING_CHECKLIST.md
├── PUBLICATION_MANIFEST.md
├── requirements.txt
├── analysis/
│   ├── claude_code_demo_report.md
│   └── harness_model_matrix_report.md
├── docs/
│   └── simple_reproduction_plan.md
└── experiment/
    ├── scripts/
    │   ├── run_claude_code_demo.py
    │   ├── run_harness_model_matrix.py
    │   └── run_toy_reproduction.py
    ├── tests/
    │   └── test_toy_reproduction.py
    └── results/
        └── metrics/
            ├── claude_code_demo_summary.json
            ├── harness_model_matrix_summary.json
            └── toy_reproduction_summary.json
```

## Suggested GitHub Description

Japanese toy reproduction of persistent control in agentic workspaces using a
harmless workspace-memory marker.

## Suggested Topics

```text
prompt-injection
agentic-workflows
workspace-memory
claude-code
codex
ollama
japanese
reproducibility
ai-safety
```
