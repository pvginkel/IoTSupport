# Phase B: Feature Implementation - Technical Plan

## 0) Research Log & Findings

**Repository Discovery:**

Examined the IoT Support frontend codebase and ElectronicsInventory reference patterns:

- Generated API hooks exist at `src/lib/api/generated/hooks.ts` with `useGetConfigs`, `useGetConfigsByMacAddress`, `usePutConfigsByMacAddress`, `useDeleteConfigsByMacAddress`
- Phase A routing established: `src/routes/__root.tsx`, `src/routes/index.tsx`, `src/routes/devices/index.tsx` (placeholder)
- Reference patterns from ElectronicsInventory:
  - `src/components/types/type-list.tsx` – card-based list with search, empty states, skeleton loaders, confirmation dialogs
  - `src/components/types/type-form.tsx` – dialog-based form with validation, instrumentation, and unsaved changes tracking
  - `src/hooks/use-types.ts` – wrapper hooks around generated API hooks
  - `src/hooks/use-confirm.ts` – promise-based confirmation dialog hook
  - `tests/e2e/types/TypesPage.ts` – page object pattern with action methods and locators
  - `tests/e2e/types/types-crud.spec.ts` – API factory-driven test scenarios
- Test infrastructure: `tests/support/fixtures.ts`, `tests/support/helpers.ts`, per-worker backend isolation
- Instrumentation: `src/lib/test/query-instrumentation.ts` exports `useListLoadingInstrumentation` for deterministic list loading events
- Toast system: ElectronicsInventory uses Radix `@radix-ui/react-toast` with light mode styling; plan will adapt for dark mode
- Dialog system: ElectronicsInventory uses Radix `@radix-ui/react-dialog` with `ConfirmDialog` helper
- No conflicts detected; Phase A shell provides the routing foundation this work extends

**Key Constraints:**
- Backend API: `GET /api/configs`, `GET /api/configs/:mac_address`, `PUT /api/configs/:mac_address`, `DELETE /api/configs/:mac_address`
- Snake_case API payloads must map to camelCase UI models in custom hooks
- MAC address is the primary key; rename operations require save-new + delete-old
- Monaco editor integration required (not present in ElectronicsInventory reference)
- All tests must use API factories, never intercept network requests (enforced by `testing/no-route-mocks` ESLint rule)

## 1) Intent & Scope

**User intent**

Deliver the complete device configuration management UI for IoT Support, building on the Phase A foundation (app shell, routing, Playwright infrastructure). The user needs a full-featured CRUD interface for device configs with sortable table display, JSON editing via Monaco, unsaved changes warnings, and comprehensive test coverage.

**Prompt quotes**

"Implement the complete device configuration management features for the IoT Support frontend."

"Device list displays all configs with MAC Address, Device Name, Entity ID, OTA Status columns"

"Monaco editor: JSON language, vs-dark theme, minimap disabled, code folding enabled, tab size 2"

"Save validates via PUT /api/configs/:macAddress, handles MAC rename (save new + delete old)"

"Playwright tests for all user flows with API factories and page objects"

**In scope**

- Device list view at `/devices` with sortable table (MAC Address, Device Name, Entity ID, OTA Status), skeleton loader, empty state
- New device route `/devices/new` with empty MAC input, template JSON, Save/Cancel buttons
- Edit device route `/devices/:macAddress` with pre-filled MAC, loaded JSON, Save/Cancel/Duplicate buttons
- Duplicate device route `/devices/:macAddress/duplicate` with empty MAC, copied JSON, Save/Cancel buttons
- Monaco JSON editor integration (vs-dark theme, minimap disabled, code folding, tab size 2)
- Save/delete flows with backend validation error handling, success/error toasts
- Unsaved changes detection with beforeunload warning and navigation confirmation
- Delete confirmation dialog (Radix UI, styled for dark mode)
- Custom hooks wrapping generated API hooks (error handling, camelCase mapping)
- Playwright tests with API factories, page objects, deterministic instrumentation waits
- LocalStorage sort preference persistence (`iot-support-device-sort`)
- Dark mode toast system (success/error/info variants, auto-dismiss)

**Out of scope**

- Light mode styling (dark mode only per design notes)
- Bulk operations (batch delete, multi-select)
- Advanced JSON validation beyond backend responses (no JSON schema validation in UI)
- Export/import functionality
- Undo/redo for editor changes
- Real-time collaboration or live updates
- Pagination (assume reasonable device count fits in memory)
- Advanced search/filtering beyond client-side sort

**Assumptions / constraints**

- Phase A is complete and stable: app shell, sidebar navigation, routing, Playwright per-worker service isolation
- Generated API hooks (`src/lib/api/generated/hooks.ts`) are available and up-to-date
- Backend API contracts are stable and documented (`/api/configs`, `/api/configs/:mac_address` GET/PUT/DELETE)
- MAC address is immutable identifier; rename requires delete-old + create-new sequence
- Backend returns validation errors with structured error messages that can surface in toasts
- Monaco editor package (`@monaco-editor/react`) will be added as dependency
- Table-based layout differs from ElectronicsInventory card-based pattern; adapt list instrumentation accordingly
- LocalStorage is acceptable for sort preferences (no backend persistence required)

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Device list displays all configs with MAC Address, Device Name, Entity ID, OTA Status columns
- [ ] OTA Status shows check icon (true), cross icon (false), or empty (null)
- [ ] All columns are sortable with click-to-toggle, preferences persisted to localStorage
- [ ] Skeleton loader during fetch, empty state with create button when no devices
- [ ] "New Device" button in header navigates to /devices/new
- [ ] Edit button on each row navigates to /devices/:macAddress
- [ ] Delete button on each row triggers confirmation dialog
- [ ] New device route: empty MAC input, template JSON, Save/Cancel buttons only
- [ ] Edit device route: pre-filled MAC (editable), loaded JSON, Save/Cancel/Duplicate buttons
- [ ] Duplicate route: empty MAC input, copied JSON from source, Save/Cancel buttons only
- [ ] Monaco editor: JSON language, vs-dark theme, minimap disabled, code folding enabled, tab size 2
- [ ] Save validates via PUT /api/configs/:macAddress, handles MAC rename (save new + delete old)
- [ ] On save success: navigate to list + success toast; On error: error toast with backend message
- [ ] Unsaved changes: beforeunload warning + confirmation dialog on navigation
- [ ] Delete confirmation: styled Radix dialog (not browser confirm), shows device MAC
- [ ] Delete success: refresh list + success toast; Delete error: error toast
- [ ] Toast system: success/error/info variants, auto-dismiss, dark mode styling
- [ ] Confirmation dialog: Radix UI Dialog, dark mode styling, destructive styling for delete
- [ ] Generated API hooks with custom wrapper hooks for error handling
- [ ] Playwright tests for all user flows with API factories and page objects

## 2) Affected Areas & File Map

### New Files (to create)

- **Area:** Device list component
- **Why:** Primary UI for displaying all device configurations in a sortable table
- **Evidence:** Placeholder at `src/routes/devices/index.tsx:1-18` – replace with DeviceList component

