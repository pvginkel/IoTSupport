# Core Dump Support — Frontend Technical Plan

## 0) Research Log & Findings

**Searched areas and findings:**

- **Generated API hooks** (`src/lib/api/generated/hooks.ts:358-445`): All coredump endpoints are already generated — `useGetDevicesCoredumpsByDeviceId` (list), `useGetDevicesCoredumpsByDeviceIdAndCoredumpId` (detail), `useDeleteDevicesCoredumpsByDeviceIdAndCoredumpId` (delete single), `useDeleteDevicesCoredumpsByDeviceId` (delete all). The download endpoint has a generated hook, but the plan calls for a plain `<a href>` link instead.
- **Generated types** (`src/lib/api/generated/types.ts:777-918`): `CoredumpDetailSchema.58985ac` includes `id`, `device_id`, `filename`, `chip`, `firmware_version`, `size`, `parse_status`, `parsed_at`, `parsed_output`, `uploaded_at`, `created_at`, `updated_at`. `CoredumpSummarySchema` is the same minus `parsed_output`. The `DeviceSummarySchema` already includes `last_coredump_at: string | null`.
- **Device list table** (`src/components/devices/device-list-table.tsx`): Sortable table with `SortPreference` type and `renderSortHeader` helper. Currently has 6 columns + Actions. Adding a new column is straightforward.
- **Sort preferences** (`src/lib/utils/sort-preferences.ts`): Column union type needs `lastCoredumpAt` added. Validation array needs updating.
- **Device hooks** (`src/hooks/use-devices.ts`): `DeviceSummary` interface and `transformDeviceSummary` function need `lastCoredumpAt` field. The `last_coredump_at` field is already present in the API response but not mapped.
- **Device editor page** (`src/routes/devices/$deviceId.tsx`, `src/components/devices/device-editor.tsx`): The editor renders `DeviceLogsViewer` at the bottom of the content area. The core dumps table should be placed below the logs viewer.
- **Route structure** (`src/routes/devices/`): File-based routing with `$deviceId.tsx` for device detail, `$deviceId/duplicate.tsx` for nested route. The core dump detail page needs a new nested route at `$deviceId/coredumps/$coredumpId.tsx`.
- **Instrumentation** (`src/lib/test/query-instrumentation.ts`, `src/lib/test/form-instrumentation.ts`): `useListLoadingInstrumentation` emits `list_loading` events. New core dumps table should emit its own scoped events.
- **ConfirmDialog** (`src/components/ui/dialog.tsx`, `src/hooks/use-confirm.ts`): Existing pattern for delete confirmation used on device list. Same pattern applies to core dump deletion.
- **Playwright tests** (`tests/e2e/devices/`): DevicesPage page object, DevicesFactory, standard patterns for list loading assertions.
- **Monaco Editor**: Already imported in `device-editor.tsx` via `@monaco-editor/react`. The detail page needs a read-only plain text instance.
- **No conflicts**: No existing coredump UI code was found. This is greenfield.

---

## 1) Intent & Scope

**User intent**

Surface backend core dump support in the frontend by adding a core dumps table to the device editor page, a dedicated core dump detail page with a Monaco-based parsed output viewer, and a "Last Core Dump" column to the devices list table.

**Prompt quotes**

- "Add a core dumps table below the device log monitor on the device editor page, always visible (with empty state)"
- "Clicking a core dump row navigates to a new dedicated detail page"
- "Detail page shows parsed output in a read-only Monaco editor with no syntax highlighting (plain text)"
- "Add sortable 'Last Core Dump' column to the devices list table with absolute datetime format"
- "Delete per row with confirmation dialog, no 'Delete All' functionality"

**In scope**

- New `use-coredumps.ts` custom hook wrapping generated API hooks with camelCase models
- Core dumps table component rendered below the device logs viewer on the device editor page
- Core dump detail route and page at `/devices/$deviceId/coredumps/$coredumpId`
- `lastCoredumpAt` column added to the device list table with sort support
- Delete single core dump with confirmation dialog
- Download via plain `<a href>` link
- Instrumentation for Playwright (list loading events, form events for delete mutation)
- Playwright spec and factory extension for core dump CRUD

**Out of scope**

- "Delete All" core dumps functionality (explicitly excluded)
- Custom UI treatment per parse status value (show as-is)
- Polling or auto-refresh for parse status changes
- Upload core dump from the frontend
- Any backend changes

**Assumptions / constraints**

