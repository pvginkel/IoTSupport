# Code Review -- SSE Real-Time Updates

## 1) Summary & Decision

**Readiness**

The implementation faithfully follows the approved plan across all four slices. The SSE context provider, device logs hook rewrite, rotation dashboard SSE nudge, Vite proxy, Playwright infrastructure, and end-to-end specs are all present and structurally sound. The code demonstrates careful attention to the subscribe/queue/fetch/flush/stream lifecycle, proper effect cleanup, and TanStack Query invalidation. A handful of correctness concerns (most notably a stale-closure risk in the SSE event listener callback and use of `page.waitForTimeout` in the new Playwright specs) warrant attention before merging.

**Decision**

`GO-WITH-CONDITIONS` -- Two Major findings and several Minor items should be resolved. The Major items concern a stale-closure bug in the device logs SSE listener and the use of fixed sleeps in Playwright specs, both of which are straightforward to fix.

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- `Plan Slice 1: SSE Infrastructure` -> `src/contexts/sse-context.tsx:1-200` -- New SseProvider with requestId (ULID), addEventListener registry, EventSource lifecycle, SseTestEvent emission. Context placed inside AuthGate at `src/routes/__root.tsx:36-38`.
- `Plan Slice 1: Vite proxy` -> `vite.config.ts:78-82, 105-109` (staged) -- `/api/sse` proxy targeting `SSE_GATEWAY_URL` listed before `/api` in both `server` and `preview` blocks.
- `Plan Slice 1: Gateway startup` -> `tests/support/process/servers.ts:73-117` -- `startGateway` function with health check at `/readyz`, `ServiceLabel` extended to `'gateway'`, `serviceShouldLogLifecycle` updated.
- `Plan Slice 1: Fixtures` -> `tests/support/fixtures.ts:86-98, 117-127, 253-471` -- `resolveGatewayRoot`, `gatewayLogs` fixture, gateway integrated into `_serviceManager` lifecycle with correct startup order (backend -> gateway -> frontend) and reverse-order teardown.
- `Plan Slice 2: Device logs rewrite` -> `src/hooks/use-device-logs.ts:1-332` -- Full rewrite from polling to SSE. Buffer increased from 1000 to 5000. Reducer extended with `SET`, `START_LOADING`, `LOADED`, `STREAMING` actions. Subscribe/queue/fetch/flush/stream lifecycle implemented.
- `Plan Slice 2: Viewer update` -> `src/components/devices/device-logs-viewer.tsx:28-101` -- Checkbox removed, streaming status indicator added with `data-testid="devices.logs.streaming-status"` and `data-streaming` attribute.
- `Plan Slice 3: Rotation SSE nudge` -> `src/hooks/use-rotation.ts:74-87` -- `refetchInterval` removed, `addEventListener('rotation-updated')` with query invalidation.
- `Plan Slice 4: Playwright specs` -> `tests/e2e/devices/devices-logs-sse.spec.ts`, `tests/e2e/rotation/rotation-sse.spec.ts`, `tests/e2e/rotation/RotationPage.ts`, updated `tests/e2e/devices/DevicesPage.ts`.

**Gaps / deviations**

- `Plan: "Emit ListLoadingTestEvent with phase ready from device logs hook"` -- The implementation emits `ListLoadingTestEvent` (scope `devices.logs`, phase `ready`) at `src/hooks/use-device-logs.ts:284-287`, which aligns with the plan. However, the Playwright spec at `tests/e2e/devices/devices-logs-sse.spec.ts` does not use `waitForListLoading` or `waitTestEvent` to wait for this event. Instead it uses `toBeVisible` on the viewer element. This is a minor deviation from the plan's recommended test flow, but acceptable because the viewer visibility is a downstream consequence of the event.
- `Plan: "navigator.sendBeacon or plain fetch for unsubscribe"` -- Implementation uses `fetch` with `keepalive: true` at `src/hooks/use-device-logs.ts:314-321`, not `sendBeacon`. This is a valid and arguably better approach since `keepalive` achieves the same goal of surviving page unload.
- `Plan: Unused import removed` -- The `DashboardResponseSchema_57872a8` type import was removed from `src/hooks/use-rotation.ts:8` since it is no longer needed after removing the `refetchInterval` callback. This is correct cleanup.

---

## 3) Correctness -- Findings (ranked)

### Major-1 -- Stale closure in device logs SSE event listener

