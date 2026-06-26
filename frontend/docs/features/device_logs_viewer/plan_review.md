# Device Logs Viewer — Plan Review

## 1) Summary & Decision

**Readiness**
The plan is comprehensive, well-researched, and demonstrates strong alignment with codebase patterns. It correctly identifies the API hooks, data contracts, testing infrastructure, and instrumentation requirements. Key improvements have been made to address instrumentation integration for imperative fetches, visibility state machine clarity, scroll position testability, and backend test helper prerequisites. The scope is appropriately bounded, and the implementation slices are logically ordered with clear dependencies.

**Decision**
`GO` — The plan addresses all major concerns identified during review. The backend test helper (Slice 0) is correctly identified as a prerequisite with a documented fallback strategy. Implementation can proceed.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**
- `docs/commands/plan_feature.md` — Pass — The plan follows all required sections (0-16), includes the user requirements checklist verbatim per `plan.md:80-93`, and provides evidence quotes throughout.
- `docs/contribute/architecture/application_overview.md` — Pass — Plan correctly uses custom hook pattern (`use-device-logs.ts`) to wrap API client with camelCase transformation per `plan.md:99-101`, matching `application_overview.md:33-34`.
- `docs/contribute/testing/playwright_developer_guide.md` — Pass — Plan now explicitly documents instrumentation via direct `emitTestEvent` calls (`plan.md:324-337`) with clear emission points, acknowledging the divergence from `useListLoadingInstrumentation` and providing rationale.
- `docs/features/device_logs_viewer/change_brief.md` — Pass — All functional requirements from the change brief are mapped to the user requirements checklist (`plan.md:80-93`).

**Fit with codebase**
- `src/hooks/use-rotation.ts` — `plan.md:101,365` — Plan references `refetchInterval` pattern but uses manual `setTimeout` for the `has_more` catch-up loop. The divergence is now explicitly justified for finer control over cursor-based pagination.
- `src/lib/test/event-emitter.ts` — `plan.md:325-337` — Plan correctly identifies direct `emitTestEvent` usage for imperative fetch loops, with documented emission points and `isTestMode()` guard.
- `tests/e2e/devices/DevicesPage.ts` — `plan.md:115-117,347-348` — Plan proposes extending the page object with log viewer locators including `data-scroll-at-bottom` for scroll state assertions.
- `tests/api/factories/devices.ts:49-53` — `plan.md:124-125` — Factory already supports `deviceEntityId` which is essential for log visibility testing.

---

## 3) Open Questions & Ambiguities

All previously identified open questions have been resolved in the updated plan:

- Question: How does `useListLoadingInstrumentation` integrate with the custom imperative fetch loop?
- Resolution: Plan now documents direct `emitTestEvent` calls at `plan.md:324-337` with explicit emission points: `loading` on initial fetch start, `ready` when `hasMore === false`. This approach is clearly justified.

- Question: What happens when device initially has no logs but logs appear during polling?
- Resolution: Plan introduces "hidden-polling" state at `plan.md:199-205`. Polling continues even when viewer is hidden; viewer transitions to visible when first logs arrive. This is documented as an intentional UX decision.

- Question: Is `/api/testing/devices/{device_id}/logs` endpoint available for seeding deterministic test logs?
- Resolution: Plan treats this as Slice 0 prerequisite (`plan.md:438-442`) with explicit fallback strategy (`plan.md:469-470`) if unavailable. The dependency is now clearly tracked rather than deferred.

---

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Log viewer visibility based on device entity_id
- Scenarios:
  - Given a device with `entity_id` and existing logs, When I navigate to edit, Then the log viewer appears (`tests/e2e/devices/devices-logs.spec.ts`)
  - Given a device without `entity_id`, When I navigate to edit, Then no log viewer is shown (`tests/e2e/devices/devices-logs.spec.ts`)
  - Given a device with `entity_id` but no logs, When I navigate to edit, Then no log viewer is shown initially but polling continues (`tests/e2e/devices/devices-logs.spec.ts`)
- Instrumentation: `data-testid="devices.logs.viewer"`, `waitForListLoading(page, 'devices.logs', 'ready')`
- Backend hooks: `testData.devices.create({ deviceEntityId: 'valid_id' })`, `POST /api/testing/devices/{device_id}/logs` for seeding
- Gaps: None if Slice 0 is complete; fallback scope documented if unavailable
- Evidence: `plan.md:402-420`

- Behavior: Live updates checkbox toggle
- Scenarios:
  - Given the log viewer is visible, When I uncheck live updates, Then polling stops (verifiable via `list_loading` metadata)
  - Given I unchecked live updates, When I check it again, Then polling resumes