- **Area:** Device editor component
- **Why:** JSON editor route for new/edit/duplicate device configs
- **Evidence:** No route exists at `src/routes/devices/new.tsx`, `src/routes/devices/$macAddress.tsx`, `src/routes/devices/$macAddress/duplicate.tsx` – create these route modules

- **Area:** Device list table component
- **Why:** Reusable table component with sortable columns, row actions
- **Evidence:** ElectronicsInventory uses cards (`src/components/types/type-list.tsx:398-409`), but this feature requires table layout – create `src/components/devices/device-list-table.tsx`

- **Area:** Device editor form component
- **Why:** Monaco JSON editor with validation, unsaved changes tracking
- **Evidence:** ElectronicsInventory form pattern at `src/components/types/type-form.tsx:1-140` uses Radix Dialog – adapt for full-screen layout with Monaco at `src/components/devices/device-editor.tsx`

- **Area:** Custom device hooks
- **Why:** Wrap generated API hooks, map snake_case to camelCase, handle errors
- **Evidence:** ElectronicsInventory pattern at `src/hooks/use-types.ts:1-54` wraps generated hooks – create `src/hooks/use-devices.ts`

- **Area:** Toast context provider
- **Why:** Global toast notifications for success/error states
- **Evidence:** ElectronicsInventory toast system at `src/components/ui/toast.tsx:1-173` – adapt for dark mode and integrate at `src/contexts/toast-context.tsx`

- **Area:** Toast hook
- **Why:** Expose toast operations to components
- **Evidence:** ElectronicsInventory hook at `src/hooks/use-toast.ts` (referenced but not read) – create `src/hooks/use-toast.ts`

- **Area:** Confirmation dialog hook
- **Why:** Promise-based confirmation dialogs for delete actions
- **Evidence:** ElectronicsInventory hook at `src/hooks/use-confirm.ts:1-65` – copy pattern to `src/hooks/use-confirm.ts`

- **Area:** Dialog UI component
- **Why:** Radix Dialog primitives with dark mode styling
- **Evidence:** ElectronicsInventory component at `src/components/ui/dialog.tsx:1-244` – adapt for dark mode at `src/components/ui/dialog.tsx`

- **Area:** Button UI component (may exist from Phase A)
- **Why:** Reusable button with loading states, variants
- **Evidence:** ElectronicsInventory component at `src/components/ui/button.tsx` (referenced at `src/components/ui/dialog.tsx:3`) – verify exists or create `src/components/ui/button.tsx`

- **Area:** Input UI component (may exist from Phase A)
- **Why:** Form inputs with consistent styling
- **Evidence:** ElectronicsInventory component at `src/components/ui/input.tsx` (referenced at `src/components/types/type-list.tsx:217`) – verify exists or create `src/components/ui/input.tsx`

- **Area:** Skeleton UI component (may exist from Phase A)
- **Why:** Loading placeholders for table rows
- **Evidence:** ElectronicsInventory component at `src/components/ui/skeleton.tsx` (referenced at `src/components/types/type-list.tsx:322`) – verify exists or create `src/components/ui/skeleton.tsx`

- **Area:** Empty state UI component (may exist from Phase A)
- **Why:** Display when no devices exist
- **Evidence:** ElectronicsInventory component at `src/components/ui/empty-state.tsx` (referenced at `src/components/types/type-list.tsx:368`) – verify exists or create `src/components/ui/empty-state.tsx`

- **Area:** Sort utility functions
- **Why:** LocalStorage persistence for sort preferences
- **Evidence:** No existing sort utility – create `src/lib/utils/sort-preferences.ts`

- **Area:** Device factories for Playwright
- **Why:** API-driven test data creation for device configs
- **Evidence:** ElectronicsInventory factory pattern at `tests/api/factories/*` (referenced at `docs/contribute/testing/playwright_developer_guide.md:36-48`) – create `tests/api/factories/devices.ts`

- **Area:** Device page object for Playwright
- **Why:** Centralize device list/editor locators and actions
- **Evidence:** ElectronicsInventory page object at `tests/e2e/types/TypesPage.ts:1-203` – create `tests/e2e/devices/DevicesPage.ts`

- **Area:** Device CRUD test specs
- **Why:** Verify create, edit, duplicate, delete, sort, unsaved changes flows
- **Evidence:** ElectronicsInventory test at `tests/e2e/types/types-crud.spec.ts:1-100` – create `tests/e2e/devices/devices-crud.spec.ts`

- **Area:** Device editor test specs
- **Why:** Verify Monaco editor, validation, MAC rename, unsaved changes warnings
- **Evidence:** Need comprehensive editor-specific tests – create `tests/e2e/devices/device-editor.spec.ts`

### Modified Files

- **Area:** Root layout
- **Why:** Integrate ToastContext provider
- **Evidence:** `src/routes/__root.tsx` establishes app shell – add ToastContext.Provider wrapping QueryClientProvider

- **Area:** API client error handling
- **Why:** Ensure ApiError integrates with toast system
- **Evidence:** `src/lib/api/api-error.ts` exists (referenced at `src/lib/api/generated/hooks.ts:3`) – verify error shape supports toast rendering

- **Area:** Playwright fixtures
- **Why:** Add `devices` page object fixture
- **Evidence:** `tests/support/fixtures.ts` registers `types` fixture (referenced at `docs/contribute/testing/playwright_developer_guide.md:56`) – add `devices` fixture

- **Area:** Test factories bundle
- **Why:** Expose device factories via testData fixture
- **Evidence:** `tests/api/client.ts` and factory pattern (referenced at `docs/contribute/testing/playwright_developer_guide.md:36-48`) – integrate devices factory into bundle

## 3) Data Model / Contracts

### API Contracts (Backend)

- **Entity / contract:** ConfigListResponseSchema (GET /api/configs)
- **Shape:**
  ```typescript
  {
    configs: Array<{
      mac_address: string;      // Primary key
      device_name: string;
      device_entity_id: string;
      enable_ota: boolean | null;
    }>
  }
  ```
- **Mapping:** Snake_case API → camelCase UI model via custom hook
  ```typescript
  {
    macAddress: string;
    deviceName: string;
    deviceEntityId: string;
    enableOta: boolean | null;
  }
  ```
- **Evidence:** `src/lib/api/generated/types.ts` (referenced at `src/lib/api/generated/hooks.ts:5`), schema inspection shows ConfigListResponseSchema_6be28b6 structure

- **Entity / contract:** ConfigResponseSchema (GET /api/configs/:mac_address)
- **Shape:**
  ```typescript
  {
    mac_address: string;
    config: {
      deviceName: string;
      deviceEntityId: string;
      enableOTA: boolean;
    }
  }
  ```
- **Mapping:** Response includes both MAC (path param) and JSON config object; UI merges into single model
- **Evidence:** `src/lib/api/generated/hooks.ts:83-94` useGetConfigsByMacAddress returns ConfigResponseSchema_6be28b6

- **Entity / contract:** ConfigSaveRequestSchema (PUT /api/configs/:mac_address)
- **Shape:**
  ```typescript
  {
    mac_address: string;        // Path parameter
    body: {
      deviceName: string;
      deviceEntityId: string;
      enableOTA: boolean;
    }
  }
  ```