- The backend already returns `last_coredump_at` on the device summary endpoint and all coredump CRUD endpoints are operational.
- The download endpoint (`GET /api/devices/{device_id}/coredumps/{coredump_id}/download`) returns the raw binary with appropriate `Content-Disposition` headers, so a plain anchor tag will trigger browser download.
- Core dump data is seeded via the backend testing infrastructure. The Playwright factory will need a way to create coredumps for a device (either via the `POST /api/iot/coredump` endpoint or a testing-specific endpoint). If neither is feasible from the test harness, the coredump Playwright specs will be deferred (see Risks).

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Add a core dumps table below the device log monitor on the device editor page, always visible (with empty state)
- [ ] Table columns: Uploaded At | Firmware | Size | Status | Actions
- [ ] Actions column has Download (plain `<a href>` to download endpoint) and Delete (with confirmation) per row
- [ ] Clicking a core dump row navigates to a new dedicated detail page
- [ ] Detail page shows parsed output in a read-only Monaco editor with no syntax highlighting (plain text)
- [ ] Detail page shows core dump metadata and a download link
- [ ] Parse status is shown as-is with no custom UI treatment per status value
- [ ] Add sortable "Last Core Dump" column to the devices list table with absolute datetime format
- [ ] "Last Core Dump" column shows "---" when null, uses toLocaleString() for formatting
- [ ] Delete per row with confirmation dialog, no "Delete All" functionality

---

## 2) Affected Areas & File Map

- Area: `src/hooks/use-coredumps.ts` (new file)
- Why: Custom hook wrapping generated coredump API hooks with camelCase domain models, toast integration for delete mutation, and form instrumentation (`useFormInstrumentation` with formId `CoredumpDelete`) for deterministic Playwright assertions on the delete flow.
- Evidence: Follows pattern of `src/hooks/use-devices.ts:122-255` — wraps generated hooks, transforms snake_case to camelCase, provides mutation with invalidation. Form instrumentation pattern from `src/components/devices/device-editor.tsx:198-199`.

---

- Area: `src/hooks/use-devices.ts`
- Why: Add `lastCoredumpAt` field to `DeviceSummary` interface and `transformDeviceSummary` function so the list table has access to the new column value.
- Evidence: `src/hooks/use-devices.ts:17-26` (DeviceSummary interface), `src/hooks/use-devices.ts:53-73` (transformDeviceSummary) — `last_coredump_at` is available in the API response (`src/lib/api/generated/types.ts:1092-1096`) but not yet mapped.

---

- Area: `src/lib/utils/sort-preferences.ts`
- Why: Add `lastCoredumpAt` to the `SortPreference['column']` union type and the validation array so the new column can be sorted and persisted.
- Evidence: `src/lib/utils/sort-preferences.ts:3-6` (column union), `src/lib/utils/sort-preferences.ts:21` (validColumns array).

---

- Area: `src/components/devices/device-list-table.tsx`
- Why: Add a "Last Core Dump" column header and cell rendering with `toLocaleString()` formatting and em-dash for null values.
- Evidence: `src/components/devices/device-list-table.tsx:119-125` (existing column headers), `src/components/devices/device-list-table.tsx:129-173` (row rendering).

---

- Area: `src/components/devices/coredump-table.tsx` (new file)
- Why: New component rendering the core dumps table on the device editor page. Displays columns (Uploaded At, Firmware, Size, Status, Actions), handles row click navigation, download link, and delete action.
- Evidence: Follows structural pattern of `src/components/devices/device-list-table.tsx` for table layout and `src/components/devices/device-logs-viewer.tsx` for placement within the editor.

---

- Area: `src/components/devices/device-editor.tsx`
- Why: Import and render `CoredumpTable` below the `DeviceLogsViewer` section, passing `deviceId`.
- Evidence: `src/components/devices/device-editor.tsx:558-564` — `DeviceLogsViewer` is the last content section in edit mode; coredump table goes below it.

---

- Area: `src/routes/devices/$deviceId/coredumps/$coredumpId.tsx` (new file)
- Why: New route for the core dump detail page at `/devices/:deviceId/coredumps/:coredumpId`.
- Evidence: Follows the nested route pattern of `src/routes/devices/$deviceId/duplicate.tsx:6` — `createFileRoute('/devices/$deviceId/duplicate')`. Note: the parent `$deviceId.tsx` does not render `<Outlet />`, but TanStack Router v1 renders child route components as full page replacements in this case (confirmed by the working `$deviceId/duplicate.tsx` precedent). After `pnpm generate:api` / route tree regeneration, verify the new route appears in `src/routeTree.gen.ts` with `parentRoute: typeof DevicesDeviceIdRoute` and renders correctly.

