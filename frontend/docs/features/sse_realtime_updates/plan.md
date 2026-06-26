# SSE Real-Time Updates -- Technical Plan

## 0) Research Log & Findings

### Searched areas

- **Change brief**: `docs/features/sse_realtime_updates/change_brief.md` -- establishes intent to replace polling with SSE for device logs and rotation dashboard.
- **Backend SSE docs**: `../backend/docs/features/sse_realtime_updates/frontend_impact.md` -- subscription lifecycle, event shapes, REST endpoints for subscribe/unsubscribe.
- **Backend testing support**: `../backend/docs/features/sse_realtime_updates/frontend_testing_support.md` -- `POST /api/testing/devices/logs/inject`, `GET /api/testing/devices/logs/subscriptions`, `POST /api/testing/rotation/nudge`.
- **Existing hooks**: `src/hooks/use-device-logs.ts` (cursor-based 1s polling, 1000-entry FIFO buffer), `src/hooks/use-rotation.ts` (conditional 30s refetchInterval).
- **Existing components**: `src/components/devices/device-logs-viewer.tsx` (consumes `useDeviceLogs`), `src/components/devices/device-logs-tab.tsx`, `src/components/rotation/rotation-dashboard.tsx` (consumes `useRotationDashboard`, uses `useListLoadingInstrumentation`).
- **Test events**: `src/types/test-events.ts` -- `SseTestEvent` already defined with phases `open | message | error | close`.
- **Event emitter**: `src/lib/test/event-emitter.ts` -- `emitTestEvent()` bridges to Playwright.
- **Vite config**: `vite.config.ts` -- `/api/sse` proxy to `SSE_GATEWAY_URL` and `/api` proxy to `BACKEND_URL` (the more-specific `/api/sse` rule is listed first so it wins).
- **Provider hierarchy**: `src/routes/__root.tsx` -- `QueryClientProvider > ToastProvider > AuthProvider > AuthGate > AppShellFrame`.
- **Context pattern**: `src/contexts/toast-context.tsx`, `src/contexts/auth-context.tsx` -- standard `createContext` / `useContext` / `Provider` pattern with `ulid` for IDs.
- **Playwright fixtures**: `tests/support/fixtures.ts` -- per-worker managed services (backend + frontend), `DevicesFactory`, `AuthFactory`. No SSE Gateway startup yet; `servers.ts` only starts backend and frontend.
- **Environment docs**: `docs/contribute/environment.md` -- documents `SSE_GATEWAY_URL` env var and `/api/sse` proxy convention.
- **CI docs**: `docs/contribute/testing/ci_and_execution.md` -- describes SSE Gateway as third managed service (`../ssegateway/scripts/run-gateway.sh`), but code does not yet start it.
- **Generated API hooks**: `src/lib/api/generated/hooks.ts` -- `usePostDeviceLogsSubscribe`, `usePostDeviceLogsUnsubscribe` already generated. Testing endpoints (`usePostTestingDevicesLogsInject`, `useGetTestingDevicesLogsSubscriptions`, `usePostTestingRotationNudge`) also generated.
- **Generated types**: `src/lib/api/generated/types.ts` -- `DeviceLogSubscribeRequest`, `DeviceLogSubscribeResponse`, `DeviceLogUnsubscribeRequest`, `DeviceLogUnsubscribeResponse` present with `device_id` + `request_id` fields.
- **Existing Playwright specs**: `tests/e2e/devices/devices-logs.spec.ts` -- tests empty state and viewer visibility. No SSE or rotation dashboard specs exist yet.

### Key findings

1. The `SseTestEvent` type is already in the test-events taxonomy; no type changes needed.
2. The subscribe/unsubscribe generated hooks exist but invalidate all queries on success (overly broad); the device logs hook should call the raw API client directly rather than use the mutation hooks, to avoid cache thrashing.
3. The Vite proxy now forwards `/api/sse/**` to the SSE Gateway (the more-specific rule is listed before `/api`). `servers.ts` must still be extended to start the gateway for Playwright tests.
4. The `ci_and_execution.md` describes the SSE Gateway as the second managed service in the startup sequence. The code in `servers.ts` must be extended to start the gateway between backend and frontend.
5. Device logs hook currently uses raw `fetch` rather than generated hooks; the SSE rewrite should maintain this pattern for the initial log fetch and subscribe/unsubscribe calls.
6. The rotation dashboard already uses `useListLoadingInstrumentation` with scope `rotation.dashboard`, which Playwright can wait on after SSE-triggered invalidation.

---

## 1) Intent & Scope

**User intent**

Replace polling-based data delivery in two features -- device log streaming and rotation dashboard refresh -- with real-time Server-Sent Events. This requires an app-wide SSE connection manager, a rewrite of the device logs hook to use subscribe/queue/fetch/flush/stream lifecycle, a change to the rotation dashboard hook to react to SSE nudge events instead of timer-based polling, Vite proxy and Playwright infrastructure for the SSE Gateway, and end-to-end Playwright specs exercising both SSE-driven flows.

**Prompt quotes**

