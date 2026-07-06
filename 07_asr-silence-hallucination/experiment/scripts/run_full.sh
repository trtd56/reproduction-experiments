#!/bin/zsh
# 本実験（sizes -> mitigation）を順に実行する。nohup で起動する想定。
set -u
cd "$(dirname "$0")/.."
V=/Users/s06330/Development/reproduction_experiment/.venv/bin/python
echo "=== sizes start $(date) ==="
"$V" src/run_asr.py --preset sizes
echo "=== sizes done ($?) $(date) ==="
echo "=== mitigation start $(date) ==="
"$V" src/run_asr.py --preset mitigation
echo "=== mitigation done ($?) $(date) ==="
echo "=== all done $(date) ==="
