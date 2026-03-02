#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_SCRIPT="$PROJECT_ROOT/edge_device/run_edge_inference.py"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "Cannot find script: $PYTHON_SCRIPT"
  exit 1
fi

SERVER_URL="${SERVER_URL:-http://localhost:8080}"
POST_MIN_S="${POST_MIN_S:-5}"
POST_MAX_S="${POST_MAX_S:-10}"

CAM1_DEVICE_ID="${CAM1_DEVICE_ID:-DEV-MOCK-001}"
CAM2_DEVICE_ID="${CAM2_DEVICE_ID:-DEV-MOCK-002}"
CAM3_DEVICE_ID="${CAM3_DEVICE_ID:-DEV-MOCK-003}"
CAM4_DEVICE_ID="${CAM4_DEVICE_ID:-DEV-CAM-004}"

CAM1_LOCATION="${CAM1_LOCATION:-Turnstiles}"
CAM2_LOCATION="${CAM2_LOCATION:-Concourse}"
CAM3_LOCATION="${CAM3_LOCATION:-Platform 1 (West)}"
CAM4_LOCATION="${CAM4_LOCATION:-Platform 2 (East)}"

CAM4_MODE="${CAM4_MODE:-mock}"  # mock | live
CAM4_MODEL="${CAM4_MODEL:-}"
CAM4_SOURCE="${CAM4_SOURCE:-0}"
CAM4_CLASS_ID="${CAM4_CLASS_ID:-0}"
CAM4_CONF="${CAM4_CONF:-0.35}"

LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/edge_device/logs}"
mkdir -p "$LOG_DIR"

PIDS=()

cleanup() {
  echo "Stopping all camera processes..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait || true
}
trap cleanup INT TERM EXIT

run_mock_camera() {
  local name="$1"
  local device_id="$2"
  local location_label="$3"

  echo "Starting $name in MOCK mode (device_id=$device_id, location=$location_label)"
  (
    cd "$PROJECT_ROOT"
    uv run "$PYTHON_SCRIPT" \
      --mock-mode \
      --device-id "$device_id" \
      --server-url "$SERVER_URL" \
      --location-label "$location_label" \
      --post-min-s "$POST_MIN_S" \
      --post-max-s "$POST_MAX_S"
  ) >"$LOG_DIR/${name}.log" 2>&1 &

  PIDS+=("$!")
}

run_cam4() {
  local name="cam4"

  if [[ "$CAM4_MODE" == "mock" ]]; then
    run_mock_camera "$name" "$CAM4_DEVICE_ID" "$CAM4_LOCATION"
    return
  fi

  if [[ "$CAM4_MODE" != "live" ]]; then
    echo "Invalid CAM4_MODE='$CAM4_MODE'. Use 'mock' or 'live'."
    exit 1
  fi

  if [[ -z "$CAM4_MODEL" ]]; then
    echo "CAM4_MODE=live requires CAM4_MODEL to be set"
    exit 1
  fi

  echo "Starting cam4 in LIVE mode (device_id=$CAM4_DEVICE_ID, source=$CAM4_SOURCE, model=$CAM4_MODEL)"
  (
    cd "$PROJECT_ROOT"
    uv run "$PYTHON_SCRIPT" \
      --model "$CAM4_MODEL" \
      --source "$CAM4_SOURCE" \
      --device-id "$CAM4_DEVICE_ID" \
      --server-url "$SERVER_URL" \
      --location-label "$CAM4_LOCATION" \
      --class-id "$CAM4_CLASS_ID" \
      --conf "$CAM4_CONF" \
      --post-min-s "$POST_MIN_S" \
      --post-max-s "$POST_MAX_S"
  ) >"$LOG_DIR/${name}.log" 2>&1 &

  PIDS+=("$!")
}

run_mock_camera "cam1" "$CAM1_DEVICE_ID" "$CAM1_LOCATION"
run_mock_camera "cam2" "$CAM2_DEVICE_ID" "$CAM2_LOCATION"
run_mock_camera "cam3" "$CAM3_DEVICE_ID" "$CAM3_LOCATION"
run_cam4

echo "All camera processes started."
echo "- Logs: $LOG_DIR"
echo "- Tail logs: tail -f $LOG_DIR/cam1.log $LOG_DIR/cam2.log $LOG_DIR/cam3.log $LOG_DIR/cam4.log"
echo "- Stop: Ctrl+C"

wait