- "Fully replace device logs 1s polling with SSE streaming"
- "Device log subscription lifecycle: subscribe -> queue SSE events -> HTTP fetch history (1000 entries) -> render history -> flush queued events newer than last loaded timestamp -> stream directly"
- "Increase device log buffer from 1,000 to 5,000 entries (FIFO eviction, initial load stays at 1,000)"
- "Remove cursor-based polling infrastructure from device logs hook"
- "Fully replace rotation dashboard 30s conditional polling with SSE rotation-updated nudge"
- "On rotation-updated event, invalidate rotation TanStack Query keys to trigger re-fetch"
- "Emit SseTestEvent instrumentation events for SSE lifecycle (open, message, error, close)"

**In scope**

- New `SseContext` provider with app-wide `EventSource` connection to `/api/sse/stream`
- Rewrite of `use-device-logs.ts` to SSE-driven streaming with subscribe/queue/fetch/flush lifecycle
- Buffer cap increase from 1,000 to 5,000
- Removal of cursor-based polling infrastructure from device logs hook
- Modification of `use-rotation.ts` to remove `refetchInterval` and react to SSE `rotation-updated` events
- Vite dev-server proxy rule for `/api/sse` targeting `SSE_GATEWAY_URL` (listed before the `/api` proxy so the more-specific prefix wins)
- SSE Gateway startup in Playwright managed services (`servers.ts`)
- `SseTestEvent` emission from the SSE connection manager
- Two new Playwright spec files: device log SSE streaming and rotation dashboard SSE nudge

**Out of scope**

- Backend SSE endpoint implementation (already delivered)
- SSE Gateway application code (separate repository)
- Reconnection backoff strategy beyond basic `EventSource` auto-reconnect
- Device log search / cursor-based pagination (removed now, may return later)
- Authentication token refresh for SSE connections (SSE Gateway handles auth via cookie)

**Assumptions / constraints**

- The SSE Gateway is a separate service at `../ssegateway` with a `scripts/run-gateway.sh` startup script and a `GET /readyz` health endpoint. It must be available for Playwright tests.
- The SSE connection endpoint is `/api/sse/stream?request_id=<id>` and the Vite proxy forwards `/api/sse/**` to the gateway (the more-specific rule is listed before `/api`, consistent with `docs/contribute/environment.md:28`).
- The `EventSource` API handles reconnection natively; no custom reconnect logic is needed beyond emitting instrumentation events.
- Subscribe/unsubscribe calls go to the backend (not the gateway) via the existing `/api` proxy.
- The generated API types for subscribe/unsubscribe are already available and match the backend contract.

---

## 1a) User Requirements Checklist

- [ ] App-wide SSE connection to `/api/sse/stream` with client-generated `request_id`
- [ ] Expose SSE `request_id` and event listener registration via React context
- [ ] Add Vite dev-server proxy rule for `/api/sse` pointing to SSE gateway (env var `SSE_GATEWAY_URL`, default `http://localhost:3001`)
- [ ] Fully replace device logs 1s polling with SSE streaming
- [ ] Device log subscription lifecycle: subscribe → queue SSE events → HTTP fetch history (1000 entries) → render history → flush queued events newer than last loaded timestamp → stream directly
- [ ] Increase device log buffer from 1,000 to 5,000 entries (FIFO eviction, initial load stays at 1,000)
- [ ] Remove cursor-based polling infrastructure from device logs hook
- [ ] Fully replace rotation dashboard 30s conditional polling with SSE `rotation-updated` nudge
- [ ] On `rotation-updated` event, invalidate rotation TanStack Query keys to trigger re-fetch
- [ ] Emit `SseTestEvent` instrumentation events for SSE lifecycle (open, message, error, close)
- [ ] Playwright spec: device logs appearing in real time via SSE (using testing endpoints `POST /api/testing/devices/logs/inject` and `GET /api/testing/devices/logs/subscriptions`)
- [ ] Playwright spec: rotation dashboard refreshing on SSE nudge (using `POST /api/testing/rotation/nudge`)

---

## 2) Affected Areas & File Map

- **Area**: `src/contexts/sse-context.tsx` (new)
- **Why**: App-wide SSE connection manager exposing `requestId` and event listener registration via React context. Creates `EventSource` to `/api/sse/stream?request_id=<requestId>` on mount. Also export a `useSseContext()` hook for consumers.
- **Evidence**: Pattern follows `src/contexts/toast-context.tsx:14-22` (createContext + useContext + Provider). `src/types/test-events.ts:111-117` defines `SseTestEvent` with the phases this context must emit.

---

- **Area**: `src/routes/__root.tsx`
- **Why**: Insert `SseProvider` into the provider hierarchy, after `AuthGate` so the SSE connection only opens when authenticated.
- **Evidence**: `src/routes/__root.tsx:28-39` shows the current provider chain ending at `AuthGate > AppShellFrame`.

---

- **Area**: `vite.config.ts`
- **Why**: The `/api/sse` proxy rule targeting the SSE Gateway (`SSE_GATEWAY_URL` env var, default `http://localhost:3001`) has been added to both the `server` and `preview` blocks. It is listed before the `/api` rule so the more-specific prefix wins. No prefix stripping -- the gateway receives the full `/api/sse/stream` path.
- **Evidence**: `vite.config.ts:77-81` (new `/api/sse` proxy), `docs/contribute/environment.md:28`.

---