- **Mapping:** UI state → request body (preserve JSON structure from Monaco editor)
- **Evidence:** `src/lib/api/generated/hooks.ts:99` usePutConfigsByMacAddress signature

### UI State Models

- **Entity / contract:** DeviceConfig (UI domain model)
- **Shape:**
  ```typescript
  interface DeviceConfig {
    macAddress: string;
    deviceName: string;
    deviceEntityId: string;
    enableOta: boolean | null;
  }
  ```
- **Mapping:** Derived from API response via custom hook; used by table rows and editor
- **Evidence:** Custom hook pattern from `src/hooks/use-types.ts:10-35` (ElectronicsInventory reference)

- **Entity / contract:** SortPreference (localStorage)
- **Shape:**
  ```typescript
  {
    column: 'macAddress' | 'deviceName' | 'deviceEntityId' | 'enableOta';
    direction: 'asc' | 'desc';
  }
  ```
- **Mapping:** Persisted to localStorage key `iot-support-device-sort`, read on mount
- **Evidence:** New utility module for sort persistence

- **Entity / contract:** EditorState (unsaved changes tracking)
- **Shape:**
  ```typescript
  {
    originalMac: string;
    currentMac: string;
    originalJson: string;
    currentJson: string;
    isDirty: boolean;
  }
  ```
- **Mapping:** Tracked in editor component state; triggers beforeunload and navigation guards
- **Evidence:** ElectronicsInventory form pattern at `src/components/types/type-form.tsx:54-70` tracks form dirty state

## 4) API / Integration Surface

- **Surface:** GET /api/configs
- **Inputs:** None
- **Outputs:** ConfigListResponseSchema with array of all device configs; custom hook maps to DeviceConfig[]
- **Errors:** Network errors surface via global error handler; empty array for zero configs is success state
- **Evidence:** `src/lib/api/generated/hooks.ts:46-57` useGetConfigs returns ConfigListResponseSchema_6be28b6

- **Surface:** GET /api/configs/:mac_address
- **Inputs:** `{ path: { mac_address: string } }`
- **Outputs:** ConfigResponseSchema with single config; custom hook merges MAC + config JSON
- **Errors:** 404 if MAC not found (handled via toast); network errors trigger global handler
- **Evidence:** `src/lib/api/generated/hooks.ts:83-94` useGetConfigsByMacAddress

- **Surface:** PUT /api/configs/:mac_address
- **Inputs:** `{ path: { mac_address: string }, body: ConfigSaveRequestSchema }`
- **Outputs:** ConfigResponseSchema with saved config; invalidates GET /api/configs cache
- **Errors:** 400 validation errors (invalid JSON, missing fields) surface in toast; 409 conflict (duplicate MAC) shows specific message
- **Evidence:** `src/lib/api/generated/hooks.ts:99-115` usePutConfigsByMacAddress with onSuccess invalidation

- **Surface:** DELETE /api/configs/:mac_address
- **Inputs:** `{ path: { mac_address: string } }`
- **Outputs:** Void response; invalidates GET /api/configs cache
- **Errors:** 404 if MAC not found; network errors trigger global handler
- **Evidence:** `src/lib/api/generated/hooks.ts:62-78` useDeleteConfigsByMacAddress

- **Surface:** TanStack Query cache keys
- **Inputs:** Query keys generated by hooks: `['getConfigs', params]`, `['getConfigsByMacAddress', params]`
- **Outputs:** Mutations invalidate all `getConfigs` queries to refresh list after create/update/delete
- **Errors:** React Query default error handling emits `query_error` test events
- **Evidence:** `src/lib/api/generated/hooks.ts:36-39, 73-74, 109` mutation onSuccess callbacks

- **Surface:** Test instrumentation (list loading)
- **Inputs:** `useListLoadingInstrumentation({ scope: 'devices.list', isLoading, isFetching, error })`
- **Outputs:** Emits `list_loading` events with phases: loading, ready, error, aborted
- **Errors:** Error phase includes metadata with error message for test assertions
- **Evidence:** `src/lib/test/query-instrumentation.ts` (referenced at `docs/contribute/architecture/test_instrumentation.md:35`), pattern from `src/components/types/type-list.tsx:93-132`

- **Surface:** Test instrumentation (form lifecycle)
- **Inputs:** `useFormInstrumentation({ formId, isOpen, snapshotFields })`
- **Outputs:** Emits `form` events with phases: open, submit, success, error, validation_error
- **Errors:** Error phase includes backend validation messages
- **Evidence:** `src/hooks/use-form-instrumentation.ts` (referenced at `src/components/types/type-form.tsx:7`), ElectronicsInventory pattern at `src/components/types/type-form.tsx:73-82`

## 5) Algorithms & UI Flows

### Device List Render Flow

- **Flow:** Device list initial load and display
- **Steps:**
  1. Route mounts `/devices`, triggers `useGetConfigs()` query
  2. While `isLoading`, render skeleton table rows (6 placeholder rows)
  3. On success, map API response to DeviceConfig[] via custom hook (snake_case → camelCase)
  4. Read sort preference from localStorage (`iot-support-device-sort`)
  5. Apply sort to DeviceConfig[] in memory (client-side)
  6. Render table rows with MAC, Device Name, Entity ID, OTA Status columns
  7. Emit `list_loading` event with phase: ready, metadata includes visible count
- **States / transitions:**
  - `isLoading=true` → skeleton UI
  - `data.length=0` → empty state with "New Device" CTA
  - `data.length>0` → table with rows + header actions
- **Hotspots:** Large device lists (100+ rows) may slow client-side sort; defer optimization until proven necessary
- **Evidence:** ElectronicsInventory list flow at `src/components/types/type-list.tsx:45-72, 316-344`

### Sort Column Flow

- **Flow:** User clicks column header to sort
- **Steps:**
  1. Click handler on column header captures column name
  2. If column matches current sort column, toggle direction (asc ↔ desc)
  3. If different column, set new column with direction=asc
  4. Persist `{ column, direction }` to localStorage (`iot-support-device-sort`)
  5. Re-sort DeviceConfig[] in memory using column accessor and direction
  6. React re-renders table rows with new order
- **States / transitions:** Synchronous sort, no loading state; table updates immediately
- **Hotspots:** Multi-field sort not required; single column sort only
- **Evidence:** New pattern (not in ElectronicsInventory reference); requires custom sort utility

### Save Device Flow (New)

- **Flow:** User saves new device config from `/devices/new`
- **Steps:**
  1. User enters MAC address in input field
  2. User edits JSON in Monaco editor (template pre-filled)
  3. User clicks Save button
  4. Validate MAC address non-empty, JSON parseable (client-side)
  5. Emit `form` event phase: submit
  6. Call `usePutConfigsByMacAddress({ path: { mac_address: mac }, body: JSON.parse(json) })`
  7. On success: emit `form` event phase: success, show success toast, navigate to `/devices`
  8. On error: emit `form` event phase: error, show error toast with backend message, remain on editor
- **States / transitions:**
  - `isSubmitting=false` → Save button enabled
  - `isSubmitting=true` → Save button disabled with spinner
  - Success → navigate away
  - Error → remain on page, show toast