---

- Area: `src/components/devices/coredump-detail.tsx` (new file)
- Why: Component rendering core dump metadata, download link, and read-only Monaco editor for parsed output.
- Evidence: Monaco import pattern from `src/components/devices/device-editor.tsx:3` — `import Editor from '@monaco-editor/react'`.

---

- Area: `tests/api/factories/devices.ts`
- Why: Add coredump factory methods (`createCoredump`, `listCoredumps`, `deleteCoredump`) to enable Playwright tests to seed core dump data.
- Evidence: `tests/api/factories/devices.ts:26-183` — DevicesFactory class with existing CRUD methods.

---

- Area: `tests/e2e/devices/DevicesPage.ts`
- Why: Add locators and actions for the coredump table, coredump detail page, and the "Last Core Dump" column.
- Evidence: `tests/e2e/devices/DevicesPage.ts:1-390` — existing page object with list, editor, and logs locators.

---

- Area: `tests/e2e/devices/devices-coredumps.spec.ts` (new file)
- Why: Playwright spec covering core dump table rendering, navigation to detail, download link, delete flow, and last coredump column visibility.
- Evidence: Follows pattern of `tests/e2e/devices/devices-crud.spec.ts` and `tests/e2e/devices/devices-logs.spec.ts`.

---

## 3) Data Model / Contracts

- Entity / contract: `CoredumpSummary` (new UI domain model)
- Shape:
  ```typescript
  interface CoredumpSummary {
    id: number
    deviceId: number
    filename: string
    chip: string
    firmwareVersion: string
    size: number
    parseStatus: string
    parsedAt: string | null
    uploadedAt: string
    createdAt: string
  }
  ```
- Mapping: `firmware_version` -> `firmwareVersion`, `parse_status` -> `parseStatus`, `parsed_at` -> `parsedAt`, `uploaded_at` -> `uploadedAt`, `created_at` -> `createdAt`, `device_id` -> `deviceId`
- Evidence: `src/lib/api/generated/types.ts:864-918` (CoredumpSummarySchema)

---

- Entity / contract: `CoredumpDetail` (new UI domain model)
- Shape:
  ```typescript
  interface CoredumpDetail extends CoredumpSummary {
    parsedOutput: string | null
    updatedAt: string
  }
  ```
- Mapping: `parsed_output` -> `parsedOutput`, `updated_at` -> `updatedAt`
- Evidence: `src/lib/api/generated/types.ts:780-846` (CoredumpDetailSchema)

---

- Entity / contract: `DeviceSummary` (existing, modified)
- Shape: Add `lastCoredumpAt: string | null`
- Mapping: `last_coredump_at` -> `lastCoredumpAt`
- Evidence: `src/hooks/use-devices.ts:17-26` (existing interface), `src/lib/api/generated/types.ts:1092-1096` (field in API response)

---

- Entity / contract: Query cache keys
- Shape: `['getDevicesCoredumpsByDeviceId', { path: { device_id } }]` for list, `['getDevicesCoredumpsByDeviceIdAndCoredumpId', { path: { device_id, coredump_id } }]` for detail
- Mapping: Direct from generated hooks
- Evidence: `src/lib/api/generated/hooks.ts:384,421`

---

## 4) API / Integration Surface

- Surface: `GET /api/devices/{device_id}/coredumps` / `useGetDevicesCoredumpsByDeviceId`
- Inputs: `{ path: { device_id: number } }`
- Outputs: `{ coredumps: CoredumpSummary[], count: number }` — populates the coredump table on the device editor
- Errors: Standard API error handling via `toApiError`; surfaces through `useListLoadingInstrumentation`
- Evidence: `src/lib/api/generated/hooks.ts:381-392`

---

- Surface: `GET /api/devices/{device_id}/coredumps/{coredump_id}` / `useGetDevicesCoredumpsByDeviceIdAndCoredumpId`
- Inputs: `{ path: { device_id: number, coredump_id: number } }`
- Outputs: `CoredumpDetail` — populates the detail page including `parsed_output`
- Errors: 404 if coredump not found; handled via error state in the route component
- Evidence: `src/lib/api/generated/hooks.ts:418-429`