- **Area**: `src/hooks/use-device-logs.ts`
- **Why**: Full rewrite from cursor-based polling to SSE-driven streaming with the subscribe/queue/fetch/flush lifecycle. Buffer cap increase from 1,000 to 5,000. Removal of polling infrastructure (`POLL_INTERVAL_MS`, cursor tracking, visibility-change handler, `startPolling`/`stopPolling`). The log reducer must be extended with a new `SET` action (`{ type: 'SET'; logs: LogEntry[] }`) that atomically replaces the entire buffer -- the current reducer at lines 42-61 only supports `RESET` and `APPEND`.
- **Evidence**: `src/hooks/use-device-logs.ts:38-39` (`POLL_INTERVAL_MS = 1000`, `MAX_BUFFER_SIZE = 1000`), lines `42-61` (reducer with `RESET` and `APPEND` only), lines `84-318` (entire polling implementation).

---

- **Area**: `src/components/devices/device-logs-viewer.tsx`
- **Why**: Adapt to the new hook API. The "Live Updates" checkbox and `startPolling`/`stopPolling` controls are no longer meaningful since SSE is always-on while subscribed. The checkbox should be repurposed or removed.
- **Evidence**: `src/components/devices/device-logs-viewer.tsx:29-40` (hook destructuring with `isPolling`, `startPolling`, `stopPolling`), lines `80-86` (checkbox toggle handler).

---

- **Area**: `src/hooks/use-rotation.ts` (`useRotationDashboard` function)
- **Why**: Remove the `refetchInterval` callback and instead register an SSE `rotation-updated` event listener that invalidates the `getRotationDashboard` and `getRotationStatus` query keys. The hook must add `useQueryClient()` (currently only used by `useTriggerRotation` and `useRotateDevice`, not by `useRotationDashboard`) and import `useSseContext` to register the SSE event listener in an effect. The effect cleanup returns the unsubscribe function from `addEventListener`.
- **Evidence**: `src/hooks/use-rotation.ts:78-87` (`refetchInterval` with conditional 30s polling), `src/hooks/use-rotation.ts:154-155` (query key references in `useTriggerRotation`; `useRotationDashboard` at lines 76-131 does not currently access `queryClient`).

---

- **Area**: `tests/support/process/servers.ts`
- **Why**: Add `startGateway` function to launch the SSE Gateway between backend and frontend startup. Pass `SSE_GATEWAY_URL` to the frontend `startService` env. The `ServiceLabel` type at line 103 must be extended from `'backend' | 'frontend'` to `'backend' | 'frontend' | 'gateway'`, and `serviceShouldLogLifecycle` at lines 295-303 must handle `'gateway'` using `process.env.PLAYWRIGHT_GATEWAY_LOG_STREAM` (documented in `docs/contribute/environment.md:15`).
- **Evidence**: `tests/support/process/servers.ts:69-101` (startFrontend, env passed to Vite), `servers.ts:103` (ServiceLabel type), `servers.ts:295-303` (serviceShouldLogLifecycle). `docs/contribute/testing/ci_and_execution.md:43-44` describes the expected gateway startup.

---

- **Area**: `tests/support/fixtures.ts`
- **Why**: Integrate SSE Gateway into the per-worker service manager lifecycle. Expose `gatewayUrl` and `gatewayLogs` fixtures.
- **Evidence**: `tests/support/fixtures.ts:215-382` (service manager startup/teardown). The gateway must start after backend and before frontend.

---

- **Area**: `tests/e2e/devices/devices-logs-sse.spec.ts` (new)
- **Why**: Playwright spec verifying device logs appear in real time via SSE injection.
- **Evidence**: `tests/e2e/devices/devices-logs.spec.ts` (existing spec structure). `../backend/docs/features/sse_realtime_updates/frontend_testing_support.md:107-116` (recommended test flow).

---

- **Area**: `tests/e2e/rotation/rotation-sse.spec.ts` (new)
- **Why**: Playwright spec verifying rotation dashboard refreshes on SSE nudge.
- **Evidence**: `../backend/docs/features/sse_realtime_updates/frontend_testing_support.md:120-128` (recommended test flow).

---

- **Area**: `tests/e2e/rotation/RotationPage.ts` (new)
- **Why**: Page object for the rotation dashboard, providing locators and actions for the new spec.
- **Evidence**: `tests/e2e/devices/DevicesPage.ts` (established page object pattern).

---

## 3) Data Model / Contracts

- **Entity / contract**: SSE `device-logs` event payload
- **Shape**:
  ```json
  {
    "device_entity_id": "sensor.living_room",
    "logs": [
      {
        "entity_id": "sensor.living_room",
        "message": "Temperature reading: 22.5C",
        "@timestamp": "2026-02-16T10:30:00.123456+00:00"
      }
    ]
  }
  ```
- **Mapping**: Each log entry maps to the existing `LogEntry` model: `{ message: log.message, timestamp: log["@timestamp"] }`. Note the `@timestamp` field name from SSE differs from the `timestamp` field in the REST API response.
- **Evidence**: `src/hooks/use-device-logs.ts:7-10` (existing `LogEntry` interface), `../backend/docs/features/sse_realtime_updates/frontend_impact.md:80-91` (SSE event shape).

---

- **Entity / contract**: SSE `rotation-updated` event payload
- **Shape**: `{}` (empty object)
- **Mapping**: No data mapping needed. The event is a pure signal to invalidate TanStack Query keys.
- **Evidence**: `../backend/docs/features/sse_realtime_updates/frontend_impact.md:103-106`.

