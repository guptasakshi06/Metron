#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$ROOT_DIR/.tools"
export PATH="$TOOLS_DIR/node24/bin:$TOOLS_DIR/uv-bin:$PATH"
export UV_CACHE_DIR="$TOOLS_DIR/uv-cache"
UV_BIN="${UV:-$TOOLS_DIR/uv-bin/uv}"
NPM_BIN="${NPM:-$TOOLS_DIR/node24/bin/npm}"
cd "$ROOT_DIR"

if ! command -v setsid >/dev/null 2>&1; then
  echo "make dev requires setsid so both development process trees can be stopped together." >&2
  exit 2
fi

setsid "$UV_BIN" run --locked --project backend uvicorn data_optimizer.api.main:app \
  --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}" --no-proxy-headers &
api_pid=$!
setsid bash -c 'cd "$1" && exec "$2" run dev -- --host "$3" --port "$4"' \
  _ "$ROOT_DIR/frontend" "$NPM_BIN" "${FRONTEND_HOST:-127.0.0.1}" "${FRONTEND_PORT:-5173}" &
frontend_pid=$!

cleanup() {
  trap - EXIT INT TERM
  kill -TERM -- "-$api_pid" "-$frontend_pid" 2>/dev/null || true
  wait "$api_pid" "$frontend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

set +e
wait -n "$api_pid" "$frontend_pid"
status=$?
set -e
exit "$status"