---

- Surface: `GET /api/devices/{device_id}/coredumps/{coredump_id}/download` (plain `<a href>`)
- Inputs: URL path parameters interpolated into the href
- Outputs: Browser-handled binary download (the backend sets `Content-Disposition`)
- Errors: Browser will show a download error; no custom handling needed
- Evidence: `src/lib/api/generated/types.ts:237-245` (path definition)

---

- Surface: `DELETE /api/devices/{device_id}/coredumps/{coredump_id}` / `useDeleteDevicesCoredumpsByDeviceIdAndCoredumpId`
- Inputs: `{ path: { device_id: number, coredump_id: number } }`
- Outputs: Void on success; invalidates coredump list cache and device list cache (to refresh `last_coredump_at`)
- Errors: Toast notification on failure via centralized error handling
- Evidence: `src/lib/api/generated/hooks.ts:397-413`

---

- Surface: `GET /api/devices` / existing `useGetDevices`
- Inputs: None
- Outputs: `{ devices: DeviceSummary[] }` — now includes `last_coredump_at` per device
- Errors: Existing handling unchanged
- Evidence: `src/hooks/use-devices.ts:123-135`

---

## 5) Algorithms & UI Flows

- Flow: Core Dump Table — Load and Display
- Steps:
  1. Device editor page mounts in edit mode with `deviceId`
  2. `CoredumpTable` component mounts and calls `useCoredumps(deviceId)` which wraps `useGetDevicesCoredumpsByDeviceId`
  3. While loading, show skeleton rows
  4. If no coredumps, show empty state ("No core dumps recorded for this device")
  5. If coredumps exist, render rows sorted by `uploadedAt` descending (newest first)
  6. Each row shows: `uploadedAt` (via `toLocaleString()`), `firmwareVersion`, formatted `size`, `parseStatus` as plain text, and Actions (Download + Delete)
- States / transitions: `isLoading` -> skeleton; `data.length === 0` -> empty state; `data.length > 0` -> populated table
- Hotspots: None expected; coredump counts are small per device
- Evidence: Pattern follows `src/components/devices/device-list-table.tsx:84-92` (loading skeleton)

---

- Flow: Core Dump Row Click — Navigate to Detail
- Steps:
  1. User clicks a coredump row (but not on Download or Delete action buttons)
  2. `onClick` handler calls `navigate({ to: '/devices/$deviceId/coredumps/$coredumpId', params: { deviceId, coredumpId } })`
  3. Detail route loads and fetches coredump detail
- States / transitions: Click -> navigation -> loading -> detail view
- Hotspots: Download and Delete button click handlers must call `e.stopPropagation()` to prevent row navigation
- Evidence: Row click pattern from `src/components/devices/device-list-table.tsx:139` — `onClick={() => navigate(...)}`

---

- Flow: Core Dump Delete
- Steps:
  1. User clicks Delete button on a core dump row
  2. `e.stopPropagation()` prevents row navigation
  3. `useConfirm` presents a ConfirmDialog asking "Delete this core dump?"
  4. On confirm, emit `trackFormSubmit` with formId `CoredumpDelete`, then call `deleteCoredump.mutate({ deviceId, coredumpId })`
  5. On success: emit `trackFormSuccess`, toast, invalidate coredump list cache and device list cache
  6. On error: emit `trackFormError`, toast with error message
- States / transitions: Click -> dialog open -> confirm/cancel -> trackFormSubmit -> mutation -> trackFormSuccess/trackFormError -> cache invalidation
- Hotspots: None
- Evidence: Delete pattern from `src/routes/devices/index.tsx:45-56` (handleDelete with useConfirm); form instrumentation pattern from `src/components/devices/device-editor.tsx:198-199,286,301,307`

---

- Flow: Core Dump Detail Page
- Steps:
  1. Route loads with `deviceId` and `coredumpId` params
  2. Fetches coredump detail via `useCoredump(deviceId, coredumpId)`
  3. Renders metadata section (filename, chip, firmware version, size, parse status, uploaded at, parsed at)
  4. Renders download link as `<a href="/api/devices/{deviceId}/coredumps/{coredumpId}/download">`
  5. Renders read-only Monaco editor with `parsed_output` value in plain text mode
  6. Back navigation link to device editor
- States / transitions: Loading -> error (404) or detail view
- Hotspots: Monaco editor height should be generous (e.g., 500px or more) since parsed crash output can be lengthy
- Evidence: Monaco usage from `src/components/devices/device-editor.tsx:537-555` (Editor component)

