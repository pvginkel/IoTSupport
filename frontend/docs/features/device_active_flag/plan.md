# Device Active Flag — Frontend Technical Plan

## 0) Research Log & Findings

**Searched areas:**

- `src/hooks/use-devices.ts` — Domain models (`DeviceSummary`, `Device`), transform functions (`transformDeviceSummary`, `transformDeviceResponse`), and mutation hooks (`useCreateDevice`, `useUpdateDevice`). The `active` field is absent from all models and transforms. The `useUpdateDevice` hook sends only `{ config }` and never `active`. The `useCreateDevice` hook sends `{ device_model_id, config }`.
- `src/lib/api/generated/types.ts` — Confirmed `active: boolean` is present in `DeviceSummarySchema` (line 1554), `DeviceResponseSchema` (line 1927), and `DeviceUpdateSchema` (line 2058). The `DeviceCreateSchema` does **not** include `active` (only `config` + `device_model_id`).
- `src/components/devices/device-list-table.tsx` — Table columns end with OTA Status, Last Core Dump, then Actions. No `active` column exists.
- `src/components/devices/device-configuration-tab.tsx` — Edit form with Keycloak section, model display, and JSON editor. No `active` toggle.
- `src/components/devices/device-editor.tsx` — New/duplicate form with model select and JSON editor. No `active` toggle.
- `src/hooks/use-device-form.ts` — Form hook managing `jsonConfig`, `selectedModelId`, validation, dirty state, and save flow. No `active` state tracked. The `useUpdateDevice` wrapper sends `{ id, config }`.
- `src/lib/utils/sort-preferences.ts` — Column union type does not include `active`.
- `src/components/rotation/rotation-dashboard.tsx` — Renders only `healthy`, `warning`, `critical` panels. The `inactive` array from the API is never consumed. No changes needed.
- `src/hooks/use-rotation.ts` — Transforms only `healthy`, `warning`, `critical` arrays from the dashboard response. The `inactive` array is ignored.
- `tests/e2e/devices/devices-crud.spec.ts` — Existing CRUD specs. No coverage for `active` column or toggle.
- `tests/e2e/devices/DevicesPage.ts` — Page object with list/editor locators. No `active`-related locators.
- `tests/api/factories/devices.ts` — `DevicesFactory.create()` and `CreatedDevice` interface. No `active` field in options or return type. No `update()` method exists.
- `src/components/primitives/` — No switch/toggle/checkbox component exists. A new primitive or inline implementation will be needed for the toggle.

**Key findings:**

1. The generated API types already include `active` everywhere needed. No `pnpm generate:api` step is required.
2. The `DeviceCreateSchema` does **not** include `active` — the backend presumably defaults it to `true`. The new device form should still show the toggle (defaulting to `true`) for visibility, but the value does not need to be sent in the create payload.
3. The `DeviceUpdateSchema` **requires** `active` alongside `config`. The `useUpdateDevice` hook currently only sends `config`, which would break once the backend enforces the required field. This is the highest-priority fix.
4. No switch/toggle primitive exists in the component library. A simple `<button role="switch">` with Tailwind styling will suffice and match the project's "extend existing abstractions" guideline.
5. The `SortPreference` column union needs `active` added if the new column should be sortable (the brief says "read-only slider/checkbox" but does not mention sorting; however, all existing columns are sortable, so consistency suggests adding it).

**Conflicts resolved:** None. All changes are additive.

---

## 1) Intent & Scope

**User intent**

Surface the backend's `active` boolean field on the device list table (read-only), the device edit form (interactive), and the new device form (read-only indicator showing the default value of `true`, since `DeviceCreateSchema` does not accept `active`). Include the field in the update mutation payload. Leave the rotation dashboard unchanged.

**Prompt quotes**

- "Add a read-only slider/checkbox 'Active' column to the device list table, positioned as the last column before 'Actions'"
- "Add an interactive 'Active' toggle/switch to the device configuration (edit) screen, placed above the JSON editor"
- "Add the same 'Active' toggle/switch to the new device form, defaulting to true" (Note: Since `DeviceCreateSchema` does not accept `active`, the new device form shows a read-only indicator fixed at `true`)
- "Include active in the device update mutation payload"
- "No changes to the rotation dashboard -- inactive devices should remain completely hidden"

