# Device Logs Viewer — Technical Plan

## 0) Research Log & Findings

**Searched areas:**
- `docs/features/device_logs_viewer/change_brief.md` — feature requirements
- `docs/contribute/architecture/application_overview.md` — React 19, TanStack Router/Query patterns
- `docs/contribute/testing/playwright_developer_guide.md` — test patterns, instrumentation requirements
- `src/components/devices/device-editor.tsx` — current device editor implementation (580 lines)
- `src/routes/devices/$deviceId.tsx` — edit device route, passes props to DeviceEditor
- `src/hooks/use-devices.ts` — device hooks pattern, snake_case to camelCase transformation
- `src/hooks/use-rotation.ts` — refetchInterval polling pattern reference
- `src/lib/api/generated/hooks.ts` — `useGetDevicesLogsByDeviceId` hook exists
- `src/lib/api/generated/types.ts` — `DeviceLogsResponseSchema` with `logs[]`, `has_more`, `window_start`, `window_end`
- `src/lib/test/form-instrumentation.ts` — instrumentation patterns
- `tests/e2e/devices/` — existing device test structure, DevicesPage page object

**Key findings:**
1. Generated API hook `useGetDevicesLogsByDeviceId` exists for `GET /api/devices/{device_id}/logs`
2. Response includes `has_more`, `window_start`, `window_end` for cursor-based pagination
3. Device editor already receives `deviceId` and config with `deviceEntityId` from parent route
4. Polling pattern established in `use-rotation.ts` using `refetchInterval`
5. No existing checkbox component; will use native `<input type="checkbox">` with Tailwind styling
6. Instrumentation must use `isTestMode()` guard and emit structured test events

**Conflicts resolved:**
- The generated hook uses standard TanStack Query; we need imperative fetch for cursor-based looping (custom hook required)
- Hiding based on no logs requires an initial fetch to determine state; will handle via loading/empty states

---

## 1) Intent & Scope

**User intent**

Add a real-time log viewer panel to the device edit screen that displays log messages from Elasticsearch, enabling operators to monitor device activity while editing configuration. The viewer should be terminal-styled, poll for new logs automatically, and stay unobtrusive when no logs are available.

**Prompt quotes**

- "Terminal-style log box (bg-gray-900, font-mono, text-gray-200) below the device editor form"
- "Fixed height of approximately 30 lines"
- "Auto-scroll to bottom only when scrollbar is already at bottom"
- "Hide log viewer when device has no entity_id or no logs"
- "Poll every 1 second when live updates enabled"
- "If has_more is true, immediately fetch again until caught up"
- "Silently retry on errors (no toasts or error UI)"
- "Only visible in edit mode (not new/duplicate)"
- "Do not display timestamps on log entries"

**In scope**

- New `useDeviceLogs` hook wrapping cursor-based polling logic
- `DeviceLogsViewer` presentational component with terminal styling
- Checkbox control for toggling live updates (right-aligned, default checked)
- Auto-scroll behavior respecting user scroll position
- Integration into `DeviceEditor` (edit mode only)
- Playwright instrumentation for loading/ready states
- Page object extension and test scenario coverage

**Out of scope**

- Log filtering/search UI (query parameter exists but not exposed in this slice)
- Historical log browsing (only live-forward from current position)
- Log level coloring or message parsing
- Export/download functionality
- Persistence of live-update preference across sessions

**Assumptions / constraints**

- Backend endpoint `GET /api/devices/{device_id}/logs` is available and stable
- Elasticsearch indices are populated for devices with `entity_id`
- Initial call without `start`/`end` returns current cursor (empty logs, `window_start === window_end`)
- Network latency is acceptable for 1-second polling
- Component unmount must cancel in-flight requests to avoid state updates on unmounted component

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Terminal-style log box (bg-gray-900, font-mono, text-gray-200) below the device editor form
- [ ] Fixed height of approximately 30 lines
- [ ] Checkbox above the box (right-aligned) to toggle live updates, default checked
- [ ] Auto-scroll to bottom only when scrollbar is already at bottom
- [ ] Hide log viewer when device has no entity_id or no logs
- [ ] Poll every 1 second when live updates enabled
- [ ] Initial call without start/end to get current cursor position
- [ ] Subsequent polls use start=previous window_end
- [ ] If has_more is true, immediately fetch again until caught up
- [ ] Silently retry on errors (no toasts or error UI)
- [ ] Only visible in edit mode (not new/duplicate)
- [ ] Do not display timestamps on log entries

