# Plan: Device Logs Backfill & Download

## 0) Research Log & Findings

**Searched areas:**
- `src/hooks/use-device-logs.ts` -- reducer-based log state management, SSE streaming lifecycle, history fetch via `GET /api/devices/{id}/logs`, `MAX_BUFFER_SIZE` constant (currently 5,000).
- `src/components/devices/device-logs-viewer.tsx` -- terminal-style viewer with auto-scroll, scroll tracking (`wasAtBottomRef`, `isAutoScrollingRef`), header with streaming status indicator.
- `src/components/devices/device-logs-tab.tsx` -- tab wrapper that passes `device.id` and `device.deviceEntityId` to the viewer; `device` is the full `Device` type with `deviceName`.
- `src/components/primitives/dialog.tsx` -- Radix-based `Dialog`, `DialogInnerContent`, `DialogHeader`, `DialogTitle`, `DialogDescription`, `DialogFooter` primitives used project-wide.
- `src/components/devices/provision-device-modal.tsx` -- reference for dialog composition pattern (Dialog + state machine + lucide icons).
- `tests/e2e/devices/DevicesPage.ts` -- page object already has `scrollLogsToTop()`, `scrollLogsToBottom()`, `logsEntries`, `logsContainer` locators.
- `tests/e2e/devices/devices-logs-sse.spec.ts` -- existing SSE streaming specs with log injection via `/api/testing/devices/logs/inject`.
- `docs/contribute/testing/playwright_developer_guide.md` -- deterministic waits, no route mocks, factory-first data setup.

**Key findings:**
- The `useDeviceLogs` hook already fetches initial history and has `SET` / `APPEND` reducer actions. A new `PREPEND` action is needed for backfill.
- The viewer tracks `isAtBottom` but not `isAtTop`; scroll-to-top detection needs to be added.
- The `DeviceLogsApiResponse` already includes `has_more` and `window_start` / `window_end` fields, providing everything needed for backward pagination.
- The viewer component receives `deviceId` and `deviceEntityId` but not `deviceName`; the download feature needs the device name for the filename, so the prop interface must expand (or the parent `DeviceLogsTab` passes it down).
- The `SCROLL_THRESHOLD_PX` constant (10px) can be reused for top-of-scroll detection.

---

## 1) Intent & Scope

**User intent**

Add two enhancements to the device log viewer: (1) infinite-scroll backfill that loads older log entries when the user scrolls to the top, and (2) a download button that fetches a user-selected number of log lines and saves them as a `.log` file.

**Prompt quotes**

- "Scrolling to the top of the log viewer triggers automatic backfill of older log entries (infinite scroll pattern, no button)"
- "Scroll position is preserved when older entries are prepended"
- "No loading indicator is shown during backfill"
- "Buffer limit is increased from 5,000 to 10,000; stop loading history at this limit"
- "A download button (Download icon from lucide-react) is added next to the streaming status indicator"
- "Clicking the download button opens a dialog with line-count options: 100, 500, 1,000, 5,000, 10,000"
- "Download fetches the requested number of lines via sequential paginated API calls (1,000 per request, backward from end)"
- "Downloaded file contains raw log messages only (no timestamps)"
- "Filename follows pattern: device-{name}-logs-{timestamp}.log"

**In scope**

- Scroll-to-top detection and automatic backward pagination in `useDeviceLogs`
- `PREPEND` reducer action with scroll-position preservation in the viewer
- Increase `MAX_BUFFER_SIZE` from 5,000 to 10,000
- Download button in viewer header, download dialog with line-count selection
- Client-side paginated fetch, file construction, and browser download trigger
- `data-testid` attributes and instrumentation for new UI elements
- Playwright specs for backfill and download flows
- Page object extensions in `DevicesPage.ts`

**Out of scope**

- Backend API changes for the feature itself (the existing `GET /api/devices/{id}/logs?end=<ISO>` endpoint is sufficient)
- Server-side download endpoint
- Filtering or search within logs
- Changing the SSE streaming mechanism