- **Hotspots:** JSON parse errors must surface clearly; invalid JSON should prevent submission
- **Evidence:** ElectronicsInventory form submission at `src/components/types/type-form.tsx:54-70`

### Save Device Flow (Edit with MAC rename)

- **Flow:** User edits device and changes MAC address
- **Steps:**
  1. Load existing config via `useGetConfigsByMacAddress({ path: { mac_address: originalMac } })`
  2. User changes MAC address input from `originalMac` to `newMac`
  3. User edits JSON in Monaco editor
  4. User clicks Save button
  5. Detect MAC change: `originalMac !== newMac`
  6. Execute two-step mutation:
     - Call `usePutConfigsByMacAddress({ path: { mac_address: newMac }, body: JSON.parse(json) })`
     - On success, call `useDeleteConfigsByMacAddress({ path: { mac_address: originalMac } })`
  7. On success: show success toast "Device renamed from {originalMac} to {newMac}", navigate to `/devices`
  8. On error (either step): show error toast, rollback if partial (delete new MAC if delete old failed)
- **States / transitions:**
  - Rename is atomic from user perspective; backend sees create-new + delete-old
  - If delete-old fails, new MAC persists (acceptable; user can manually delete orphan)
- **Hotspots:** Partial failure state (new created, old not deleted) requires clear error message
- **Evidence:** Inferred from "handles MAC rename (save new + delete old)" requirement

### Unsaved Changes Detection Flow

- **Flow:** User navigates away with unsaved changes
- **Steps:**
  1. Track dirty state: `isDirty = (currentMac !== originalMac || currentJson !== originalJson)`
  2. Attach `beforeunload` event listener when `isDirty=true`
  3. On browser tab close/refresh, show browser confirmation "You have unsaved changes"
  4. On navigation via TanStack Router link, intercept via `useBlocker` (or custom guard)
  5. Show Radix confirmation dialog "Discard unsaved changes?"
  6. If user confirms, allow navigation and reset dirty state
  7. If user cancels, remain on editor
- **States / transitions:**
  - Clean state → no warnings
  - Dirty state → beforeunload + navigation guards active
- **Hotspots:** TanStack Router navigation interception requires custom blocker or prompt pattern
- **Evidence:** ElectronicsInventory form dirty tracking at `src/components/types/type-form.tsx:54-70` (dialog-based, not full-page editor); adapt pattern for route-level blocker

### Delete Device Flow

- **Flow:** User deletes device from list
- **Steps:**
  1. User clicks delete button on table row
  2. Show Radix ConfirmDialog: "Delete device {macAddress}? This action cannot be undone."
  3. User clicks Confirm button
  4. Call `useDeleteConfigsByMacAddress({ path: { mac_address: mac } })`
  5. On success: emit `form` event (or custom event), show success toast "Device {mac} deleted", list refreshes via cache invalidation
  6. On error: show error toast with backend message, dialog closes, row remains
- **States / transitions:**
  - Dialog open → mutation pending → dialog closes regardless of outcome
  - Success → row disappears from table
  - Error → row remains, toast shows error
- **Hotspots:** Optimistic update not required; rely on cache invalidation to refresh list
- **Evidence:** ElectronicsInventory delete flow at `src/components/types/type-list.tsx:177-199`

## 6) Derived State & Invariants

- **Derived value:** sortedDevices
  - **Source:** Raw DeviceConfig[] from `useGetConfigs()` + SortPreference from localStorage
  - **Writes / cleanup:** Sort applied in useMemo; no writes, read-only transformation
  - **Guards:** If localStorage preference references invalid column, fall back to default (macAddress, asc)
  - **Invariant:** Sorted array length === raw array length; no filtering in sort, only reordering
  - **Evidence:** Pattern from `src/components/types/type-list.tsx:83-86` for sorted list

- **Derived value:** isDirty (editor state)
  - **Source:** `originalMac`, `currentMac`, `originalJson`, `currentJson` from editor component state
  - **Writes / cleanup:** Resets to false on successful save or user discard; no persistence
  - **Guards:** Must check both MAC and JSON for changes; whitespace-only JSON changes should not mark dirty (optional UX refinement)
  - **Invariant:** `isDirty=true` ⇒ beforeunload listener active; `isDirty=false` ⇒ no navigation guards
  - **Evidence:** ElectronicsInventory form dirty state at `src/components/types/type-form.tsx:54-70`

- **Derived value:** isValidJson (editor validation)
  - **Source:** Current JSON string from Monaco editor value
  - **Writes / cleanup:** Recomputed on every editor change; no persistence
  - **Guards:** JSON.parse() wrapped in try-catch; invalid JSON → Save button disabled
  - **Invariant:** `isValidJson=false` ⇒ Save button disabled; user cannot submit unparseable JSON
  - **Evidence:** New validation requirement; Monaco editor change handler must validate

- **Derived value:** hasUnsavedChanges (navigation guard)
  - **Source:** `isDirty` flag from editor state
  - **Writes / cleanup:** Triggers `useBlocker` hook from TanStack Router to intercept navigation
  - **Guards:** Guard only active when `hasUnsavedChanges=true` and route is editor
  - **Invariant:** Navigation blocked → user sees confirmation → navigation proceeds only on confirm
  - **Evidence:** TanStack Router blocker pattern (not in ElectronicsInventory reference); requires research/implementation

## 7) State Consistency & Async Coordination

- **Source of truth:** TanStack Query cache for DeviceConfig[] list; backend is authoritative
- **Coordination:**
  - Mutations (`PUT`, `DELETE`) invalidate `['getConfigs']` query keys to trigger list refresh
  - Editor loads single config via `['getConfigsByMacAddress', { mac }]` query key; independent from list cache
  - Sort state lives in localStorage; React state syncs on mount and user interaction
- **Async safeguards:**
  - React Query automatic request deduplication prevents double-fetches
  - Mutation `isLoading` state disables Save button during submission
  - No abort controllers needed for mutations (short-lived)
  - List query supports background refetch; no manual abort required
- **Instrumentation:**
  - `useListLoadingInstrumentation({ scope: 'devices.list' })` emits events: loading, ready, error
  - `useFormInstrumentation({ formId: 'DeviceEditor_new|edit|duplicate' })` emits events: open, submit, success, error
  - Tests rely on `waitForListLoading(page, 'devices.list', 'ready')` and `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success')`
- **Evidence:** ElectronicsInventory coordination at `src/components/types/type-list.tsx:93-132` for list instrumentation, `src/components/types/type-form.tsx:73-82` for form instrumentation

## 8) Errors & Edge Cases

- **Failure:** Backend returns 400 validation error on save (invalid JSON structure, missing required fields)
- **Surface:** Device editor route (`/devices/new`, `/devices/:macAddress`)
- **Handling:** Show error toast with backend error message; remain on editor, do not navigate; preserve user's JSON input
- **Guardrails:** Client-side JSON.parse() validation prevents unparseable JSON submission; backend validates schema
- **Evidence:** ElectronicsInventory error handling at `src/components/types/type-form.tsx:66-69`

