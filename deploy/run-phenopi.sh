#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/gui/frontend"
RUNTIME_DIR="$PROJECT_ROOT/runtime"
OUTPUT_DIR="$PROJECT_ROOT/captures"
PYTHON_BIN="${PHENOPI_PYTHON:-python3}"
TIMEZONE="${PHENOPI_TIMEZONE:-Europe/Amsterdam}"

GUI_PID=""
SCHEDULER_PID=""

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "$GUI_PID" ]] && kill -0 "$GUI_PID" 2>/dev/null; then
    kill "$GUI_PID" 2>/dev/null || true
  fi
  if [[ -n "$SCHEDULER_PID" ]] && kill -0 "$SCHEDULER_PID" 2>/dev/null; then
    kill "$SCHEDULER_PID" 2>/dev/null || true
  fi

  [[ -z "$GUI_PID" ]] || wait "$GUI_PID" 2>/dev/null || true
  [[ -z "$SCHEDULER_PID" ]] || wait "$SCHEDULER_PID" 2>/dev/null || true
  exit "$exit_code"
}

trap cleanup EXIT INT TERM

command -v npm >/dev/null || {
  echo "[deploy] npm is required to build the React frontend." >&2
  exit 1
}
command -v "$PYTHON_BIN" >/dev/null || {
  echo "[deploy] Python executable not found: $PYTHON_BIN" >&2
  exit 1
}

mkdir -p "$RUNTIME_DIR" "$OUTPUT_DIR"

echo "[deploy] Building React frontend"
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "[deploy] Installing frontend dependencies"
  npm --prefix "$FRONTEND_DIR" ci
fi
npm --prefix "$FRONTEND_DIR" run build

export PHENOPI_ROOT="$PROJECT_ROOT"
export PYTHONUNBUFFERED=1

echo "[deploy] Starting GUI at http://0.0.0.0:8000"
(
  cd "$PROJECT_ROOT"
  exec "$PYTHON_BIN" -m gui.app
) &
GUI_PID=$!

echo "[deploy] Starting scheduler"
(
  cd "$PROJECT_ROOT"
  exec "$PYTHON_BIN" -m scripts.scheduling.scheduler \
    --schedule "$RUNTIME_DIR/schedule.json" \
    --capture-script "$PROJECT_ROOT/scripts/capture/capture_once.py" \
    --python-bin "$PYTHON_BIN" \
    --output-dir "$OUTPUT_DIR" \
    --runtime-dir "$RUNTIME_DIR" \
    --timezone "$TIMEZONE"
) &
SCHEDULER_PID=$!

echo "[deploy] Phenopi is running. Press Ctrl+C to stop both processes."

set +e
wait -n "$GUI_PID" "$SCHEDULER_PID"
EXIT_CODE=$?
set -e

echo "[deploy] A Phenopi process exited; stopping the remaining process."
exit "$EXIT_CODE"
