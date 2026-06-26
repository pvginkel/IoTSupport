# Core Dump Support -- Code Review

## 1) Summary & Decision

**Readiness**

The change delivers slices 1-3 of the plan: the `use-coredumps.ts` data layer hook, `lastCoredumpAt` on the device list table, the `CoredumpTable` component on the device editor, and the `CoredumpDetail` page at `/devices/$deviceId/coredumps/$coredumpId`. The code is well-structured, follows existing codebase patterns closely, passes TypeScript strict mode, and includes the instrumentation hooks needed for Playwright. However, the change ships zero Playwright tests, zero factory extensions, and zero page object updates -- all of which the plan's Slice 4 designates as part of the same feature. Per CLAUDE.md, "a UI feature is incomplete without automated verification" and instrumentation + tests must ship in the same slice.

**Decision**

`GO-WITH-CONDITIONS` -- The UI implementation is solid and consistent with project conventions. The conditions are: (1) Playwright specs, factory, and page object must be delivered before the feature is considered complete, and (2) the minor findings below should be addressed.

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- Plan Section 2 "use-coredumps.ts" -> `src/hooks/use-coredumps.ts:1-163` -- Custom hook wrapping generated API hooks with camelCase domain models, toast integration, and cache invalidation. Matches plan.
- Plan Section 2 "use-devices.ts" -> `src/hooks/use-devices.ts:26,63,74` -- `lastCoredumpAt` added to `DeviceSummary` interface and `transformDeviceSummary`. Matches plan.
- Plan Section 2 "sort-preferences.ts" -> `src/lib/utils/sort-preferences.ts:4,21` -- `lastCoredumpAt` added to column union and validation array. Matches plan.
- Plan Section 2 "device-list-table.tsx" -> `src/components/devices/device-list-table.tsx:125,158-162` -- New sortable column with `toLocaleString()` and em-dash fallback. Matches plan.
- Plan Section 2 "device-editor.tsx" -> `src/components/devices/device-editor.tsx:15,567-570` -- `CoredumpTable` imported and rendered below `DeviceLogsViewer` in edit mode. Matches plan.
- Plan Section 2 "coredump-table.tsx" -> `src/components/devices/coredump-table.tsx:1-200` -- Table component with loading, error, empty states, row click navigation, download link, delete confirmation. Matches plan.
- Plan Section 2 "coredump-detail.tsx" -> `src/components/devices/coredump-detail.tsx:1-117` -- Metadata display, download link, read-only Monaco editor. Matches plan.
- Plan Section 2 "$coredumpId.tsx" -> `src/routes/devices/$deviceId/coredumps/$coredumpId.tsx:1-57` -- Route with ID validation, loading, error states, renders `CoredumpDetail`. Matches plan.
- Plan Section 9 "list_loading scope coredumps.list" -> `src/components/devices/coredump-table.tsx:34-40` -- `useListLoadingInstrumentation` with correct scope. Matches plan.
- Plan Section 9 "form events CoredumpDelete" -> `src/components/devices/coredump-table.tsx:29-31` -- `useFormInstrumentation` with formId `CoredumpDelete`. Matches plan.
- Plan Section 9 "data-testid attributes" -> `src/components/devices/coredump-table.tsx:76,80,92,96,106,113,123,143,169,181` and `src/components/devices/coredump-detail.tsx:20,26,38,51,77,98` -- All planned test selectors are present.

**Gaps / deviations**

- Plan Section 1a requirement: "Last Core Dump column shows '---' when null" -- Implementation uses the em-dash character (`'---'` in plan vs `'---'` em-dash in code at `src/components/devices/device-list-table.tsx:161`). This is an intentional deviation that matches the existing codebase convention. Not a defect.
- Plan Section 14 "Slice 4: Playwright tests and factory" -- `tests/api/factories/devices.ts` was not extended, `tests/e2e/devices/DevicesPage.ts` was not updated, `tests/e2e/devices/devices-coredumps.spec.ts` does not exist. This is the largest gap; the plan explicitly designates Slice 4 as a separate slice with a backend dependency, so deferral may be intentional but must be tracked.

---

## 3) Correctness -- Findings (ranked)

- Title: `Major -- No Playwright tests shipped with the UI change`
- Evidence: No files matching `tests/**/*coredump*` exist. Plan Section 14 defines Slice 4 for test coverage; CLAUDE.md states "Ship instrumentation changes and matching Playwright coverage in the same slice."
- Impact: The feature has zero automated verification. Regressions will go undetected. The instrumentation hooks in `coredump-table.tsx:29-40` cannot be validated without corresponding specs.
- Fix: Implement Slice 4 before merging: create `tests/e2e/devices/devices-coredumps.spec.ts`, extend `DevicesFactory` with coredump methods, and add coredump locators to `DevicesPage.ts`.
- Confidence: High