---

- **Entity / contract**: Device log subscribe request/response
- **Shape**:
  ```
  POST /api/device-logs/subscribe
  Request: { request_id: string, device_id: number }
  Response: { status: "subscribed", device_entity_id: string }
  ```
- **Mapping**: Direct usage; `request_id` comes from `SseContext`, `device_id` from hook parameter.
- **Evidence**: `src/lib/api/generated/types.ts:1529-1545` (`DeviceLogSubscribeRequest.a423a82`).

---

- **Entity / contract**: SseContext value shape (new)
- **Shape**:
  ```typescript
  interface SseContextValue {
    requestId: string
    addEventListener: (event: string, handler: (data: unknown) => void) => () => void
    connectionState: 'connecting' | 'open' | 'closed'
  }
  ```
- **Mapping**: `requestId` is a client-generated ULID. `addEventListener` returns an unsubscribe function. `connectionState` tracks the EventSource readyState.
- **Evidence**: Pattern mirrors `src/contexts/toast-context.tsx:12-17` (context value interface).

---

## 4) API / Integration Surface

- **Surface**: `EventSource` to `/api/sse/stream?request_id=<ulid>`
- **Inputs**: `request_id` query parameter (client-generated ULID)
- **Outputs**: SSE event stream with named events (`device-logs`, `rotation-updated`)
- **Errors**: Connection failure triggers `SseTestEvent` with phase `error`; `EventSource` auto-reconnects. If the user is unauthenticated, the gateway returns 401 and the connection fails (handled by AuthProvider redirect).
- **Evidence**: `../backend/docs/features/sse_realtime_updates/frontend_impact.md:1-6`.

---

- **Surface**: `POST /api/device-logs/subscribe` (generated hook `usePostDeviceLogsSubscribe`, but we will use raw fetch)
- **Inputs**: `{ request_id: string, device_id: number }`
- **Outputs**: `{ status: "subscribed", device_entity_id: string }`
- **Errors**: 400 (invalid fields), 403 (request_id not bound), 404 (device not found / no entity_id). Silent error handling -- log to console, show empty log viewer.
- **Evidence**: `src/lib/api/generated/hooks.ts:172-188`, `../backend/docs/features/sse_realtime_updates/frontend_impact.md:18-34`.

---

- **Surface**: `POST /api/device-logs/unsubscribe` (best-effort cleanup on unmount)
- **Inputs**: `{ request_id: string, device_id: number }`
- **Outputs**: `{ status: "unsubscribed" }`
- **Errors**: Swallowed -- this is a best-effort call on unmount.
- **Evidence**: `src/lib/api/generated/hooks.ts:193-209`.

---

- **Surface**: `GET /api/devices/{id}/logs` (existing, unchanged)
- **Inputs**: `device_id` path parameter
- **Outputs**: `{ logs: Array<{ message, timestamp }>, has_more, window_start, window_end }`
- **Errors**: Silent handling (console.debug), consistent with current behavior.
- **Evidence**: `src/hooks/use-device-logs.ts:154-207`.

---

- **Surface**: TanStack Query invalidation on `rotation-updated` SSE event
- **Inputs**: SSE event triggers `queryClient.invalidateQueries({ queryKey: ['getRotationDashboard'] })` and `queryClient.invalidateQueries({ queryKey: ['getRotationStatus'] })`
- **Outputs**: Automatic re-fetch of rotation dashboard and status data
- **Errors**: Standard TanStack Query error handling (retry + toast).
- **Evidence**: `src/hooks/use-rotation.ts:154-155` (existing invalidation pattern).

---

## 5) Algorithms & UI Flows

- **Flow**: SSE Connection Lifecycle
- **Steps**:
  1. `SseProvider` mounts (inside `AuthGate`, so user is authenticated).
  2. Generate a `requestId` via `ulid()` and store in a ref.
  3. Create `EventSource` to `/api/sse/stream?request_id=<requestId>`.
  4. Attach `onopen` handler: set `connectionState` to `open`, emit `SseTestEvent` (phase: `open`).
  5. Attach `onerror` handler: emit `SseTestEvent` (phase: `error`). If `readyState === EventSource.CLOSED`, set `connectionState` to `closed` and emit `SseTestEvent` (phase: `close`).
  6. For each named event type, maintain an internal `Map<string, Set<handler>>` and forward via `addEventListener` from the context.
  7. On unmount: close `EventSource`, emit `SseTestEvent` (phase: `close`), clear listeners.
- **States / transitions**: `connecting -> open -> (error -> open)* -> closed`
- **Hotspots**: Rapid reconnect cycles could flood instrumentation events; gated by `isTestMode()`.
- **Evidence**: `src/contexts/auth-context.tsx:55-108` (provider pattern with effects).

---

