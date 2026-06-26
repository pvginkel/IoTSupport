# Plan: Routed Tabs Primitive

## 0) Research Log & Findings

**Searched areas:**

- `src/components/devices/device-detail-header.tsx` — current tab bar implementation with inline `TabLink` helper, `useLocation`-based persistence effect, and coredump badge composition.
- `src/lib/utils/device-tab-preference.ts` — localStorage read/write with `DeviceTab` type validation.
- `src/routes/devices/$deviceId/index.tsx` — redirect-on-mount index route using `getDeviceTabPreference()`.
- `src/routes/devices/$deviceId.tsx` — layout route rendering `DeviceDetailHeader` + `<Outlet />`.
- `src/hooks/use-device-form.ts` — calls `setDeviceTabPreference('logs')` after successful device save to steer post-save navigation.
- `src/components/primitives/` — existing primitive library (SegmentedTabs, Button, Dialog, etc.) and barrel export in `index.ts`.
- `tests/e2e/devices/devices-tabs.spec.ts` — full Playwright coverage for tab navigation, persistence, deep-linking, badge count, and header identity.
- `tests/e2e/devices/DevicesPage.ts` — page object with locators for `devices.detail.tab.*` and `devices.detail.tabs`.

**Key findings:**

1. The tab bar in `device-detail-header.tsx` is self-contained: a `<nav>` with three `<Link>` components using TanStack Router's `activeProps` pattern and an absolute-positioned underline indicator via CSS.
2. Tab preference persistence happens in two places: (a) a `useEffect` in the header that watches `location.pathname` and writes to localStorage, and (b) `onClick` handlers on each `TabLink` that eagerly write the preference.
3. `use-device-form.ts:151` programmatically calls `setDeviceTabPreference('logs')` after a successful save — this call site must continue working after refactoring. It does not use the tab bar; it writes directly to localStorage before navigating. This will need to use the new primitive's persistence API.
4. The index route (`devices/$deviceId/index.tsx`) is a pure redirect component that reads the preference and calls `navigate()` with `replace: true`.
5. Existing test IDs (`devices.detail.tabs`, `devices.detail.tab.configuration`, etc.) are consumed by the `DevicesPage` page object. The primitive should allow the consumer to produce these exact IDs via a `testIdPrefix` prop.
6. `SegmentedTabs` serves a different purpose (in-page state, `role="tablist"` with buttons) and should not be modified.

**Conflicts resolved:**

- The brief says "helper/hook for index-route redirect logic." The current redirect is a tiny component. The primitive will export a `useRestoreTab` hook that encapsulates the navigate-with-replace pattern, which the index route will consume.
- `use-device-form.ts` calls `setDeviceTabPreference` directly. After refactoring, it will import a `setTabPreference(storageKey, tab)` utility from the primitive module instead.

---

## 1) Intent & Scope

**User intent**

Extract the URL-driven tab bar and localStorage-based tab preference persistence from the device detail header into a reusable `RoutedTabs` primitive, then refactor the device domain to consume it.

**Prompt quotes**

- "reusable RoutedTabs primitive lives in src/components/primitives/"
- "Tab definitions accept ReactNode labels so consumers can compose badges or other content"
- "Built-in localStorage preference persistence via a configurable storageKey"
- "Helper/hook for index-route redirect logic (restore last tab on bare URL visit)"
- "DeviceDetailHeader refactored to use the new primitive, keeping only device-specific content"

**In scope**

- New `RoutedTabs` component in `src/components/primitives/routed-tabs.tsx`
- Persistence utilities (`getTabPreference`, `setTabPreference`) generic over any storage key
- `useRestoreTab` hook for index-route redirect
- Refactor `DeviceDetailHeader` to delegate tab rendering to `RoutedTabs`
- Delete `src/lib/utils/device-tab-preference.ts` and update all import sites
- Update `use-device-form.ts` to use the generic persistence utility
- Barrel export from `src/components/primitives/index.ts`
- Inline JSDoc documentation on the primitive
- Playwright test ID stability (no spec changes needed if IDs remain the same; update page object if IDs change)

**Out of scope**

- Per-entity tab persistence (e.g., different remembered tab per device ID)
- Modifying or replacing `SegmentedTabs`
- Badge/count as a first-class primitive feature (consumers compose via `ReactNode` labels)
- New Playwright specs beyond updating existing ones for changed test IDs

**Assumptions / constraints**