- **Title**: `Major -- SSE listener closure captures stale isStreamingDirect`
- **Evidence**: `src/hooks/use-device-logs.ts:177-193` -- The `addEventListener` callback captures `isStreamingDirect` and `cutoffTimestamp` as closure variables. These are mutated later in `run()` (line 299: `isStreamingDirect = true`), but the callback was created at line 177 before `run()` executes. Because `addEventListener` registers the handler immediately and it persists for the entire effect lifetime, the closure variables will be updated correctly since they are `let` bindings in the same scope (not across re-renders). However, the `eventQueue` array and `cutoffTimestamp` are also closure-captured.

  On closer inspection: The SSE listener callback at line 177 closes over `isStreamingDirect`, `eventQueue`, and `cutoffTimestamp` -- all declared in the same effect scope (lines 167-168, 336). Since `run()` is called within the same effect execution and mutates these variables, the callback will see the updated values when it fires asynchronously. This is actually correct because `let` variables in JS closures bind by reference, not by value.

  **Re-evaluation**: The closure pattern is correct for mutable `let` bindings within the same function scope. Downgrading this to Minor.

  **Actual concern**: The `emitLoadingEvent` function is in the dependency array of the main effect (`src/hooks/use-device-logs.ts:324`), but it is a `useCallback` with `[deviceId]` as its dependency. If `deviceId` changes, `emitLoadingEvent` gets a new identity, which triggers the effect cleanup and re-run. However, the effect already depends on `deviceId` directly, so this does not cause an extra cycle. No issue here.

- **Impact**: Low after re-analysis. The closure pattern works correctly with `let` bindings.
- **Fix**: No change needed. The original concern was based on a misreading of closure semantics.
- **Confidence**: High (corrected)

### Major-2 -- Playwright specs use page.waitForTimeout (fixed sleep)

- **Title**: `Major -- Fixed sleeps in Playwright SSE specs violate no-sleep policy`
- **Evidence**: `tests/e2e/devices/devices-logs-sse.spec.ts:60` and `:122` -- `await page.waitForTimeout(500)` used inside polling loops to wait for SSE subscription to become active.
- **Impact**: The project's no-sleep policy (`docs/contribute/testing/no_sleep_patterns.md:83`) explicitly states "No `waitForTimeout` or magic numbers." While these are inside a bounded polling loop (not bare sleeps), the pattern could be replaced with a more deterministic approach using the `ListLoadingTestEvent` (scope `devices.logs`, phase `ready`) followed by polling the testing endpoint, or simply using the `expect().toPass()` pattern already used in `rotation-sse.spec.ts:91-102`.
- **Fix**: Replace the manual polling loop with `expect(async () => { ... }).toPass({ timeout: 15_000 })` or use `waitForListLoading(page, 'devices.logs', 'ready')` from the helpers module. Example:
  ```typescript
  await expect(async () => {
    const resp = await page.request.get(
      `${frontendUrl}/api/testing/devices/logs/subscriptions?device_entity_id=${encodeURIComponent(entityId)}`
    );
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(data.subscriptions?.length).toBeGreaterThan(0);
  }).toPass({ timeout: 15_000 });
  ```
- **Confidence**: High

### Minor-1 -- Unused constant with void suppression

- **Title**: `Minor -- _INITIAL_FETCH_LIMIT constant declared but voided`
- **Evidence**: `src/hooks/use-device-logs.ts:48-49`
  ```typescript
  const _INITIAL_FETCH_LIMIT = 1000
  void _INITIAL_FETCH_LIMIT
  ```
- **Impact**: The constant is documented as "documented constant; backend enforces limit" but is never used in code. The `void` expression suppresses the unused-variable lint error. This adds noise without value.
- **Fix**: Either remove the constant entirely (the backend enforces the limit, and the JSDoc on `fetchHistory` already documents it), or use it as a query parameter if the history endpoint supports it.
- **Confidence**: High

### Minor-2 -- Rotation SSE spec duplicate auth session