**Backend testing prerequisite (cross-repo)**

- A new `POST /api/testing/devices/logs/seed` endpoint is required to write historical log entries directly to Elasticsearch for deterministic Playwright testing. This does not change the production API surface but is required before Slice 4 (Playwright specs) can proceed.

**Assumptions / constraints**

- The backend `GET /api/devices/{id}/logs?end=<ISO>` returns up to 1,000 entries backward from `end`, with `has_more`, `window_start`, and `window_end` fields. Pagination is achieved by setting `end` to `window_start` of the previous response.
- The `has_more` field accurately reflects whether additional older entries exist.
- Device name is available from the `Device` model passed to `DeviceLogsTab`.

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Scrolling to the top of the log viewer triggers automatic backfill of older log entries (infinite scroll pattern, no button)
- [ ] Scroll position is preserved when older entries are prepended (user stays where they were reading)
- [ ] No loading indicator is shown during backfill
- [ ] Buffer limit is increased from 5,000 to 10,000; stop loading history at this limit
- [ ] A download button (Download icon from lucide-react) is added next to the streaming status indicator in the log viewer header
- [ ] Clicking the download button opens a dialog with line-count options: 100, 500, 1,000, 5,000, 10,000
- [ ] The "end" of the download is wall-clock "now"
- [ ] Download fetches the requested number of lines via sequential paginated API calls (1,000 per request, backward from end)
- [ ] If fewer lines exist than requested, the user gets whatever is available
- [ ] Downloaded file contains raw log messages only (no timestamps)
- [ ] File format is plain text (.log extension), one message per line
- [ ] Filename follows pattern: device-{name}-logs-{timestamp}.log
- [ ] Download is constructed client-side from fetched log data

---

## 2) Affected Areas & File Map

- Area: `src/hooks/use-device-logs.ts`
- Why: Add `PREPEND` reducer action, expose `fetchOlderLogs` callback, increase `MAX_BUFFER_SIZE` to 10,000, track `hasMore` and `oldestTimestamp` state.
- Evidence: `src/hooks/use-device-logs.ts:46` -- `const MAX_BUFFER_SIZE = 5000`; `src/hooks/use-device-logs.ts:58-64` -- `LogsAction` union type; `src/hooks/use-device-logs.ts:72-99` -- `logsReducer` function.

- Area: `src/components/devices/device-logs-viewer.tsx`
- Why: Add scroll-to-top detection, call `fetchOlderLogs` on scroll to top, preserve scroll position after prepend, add download button to header, render download dialog.
- Evidence: `src/components/devices/device-logs-viewer.tsx:62-67` -- `handleScroll` callback; `src/components/devices/device-logs-viewer.tsx:94-112` -- header with streaming status indicator.

- Area: `src/components/devices/device-logs-tab.tsx`
- Why: Pass `deviceName` to `DeviceLogsViewer` so the download filename can include it.
- Evidence: `src/components/devices/device-logs-tab.tsx:30-34` -- `<DeviceLogsViewer deviceId={device.id} deviceEntityId={device.deviceEntityId} fullHeight />`.

- Area: `src/components/devices/device-logs-download-dialog.tsx` (new file)
- Why: Encapsulate the download dialog with line-count selection, progress state, and file generation logic.
- Evidence: Pattern from `src/components/devices/provision-device-modal.tsx:1-360` -- dialog composition with state machine.

- Area: `tests/e2e/devices/DevicesPage.ts`
- Why: Add locators for download button, download dialog, and line-count options.
- Evidence: `tests/e2e/devices/DevicesPage.ts:203-218` -- existing logs viewer locators.

- Area: `tests/e2e/devices/devices-logs.spec.ts` (extend)
- Why: Add backfill and download scenarios.
- Evidence: `tests/e2e/devices/devices-logs.spec.ts:1-92` -- existing log viewer visibility specs.

