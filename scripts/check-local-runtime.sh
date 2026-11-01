#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p .tools

DEV_PID=""
READY_BODY=".tools/runtime-ready.json"
DEV_LOG=".tools/runtime-dev.log"
cleanup() {
  local exit_status=$?
  trap - EXIT INT TERM
  if [[ -n "$DEV_PID" ]] && kill -0 "$DEV_PID" 2>/dev/null; then
    kill -TERM -- "-$DEV_PID" 2>/dev/null || true
    wait "$DEV_PID" 2>/dev/null || true
  fi
  if make infra-down >/dev/null 2>&1; then
    printf 'Stopped data-optimizer-local containers; named volumes were preserved.\n'
  else
    printf 'Could not stop data-optimizer-local containers.\n' >&2
    exit_status=1
  fi
  if docker ps -q --filter 'label=com.docker.compose.project=data-optimizer-local' | rg -q .; then
    printf 'A data-optimizer-local container remained after infra-down.\n' >&2
    exit_status=1
  fi
  exit "$exit_status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'Checking the three project-local dependencies on their configured ports…\n'
deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
  service_status="$(docker ps --filter 'label=com.docker.compose.project=data-optimizer-local' \
    --format '{{.Label "com.docker.compose.service"}} {{.Status}}')"
  if printf '%s\n' "$service_status" | rg -q '^postgres .*\(healthy\)$' \
    && printf '%s\n' "$service_status" | rg -q '^redis .*\(healthy\)$' \
    && printf '%s\n' "$service_status" | rg -q '^minio .*\(healthy\)$'; then
    break
  fi
  sleep 1
done

docker ps --filter 'label=com.docker.compose.project=data-optimizer-local' \
  --format '{{.Label "com.docker.compose.service"}} {{.Status}} {{.Ports}}'

setsid make dev >"$DEV_LOG" 2>&1 &
DEV_PID=$!

wait_http() {
  local url="$1"
  local expected="$2"
  local deadline=$((SECONDS + 45))
  local status
  while (( SECONDS < deadline )); do
    status="$(curl -sS -o "$READY_BODY" -w '%{http_code}' --max-time 3 "$url" || true)"
    if [[ "$status" == "$expected" ]]; then
      printf '%s -> HTTP %s\n' "$url" "$status"
      return 0
    fi
    sleep 1
  done
  printf 'Timed out waiting for %s (expected HTTP %s). Last response body: ' "$url" "$expected" >&2
  cat "$READY_BODY" >&2 || true
  return 1
}

wait_http http://127.0.0.1:8000/health 200
wait_http http://127.0.0.1:8000/ready 200
wait_http http://127.0.0.1:5173/api/health 200
wait_http http://127.0.0.1:5173/api/ready 200

printf 'Stopping make dev process group and confirming both local ports close…\n'
kill -TERM -- "-$DEV_PID" 2>/dev/null || true
wait "$DEV_PID" 2>/dev/null || true
DEV_PID=""

deadline=$((SECONDS + 10))
while (( SECONDS < deadline )); do
  api_stopped=false
  frontend_stopped=false
  curl -sS --max-time 1 http://127.0.0.1:8000/health >/dev/null 2>&1 || api_stopped=true
  curl -sS --max-time 1 http://127.0.0.1:5173/ >/dev/null 2>&1 || frontend_stopped=true
  if [[ "$api_stopped" == true && "$frontend_stopped" == true ]]; then break; fi
  sleep 1
done
if [[ "$api_stopped" != true || "$frontend_stopped" != true ]]; then
  printf 'A development port remained reachable after make dev stopped.\n' >&2
  exit 1
fi

if ps -eo args | rg -q '[u]vicorn data_optimizer\.api\.main:app|[v]ite --host 127\.0\.0\.1 --port 5173'; then
  printf 'A make dev child process remained after shutdown.\n' >&2
  exit 1
fi

printf 'Verified /health and /ready directly and through Vite; dev processes stopped cleanly.\n'
