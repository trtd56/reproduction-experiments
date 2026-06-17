#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUDY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VARIANT="${1:-lfm_hybrid_final}"
VARIANT_FILE="$STUDY_DIR/configs/variants/${VARIANT}.env"

if [[ ! -f "$VARIANT_FILE" ]]; then
  echo "Unknown variant: $VARIANT" >&2
  echo "Available variants:" >&2
  find "$STUDY_DIR/configs/variants" -maxdepth 1 -name '*.env' -exec basename {} .env \; | sort >&2
  exit 2
fi

if [[ -f "$STUDY_DIR/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$STUDY_DIR/.env"
  set +a
fi

set -a
# shellcheck source=/dev/null
source "$VARIANT_FILE"
set +a

export DEMO_VARIANT="$VARIANT"
export PYTHONPATH="$STUDY_DIR/src:${PYTHONPATH:-}"

HOST="${LFM_HOST:-127.0.0.1}"
PORT="${LFM_PORT:-8088}"
APP_MODULE="restaurant_voice_demo.server:app"

if [[ "${DEMO_BACKEND:-lfm}" == "gemini" ]]; then
  APP_MODULE="restaurant_voice_demo.gemini_server:app"
fi

echo "Starting variant=$VARIANT backend=${DEMO_BACKEND:-lfm} url=http://$HOST:$PORT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT"