---

## 2) Affected Areas & File Map

- Area: `src/hooks/use-device-logs.ts` (new file)
- Why: Custom hook encapsulating cursor-based polling, fetch loop for `has_more`, and abort handling
- Evidence: Pattern from `src/hooks/use-rotation.ts:71-86` (refetchInterval), `src/hooks/use-devices.ts:138-157` (single-device query pattern)

- Area: `src/components/devices/device-logs-viewer.tsx` (new file)
- Why: Presentational component for terminal-style log display with auto-scroll and checkbox control
- Evidence: Terminal styling matches `font-mono` usage in `src/components/devices/device-editor.tsx:447` (Device Key display)

- Area: `src/components/devices/device-editor.tsx`
- Why: Integration point; conditionally render `DeviceLogsViewer` below JSON editor in edit mode
- Evidence: `src/components/devices/device-editor.tsx:441-452` (edit-mode sections), `src/components/devices/device-editor.tsx:515-548` (JSON Configuration section placement)

- Area: `src/types/test-events.ts`
- Why: May need `list_loading` scope registration for `devices.logs` instrumentation (existing taxonomy suffices)
- Evidence: `src/types/test-events.ts:133-144` (`ListLoadingTestEvent` with `scope` field)

- Area: `tests/e2e/devices/DevicesPage.ts`
- Why: Add locators for log viewer elements (container, checkbox, log entries)
- Evidence: `tests/e2e/devices/DevicesPage.ts:62-101` (existing editor locators pattern)

- Area: `tests/e2e/devices/devices-logs.spec.ts` (new file)
- Why: Test scenarios for log viewer behavior (visibility, polling, scrolling)
- Evidence: `tests/e2e/devices/devices-crud.spec.ts` (existing device test patterns)

- Area: `tests/api/factories/devices.ts`
- Why: May need helper to create device with specific `entity_id` for log testing (optional, factory already supports `deviceEntityId`)
- Evidence: `tests/api/factories/devices.ts:49-53` (`randomDeviceEntityId` helper)

---

## 3) Data Model / Contracts

- Entity / contract: Device Logs API Response
- Shape:
  ```typescript
  interface DeviceLogsResponse {
    logs: Array<{ message: string; timestamp: string }>;
    hasMore: boolean;
    windowStart: string | null;
    windowEnd: string | null;
  }
  ```
- Mapping: Snake_case `has_more`, `window_start`, `window_end` from API → camelCase in hook
- Evidence: `src/lib/api/generated/types.ts:893-918` (`DeviceLogsResponseSchema.e6f48c9`)

- Entity / contract: Log Entry (UI model)
- Shape:
  ```typescript
  interface LogEntry {
    message: string;
    // timestamp excluded from display per requirements
  }
  ```
- Mapping: Direct from API `logs[].message`; timestamp stored internally for sorting but not rendered
- Evidence: `src/lib/api/generated/types.ts:923-937` (`LogEntrySchema`)

- Entity / contract: Hook State
- Shape:
  ```typescript
  interface UseDeviceLogsState {
    logs: LogEntry[];
    isLoading: boolean;      // true during initial fetch
    hasEntityId: boolean;    // derived from config
    isPolling: boolean;      // current polling status
    startPolling: () => void;
    stopPolling: () => void;
  }
  ```
- Mapping: Internal state management
- Evidence: Pattern from `src/hooks/use-rotation.ts:75-129`

---

## 4) API / Integration Surface

- Surface: `GET /api/devices/{device_id}/logs`
- Inputs: `path.device_id` (number), `query.start` (ISO datetime, optional), `query.end` (ISO datetime, optional)
- Outputs: `{ logs: LogEntry[], has_more: boolean, window_start: string | null, window_end: string | null }`
- Errors: 400 (validation), 404 (device not found), 503 (Elasticsearch unavailable) — all silently swallowed per requirements
- Evidence: `src/lib/api/generated/types.ts:2159-2213` (operation schema)

- Surface: Generated hook `useGetDevicesLogsByDeviceId`
- Inputs: `{ path: { device_id }, query: { start?, end? } }`
- Outputs: Standard TanStack Query result
- Errors: Handled via `onError` callback; no toast/UI surfacing
- Evidence: `src/lib/api/generated/hooks.ts:387-399`

Note: Will use imperative fetch via the generated client rather than the hook directly, to support the `has_more` loop and custom polling interval control.

---

## 5) Algorithms & UI Flows

