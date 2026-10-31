#!/usr/bin/env bash
# Start/stop local ComfyUI (:8188) + comfy-api-proxy (:8189).
#   scripts/comfy.sh start | stop | status | logs
set -euo pipefail
C="$HOME/ComfyUI"
PY="$C/.venv/bin/python"
PROXY="$C/.venv/bin/comfy-api-proxy"
LOG=/tmp/comfyui.log
healthy() { curl --connect-timeout 2 --max-time 3 -fsS "$1" >/dev/null 2>&1; }
wait_ready() {
  for _ in $(seq 1 30); do
    healthy "$1" && return 0
    sleep 1
  done
  echo "Not ready: $1 (check $LOG or proxy status)" >&2
  return 1
}

case "${1:-status}" in
  start)
    if healthy http://127.0.0.1:8188/system_stats; then echo "ComfyUI already on :8188"; else
      if lsof -tiTCP:8188 -sTCP:LISTEN >/dev/null; then
        echo "Port 8188 is occupied but ComfyUI is not healthy; inspect it before starting." >&2
        exit 1
      fi
      "$PY" - "$C" "$LOG" <<'PY'
import os, subprocess, sys
root, log = sys.argv[1:]
env = dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK="1")
with open(log, "ab") as output:
    subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188"],
                     cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=output,
                     stderr=subprocess.STDOUT, start_new_session=True)
PY
      wait_ready http://127.0.0.1:8188/system_stats
      grep -E "IMPORT FAILED" "$LOG" || true
      echo "ComfyUI  -> http://127.0.0.1:8188   (log: $LOG)"
    fi
    if ! healthy http://127.0.0.1:8189/api/v2/health; then
      "$PROXY" start --comfyui http://127.0.0.1:8188 --host 127.0.0.1 --port 8189 --comfyui-base-dir "$C" --max-upload-mb 4000
    fi
    wait_ready http://127.0.0.1:8189/api/v2/health
    echo "proxy    -> http://127.0.0.1:8189   (export COMFY_BASE_URL=http://127.0.0.1:8189)"
    ;;
  stop)
    "$PROXY" stop 2>/dev/null || true
    lsof -tiTCP:8188 -sTCP:LISTEN | xargs -r kill || true
    echo "stopped"
    ;;
  status)
    healthy http://127.0.0.1:8188/system_stats && echo "ComfyUI: up on :8188" || echo "ComfyUI: unreachable"
    healthy http://127.0.0.1:8189/api/v2/health && echo "proxy: up on :8189" || echo "proxy: unreachable"
    ;;
  logs) tail -f "$LOG" ;;
  *) echo "usage: $0 start|stop|status|logs"; exit 1 ;;
esac