**In scope**

- Add `active` to `DeviceSummary` and `Device` domain models and their transform functions
- Add read-only "Active" column to device list table (last column before Actions)
- Add interactive "Active" toggle to device edit form (above JSON editor)
- Add read-only "Active" indicator to new device form (fixed at `true`, non-interactive since `DeviceCreateSchema` does not accept `active`)
- Include `active` in the device update mutation payload
- Update the `useDeviceForm` hook to manage `active` state and dirty tracking
- Add `data-testid` attributes and page object locators for the new UI elements
- Playwright tests covering the new column and toggle
- Update the test factory `CreatedDevice` to include `active`

**Out of scope**

- Rotation dashboard changes (confirmed no changes needed)
- Backend API changes (the field already exists in all schemas)
- Regenerating the OpenAPI client (`active` is already in generated types)
- Filtering the device list by active status (not requested)
- Bulk active/inactive toggling

**Assumptions / constraints**

- The backend defaults `active` to `true` when creating a device (the `DeviceCreateSchema` does not accept `active`).
- The `DeviceUpdateSchema` requires both `active` and `config` — the current frontend omission of `active` may already cause 422 errors in environments with strict validation. This plan treats adding `active` to the update payload as a correctness fix.
- No existing switch/toggle primitive exists; a minimal inline implementation using a `<button role="switch">` with Tailwind classes is appropriate. If reuse emerges later, it can be extracted.

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Add `active` boolean to `DeviceSummary` and `Device` domain models and their transform functions in `use-devices.ts`
- [ ] Add a read-only slider/checkbox "Active" column to the device list table, positioned as the last column before "Actions"
- [ ] Add an interactive "Active" toggle/switch to the device configuration (edit) screen, placed above the JSON editor
- [ ] Add an "Active" indicator to the new device form, showing the default value of `true` (read-only, since the backend always creates devices as active)
- [ ] Include `active` in the device update mutation payload
- [ ] No changes to the rotation dashboard — inactive devices should remain completely hidden
- [ ] Playwright tests cover the new column and toggle

---

## 2) Affected Areas & File Map

- Area: `src/hooks/use-devices.ts` — Domain models and transforms
- Why: Add `active` field to `DeviceSummary` and `Device` interfaces and their transform functions. Update `useUpdateDevice` to accept and send `active` in the mutation payload.
- Evidence: `src/hooks/use-devices.ts:17-27` — `DeviceSummary` interface missing `active`. `src/hooks/use-devices.ts:54-76` — `transformDeviceSummary` omits `active`. `src/hooks/use-devices.ts:196-229` — `useUpdateDevice` sends only `{ config }`, but `DeviceUpdateSchema` requires `{ active, config }`.

- Area: `src/hooks/use-device-form.ts` — Form state hook
- Why: Add `active` state, expose getter/setter, include `active` in dirty tracking, pass `active` to `useUpdateDevice`.
- Evidence: `src/hooks/use-device-form.ts:49-50` — State declarations (need `active` alongside `selectedModelId`). `src/hooks/use-device-form.ts:62-69` — `isDirty` logic (needs `active` comparison). `src/hooks/use-device-form.ts:114-169` — `handleSave` callback (needs to pass `active` to update mutation).

- Area: `src/components/devices/device-list-table.tsx` — Device list table
- Why: Add read-only "Active" column between "Last Core Dump" and "Actions".
- Evidence: `src/components/devices/device-list-table.tsx:104-111` — Column headers. `src/components/devices/device-list-table.tsx:138-147` — Row cells ending at "Last Core Dump" before Actions.

- Area: `src/components/devices/device-configuration-tab.tsx` — Edit form
- Why: Add interactive "Active" toggle above the JSON editor section.
- Evidence: `src/components/devices/device-configuration-tab.tsx:75-108` — JSON editor section. The toggle should be inserted before this block.