- Flow: Initial Log Cursor Acquisition
- Steps:
  1. Component mounts in edit mode with valid `deviceId`
  2. Check if device has `deviceEntityId` (from config/initialConfig)
  3. If no `entityId`, skip fetching; viewer remains hidden permanently
  4. Fetch logs without `start`/`end` to get current cursor position
  5. Store `windowEnd` as cursor for subsequent polls
  6. If `logs.length === 0`, viewer remains hidden BUT polling continues in background
  7. If `logs.length > 0`, render viewer immediately
  8. On subsequent polls, if viewer is hidden and logs arrive, transition to visible
- States / transitions: `idle` → `initializing` → `ready` | `hidden-polling`; `hidden-polling` → `ready` (when first logs arrive)
- Hotspots: First fetch determines initial visibility; polling continues even when hidden to catch late-arriving logs
- Evidence: Change brief sections on "Initial call without start/end" and "Hide log viewer when... no logs"
- Note: The "hidden-polling" state ensures users see logs that appear after initial navigation without requiring a page refresh. This is more user-friendly than permanently hiding the viewer.

- Flow: Polling Loop
- Steps:
  1. Wait 1 second since last fetch completion
  2. Fetch with `start=previousWindowEnd`
  3. Append new logs to accumulated log list
  4. Update cursor to new `windowEnd`
  5. If `hasMore === true`, immediately fetch again (no wait)
  6. Repeat until `hasMore === false`, then wait 1 second and poll again
- States / transitions: `polling` → `fetching` → `appending` → `polling`
- Hotspots: Rapid fetches when catching up could cause render thrashing; batch updates
- Evidence: Change brief "If has_more is true, immediately fetch again until caught up"

- Flow: Auto-Scroll Behavior
- Steps:
  1. Before appending new logs, check if scroll position is at bottom
  2. Determine "at bottom" via: `scrollTop + clientHeight >= scrollHeight - threshold`
  3. Append logs to DOM
  4. If was at bottom, scroll to new bottom
  5. If user had scrolled up, preserve position (no auto-scroll)
- States / transitions: `userScrolled` (boolean ref)
- Hotspots: Scroll event listeners need passive flag; threshold handles rounding (use ~10px)
- Evidence: Requirement "Auto-scroll to bottom only when scrollbar is already at bottom"

- Flow: Toggle Live Updates
- Steps:
  1. User unchecks checkbox → `stopPolling()` called
  2. Cancel any pending fetch timeout
  3. User checks checkbox → `startPolling()` called
  4. Resume polling from current cursor position
- States / transitions: `isPolling` boolean
- Hotspots: Must not lose accumulated logs when toggling
- Evidence: Requirement "Checkbox above the box (right-aligned) to toggle live updates"

---

## 6) Derived State & Invariants

- Derived value: `shouldShowViewer`
  - Source: `hasEntityId` (from device config) AND `logs.length > 0` (dynamically evaluated)
  - Writes / cleanup: Controls conditional rendering; no persistence
  - Guards: Initial fetch must complete before evaluating; viewer transitions from hidden to visible when first logs arrive during polling
  - Invariant: Never show viewer if `deviceEntityId` is falsy or empty; always show viewer once `logs.length > 0` (even if it was initially hidden)
  - Evidence: Requirement "Hide log viewer when device has no entity_id or no logs"
  - Note: The invariant allows for dynamic visibility — if device has entity_id but no logs initially, polling continues in background and viewer appears when first logs arrive without requiring page refresh

- Derived value: `isAtBottom`
  - Source: Scroll container position computed on scroll events
  - Writes / cleanup: Determines auto-scroll on new log append
  - Guards: Must use passive scroll listener; debounce not needed (cheap check)
  - Invariant: Must default to `true` on mount so first logs auto-scroll
  - Evidence: Requirement "Auto-scroll to bottom only when scrollbar is already at bottom"

- Derived value: `pollingCursor`
  - Source: `windowEnd` from most recent successful fetch
  - Writes / cleanup: Used as `start` param for next fetch
  - Guards: Must not poll if cursor is null (initial state)
  - Invariant: Cursor only advances forward; never goes backward
  - Evidence: Requirement "Subsequent polls use start=previous window_end"

- Derived value: `logs` array buffer
  - Source: Accumulated log entries from all successful fetches
  - Writes / cleanup: Appended on each fetch; FIFO eviction when buffer exceeds limit
  - Guards: Max buffer size of 1000 entries
  - Invariant: `logs.length <= 1000`; older entries evicted when limit exceeded to prevent memory issues
  - Evidence: Defensive implementation for high-volume log scenarios