- **Failure:** Network error during list fetch (GET /api/configs)
- **Surface:** Device list route (`/devices`)
- **Handling:** Show error state in list UI with error message; retry button optional (React Query auto-retries)
- **Guardrails:** Global error handler logs error; `list_loading` event emits with phase: error
- **Evidence:** ElectronicsInventory error state at `src/components/types/type-list.tsx:346-361`

- **Failure:** User attempts to save with duplicate MAC address (409 conflict)
- **Surface:** Device editor route (new or rename scenario)
- **Handling:** Show error toast "Device with MAC {mac} already exists"; remain on editor
- **Guardrails:** Backend enforces uniqueness; UI shows clear message
- **Evidence:** ElectronicsInventory duplicate handling at `tests/e2e/types/types-crud.spec.ts:65-83`

- **Failure:** User navigates away from editor with unsaved changes
- **Surface:** Device editor route
- **Handling:** Show confirmation dialog "Discard unsaved changes?"; block navigation until user confirms or cancels
- **Guardrails:** `isDirty` flag triggers navigation guard; beforeunload prevents browser close without warning
- **Evidence:** New pattern required; ElectronicsInventory uses dialog-based forms, not full-page editors with navigation guards

- **Failure:** User enters invalid MAC address format (if backend validates format)
- **Surface:** Device editor route
- **Handling:** Backend 400 error surfaces in toast; client-side validation optional (defer to backend)
- **Guardrails:** Save button enabled even with potentially invalid MAC; backend is authoritative
- **Evidence:** No client-side MAC validation in requirements; backend error message sufficient

- **Failure:** User closes browser tab with unsaved changes
- **Surface:** Device editor route
- **Handling:** Browser beforeunload confirmation: "You have unsaved changes. Leave page?"
- **Guardrails:** `isDirty` flag attaches beforeunload listener
- **Evidence:** Standard web API pattern; no framework-specific helper needed

- **Failure:** Delete fails due to backend constraint (e.g., device referenced elsewhere)
- **Surface:** Device list route, delete action
- **Handling:** Show error toast with backend error message; row remains in table
- **Guardrails:** ConfirmDialog closes regardless of outcome; error does not leave UI in broken state
- **Evidence:** ElectronicsInventory blocked delete at `tests/e2e/types/types-crud.spec.ts:37-63`

- **Failure:** MAC rename fails on delete-old step (new device created, old not deleted)
- **Surface:** Device editor route, edit with MAC change
- **Handling:** Show error toast "Device saved to {newMac}, but failed to delete {oldMac}: {error}"; navigate to list (partial success)
- **Guardrails:** User can manually delete orphaned old MAC from list; clear error message explains state
- **Evidence:** New edge case for MAC rename flow; requires explicit handling

- **Failure:** Empty device list (zero configs in backend)
- **Surface:** Device list route (`/devices`)
- **Handling:** Show empty state with "No devices configured" message and "New Device" button
- **Guardrails:** Not an error; normal state for new deployments
- **Evidence:** Requirement "empty state with create button when no devices", ElectronicsInventory pattern at `src/components/types/type-list.tsx:363-385`

- **Failure:** Monaco editor fails to load (script error, CDN unavailable if using CDN)
- **Surface:** Device editor route
- **Handling:** Show error message "Editor failed to load"; provide fallback textarea or block save
- **Guardrails:** React error boundary catches Monaco initialization errors
- **Evidence:** New integration; Monaco error handling not in ElectronicsInventory reference

## 9) Observability / Instrumentation

- **Signal:** list_loading (devices.list)
- **Type:** Instrumentation event
- **Trigger:** `useListLoadingInstrumentation` in DeviceList component; emits on query lifecycle transitions
- **Labels / fields:** `{ scope: 'devices.list', phase: 'loading'|'ready'|'error'|'aborted', metadata: { visible, total, status } }`
- **Consumer:** Playwright `waitForListLoading(page, 'devices.list', 'ready')` helper
- **Evidence:** Pattern from `src/components/types/type-list.tsx:93-132`, documented at `docs/contribute/architecture/test_instrumentation.md:23`

- **Signal:** form (DeviceEditor_new, DeviceEditor_edit, DeviceEditor_duplicate)
- **Type:** Instrumentation event
- **Trigger:** `useFormInstrumentation` in DeviceEditor component; emits on open, submit, success, error, validation_error phases
- **Labels / fields:** `{ formId, phase, fields?, metadata? }`
- **Consumer:** Playwright `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success')` assertions
- **Evidence:** Pattern from `src/components/types/type-form.tsx:73-82`, documented at `docs/contribute/architecture/test_instrumentation.md:18`

- **Signal:** toast (success/error notifications)
- **Type:** Instrumentation event
- **Trigger:** Toast context provider emits on `showSuccess()`, `showError()`, `showException()` calls
- **Labels / fields:** `{ level: 'success'|'error'|'warning'|'info', message, code? }`
- **Consumer:** Playwright assertions on toast visibility and content
- **Evidence:** ElectronicsInventory toast instrumentation (inferred from test usage at `tests/e2e/types/types-crud.spec.ts:56, 77`)

- **Signal:** data-testid attributes (table rows, buttons, inputs)
- **Type:** DOM attributes for test selectors
- **Trigger:** Rendered by components; static attributes on key elements
- **Labels / fields:**
  - `devices.list.table` – table container
  - `devices.list.row` – table row (repeated)
  - `devices.list.header.new-device` – New Device button
  - `devices.editor.mac-input` – MAC address input field
  - `devices.editor.json-editor` – Monaco editor container
  - `devices.editor.save` – Save button
  - `devices.editor.cancel` – Cancel button
  - `devices.editor.duplicate` – Duplicate button (edit mode only)
  - `devices.delete.confirm-dialog` – Delete confirmation dialog
- **Consumer:** Playwright page object locators
- **Evidence:** ElectronicsInventory testid pattern at `src/components/types/type-list.tsx:205, 213, 240, 266`

- **Signal:** Route instrumentation (navigation events)
- **Type:** Instrumentation event
- **Trigger:** TanStack Router transitions emit `route` events via `src/lib/test/router-instrumentation.ts`
- **Labels / fields:** `{ from, to, params? }`
- **Consumer:** Playwright tests asserting navigation after save/cancel
- **Evidence:** Documented at `docs/contribute/architecture/test_instrumentation.md:16`

## 10) Lifecycle & Background Work

- **Hook / effect:** useEffect for sort preference persistence
- **Trigger cadence:** On mount (read from localStorage), on sort change (write to localStorage)
- **Responsibilities:** Sync UI sort state with localStorage; no network calls
- **Cleanup:** None required; localStorage operations are synchronous
- **Evidence:** New utility module for sort preferences; pattern inferred from requirement

- **Hook / effect:** useEffect for beforeunload listener
- **Trigger cadence:** Attach when `isDirty=true`, detach when `isDirty=false` or component unmounts
- **Responsibilities:** Warn user before browser tab close with unsaved changes
- **Cleanup:** Remove event listener on unmount or when `isDirty` becomes false
- **Evidence:** Standard web API pattern; dependency array must include `isDirty`