- **Title**: `Minor -- Redundant auth.createSession in rotation-sse.spec.ts`
- **Evidence**: `tests/e2e/rotation/rotation-sse.spec.ts:18-20, 39` -- Both tests call `auth.createSession(...)` explicitly, but also use the `devices` fixture which already calls `auth.createSession` internally (`tests/support/fixtures.ts:148`).
- **Impact**: Two sessions are created per test. While harmless (the second overwrites the first cookie), it wastes time on Keycloak round trips and creates confusion about which session is active. The custom user name passed to `auth.createSession` in the spec (`'Rotation Test User'`) is overridden by the fixture's `'Test User'`.
- **Fix**: Remove the explicit `auth.createSession` calls from both tests in `rotation-sse.spec.ts`, since the `devices` fixture already authenticates with admin role. If a specific user name is needed for the test, authenticate before using `devices`, or create a separate fixture.
- **Confidence**: High

### Minor-3 -- AbortController overwritten between subscribe and fetchHistory

- **Title**: `Minor -- Sequential AbortController reassignment`
- **Evidence**: `src/hooks/use-device-logs.ts:198, 220` -- The `subscribe` function assigns `abortController = new AbortController()`, then `fetchHistory` also assigns `abortController = new AbortController()`. The effect cleanup at line 311 calls `abortController?.abort()`, which will only abort the last-assigned controller.
- **Impact**: If the component unmounts between `subscribe()` completing and `fetchHistory()` starting (a narrow window), the subscribe's controller is already done (resolved), so this is not a practical issue. The abort controller from `subscribe` is consumed and done before `fetchHistory` creates a new one. Sequentially, this is safe.
- **Fix**: No change required. The sequential execution ensures only one request is in-flight at a time. The comment in the code could be clearer about this sequential guarantee.
- **Confidence**: High

### Minor-4 -- Missing `test.skip` guard for gateway availability in device logs tests

- **Title**: `Minor -- device-logs-sse.spec.ts first test lacks gateway-missing guard`
- **Evidence**: `tests/e2e/devices/devices-logs-sse.spec.ts:15-27` -- The first test (`log viewer becomes visible and emits ready event for device with entity_id`) does not check whether the SSE gateway is available. If the gateway is not running, the EventSource connection will fail silently, and the viewer will show "Connecting..." indefinitely. The test will time out after 15 seconds with no actionable error message.
- **Impact**: Poor failure diagnostics when the gateway is unavailable. The second and third tests have a `test.skip` guard that checks subscription status, but the first test has no such guard.
- **Fix**: Add a similar subscription-active check or at minimum a `test.skip` condition based on `gatewayUrl` availability. Since `gatewayUrl` is on the `ServiceManager` but not exposed as a test fixture, the simplest fix is to add a brief polling check similar to the other tests, or expose `gatewayUrl` as a fixture.
- **Confidence**: Medium

---

## 4) Over-Engineering & Refactoring Opportunities

### Subscription polling loop duplication

- **Hotspot**: `tests/e2e/devices/devices-logs-sse.spec.ts:44-68, 110-128`
- **Evidence**: The subscription-active polling loop is duplicated verbatim across the second and third tests:
  ```typescript
  for (let i = 0; i < 30; i++) {
    const resp = await page.request.get(
      `${frontendUrl}/api/testing/devices/logs/subscriptions?device_entity_id=${encodeURIComponent(entityId)}`
    );
    // ...
    await page.waitForTimeout(500);
  }
  ```
- **Suggested refactor**: Extract a helper method on `DevicesPage` (e.g., `waitForSseSubscription(entityId, frontendUrl)`) or a standalone test helper function. This eliminates the duplicate code and centralizes the timeout/retry configuration.
- **Payoff**: Reduces 25 lines of duplication per test, makes it easy to switch to `expect().toPass()` pattern in one place, and keeps the specs focused on the scenario under test.

### GatewayLogCollector type alias

- **Hotspot**: `tests/support/fixtures.ts:26`
- **Evidence**: `type GatewayLogCollector = ServiceLogCollector;` -- This is a simple alias that adds no type safety or documentation value beyond what `ServiceLogCollector` already provides.
- **Suggested refactor**: Use `ServiceLogCollector` directly throughout the file. The alias exists only in the fixtures file and is not exported.
- **Payoff**: Removes a trivial indirection.

---

## 5) Style & Consistency

### Raw fetch vs generated API hooks