---

- Title: `Major -- Delete mutation onSuccess/onError callbacks may not fire for instrumentation tracking`
- Evidence: `src/hooks/use-coredumps.ts:119-130` configures `onSuccess`/`onError` at the `useMutation` hook level. `src/components/devices/coredump-table.tsx:59-69` passes `onSuccess`/`onError` at the `mutate()` call site for instrumentation tracking. In TanStack Query v5, both hook-level and call-site callbacks fire on success/error. However, there is a subtle issue: if the hook-level `onSuccess` throws (e.g., `showSuccess` or `invalidateQueries` encounters an error), the call-site `onSuccess` may not execute, which would silently drop the `trackSuccess` instrumentation event.
- Impact: In rare error conditions during cache invalidation, `trackSuccess` might not fire, causing Playwright tests to hang waiting for the form success event.
- Fix: Move the instrumentation tracking (`trackSubmit`/`trackSuccess`/`trackError`) into the hook itself alongside the toast calls, or wrap the hook-level `onSuccess` in a try-catch to ensure call-site callbacks always execute. The safer approach is to emit instrumentation events from within `useDeleteCoredump` directly, similar to how `device-editor.tsx:286-309` handles form instrumentation inline with the mutation call.
- Confidence: Medium

---

- Title: `Minor -- formatFileSize utility is co-located with hooks instead of utils`
- Evidence: `src/hooks/use-coredumps.ts:155-163` -- `formatFileSize` is a pure utility function exported from a hooks file.
- Impact: Other components needing file size formatting would need to import from a hooks file, breaking the project's domain separation (pure functions belong in `src/lib/utils/`).
- Fix: Move `formatFileSize` to `src/lib/utils/format.ts` or a similar utility module and re-export from the hooks file if needed for backward compatibility.
- Confidence: High

---

- Title: `Minor -- ConfirmDialog rendered in empty state branch will never trigger`
- Evidence: `src/components/devices/coredump-table.tsx:114-117` -- A `ConfirmDialog` is rendered in the empty state branch (when `sortedCoredumps.length === 0`). Since there are no rows to delete, the confirm dialog can never be opened from this state.
- Impact: Unnecessary DOM node. No functional impact, but it adds confusion about intent.
- Fix: Remove the `ConfirmDialog` from the empty state branch. It is already rendered in the populated table branch at line 194-197.
- Confidence: High

---

## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: `useDeleteCoredump` mutate/mutateAsync wrappers
- Evidence: `src/hooks/use-coredumps.ts:132-148` -- The hook wraps `mutation.mutate` and `mutation.mutateAsync` to translate `{ deviceId, coredumpId }` to `{ path: { device_id, coredump_id } }`. This is consistent with the pattern in `src/hooks/use-devices.ts:246-257`.
- Suggested refactor: None needed. The wrapper pattern is consistent with the codebase.
- Payoff: N/A -- already aligned with project conventions.

---

- Hotspot: Inline transform functions duplicating field mapping
- Evidence: `src/hooks/use-coredumps.ts:31-55,58-77` -- `transformCoredumpSummary` and `transformCoredumpDetail` share 10 fields; the detail variant uses spread from the summary transform and adds two fields. This is a clean approach.
- Suggested refactor: None. The `...transformCoredumpSummary(apiCoredump)` reuse at line 73 is exactly the right pattern.
- Payoff: N/A -- already well-factored.

---

## 5) Style & Consistency

- Pattern: Download link anchor styling
- Evidence: `src/components/devices/coredump-table.tsx:164-173` -- The download link uses inline utility classes to mimic button styling (`inline-flex items-center justify-center rounded-md text-sm font-medium h-8 w-8`). Compare with `src/components/devices/coredump-detail.tsx:35-44` which wraps an anchor around a `<Button variant="outline">`.
- Impact: Inconsistent interaction affordance between the table download action (icon-only, custom classes) and the detail page download action (full button with text).
- Recommendation: Both approaches are reasonable given their contexts (compact table row vs spacious header). No change required, but documenting the rationale via a brief comment in the table version would help future maintainers.

---