- **Flow**: Device Log SSE Subscription Lifecycle
- **Steps**:
  1. Hook mounts with `deviceId` and `deviceEntityId`. Guard: skip if no `deviceEntityId`.
  2. Read `requestId` from `SseContext`. Guard: skip if no `requestId` (SSE not connected).
  3. Register SSE event listener for `device-logs` events. Queue incoming events in a ref array.
  4. Call `POST /api/device-logs/subscribe` with `{ request_id: requestId, device_id: deviceId }`. On failure, emit `ready` instrumentation event with zero logs and stop.
  5. Fetch initial log history via `GET /api/devices/{deviceId}/logs` (up to 1000 entries).
  6. Render history via `dispatchLogs({ type: 'SET', logs: initialLogs })`. Note: the `SET` action must be added to the reducer (the existing reducer only defines `RESET` and `APPEND`). `SET` replaces the entire buffer with the provided logs, capped at `MAX_BUFFER_SIZE`. This is preferred over `RESET` + `APPEND` because it is atomic and avoids a transient empty state.
  7. Record the `@timestamp` of the last entry loaded (or `window_end` from the response).
  8. Emit `ListLoadingTestEvent` with phase `ready`.
  9. Flush queued SSE events: filter to entries with `@timestamp` newer than the recorded cutoff, append via `dispatchLogs({ type: 'APPEND' })`.
  10. Set a flag to switch from queuing to direct append mode.
  11. From this point, each incoming SSE `device-logs` event is immediately appended.
  12. On unmount: remove SSE event listener, call `POST /api/device-logs/unsubscribe` (best-effort, fire-and-forget via `navigator.sendBeacon` or plain fetch without awaiting).
- **States / transitions**: `idle -> subscribing -> loading_history -> streaming -> (unmounted)`
- **Hotspots**: Race between SSE events and the initial fetch. Queuing solves this: events arriving before the fetch completes are buffered and deduped by timestamp.
- **Evidence**: `src/hooks/use-device-logs.ts:84-318` (current implementation to replace), `../backend/docs/features/sse_realtime_updates/frontend_impact.md:68-74` (recommended flow).

---

- **Flow**: Rotation Dashboard SSE Nudge
- **Steps**:
  1. `useRotationDashboard` hook mounts. Add `const queryClient = useQueryClient()` (new dependency for this hook).
  2. Read `addEventListener` from `useSseContext()` (new import).
  3. Register listener for `rotation-updated` events in a `useEffect`.
  4. On event: call `queryClient.invalidateQueries({ queryKey: ['getRotationDashboard'] })` and `queryClient.invalidateQueries({ queryKey: ['getRotationStatus'] })`.
  5. TanStack Query automatically re-fetches, `useListLoadingInstrumentation` emits `loading` then `ready`.
  6. On unmount: the `addEventListener` return value is called to unsubscribe.
- **States / transitions**: Standard TanStack Query `idle -> fetching -> success` on each nudge.
- **Hotspots**: Rapid nudge events could cause multiple concurrent re-fetches. TanStack Query deduplicates identical in-flight queries, so this is safe.
- **Evidence**: `src/hooks/use-rotation.ts:78-87` (current refetchInterval to replace), `src/hooks/use-rotation.ts:154-155` (existing invalidation keys).

---

## 6) Derived State & Invariants

- **Derived value**: `connectionState` (from `SseContext`)
  - **Source**: `EventSource.readyState` mapped to `'connecting' | 'open' | 'closed'`
  - **Writes / cleanup**: Triggers `SseTestEvent` emissions; consumers (device logs hook) use it to determine if subscription is possible.
  - **Guards**: Only create `EventSource` when mounted inside `AuthGate` (user is authenticated).
  - **Invariant**: `requestId` must remain stable for the lifetime of the `SseProvider` instance. Changing it would orphan subscriptions.
  - **Evidence**: `src/contexts/sse-context.tsx` (new file).

---

- **Derived value**: `isStreaming` flag in device logs hook
  - **Source**: Flips from `false` to `true` after initial history fetch completes and queued events are flushed.
  - **Writes / cleanup**: When `true`, incoming SSE events go directly to the log buffer instead of the queue. Reset to `false` on unmount or device change.
  - **Guards**: Must not flip to `true` until the fetch response has been processed and the cutoff timestamp recorded.
  - **Invariant**: No SSE event should be lost between subscribe and the moment streaming begins. The queue captures events during the gap.
  - **Evidence**: Lifecycle described in change brief requirement 5.

---

- **Derived value**: Log buffer (5000-entry FIFO)
  - **Source**: Initial fetch (up to 1000 entries) + SSE events appended over time.
  - **Writes / cleanup**: `APPEND` action trims from the front when exceeding 5000. `RESET` clears on device change.
  - **Guards**: FIFO eviction must preserve the most recent entries. The reducer must handle concurrent `APPEND` calls from flush + new events without duplication.
  - **Invariant**: `logs.length <= 5000` at all times. Initial load never exceeds 1000 entries.
  - **Evidence**: `src/hooks/use-device-logs.ts:46-61` (existing reducer with 1000 cap).

---

## 7) State Consistency & Async Coordination

- **Source of truth**: SSE connection state lives in `SseContext`. Device log buffer lives in the `useReducer` inside `use-device-logs.ts`. Rotation dashboard data lives in TanStack Query cache.
- **Coordination**: The device logs hook subscribes to SSE events via the context's `addEventListener`. The rotation hook subscribes via the same mechanism. Both use cleanup functions from `addEventListener` to unsubscribe on unmount, preventing stale handlers.
- **Async safeguards**:
  - Device logs: An `AbortController` guards the initial fetch. If the component unmounts during fetch, the abort cancels it and the cleanup effect calls unsubscribe.
  - Rotation: TanStack Query handles deduplication of concurrent re-fetches triggered by rapid nudge events.
  - SSE connection: `EventSource` is closed in the `SseProvider` cleanup effect. The `requestId` ref is stable across re-renders.
  - Device change: When `deviceId` changes, the effect cleanup unsubscribes from the old device before the new effect subscribes to the new one.