---

## 3) Data Model / Contracts

- Entity / contract: `LogsState` (reducer state in `use-device-logs.ts`)
- Shape: Add `hasMore: boolean`, `oldestTimestamp: string | null` fields to track backward pagination cursor and availability.
- Mapping: `has_more` from API response maps to `hasMore`; `window_start` maps to `oldestTimestamp`.
- Evidence: `src/hooks/use-device-logs.ts:52-56` -- current `LogsState` interface.

- Entity / contract: `LogsAction` union (reducer actions)
- Shape: Add `| { type: 'PREPEND'; logs: LogEntry[]; hasMore: boolean; oldestTimestamp: string | null }` and update `SET` action to also carry `hasMore` and `oldestTimestamp`.
- Mapping: Direct 1:1 from API response fields.
- Evidence: `src/hooks/use-device-logs.ts:58-65` -- current action union.

- Entity / contract: `UseDeviceLogsResult` (hook return type)
- Shape: Add `fetchOlderLogs: () => Promise<void>`, `hasMore: boolean`, `isFetchingOlder: boolean` to the return type.
- Mapping: N/A -- new fields.
- Evidence: `src/hooks/use-device-logs.ts:44` -- current `UseDeviceLogsResult` type alias.

- Entity / contract: `DeviceLogsApiResponse` (API response)
- Shape: Already contains `logs`, `has_more`, `window_start`, `window_end`. No changes needed.
- Mapping: `has_more` -> `hasMore`, `window_start` -> `oldestTimestamp`.
- Evidence: `src/hooks/use-device-logs.ts:14-19`.

---

## 4) API / Integration Surface

- Surface: `GET /api/devices/{device_id}/logs?end=<ISO>`
- Inputs: `device_id` (path), `end` (query, ISO 8601 timestamp -- set to `oldestTimestamp` for backfill, or `new Date().toISOString()` for download)
- Outputs: `{ logs: Array<{message, timestamp}>, has_more: boolean, window_start: string | null, window_end: string | null }` -- up to 1,000 entries per call
- Errors: 404 (device not found), 500 (Elasticsearch unavailable) -- both handled by existing error path (console.debug, return null)
- Evidence: `src/hooks/use-device-logs.ts:223-253` -- existing `fetchHistory` function.

- Surface: Download flow (client-side, no new endpoint)
- Inputs: `deviceId`, line count (100/500/1,000/5,000/10,000), wall-clock "now" as initial `end`
- Outputs: Sequential calls to the logs endpoint, collecting up to `lineCount` entries; stops when `has_more` is false or target count reached
- Errors: Individual page fetch failure -- stop early, download whatever was collected
- Evidence: N/A -- new flow, modeled on existing `fetchHistory` pattern.

---

## 5) Algorithms & UI Flows

- Flow: Infinite scroll backfill (scroll to top)
- Steps:
  1. User scrolls up; `handleScroll` detects `scrollTop <= SCROLL_THRESHOLD_PX`.
  2. Guard: skip if `isFetchingOlder` is true, `hasMore` is false, or buffer has reached `MAX_BUFFER_SIZE` (10,000).
  3. Record `scrollHeight` before fetch (for position restoration).
  4. Call `fetchOlderLogs()` which fetches `GET /api/devices/{id}/logs?end={oldestTimestamp}`.
  5. On response, guard: if `state.logs.length + newLogs.length > MAX_BUFFER_SIZE`, skip the dispatch and set `hasMore` to false, preserving the live streaming tail. Otherwise dispatch `PREPEND` action with new logs.
  6. After React renders the prepended entries, restore scroll position: set `isAutoScrollingRef.current = true`, then assign `container.scrollTop += container.scrollHeight - previousScrollHeightRef.current`, then clear via `requestAnimationFrame(() => { isAutoScrollingRef.current = false })` to mirror the existing auto-scroll pattern at `device-logs-viewer.tsx:75-83`.
  7. Update `hasMore` and `oldestTimestamp` from response.