- TanStack Router's `Link` component with `activeProps` remains the mechanism for active-tab styling.
- The primitive is purely presentational + persistence; it does not fetch data or manage route definitions.
- localStorage is the only persistence backend; no server-side preference storage.

---

## 1a) User Requirements Checklist

- [ ] New reusable RoutedTabs primitive lives in src/components/primitives/
- [ ] Tab bar renders TanStack Router Link components with active-state underline styling
- [ ] Tab definitions accept ReactNode labels so consumers can compose badges or other content
- [ ] Built-in localStorage preference persistence via a configurable storageKey
- [ ] Helper/hook for index-route redirect logic (restore last tab on bare URL visit)
- [ ] Configurable data-testid prefix support
- [ ] DeviceDetailHeader refactored to use the new primitive, keeping only device-specific content
- [ ] Device tab preference utility replaced by the primitive's built-in persistence
- [ ] Index route redirect uses the primitive's helper
- [ ] Core Dumps badge passed as ReactNode label by the consumer (not a primitive feature)
- [ ] Existing Playwright tests updated for any changed test IDs and pass green
- [ ] Inline documentation on how to use the primitive (preferred over separate MD docs)

---

## 2) Affected Areas & File Map

- **Area:** `src/components/primitives/routed-tabs.tsx` (NEW)
- **Why:** Houses the `RoutedTabs` component, `RoutedTabDefinition` type, persistence utilities (`getTabPreference`, `setTabPreference`), and the `useRestoreTab` hook.
- **Evidence:** No existing file — new primitive following the pattern of `src/components/primitives/segmented-tabs.tsx`.

---

- **Area:** `src/components/primitives/index.ts`
- **Why:** Must re-export `RoutedTabs`, `RoutedTabDefinition`, `getTabPreference`, `setTabPreference`, and `useRestoreTab`.
- **Evidence:** `src/components/primitives/index.ts:57-58` — existing pattern for `SegmentedTabs` export.

---

- **Area:** `src/components/devices/device-detail-header.tsx`
- **Why:** Remove the inline `TabLink` component, the `useLocation`/`useEffect` persistence logic, and the `useCoredumps` import. Replace with a `<RoutedTabs>` consumer that passes device-specific tab definitions including the coredumps badge as a `ReactNode` label. Export a `DEVICE_TAB_STORAGE_KEY` constant (value: `'iot-support-device-tab'`) so both this file and `use-device-form.ts` reference the same key without magic strings.
- **Evidence:** `src/components/devices/device-detail-header.tsx:1-177` — entire tab bar and persistence effect. `src/lib/utils/device-tab-preference.ts:1` — current storage key constant being replaced.

---

- **Area:** `src/lib/utils/device-tab-preference.ts` (DELETE)
- **Why:** Replaced entirely by the primitive's generic `getTabPreference` / `setTabPreference` utilities.
- **Evidence:** `src/lib/utils/device-tab-preference.ts:1-25` — full file.

---

- **Area:** `src/routes/devices/$deviceId/index.tsx`
- **Why:** Replace manual `useEffect` + `useNavigate` redirect with the primitive's `useRestoreTab` hook.
- **Evidence:** `src/routes/devices/$deviceId/index.tsx:1-25` — full file.

---

- **Area:** `src/hooks/use-device-form.ts`
- **Why:** Replace `import { setDeviceTabPreference }` with `import { setTabPreference }` from the primitive and `import { DEVICE_TAB_STORAGE_KEY }` from `device-detail-header.tsx`. Update the call at line 151 to `setTabPreference(DEVICE_TAB_STORAGE_KEY, 'logs')`.
- **Evidence:** `src/hooks/use-device-form.ts:8` (import) and `src/hooks/use-device-form.ts:151` (`setDeviceTabPreference('logs')`).

---

- **Area:** `tests/e2e/devices/DevicesPage.ts`
- **Why:** If test IDs change, update locators. The plan preserves existing `devices.detail.tabs` and `devices.detail.tab.*` IDs, so this file should require no changes. Verify after implementation.
- **Evidence:** `tests/e2e/devices/DevicesPage.ts:37-53` — tab locators.

---

- **Area:** `tests/e2e/devices/devices-tabs.spec.ts`
- **Why:** The localStorage key `'iot-support-device-tab'` is referenced directly in `page.evaluate()` calls. If the storage key changes, these must be updated. The plan keeps the same key constant defined in the device consumer, so the specs reference stays valid.
- **Evidence:** `tests/e2e/devices/devices-tabs.spec.ts:10,26` — `localStorage.removeItem('iot-support-device-tab')`.