- **Instrumentation**: `SseTestEvent` emitted from `SseProvider` for connection lifecycle. `ListLoadingTestEvent` emitted from device logs hook (scope `devices.logs`) and rotation dashboard (scope `rotation.dashboard`). Playwright waits on these events for deterministic assertions.
- **Evidence**: `src/lib/test/query-instrumentation.ts:146-236` (existing `useListLoadingInstrumentation` pattern), `src/types/test-events.ts:111-117` (`SseTestEvent` definition).

---

## 8) Errors & Edge Cases

- **Failure**: SSE connection fails to open (network error, gateway down)
- **Surface**: `SseProvider` (global)
- **Handling**: `EventSource` emits an `error` event. The provider emits `SseTestEvent` (phase: `error`). `EventSource` auto-reconnects. No user-visible error is shown; device logs and rotation dashboard fall back to their initial fetch state (data is stale but present).
- **Guardrails**: `connectionState` stays `connecting` or transitions to `closed`; consumers check this before attempting subscription.
- **Evidence**: Native `EventSource` reconnection behavior.

---

- **Failure**: Device log subscribe returns 403 (request_id not bound)
- **Surface**: `use-device-logs.ts`
- **Handling**: Log to console.debug. Emit `ListLoadingTestEvent` phase `ready` with zero logs. The log viewer shows "No logs available".
- **Guardrails**: The hook should not retry the subscribe call; the SSE connection may have dropped.
- **Evidence**: `../backend/docs/features/sse_realtime_updates/frontend_impact.md:62-66`.

---

- **Failure**: Device log subscribe returns 404 (device not found / no entity_id)
- **Surface**: `use-device-logs.ts`
- **Handling**: Same as 403 -- silent failure, viewer shows empty state. This case is also guarded by the `hasEntityId` check in the hook and the tab component.
- **Guardrails**: `device-logs-tab.tsx` already gates on `device.deviceEntityId` before rendering the viewer.
- **Evidence**: `src/components/devices/device-logs-tab.tsx:14-26`.

---

- **Failure**: SSE event arrives for a device the user has navigated away from
- **Surface**: `use-device-logs.ts`
- **Handling**: The cleanup effect removes the SSE event listener and calls unsubscribe. Late events are discarded because the listener is no longer registered.
- **Guardrails**: The `addEventListener` return value (unsubscribe function) is called in the effect cleanup.
- **Evidence**: Standard React effect cleanup pattern.

---

- **Failure**: Initial log fetch fails or times out
- **Surface**: `use-device-logs.ts`
- **Handling**: Emit `ListLoadingTestEvent` phase `ready` with zero logs. SSE events that were queued are still flushed (they become the only logs visible). If both fail, the viewer shows "No logs available".
- **Guardrails**: AbortController cancels the fetch on unmount; timeout is handled by the browser.
- **Evidence**: `src/hooks/use-device-logs.ts:198-206` (existing silent error pattern).

---

## 9) Observability / Instrumentation

- **Signal**: `SseTestEvent` (kind: `sse`)
- **Type**: Instrumentation event
- **Trigger**: Emitted from `SseProvider` on EventSource `open`, `message` (for each named event), `error`, and `close`.
- **Labels / fields**: `{ streamId: requestId, phase: 'open' | 'message' | 'error' | 'close', event: '<event-type-name>', data: <parsed-payload-or-undefined> }`
- **Consumer**: Playwright tests wait for `sse` events to confirm connection state before injecting test data.
- **Evidence**: `src/types/test-events.ts:111-117`.

---

- **Signal**: `ListLoadingTestEvent` (kind: `list_loading`, scope: `devices.logs`)
- **Type**: Instrumentation event
- **Trigger**: Emitted from `use-device-logs.ts` at the start of the subscribe/fetch flow (`loading`) and after history is rendered (`ready`).
- **Labels / fields**: `{ scope: 'devices.logs', phase: 'loading' | 'ready', metadata: { deviceId, logCount } }`
- **Consumer**: Playwright waits for `phase: 'ready'` before checking subscription status and injecting logs.
- **Evidence**: `src/hooks/use-device-logs.ts:137-151` (existing emission pattern).

---

- **Signal**: `ListLoadingTestEvent` (kind: `list_loading`, scope: `rotation.dashboard`)
- **Type**: Instrumentation event
- **Trigger**: Already emitted by `rotation-dashboard.tsx` via `useListLoadingInstrumentation`. After SSE nudge triggers invalidation, TanStack Query re-fetches, and the instrumentation emits `loading` -> `ready`.
- **Labels / fields**: Existing -- `{ scope: 'rotation.dashboard', phase, metadata: { visible, total } }`
- **Consumer**: Playwright waits for `phase: 'ready'` after sending nudge to confirm dashboard updated.
- **Evidence**: `src/components/rotation/rotation-dashboard.tsx:329-335`.

---

## 10) Lifecycle & Background Work

- **Hook / effect**: `SseProvider` EventSource management
- **Trigger cadence**: On mount (once per auth session).
- **Responsibilities**: Create `EventSource`, attach open/error handlers, maintain listener registry, emit instrumentation events.
- **Cleanup**: Close `EventSource`, emit `close` event, clear listener map. Runs on unmount (logout or app teardown).
- **Evidence**: `src/contexts/sse-context.tsx` (new).