- States / transitions: `idle` -> `fetching` (isFetchingOlder=true) -> `idle` (isFetchingOlder=false). No visible loading indicator.
- Hotspots: The viewer stores `previousScrollHeightRef.current = container.scrollHeight` immediately before calling `fetchOlderLogs()`. The `useLayoutEffect`, keyed on a `prependCounter` value returned by the hook (incremented on each PREPEND dispatch), reads `previousScrollHeightRef.current` and adjusts `scrollTop`. The `isAutoScrollingRef` guard must be set to `true` before the `scrollTop` assignment and cleared via `requestAnimationFrame` to suppress scroll events during position restoration and prevent re-triggering backfill.
- Evidence: `src/components/devices/device-logs-viewer.tsx:62-67` -- handleScroll; `src/hooks/use-device-logs.ts:72-99` -- logsReducer.

- Flow: Download with line-count dialog
- Steps:
  1. User clicks Download icon button in viewer header.
  2. Dialog opens with line-count radio/button options: 100, 500, 1,000, 5,000, 10,000.
  3. User selects a count and clicks "Download".
  4. Dialog shows a progress indicator (e.g., "Fetching logs... 2,000 / 5,000").
  5. System sets `end = new Date().toISOString()` and loops: fetch 1,000 entries per call, advancing `end` to `window_start` of each response.
  6. Loop terminates when collected entries >= requested count, or `has_more` is false.
  7. Trim to exact requested count (take the last N entries if over-fetched).
  8. Build plain text: one `message` per line (no timestamps).
  9. Create Blob, generate `device-{name}-logs-{timestamp}.log` filename, trigger download via temporary anchor element.
  10. Close dialog on completion.
- States / transitions: `idle` -> `selecting` (dialog open) -> `fetching` (progress shown) -> `complete` (auto-close) or `error` (show message with retry).
- Hotspots: Sequential fetch loop must be abortable if user closes dialog mid-download.
- Evidence: `src/hooks/use-device-logs.ts:223-253` -- fetchHistory pattern to replicate.

---

## 6) Derived State & Invariants

- Derived value: `canFetchOlder`
  - Source: `hasMore` (from last API response), `isFetchingOlder` (local ref/state), `logs.length` vs `MAX_BUFFER_SIZE`.
  - Writes / cleanup: Guards the backfill fetch; no cache mutation.
  - Guards: Must be false when any of: `!hasMore`, `isFetchingOlder`, `logs.length >= MAX_BUFFER_SIZE`.
  - Invariant: A backfill fetch must never fire while another is in-flight; the buffer must never exceed 10,000 entries.
  - Evidence: `src/hooks/use-device-logs.ts:46` (MAX_BUFFER_SIZE), `src/hooks/use-device-logs.ts:87-91` (APPEND cap logic).

- Derived value: `oldestTimestamp`
  - Source: Initially set from the first history fetch response's earliest entry timestamp (or `window_start`). Updated after each backfill fetch.
  - Writes / cleanup: Used as the `end` parameter for the next backfill request.
  - Guards: Must be non-null before a backfill fetch can proceed; reset on device change (RESET action).
  - Invariant: Always reflects the timestamp of the oldest loaded entry; must advance backward monotonically.
  - Evidence: `src/hooks/use-device-logs.ts:280-286` -- initial history sets cutoffTimestamp.

- Derived value: `isAtTop` (viewer scroll state)
  - Source: `scrollContainerRef.current.scrollTop <= SCROLL_THRESHOLD_PX`.
  - Writes / cleanup: Triggers `fetchOlderLogs` call when conditions are met.
  - Guards: Gated by `canFetchOlder`.
  - Invariant: Must not trigger during programmatic scroll position restoration.
  - Evidence: `src/components/devices/device-logs-viewer.tsx:50-56` -- checkIsAtBottom pattern (mirror for top).

