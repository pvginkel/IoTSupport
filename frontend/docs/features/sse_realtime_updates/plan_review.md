# Plan Review: SSE Real-Time Updates

## 1) Summary & Decision

**Readiness**

The plan is thorough, well-researched, and closely aligned with existing codebase patterns. It correctly identifies the provider hierarchy, existing instrumentation taxonomy, generated API hooks, and Playwright infrastructure. The research log is exceptionally detailed, accurately quoting line ranges and file paths. The plan covers all 16 sections required by the feature plan template with precise evidence. An initial review identified three issues (proxy path prefix discrepancy, missing `SET` reducer action, and `queryClient` access gap in the rotation hook). All three have been resolved in the updated plan: the proxy prefix now consistently uses `/sse` matching `docs/contribute/environment.md:28`, the reducer `SET` action is explicitly documented as a new addition, and `useQueryClient()` and `useSseContext()` are called out as new dependencies for `useRotationDashboard`.

**Decision**

`GO` -- All identified issues have been resolved in the plan. The plan is implementation-ready.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/commands/plan_feature.md` -- Pass -- The plan includes all 16 required sections (0 through 16) with the correct headings and uses the prescribed template structures throughout.
- `docs/product_brief.md` -- Pass -- `plan.md:35-61` -- The plan scope (device log streaming and rotation dashboard) aligns with the product brief's device management domain. No contradictions with the product brief's stated features.
- `docs/contribute/architecture/application_overview.md` -- Pass -- `plan.md:100-108` -- The plan follows the documented context/provider pattern (`createContext` + `useContext` + Provider), hooks in `src/hooks/`, and generated API client usage.
- `docs/contribute/testing/playwright_developer_guide.md` -- Pass -- `plan.md:481-506` -- The test plan uses API-first data setup (testing endpoints for injection), deterministic waits (test-event signals), and real backend only (no route mocking). The plan explicitly references `waitTestEvent` helpers and the `ListLoadingTestEvent` pattern.
- `docs/contribute/testing/ci_and_execution.md` -- Pass -- `plan.md:136-144` -- The plan correctly identifies the need to extend `servers.ts` to start the SSE Gateway between backend and frontend, matching the documented startup sequence at `ci_and_execution.md:42-44`.
- `docs/contribute/environment.md` -- Pass -- `plan.md:74,113-114` -- The plan now correctly uses `/sse` as the proxy prefix, matching `environment.md:10,28`. The `/sse` prefix is stripped before forwarding to the gateway, and the proxy is defined separately from the `/api` rule.

**Fit with codebase**

- `src/contexts/toast-context.tsx` -- `plan.md:100-103` -- The `SseContext` follows the established `createContext` / `useContext` / Provider pattern. Uses `ulid` for ID generation consistent with `toast-context.tsx:3,36`. Good alignment.
- `src/routes/__root.tsx` -- `plan.md:106-108` -- Placement of `SseProvider` inside `AuthGate` is correct; the provider hierarchy at `__root.tsx:28-39` shows `AuthGate` wrapping `AppShellFrame`, and SSE should only connect when authenticated.
- `src/hooks/use-device-logs.ts` -- `plan.md:118-121` -- The plan correctly identifies the polling infrastructure to remove (`POLL_INTERVAL_MS`, cursor tracking, visibility-change handler) and the reducer pattern to extend. The plan now explicitly documents the need to add a `SET` action to the reducer at `plan.md:119,286`.
- `src/hooks/use-rotation.ts` -- `plan.md:130-132` -- The plan correctly identifies `refetchInterval` at `use-rotation.ts:78-87` as the target for replacement. The plan now explicitly notes that `useQueryClient()` and `useSseContext()` must be added to `useRotationDashboard`.
- `tests/support/process/servers.ts` -- `plan.md:136-138` -- The plan now explicitly calls out that `ServiceLabel` must be extended to include `'gateway'` and `serviceShouldLogLifecycle` must handle the gateway case using `PLAYWRIGHT_GATEWAY_LOG_STREAM`.
- `tests/support/fixtures.ts` -- `plan.md:142-144` -- The fixture file at `fixtures.ts:215-382` manages backend and frontend lifecycle. Adding gateway startup between them follows the documented pattern. The plan correctly identifies the insertion point.

---

## 3) Open Questions & Ambiguities

- Question: Does the plan intend to add `SSE_GATEWAY_URL` as an environment variable to the `startFrontend` call in `servers.ts`, or does the frontend testing-server script handle this differently?
- Why it matters: At `servers.ts:95-99`, the frontend start passes `BACKEND_URL` and `VITE_TEST_MODE` but not `SSE_GATEWAY_URL`. The Vite proxy for `/sse` needs this variable.
- Needed answer: The plan states at `plan.md:137` "Pass `SSE_GATEWAY_URL` to the frontend `startService` env" and the implementation slice at `plan.md:514` confirms this. The question is resolved.

No unresolved open questions remain.

---

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Device logs appearing in real time via SSE
- Scenarios:
  - Given an authenticated user and a device with `deviceEntityId`, When the user navigates to the device logs tab, Then the log viewer becomes visible and `ListLoadingTestEvent` (scope `devices.logs`, phase `ready`) is emitted (`tests/e2e/devices/devices-logs-sse.spec.ts`)
  - Given the log viewer is ready and the backend confirms an active subscription, When the test injects log entries via `POST /api/testing/devices/logs/inject`, Then the injected log messages appear in the viewer DOM (`tests/e2e/devices/devices-logs-sse.spec.ts`)
  - Given multiple log entries are injected, When the viewer renders them, Then entries appear in chronological order (`tests/e2e/devices/devices-logs-sse.spec.ts`)
- Instrumentation: `ListLoadingTestEvent` (scope `devices.logs`, phase `ready`), `SseTestEvent` (phase `open`), `[data-testid="devices.logs.entry"]` locators
- Backend hooks: `POST /api/testing/devices/logs/inject`, `GET /api/testing/devices/logs/subscriptions`
- Gaps: No test for SSE reconnection or connection loss. Deferred with justification (gateway shutdown simulation is fragile). Acceptable.
- Evidence: `plan.md:483-493`

- Behavior: Rotation dashboard refreshing on SSE nudge
- Scenarios:
  - Given an authenticated user with devices in the rotation dashboard, When the user navigates to the rotation dashboard, Then the dashboard renders with device panels and `ListLoadingTestEvent` (scope `rotation.dashboard`, phase `ready`) is emitted (`tests/e2e/rotation/rotation-sse.spec.ts`)
  - Given the dashboard is loaded, When the test mutates rotation state and sends `POST /api/testing/rotation/nudge`, Then the dashboard content updates without manual refresh (`tests/e2e/rotation/rotation-sse.spec.ts`)
- Instrumentation: `ListLoadingTestEvent` (scope `rotation.dashboard`, phase `ready`), `[data-testid="rotation.dashboard.row"]` with `data-rotation-state` attributes
- Backend hooks: `POST /api/testing/rotation/nudge`, rotation trigger APIs
- Gaps: No test for rapid nudge deduplication. Deferred with justification (TanStack Query handles this). Acceptable.
- Evidence: `plan.md:497-506`

- Behavior: SSE connection lifecycle (new SseProvider)
- Scenarios: Not explicitly tested as a standalone spec. SSE connection is implicitly tested by both device logs and rotation specs that rely on the connection being open.
- Instrumentation: `SseTestEvent` (phases `open`, `message`, `error`, `close`)
- Backend hooks: SSE Gateway `GET /readyz` health check
- Gaps: No dedicated spec for SSE connection lifecycle instrumentation. This is minor since both consumer specs depend on it working. Consider adding a brief assertion in at least one spec that the `SseTestEvent` with phase `open` was emitted before proceeding to consumer tests.
- Evidence: `plan.md:264-274`, `plan.md:489`

---

## 5) Adversarial Sweep

**Resolved -- Vite proxy path prefix now matches environment documentation**

**Evidence:** `plan.md:53,58,74,113-114` now consistently use `/sse` as the proxy prefix, matching `docs/contribute/environment.md:10,28`.

**Status:** The plan has been updated. The EventSource URL is `/sse/stream?request_id=<id>`, the Vite proxy matches `/sse/**` separate from `/api`, and the prefix is stripped. All references are consistent.

**Confidence:** High

---

**Resolved -- Reducer `SET` action now explicitly documented**

**Evidence:** `plan.md:119` -- "The log reducer must be extended with a new `SET` action (`{ type: 'SET'; logs: LogEntry[] }`) that atomically replaces the entire buffer". `plan.md:286` -- "Note: the `SET` action must be added to the reducer (the existing reducer only defines `RESET` and `APPEND`). `SET` replaces the entire buffer with the provided logs, capped at `MAX_BUFFER_SIZE`."

**Status:** The plan now clearly documents this as a new action to add, with rationale for why it is preferred over `RESET` + `APPEND`.

**Confidence:** High

---

**Resolved -- Rotation hook `queryClient` and `useSseContext` access documented**

**Evidence:** `plan.md:131` -- "The hook must add `useQueryClient()` (currently only used by `useTriggerRotation` and `useRotateDevice`, not by `useRotationDashboard`) and import `useSseContext` to register the SSE event listener in an effect." `plan.md:301-302` -- Algorithm steps now include these dependencies.

**Status:** The plan explicitly calls out both new hook dependencies.

**Confidence:** High

---

**Minor -- Consider adding `SseTestEvent` open assertion to consumer specs**

**Evidence:** `plan.md:489` describes waiting for `ListLoadingTestEvent` but does not explicitly wait for the SSE connection to be open first. Both consumer specs (device logs and rotation) implicitly depend on the SSE connection being open, but do not assert this.

**Why it matters:** If the SSE connection fails silently, the consumer specs would time out waiting for events rather than failing with a clear SSE connection error. Adding a `waitTestEvent(page, 'sse', evt => evt.phase === 'open')` assertion at the start of each spec would provide a clearer failure message.

**Fix suggestion:** Add a note to the test plan section recommending that each SSE consumer spec begins by waiting for `SseTestEvent` with phase `open` before proceeding to feature-specific assertions. This is not blocking but improves test diagnostics.

**Confidence:** Medium

---

**Minor -- `ServiceLabel` type and log lifecycle updated in plan**

**Evidence:** `plan.md:137` now explicitly documents: "The `ServiceLabel` type at line 103 must be extended from `'backend' | 'frontend'` to `'backend' | 'frontend' | 'gateway'`, and `serviceShouldLogLifecycle` at lines 295-303 must handle `'gateway'` using `process.env.PLAYWRIGHT_GATEWAY_LOG_STREAM`."

**Status:** Resolved in the plan.

**Confidence:** High

---

## 6) Derived-Value & State Invariants (table)

- Derived value: `connectionState`
  - Source dataset: `EventSource.readyState` mapped to `'connecting' | 'open' | 'closed'`
  - Write / cleanup triggered: `SseTestEvent` emissions on state change; consumers (device logs hook) gate subscription attempts on `connectionState === 'open'` or presence of `requestId`
  - Guards: `SseProvider` only mounts inside `AuthGate` (user authenticated); `EventSource` is closed in cleanup effect
  - Invariant: `requestId` remains stable for the lifetime of the `SseProvider` instance. If `requestId` changes, all active subscriptions become orphaned because the backend binds subscriptions to the `request_id`.
  - Evidence: `plan.md:315-320`

- Derived value: `isStreaming` flag in device logs hook
  - Source dataset: Flips from `false` to `true` after initial history fetch completes and queued events are flushed
  - Write / cleanup triggered: When `true`, incoming SSE events bypass the queue and go directly to the log buffer. Reset to `false` on unmount or device change.
  - Guards: Must not flip to `true` until the fetch response has been processed and the cutoff timestamp recorded. The queue captures all events during the subscribe-to-streaming gap.
  - Invariant: No SSE event is lost between subscribe and streaming start. The queue is the bridge. If `isStreaming` flips prematurely (before cutoff timestamp is set), events could be duplicated or lost.
  - Evidence: `plan.md:324-329`

- Derived value: Log buffer (5000-entry FIFO)
  - Source dataset: Initial fetch (up to 1000 entries) + SSE events appended over time
  - Write / cleanup triggered: `SET` action replaces buffer with initial load; `APPEND` action adds new entries with FIFO eviction at 5000; `RESET` clears on device change
  - Guards: FIFO eviction preserves most recent entries. The reducer handles concurrent `APPEND` calls atomically. The `SET` action is documented as a new addition to the reducer.
  - Invariant: `logs.length <= 5000` at all times. Initial load never exceeds 1000 entries. Buffer must never contain duplicates from the queue-flush step (deduplication by `@timestamp`).
  - Evidence: `plan.md:333-338`, `src/hooks/use-device-logs.ts:46-61`

---

## 7) Risks & Mitigations (top 3)

- Risk: SSE Gateway repository not available in the sandbox/CI environment. The plan acknowledges this at `plan.md:542-544` but the mitigation ("check and skip with error") would effectively disable all SSE-related Playwright tests, which are the primary verification for this feature.
- Mitigation: Verify SSE Gateway availability in the sandbox before implementation begins. If the gateway repo is not available, the infrastructure slice (Slice 1) cannot be validated. This is a blocking dependency for Slices 2-4.
- Evidence: `plan.md:542-544`, `docs/contribute/testing/ci_and_execution.md:43-44,88`

- Risk: Event ordering race between subscribe, SSE events, and initial fetch may produce duplicates or gaps. The plan's deduplication strategy relies on `@timestamp` comparison, but the SSE payload uses `@timestamp` while the REST API uses `timestamp` (different field names, potentially different precision).
- Mitigation: The plan notes this field name difference at `plan.md:182` ("Note the `@timestamp` field name from SSE differs from the `timestamp` field in the REST API response"). Ensure the timestamp mapping normalizes both sources to the same format and precision before comparison. Add explicit documentation of the normalization in the hook implementation.
- Evidence: `plan.md:182,289,548-550`

- Risk: Removing the "Live Updates" checkbox removes user control over log streaming. The plan proposes repurposing it as "Auto-scroll" or "Pause/Resume display" but the final UX decision is deferred.
- Mitigation: The plan at `plan.md:560-562` proposes keeping the checkbox with changed semantics. The implementer should finalize the UX before coding the viewer component to avoid rework.
- Evidence: `plan.md:124-126,560-562`

---

## 8) Confidence

Confidence: High -- All major review findings have been resolved in the updated plan. The proxy prefix is consistent with environment documentation, the reducer extension is explicitly documented, and hook dependency changes are called out. The remaining risks (gateway availability, timestamp normalization, UX decision on the checkbox) are implementation-level concerns that do not block the plan's design integrity.