---

## 3) Data Model / Contracts

- **Entity / contract:** `RoutedTabDefinition` — tab descriptor passed to `RoutedTabs`
- **Shape:**
  ```ts
  interface RoutedTabDefinition {
    /** Route path for TanStack Router Link `to` prop */
    to: string
    /** Route params object passed to Link */
    params?: Record<string, string>
    /** Slug used for persistence (written to localStorage) */
    value: string
    /** Tab label — any ReactNode, enabling badge composition */
    label: ReactNode
    /** Optional test ID; if omitted, derived from testIdPrefix + value */
    testId?: string
  }
  ```
- **Mapping:** No snake_case/camelCase mapping needed — this is a frontend-only view model.
- **Evidence:** Modeled after the inline `TabLink` props in `device-detail-header.tsx:147-158`.

---

- **Entity / contract:** Persistence utilities
- **Shape:**
  ```ts
  function getTabPreference(storageKey: string, validValues: string[], defaultValue: string): string
  function setTabPreference(storageKey: string, value: string): void
  ```
- **Mapping:** Direct replacement for `getDeviceTabPreference` / `setDeviceTabPreference` in `device-tab-preference.ts:7-25`.
- **Evidence:** `src/lib/utils/device-tab-preference.ts:1-25`.

---

- **Entity / contract:** `useRestoreTab` hook
- **Shape:**
  ```ts
  function useRestoreTab(options: {
    storageKey: string
    validValues: string[]
    defaultValue: string
    /** Function that maps tab value to a full route path, receiving current route params */
    toPath: (tab: string) => { to: string; params?: Record<string, string> }
  }): void
  ```
- **Mapping:** Encapsulates the navigate-with-replace pattern from `devices/$deviceId/index.tsx:11-24`.
- **Evidence:** `src/routes/devices/$deviceId/index.tsx:11-24`.

---

## 4) API / Integration Surface

No backend API changes. This feature is entirely frontend. The only external integration is `localStorage`, which is already used by the existing `device-tab-preference.ts` module.

---

## 5) Algorithms & UI Flows

- **Flow:** Tab bar rendering and active-state indication
- **Steps:**
  1. Consumer passes an array of `RoutedTabDefinition` objects to `<RoutedTabs>`.
  2. `RoutedTabs` renders a `<nav>` element with `data-testid` derived from the `testIdPrefix` prop.
  3. For each tab definition, render a TanStack Router `<Link>` with the `to`/`params` props.
  4. Apply `activeProps={{ className: 'active', 'aria-current': 'page' }}` for the router to mark the current route.
  5. The underline indicator is rendered as a child `<span>` that becomes visible via the `.active` parent CSS class (same pattern as current `TabLink`).
- **States / transitions:** Active tab is determined entirely by TanStack Router's URL matching — no local React state for selection.
- **Hotspots:** None — the tab bar is a thin wrapper over `<Link>` with CSS classes.
- **Evidence:** `src/components/devices/device-detail-header.tsx:146-177` — existing `TabLink`.

---

- **Flow:** Tab preference persistence (write)
- **Steps:**
  1. `RoutedTabs` accepts an optional `storageKey` prop and an `onTabChange` callback.
  2. When `storageKey` is provided, the component registers a `useLocation` + `useEffect` that watches `location.pathname`, determines which tab definition's `to` path matches, and writes the corresponding `value` to localStorage via `setTabPreference(storageKey, value)`.
  3. Additionally, each tab's `<Link>` receives an `onClick` that eagerly calls `setTabPreference` for immediate persistence before navigation completes.
- **States / transitions:** localStorage is the side-effect; component state is not affected.
- **Hotspots:** The `useEffect` must guard against writing when navigating away from the tab bar's parent route (same guard as current `devicePrefix` check in `device-detail-header.tsx:29`). The primitive accepts a `basePath` prop for this guard. Path matching uses each tab definition's `value` slug (e.g., `'edit'`, `'logs'`, `'coredumps'`) rather than the `to` route template, because `to` contains unresolved param placeholders (e.g., `$deviceId`). The effect iterates tab definitions and checks `location.pathname.startsWith(basePath + definition.value)` to determine the active tab. This also correctly handles nested routes (e.g., `/devices/42/coredumps/7` matches the `coredumps` tab).
- **Evidence:** `src/components/devices/device-detail-header.tsx:26-34` — current persistence effect. `src/routes/devices/$deviceId/coredumps/$coredumpId.tsx` — nested child route that must still match the coredumps tab.