- Instrumentation: `data-testid="devices.logs.live-checkbox"`, `list_loading` events with `metadata.isPolling`
- Backend hooks: None required for toggle behavior
- Gaps: None
- Evidence: `plan.md:407-408`

- Behavior: Auto-scroll behavior
- Scenarios:
  - Given logs are visible and scrollbar is at bottom, When new logs arrive, Then view auto-scrolls
  - Given I have scrolled up, When new logs arrive, Then my scroll position is preserved and `data-scroll-at-bottom="false"`
- Instrumentation: `data-testid="devices.logs.container"` with `data-scroll-at-bottom` attribute
- Backend hooks: Requires log seeding (`POST /api/testing/devices/{device_id}/logs`)
- Gaps: None if Slice 0 is complete
- Evidence: `plan.md:350-355,406-407,414`

---

## 5) Adversarial Sweep (must find >=3 credible issues or declare why none exist)

- Checks attempted: Instrumentation integration for imperative fetch, visibility state machine transitions, scroll position testability, backend test helper dependency, memory buffer limits, tab visibility handling
- Evidence: `plan.md:324-337` (instrumentation), `plan.md:199-205,244-250` (visibility), `plan.md:350-355` (scroll instrumentation), `plan.md:438-442` (backend prerequisite), `plan.md:266-271` (buffer limit), `plan.md:448,480-482` (tab visibility)
- Why the plan holds: All major concerns have been addressed with explicit documentation. The plan now includes:
  1. Direct `emitTestEvent` emission points with clear triggers
  2. "hidden-polling" state for late-arriving logs with documented UX rationale
  3. `data-scroll-at-bottom` attribute for deterministic scroll assertions
  4. Slice 0 prerequisite for backend test helper with fallback strategy
  5. Log buffer invariant (max 1000 entries with FIFO eviction)
  6. `document.visibilityState` handling in Slice 1

No remaining credible issues that would block implementation.

---

## 6) Derived-Value & State Invariants (table)

- Derived value: `shouldShowViewer`
  - Source dataset: `hasEntityId` (from device config, unfiltered) AND `logs.length > 0` (dynamically evaluated)
  - Write / cleanup triggered: Conditional rendering; no persistence
  - Guards: Initial fetch must complete; viewer transitions to visible when first logs arrive
  - Invariant: Never show if `!hasEntityId`; always show once `logs.length > 0`
  - Evidence: `plan.md:244-250`

- Derived value: `isAtBottom`
  - Source dataset: DOM scroll position (scrollTop + clientHeight vs scrollHeight)
  - Write / cleanup triggered: Determines auto-scroll; updates `data-scroll-at-bottom` attribute
  - Guards: Passive scroll listener; ~10px threshold
  - Invariant: Defaults to `true` on mount
  - Evidence: `plan.md:252-257,350-355`

- Derived value: `pollingCursor` (windowEnd from API)
  - Source dataset: Most recent successful fetch response `windowEnd`
  - Write / cleanup triggered: Used as `start` param for subsequent fetches
  - Guards: Must not poll if cursor is null
  - Invariant: Cursor only advances forward
  - Evidence: `plan.md:259-264`

- Derived value: `logs` array buffer
  - Source dataset: Accumulated log entries from all successful fetches
  - Write / cleanup triggered: Appended on fetch; FIFO eviction when exceeds limit
  - Guards: Max buffer size of 1000 entries
  - Invariant: `logs.length <= 1000`
  - Evidence: `plan.md:266-271`

All derived values use appropriate sources; no persistent writes driven by filtered views.

---

## 7) Risks & Mitigations (top 3)

- Risk: Backend log seeding endpoint unavailable, limiting test coverage
- Mitigation: Slice 0 explicitly tracks this as a prerequisite with documented fallback (visibility and checkbox tests only)
- Evidence: `plan.md:438-442,469-470,484-486`

- Risk: Imperative fetch pattern diverges from established `useListLoadingInstrumentation` pattern
- Mitigation: Documented emission points in Section 9; consider extracting reusable helper if pattern is needed elsewhere
- Evidence: `plan.md:324-337,488-490`

- Risk: High log volume causes UI jank or memory issues
- Mitigation: Max buffer of 1000 entries with FIFO eviction; batch DOM updates
- Evidence: `plan.md:266-271,476-478`

---

## 8) Confidence

Confidence: High — The plan demonstrates thorough research, correct architectural alignment, and addresses all major review concerns. Instrumentation integration is explicitly documented, visibility state machine is clarified, scroll position is testable via data attributes, and backend test helper is tracked as a prerequisite with fallback strategy. The plan is implementation-ready.