- **Hook / effect:** useEffect for form instrumentation (open event)
- **Trigger cadence:** On component mount when editor route is active
- **Responsibilities:** Emit `form` event with phase: open, formId, initial field snapshot
- **Cleanup:** None; event emission is fire-and-forget
- **Evidence:** ElectronicsInventory form instrumentation at `src/components/types/type-form.tsx:73-82`

- **Hook / effect:** useBlocker for navigation guard
- **Trigger cadence:** Active when `isDirty=true` and user attempts navigation
- **Responsibilities:** Intercept TanStack Router navigation, show confirmation dialog, allow or block based on user choice
- **Cleanup:** None; blocker automatically deactivates when condition becomes false
- **Evidence:** TanStack Router useBlocker hook (not in ElectronicsInventory reference); requires implementation research

- **Hook / effect:** Monaco editor initialization
- **Trigger cadence:** On component mount
- **Responsibilities:** Load Monaco editor, set language to JSON, apply theme and options
- **Cleanup:** Dispose editor instance on unmount to prevent memory leaks
- **Evidence:** Monaco React component handles lifecycle; minimal custom cleanup needed

## 11) Security & Permissions

No authentication, authorization, or role-based access control in scope for Phase B. The application is deployed in a trusted environment (internal tooling for IoT device management). All users have full CRUD permissions on all device configs.

**Residual risk:** MAC addresses and device configs are visible to all users; no audit logging of changes. Acceptable for internal tooling; defer security enhancements to future phases if multi-tenant or external deployment is required.

## 12) UX / UI Impact

- **Entry point:** Sidebar link "Device Configs" at `/devices` (already present from Phase A)
- **Change:** Replace placeholder content with functional device list table
- **User interaction:** Users can view all device configs in a sortable table, click column headers to sort, click New Device to create, click Edit/Delete buttons on rows
- **Dependencies:** None; Phase A routing and app shell complete
- **Evidence:** Placeholder at `src/routes/devices/index.tsx:1-18`

- **Entry point:** "New Device" button in list header, navigates to `/devices/new`
- **Change:** Create new route with empty form (MAC input + Monaco JSON editor)
- **User interaction:** Users enter MAC address, edit JSON template, click Save to create or Cancel to discard
- **Dependencies:** Monaco editor package (`@monaco-editor/react`) must be installed
- **Evidence:** Requirement "New Device button in header navigates to /devices/new"

- **Entry point:** Edit button on table row, navigates to `/devices/:macAddress`
- **Change:** Create new route with pre-filled form (MAC input editable, JSON loaded from backend)
- **User interaction:** Users edit MAC or JSON, click Save (with rename handling if MAC changed), Cancel to discard, or Duplicate to copy to new device
- **Dependencies:** None; uses existing generated API hooks
- **Evidence:** Requirement "Edit button on each row navigates to /devices/:macAddress"

- **Entry point:** Duplicate button on editor (edit mode only), navigates to `/devices/:macAddress/duplicate`
- **Change:** Create new route with empty MAC input, JSON pre-filled from source device
- **User interaction:** Users enter new MAC address, optionally edit copied JSON, click Save to create
- **Dependencies:** None; route receives source MAC via path param, fetches config, resets MAC field
- **Evidence:** Requirement "Duplicate route: empty MAC input, copied JSON from source, Save/Cancel buttons only"

- **Entry point:** Delete button on table row
- **Change:** Show Radix confirmation dialog (not browser confirm) with device MAC in message
- **User interaction:** Users click Delete, see "Delete device {macAddress}?" dialog, confirm or cancel
- **Dependencies:** `useConfirm` hook, ConfirmDialog component
- **Evidence:** Requirement "Delete confirmation: styled Radix dialog (not browser confirm), shows device MAC"

- **Entry point:** Navigation away from editor with unsaved changes
- **Change:** Block navigation with confirmation dialog "Discard unsaved changes?"
- **User interaction:** Users see dialog, choose to discard (navigate away) or cancel (stay on editor)
- **Dependencies:** TanStack Router blocker, ConfirmDialog component
- **Evidence:** Requirement "Unsaved changes: beforeunload warning + confirmation dialog on navigation"

- **Entry point:** Save success/error outcomes
- **Change:** Show toast notifications (dark mode styled) in top-right corner
- **User interaction:** Users see auto-dismissing toast with success message or persistent error toast with backend error details
- **Dependencies:** ToastContext provider, Toast UI component
- **Evidence:** Requirement "Toast system: success/error/info variants, auto-dismiss, dark mode styling"

## 13) Deterministic Test Plan

### Device List Display

- **Surface:** `/devices` route, DeviceList component
- **Scenarios:**
  - **Given** backend has 3 device configs, **When** user navigates to `/devices`, **Then** table displays 3 rows with MAC Address, Device Name, Entity ID, OTA Status columns
  - **Given** device with enableOta=true, **When** list renders, **Then** OTA Status column shows check icon (✓)
  - **Given** device with enableOta=false, **When** list renders, **Then** OTA Status column shows cross icon (✕)
  - **Given** device with enableOta=null, **When** list renders, **Then** OTA Status column is empty
  - **Given** backend has zero devices, **When** user navigates to `/devices`, **Then** empty state displays with "No devices configured" and "New Device" button
  - **Given** list is loading, **When** query is pending, **Then** skeleton loader displays 6 placeholder rows
- **Instrumentation / hooks:**
  - `data-testid="devices.list.table"` on table container
  - `data-testid="devices.list.row"` on each row
  - `data-testid="devices.list.empty"` on empty state
  - `data-testid="devices.list.loading"` on skeleton loader
  - `waitForListLoading(page, 'devices.list', 'ready')` in tests
- **Gaps:** None; all list display scenarios covered
- **Evidence:** ElectronicsInventory list test at `tests/e2e/types/type-list.spec.ts`

### Table Sorting

- **Surface:** `/devices` route, column headers
- **Scenarios:**
  - **Given** user is on device list, **When** user clicks "MAC Address" column header, **Then** table sorts by MAC ascending, preference persists to localStorage
  - **Given** table sorted by MAC ascending, **When** user clicks "MAC Address" header again, **Then** table sorts by MAC descending
  - **Given** table sorted by MAC, **When** user clicks "Device Name" header, **Then** table sorts by Device Name ascending
  - **Given** table sorted, **When** user refreshes page, **Then** table loads with persisted sort preference
- **Instrumentation / hooks:**
  - `data-testid="devices.list.header.mac-address"` on sortable column header
  - `data-sort-column` and `data-sort-direction` attributes on table for test assertions
- **Gaps:** None; sort scenarios comprehensive
- **Evidence:** New feature; pattern inferred from requirements

### Create New Device

- **Surface:** `/devices/new` route, DeviceEditor component
- **Scenarios:**
  - **Given** user clicks "New Device" button, **When** navigation completes, **Then** editor route displays with empty MAC input and template JSON `{"deviceName": "", "deviceEntityId": "", "enableOTA": false}`
  - **Given** user is on new device editor, **When** user enters MAC "AA:BB:CC:DD:EE:FF" and edits JSON, clicks Save, **Then** backend receives PUT request, success toast shows, navigates to `/devices`, list includes new device
  - **Given** user is on new device editor, **When** user clicks Cancel, **Then** navigates to `/devices` without saving
  - **Given** user enters invalid JSON (missing brace), **When** user attempts to save, **Then** Save button is disabled