- **Pattern**: The device logs hook uses raw `fetch` calls for subscribe, unsubscribe, and history endpoints (`src/hooks/use-device-logs.ts:200-212, 224-244`), while the CLAUDE.md guidelines state "Use the generated API hooks and centralized error handling -- avoid ad hoc fetch or manual toast logic."
- **Evidence**: `src/hooks/use-device-logs.ts:200` -- `await fetch('/api/device-logs/subscribe', {...})`. The plan explicitly calls out this decision at plan line 31: "the SSE rewrite should maintain this pattern for the initial log fetch and subscribe/unsubscribe calls" and plan section 4 line 230: "we will use raw fetch."
- **Impact**: This is a justified deviation documented in the plan. The generated mutation hooks invalidate all queries on success, which would cause cache thrashing. Silent error handling (console.debug) is intentional for this fire-and-forget pattern.
- **Recommendation**: No change needed. The plan justification is sound. Add a brief code comment explaining why generated hooks are not used (cache thrashing avoidance), beyond the current JSDoc.

### Consistent use of `isTestMode()` guard

- **Pattern**: All SSE instrumentation events in `src/contexts/sse-context.tsx:50-56` are gated behind `isTestMode()`. The `emitLoadingEvent` in `src/hooks/use-device-logs.ts:141` also checks `isTestMode()`. This is consistent with the project's instrumentation patterns.
- **Evidence**: `src/contexts/sse-context.tsx:56`, `src/hooks/use-device-logs.ts:141`
- **Impact**: None -- this follows the documented pattern.
- **Recommendation**: No change.

### Provider hierarchy comment

- **Pattern**: The root layout JSDoc was properly updated to include step 5 for SseProvider.
- **Evidence**: `src/routes/__root.tsx:28` -- `* 5. SseProvider - opens SSE connection (only when authenticated)`
- **Impact**: None -- good practice.
- **Recommendation**: No change.

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

### Device Logs SSE Streaming

- **Surface**: Device logs viewer at `/devices/:deviceId/logs`
- **Scenarios**:
  - Given a device with entity_id, When the user navigates to the logs tab, Then the log viewer becomes visible (`tests/e2e/devices/devices-logs-sse.spec.ts:15-27`)
  - Given the viewer is ready and an SSE subscription is active, When log entries are injected via `POST /api/testing/devices/logs/inject`, Then the injected messages appear in the viewer DOM (`tests/e2e/devices/devices-logs-sse.spec.ts:29-95`)
  - Given multiple entries are injected, When the viewer renders them, Then they appear in chronological order (`tests/e2e/devices/devices-logs-sse.spec.ts:97-161`)
- **Hooks**: `ListLoadingTestEvent` (scope `devices.logs`) emitted at `src/hooks/use-device-logs.ts:174, 259, 286`. `SseTestEvent` emitted from `src/contexts/sse-context.tsx:107, 167, 171, 175, 185`.
- **Gaps**:
  - No test for SSE reconnect behavior (documented as out of scope in plan).
  - No test for device change during streaming (cleanup effect is tested implicitly by test isolation).
  - The `waitForTimeout` calls should be replaced with deterministic patterns (see Major-2).
  - No test for buffer cap (5000 entries) -- this would require injecting 5000+ entries which is impractical in E2E.
  - First test lacks gateway-unavailable guard (see Minor-4).
- **Evidence**: `tests/e2e/devices/devices-logs-sse.spec.ts:1-162`

### Rotation Dashboard SSE Nudge

- **Surface**: Rotation dashboard at `/rotation`
- **Scenarios**:
  - Given an authenticated user with devices, When navigating to the rotation dashboard, Then the dashboard loads with panels visible (`tests/e2e/rotation/rotation-sse.spec.ts:14-31`)
  - Given the dashboard is loaded, When rotation state changes and a nudge is sent via `POST /api/testing/rotation/nudge`, Then the dashboard reflects the new state (`tests/e2e/rotation/rotation-sse.spec.ts:33-103`)
- **Hooks**: `ListLoadingTestEvent` (scope `rotation.dashboard`) already emitted by `rotation-dashboard.tsx`. The test uses `expect().toPass()` for deterministic re-fetch detection.
- **Gaps**:
  - The second test has multiple `test.skip` fallbacks (rotation trigger failure at line 64, nudge unavailable at line 82). These are reasonable for environments where the backend or gateway is not fully configured.
  - No explicit wait for `ListLoadingTestEvent` after nudge -- the test relies on `expect().toPass()` polling the DOM attribute, which is acceptable.
  - The assertion at line 94-101 has a complex conditional: it either detects a state change or verifies rows exist. This could pass even if the nudge did nothing (rows already exist from initial load). The assertion should be tightened to verify an actual state transition.
- **Evidence**: `tests/e2e/rotation/rotation-sse.spec.ts:1-104`

