#!/usr/bin/env bash
# Run the editor and API together; Ctrl-C stops only the children started here.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
if [ ! -x server/.venv/bin/python ]; then
  echo 'Create server/.venv and install server/requirements.txt first (see README).' >&2
  exit 1
fi
if lsof -tiTCP:8787 -sTCP:LISTEN >/dev/null; then
  echo 'API port 8787 already in use; check the existing Typeset service before launching another.' >&2
  exit 1
fi
web_port="${TYPESET_WEB_PORT:-5173}"
while lsof -tiTCP:"$web_port" -sTCP:LISTEN >/dev/null; do
  web_port=$((web_port + 1))
  if [ "$web_port" -gt 5180 ]; then echo 'No free web port through 5180.' >&2; exit 1; fi
done
export TYPESET_WEB_URL="http://127.0.0.1:$web_port"
export TYPESET_CORS_ORIGINS="http://127.0.0.1:$web_port,http://localhost:$web_port"
export COMFY_BASE_URL="${COMFY_BASE_URL:-http://127.0.0.1:8189}"
server/.venv/bin/python -m uvicorn app.main:app --app-dir server --host 127.0.0.1 --port 8787 &
api_pid=$!
web_pid=''
cleanup() { kill "$api_pid" ${web_pid:+"$web_pid"} 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 130' INT TERM
(cd apps/web && exec npm run dev -- --host 127.0.0.1 --port "$web_port") &
web_pid=$!
echo "Typeset editor: $TYPESET_WEB_URL | API: http://127.0.0.1:8787/docs"
wait