- **Instrumentation / hooks:**
  - `data-testid="devices.editor.mac-input"`
  - `data-testid="devices.editor.json-editor"`
  - `data-testid="devices.editor.save"`
  - `data-testid="devices.editor.cancel"`
  - `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_new' && evt.phase === 'success')`
- **Gaps:** None; create flow fully covered
- **Evidence:** ElectronicsInventory create test at `tests/e2e/types/create-type.spec.ts`

### Edit Existing Device

- **Surface:** `/devices/:macAddress` route, DeviceEditor component
- **Scenarios:**
  - **Given** device with MAC "11:22:33:44:55:66" exists, **When** user clicks Edit button, **Then** editor route displays with MAC input pre-filled (editable), JSON loaded from backend
  - **Given** user edits JSON (changes deviceName), **When** user clicks Save without changing MAC, **Then** backend receives PUT to same MAC, success toast shows, navigates to `/devices`
  - **Given** user is on edit editor, **When** user clicks Duplicate button, **Then** navigates to `/devices/:macAddress/duplicate` with copied JSON
  - **Given** user is on edit editor with unsaved changes, **When** user clicks Cancel, **Then** confirmation dialog "Discard unsaved changes?" appears, user confirms, navigates to `/devices`
- **Instrumentation / hooks:**
  - `data-testid="devices.editor.duplicate"` (only on edit mode)
  - `data-testid="devices.editor.unsaved-changes-dialog"`
  - `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success')`
- **Gaps:** None; edit flow comprehensive
- **Evidence:** ElectronicsInventory edit test at `tests/e2e/types/types-crud.spec.ts:5-15`

### MAC Address Rename

- **Surface:** `/devices/:macAddress` route, DeviceEditor component
- **Scenarios:**
  - **Given** device with MAC "AA:AA:AA:AA:AA:AA" exists, **When** user edits MAC to "BB:BB:BB:BB:BB:BB" and clicks Save, **Then** backend receives PUT to new MAC, DELETE to old MAC, success toast shows "Device renamed from AA:AA:AA:AA:AA:AA to BB:BB:BB:BB:BB:BB", navigates to `/devices`, list shows new MAC only
  - **Given** user renames MAC but backend DELETE fails, **When** save completes, **Then** error toast shows "Device saved to {newMac}, but failed to delete {oldMac}: {error}", navigates to `/devices`, both MACs visible in list
- **Instrumentation / hooks:**
  - Test factory creates source device, test edits MAC, asserts both PUT and DELETE requests via network interception or backend logs
  - `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success')`
- **Gaps:** Partial failure rollback not required; orphaned old MAC acceptable with clear error message
- **Evidence:** New flow; derived from requirement "handles MAC rename (save new + delete old)"

### Duplicate Device

- **Surface:** `/devices/:macAddress/duplicate` route, DeviceEditor component
- **Scenarios:**
  - **Given** device with MAC "11:22:33:44:55:66" exists, **When** user clicks Duplicate button on edit page, **Then** duplicate route displays with empty MAC input, JSON copied from source
  - **Given** user is on duplicate editor, **When** user enters new MAC "77:88:99:AA:BB:CC" and clicks Save, **Then** backend receives PUT to new MAC, success toast shows, navigates to `/devices`, list includes both original and duplicate
  - **Given** user is on duplicate editor, **When** user clicks Cancel, **Then** navigates to `/devices` without saving
- **Instrumentation / hooks:**
  - `data-testid="devices.editor.duplicate"` (Duplicate button only on edit mode, not on duplicate route)
  - `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_duplicate' && evt.phase === 'success')`
- **Gaps:** None; duplicate flow covered
- **Evidence:** New flow; derived from requirement "Duplicate route: empty MAC input, copied JSON from source"

### Delete Device

- **Surface:** `/devices` route, delete button on table row
- **Scenarios:**
  - **Given** device with MAC "11:22:33:44:55:66" exists, **When** user clicks Delete button, **Then** confirmation dialog displays "Delete device 11:22:33:44:55:66?"
  - **Given** confirmation dialog open, **When** user clicks Confirm, **Then** backend receives DELETE request, success toast shows "Device 11:22:33:44:55:66 deleted", list refreshes, row removed
  - **Given** confirmation dialog open, **When** user clicks Cancel, **Then** dialog closes, no backend request, row remains
  - **Given** delete fails with backend error, **When** user confirms delete, **Then** error toast shows backend message, row remains in list
- **Instrumentation / hooks:**
  - `data-testid="devices.delete.confirm-dialog"`
  - `data-testid="devices.list.row.delete-button"`
  - `waitTestEvent(page, 'toast', evt => evt.level === 'success' && evt.message.includes('deleted'))`
- **Gaps:** None; delete flow comprehensive
- **Evidence:** ElectronicsInventory delete test at `tests/e2e/types/types-crud.spec.ts:17-25`

### Unsaved Changes Warning

- **Surface:** `/devices/new`, `/devices/:macAddress`, `/devices/:macAddress/duplicate` routes
- **Scenarios:**
  - **Given** user edits JSON on editor, **When** user clicks browser back button or sidebar link, **Then** confirmation dialog "Discard unsaved changes?" appears, user confirms to navigate or cancels to stay
  - **Given** user edits JSON on editor, **When** user attempts to close browser tab, **Then** browser beforeunload warning shows "You have unsaved changes"
  - **Given** user saves successfully, **When** editor navigates to list, **Then** no unsaved changes warning (dirty state reset)
- **Instrumentation / hooks:**
  - `data-testid="devices.editor.unsaved-changes-dialog"`
  - Test triggers navigation via sidebar click, asserts dialog appears
  - Test cannot assert beforeunload (browser restriction), but can verify listener attachment via test hook
- **Gaps:** Beforeunload listener attachment verified via test hook, but browser warning cannot be automated; manual verification required
- **Evidence:** New flow; derived from requirement "Unsaved changes: beforeunload warning + confirmation dialog on navigation"

### Error Handling

- **Surface:** All editor routes and list route
- **Scenarios:**
  - **Given** backend returns 400 validation error on save, **When** user clicks Save, **Then** error toast shows backend message, editor remains open with user's input preserved
  - **Given** backend returns 409 conflict (duplicate MAC), **When** user saves, **Then** error toast shows "Device with MAC {mac} already exists", editor remains open
  - **Given** backend returns network error on list fetch, **When** list loads, **Then** error state displays with retry option (or auto-retry via React Query)
  - **Given** Monaco editor fails to initialize, **When** editor route loads, **Then** error message displays "Editor failed to load"
- **Instrumentation / hooks:**
  - `data-testid="devices.list.error"` on list error state
  - `waitTestEvent(page, 'toast', evt => evt.level === 'error')`
  - `waitTestEvent(page, 'form', evt => evt.phase === 'error')`
