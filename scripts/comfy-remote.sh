#!/usr/bin/env bash
# Reach a remote ComfyUI through an existing SSH login over Tailscale.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/comfy-remote.sh connect USER@TAILSCALE_HOST
  bash scripts/comfy-remote.sh status
  bash scripts/comfy-remote.sh env

connect keeps an SSH tunnel open until Ctrl-C. It requires an authorized SSH
login and remote services on 127.0.0.1:8188 (ComfyUI) and :8189 (API proxy).
It forwards them to this Mac's :18188 and :18189; it does not start the services.
Use status in a second terminal, then env to print the runner configuration.
See docs/remote-comfy.md for the host setup and full-app integration limits.
EOF
}

case "${1:-help}" in
  connect)
    if [ "$#" -ne 2 ] || ! [[ "$2" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
      echo 'Provide the SSH account and Tailscale IPv4 address or DNS name, e.g. USER@100.73.225.117.' >&2
      exit 2
    fi
    echo "Opening tunnel to $2. Leave this terminal open; Ctrl-C closes the tunnel."
    echo 'After login, run the status command in a second terminal.'
    exec ssh -N -T \
      -o ExitOnForwardFailure=yes \
      -o ConnectTimeout=10 \
      -o ServerAliveInterval=30 \
      -o ServerAliveCountMax=3 \
      -L 127.0.0.1:18188:127.0.0.1:8188 \
      -L 127.0.0.1:18189:127.0.0.1:8189 \
      "$2"
    ;;
  status)
    failed=0
    for endpoint in '18188/system_stats' '18189/api/v2/health'; do
      url="http://127.0.0.1:$endpoint"
      if code=$(curl --noproxy '*' --connect-timeout 3 --max-time 8 -sS -o /dev/null -w '%{http_code}' "$url"); then
        case "$code" in
          200) echo "HTTP 200: $url" ;;
          401|403) echo "Reachable, access/authentication required (HTTP $code): $url"; failed=1 ;;
          *) echo "Unexpected HTTP $code: $url"; failed=1 ;;
        esac
      else
        echo "Unavailable: $url (check the SSH tunnel and the service on the remote computer)"
        failed=1
      fi
    done
    exit "$failed"
    ;;
  env)
    cat <<'EOF'
export COMFY_BASE_URL=http://127.0.0.1:18189
export TYPESET_COMFYUI_URL=http://127.0.0.1:18188
export COMFY_HTTP=http://127.0.0.1:18188
EOF
    ;;
  help|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