---

- Flow: Devices List — Last Core Dump Column
- Steps:
  1. `DeviceSummary` now includes `lastCoredumpAt`
  2. `DeviceListTable` renders a new sortable column header "Last Core Dump"
  3. Cell value: `device.lastCoredumpAt ? new Date(device.lastCoredumpAt).toLocaleString() : '---'`
  4. Sort preference supports `lastCoredumpAt` as a valid column
- States / transitions: Null -> em-dash; non-null -> formatted datetime
- Hotspots: None
- Evidence: `src/components/devices/device-list-table.tsx:119-124` (existing column headers)

---

## 6) Derived State & Invariants

- Derived value: `sortedCoredumps`
  - Source: `coredumps` array from `useCoredumps(deviceId)`, sorted by `uploadedAt` descending
  - Writes / cleanup: Read-only derivation; no writes
  - Guards: Empty array guard for empty state rendering
  - Invariant: The list always reflects the latest server state after mutations invalidate the cache
  - Evidence: Pattern from `src/components/devices/device-list-table.tsx:60-82` (sortedDevices derivation)

- Derived value: `formattedSize`
  - Source: `coredump.size` (bytes) formatted as human-readable (e.g., "24.5 KB")
  - Writes / cleanup: Pure function, no side effects
  - Guards: Always a positive integer from the API
  - Invariant: Display-only formatting, no persistence
  - Evidence: New utility; no existing file size formatter in codebase

- Derived value: `lastCoredumpAtDisplay`
  - Source: `device.lastCoredumpAt` from `DeviceSummary`
  - Writes / cleanup: None; display-only
  - Guards: Null check — render em-dash when null
  - Invariant: Value is read from the server; no client mutations write to this field directly (cache invalidation updates it after coredump delete)
  - Evidence: `src/hooks/use-devices.ts:17-26` (DeviceSummary)

---

## 7) State Consistency & Async Coordination

- Source of truth: TanStack Query cache for coredump list (`getDevicesCoredumpsByDeviceId`) and coredump detail (`getDevicesCoredumpsByDeviceIdAndCoredumpId`)
- Coordination: After a successful delete mutation, invalidate both `getDevicesCoredumpsByDeviceId` (to refresh the table) and `getDevices` (to refresh `lastCoredumpAt` on the list page). The detail query key should also be invalidated so that navigating back doesn't show stale data.
- Async safeguards: Generated hooks already use TanStack Query's built-in stale data management. No abort controllers needed since queries are short-lived. If the user navigates away during a delete mutation, the mutation completes in the background and the invalidation fires regardless.
- Instrumentation: `useListLoadingInstrumentation` with scope `coredumps.list` emits `list_loading` events (`loading` -> `ready` | `error`) so Playwright can await deterministic states.
- Evidence: Invalidation pattern from `src/hooks/use-devices.ts:229-241` (useDeleteDevice invalidates `getDevices`)

---

## 8) Errors & Edge Cases

- Failure: Coredump list endpoint returns error
- Surface: `CoredumpTable` component
- Handling: Show inline error message within the table area (e.g., "Failed to load core dumps"). No retry button needed — user can refresh the page.
- Guardrails: Error state is emitted via `useListLoadingInstrumentation` so tests can assert on it.
- Evidence: Error pattern from `src/routes/devices/index.tsx:58-65`

---

- Failure: Coredump detail endpoint returns 404
- Surface: Core dump detail route component
- Handling: Show "Core dump not found" message with a link back to the device editor, following the device editor's 404 pattern.
- Guardrails: None needed beyond the UI message.
- Evidence: `src/routes/devices/$deviceId.tsx:34-44` (error state in device route)

---

- Failure: Delete mutation fails
- Surface: `CoredumpTable` component (toast notification)
- Handling: Error toast via `useToast` in the custom hook's `onError` callback. Table remains unchanged (optimistic update not used).
- Guardrails: Delete button re-enables after mutation settles.
- Evidence: `src/hooks/use-devices.ts:237-240` (delete error handling)

---

- Failure: Download link returns error (e.g., file deleted from disk)
- Surface: Browser's native download behavior
- Handling: The browser will display its own error. No custom frontend handling needed since the download is a plain anchor tag.
- Guardrails: None.
- Evidence: Change brief specifies "plain `<a href>` link to the download endpoint, letting the browser handle the binary download"