---

## 7) State Consistency & Async Coordination

- Source of truth: Local state in `useDeviceLogs` hook (logs array, cursor, polling flag)
- Coordination: No TanStack Query cache involved; imperative fetch keeps state local to prevent stale data from other components
- Async safeguards:
  - AbortController per fetch; abort on unmount or when polling stops
  - Ignore responses from aborted requests
  - Clear timeout on unmount to prevent `setInterval` leaks
- Instrumentation: Emit `list_loading` events with scope `devices.logs` on initial fetch and when catching up (`loading` → `ready`)
- Evidence: `src/lib/test/query-instrumentation.ts` for `useListLoadingInstrumentation` pattern

---

## 8) Errors & Edge Cases

- Failure: Network error during fetch
- Surface: `useDeviceLogs` hook
- Handling: Log to console (debug level), continue polling on next interval; no UI indication
- Guardrails: Retry is automatic via polling loop; exponential backoff not required per spec
- Evidence: Requirement "Silently retry on errors (no toasts or error UI)"

- Failure: Device has no `entity_id`
- Surface: `DeviceLogsViewer` component
- Handling: Hook returns `hasEntityId: false`; component renders nothing
- Guardrails: Check performed before any fetch attempt
- Evidence: Requirement "Hide log viewer when device has no entity_id"

- Failure: Elasticsearch unavailable (503)
- Surface: `useDeviceLogs` hook
- Handling: Same as network error; silent retry
- Guardrails: None special; polling continues
- Evidence: `src/lib/api/generated/types.ts:2204-2212` (503 response schema)

- Failure: Device deleted while viewing logs
- Surface: Parent route redirects on 404; logs viewer unmounts naturally
- Handling: AbortController cancels in-flight; no special handling needed
- Guardrails: Unmount cleanup in useEffect
- Evidence: `src/routes/devices/$deviceId.tsx:34-44` (error handling)

- Failure: Very high log volume (many `has_more` iterations)
- Surface: `useDeviceLogs` hook
- Handling: Batch append logs; limit retained log count to prevent memory issues (e.g., keep last 1000 lines)
- Guardrails: Implement max buffer size with FIFO eviction
- Evidence: Not explicit in requirements; defensive implementation

---

## 9) Observability / Instrumentation

- Signal: `list_loading` with scope `devices.logs`
- Type: Instrumentation event via `emitTestEvent` (direct call, not `useListLoadingInstrumentation`)
- Trigger: Manual emission points in imperative fetch loop
- Emission points:
  1. Emit `{ kind: 'list_loading', scope: 'devices.logs', phase: 'loading' }` when:
     - Initial fetch starts (logs.length === 0 and first fetch initiated)
  2. Emit `{ kind: 'list_loading', scope: 'devices.logs', phase: 'ready', metadata: { deviceId, logCount, isPolling } }` when:
     - Initial fetch completes and `hasMore === false`
     - Component transitions from hidden to visible (first logs arrived)
  3. Do NOT re-emit on subsequent polling cycles to avoid event spam
- Labels / fields: `scope: 'devices.logs'`, `phase: 'loading' | 'ready'`, `metadata: { deviceId, logCount, isPolling }`
- Consumer: Playwright `waitForListLoading(page, 'devices.logs', 'ready')`
- Evidence: `src/lib/test/event-emitter.ts:emitTestEvent` for direct emission pattern
- Note: Since the hook uses imperative fetch with local state rather than TanStack Query, `useListLoadingInstrumentation` cannot be used directly. Manual emission via `emitTestEvent` is required, guarded by `isTestMode()`.

- Signal: `data-testid` attributes
- Type: DOM attributes for Playwright selectors
- Trigger: Component render
- Labels / fields:
  - `devices.logs.viewer` — main container
  - `devices.logs.live-checkbox` — toggle checkbox
  - `devices.logs.container` — scrollable log area (with `data-scroll-at-bottom="true|false"` for scroll state)
  - `devices.logs.entry` — individual log line
- Consumer: Playwright locators in `DevicesPage.ts`
- Evidence: Existing pattern in `tests/e2e/devices/DevicesPage.ts:23-101`

- Signal: `data-scroll-at-bottom` attribute
- Type: DOM data attribute on scroll container
- Trigger: Updated on scroll events and after log appends
- Labels / fields: `"true"` when scroll is at bottom, `"false"` when user has scrolled up
- Consumer: Playwright assertions for auto-scroll behavior tests
- Evidence: Required for deterministic scroll position assertions without brittle DOM measurements