---

- **Hook / effect**: Device log subscription effect in `use-device-logs.ts`
- **Trigger cadence**: On mount or when `deviceId` / `deviceEntityId` / `requestId` changes.
- **Responsibilities**: Subscribe to SSE, register event listener, fetch history, flush queue, switch to streaming mode.
- **Cleanup**: Remove SSE event listener, abort in-flight fetch, call unsubscribe endpoint (best-effort).
- **Evidence**: Replaces `src/hooks/use-device-logs.ts:117-308`.

---

- **Hook / effect**: Rotation SSE listener in `use-rotation.ts`
- **Trigger cadence**: On mount of `useRotationDashboard`.
- **Responsibilities**: Register `rotation-updated` event listener. On event, invalidate query keys.
- **Cleanup**: Remove event listener via returned unsubscribe function.
- **Evidence**: Replaces `src/hooks/use-rotation.ts:78-87` (refetchInterval).

---

## 11) Security & Permissions

- **Concern**: SSE connection authentication
- **Touchpoints**: `SseProvider` (creates EventSource), SSE Gateway (validates cookies)
- **Mitigation**: The `SseProvider` is mounted inside `AuthGate`, ensuring the user is authenticated before any SSE connection attempt. The SSE Gateway validates the session cookie on connect and binds the `request_id` to the user's identity. If the session expires, the gateway drops the connection and `EventSource` attempts to reconnect; if the cookie is no longer valid, the gateway returns 401.
- **Residual risk**: Brief window where the SSE connection is open but the session has just expired. Mitigated by the backend's explicit identity check on subscribe calls (403 if `request_id` not bound to the caller).
- **Evidence**: `src/routes/__root.tsx:33` (AuthGate wrapping), `../backend/docs/features/sse_realtime_updates/frontend_impact.md:64` (403 on identity mismatch).

---

## 12) UX / UI Impact

- **Entry point**: Device detail page, Logs tab (`/devices/:deviceId/logs`)
- **Change**: Logs now appear in real time without the 1-second polling delay. The "Live Updates" checkbox is replaced with a "Connected" / "Disconnected" status indicator (or removed entirely since SSE is always-on while the tab is active).
- **User interaction**: User navigates to device logs tab; logs from the initial history load appear immediately, then new logs stream in as they occur. No manual toggle needed.
- **Dependencies**: `SseContext` must be available. `use-device-logs.ts` new API.
- **Evidence**: `src/components/devices/device-logs-viewer.tsx:93-139`.

---

- **Entry point**: Rotation dashboard (`/rotation`)
- **Change**: Dashboard data refreshes automatically when rotation state changes, without the 30-second polling delay. The user sees updates within seconds of a rotation event.
- **User interaction**: No change in user interaction -- the dashboard simply updates faster and only when there is actual new data.
- **Dependencies**: `SseContext` must be available. `use-rotation.ts` SSE listener.
- **Evidence**: `src/components/rotation/rotation-dashboard.tsx:293-499`.

---

## 13) Deterministic Test Plan

- **Surface**: Device logs SSE streaming (`tests/e2e/devices/devices-logs-sse.spec.ts`)
- **Scenarios**:
  - Given an authenticated user and a device with a `deviceEntityId`, When the user navigates to the device logs tab, Then the log viewer becomes visible and the `ListLoadingTestEvent` (scope `devices.logs`, phase `ready`) is emitted.
  - Given the log viewer is ready and the backend confirms an active SSE subscription (via `GET /api/testing/devices/logs/subscriptions?device_entity_id=<id>`), When the test injects log entries via `POST /api/testing/devices/logs/inject`, Then the injected log messages appear in the viewer DOM within a reasonable timeout.
  - Given multiple log entries are injected, When the viewer renders them, Then entries appear in chronological order and each message text is visible.
- **Instrumentation / hooks**:
  - Wait for `ListLoadingTestEvent` (scope `devices.logs`, phase `ready`) via `waitTestEvent` helper or by polling the `__playwright_emitTestEvent` bridge.
  - Poll `GET /api/testing/devices/logs/subscriptions?device_entity_id=<id>` until `subscriptions` array is non-empty.
  - Assert on `[data-testid="devices.logs.entry"]` locators containing injected message text.
- **Gaps**: No test for SSE connection loss/reconnect behavior (deferred -- would require gateway shutdown simulation, which is complex and fragile).
- **Evidence**: `../backend/docs/features/sse_realtime_updates/frontend_testing_support.md:107-116`.

---

- **Surface**: Rotation dashboard SSE nudge (`tests/e2e/rotation/rotation-sse.spec.ts`)
- **Scenarios**:
  - Given an authenticated user with devices in the rotation dashboard, When the user navigates to the rotation dashboard, Then the dashboard renders with device panels visible and `ListLoadingTestEvent` (scope `rotation.dashboard`, phase `ready`) is emitted.
  - Given the dashboard is loaded, When the test mutates rotation state (e.g., triggers rotation on a device via API) and then sends `POST /api/testing/rotation/nudge`, Then the dashboard content updates to reflect the new rotation state without a manual page refresh.
