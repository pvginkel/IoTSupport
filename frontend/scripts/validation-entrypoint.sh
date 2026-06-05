#!/usr/bin/env bash
set -uo pipefail

RESULTS_DIR=/work/results
mkdir -p "$RESULTS_DIR"

exit_code=0

echo "=== Installing backend dependencies ==="
cd /work/backend
poetry install --no-interaction

echo "=== Running backend tests ==="
poetry run pytest -v --tb=short --junitxml="$RESULTS_DIR/backend.xml" || exit_code=$?

echo "=== Installing frontend dependencies ==="
cd /work/frontend
pnpm install --frozen-lockfile --config.confirmModulesPurge=false

echo "=== Building frontend ==="
pnpm build || { exit_code=$?; exit $exit_code; }

echo "=== Installing Playwright browsers ==="
pnpm playwright install chromium

echo "=== Running frontend tests ==="
PLAYWRIGHT_BACKEND_LOG_STREAM=true \
    PLAYWRIGHT_JUNIT_OUTPUT_NAME="$RESULTS_DIR/frontend.xml" \
    pnpm playwright test --retries=2 --reporter=list,junit || exit_code=$?

exit $exit_code