- Derived value: `downloadFilename`
  - Source: `deviceName` prop and current wall-clock time.
  - Writes / cleanup: Used once at file construction time.
  - Guards: Sanitize device name for filesystem safety (replace non-alphanumeric with hyphens).
  - Invariant: Must match pattern `device-{name}-logs-{timestamp}.log`.
  - Evidence: N/A -- new derived value.

---

## 7) State Consistency & Async Coordination

- Source of truth: `useReducer` in `useDeviceLogs` -- single reducer manages `logs`, `isLoading`, `isStreaming`, `hasMore`, `oldestTimestamp`.
- Coordination: The viewer component reads state from the hook. Backfill is triggered by scroll events in the viewer; the hook exposes `fetchOlderLogs` and `isFetchingOlder` so the viewer can guard re-entry. The download dialog operates independently -- it makes its own fetch calls and does not modify the hook's log buffer. (Note: the change brief mentions "backfill the viewer with the requested data, then build the file from the buffered log entries" but the independent-fetch approach is cleaner and avoids polluting the viewer's buffer with download-only data.)
- Async safeguards:
  - Backfill fetch uses the existing `isMounted` guard pattern from the hook. A ref (`isFetchingOlderRef`) prevents concurrent backfill requests.
  - Download fetch loop uses an `AbortController` tied to the dialog's lifecycle; closing the dialog aborts in-flight requests.
  - The `PREPEND` reducer action is the only way to add older entries, ensuring atomic state updates.
  - Scroll position restoration uses `useLayoutEffect` keyed on a prepend counter/flag to execute before the browser paints.
- Instrumentation: No new test events are strictly required for the backfill flow (no loading indicator means no loading/ready lifecycle). The download dialog will emit standard test events if needed for Playwright waits, but the primary mechanism is `data-testid` attributes and `waitForResponse` on API calls.
- Evidence: `src/hooks/use-device-logs.ts:160-335` -- main effect lifecycle; `src/components/devices/device-logs-viewer.tsx:70-84` -- auto-scroll effect.

---

## 8) Errors & Edge Cases

- Failure: Backfill fetch returns error (network failure, 500)
- Surface: `useDeviceLogs` hook
- Handling: Log to console.debug (matching existing pattern), set `isFetchingOlder` to false, do not update `oldestTimestamp`. User can retry by scrolling to top again.
- Guardrails: No user-visible error; silent failure is acceptable for backfill per requirements ("no loading indicator").
- Evidence: `src/hooks/use-device-logs.ts:247-250` -- existing error handling pattern.

- Failure: Device has fewer logs than requested download count
- Surface: Download dialog
- Handling: Loop terminates when `has_more` is false. Download whatever was collected. Show a note in progress text if final count < requested.
- Guardrails: The download button remains enabled; file is still generated with available entries.
- Evidence: Change brief: "If fewer lines exist than requested, the user gets whatever is available."

- Failure: Download fetch fails mid-way through pagination loop
- Surface: Download dialog
- Handling: Show error state in dialog with a message. Offer option to download whatever was fetched so far, or retry.
- Guardrails: AbortController prevents orphaned requests.

- Failure: User closes download dialog during active fetch
- Surface: Download dialog
- Handling: AbortController aborts all in-flight requests. Dialog closes cleanly.
- Guardrails: Cleanup in effect or callback.

- Failure: Buffer reaches MAX_BUFFER_SIZE (10,000) during backfill
- Surface: `useDeviceLogs` hook (fetchOlderLogs guard)
- Handling: When `logs.length + incoming.length > MAX_BUFFER_SIZE`, the fetch is skipped and `hasMore` is set to false. No entries are prepended or trimmed. This preserves the live streaming tail.
- Guardrails: The `canFetchOlder` guard in `fetchOlderLogs` prevents the fetch from firing when the buffer is at or near capacity.