---

## 10) Lifecycle & Background Work

- Hook / effect: `useDeviceLogs` polling effect
- Trigger cadence: 1-second interval when `isPolling === true`
- Responsibilities: Fetch logs, update cursor, append to buffer, manage `has_more` loop
- Cleanup: Clear timeout via `clearTimeout`, abort fetch via `AbortController.abort()`, reset state on unmount
- Evidence: `src/hooks/use-rotation.ts:76-86` (refetchInterval pattern, though we use manual setTimeout for finer control)

- Hook / effect: Scroll position tracking
- Trigger cadence: On `scroll` event (passive listener)
- Responsibilities: Update `isAtBottom` ref
- Cleanup: Remove event listener on unmount
- Evidence: Standard React pattern; no existing reference needed

---

## 11) Security & Permissions

- Concern: Log data exposure
- Touchpoints: `DeviceLogsViewer` component, `/api/devices/{device_id}/logs` endpoint
- Mitigation: Backend enforces authentication; frontend inherits session from existing device edit access. No additional permission check needed beyond existing device access.
- Residual risk: Logs may contain sensitive data (API keys, errors with PII); acceptable as this mirrors existing log access patterns. Operators with device edit access are expected to have log visibility.
- Evidence: Device editor already requires authenticated session; `src/routes/devices/$deviceId.tsx` inherits auth guards

---

## 12) UX / UI Impact

- Entry point: Device edit route `/devices/:deviceId`
- Change: New section below JSON Configuration showing terminal-style log viewer
- User interaction:
  - Logs appear automatically if device has `entity_id` and logs exist
  - Checkbox controls live polling (checked by default)
  - User can scroll up to read history; auto-scroll pauses
  - Scrolling to bottom resumes auto-scroll
- Dependencies: Device must have `deviceEntityId` configured; logs must exist in Elasticsearch
- Evidence: `src/components/devices/device-editor.tsx:515-548` (JSON editor placement)

---

## 13) Deterministic Test Plan

- Surface: Device edit page with log viewer
- Scenarios:
  - Given a device with `entity_id` and existing logs, When I navigate to edit, Then the log viewer appears with terminal styling and logs are visible
  - Given a device without `entity_id`, When I navigate to edit, Then no log viewer is shown
  - Given a device with `entity_id` but no logs, When I navigate to edit, Then no log viewer is shown initially (but polling continues in background)
  - Given the log viewer is visible with live updates enabled, When new logs arrive, Then they appear at the bottom and view auto-scrolls
  - Given I have scrolled up in the log viewer, When new logs arrive, Then my scroll position is preserved (no auto-scroll) and `data-scroll-at-bottom="false"`
  - Given the log viewer is visible, When I uncheck live updates, Then polling stops (verifiable via `list_loading` metadata `isPolling: false`)
  - Given I unchecked live updates, When I check it again, Then polling resumes from current position
- Instrumentation / hooks:
  - `waitForListLoading(page, 'devices.logs', 'ready')` — wait for initial load complete
  - `data-testid="devices.logs.viewer"` — assert visibility
  - `data-testid="devices.logs.live-checkbox"` — interact with toggle
  - `data-testid="devices.logs.container"` with `data-scroll-at-bottom` — assert scroll position
  - `data-testid="devices.logs.entry"` — count visible log entries