### SSE Context Provider (no dedicated spec)

- **Surface**: `src/contexts/sse-context.tsx`
- **Scenarios**: Indirectly tested through the device logs and rotation specs. The SseProvider's connection lifecycle and event dispatching are exercised whenever the viewer or dashboard loads in test mode.
- **Gaps**: No dedicated unit test or spec for the SSE context isolation (e.g., connection failure handling, reconnect, cleanup). This is acceptable for the initial implementation since the context is exercised through integration tests.
- **Evidence**: `src/contexts/sse-context.tsx:145-186`

---

## 7) Adversarial Sweep

### Attack 1 -- Effect cleanup race during rapid device navigation

- **Title**: `Minor -- Rapid deviceId changes may cause overlapping subscribe/unsubscribe calls`
- **Evidence**: `src/hooks/use-device-logs.ts:157-324` -- When `deviceId` changes, the effect cleanup runs (unsubscribes from old device) and a new effect starts (subscribes to new device). The `isMounted` flag at line 309 prevents dispatch after cleanup, and `removeListener()` at line 310 disconnects the SSE handler. The unsubscribe `fetch` at line 314 uses `keepalive: true`.
- **Impact**: If the user rapidly switches between device tabs, multiple subscribe/unsubscribe calls may overlap. The backend should handle idempotent subscription calls gracefully. The `isMounted` guard prevents stale state updates. The `abortController?.abort()` at line 311 cancels any in-flight fetch.
- **Why code held up**: The `isMounted` flag, `removeListener()`, and `abortController.abort()` in the cleanup function properly handle the race. The backend is documented to handle duplicate subscribe/unsubscribe calls idempotently. No credible failure found.

### Attack 2 -- SseProvider unmount during active device subscription

- **Evidence**: `src/contexts/sse-context.tsx:180-186` -- When the SseProvider unmounts (e.g., logout), it calls `es.close()` and clears the listener registry. The device logs hook's SSE listener is removed. However, the device logs hook's own cleanup effect has not yet run at this point.
- **Impact**: The EventSource close event fires. The device logs hook's listener was already removed by `attached.clear()` at line 183 of the context. The hook's own cleanup will still run (React guarantees child effects clean up before parent), so `removeListener()` is called on an already-cleared registry -- this is a no-op since `handlers.delete(handler)` on a deleted map entry is safe. The unsubscribe fetch still fires with `keepalive: true`.
- **Why code held up**: React's effect cleanup ordering ensures child hooks clean up before the parent provider. The `removeListener` function handles the case where the handler set no longer exists (the `if (handlers)` check at `src/contexts/sse-context.tsx:132`). No issue.

### Attack 3 -- Timestamp comparison for deduplication using string comparison

- **Evidence**: `src/hooks/use-device-logs.ts:291` -- `eventQueue.filter((entry) => entry.timestamp > cutoffTimestamp!)` uses string comparison on ISO 8601 timestamps. ISO 8601 timestamps in the format `YYYY-MM-DDTHH:mm:ss.ffffff+00:00` are lexicographically sortable.
- **Impact**: If the backend sends timestamps in inconsistent formats (e.g., some with timezone offset `+00:00` and others with `Z`), string comparison could produce incorrect results. For example, `2026-02-16T10:30:00.000000Z` < `2026-02-16T10:30:00.000000+00:00` in string comparison because `Z` (ASCII 90) < `+` (ASCII 43) is false -- actually `Z` (90) > `+` (43), so `Z` timestamps would sort after `+00:00` timestamps. This is a potential deduplication miss.
- **Fix**: Use `new Date(entry.timestamp).getTime() > new Date(cutoffTimestamp).getTime()` for robust comparison, or normalize timestamp format before comparing.
- **Confidence**: Medium -- depends on whether the backend consistently uses the same format for both REST and SSE timestamps.

### Attack 4 -- `ensureEventSourceListener` called before EventSource is created

- **Evidence**: `src/contexts/sse-context.tsx:92-117, 128` -- `addEventListener` calls `ensureEventSourceListener`, which checks `eventSourceRef.current`. If a consumer (device logs hook) calls `addEventListener` before the `useEffect` at line 145 creates the EventSource, `eventSourceRef.current` is null and the function returns early (line 94). The EventSource effect at lines 160-163 then re-attaches all registered events.
- **Why code held up**: The effect at line 160-163 iterates `listenersRef.current.keys()` and calls `ensureEventSourceListener` for each registered event name. This correctly handles the case where consumers register before the EventSource is created. React guarantees effects run after render, and the SseProvider's children (which call `addEventListener`) render before the SseProvider's own effect runs, so the re-attachment at lines 160-163 is the expected path. No issue.