- **Gaps:** Monaco initialization error handling requires error boundary; defer to implementation if complexity arises
- **Evidence:** ElectronicsInventory error tests at `tests/e2e/types/types-crud.spec.ts:37-63, 65-83`

## 14) Implementation Slices

This feature set is moderate in size; recommend implementing in 3 sequential slices.

### Slice 1: Foundation (UI components, hooks, routing)

- **Goal:** Establish device list UI, custom hooks, and routing skeleton
- **Touches:**
  - Create `src/hooks/use-devices.ts` (wrapper hooks for API)
  - Create `src/hooks/use-confirm.ts` (confirmation dialog hook)
  - Create `src/hooks/use-toast.ts` (toast notification hook)
  - Create `src/contexts/toast-context.tsx` (global toast provider)
  - Copy `src/components/ui/dialog.tsx` from ElectronicsInventory, adapt for dark mode
  - Copy `src/components/ui/toast.tsx` from ElectronicsInventory, adapt for dark mode
  - Verify or create `src/components/ui/button.tsx`, `src/components/ui/input.tsx`, `src/components/ui/skeleton.tsx`, `src/components/ui/empty-state.tsx`
  - Create `src/lib/utils/sort-preferences.ts` (localStorage sort utility)
  - Update `src/routes/__root.tsx` to integrate ToastContext provider
  - Create `src/routes/devices/index.tsx` (replace placeholder with DeviceList component stub)
  - Create `src/routes/devices/new.tsx` (route module stub)
  - Create `src/routes/devices/$macAddress.tsx` (route module stub)
  - Create `src/routes/devices/$macAddress/duplicate.tsx` (route module stub)
- **Dependencies:** None; foundational work
- **Verification:** Navigate to `/devices`, see empty state or skeleton loader (no backend data yet); toast and dialog components render in isolation

### Slice 2: Device List & CRUD (table, editor, save/delete)

- **Goal:** Deliver full device list with sortable table, Monaco editor, save/delete flows
- **Touches:**
  - Install `@monaco-editor/react` dependency via `pnpm add @monaco-editor/react`
  - Create `src/components/devices/device-list-table.tsx` (sortable table component)
  - Implement DeviceList component in `src/routes/devices/index.tsx` with list loading instrumentation
  - Create `src/components/devices/device-editor.tsx` (Monaco editor with validation, dirty state tracking)
  - Implement DeviceEditor in `src/routes/devices/new.tsx`, `src/routes/devices/$macAddress.tsx`, `src/routes/devices/$macAddress/duplicate.tsx`
  - Implement MAC rename logic (save new + delete old) in save handler
  - Implement unsaved changes detection (beforeunload listener, navigation blocker)
  - Wire up delete flow with confirmation dialog
  - Add all `data-testid` attributes per instrumentation plan (section 9)
  - Integrate `useListLoadingInstrumentation` for device list
  - Integrate `useFormInstrumentation` for device editor (new, edit, duplicate modes)
- **Dependencies:** Slice 1 complete
- **Verification:** Manual testing of all CRUD flows; check toast notifications, navigation guards, Monaco editor rendering

### Slice 3: Playwright Tests & Coverage

- **Goal:** Deliver comprehensive test coverage with API factories and page objects
- **Touches:**
  - Create `tests/api/factories/devices.ts` (API factory for device config creation/deletion)
  - Integrate devices factory into test data bundle (`tests/support/fixtures.ts`)
  - Create `tests/e2e/devices/DevicesPage.ts` (page object with locators and actions)
  - Add `devices` fixture to `tests/support/fixtures.ts`
  - Create `tests/e2e/devices/devices-crud.spec.ts` (create, edit, delete, sort scenarios)
  - Create `tests/e2e/devices/device-editor.spec.ts` (Monaco editor, MAC rename, duplicate, unsaved changes scenarios)
  - Create `tests/e2e/devices/device-errors.spec.ts` (validation errors, network errors, conflict errors)
- **Dependencies:** Slice 2 complete; UI must emit instrumentation events
- **Verification:** Run `pnpm playwright test tests/e2e/devices/` – all specs pass, no console errors, `testing/no-route-mocks` lint rule green

## 15) Risks & Open Questions

### Risks

- **Risk:** Monaco editor bundle size increases frontend load time significantly
- **Impact:** Slower initial page load for editor routes; acceptable for internal tooling
- **Mitigation:** Defer Monaco loading via dynamic import (lazy load on editor route); monitor bundle size via Vite build output

- **Risk:** TanStack Router navigation blocker (`useBlocker`) may not support confirmation dialogs in current version
- **Impact:** Unsaved changes guard may require custom implementation or library upgrade
- **Mitigation:** Research TanStack Router blocker API during Slice 2; fallback to `window.confirm` if Radix dialog integration is complex (trade-off: browser confirm vs. styled dialog)

- **Risk:** MAC rename flow partial failure (new device created, old not deleted) leaves orphaned config
- **Impact:** User confusion; requires manual cleanup
- **Mitigation:** Clear error message explains state; acceptable for internal tooling; consider backend transaction if becomes frequent issue

- **Risk:** Large device lists (100+ configs) may slow client-side sort/render
- **Impact:** UI lag on sort operations
- **Mitigation:** Defer optimization until proven necessary; if required, add virtualization (`react-window`) or backend-side sorting in future phase

- **Risk:** Test flakiness due to Monaco editor async initialization
- **Impact:** Playwright tests timeout waiting for editor ready state
- **Mitigation:** Add explicit wait for Monaco editor `data-state="ready"` attribute after mount; emit instrumentation event when editor initializes

### Open Questions

- **Question:** Should MAC address input enforce format validation (e.g., XX:XX:XX:XX:XX:XX pattern)?
- **Why it matters:** Improves UX by catching errors early, but adds frontend validation complexity
- **Owner / follow-up:** Defer to backend validation; if users frequently enter invalid MACs, add client-side regex validation in future iteration

- **Question:** Should duplicate operation preserve original MAC in metadata or URL for audit trail?
- **Why it matters:** Helps trace config lineage if debugging issues
- **Owner / follow-up:** Not required for MVP; defer to future phase if audit logging is needed

- **Question:** Should sort preferences be scoped per-user (if multi-user deployment) or global (localStorage)?
- **Why it matters:** Multi-user deployments may want user-specific sort preferences
- **Owner / follow-up:** Current design uses browser localStorage (single-user scope); if backend user accounts added, migrate to backend preference storage

- **Question:** Should Monaco editor support schema validation (JSON schema for device config structure)?
- **Why it matters:** Prevents submission of malformed configs that backend will reject
- **Owner / follow-up:** Backend validation is authoritative; defer schema validation to future phase unless validation errors become frequent pain point

## 16) Confidence

**Confidence:** High — The feature set is well-defined with explicit requirements, ElectronicsInventory provides strong reference patterns for most components (list, form, toast, dialog, testing), and the generated API hooks are already available. The primary unknowns are Monaco editor integration (new dependency) and TanStack Router navigation blocker (may require research), but both have fallback options (textarea for Monaco, browser confirm for blocker) if complexity exceeds estimates. Test infrastructure from Phase A is proven, so Playwright coverage should follow established patterns with minimal friction.