- Pattern: Consistent error type checking
- Evidence: `src/hooks/use-coredumps.ts:127` uses `error instanceof Error ? error.message : 'Failed to delete core dump'`. `src/components/devices/coredump-table.tsx:66` uses `err instanceof Error ? err.message : 'Unknown error'`. The fallback messages differ.
- Impact: Minor inconsistency in error messages shown to the user if the same error is handled at both levels.
- Recommendation: The hook-level `onError` handles the toast; the call-site `onError` handles instrumentation. They serve different purposes, so different fallback text is acceptable. No change needed.

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: Core dumps table on device editor page
- Scenarios:
  - Given a device with no coredumps, When the user navigates to the device editor, Then the coredumps table section is visible with the empty state message "No core dumps recorded for this device"
  - Given a device with coredumps, When the user navigates to the device editor, Then the coredumps table displays rows with Uploaded At, Firmware, Size, Status, and Actions columns
  - Given a device with coredumps, When the user clicks a coredump row, Then the browser navigates to `/devices/{deviceId}/coredumps/{coredumpId}`
  - Given a device with coredumps, When the user clicks the Delete button on a row, Then a confirmation dialog appears; confirming deletes the coredump and refreshes the table
  - Given a device with coredumps, When the user clicks the Download link, Then the link href points to the correct download endpoint
- Hooks: `coredumps.table` (data-testid), `coredumps.list` (list_loading scope), `coredumps.delete.confirm-dialog` (data-testid), `CoredumpDelete` form events
- Gaps: **All scenarios are untested.** No `tests/e2e/devices/devices-coredumps.spec.ts` exists. No `DevicesFactory` coredump methods exist. No `DevicesPage` coredump locators exist.
- Evidence: Zero files match `tests/**/*coredump*`.

---

- Surface: Core dump detail page
- Scenarios:
  - Given a coredump with parsed output, When the user navigates to the detail page, Then the Monaco editor displays the parsed output in read-only plain text mode
  - Given a coredump with null parsed output, When the user navigates to the detail page, Then a message indicates parsed output is not available
  - Given the detail page is loaded, Then the metadata section shows filename, chip, firmware version, size, parse status, uploaded at, and parsed at
  - Given the detail page is loaded, Then a download link is present with the correct href
  - Given the detail page is loaded, Then a back link navigates to the device editor
- Hooks: `coredumps.detail` (data-testid), `coredumps.detail.editor` (data-testid), `coredumps.detail.download` (data-testid)
- Gaps: **All scenarios are untested.**
- Evidence: Zero files match `tests/**/*coredump*`.

---

- Surface: Devices list -- Last Core Dump column
- Scenarios:
  - Given devices exist, When the user views the devices list, Then the "Last Core Dump" column is visible with formatted datetimes or em-dash for null values
  - Given the devices list, When the user clicks the "Last Core Dump" column header, Then the table sorts by that column
- Hooks: `devices.list.header.lastCoredumpAt` (data-testid from `renderSortHeader`)
- Gaps: **Untested.** The existing `devices-crud.spec.ts` does not cover the new column.
- Evidence: Grep of `tests/` for `coredump` returns no matches.

---

## 7) Adversarial Sweep (must attempt >= 3 credible failures or justify none)

- Title: `Minor -- Race between delete mutation and row click navigation`
- Evidence: `src/components/devices/coredump-table.tsx:177-179` -- The delete button's `onClick` calls `e.stopPropagation()` before `handleDelete`. If the user double-clicks rapidly, the confirmation dialog from `useConfirm` is promise-based and will serialize the two clicks (the second `confirm()` call opens a new dialog only after the first resolves). However, if a user clicks Delete and then quickly clicks the row before the dialog opens, `stopPropagation` on the button prevents row navigation. This path is safe.
- Impact: No real risk; the `useConfirm` promise serialization and `stopPropagation` guard this correctly.
- Fix: None needed.
- Confidence: High

---

- Title: `Minor -- Stale closure risk in handleDelete callback`
- Evidence: `src/components/devices/coredump-table.tsx:49-71` -- `handleDelete` is wrapped in `useCallback` with `[confirm, deleteCoredump, deviceId, trackSubmit, trackSuccess, trackError]` as dependencies. The `deleteCoredump` object is returned from `useDeleteCoredump()` which returns a new object on every render (due to the spread `...mutation` and new `mutate`/`mutateAsync` functions). This means `handleDelete` will be recreated on every render.
- Impact: No functional issue since the callback always captures the latest values. The `useCallback` is effectively a no-op because `deleteCoredump` is a new reference each render. Minor performance concern on re-renders.
- Fix: Consider memoizing the `mutate` function returned from `useDeleteCoredump` using `useCallback` inside the hook, or accept the re-creation cost (negligible for this component).
- Confidence: Medium

---

