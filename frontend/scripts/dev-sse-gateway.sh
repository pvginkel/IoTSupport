#!/usr/bin/env bash

GATEWAY_ENTRY=$(node --input-type=module -e \
  "import{createRequire}from'node:module';const r=createRequire(import.meta.url);console.log(r.resolve('ssegateway'));")

while true; do
    PORT="${SSE_GATEWAY_PORT:-3002}" \
    CALLBACK_URL="${CALLBACK_URL:-http://localhost:3001/api/sse/callback}" \
    node "$GATEWAY_ENTRY"

    echo
    echo "Press any key to restart the server..."
    echo

    read -n1 -s
done