- Area: `src/components/devices/device-editor.tsx` — New/duplicate form
- Why: Add interactive "Active" toggle between model selection and JSON editor.
- Evidence: `src/components/devices/device-editor.tsx:99-163` — Form body with model select then JSON editor.

- Area: `src/lib/utils/sort-preferences.ts` — Sort column type
- Why: Add `'active'` to the `SortPreference['column']` union so the new column is sortable.
- Evidence: `src/lib/utils/sort-preferences.ts:3-6` — Column union type, `validColumns` array at line 21.

- Area: `tests/e2e/devices/DevicesPage.ts` — Page object
- Why: Add locators for the Active column cells and the Active toggle in editor forms.
- Evidence: `tests/e2e/devices/DevicesPage.ts:87-118` — List locators. `tests/e2e/devices/DevicesPage.ts:120-155` — Editor locators.

- Area: `tests/api/factories/devices.ts` — Test factory
- Why: Add `active: boolean` to `CreatedDevice` interface return (from `data.active` in create/get responses). Add an `update()` method to enable toggling active in tests. The `update()` method signature: `update(options: { id: number; active: boolean; config: string }): Promise<CreatedDevice>`. It calls `PUT /api/devices/{device_id}` with `{ active, config }` and returns the updated device. Both `active` and `config` are required because `DeviceUpdateSchema` mandates both fields. Test usage: `await devices.update({ id: device.id, active: false, config: device.config })`.
- Evidence: `tests/api/factories/devices.ts:14-24` — `CreatedDevice` interface missing `active`. `tests/api/factories/devices.ts:82-118` — `create()` method return mapping. `src/lib/api/generated/types.ts:2053-2064` — `DeviceUpdateSchema` requires `{ active, config }`.

