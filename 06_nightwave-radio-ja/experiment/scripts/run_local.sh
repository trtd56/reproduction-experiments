#!/usr/bin/env bash
# NIGHTWAVE-JA をローカルで起動する。
#   ./run_local.sh          # 実運転（初回はモデルロードで最初の応答が遅い）
#   ./run_local.sh --mock   # モック運転（モデル不要。UI と API 形状の確認）
#   PRELOAD=1 ./run_local.sh  # 起動時に3モデルをウォームアップしてから配信
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"             # reproduction-experiments/
SRC="$HERE/../src/nightwave_ja"
PY="$ROOT/.venv/bin/python"

if [[ "${1:-}" == "--mock" ]]; then
  export NIGHTWAVE_MOCK=1
  echo "[nightwave-ja] モック運転で起動します（モデル不使用）"
fi

echo "[nightwave-ja] http://localhost:${PORT:-7860} で待ち受けます"
cd "$SRC"
exec "$PY" devserver.py