- Title: `Minor -- Cache invalidation breadth after delete`
- Evidence: `src/hooks/use-coredumps.ts:122-123` -- After deleting a coredump, the hook invalidates `['getDevicesCoredumpsByDeviceId']` (matches all devices' coredump lists) and `['getDevices']`. This is broader than necessary -- it will refetch coredump lists for devices the user is not currently viewing.
- Impact: Negligible performance impact since TanStack Query only refetches active observers. Inactive query data is simply marked stale. No functional issue.
- Fix: Could scope to `['getDevicesCoredumpsByDeviceId', { path: { device_id: ... } }]` for the specific device, but this would require passing `deviceId` into the hook. The broad invalidation follows the pattern in `src/hooks/use-devices.ts:237` and is acceptable.
- Confidence: High

---

## 8) Invariants Checklist (table)

- Invariant: Coredump list always reflects server state after mutations
  - Where enforced: `src/hooks/use-coredumps.ts:122` -- `queryClient.invalidateQueries({ queryKey: ['getDevicesCoredumpsByDeviceId'] })` fires on successful delete
  - Failure mode: If invalidation is skipped (e.g., `onSuccess` throws before reaching the invalidation call), the table shows deleted coredumps
  - Protection: The generated hook at `src/lib/api/generated/hooks.ts:407-410` also has a global `invalidateQueries()` call, but it is overridden by the `...options` spread. The custom hook's scoped invalidation is the sole guard.
  - Evidence: `src/hooks/use-coredumps.ts:119-130`

---

- Invariant: `lastCoredumpAt` on device list updates after coredump deletion
  - Where enforced: `src/hooks/use-coredumps.ts:123` -- `queryClient.invalidateQueries({ queryKey: ['getDevices'] })` fires on successful delete
  - Failure mode: If the device list is not refetched, the "Last Core Dump" column shows stale data until next navigation
  - Protection: The invalidation triggers an automatic refetch for any active `useGetDevices` observer
  - Evidence: `src/hooks/use-coredumps.ts:123`, `src/components/devices/device-list-table.tsx:158-162`

---

- Invariant: Route params are always valid integers before API calls
  - Where enforced: `src/routes/devices/$deviceId/coredumps/$coredumpId.tsx:12-14` -- `parseInt` with `isNaN` check, query `enabled` flag
  - Failure mode: NaN device/coredump ID causes API error; guarded by `enabled: deviceId !== undefined && coredumpId !== undefined` in the hook
  - Protection: Explicit `!validIds` branch renders error UI at line 22-29
  - Evidence: `src/routes/devices/$deviceId/coredumps/$coredumpId.tsx:12-21`

---

## 9) Questions / Needs-Info

- Question: Is Slice 4 (Playwright tests) intentionally deferred or was it expected to be part of this change?
- Why it matters: CLAUDE.md mandates that instrumentation and tests ship together. If deferred, the plan's risk section (Section 15) notes a backend dependency for coredump seeding that may block the factory.
- Desired answer: Confirmation that Slice 4 is tracked as a follow-up with a clear timeline, or agreement that it should be included before merge.

---

- Question: Does the backend's `POST /api/iot/coredump` endpoint support seeding coredumps from the test harness, or is a dedicated testing endpoint needed?
- Why it matters: The Playwright factory for coredumps depends on the ability to create test data programmatically. The plan identifies this as a risk.
- Desired answer: Backend confirmation of the seeding mechanism and any required headers (device auth, binary payload format).

---

## 10) Risks & Mitigations (top 3)

- Risk: Feature ships without automated test coverage, violating the project's "instrumentation + tests in the same slice" policy.
- Mitigation: Implement Slice 4 (factory, page object, spec) before merge, or create a tracked follow-up with explicit acceptance criteria and timeline.
- Evidence: Zero files matching `tests/**/*coredump*`; CLAUDE.md "UI & Playwright Coupling" section.

---

- Risk: `trackSuccess`/`trackError` instrumentation events may not fire reliably due to the two-layer callback architecture (hook-level + call-site).
- Mitigation: Consolidate instrumentation into the hook or add defensive try-catch around hook-level callbacks. Validate with a Playwright test that asserts on the `CoredumpDelete` form success event after a delete.
- Evidence: `src/hooks/use-coredumps.ts:119-130`, `src/components/devices/coredump-table.tsx:57-69`

---

- Risk: Backend coredump seeding endpoint may not be available for the Playwright factory, blocking automated test coverage indefinitely.
- Mitigation: Verify backend support for `POST /api/iot/coredump` from the test harness. If not feasible, request a `POST /api/testing/coredumps` endpoint.
- Evidence: Plan Section 15 risk item 1.

---

## 11) Confidence

Confidence: High -- The UI implementation is clean, follows project patterns faithfully, and passes TypeScript strict mode. The sole blocker to full readiness is the absence of Playwright tests, which is a clearly scoped follow-up deliverable. The code can ship with confidence once test coverage is in place.