---

- Failure: Empty coredump list
- Surface: `CoredumpTable` component
- Handling: Show an `EmptyState` component with message "No core dumps recorded for this device"
- Guardrails: Empty state is always visible per requirements (table section is never hidden)
- Evidence: `src/components/ui/empty-state.tsx` (existing EmptyState component)

---

- Failure: `parsed_output` is null on detail page (status is PENDING or ERROR)
- Surface: Core dump detail page Monaco editor area
- Handling: Show a placeholder message instead of the editor (e.g., "Parsed output not available" or "Parsing pending..."). No custom per-status styling per requirements.
- Guardrails: None.
- Evidence: Change brief: "Show the parse status as-is without any custom UI treatment"

---

## 9) Observability / Instrumentation

- Signal: `list_loading` with scope `coredumps.list`
- Type: Instrumentation event
- Trigger: Emitted by `useListLoadingInstrumentation` inside `CoredumpTable` when the coredump list query transitions between loading/ready/error states.
- Labels / fields: `{ scope: 'coredumps.list', phase: 'loading' | 'ready' | 'error', metadata: { visible, total } }`
- Consumer: Playwright `waitForListLoading(page, 'coredumps.list', 'ready')` helper
- Evidence: `src/lib/test/query-instrumentation.ts:146-236` (useListLoadingInstrumentation)

---

- Signal: `data-testid` attributes on coredump table elements
- Type: Test selectors
- Trigger: Present in DOM when component renders
- Labels / fields: `coredumps.table`, `coredumps.table.row`, `coredumps.table.row.download`, `coredumps.table.row.delete`, `coredumps.table.empty`, `coredumps.table.loading`, `coredumps.table.error`
- Consumer: Playwright page object locators
- Evidence: Naming convention from `src/components/devices/device-list-table.tsx:115,86` (data-testid on table, loading)

---

- Signal: `data-testid` attributes on coredump detail page elements
- Type: Test selectors
- Trigger: Present in DOM when detail page renders
- Labels / fields: `coredumps.detail`, `coredumps.detail.metadata`, `coredumps.detail.download`, `coredumps.detail.editor`, `coredumps.detail.error`
- Consumer: Playwright page object locators
- Evidence: Naming convention consistency

---

- Signal: `data-testid` on delete confirmation dialog
- Type: Test selector
- Trigger: When delete confirmation dialog opens
- Labels / fields: `coredumps.delete.confirm-dialog`
- Consumer: Playwright page object for confirming/canceling delete
- Evidence: `src/routes/devices/index.tsx:112` (ConfirmDialog contentProps data-testid pattern)

---

- Signal: `form` events with formId `CoredumpDelete`
- Type: Instrumentation event (form lifecycle)
- Trigger: Emitted by `useFormInstrumentation` / `trackFormSubmit`, `trackFormSuccess`, `trackFormError` during the delete mutation lifecycle in the `CoredumpTable` component
- Labels / fields: `{ formId: 'CoredumpDelete', phase: 'submit' | 'success' | 'error' }`
- Consumer: Playwright `waitTestEvent(page, 'form', evt => evt.formId === 'CoredumpDelete' && evt.phase === 'success')` for deterministic delete flow assertions
- Evidence: Form instrumentation pattern from `src/components/devices/device-editor.tsx:198-199,286,301,307`; `src/lib/test/form-instrumentation.ts`

---

## 10) Lifecycle & Background Work

- Hook / effect: `useCoredumps(deviceId)` — wraps `useGetDevicesCoredumpsByDeviceId`
- Trigger cadence: On mount when device editor loads in edit mode
- Responsibilities: Fetches the coredump list for the given device and transforms to camelCase models
- Cleanup: TanStack Query manages the subscription automatically on unmount
- Evidence: Pattern from `src/hooks/use-devices.ts:138-153` (useDevice hook)

---

- Hook / effect: `useCoredump(deviceId, coredumpId)` — wraps `useGetDevicesCoredumpsByDeviceIdAndCoredumpId`
- Trigger cadence: On mount when the detail route loads
- Responsibilities: Fetches the full coredump detail including parsed output
- Cleanup: TanStack Query manages the subscription automatically on unmount
- Evidence: Same pattern as above

---

