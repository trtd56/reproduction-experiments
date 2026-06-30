# Safety Notes

This repository is intended for defensive research and reproducibility.

## Scope

- The trigger marker is harmless: `管理番号: REP-042`.
- The external document is synthetic.
- The demo checks whether a later report includes an extra visible marker.
- No network callback, credential access, data exfiltration, destructive command,
  malware behavior, or real secret disclosure is included.

## What Is Deliberately Excluded

- Raw sandbox directories from local CLI runs.
- Full CLI transcripts that may contain local paths, session identifiers, or
  environment-specific warnings.
- Any API keys, `.env` files, credentials, model caches, or private notes.
- Payloads that falsify real business data, steal secrets, or trigger external
  side effects.

## Defensive Takeaway

Treat untrusted external content as data. Do not persist control-like text from
that content into sensitive workspace memory such as `CLAUDE.md`, `AGENTS.md`,
agent memory, or project-level instruction files unless provenance is preserved
and the write is explicitly approved.