- Area: `tests/e2e/devices/devices-crud.spec.ts` — Playwright specs
- Why: Add test scenarios for Active column visibility, Active toggle in edit form, and Active toggle in new device form.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:1-497` — Existing CRUD tests to extend with new scenarios.

---

## 3) Data Model / Contracts

- Entity / contract: `DeviceSummary` (UI domain model for list view)
- Shape: Add `active: boolean` field
- Mapping: `apiDevice.active` (already boolean in API) maps directly to `active` on the domain model
- Evidence: `src/hooks/use-devices.ts:17-27` (current interface), `src/lib/api/generated/types.ts:1549-1554` (API schema with `active: boolean`)

- Entity / contract: `Device` (UI domain model for detail/edit view)
- Shape: Add `active: boolean` field
- Mapping: `apiDevice.active` maps directly to `active` (no snake_case conversion needed since the field name is a single word)
- Evidence: `src/hooks/use-devices.ts:30-51` (current interface), `src/lib/api/generated/types.ts:1922-1927` (API schema with `active: boolean`)

- Entity / contract: `useUpdateDevice` mutation variables
- Shape: Change from `{ id: number; config: string }` to `{ id: number; config: string; active: boolean }`
- Mapping: Variables `active` maps to `body.active` in `DeviceUpdateSchema`
- Evidence: `src/hooks/use-devices.ts:212-228` (current mutation wrapper), `src/lib/api/generated/types.ts:2053-2063` (`DeviceUpdateSchema` requires `active` + `config`)

- Entity / contract: `useDeviceForm` options and state
- Shape: Add `initialActive?: boolean` to `UseDeviceFormOptions`. Add `active: boolean` and `setActive` to returned state. The `handleSave` function passes `active` in the update payload.
- Mapping: Passed through from `device.active` in the edit route, defaulting to `true` in new/duplicate mode.
- Evidence: `src/hooks/use-device-form.ts:16-26` (options interface), `src/hooks/use-device-form.ts:207-233` (return object)

---

## 4) API / Integration Surface

- Surface: `PUT /api/devices/{device_id}` / `usePutDevicesByDeviceId`
- Inputs: `{ active: boolean, config: string }` (body), `{ device_id: number }` (path)
- Outputs: `DeviceResponseSchema` (full device details including `active`). Post-mutation: invalidates `getDevices` and `getDevicesByDeviceId` query keys.
- Errors: 400 (Bad Request — invalid payload), 404 (device not found). Errors surface through the existing `showError` toast in `useUpdateDevice`.
- Evidence: `src/hooks/use-devices.ts:196-229` (current hook), `src/lib/api/generated/types.ts:2053-2064` (schema)

- Surface: `GET /api/devices` / `useGetDevices`
- Inputs: None
- Outputs: `DeviceListResponseSchema` containing `devices[]` with `active: boolean` on each summary. No changes to the hook — only the transform needs updating.
- Errors: Standard error handling via React Query.
- Evidence: `src/hooks/use-devices.ts:126-138` (hook), `src/lib/api/generated/types.ts:1543-1554` (summary schema)

- Surface: `GET /api/devices/{device_id}` / `useGetDevicesByDeviceId`
- Inputs: `{ device_id: number }` (path)
- Outputs: `DeviceResponseSchema` with `active: boolean`. No changes to the hook — only the transform needs updating.
- Errors: 404 handled by existing error boundary.
- Evidence: `src/hooks/use-devices.ts:141-156` (hook), `src/lib/api/generated/types.ts:1919-1927` (response schema)

- Surface: `POST /api/devices` / `usePostDevices`
- Inputs: `{ device_model_id: number, config: string }` (body). Note: `active` is **not** part of `DeviceCreateSchema`. The backend defaults to `true`.
- Outputs: `DeviceResponseSchema`. No payload change needed.
- Errors: Standard.
- Evidence: `src/hooks/use-devices.ts:159-193` (hook), `src/lib/api/generated/types.ts:1492-1503` (create schema)

---

## 5) Algorithms & UI Flows

- Flow: Device list renders "Active" column
- Steps:
  1. `useDevices()` fetches device list; `transformDeviceSummary` now includes `active: boolean` on each `DeviceSummary`.
  2. `DeviceListTable` renders a new column header "Active" (sortable, between "Last Core Dump" and "Actions").
  3. Each row renders a read-only visual indicator: a small pill/badge showing a styled toggle appearance. Uses `data-active-state` attribute (`true`/`false`) for test selectors.
  4. The indicator is purely visual (not interactive) — no click handler.
- States / transitions: None (read-only display).
- Hotspots: None — adding a column is lightweight.
- Evidence: `src/components/devices/device-list-table.tsx:99-168`

- Flow: Edit device with Active toggle
- Steps:
  1. `EditTabRoute` passes `device` (now including `device.active`) to `DeviceConfigurationTab`.
  2. `DeviceConfigurationTab` passes `device` to `useDeviceForm` which reads `initialActive` from `device.active` (via a new option or by reading it from the device prop).
  3. `useDeviceForm` initializes `active` state to `device.active` and tracks it in `isDirty`.
  4. The toggle renders above the JSON editor. Clicking toggles `active` state, which marks the form dirty.
  5. On save, `handleSave` calls `updateDevice.mutate({ id, config, active })`.
  6. The mutation sends `{ active, config }` in the request body.
- States / transitions: `active` boolean state toggles on click. `isDirty` reflects any change from initial value.
- Hotspots: The `isDirty` computation now includes `active !== initialActive`.
- Evidence: `src/hooks/use-device-form.ts:114-169`, `src/components/devices/device-configuration-tab.tsx:21-44`

- Flow: New device with Active toggle
- Steps:
  1. `DeviceEditor` (new/duplicate mode) calls `useDeviceForm({ mode: 'new', ... })`.
  2. `useDeviceForm` initializes `active` to `true` (the default for new devices).
  3. A read-only "Active" indicator renders between model selection and JSON editor, fixed at `true`.
  4. Since `DeviceCreateSchema` does not accept `active`, the indicator is non-interactive in new mode — it communicates the backend's default. If the backend is later updated to accept `active` in create, the indicator can be upgraded to an interactive toggle by removing the `disabled` prop and adding `active` to the create payload.
- States / transitions: New mode: `active` = `true`, non-interactive. Duplicate mode: same as new. Edit mode: interactive, initialized from `device.active`.
- Hotspots: Mode-dependent interactivity requires conditional `disabled` prop.
- Evidence: `src/components/devices/device-editor.tsx:21-57`, `src/hooks/use-device-form.ts:27-37`

---

## 6) Derived State & Invariants

- Derived value: `isDirty` (form has unsaved changes)
  - Source: Compares current `active` against `initialActive`, plus existing `jsonConfig` vs `originalJson` and model comparisons.
  - Writes / cleanup: Drives navigation blocker and cancel confirmation dialog.
  - Guards: Only compared in edit mode (new/duplicate mode `active` is not interactive).
  - Invariant: `isDirty` must include `active` changes so that toggling active alone triggers the unsaved-changes dialog.
  - Evidence: `src/hooks/use-device-form.ts:62-69`

- Derived value: `isValid` (form can be submitted)
  - Source: Model selected (or edit mode), no JSON error, not pending. `active` is always a valid boolean, so no additional validation needed.
  - Writes / cleanup: Enables/disables save button.
  - Guards: No new guards needed — `active` cannot be in an invalid state.
  - Invariant: `isValid` is not affected by the `active` value (both `true` and `false` are valid).
  - Evidence: `src/hooks/use-device-form.ts:202`

- Derived value: `sortedDevices` (sorted device list)
  - Source: `devices` array with `active` field, `sortPreference` with `active` as a valid column.
  - Writes / cleanup: Drives table row order.
  - Guards: Boolean sorting works with the existing comparator: JavaScript evaluates `false < true` as `true`, so ascending order places inactive devices first. No comparator changes needed.
  - Invariant: All devices appear regardless of `active` value; no filtering is applied.
  - Evidence: `src/components/devices/device-list-table.tsx:45-67`

---

## 7) State Consistency & Async Coordination

- Source of truth: `active` in edit mode is initialized from the React Query cache (`useDevice` result), then held in local React state via `useDeviceForm`. After a successful save, query invalidation re-fetches from the backend.
- Coordination: The `active` local state is set once on mount from `device.active`. If the query refetches in the background, the local state is not overwritten (same pattern as `jsonConfig` — the form is an "optimistic local editor"). This is consistent with the existing config editing pattern.
- Async safeguards: The `isNavigatingRef` flag prevents the navigation blocker from firing after a successful save. Query invalidation on success ensures the list and detail views reflect the updated `active` value.
- Instrumentation: The existing `useFormInstrumentation` hook already tracks submit/success/error for `DeviceEditor_edit`. No new instrumentation events are needed — the `active` field is part of the same form lifecycle.
- Evidence: `src/hooks/use-device-form.ts:114-169` (save flow), `src/hooks/use-devices.ts:198-203` (query invalidation)

---

## 8) Errors & Edge Cases

- Failure: Backend rejects update because `active` is missing from payload (current state before this fix)
  - Surface: Device edit form save action
  - Handling: The `useUpdateDevice` `onError` handler shows a toast with the error message. After this plan is implemented, `active` will always be included, resolving the issue.
  - Guardrails: The TypeScript type for the mutation variables will require `active: boolean`, making omission a compile error.
  - Evidence: `src/hooks/use-devices.ts:204-208`

- Failure: API returns a device without `active` (schema mismatch, e.g., older backend)
  - Surface: Device list or detail view
  - Handling: The transform function should default `active` to `true` if the field is undefined, matching the backend's documented default. Use `apiDevice.active ?? true` in both transforms.
  - Guardrails: TypeScript `??` operator provides the fallback silently.
  - Evidence: `src/hooks/use-devices.ts:54-76`, `src/hooks/use-devices.ts:79-123`

- Failure: User toggles Active, then navigates away without saving
  - Surface: Edit form with unsaved changes
  - Handling: Existing navigation blocker dialog ("Discard changes?") fires because `isDirty` now accounts for `active` changes. No new code needed — the blocker is already wired.
  - Guardrails: `isDirty` comparison: `active !== initialActive`.
  - Evidence: `src/hooks/use-device-form.ts:74-79` (blocker)

---

## 9) Observability / Instrumentation

- Signal: `data-testid="devices.list.row.active"` (per-row active cell)
  - Type: DOM attribute for Playwright selectors
  - Trigger: Rendered on every device row in the list table
  - Labels / fields: `data-active-state="true"` or `data-active-state="false"` for assertion
  - Consumer: Playwright specs via `DevicesPage` page object
  - Evidence: Pattern from `src/components/devices/device-list-table.tsx:133` (`data-testid="devices.list.row.rotation-state"`)

- Signal: `data-testid="devices.editor.active-toggle"` (interactive toggle in edit/new forms)
  - Type: DOM attribute for Playwright selectors
  - Trigger: Rendered in `DeviceConfigurationTab` and `DeviceEditor`
  - Labels / fields: `aria-checked="true"` or `aria-checked="false"` (standard `role="switch"` semantics)
  - Consumer: Playwright specs via `DevicesPage` page object
  - Evidence: Pattern from `src/components/devices/device-editor.tsx:111` (`data-testid="devices.editor.model-select"`)

- Signal: Existing `DeviceEditor_edit` form instrumentation
  - Type: Test-mode form events (submit, success, error)
  - Trigger: On save — already emitted, no changes needed. The `active` value is implicitly included in the mutation.
  - Labels / fields: `{ formId: 'DeviceEditor_edit', phase: 'success' }`
  - Consumer: `waitTestEvent(page, 'form', ...)` in Playwright specs
  - Evidence: `src/hooks/use-device-form.ts:46-47`

---

## 10) Lifecycle & Background Work

- Hook / effect: `useDeviceForm` — `active` state initialization
  - Trigger cadence: On mount (initial render of the form component)
  - Responsibilities: Sets `active` from `initialActive` option (which comes from `device.active` in edit mode or `true` in new mode). No side effects.
  - Cleanup: None needed — simple `useState` with initial value.
  - Evidence: `src/hooks/use-device-form.ts:50` (pattern for `selectedModelId` initialization)

No new effects, timers, subscriptions, or polling are introduced by this change. The existing query invalidation and SSE listener patterns are unaffected.

---

## 11) Security & Permissions

Not applicable. The `active` field does not introduce any new authorization requirements. All users who can currently edit devices can toggle the active flag. The backend enforces any permission checks on the PUT endpoint.

---

## 12) UX / UI Impact

- Entry point: `/devices` (device list page)
  - Change: New "Active" column added between "Last Core Dump" and "Actions"
  - User interaction: Read-only visual indicator per row. A green check mark for active, a red cross for inactive (matching the existing OTA status pattern for consistency).
  - Dependencies: `DeviceSummary.active` field from `useDevices()` hook
  - Evidence: `src/components/devices/device-list-table.tsx:138-141` (OTA status pattern to replicate)

- Entry point: `/devices/$deviceId/edit` (device configuration tab)
  - Change: New "Active" toggle/switch inserted between the "Device Model" display and the "Configuration (JSON)" editor
  - User interaction: Clicking the toggle switches between active/inactive. The switch uses `role="switch"` with `aria-checked` for accessibility. A label "Active" appears to the left; a short description "Whether device participates in automatic fleet rotation" appears below.
  - Dependencies: `device.active` passed through `DeviceConfigurationTab` props, `useDeviceForm` state management
  - Evidence: `src/components/devices/device-configuration-tab.tsx:58-73` (Device Model section, toggle goes after this)

- Entry point: `/devices/new` (new device form)
  - Change: New "Active" label and indicator between model selection and JSON editor. Shows "Active" with a static enabled indicator and the same description text. Not interactive (the backend always creates devices as active).
  - User interaction: Visual only — communicates the default. No click handling.
  - Dependencies: None (hardcoded `true` display)
  - Evidence: `src/components/devices/device-editor.tsx:101-128` (model selection section, indicator goes after this)

---

## 13) Deterministic Test Plan

- Surface: Device list — Active column display
- Scenarios:
  - Given a device exists with `active=true`, When the device list loads, Then the row for that device shows an active indicator (green check) in the Active column with `data-active-state="true"`
  - Given a device exists with `active=false` (set via API update), When the device list loads, Then the row shows an inactive indicator (red cross) with `data-active-state="false"`
- Instrumentation / hooks: `data-testid="devices.list.row.active"`, `data-active-state` attribute, `waitForListLoading(page, 'devices.list', 'ready')`
- Gaps: None
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:45-60` (existing OTA status test as template)

