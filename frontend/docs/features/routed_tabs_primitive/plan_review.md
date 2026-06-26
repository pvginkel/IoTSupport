# Plan Review: Routed Tabs Primitive

## 1) Summary & Decision

**Readiness**

The plan is well-researched, clearly scoped, and demonstrates strong alignment with the existing codebase. The research log accurately reflects the current implementation, the file map is exhaustive, and the data contracts are sensible. After applying fixes for path-matching clarity, the `useRestoreTab` return type, and storage key constant management, the plan is ready for implementation.

**Decision**

`GO` -- All previously identified conditions have been resolved in the updated plan. The extraction is mechanical, the Playwright suite provides full behavioral coverage, and no backend changes are required.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/commands/plan_feature.md` -- Pass -- All 16 required sections are present and populated. The user requirements checklist in section 1a is included verbatim.
- `docs/product_brief.md` -- Pass -- `plan.md:36-37` correctly identifies this as a frontend-only refactoring with no product behavior changes. The product brief's device detail routes are respected.
- `docs/contribute/architecture/application_overview.md` -- Pass -- `plan.md:48,67` places the primitive in `src/components/primitives/` which aligns with the architecture doc's "shared UI building blocks" pattern (`application_overview.md:52`).
- `docs/contribute/testing/playwright_developer_guide.md` -- Pass -- `plan.md:357-369` identifies all existing test scenarios and confirms no route mocking is needed. The plan correctly states existing specs should pass without changes.
- `CLAUDE.md` -- Pass -- The plan follows the guideline to "prefer extending existing abstractions over introducing new ones" (`CLAUDE.md` working guidelines point 1) by extracting into a primitive rather than creating ad hoc helpers.

**Fit with codebase**

- `src/components/primitives/index.ts` -- `plan.md:98-100` -- The barrel export pattern matches the existing convention at lines 57-58 of the index file (SegmentedTabs export). Confirmed.
- `src/components/devices/device-detail-header.tsx` -- `plan.md:104-106` -- The plan correctly identifies the full scope of code to extract (TabLink helper, useEffect persistence, useLocation) and now includes the `DEVICE_TAB_STORAGE_KEY` constant export.
- `src/hooks/use-device-form.ts` -- `plan.md:122-124` -- The import at line 8 and call at line 151 are accurately cited. The migration path now references the shared `DEVICE_TAB_STORAGE_KEY` constant.
- `src/routes/devices/$deviceId/coredumps.tsx` -- The coredumps tab is a layout route with nested children (`coredumps/index.tsx`, `coredumps/$coredumpId.tsx`). The plan now explicitly addresses this in the path-matching strategy at `plan.md:217-218`.

---

## 3) Open Questions & Ambiguities

No open questions remain. The three issues identified in the initial review have been resolved:

1. Path matching for nested routes is now specified using `value` slug matching (`plan.md:217`).
2. The `useRestoreTab` return type is corrected to `void` (`plan.md:183`).
3. The storage key constant pattern is documented (`plan.md:105-106`, `plan.md:123`).

---

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Tab navigation, persistence, deep-linking, badge count, and header identity
- Scenarios:
  - Given a device exists, When the user visits `/devices/{id}` with no stored preference, Then the URL redirects to `/devices/{id}/edit` and the configuration tab has `aria-current="page"` (`tests/e2e/devices/devices-tabs.spec.ts:5-19`)
  - Given a device exists, When the user clicks each tab in sequence, Then the URL updates and the clicked tab shows `aria-current="page"` (`tests/e2e/devices/devices-tabs.spec.ts:21-46`)
  - Given the user visited the logs tab on device A, When the user navigates to device B via the list, Then device B opens on the logs tab (`tests/e2e/devices/devices-tabs.spec.ts:121-146`)
  - Given a device has coredumps, When the detail header renders, Then the coredumps tab label includes the count (`tests/e2e/devices/devices-tabs.spec.ts:89-100`)
  - Given the user is in new-device or duplicate mode, When the page renders, Then the tab bar and header are not visible (`tests/e2e/devices/devices-tabs.spec.ts:48-68`)
  - Given a device exists, When the user deep-links to each tab URL, Then the corresponding tab is active (`tests/e2e/devices/devices-tabs.spec.ts:71-87`)
- Instrumentation: `data-testid="devices.detail.tabs"`, `data-testid="devices.detail.tab.configuration"`, `data-testid="devices.detail.tab.logs"`, `data-testid="devices.detail.tab.coredumps"`, `aria-current="page"` on active links.
- Backend hooks: `devices.create()`, `devices.createCoredump()` factories -- already exist.
- Gaps: None. All scenarios are covered by existing specs. The refactoring is behavior-preserving.
- Evidence: `plan.md:357-369`, `tests/e2e/devices/devices-tabs.spec.ts:1-174`

---

## 5) Adversarial Sweep

**Minor -- `basePath` trailing slash convention not specified**

**Evidence:** `plan.md:217` -- "checks `location.pathname.startsWith(basePath + definition.value)`"

**Why it matters:** If `basePath` is `/devices/42/` (with trailing slash) and `definition.value` is `edit`, the concatenation produces `/devices/42/edit` which matches correctly. But if `basePath` is `/devices/42` (no trailing slash), the concatenation produces `/devices/42edit` which would never match. The plan should clarify whether `basePath` includes a trailing slash or whether the matching logic inserts one.

**Fix suggestion:** Document in the JSDoc for the `basePath` prop that it must end with `/`, or have the primitive normalize it internally (e.g., `const normalizedBase = basePath.endsWith('/') ? basePath : basePath + '/'`). This is a minor implementation detail the developer will handle, but worth noting.

**Confidence:** Medium

---

- Checks attempted: React 19 concurrent mode double-mount of useEffect in StrictMode
- Evidence: `plan.md:325-329` -- persistence useEffect, `plan.md:333-337` -- restore useEffect
- Why the plan holds: The persistence `useEffect` is idempotent (writing the same value to localStorage twice is harmless). The `useRestoreTab` navigate effect fires `navigate({ replace: true })` which is also idempotent -- a second call with the same destination is a no-op in TanStack Router. React 19 StrictMode double-mount does not create issues here.

---

- Checks attempted: Stale closure in onClick handler capturing wrong tab value
- Evidence: `plan.md:215` -- "onClick that eagerly calls setTabPreference"
- Why the plan holds: Each `<Link>` is rendered in a `.map()` over tab definitions, and the `onClick` closure captures the current iteration's `definition.value`. Since tab definitions are stable props (not derived from async state), there is no stale closure risk.

---

- Checks attempted: Race condition between onClick eager write and useEffect fallback write
- Evidence: `plan.md:214-215` -- both onClick and useEffect write to localStorage
- Why the plan holds: Both mechanisms write the same value for the same navigation. The onClick fires synchronously on click; the useEffect fires after the URL updates. Even if both run, they write the same `value` to the same `storageKey`, so the final state is always correct. This matches the existing behavior in `device-detail-header.tsx:28-34,170`.

---

## 6) Derived-Value & State Invariants

- Derived value: Active tab identity (for persistence writes)
  - Source dataset: `location.pathname` from `useLocation()` matched against tab definitions' `value` slugs
  - Write / cleanup triggered: `localStorage.setItem(storageKey, value)` on every matching pathname change
  - Guards: `useEffect` only writes when `location.pathname.startsWith(basePath)` (`plan.md:239`)
  - Invariant: The persisted value must always be one of the declared tab `value` strings. The `basePath` guard prevents writes when navigating away from the tabbed view.
  - Evidence: `plan.md:236-241`, `device-detail-header.tsx:28-34`

- Derived value: Restored tab on index visit
  - Source dataset: `localStorage.getItem(storageKey)` validated against `validValues` array
  - Write / cleanup triggered: `navigate({ replace: true })` -- no persistent write, only a route transition
  - Guards: Validation ensures only known tab values produce a redirect; unknown values fall back to `defaultValue`
  - Invariant: The redirect must always produce a valid child route URL. The `toPath` callback is consumer-defined and must map every valid tab value to a resolvable route.
  - Evidence: `plan.md:245-250`, `devices/$deviceId/index.tsx:14-21`

- Derived value: Coredump badge count (consumer-side, not in primitive)
  - Source dataset: `useCoredumps(device.id)` query result (unfiltered)
  - Write / cleanup triggered: None -- read-only, rendered as ReactNode label
  - Guards: Badge only renders when `coredumps.length > 0`
  - Invariant: Count reflects current React Query cache. Since `useCoredumps` is called in the consumer, staleness is managed by React Query's default refresh behavior.
  - Evidence: `plan.md:255-259`, `device-detail-header.tsx:18,135-139`

No filtered-view-drives-persistent-write violations found.

---

## 7) Risks & Mitigations (top 3)

- Risk: Test ID drift breaks all six device tab Playwright specs in CI.
- Mitigation: Plan preserves existing IDs via `testIdPrefix` prop and explicit `testId` overrides (`plan.md:400-402`). Run `pnpm playwright test tests/e2e/devices/devices-tabs.spec.ts` as final verification gate before merge.
- Evidence: `plan.md:400-402`, `tests/e2e/devices/DevicesPage.ts:37-53`

- Risk: Path matching for nested routes (coredumps child routes) produces incorrect tab value in localStorage.
- Mitigation: Plan now specifies `value`-based slug matching with `basePath` prefix (`plan.md:217`). The existing Playwright persistence tests (`devices-tabs.spec.ts:120-173`) will catch regressions.
- Evidence: `plan.md:412-414`, `src/routes/devices/$deviceId/coredumps/$coredumpId.tsx`

- Risk: `use-device-form.ts` storage key diverges from the `RoutedTabs` consumer's key after refactoring.
- Mitigation: Plan specifies a shared `DEVICE_TAB_STORAGE_KEY` constant exported from `device-detail-header.tsx` and imported by both consumers (`plan.md:105-106,123`). TypeScript will flag any import errors at compile time.
- Evidence: `plan.md:105-106`, `plan.md:122-124`

---

## 8) Confidence

Confidence: High -- The plan is thorough, well-evidenced, and all previously identified issues have been resolved. The extraction is mechanical with full Playwright coverage ensuring behavioral parity.