- Hook / effect: `useListLoadingInstrumentation` in `CoredumpTable`
- Trigger cadence: Reacts to `isLoading`/`isFetching`/`error` changes from the query
- Responsibilities: Emits `list_loading` test events for Playwright
- Cleanup: Emits `aborted` event on unmount if still in-flight
- Evidence: `src/lib/test/query-instrumentation.ts:213-235` (cleanup effect)

---

## 11) Security & Permissions

- Concern: Download link exposes file URL
- Touchpoints: `CoredumpTable` and `CoredumpDetail` render `<a href="/api/devices/{deviceId}/coredumps/{coredumpId}/download">`
- Mitigation: The download endpoint is behind the same auth middleware as all other API routes (the `authMiddleware` in `src/lib/api/generated/client.ts:7-14` handles 401 redirects; the Vite proxy forwards cookies). The anchor tag is relative, so it inherits the session cookie.
- Residual risk: None beyond what already exists for other API calls — the app runs in a trusted homelab network with session-based auth.
- Evidence: `src/lib/api/generated/client.ts:7-14` (auth middleware)

---

## 12) UX / UI Impact

- Entry point: Device editor page (`/devices/:deviceId`) — edit mode only
- Change: New "Core Dumps" section below Device Logs with a table and empty state
- User interaction: User sees core dumps table at the bottom of the editor. Can click rows to view detail, click Download to get the .dmp file, click Delete to remove with confirmation.
- Dependencies: `CoredumpTable` component, `use-coredumps` hook
- Evidence: `src/components/devices/device-editor.tsx:558-564` (DeviceLogsViewer placement)

---

- Entry point: New route `/devices/:deviceId/coredumps/:coredumpId`
- Change: Dedicated page showing core dump metadata, download link, and parsed output in a read-only Monaco editor
- User interaction: User arrives via row click in the coredump table. Views crash analysis output. Clicks "Back" to return to device editor. Clicks download link to save the .dmp file.
- Dependencies: `CoredumpDetail` component, `use-coredumps` hook, Monaco Editor
- Evidence: Route nesting pattern from `src/routes/devices/$deviceId/duplicate.tsx`

---

- Entry point: Devices list page (`/devices`)
- Change: New "Last Core Dump" sortable column between "OTA Status" and "Actions"
- User interaction: User sees the datetime of the most recent core dump per device. Null values show em-dash. Column is sortable with sort preference persisted to local storage.
- Dependencies: `DeviceSummary.lastCoredumpAt`, `SortPreference` type update
- Evidence: `src/components/devices/device-list-table.tsx:119-125` (column headers)

---

## 13) Deterministic Test Plan

- Surface: Core dumps table on device editor page
- Scenarios:
  - Given a device with no coredumps, When the user navigates to the device editor, Then the coredumps table section is visible with the empty state message "No core dumps recorded for this device"
  - Given a device with coredumps, When the user navigates to the device editor, Then the coredumps table displays rows with Uploaded At, Firmware, Size, Status, and Actions columns
  - Given a device with coredumps, When the user clicks a coredump row, Then the browser navigates to `/devices/{deviceId}/coredumps/{coredumpId}`
  - Given a device with coredumps, When the user clicks the Delete button on a row, Then a confirmation dialog appears; confirming deletes the coredump and refreshes the table
  - Given a device with coredumps, When the user clicks the Download link, Then the link href points to the correct download endpoint