- Surface: Device edit form — Active toggle interaction
- Scenarios:
  - Given a device with `active=true`, When the edit form loads, Then the Active toggle shows `aria-checked="true"`
  - Given the edit form is loaded, When the user clicks the Active toggle, Then `aria-checked` flips to `"false"` and the save button remains enabled
  - Given the user has toggled Active, When the user saves, Then the success toast appears and the device list shows the updated active state
  - Given the user has toggled Active (dirty form), When the user clicks Cancel, Then the unsaved-changes dialog appears
- Instrumentation / hooks: `data-testid="devices.editor.active-toggle"`, `aria-checked`, `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success')`
- Gaps: None
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:151-178` (existing edit test as template)

- Surface: New device form — Active indicator display
- Scenarios:
  - Given the new device form is open, When the form loads, Then the Active indicator shows as enabled (active) and is not interactive
- Instrumentation / hooks: `data-testid="devices.editor.active-toggle"`, `aria-checked="true"`, `aria-disabled="true"`
- Gaps: None
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:91-125` (existing new device test)

---

## 14) Implementation Slices

- Slice: 1 — Domain models and mutation payload fix
  - Goal: `active` flows through from API to UI models; update mutation sends `active` to the backend
  - Touches: `src/hooks/use-devices.ts`, `src/hooks/use-device-form.ts`
  - Dependencies: None. This is the foundation slice.