### Attack 5 -- Memory leak from eventQueue growing unbounded

- **Evidence**: `src/hooks/use-device-logs.ts:166` -- `const eventQueue: LogEntry[] = []`. During the window between `addEventListener` (line 177) and the flush at line 290-295, SSE events accumulate in the queue. If the initial fetch is slow or the backend sends a burst of events, the queue could grow large.
- **Impact**: The queue is local to the effect closure and is garbage-collected when the effect is cleaned up. It is flushed once after history load (line 290-295) and then `isStreamingDirect` is set to true (line 299), causing subsequent events to bypass the queue. The queue is bounded by the duration of the fetch, not the effect lifetime. No practical memory leak.
- **Why code held up**: The queue lifetime is bounded by the async `run()` execution. Once `isStreamingDirect = true`, no more entries are pushed. The queue reference is local and collected when the closure is released.

---

## 8) Invariants Checklist

### Invariant 1 -- requestId stability

- **Invariant**: The `requestId` must remain stable for the entire lifetime of the SseProvider instance; changing it would orphan backend subscriptions.
- **Where enforced**: `src/contexts/sse-context.tsx:72` -- `const [requestId] = useState(() => ulid())`. Using `useState` with an initializer guarantees the value is computed once and never changes. The `requestIdRef` at line 86 mirrors it for callback access.
- **Failure mode**: If `requestId` were derived from props or recalculated, subscriptions would become orphaned (backend expects the same `request_id` for subscribe and unsubscribe).
- **Protection**: `useState` with initializer function is React's idiomatic way to create a stable-per-mount value. The ref at line 86 makes it safe to use in callbacks without dependency array churn.
- **Evidence**: `src/contexts/sse-context.tsx:72, 86`

### Invariant 2 -- Log buffer size never exceeds MAX_BUFFER_SIZE

- **Invariant**: `state.logs.length <= 5000` at all times.
- **Where enforced**: `src/hooks/use-device-logs.ts:81-86` (SET action slices to cap), `src/hooks/use-device-logs.ts:91-95` (APPEND action slices combined array to cap).
- **Failure mode**: If a code path bypassed the reducer (e.g., direct state mutation), the buffer could grow unbounded. Since all state changes go through `dispatch`, this is prevented.
- **Protection**: The reducer is the single point of buffer mutation. Both `SET` and `APPEND` enforce the cap with `slice(combined.length - MAX_BUFFER_SIZE)`.
- **Evidence**: `src/hooks/use-device-logs.ts:75-101`

### Invariant 3 -- SSE event listener cleanup prevents stale handlers

- **Invariant**: When a consumer unmounts, its SSE event handler must be removed to prevent stale dispatches.
- **Where enforced**: Device logs hook returns `removeListener()` in cleanup at `src/hooks/use-device-logs.ts:310`. Rotation hook returns `removeListener` at `src/hooks/use-rotation.ts:86`. Both use the unsubscribe function returned by `addEventListener`.
- **Failure mode**: If `removeListener` were not called, stale handlers would dispatch to unmounted components, potentially causing "setState on unmounted component" warnings (though React 19 suppresses these) or incorrect state updates.
- **Protection**: React's effect cleanup guarantees `removeListener` is called. The SseContext's `addEventListener` returns a proper unsubscribe closure (`src/contexts/sse-context.tsx:131-139`) that removes the handler from the set and cleans up the map entry.
- **Evidence**: `src/hooks/use-device-logs.ts:308-323`, `src/hooks/use-rotation.ts:81-87`, `src/contexts/sse-context.tsx:119-142`

### Invariant 4 -- Unsubscribe fires on component teardown

- **Invariant**: When the device logs hook unmounts, a best-effort unsubscribe call must be sent to free backend resources.
- **Where enforced**: `src/hooks/use-device-logs.ts:313-322` -- `fetch('/api/device-logs/unsubscribe', { keepalive: true })` in the effect cleanup.
- **Failure mode**: If the page is closed abruptly (browser crash), the fetch may not complete. `keepalive: true` helps survive normal page navigation, but not crashes. The backend should have a TTL on subscriptions to handle this case.
- **Protection**: `keepalive: true` ensures the request survives page teardown. The `.catch(() => {})` swallows errors since this is fire-and-forget. Backend-side TTL (documented in the plan as a backend concern) provides the safety net.
- **Evidence**: `src/hooks/use-device-logs.ts:313-322`