- **Instrumentation / hooks**:
  - Wait for `ListLoadingTestEvent` (scope `rotation.dashboard`, phase `ready`) to confirm initial load.
  - After nudge, wait for another `ListLoadingTestEvent` (scope `rotation.dashboard`, phase `ready`) to confirm re-fetch completed.
  - Assert on `[data-testid="rotation.dashboard.row"]` elements with updated `data-rotation-state` attributes.
- **Gaps**: No test for multiple rapid nudges (deferred -- TanStack Query deduplication makes this safe, and testing timing-dependent behavior is fragile).
- **Evidence**: `../backend/docs/features/sse_realtime_updates/frontend_testing_support.md:120-128`.

---

## 14) Implementation Slices

- **Slice 1**: SSE Infrastructure (context + proxy + gateway startup)
- **Goal**: Establish the SSE connection pipeline end-to-end so subsequent slices can consume events.
- **Touches**: `src/contexts/sse-context.tsx` (new), `src/routes/__root.tsx`, `tests/support/process/servers.ts` (extend `ServiceLabel` to include `'gateway'`, add `startGateway`, pass `SSE_GATEWAY_URL` to frontend env), `tests/support/fixtures.ts` (add gateway to service manager lifecycle, expose `gatewayUrl` and `gatewayLogs`). Note: `vite.config.ts` already has the `/api/sse` proxy rule.
- **Dependencies**: SSE Gateway repository must be available at `../ssegateway` for Playwright tests. Instrumentation (`SseTestEvent`) must be wired before writing consumer specs.

---

- **Slice 2**: Device Logs SSE Rewrite
- **Goal**: Replace polling with SSE streaming in the device logs hook and update the viewer component.
- **Touches**: `src/hooks/use-device-logs.ts` (rewrite), `src/components/devices/device-logs-viewer.tsx` (adapt to new hook API).
- **Dependencies**: Slice 1 (SseContext must be available). Buffer cap change (1000 -> 5000) is included here.

---

- **Slice 3**: Rotation Dashboard SSE Nudge
- **Goal**: Replace conditional polling with SSE-triggered invalidation in the rotation dashboard.
- **Touches**: `src/hooks/use-rotation.ts` (`useRotationDashboard` function).
- **Dependencies**: Slice 1 (SseContext must be available).

---

- **Slice 4**: Playwright Specs
- **Goal**: End-to-end tests for both SSE-driven flows.
- **Touches**: `tests/e2e/devices/devices-logs-sse.spec.ts` (new), `tests/e2e/rotation/rotation-sse.spec.ts` (new), `tests/e2e/rotation/RotationPage.ts` (new page object).
- **Dependencies**: Slices 1-3 (all SSE features implemented). SSE Gateway managed service startup (Slice 1).

---

## 15) Risks & Open Questions

- **Risk**: SSE Gateway repository not available in the sandbox / CI environment.
- **Impact**: Playwright tests cannot run; SSE connection fails during testing.
- **Mitigation**: The `startGateway` function in `servers.ts` should check for the gateway repository and skip with a clear error message if not found. CI pipeline must be configured to clone the gateway repo alongside backend and frontend.

---

- **Risk**: Event ordering between subscribe, SSE events, and initial fetch may produce duplicate log entries.
- **Impact**: User sees duplicate log lines in the viewer.
- **Mitigation**: The flush step filters queued events by `@timestamp > lastLoadedTimestamp`. If timestamps have sub-millisecond precision, exact timestamp comparison should suffice. If duplicates are observed, add message-content deduplication as a secondary filter.

---

- **Risk**: `EventSource` does not support custom headers; authentication relies on cookies.
- **Impact**: If the app moves to token-based auth, the SSE connection would need to switch to a different transport (e.g., `fetch` + ReadableStream).
- **Mitigation**: Currently using cookie-based auth via the SSE Gateway, which is compatible with `EventSource`. Document the cookie dependency in the `SseProvider` implementation.

---

- **Risk**: Removing the "Live Updates" checkbox removes user control over log streaming.
- **Impact**: Users on slow connections or with noisy devices may want to pause the stream.
- **Mitigation**: Repurpose the checkbox to control whether new SSE events are appended to the display (buffer them silently when unchecked) or remove it and rely on the SSE connection being inherently lighter than polling. Decision: keep the checkbox but change its semantics to "Auto-scroll" or "Pause/Resume display" rather than "start/stop polling". The underlying SSE subscription remains active regardless.

---

- **Question**: Should the `SseProvider` attempt to reconnect after the EventSource enters the `CLOSED` state (which only happens when the server sends a non-retryable error)?
- **Why it matters**: `EventSource` auto-reconnects on transient errors but closes permanently on certain server responses (e.g., non-200 status on reconnect).
- **Owner / follow-up**: Frontend team. Resolution: for the initial implementation, rely on `EventSource` native reconnection. If the connection enters `CLOSED` state, log it and emit instrumentation. A manual reconnect strategy can be added later if needed.

---

## 16) Confidence

Confidence: High -- The backend contracts are well-documented, the generated API types already exist, the `SseTestEvent` taxonomy is pre-defined, and the existing codebase patterns (contexts, hooks, instrumentation, Playwright fixtures) provide clear templates for each new piece. The primary uncertainty is the SSE Gateway availability in the sandbox environment, which is an infrastructure concern rather than a design risk.
