# Plan Review: Device Logs Backfill & Download

## 1) Summary & Decision

**Readiness**

The plan is well-structured, demonstrates thorough codebase research, and provides implementation-ready detail across all 16 required sections. The hook extension points (reducer actions, `fetchHistory` pattern), API response shape (`has_more`, `window_start`), dialog composition pattern, and scroll management strategy are all accurately identified. The updated plan now correctly handles the PREPEND buffer-cap semantics (refuse rather than trim), includes explicit scroll restoration detail with `isAutoScrollingRef` guard, acknowledges the change brief vs. plan divergence on download buffer independence, and identifies the backend testing endpoint prerequisite for Playwright coverage. The remaining condition is that the backend `POST /api/testing/devices/logs/seed` endpoint must be implemented before Slice 4 can proceed -- this is clearly documented in the plan's scope, test plan, implementation slices, and risks sections.

**Decision**

`GO` -- The plan is implementation-ready. The backend testing endpoint prerequisite is clearly documented as a dependency for Slice 4, and Slices 1-3 (the actual UI feature work) can proceed immediately without it.

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/commands/plan_feature.md` -- Pass -- All 16 required headings present with templates correctly applied. User Requirements Checklist at `plan.md:74-88` included verbatim.
- `docs/product_brief.md` -- Pass -- Feature extends the device detail page's logs tab, consistent with the product's device management scope.
- `AGENTS.md` (line 5: "Treat instrumentation as part of the UI contract") -- Pass -- `plan.md:277-315` defines `data-testid` attributes, `data-scroll-at-top`, and `data-log-count` instrumentation.
- `AGENTS.md` (line 6: "Ship instrumentation changes and matching Playwright coverage in the same slice") -- Pass -- Slice 4 (`plan.md:410-413`) bundles all instrumentation and Playwright specs together with explicit backend prerequisite noted.
- `docs/contribute/testing/playwright_developer_guide.md` (line 2: "Real backend always") -- Pass -- `plan.md:370` uses `waitForResponse` on the real API endpoint. No route mocks proposed.
- `docs/contribute/testing/playwright_developer_guide.md` (line 1: "API-first data setup") -- Pass -- `plan.md:367` now explicitly references `POST /api/testing/devices/logs/seed` for data setup. `plan.md:371` describes the required endpoint shape.
- `docs/contribute/testing/playwright_developer_guide.md` ("Missing behavior belongs in the backend") -- Pass -- `plan.md:60-62` and `plan.md:431-433` correctly identify the backend prerequisite rather than proposing a Playwright workaround.
- `docs/contribute/architecture/application_overview.md` (line 33: "Custom hooks adapt API responses to frontend domain models") -- Pass -- `plan.md:122-140` correctly maps `has_more` to `hasMore` and `window_start` to `oldestTimestamp`.

**Fit with codebase**

- `useDeviceLogs` hook (`src/hooks/use-device-logs.ts`) -- `plan.md:94-96` -- The `PREPEND` action and `fetchOlderLogs` callback are natural extensions of the existing reducer pattern. The `isMounted` guard at line 170 and `AbortController` at line 171 provide reusable patterns. Good fit.
- `DeviceLogsViewer` (`src/components/devices/device-logs-viewer.tsx`) -- `plan.md:98-100` -- The existing `isAutoScrollingRef` guard (line 47) and `SCROLL_THRESHOLD_PX` (line 14) are correctly identified for reuse. The updated plan at `plan.md:169` now explicitly mirrors the `requestAnimationFrame` clearing pattern from line 80. Good fit.
- `DeviceLogsTab` (`src/components/devices/device-logs-tab.tsx`) -- `plan.md:102-104` -- Adding `deviceName` pass-through is straightforward; `Device` type already includes `deviceName`. Good fit.
- `Dialog primitives` -- `plan.md:106-108` -- Pattern match with `provision-device-modal.tsx` is appropriate. Good fit.
- `DevicesPage.ts` page object -- `plan.md:110-112` -- Existing `scrollLogsToTop()` at line 520 is directly reusable. Good fit.

## 3) Open Questions & Ambiguities

No blocking open questions remain after the plan updates. The three ambiguities identified in the initial review have been resolved:

1. Backend testing endpoint -- Now documented as a cross-repo prerequisite at `plan.md:60-62`.
2. PREPEND buffer-cap behavior -- Resolved in favor of "refuse to prepend" at `plan.md:168` and `plan.md:263-266`.
3. Change brief vs. plan divergence on download buffer -- Explicitly acknowledged at `plan.md:228`.

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Backfill on scroll to top
- Scenarios:
  - Given a device with >1,000 log entries seeded via `POST /api/testing/devices/logs/seed`, When the user navigates to the logs tab and scrolls to the top, Then additional older entries are prepended and `data-log-count` increases (`tests/e2e/devices/devices-logs.spec.ts`)
  - Given the log buffer has reached 10,000 entries, When the user scrolls to top, Then no additional API request is made
  - Given a device with <1,000 entries (has_more=false), When the user scrolls to top, Then no backfill request is made
- Instrumentation: `data-scroll-at-top`, `data-log-count`, `waitForResponse` on `/api/devices/{id}/logs`
- Backend hooks: `POST /api/testing/devices/logs/seed` (documented at `plan.md:371`)
- Gaps: Scroll position preservation verified only as `scrollTop > 0` (not pixel-exact). Acceptable -- documented at `plan.md:372`.
- Evidence: `plan.md:365-373`

- Behavior: Download dialog interaction
- Scenarios:
  - Given the logs tab is visible, When the user clicks the download button, Then the download dialog opens with line-count options
  - Given 100+ seeded log entries, When the user selects 100 and clicks Download, Then a file is downloaded with correct name pattern and up to 100 lines
  - Given fewer lines than requested, When download completes, Then file contains all available lines
- Instrumentation: `data-testid="devices.logs.download-button"`, `data-testid="devices.logs.download-dialog"`, `data-testid="devices.logs.download-dialog.option-100"`, `data-testid="devices.logs.download-dialog.submit"`, `page.waitForEvent('download')`
- Backend hooks: Same `POST /api/testing/devices/logs/seed` endpoint
- Gaps: File content verification limited to the 100-line case for speed. Acceptable.
- Evidence: `plan.md:375-383`

- Behavior: Download dialog cancel/close
- Scenarios:
  - Given the download dialog is open, When the user closes it, Then dialog closes and no download event fires
- Instrumentation: Dialog close button, absence of download event
- Backend hooks: None needed
- Gaps: None
- Evidence: `plan.md:385-389`

## 5) Adversarial Sweep

- Checks attempted: PREPEND buffer-cap contradiction, scroll restoration timing, `isAutoScrollingRef` re-trigger risk, backend testing endpoint gap, change brief vs. plan divergence, download AbortController cleanup
- Evidence: `plan.md:168` (refuse to prepend), `plan.md:169` (explicit `isAutoScrollingRef` and `requestAnimationFrame` pattern), `plan.md:172` (previousScrollHeightRef data flow), `plan.md:60-62` (backend prerequisite), `plan.md:228` (change brief acknowledgment)
- Why the plan holds: All previously identified issues have been resolved. The buffer-cap behavior is now consistent (refuse, not trim) at `plan.md:168` and `plan.md:263-266`. The scroll restoration detail at `plan.md:169` and `plan.md:172` explicitly describes the `isAutoScrollingRef` guard with `requestAnimationFrame` clearing, preventing re-trigger. The backend testing endpoint is documented as a prerequisite rather than an afterthought. The download dialog independence from the viewer buffer is explicitly justified at `plan.md:228`.

## 6) Derived-Value & State Invariants

- Derived value: `canFetchOlder`
  - Source dataset: `hasMore` (from API `has_more`), `isFetchingOlderRef` (local ref), `logs.length` vs `MAX_BUFFER_SIZE` (10,000)
  - Write / cleanup triggered: Guards backfill fetch; no persistent write or cache mutation
  - Guards: False when `!hasMore || isFetchingOlder || logs.length >= MAX_BUFFER_SIZE`
  - Invariant: Buffer never exceeds 10,000 entries; no concurrent backfill fetches
  - Evidence: `plan.md:195-200`

- Derived value: `oldestTimestamp`
  - Source dataset: `window_start` from API response
  - Write / cleanup triggered: Used as `end` query parameter for next backfill request
  - Guards: Non-null required; reset on device change (RESET action)
  - Invariant: Advances backward monotonically; stale value after device change prevented by RESET
  - Evidence: `plan.md:202-207`

- Derived value: `isAtTop` (scroll state)
  - Source dataset: `scrollTop <= SCROLL_THRESHOLD_PX`
  - Write / cleanup triggered: Triggers `fetchOlderLogs` when combined with `canFetchOlder`
  - Guards: Suppressed during programmatic scroll via `isAutoScrollingRef`
  - Invariant: Must not fire during scroll position restoration. Failure causes infinite backfill loop.
  - Evidence: `plan.md:209-214`

- Derived value: `downloadFilename`
  - Source dataset: `deviceName` prop + wall-clock timestamp
  - Write / cleanup triggered: Single-use at Blob construction; triggers browser download
  - Guards: Device name sanitized (non-alphanumeric to hyphens)
  - Invariant: Matches `device-{sanitized-name}-logs-{ISO-timestamp}.log`
  - Evidence: `plan.md:216-221`

## 7) Risks & Mitigations (top 3)

- Risk: Backend testing endpoint `POST /api/testing/devices/logs/seed` does not yet exist. Playwright specs for backfill and download depend on seeded historical data in Elasticsearch.
- Mitigation: Documented as a cross-repo prerequisite at `plan.md:60-62`. Slices 1-3 can proceed independently. Slice 4 blocks on this endpoint.
- Evidence: `plan.md:60-62`, `plan.md:371`, `plan.md:413`, `plan.md:431-433`

- Risk: Scroll position restoration flickers or re-triggers backfill on fast repeated scrolls.
- Mitigation: `useLayoutEffect` for synchronous DOM adjustment before paint. `isAutoScrollingRef` set before `scrollTop` assignment, cleared via `requestAnimationFrame`. Optional debounce (100ms) after backfill completes.
- Evidence: `plan.md:169`, `plan.md:172`, `plan.md:419-421`

- Risk: Sequential download fetch for 10,000 lines (10 requests) takes noticeable time.
- Mitigation: Progress indicator in dialog ("Fetching 3,000 / 10,000..."). AbortController for cancellation at any point.
- Evidence: `plan.md:180`, `plan.md:423-425`

## 8) Confidence

Confidence: High -- The updated plan resolves all previously identified contradictions and gaps. The architecture is a clean extension of existing patterns, the backend prerequisite is explicitly documented, and the implementation slices allow UI work to proceed immediately while the testing endpoint is coordinated.