- Gaps:
  - Testing actual log content requires backend test helper to seed Elasticsearch logs
  - **Prerequisite**: Backend must provide `/api/testing/devices/{device_id}/logs` endpoint to seed deterministic log entries
  - **Fallback if unavailable**: Initial slice tests only visibility states (no entity_id = hidden, with entity_id = either hidden or visible depending on existing logs) and checkbox toggle behavior. Log content and auto-scroll tests deferred until seeding endpoint available.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts` patterns

**Backend Test Helper Requirement**: For deterministic testing, backend needs:
- `POST /api/testing/devices/{device_id}/logs` — Seed log entries with specified messages
- This enables tests to:
  1. Create device with entity_id
  2. Seed specific log messages
  3. Navigate to edit page
  4. Assert log content matches seeded messages
  5. Seed additional logs while viewing
  6. Assert new logs appear and auto-scroll works

If backend endpoint is unavailable, add it as a prerequisite in Slice 0 before implementing Slice 5 (Tests).

---

## 14) Implementation Slices

- Slice 0: Backend Test Helper (prerequisite, may already exist)
- Goal: Ensure `/api/testing/devices/{device_id}/logs` endpoint exists for seeding deterministic test logs
- Touches: Backend repository (out of frontend scope)
- Dependencies: None; blocks Slice 5 if unavailable
- Note: Confirm availability before starting Slice 5. If unavailable, request backend team to add it or adjust Slice 5 scope.

- Slice 1: Hook Implementation
- Goal: `useDeviceLogs` hook with cursor-based polling, abort handling, state management, and visibility change pause
- Touches: `src/hooks/use-device-logs.ts` (new)
- Dependencies: Generated API client; no feature flags
- Includes: `document.visibilityState` handling to pause polling when tab is backgrounded

- Slice 2: UI Component
- Goal: `DeviceLogsViewer` component with terminal styling, checkbox, auto-scroll, and `data-scroll-at-bottom` attribute
- Touches: `src/components/devices/device-logs-viewer.tsx` (new)
- Dependencies: Hook from Slice 1

- Slice 3: Integration
- Goal: Wire `DeviceLogsViewer` into `DeviceEditor` for edit mode
- Touches: `src/components/devices/device-editor.tsx`
- Dependencies: Component from Slice 2

- Slice 4: Instrumentation
- Goal: Emit `list_loading` events via `emitTestEvent` for Playwright, add `data-testid` attributes
- Touches: `src/hooks/use-device-logs.ts`, `src/components/devices/device-logs-viewer.tsx`
- Dependencies: Slices 1-2 complete
- Note: Uses direct `emitTestEvent` calls (not `useListLoadingInstrumentation`) due to imperative fetch pattern

- Slice 5: Tests
- Goal: Page object extension and spec file for log viewer behavior
- Touches: `tests/e2e/devices/DevicesPage.ts`, `tests/e2e/devices/devices-logs.spec.ts` (new)
- Dependencies: All previous slices; Slice 0 must be confirmed
- Fallback: If Slice 0 unavailable, limit tests to visibility states and checkbox toggle (no log content assertions)

---

## 15) Risks & Open Questions

- Risk: High log volume causes UI jank
- Impact: Poor user experience; potential memory issues
- Mitigation: Implement max buffer (1000 lines) with FIFO eviction; batch DOM updates

- Risk: Polling continues when tab is backgrounded
- Impact: Unnecessary network requests; battery drain on mobile
- Mitigation: Use `document.visibilityState` to pause polling when hidden; resume on focus

- Risk: Backend log seeding for tests unavailable
- Impact: Cannot write deterministic tests for log content or auto-scroll behavior
- Mitigation: Treat `/api/testing/devices/{device_id}/logs` as Slice 0 prerequisite; confirm with backend team before starting Slice 5. Fallback: limit test scope to visibility and checkbox toggle only.

- Risk: Imperative fetch loop diverges from `useListLoadingInstrumentation` pattern
- Impact: Instrumentation may behave inconsistently with other list-loading components; maintenance burden
- Mitigation: Document emission points clearly in Section 9; consider extracting reusable helper if pattern is needed elsewhere

- Question: Should the log viewer have a loading spinner during initial fetch?
- Why it matters: Without visual feedback, users may not realize logs are loading
- Owner / follow-up: Resolved autonomously — show subtle "Loading logs..." text that disappears when ready or when no logs found

- Question: Maximum number of logs to retain in buffer?
- Why it matters: Affects memory usage and scroll performance
- Owner / follow-up: Resolved autonomously — 1000 lines is reasonable for terminal-style viewer; older entries evicted FIFO

- Question: Should polling continue when viewer is hidden (no logs yet)?
- Why it matters: If polling stops when no logs, users must refresh to see logs that arrive later
- Owner / follow-up: Resolved autonomously — polling continues in "hidden-polling" state; viewer transitions to visible when first logs arrive. This provides better UX at minimal resource cost (1 request/second).

---

## 16) Confidence

Confidence: High — Requirements are well-defined, API endpoint exists with clear contract, similar patterns (polling, instrumentation) already established in codebase. The plan now addresses:
- Instrumentation integration via direct `emitTestEvent` calls with documented emission points
- Visibility state machine clarified (hidden-polling state for late-arriving logs)
- Scroll position instrumentation via `data-scroll-at-bottom` attribute
- Backend test helper as explicit prerequisite (Slice 0) with fallback scope

Main remaining uncertainty is backend test helper availability, which is now explicitly tracked as a prerequisite rather than a deferred concern.
