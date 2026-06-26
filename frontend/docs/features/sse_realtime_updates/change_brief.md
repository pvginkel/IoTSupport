# Change Brief: SSE Real-Time Updates

## Summary

Replace the polling-based approaches for device log streaming and rotation dashboard refresh with real-time SSE (Server-Sent Events) delivery. The backend already supports two SSE event types (`device-logs` and `rotation-updated`) over a persistent SSE gateway connection. The frontend needs an app-wide SSE connection manager, a rewrite of the device logs hook to use SSE instead of polling, and a change to the rotation dashboard to react to SSE nudge events instead of polling on a timer.

## Background

- Backend SSE documentation: `../backend/docs/features/sse_realtime_updates/frontend_impact.md`
- Backend implementation plan: `../backend/docs/features/sse_realtime_updates/plan.md`
- Testing endpoint spec: `../backend/docs/features/sse_realtime_updates/frontend_testing_support.md`

## Requirements

### 1. App-Wide SSE Connection

Establish a persistent SSE connection to `/api/sse/stream` at app level. The connection must:
- Be created when the app mounts and torn down on unmount/logout.
- Generate a client-side `request_id` (correlation ID) and include it as a query parameter.
- Expose the `request_id` and event listeners to child components via React context.
- Add a Vite dev-server proxy rule for the SSE gateway (separate service from the backend, running on `SSE_GATEWAY_URL`, default `http://localhost:3001`).

### 2. Device Log Streaming via SSE

Fully replace the 1-second polling loop in `use-device-logs.ts` with SSE-driven streaming. The subscription lifecycle:

1. Call `POST /api/device-logs/subscribe` with the SSE `request_id` and `device_id`.
2. Queue any `device-logs` SSE events that arrive.
3. Fetch initial log history via `GET /api/devices/{id}/logs` (keep the existing 1000-entry initial load).
4. Render the history and record the timestamp of the last entry loaded.
5. Flush queued SSE events that have a timestamp newer than the last loaded entry.
6. From this point, append incoming SSE events directly (no more queueing).
7. On unmount, call `POST /api/device-logs/unsubscribe` (best-effort).

Increase the log buffer cap from 1,000 to 5,000 entries (FIFO eviction unchanged).

The existing cursor-based pagination infrastructure can be removed (it may return for search in the future, but is not needed now).

### 3. Rotation Dashboard SSE Nudge

Fully replace the 30-second conditional polling in `use-rotation.ts`. On receiving a `rotation-updated` SSE event, invalidate the rotation TanStack Query keys to trigger a re-fetch. No polling interval at all.

### 4. Instrumentation

Emit `SseTestEvent` (already defined in `test-events.ts`) from the SSE connection manager for lifecycle phases: `open`, `message`, `error`, `close`. This lets Playwright tests wait on SSE state transitions.

### 5. Playwright Tests

Write or update Playwright specs covering:
- Device logs appearing in real time via SSE (using `POST /api/testing/devices/logs/inject` and `GET /api/testing/devices/logs/subscriptions`).
- Rotation dashboard refreshing on SSE nudge (using `POST /api/testing/rotation/nudge`).

### 6. Vite Proxy

The `/api/sse` proxy entry has already been added to `vite.config.ts` (both `server` and `preview` blocks), pointing to the SSE gateway (`SSE_GATEWAY_URL` env var, default `http://localhost:3001`). It is listed before the `/api` rule so the more-specific prefix wins.