- Failure: `oldestTimestamp` is null (empty log history)
- Surface: `useDeviceLogs` hook
- Handling: `canFetchOlder` evaluates to false; no backfill fetch attempted.
- Guardrails: Guard in `fetchOlderLogs`.

---

## 9) Observability / Instrumentation

- Signal: `data-testid="devices.logs.download-button"`
- Type: DOM attribute
- Trigger: Rendered on the download icon button in the viewer header.
- Labels / fields: N/A
- Consumer: Playwright locators in `DevicesPage.ts`.
- Evidence: Pattern from `src/components/devices/device-logs-viewer.tsx:98-111` -- streaming status testid.

- Signal: `data-testid="devices.logs.download-dialog"`
- Type: DOM attribute
- Trigger: Rendered on the download dialog content wrapper.
- Labels / fields: N/A
- Consumer: Playwright locators.
- Evidence: Pattern from `src/components/devices/provision-device-modal.tsx:333` -- `contentProps={{ 'data-testid': ... }}`.

- Signal: `data-testid="devices.logs.download-dialog.option-{count}"`
- Type: DOM attribute
- Trigger: Rendered on each line-count option button/radio.
- Labels / fields: `count` = 100, 500, 1000, 5000, 10000
- Consumer: Playwright locators for option selection.

- Signal: `data-testid="devices.logs.download-dialog.submit"`
- Type: DOM attribute
- Trigger: Rendered on the "Download" confirmation button.
- Labels / fields: N/A
- Consumer: Playwright locators.

- Signal: `data-scroll-at-top` attribute on log container
- Type: DOM data attribute
- Trigger: Updated on scroll events alongside existing `data-scroll-at-bottom`.
- Labels / fields: `"true"` / `"false"`
- Consumer: Playwright assertions for backfill trigger verification.
- Evidence: `src/components/devices/device-logs-viewer.tsx:121` -- existing `data-scroll-at-bottom`.

- Signal: `data-log-count` attribute on log container
- Type: DOM data attribute
- Trigger: Updated whenever logs array changes. Reflects `logs.length`.
- Labels / fields: Numeric string.
- Consumer: Playwright can poll this to detect when backfill entries have been prepended.
- Evidence: New attribute, following pattern of `data-scroll-at-bottom`.

---

## 10) Lifecycle & Background Work

- Hook / effect: `fetchOlderLogs` callback in `useDeviceLogs`
- Trigger cadence: On demand, called by the viewer's scroll handler when `isAtTop` and `canFetchOlder`.
- Responsibilities: Fetches one page of older logs, dispatches `PREPEND`, updates `hasMore` and `oldestTimestamp`.
- Cleanup: Uses `isMounted` guard from the parent effect. The `isFetchingOlderRef` prevents concurrent calls.
- Evidence: New callback; pattern from `src/hooks/use-device-logs.ts:256-310` -- `run()` async function.

- Hook / effect: Scroll position restoration (useLayoutEffect in viewer)
- Trigger cadence: After each `PREPEND`-induced re-render (tracked via a counter or flag from the hook).
- Responsibilities: Compute `newScrollTop = container.scrollHeight - previousScrollHeight + container.scrollTop` and apply it before paint.
- Cleanup: None needed (synchronous adjustment).
- Evidence: `src/components/devices/device-logs-viewer.tsx:70-84` -- existing auto-scroll effect pattern.

- Hook / effect: Download fetch loop (in download dialog)
- Trigger cadence: Once, when user confirms download with a line count.
- Responsibilities: Sequential paginated fetch, progress tracking, Blob construction, browser download.
- Cleanup: AbortController aborted when dialog closes or component unmounts.
- Evidence: New; pattern from `src/hooks/use-device-logs.ts:204-220` -- subscribe/fetch with AbortController.

---

## 11) Security & Permissions

Not applicable. The download uses the same authenticated `GET /api/devices/{id}/logs` endpoint as the viewer. No new endpoints or permission surfaces are introduced. The device name in the filename is sanitized to prevent filesystem injection.

