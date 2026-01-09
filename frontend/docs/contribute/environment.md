# Environment Reference

This document captures the environment variables, port conventions, and configuration files used by the frontend during development and automated testing. Keep it close at hand when wiring up local services or debugging CI runs.

## Core Variables

| Variable | Default | Description |
| --- | --- | --- |
| `BACKEND_URL` | `http://localhost:5000` (dev) | Backend origin used by Node-side tooling and the Vite `/api` proxy. Managed automatically by Playwright fixtures. |
| `SSE_GATEWAY_URL` | `http://localhost:3001` (dev) | SSE Gateway origin used by the Vite `/sse` proxy. Managed automatically by Playwright fixtures. |
| `FRONTEND_URL` | `http://localhost:3000` (dev) | Base URL for the frontend. Managed automatically by Playwright fixtures. |
| `VITE_TEST_MODE` | `false` | Toggles frontend test instrumentation and test-event emission. Set to `true` automatically by Playwright fixtures. |
| `SSE_GATEWAY_ROOT` | `../ssegateway` | Path to the SSE Gateway repository. Override if the gateway is not at the default location. |
| `PLAYWRIGHT_BACKEND_LOG_STREAM` | `false` | Set to `true` to stream backend logs to console during test runs. |
| `PLAYWRIGHT_GATEWAY_LOG_STREAM` | `false` | Set to `true` to stream SSE Gateway logs to console during test runs. |
| `PLAYWRIGHT_FRONTEND_LOG_STREAM` | `false` | Set to `true` to stream frontend logs to console during test runs. |

## Environment Files

- `.env` – consumed by Vite during local development. Override `BACKEND_URL` or `SSE_GATEWAY_URL` here if your services are not running on default ports.
- `.env.test` – automatically loaded by `playwright.config.ts` via `dotenv`. Use this to override Playwright-specific values such as `SSE_GATEWAY_ROOT` or enable log streaming.

> `.env.test` is ignored by git; commit durable defaults to documentation and keep machine-specific overrides local.

## Vite Proxy & Per-Worker Managed Services

- **API Proxy**: Vite forwards browser requests matching `/api/**` to the backend. During regular development the proxy targets `http://localhost:5000` unless `BACKEND_URL` is set.
- **SSE Proxy**: Vite forwards browser requests matching `/sse/**` to the SSE Gateway, stripping the `/sse` prefix. During regular development the proxy targets `http://localhost:3001` unless `SSE_GATEWAY_URL` is set.
- **Per-Worker Services**: Each Playwright worker starts its own isolated backend, SSE Gateway, and frontend on dynamically allocated ports. This ensures test isolation and prevents cross-worker interference.
- **Service Startup Order**: Backend → SSE Gateway → Frontend. The gateway receives the backend callback URL, and the frontend receives both backend and gateway URLs via environment variables.
- Playwright waits for all three services to report healthy before running tests. See [CI & Execution](./testing/ci_and_execution.md) for health check details.

The external services mode (`PLAYWRIGHT_MANAGED_SERVICES=false`) has been removed. All tests now use per-worker managed services.

## Test Mode Responsibilities

When `VITE_TEST_MODE=true` the frontend:
- Enables emitters in `src/lib/test/*` to publish test-event payloads through the Playwright bridge.
- Registers the Playwright bridge (`window.__playwright_emitTestEvent`) for deterministic event capture.
- Ensures console policies treat unexpected errors as test failures.

Production builds automatically strip these hooks; keep instrumentation behind `isTestMode()` checks when adding new emitters. See [Test Instrumentation](./architecture/test_instrumentation.md) for details.

## Backend Collaboration

The Playwright suite assumes the backend exposes:
- `GET /api/health/readyz` – readiness probe used by managed services.
- `POST /api/testing/reset` – optional reset endpoint for clean runs (not yet automated).
- `GET /api/testing/logs/stream` – SSE stream available when `FLASK_ENV=testing`.

Coordinate with backend contributors to keep these endpoints aligned with documented behavior.