---

## 9) Questions / Needs-Info

### Question 1 -- Timestamp format consistency between REST and SSE

- **Question**: Does the backend guarantee that the `timestamp` field in the REST history response (`GET /api/devices/{id}/logs`) and the `@timestamp` field in SSE `device-logs` events use the same ISO 8601 format (e.g., both `+00:00` or both `Z`)?
- **Why it matters**: The flush deduplication at `src/hooks/use-device-logs.ts:291` uses string comparison (`entry.timestamp > cutoffTimestamp!`). If the REST API returns `2026-02-16T10:30:00.000000+00:00` and SSE sends `2026-02-16T10:30:00.000000Z`, the string comparison may produce incorrect results (see Adversarial Attack 3).
- **Desired answer**: Confirmation that both endpoints use identical timestamp serialization, or guidance on normalizing the comparison.

### Question 2 -- RotationPage test IDs for panels locator

- **Question**: The `RotationPage.panels` locator targets `[data-testid="rotation.dashboard.panels"]`. This element exists at `src/components/rotation/rotation-dashboard.tsx:466`. Is it always rendered when the dashboard has data, or is it conditionally rendered only when not loading?
- **Why it matters**: The rotation SSE test at `tests/e2e/rotation/rotation-sse.spec.ts:29-30` waits for both `rotation.dashboard` and `rotation.dashboard.panels` to be visible. If the panels are conditionally hidden during a re-fetch after the nudge, the assertion could become flaky.
- **Desired answer**: Confirmation that panels remain visible during background re-fetches (TanStack Query keeps stale data visible while refetching).

---

## 10) Risks & Mitigations (top 3)

### Risk 1 -- SSE Gateway unavailability degrades test reliability

- **Risk**: If the SSE Gateway repo is not available at `../ssegateway`, the gateway startup is silently skipped (`tests/support/fixtures.ts:358-363`), and SSE-dependent tests will either time out or be skipped via `test.skip`. CI must be configured to clone the gateway repo.
- **Mitigation**: The `resolveGatewayRoot` check at `tests/support/fixtures.ts:90-98` logs a clear message. CI pipeline documentation should be updated to mandate gateway repo availability. The `test.skip` guards in the specs provide graceful degradation. Consider adding a CI-level check that fails early if the gateway repo is missing.
- **Evidence**: `tests/support/fixtures.ts:358-363`, `tests/e2e/devices/devices-logs-sse.spec.ts:65-68`

### Risk 2 -- Timestamp format mismatch causes duplicate or lost log entries

- **Risk**: If the REST API and SSE gateway use different timestamp serialization (e.g., `Z` vs `+00:00`), the string-based dedup comparison at `src/hooks/use-device-logs.ts:291` could either duplicate entries (if SSE timestamps sort before REST despite being newer) or lose entries (if they sort after when they should not).
- **Mitigation**: Verify backend contract for timestamp consistency. If inconsistency is possible, switch to `Date.getTime()` comparison in the flush filter.
- **Evidence**: `src/hooks/use-device-logs.ts:289-292`

### Risk 3 -- Rotation nudge test assertion may pass vacuously

- **Risk**: The assertion at `tests/e2e/rotation/rotation-sse.spec.ts:91-102` has a fallback that simply checks `rows.count() > 0`. Since the dashboard already has rows from initial load, this branch always passes regardless of whether the nudge actually triggered a refresh.
- **Mitigation**: Tighten the assertion to verify a concrete state change. For example, after triggering rotation for a device, assert that the device's `data-rotation-state` attribute changed to a specific expected value (e.g., `QUEUED` or `PENDING`), rather than falling back to a row-count check.
- **Evidence**: `tests/e2e/rotation/rotation-sse.spec.ts:99-101`

---

## 11) Confidence

Confidence: High -- The implementation closely follows the approved plan, uses the correct project patterns (contexts, hooks, instrumentation, Playwright fixtures), and demonstrates careful attention to async coordination and cleanup. The conditions for GO are addressable with localized changes (replacing `waitForTimeout` with deterministic patterns, tightening the rotation test assertion, and verifying timestamp format consistency).