---

## 12) UX / UI Impact

- Entry point: Device detail page, Logs tab, log viewer header
- Change: Add a Download icon button (`lucide-react` `Download` icon) to the right side of the header, positioned between the "Device Logs" label and the streaming status indicator.
- User interaction: Click opens a dialog; user selects line count; download starts; file saves automatically.
- Dependencies: `lucide-react` `Download` icon (already a project dependency); `Dialog` primitives from `@/components/primitives/dialog`.
- Evidence: `src/components/devices/device-logs-viewer.tsx:94-112` -- header layout.

- Entry point: Device detail page, Logs tab, log viewer scroll area
- Change: Scrolling to the top silently loads older entries. No visible loading spinner. Scroll position stays in place.
- User interaction: User scrolls up; older entries appear above; user continues reading from the same position.
- Dependencies: None beyond existing scroll container.
- Evidence: `src/components/devices/device-logs-viewer.tsx:115-139` -- scroll container.

---

## 13) Deterministic Test Plan

- Surface: Backfill on scroll to top
- Scenarios:
  - Given a device with >1,000 log entries seeded via `POST /api/testing/devices/logs/seed`, When the user navigates to the logs tab and scrolls to the top, Then additional older entries are prepended and the total entry count increases.
  - Given the log buffer has reached 10,000 entries, When the user scrolls to top, Then no additional fetch is made.
  - Given a device with exactly 500 log entries (has_more=false), When the user scrolls to top after initial load, Then no backfill fetch is attempted.
- Instrumentation / hooks: `data-scroll-at-top` attribute on container, `data-log-count` attribute, `waitForResponse` on `/api/devices/{id}/logs` for detecting backfill requests.
- Backend dependency: **Requires a new backend testing endpoint** `POST /api/testing/devices/logs/seed` that writes log entries directly to Elasticsearch for a given `device_entity_id`. The existing `POST /api/testing/devices/logs/inject` only forwards to SSE subscribers and does not persist to the search index. Request body: `{ device_entity_id, count, start_time?, end_time? }`. Response: `{ seeded, window_start, window_end }`. This endpoint must be implemented before the backfill and download Playwright specs can proceed.
- Gaps: Testing scroll position preservation precisely in Playwright is fragile; verify that `scrollTop > 0` after backfill (user is not snapped to top). Exact pixel assertion deferred.
- Evidence: `tests/e2e/devices/DevicesPage.ts:520-524` -- existing `scrollLogsToTop()` helper.

- Surface: Download dialog interaction
- Scenarios:
  - Given the logs tab is visible, When the user clicks the download button, Then the download dialog opens with line-count options.
  - Given the download dialog is open and the device has 100+ log entries seeded via `POST /api/testing/devices/logs/seed`, When the user selects 100 and clicks Download, Then a file `device-{name}-logs-{timestamp}.log` is downloaded containing up to 100 lines.
  - Given the device has fewer than the requested line count, When the download completes, Then the file contains all available lines.
- Instrumentation / hooks: `data-testid="devices.logs.download-button"`, `data-testid="devices.logs.download-dialog"`, `data-testid="devices.logs.download-dialog.option-100"`, `data-testid="devices.logs.download-dialog.submit"`. Playwright `page.waitForEvent('download')` to capture the file.
- Backend dependency: Same `POST /api/testing/devices/logs/seed` endpoint required for backfill tests.
- Gaps: Verifying exact file content in Playwright requires reading the download stream; implement for the 100-line case to keep it fast.
- Evidence: Pattern from Playwright docs on download handling.

- Surface: Download dialog cancel/close
- Scenarios:
  - Given the download dialog is open and a fetch is in progress, When the user closes the dialog, Then in-flight requests are aborted and no file is downloaded.