- Instrumentation / hooks: `coredumps.table` (data-testid), `coredumps.list` (list_loading scope), `coredumps.delete.confirm-dialog` (data-testid), `CoredumpDelete` form events (`trackFormSubmit`/`trackFormSuccess`/`trackFormError`) for deterministic delete mutation assertions
- Gaps: If the backend lacks a testing endpoint to seed coredumps, the factory will need to call the `POST /api/iot/coredump` endpoint or a dedicated test seeding helper. If neither is available, defer these specs until backend support is added.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts` (existing spec patterns)

---

- Surface: Core dump detail page
- Scenarios:
  - Given a coredump with parsed output, When the user navigates to the detail page, Then the Monaco editor displays the parsed output in read-only plain text mode
  - Given a coredump with null parsed output, When the user navigates to the detail page, Then a message indicates parsed output is not available
  - Given the detail page is loaded, Then the metadata section shows filename, chip, firmware version, size, parse status, uploaded at, and parsed at
  - Given the detail page is loaded, Then a download link is present with the correct href
  - Given the detail page is loaded, Then a back link navigates to the device editor
- Instrumentation / hooks: `coredumps.detail` (data-testid), `coredumps.detail.editor` (data-testid), `coredumps.detail.download` (data-testid)
- Gaps: Same factory dependency as above.
- Evidence: `src/routes/devices/$deviceId.tsx` (route pattern)

---

- Surface: Devices list — Last Core Dump column
- Scenarios:
  - Given devices with `last_coredump_at` values, When the user views the devices list, Then the "Last Core Dump" column displays formatted datetimes
  - Given a device with null `last_coredump_at`, When the user views the devices list, Then the column shows "---"
  - Given the devices list, When the user clicks the "Last Core Dump" column header, Then the table sorts by that column
- Instrumentation / hooks: `devices.list.header.lastCoredumpAt` (data-testid for sort header)
- Gaps: None; existing device factory creates devices (which will have null `lastCoredumpAt` by default). Testing non-null values requires seeding a coredump first.
- Evidence: `src/components/devices/device-list-table.tsx:96-112` (renderSortHeader)

---

## 14) Implementation Slices

- Slice: 1 — Data layer and device list column
- Goal: `lastCoredumpAt` visible on the devices list; `use-coredumps.ts` hook ready for consumption
- Touches: `src/hooks/use-devices.ts`, `src/lib/utils/sort-preferences.ts`, `src/components/devices/device-list-table.tsx`, `src/hooks/use-coredumps.ts` (new)
- Dependencies: None; API is already available.

---

- Slice: 2 — Coredump table on device editor
- Goal: Core dumps table rendered below logs viewer with empty state, row display, download links, and delete with confirmation
- Touches: `src/components/devices/coredump-table.tsx` (new), `src/components/devices/device-editor.tsx`
- Dependencies: Slice 1 (use-coredumps hook)

---

- Slice: 3 — Coredump detail page
- Goal: Dedicated route and page showing metadata, download link, and read-only Monaco editor
- Touches: `src/routes/devices/$deviceId/coredumps/$coredumpId.tsx` (new), `src/components/devices/coredump-detail.tsx` (new)
- Dependencies: Slice 1 (use-coredumps hook)

---

- Slice: 4 — Playwright tests and factory
- Goal: Automated coverage for all new UI flows
- Touches: `tests/api/factories/devices.ts`, `tests/e2e/devices/DevicesPage.ts`, `tests/e2e/devices/devices-coredumps.spec.ts` (new)
- Dependencies: Slices 1-3; backend must expose a mechanism to seed coredump data from the test harness

---

## 15) Risks & Open Questions

- Risk: The coredump seeding endpoint (`POST /api/iot/coredump`) may require device authentication headers or binary payloads that are difficult to construct in Playwright factories.
- Impact: Playwright specs for coredump CRUD would be blocked.
- Mitigation: Check if a testing-specific endpoint exists (e.g., `POST /api/testing/coredumps`). If not, ask for one to be added to the backend. As a fallback, the factory can POST raw bytes to the IoT endpoint with test device credentials.

---

- Risk: The download endpoint may not set `Content-Disposition` correctly, causing the browser to navigate instead of downloading.
- Impact: User sees raw binary instead of getting a file download.
- Mitigation: Verify the backend sets `Content-Disposition: attachment` on the download response. If not, add `download` attribute to the anchor tag as a browser hint.

---

- Risk: Monaco editor bundle size increase from loading it on the coredump detail page.
- Impact: Minimal — Monaco is already loaded on the device editor page and is code-split by `@monaco-editor/react`.
- Mitigation: None needed; Monaco is already a project dependency.

---

- Question: Should the coredump table support pagination or is the full list always small enough?
- Why it matters: If a device has hundreds of coredumps, rendering all rows could be slow.
- Owner / follow-up: Resolved autonomously — the change brief does not mention pagination, and ESP32 devices in a homelab are expected to have a small number of coredumps. Implement without pagination; add it later if needed.

---

- Question: What format should the file size be displayed in?
- Why it matters: Bytes are not user-friendly.
- Owner / follow-up: Resolved autonomously — use a simple KB/MB formatter (e.g., `formatFileSize` utility). ESP32 coredumps are typically 100KB-500KB range, so KB formatting with one decimal is appropriate.

---

## 16) Confidence

Confidence: High — All API endpoints and generated hooks are in place. The UI patterns (sortable table, ConfirmDialog, Monaco editor, route nesting, custom hooks) are well-established in the codebase. The only uncertainty is around Playwright test data seeding, which is a backend coordination item that does not block the frontend implementation.
