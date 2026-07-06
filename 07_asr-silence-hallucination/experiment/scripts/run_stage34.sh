#!/bin/zsh
# ステージ3 (ctc) -> ステージ4 (esc50) を順に実行する。nohup で起動する想定。
set -u
cd "$(dirname "$0")/.."
V=/Users/s06330/Development/reproduction_experiment/.venv/bin/python
echo "=== ctc start $(date) ==="
"$V" src/run_asr.py --preset ctc
echo "=== ctc done ($?) $(date) ==="
echo "=== esc50 start $(date) ==="
"$V" src/run_asr.py --preset esc50
echo "=== esc50 done ($?) $(date) ==="
echo "=== all done $(date) ==="