- Instrumentation / hooks: Dialog close button, AbortController behavior.
- Gaps: Verifying AbortController cancellation is an implementation detail; test only that the dialog closes and no download event fires.

---

## 14) Implementation Slices

- Slice: 1 -- Hook changes (backfill support)
- Goal: `useDeviceLogs` supports backward pagination and exposes `fetchOlderLogs`, `hasMore`, `isFetchingOlder`.
- Touches: `src/hooks/use-device-logs.ts`
- Dependencies: None.

- Slice: 2 -- Viewer scroll-to-top backfill
- Goal: Scrolling to top triggers backfill; scroll position is preserved; buffer cap enforced at 10,000.
- Touches: `src/components/devices/device-logs-viewer.tsx`, `src/components/devices/device-logs-tab.tsx` (pass `deviceName` prop)
- Dependencies: Slice 1.

- Slice: 3 -- Download dialog and file generation
- Goal: Download button in header, dialog with line-count options, paginated fetch, client-side file construction and download.
- Touches: `src/components/devices/device-logs-download-dialog.tsx` (new), `src/components/devices/device-logs-viewer.tsx`
- Dependencies: Slice 1 (for API fetch pattern reuse), Slice 2 (for `deviceName` prop).

- Slice: 4 -- Instrumentation and Playwright specs
- Goal: All `data-testid` attributes in place, page object updated, backfill and download specs passing.
- Touches: `tests/e2e/devices/DevicesPage.ts`, `tests/e2e/devices/devices-logs.spec.ts`
- Dependencies: Slices 2 and 3. **Backend prerequisite:** `POST /api/testing/devices/logs/seed` endpoint must be implemented to allow seeding historical log data into Elasticsearch for deterministic testing. The existing `POST /api/testing/devices/logs/inject` only forwards to SSE subscribers and does not persist to the search index.

---

## 15) Risks & Open Questions

- Risk: Scroll position restoration flickers or fails on fast repeated backfills.
- Impact: User sees a visual jump when older entries are prepended.
- Mitigation: Use `useLayoutEffect` for synchronous DOM measurement before paint. Set `isAutoScrollingRef` during restoration to suppress re-entrant scroll events. Debounce backfill triggers with a small threshold (e.g., 100ms after last backfill completes).

- Risk: Sequential download fetch for 10,000 lines (10 requests) takes noticeable time.
- Impact: User waits during download with progress indicator.
- Mitigation: Show a progress bar or text ("Fetching 3,000 / 10,000...") in the dialog. Allow cancellation at any point.

- Risk: Buffer at capacity could conflict with backfill if not properly guarded.
- Impact: User loses visibility of the newest log lines if trimming from the bottom, or cannot load more history if refused.
- Mitigation: When buffer is at or near capacity (`logs.length + incoming.length > MAX_BUFFER_SIZE`), refuse to prepend and set `hasMore` to false. This preserves the live streaming tail. The `canFetchOlder` guard prevents further backfill attempts.

- Risk: No backend testing endpoint exists for seeding historical log data into Elasticsearch.
- Impact: Playwright specs for backfill and download cannot deterministically set up >1,000 log entries. The existing `POST /api/testing/devices/logs/inject` only forwards to SSE subscribers and does not persist.
- Mitigation: Coordinate with the backend to implement `POST /api/testing/devices/logs/seed` before Slice 4. This endpoint should write log entries directly to Elasticsearch, accepting `device_entity_id`, `count`, and optional timestamp range parameters.

- Risk: Device name may contain characters unsafe for filenames.
- Impact: Download could fail or produce a confusing filename.
- Mitigation: Sanitize by replacing non-alphanumeric characters (except hyphens) with hyphens, and collapse consecutive hyphens.

---

## 16) Confidence

Confidence: High -- the existing hook architecture (reducer pattern, fetch helpers, SSE lifecycle) provides clear extension points for both backfill and download. The API already supports backward pagination via `end` + `has_more`. The dialog pattern is well-established in the codebase.