---

- **Flow:** Index-route restore (redirect to last tab)
- **Steps:**
  1. Index route component calls `useRestoreTab({ storageKey, validValues, defaultValue, toPath })`.
  2. The hook calls `getTabPreference(storageKey, validValues, defaultValue)` to read localStorage.
  3. It calls `useNavigate` and issues a `navigate({ ...toPath(tab), replace: true })` inside a `useEffect`.
  4. Returns `void` — the hook is a pure side-effect. The consumer component separately returns `null` as its JSX.
- **States / transitions:** Single render, immediate redirect. No intermediate UI.
- **Hotspots:** Must use `replace: true` to avoid polluting browser history.
- **Evidence:** `src/routes/devices/$deviceId/index.tsx:11-24`.

---

## 6) Derived State & Invariants

- **Derived value:** Active tab identity (for persistence writes)
  - **Source:** `location.pathname` from `useLocation()`, matched against the tab definitions' `value` slugs (not `to` templates, which contain unresolved param placeholders).
  - **Writes / cleanup:** Writes to `localStorage` under the configured `storageKey`. No cleanup needed — values persist indefinitely.
  - **Guards:** The `useEffect` only writes when the current pathname starts with `basePath` to avoid clobbering the preference on navigation away from the tabbed view.
  - **Invariant:** The persisted value must always be one of the declared tab `value` strings. `getTabPreference` validates against `validValues` and falls back to `defaultValue`.
  - **Evidence:** `src/components/devices/device-detail-header.tsx:28-34`, `src/lib/utils/device-tab-preference.ts:9-11`.

---

- **Derived value:** Restored tab on index visit
  - **Source:** `localStorage.getItem(storageKey)` validated against `validValues`.
  - **Writes / cleanup:** Triggers a `navigate()` with `replace: true`; no persistent write.
  - **Guards:** Validation ensures only known tab values produce a redirect; unknown values fall back to `defaultValue`.
  - **Invariant:** The redirect must always produce a valid child route URL. The `toPath` callback is consumer-defined and produces the route descriptor.
  - **Evidence:** `src/routes/devices/$deviceId/index.tsx:14`.

---

- **Derived value:** Coredump badge count
  - **Source:** `useCoredumps(device.id)` in the consumer (`DeviceDetailHeader`), not in the primitive.
  - **Writes / cleanup:** None — read-only derived from server state via React Query.
  - **Guards:** The badge only renders when `coredumps.length > 0`.
  - **Invariant:** The count must reflect the current query cache. Since `useCoredumps` is called in the consumer, React Query handles staleness.
  - **Evidence:** `src/components/devices/device-detail-header.tsx:18,133-139`.

---

## 7) State Consistency & Async Coordination

- **Source of truth:** TanStack Router URL for active tab; localStorage for persisted preference.
- **Coordination:** The `RoutedTabs` component has no internal state for which tab is active — it relies entirely on router `Link` active matching. Persistence is a side-effect that shadows the URL state into localStorage.
- **Async safeguards:** None needed — `localStorage` is synchronous, and the `useEffect` for persistence runs after navigation settles. The `useRestoreTab` hook's navigate call is guarded by `useEffect` dependency array to fire only once per mount.
- **Instrumentation:** The existing `data-testid` attributes on the tab `<nav>` and individual `<Link>` elements provide Playwright hooks. No new instrumentation events are needed since the tab bar does not involve loading states or mutations.
- **Evidence:** `src/components/devices/device-detail-header.tsx:26-34` (persistence effect), `src/routes/devices/$deviceId/index.tsx:16-22` (restore effect).

---

## 8) Errors & Edge Cases

- **Failure:** localStorage is unavailable (private browsing, storage quota exceeded)
  - **Surface:** `RoutedTabs` persistence write, `useRestoreTab` read
  - **Handling:** Both `getTabPreference` and `setTabPreference` wrap calls in try/catch and silently degrade — `getTabPreference` returns `defaultValue`, `setTabPreference` is a no-op. This matches the current behavior.
  - **Guardrails:** Existing pattern in `device-tab-preference.ts:8-16,20-24`.
  - **Evidence:** `src/lib/utils/device-tab-preference.ts:8-16`.