- Slice: 2 — Device list Active column
  - Goal: Read-only Active column visible in the device list table
  - Touches: `src/components/devices/device-list-table.tsx`, `src/lib/utils/sort-preferences.ts`
  - Dependencies: Slice 1 (models include `active`)

- Slice: 3 — Edit form Active toggle
  - Goal: Interactive Active toggle on the device configuration tab, integrated with save flow
  - Touches: `src/components/devices/device-configuration-tab.tsx`, `src/hooks/use-device-form.ts` (state + dirty + save)
  - Dependencies: Slice 1 (mutation payload)

- Slice: 4 — New device form Active indicator
  - Goal: Read-only Active indicator on the new device form showing the default value
  - Touches: `src/components/devices/device-editor.tsx`
  - Dependencies: Slice 1 (form hook)

- Slice: 5 — Test factory update and Playwright specs
  - Goal: Full E2E coverage for the active column and toggle
  - Touches: `tests/api/factories/devices.ts`, `tests/e2e/devices/DevicesPage.ts`, `tests/e2e/devices/devices-crud.spec.ts`
  - Dependencies: Slices 2, 3, 4

---

## 15) Risks & Open Questions

- Risk: The `DeviceCreateSchema` does not accept `active`, but a future backend change might add it
  - Impact: If the backend adds `active` to create, the new device form toggle should become interactive and send the value
  - Mitigation: The toggle UI is already present (disabled in new mode). Enabling it later requires only removing the `disabled` prop and adding `active` to the create payload — a small follow-up change.

- Risk: Existing edit flows may already be failing silently because `active` is missing from the update payload
  - Impact: Users may see 422 errors when saving device config if the backend strictly validates
  - Mitigation: This plan prioritizes the mutation payload fix in Slice 1. Ship it first.

- Risk: The read-only toggle in the list table might be confused for an interactive control
  - Impact: Users may click it expecting to toggle active status inline
  - Mitigation: Use a simple check/cross visual (matching the existing OTA status pattern) rather than a switch control. The `cursor-default` style and absence of hover effects signal non-interactivity.

---

Confidence: High — All API types are already generated, the UI patterns are well-established in the codebase, and the change is additive with clear boundaries. The only minor uncertainty is the `DeviceCreateSchema` not accepting `active`, which is handled by making the new-device toggle read-only.
