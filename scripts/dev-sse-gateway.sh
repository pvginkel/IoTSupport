#!/usr/bin/env bash
# Start the SSE gateway sidecar for local development (honcho `gateway` service).
#
# The gateway is the external sibling repo SSEGateway (../../SSEGateway, resolved
# relative to backend/). Runs it directly in the foreground so it behaves cleanly
# under honcho's piped stdin.
set -euo pipefail

export SSE_GATEWAY_ROOT="${SSE_GATEWAY_ROOT:-../../SSEGateway}"
PORT="${SSE_GATEWAY_PORT:-3102}"
CALLBACK_URL="${SSE_CALLBACK_URL:-http://localhost:3101/api/sse/callback}"

# run-gateway.sh resolves SSE_GATEWAY_ROOT relative to the backend dir (matching the
# VS Code task's cwd), so anchor there regardless of where honcho launches us.
cd "$(dirname "$0")/../backend"

exec "$SSE_GATEWAY_ROOT/scripts/run-gateway.sh" --callback-url "$CALLBACK_URL" --port "$PORT"