---

- **Failure:** Corrupted or unknown value in localStorage
  - **Surface:** `useRestoreTab` on index route mount
  - **Handling:** `getTabPreference` validates against `validValues` array and returns `defaultValue` if the stored value is not recognized.
  - **Guardrails:** Validation at read time prevents redirect to invalid routes.
  - **Evidence:** `src/lib/utils/device-tab-preference.ts:10-11`.

---

- **Failure:** Consumer provides empty tabs array
  - **Surface:** `RoutedTabs` render
  - **Handling:** Render an empty `<nav>` — no crash. The component does not require a minimum tab count.
  - **Guardrails:** TypeScript type requires `RoutedTabDefinition[]`; an empty array is valid but unusual.
  - **Evidence:** N/A — defensive coding in the new primitive.

---

## 9) Observability / Instrumentation

- **Signal:** `data-testid` on tab nav container
  - **Type:** DOM attribute
  - **Trigger:** Always present on the `<nav>` element. Value is `${testIdPrefix}.tabs` (e.g., `devices.detail.tabs`).
  - **Labels / fields:** `testIdPrefix` configured by consumer.
  - **Consumer:** Playwright page object `DevicesPage.detailTabs`.
  - **Evidence:** `src/components/devices/device-detail-header.tsx:111`.

---

- **Signal:** `data-testid` on individual tab links
  - **Type:** DOM attribute
  - **Trigger:** Always present on each `<Link>`. Value is the tab definition's `testId`, or `${testIdPrefix}.tab.${value}` if `testId` is omitted.
  - **Labels / fields:** Per-tab, configurable.
  - **Consumer:** Playwright page object `DevicesPage.tabConfiguration`, `.tabLogs`, `.tabCoredumps`.
  - **Evidence:** `src/components/devices/device-detail-header.tsx:169`.

---

No new instrumentation events (ListLoading, Form tracking) are needed — the tab bar is a navigation primitive, not a data-loading or mutation flow.

---

## 10) Lifecycle & Background Work

- **Hook / effect:** Persistence `useEffect` inside `RoutedTabs`
  - **Trigger cadence:** On every `location.pathname` change while the component is mounted.
  - **Responsibilities:** Determines which tab matches the current path and writes to localStorage.
  - **Cleanup:** Standard effect cleanup — no subscriptions or timers to dispose.
  - **Evidence:** `src/components/devices/device-detail-header.tsx:28-34`.

---

- **Hook / effect:** `useRestoreTab` navigate effect
  - **Trigger cadence:** Once on mount (deps: `navigate`, params, tab value).
  - **Responsibilities:** Reads persisted preference, calls `navigate` with `replace: true`.
  - **Cleanup:** None needed — single fire-and-forget navigation.
  - **Evidence:** `src/routes/devices/$deviceId/index.tsx:16-22`.

---

## 11) Security & Permissions

Not applicable. The tab bar is a UI navigation primitive with no authentication, authorization, or sensitive data concerns. localStorage preference values are non-sensitive (tab slug strings).

---

## 12) UX / UI Impact

- **Entry point:** Device detail view (`/devices/$deviceId/*`)
- **Change:** No visual change. The tab bar renders identically — same HTML structure, same CSS classes, same underline indicator, same badge. The refactoring is purely structural.
- **User interaction:** Identical to current behavior. Clicking a tab navigates to the child route and persists the preference. Visiting a bare device URL restores the last-used tab.
- **Dependencies:** TanStack Router `Link` component, `useLocation`, `useNavigate`.
- **Evidence:** `src/components/devices/device-detail-header.tsx:110-141`.

---

## 13) Deterministic Test Plan

- **Surface:** Device tab navigation and persistence
- **Scenarios:**
  - Given a device exists, When the user visits `/devices/{id}` with no stored preference, Then the URL redirects to `/devices/{id}/edit` and the configuration tab has `aria-current="page"`. (Existing: `devices-tabs.spec.ts:5-19`)
  - Given a device exists, When the user clicks each tab in sequence, Then the URL updates and the clicked tab shows `aria-current="page"`. (Existing: `devices-tabs.spec.ts:21-46`)
  - Given the user visited the logs tab on device A, When the user navigates to device B via the list, Then device B opens on the logs tab. (Existing: `devices-tabs.spec.ts:121-146`)
  - Given a device has coredumps, When the detail header renders, Then the coredumps tab label includes the count. (Existing: `devices-tabs.spec.ts:89-100`)
  - Given the user is in new-device or duplicate mode, When the page renders, Then the tab bar and header are not visible. (Existing: `devices-tabs.spec.ts:48-68`)
  - Given a device exists, When the user deep-links to each tab URL, Then the corresponding tab is active. (Existing: `devices-tabs.spec.ts:71-87`)
