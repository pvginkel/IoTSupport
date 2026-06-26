# Core Dump Support -- Plan Review

## 1) Summary & Decision

**Readiness**

The plan is thorough, well-researched, and closely aligned with the codebase's established patterns. It covers all required sections from the plan template, provides line-range evidence for every claim, and proposes a sensible implementation strategy across four slices. The API surface is already generated and the data model is accurately documented. Two issues were identified during the initial review -- missing form instrumentation for the delete mutation and an undocumented routing nuance for the detail page -- and both have been addressed in the updated plan.

**Decision**

`GO` -- All conditions from the initial review have been resolved. The routing clarification now references the working `$deviceId/duplicate.tsx` precedent (`plan.md:120`), and form instrumentation for the delete mutation has been added to sections 2, 5, 9, and 13 (`plan.md:83-84,272-277,430-435,510`). The remaining open item (Playwright factory backend dependency) is correctly scoped as a coordination item that does not block frontend implementation.

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/commands/plan_feature.md` -- Pass -- All 17 sections (0-16) are present and follow the prescribed templates. The User Requirements Checklist at `plan.md:63-76` is included as required.
- `docs/product_brief.md` -- Pass -- The plan extends the device editor and device list table consistent with the existing device management architecture (`plan.md:112-114`). No conflict with core product functionality.
- `docs/contribute/architecture/application_overview.md` -- Pass -- The plan correctly uses the domain-driven folder layout (`src/components/devices/`, `src/hooks/`), generated API hooks, custom hooks with camelCase transformation, and TanStack Query for state management (`plan.md:82-84`).
- `docs/contribute/testing/playwright_developer_guide.md` -- Pass -- The test plan proposes factory-based data seeding (`plan.md:130-132`), `data-testid` attributes following the `feature.section.element` naming scheme (`plan.md:403-426`), `useListLoadingInstrumentation` for deterministic waits (`plan.md:394-399`), and `trackForm*` events for the delete mutation (`plan.md:430-435`). No route interception is proposed.

**Fit with codebase**

- `DeviceSummary` / `transformDeviceSummary` (`src/hooks/use-devices.ts:17-26,53-73`) -- `plan.md:88-90` -- Confirmed fit. The `last_coredump_at` field exists in the API response (`src/lib/api/generated/types.ts:1092-1096`) but is not yet mapped. The plan correctly identifies this gap.
- `SortPreference` column union (`src/lib/utils/sort-preferences.ts:4`) -- `plan.md:94-96` -- Confirmed fit. Adding `lastCoredumpAt` to the union and validation array is straightforward.
- `DeviceListTable` (`src/components/devices/device-list-table.tsx:118-125`) -- `plan.md:100-102` -- Confirmed fit. Adding a new `renderSortHeader` call and table cell is consistent with the existing pattern. The plan correctly places the column between "OTA Status" and "Actions" (`plan.md:494`).
- `DeviceEditor` (`src/components/devices/device-editor.tsx:558-564`) -- `plan.md:112-114` -- Confirmed fit. The `DeviceLogsViewer` is the last content element in the editor's scrollable area; placing the coredump table below it follows the natural content flow.
- `useListLoadingInstrumentation` (`src/lib/test/query-instrumentation.ts:146-236`) -- `plan.md:394-399` -- Confirmed fit. The hook's signature matches the plan's proposed usage with `scope: 'coredumps.list'`.
- `useFormInstrumentation` (`src/lib/test/form-instrumentation.ts`) -- `plan.md:430-435` -- Confirmed fit. The plan now includes `trackFormSubmit`/`trackFormSuccess`/`trackFormError` for the delete mutation, consistent with `CLAUDE.md` Working Guidelines item 5.
- `DevicesFactory` (`tests/api/factories/devices.ts:26-183`) -- `plan.md:130-132` -- Confirmed fit. The factory class pattern supports extension with new methods for coredump seeding.
- TanStack Router file-based routing (`src/routes/devices/$deviceId/duplicate.tsx`) -- `plan.md:118-120` -- The plan now acknowledges the routing nuance and references the working `$deviceId/duplicate.tsx` precedent. Verified that `src/routeTree.gen.ts:62-67` shows the duplicate route as a child of `DevicesDeviceIdRoute` with the same nesting pattern the coredump detail route will use.

## 3) Open Questions & Ambiguities

- Question: Does the backend `POST /api/iot/coredump` endpoint accept requests from the Playwright test harness, or does it require device-level authentication that the factory cannot provide?
- Why it matters: This is the sole blocker for Slice 4 (Playwright tests). Without a way to seed coredumps, all coredump table and detail page specs are deferred (`plan.md:511,524`).
- Needed answer: Check if the backend has a `POST /api/testing/coredumps` endpoint or if the IoT endpoint accepts standard API authentication. The plan already proposes this investigation (`plan.md:572-574`) but should attempt to resolve it before Slice 4 begins.

- Question: Should the `CoredumpSummary` model include `updated_at`?
- Why it matters: The plan defines `CoredumpSummary` without `updatedAt` (`plan.md:153-164`), which matches the API's `CoredumpSummarySchema` (`src/lib/api/generated/types.ts:864-918`). The API summary schema does indeed omit `updated_at`, so the plan is correct.
- Needed answer: None -- resolved by research. The API summary schema does not include `updated_at`.

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Core dumps table on device editor page
- Scenarios:
  - Given a device with no coredumps, When the user navigates to the device editor, Then the coredumps table section shows the empty state message (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given a device with seeded coredumps, When the user navigates to the device editor, Then rows display with Uploaded At, Firmware, Size, Status, and Actions columns (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given a device with coredumps, When the user clicks a coredump row, Then navigation goes to `/devices/{deviceId}/coredumps/{coredumpId}` (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given a device with coredumps, When the user clicks Delete and confirms, Then the coredump is removed and the table refreshes (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given a device with coredumps, When the user clicks the Download link, Then the link href points to the correct download endpoint (`tests/e2e/devices/devices-coredumps.spec.ts`)
- Instrumentation: `coredumps.table` (data-testid), `coredumps.list` (list_loading scope), `coredumps.delete.confirm-dialog` (data-testid), `CoredumpDelete` form events, `coredumps.table.row` (data-testid), `coredumps.table.row.download` (data-testid), `coredumps.table.row.delete` (data-testid)
- Backend hooks: Coredump factory methods (`createCoredump`, `listCoredumps`, `deleteCoredump`) in `tests/api/factories/devices.ts`
- Gaps: The factory's ability to seed coredumps depends on backend endpoint availability. The plan correctly identifies this as a risk (`plan.md:511,572-574`).
- Evidence: `plan.md:503-512`

- Behavior: Core dump detail page
- Scenarios:
  - Given a coredump with parsed output, When the user navigates to the detail page, Then the Monaco editor displays parsed output in read-only plain text mode (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given a coredump with null parsed output, When the user navigates to the detail page, Then a message indicates parsed output is not available (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given the detail page is loaded, Then metadata section shows filename, chip, firmware version, size, parse status, uploaded at, and parsed at (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given the detail page is loaded, Then a download link is present with the correct href (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given the detail page is loaded, Then a back link navigates to the device editor (`tests/e2e/devices/devices-coredumps.spec.ts`)
- Instrumentation: `coredumps.detail` (data-testid), `coredumps.detail.editor` (data-testid), `coredumps.detail.download` (data-testid), `coredumps.detail.metadata` (data-testid), `coredumps.detail.error` (data-testid)
- Backend hooks: Same coredump factory dependency as above.
- Gaps: Same factory dependency. Additionally, testing both parsed and unparsed coredumps requires the factory to support creating coredumps in different parse states.
- Evidence: `plan.md:516-525`

- Behavior: Devices list -- Last Core Dump column
- Scenarios:
  - Given devices with `last_coredump_at` values, When the user views the devices list, Then the "Last Core Dump" column displays formatted datetimes (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given a device with null `last_coredump_at`, When the user views the devices list, Then the column shows "---" (`tests/e2e/devices/devices-coredumps.spec.ts`)
  - Given the devices list, When the user clicks the "Last Core Dump" column header, Then the table sorts by that column (`tests/e2e/devices/devices-coredumps.spec.ts`)
- Instrumentation: `devices.list.header.lastCoredumpAt` (data-testid for sort header, consistent with existing `devices.list.header.{column}` pattern in `src/components/devices/device-list-table.tsx:102`)
- Backend hooks: Device factory creates devices with null `lastCoredumpAt` by default. Testing non-null values requires seeding a coredump, which depends on the factory.
- Gaps: Non-null column testing depends on coredump seeding capability. However, null display and sort header click can be tested independently.
- Evidence: `plan.md:529-536`

## 5) Adversarial Sweep

**Minor (downgraded from Major) -- Route nesting for coredump detail page and the $deviceId layout route**

**Evidence:** `plan.md:118-120` -- "New route for the core dump detail page... Note: the parent `$deviceId.tsx` does not render `<Outlet />`, but TanStack Router v1 renders child route components as full page replacements in this case (confirmed by the working `$deviceId/duplicate.tsx` precedent)"; `src/routeTree.gen.ts:62-67,218-228` -- `$deviceId.tsx` is already a layout route with `DevicesDeviceIdRouteWithChildren`

**Why it matters:** The routing nuance is now documented in the plan with an explicit reference to the working precedent. The risk is reduced to a verification step during implementation rather than a design gap.

**Fix suggestion:** Already applied -- the plan now acknowledges the behavior and provides a fallback strategy.

**Confidence:** High -- The precedent is established and documented.

---

**Resolved (previously Major) -- Delete mutation form instrumentation**

**Evidence:** `plan.md:272-277` -- Delete flow now includes `trackFormSubmit`, `trackFormSuccess`, `trackFormError` emission; `plan.md:430-435` -- New instrumentation entry for `form` events with formId `CoredumpDelete`; `plan.md:510` -- Test plan now references `CoredumpDelete` form events for deterministic assertions

**Why it matters:** The delete mutation flow now has deterministic instrumentation matching the `CLAUDE.md` requirement for `trackForm*` hooks on mutation flows.

**Fix suggestion:** Already applied.

**Confidence:** High

---

**Minor -- The `sortedCoredumps` derivation specifies client-side sort by `uploadedAt` descending, but the plan does not address whether the API already returns coredumps in this order**

**Evidence:** `plan.md:248` -- "render rows sorted by `uploadedAt` descending (newest first)"; `plan.md:309-313` -- derived value `sortedCoredumps` sourced from the coredump list query

**Why it matters:** If the API already returns coredumps sorted by `uploaded_at` descending, the client-side sort is redundant but harmless. If the API returns them in a different order, the client-side sort is necessary. The plan does not specify whether a `useMemo` sort is needed or if the API ordering can be relied upon.

**Fix suggestion:** During implementation, check the API response ordering. If unspecified, keep the client-side sort. Client-side sorting a small list is cheap regardless.

**Confidence:** Low -- This is a correctness clarification, not a functional risk.

## 6) Derived-Value & State Invariants

- Derived value: `sortedCoredumps`
  - Source dataset: `coredumps` array from `useCoredumps(deviceId)` query, sorted client-side by `uploadedAt` descending
  - Write / cleanup triggered: Read-only derivation in `useMemo`; no writes. Cache invalidation after delete mutation triggers a refetch that produces a new sorted list.
  - Guards: Empty array guard for empty state rendering. TanStack Query's `isLoading` flag prevents rendering stale sorted data during refetch.
  - Invariant: The sorted list always reflects the latest server state after cache invalidation. No persistent write derives from this filtered view.
  - Evidence: `plan.md:309-314`, pattern from `src/components/devices/device-list-table.tsx:60-82`

- Derived value: `lastCoredumpAtDisplay`
  - Source dataset: `device.lastCoredumpAt` from `DeviceSummary`, which is server-provided via `useDevices()` query
  - Write / cleanup triggered: None; display-only. After a coredump delete mutation, the plan correctly invalidates the `getDevices` query key (`plan.md:335`), which refreshes `lastCoredumpAt` from the server.
  - Guards: Null check renders em-dash. No client-side mutation writes to this field.
  - Invariant: The displayed value always matches the server's `last_coredump_at`. Cache invalidation after coredump deletion ensures the device list reflects the updated timestamp.
  - Evidence: `plan.md:323-328`, `plan.md:335`

- Derived value: `formattedSize`
  - Source dataset: `coredump.size` (integer bytes) from the API response, formatted as human-readable string (e.g., "24.5 KB")
  - Write / cleanup triggered: Pure function, no side effects or persistent writes.
  - Guards: API guarantees a positive integer. Formatter should handle zero gracefully.
  - Invariant: Display-only transformation with no persistence. Cannot cause UI drift.
  - Evidence: `plan.md:316-321`

None of the derived values use a filtered view to drive a persistent write or cleanup, so no Major flag is warranted.

## 7) Risks & Mitigations (top 3)

- Risk: Coredump seeding in Playwright tests may be blocked if the backend does not expose a test-friendly endpoint for creating coredumps. The `POST /api/iot/coredump` endpoint likely requires device-level authentication or binary payloads that are difficult to construct in the test harness.
- Mitigation: Investigate the backend's testing endpoints before starting Slice 4. If no suitable endpoint exists, request one from the backend team (e.g., `POST /api/testing/coredumps`). The plan already identifies this risk and proposes fallbacks (`plan.md:572-574`).
- Evidence: `plan.md:572-574`, `plan.md:511`

- Risk: The coredump detail route at `$deviceId/coredumps/$coredumpId.tsx` may not render correctly if TanStack Router's nested route behavior differs from the established `$deviceId/duplicate.tsx` precedent.
- Mitigation: The plan now documents this routing nuance (`plan.md:120`) and references the working precedent. Verify during implementation and fall back to a flat route if needed.
- Evidence: `plan.md:118-120`, `src/routeTree.gen.ts:62-67`, `src/routes/devices/$deviceId.tsx:46-59`

- Risk: The download anchor tag may cause browser navigation instead of a file download if the backend does not set `Content-Disposition: attachment` headers correctly.
- Mitigation: Verify the backend response headers. If `Content-Disposition` is missing, add the `download` attribute to the `<a>` tag as a browser hint. The plan already identifies this (`plan.md:578-580`).
- Evidence: `plan.md:578-580`

## 8) Confidence

Confidence: High -- The plan is comprehensive, well-evidenced, and closely follows established codebase patterns. Both issues identified during the initial review (routing clarification and delete mutation instrumentation) have been addressed in the updated plan. The remaining open item (Playwright factory backend dependency) is correctly scoped as a backend coordination item that does not block frontend implementation.