- **Instrumentation / hooks:** `data-testid="devices.detail.tabs"`, `data-testid="devices.detail.tab.configuration"`, `data-testid="devices.detail.tab.logs"`, `data-testid="devices.detail.tab.coredumps"`.
- **Gaps:** No new scenarios needed. All existing specs in `devices-tabs.spec.ts` cover the required behaviors. The refactoring must keep these tests green with no locator changes.
- **Evidence:** `tests/e2e/devices/devices-tabs.spec.ts:1-174`, `tests/e2e/devices/DevicesPage.ts:36-53`.

---

## 14) Implementation Slices

- **Slice 1:** Create `RoutedTabs` primitive
  - **Goal:** Ship the reusable component, persistence utilities, and `useRestoreTab` hook with inline JSDoc.
  - **Touches:** `src/components/primitives/routed-tabs.tsx` (new), `src/components/primitives/index.ts` (add exports).
  - **Dependencies:** None. Can be built and reviewed independently.

---

- **Slice 2:** Refactor device domain to consume the primitive
  - **Goal:** Remove device-specific tab/persistence code and delegate to `RoutedTabs`.
  - **Touches:** `src/components/devices/device-detail-header.tsx`, `src/routes/devices/$deviceId/index.tsx`, `src/hooks/use-device-form.ts`, `src/lib/utils/device-tab-preference.ts` (delete).
  - **Dependencies:** Slice 1 must be merged or in the same PR.

---

- **Slice 3:** Verify Playwright tests
  - **Goal:** Confirm all existing specs pass green. Update `DevicesPage.ts` or spec files if any test IDs changed.
  - **Touches:** `tests/e2e/devices/DevicesPage.ts`, `tests/e2e/devices/devices-tabs.spec.ts` (update `localStorage.removeItem` key if it changed — plan preserves the same key, so likely no change).
  - **Dependencies:** Slice 2 complete.

These slices are small enough to ship as a single PR.

---

## 15) Risks & Open Questions

- **Risk:** Test ID drift — if the primitive generates test IDs differently than the hardcoded ones in the current header, Playwright locators break.
  - **Impact:** CI failures on all device tab specs.
  - **Mitigation:** The device consumer will pass explicit `testId` values matching the current IDs (`devices.detail.tab.configuration`, etc.), and the `testIdPrefix` will produce `devices.detail.tabs` for the nav container. Verify by running `pnpm playwright test tests/e2e/devices/devices-tabs.spec.ts` before merging.

---

- **Risk:** `use-device-form.ts` calls `setDeviceTabPreference('logs')` programmatically outside the tab bar. If this import is missed during refactoring, the post-save redirect to logs breaks.
  - **Impact:** After saving a device, the user lands on the wrong tab next time.
  - **Mitigation:** The deletion of `device-tab-preference.ts` will cause a TypeScript compilation error at the import site, making this impossible to miss. The fix is to import `setTabPreference` from the primitive and `DEVICE_TAB_STORAGE_KEY` from `device-detail-header.tsx`, then call `setTabPreference(DEVICE_TAB_STORAGE_KEY, 'logs')`.

---

- **Risk:** The persistence `useEffect` path-matching logic is currently device-specific (`location.pathname.includes('/logs')`). The primitive needs a generic approach that also handles nested routes (e.g., `/devices/42/coredumps/7` must still match the `coredumps` tab).
  - **Impact:** Incorrect tab value written to localStorage.
  - **Mitigation:** The primitive matches against each tab definition's `value` slug, not the `to` route template (which contains unresolved param placeholders). The `useEffect` iterates tab definitions and checks `location.pathname.startsWith(basePath + definition.value)` to find the active tab. This handles both direct tab URLs and nested child routes. The `onClick` handler on each `<Link>` provides eager persistence for click-based navigation; the `useEffect` serves as a fallback for direct-URL navigation and back-button usage.

---

## 16) Confidence

Confidence: High — the extraction is mechanical (move code into a reusable wrapper), the existing Playwright suite fully covers the behavior, and no API or data model changes are involved.
