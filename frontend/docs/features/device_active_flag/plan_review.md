# Plan Review: Device Active Flag

## 1) Summary & Decision

**Readiness**
The plan is thorough, well-researched, and implementation-ready. All three conditions from the initial review have been addressed: the new-device toggle is consistently described as a non-interactive read-only indicator, the test factory `update()` method is fully specified with signature and usage example, and the boolean sort comparator behavior is documented. The plan demonstrates strong alignment with the codebase patterns, correctly identifies a pre-existing TypeScript build error as the highest-priority fix, and provides deterministic Playwright test scenarios with proper instrumentation coverage.

**Decision**
`GO` -- The plan is ready for implementation. All sections are consistent, evidence is well-cited, and the implementation slices are logically ordered. A competent developer can implement this without ambiguity.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**
- `docs/commands/plan_feature.md` -- Pass -- The plan includes all 16 required sections (0 through 15) with proper templates and evidence citations. Section 1a includes the user requirements checklist.
- `docs/product_brief.md` -- Pass -- `plan.md:37` -- The plan adds the Active column to the device list and toggle to the editor, consistent with the product brief's device configuration management scope. The `change_brief.md` provides the specific requirements.
- `docs/contribute/architecture/application_overview.md` -- Pass -- `plan.md:91-93` -- The plan extends `DeviceSummary` and `Device` domain models in `src/hooks/use-devices.ts`, following the architecture's pattern of custom hooks that transform snake_case API responses to camelCase domain models.
- `docs/contribute/testing/playwright_developer_guide.md` -- Pass -- `plan.md:341-364` -- The test plan uses factories for data setup, `data-testid` attributes for selectors, and `waitTestEvent` for deterministic waits. No route interception is proposed. The `testing/no-route-mocks` rule is not violated.

**Fit with codebase**
- `useUpdateDevice` mutation wrapper -- `plan.md:142-144` -- Confirmed alignment. The current code at `src/hooks/use-devices.ts:217-219` produces TypeScript error TS2741 ("Property 'active' is missing") under `tsc -b`. The plan correctly fixes this by adding `active` to the mutation variables.
- `useDeviceForm` dirty tracking -- `plan.md:96-97` -- Confirmed alignment. The existing dirty logic at `src/hooks/use-device-form.ts:62-69` uses comparison-based detection. Adding `active !== initialActive` follows the established pattern.
- `DeviceListTable` column ordering -- `plan.md:99-101` -- Confirmed alignment. The column order at `src/components/devices/device-list-table.tsx:104-111` currently ends with OTA Status, Last Core Dump, Actions. Inserting Active before Actions is consistent.
- `SortPreference` column union -- `plan.md:111-113` -- Confirmed alignment. Both the type union at `src/lib/utils/sort-preferences.ts:4` and `validColumns` array at line 21 need `'active'` added.
- `DevicesFactory` -- `plan.md:119-121` -- Confirmed alignment. The factory specification is now complete with method signature `update(options: { id: number; active: boolean; config: string }): Promise<CreatedDevice>`, API endpoint, and usage example.
- `useListLoadingInstrumentation` -- Present at `src/routes/devices/index.tsx:26-27` with scope `'devices.list'`. No changes needed since the instrumentation is at the route level. The plan correctly omits this from the change set.

---

## 3) Open Questions & Ambiguities

No open questions remain. The previously identified ambiguities have been resolved:
- The new-device toggle is consistently described as a non-interactive read-only indicator across all sections (lines 37, 43, 52, 82, 207-210, 332-334, 361-362, 385-386).
- The factory `update()` method is fully specified at line 120-121 with signature, API call, and test usage.
- The boolean sort behavior is documented at line 236.

---

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Device list -- Active column display
- Scenarios:
  - Given a device exists with `active=true` (default from create), When the device list loads, Then the row shows an active indicator with `data-active-state="true"` (`tests/e2e/devices/devices-crud.spec.ts`)
  - Given a device exists with `active=false` (set via `devices.update({ id, active: false, config })`), When the device list loads, Then the row shows an inactive indicator with `data-active-state="false"` (`tests/e2e/devices/devices-crud.spec.ts`)
- Instrumentation: `data-testid="devices.list.row.active"`, `data-active-state` attribute, `waitForListLoading(page, 'devices.list', 'ready')`
- Backend hooks: `DevicesFactory.create()` for active device, `DevicesFactory.update()` for setting `active=false`
- Gaps: None.
- Evidence: `plan.md:341-347`

- Behavior: Device edit form -- Active toggle interaction
- Scenarios:
  - Given a device with `active=true`, When the edit form loads, Then the Active toggle shows `aria-checked="true"` (`tests/e2e/devices/devices-crud.spec.ts`)
  - Given the user clicks the Active toggle, When the toggle flips, Then `aria-checked` changes to `"false"` and save button remains enabled (`tests/e2e/devices/devices-crud.spec.ts`)
  - Given the user has toggled Active and saves, When the mutation succeeds, Then the success toast appears and the device list shows the updated state (`tests/e2e/devices/devices-crud.spec.ts`)
  - Given the user has toggled Active (dirty form), When the user clicks Cancel, Then the unsaved-changes dialog appears (`tests/e2e/devices/devices-crud.spec.ts`)
- Instrumentation: `data-testid="devices.editor.active-toggle"`, `aria-checked`, `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success')`
- Backend hooks: `DevicesFactory.create()` for initial device, `DevicesFactory.get()` to verify post-save state
- Gaps: None.
- Evidence: `plan.md:349-357`

- Behavior: New device form -- Active indicator display
- Scenarios:
  - Given the new device form is open, When the form loads, Then the Active indicator shows as enabled and is not interactive (`tests/e2e/devices/devices-crud.spec.ts`)
- Instrumentation: `data-testid="devices.editor.active-toggle"`, `aria-checked="true"`, `aria-disabled="true"`
- Backend hooks: None required.
- Gaps: None.
- Evidence: `plan.md:359-364`

---

## 5) Adversarial Sweep (must find >=3 credible issues or declare why none exist)

- Checks attempted: Boolean sort comparator correctness, factory `update()` completeness, new-device toggle consistency, `isDirty` in new mode for non-interactive toggle, `initialActive` synchronization on re-render, cache staleness after toggle save
- Evidence: `plan.md:207-212` (new device flow), `plan.md:236` (sort behavior), `plan.md:119-121` (factory spec), `plan.md:219-224` (isDirty), `plan.md:244-248` (state consistency)
- Why the plan holds:
  1. **Boolean sort**: The plan now documents that `false < true` evaluates correctly in JavaScript (line 236). The existing comparator at `src/components/devices/device-list-table.tsx:53-65` handles this without modification.
  2. **Factory completeness**: The `update()` method signature is fully specified (line 120-121) with both required fields (`active`, `config`), matching the `DeviceUpdateSchema` requirements at `src/lib/api/generated/types.ts:2053-2064`.
  3. **New-device toggle consistency**: All sections now consistently describe the new-device form as showing a read-only indicator. The `isDirty` guard at line 222 correctly notes "Only compared in edit mode" so the non-interactive toggle cannot produce false dirty state.
  4. **Cache staleness**: Query invalidation on mutation success (line 246, `src/hooks/use-devices.ts:201-202`) ensures both `getDevices` and `getDevicesByDeviceId` caches refresh after save. The plan follows the existing pattern for `config` updates.
  5. **Re-render sync**: The plan follows the existing `jsonConfig` initialization pattern -- local state set once on mount, not overwritten by background refetches (line 245). This is the established "optimistic local editor" pattern in `useDeviceForm`.

---

## 6) Derived-Value & State Invariants (table)

- Derived value: `isDirty`
  - Source dataset: Current `active` state vs `initialActive`, plus existing `jsonConfig` vs `originalJson` and model comparisons.
  - Write / cleanup triggered: Drives navigation blocker dialog and cancel confirmation dialog.
  - Guards: `active` comparison only applies in edit mode (new/duplicate mode has a non-interactive indicator).
  - Invariant: Toggling `active` alone (without changing JSON config) must mark the form dirty and trigger the unsaved-changes dialog on navigation.
  - Evidence: `plan.md:219-224`, `src/hooks/use-device-form.ts:62-69`

- Derived value: `isValid`
  - Source dataset: Model selection state, JSON error state, pending state. `active` is always a valid boolean.
  - Write / cleanup triggered: Enables/disables the save button.
  - Guards: No new guards -- `active` cannot be invalid.
  - Invariant: `isValid` must not be affected by the `active` value. Both `true` and `false` are valid states.
  - Evidence: `plan.md:226-231`, `src/hooks/use-device-form.ts:202`

- Derived value: `sortedDevices`
  - Source dataset: `devices` array including `active` field, `sortPreference` with `active` as a valid column.
  - Write / cleanup triggered: Drives table row rendering order.
  - Guards: Boolean comparison (`false < true`) is valid in JavaScript. No filtering applied.
  - Invariant: All devices must appear in the list regardless of `active` value. The `active` column must not filter or hide rows.
  - Evidence: `plan.md:233-238`, `src/components/devices/device-list-table.tsx:45-67`

- Derived value: Update mutation payload `{ active, config }`
  - Source dataset: Local form state `active` and `jsonConfig`, both initialized from device query cache on mount.
  - Write / cleanup triggered: Sends PUT request, invalidates `getDevices` and `getDevicesByDeviceId` query keys on success.
  - Guards: TypeScript type `DeviceUpdateSchema_d48fbce` requires both fields. Omission is a compile-time error (verified via `tsc -b`).
  - Invariant: Every device update request must include both `active` and `config`.
  - Evidence: `plan.md:141-144`, `src/lib/api/generated/types.ts:2053-2064`

---

## 7) Risks & Mitigations (top 3)

- Risk: The existing `useUpdateDevice` hook currently fails TypeScript build (`tsc -b`) due to missing `active` in the mutation body. Until Slice 1 lands, `pnpm check` reports TS2741 errors at `src/hooks/use-devices.ts:217` and `:223`.
- Mitigation: Slice 1 is prioritized as the foundation. The fix is additive: add `active: variables.active` to the body object and update the mutation variables type.
- Evidence: `plan.md:370-373`, `src/hooks/use-devices.ts:196-229`

- Risk: The `DeviceCreateSchema` does not accept `active`, but a future backend change might add it. The current plan shows a non-interactive indicator in new mode.
- Mitigation: The plan correctly uses a `disabled` prop approach (line 212) so enabling interactivity later requires only removing `disabled` and adding `active` to the create payload.
- Evidence: `plan.md:399-401`

- Risk: The read-only indicator in the device list might be confused for an interactive control by users.
- Mitigation: The plan uses the existing check/cross pattern from OTA status (lines 321, 407-409) with `cursor-default` styling, which is already established in the codebase at `src/components/devices/device-list-table.tsx:138-141`.
- Evidence: `plan.md:407-409`, `src/components/devices/device-list-table.tsx:138-141`

---

## 8) Confidence

Confidence: High -- The plan is complete, internally consistent, and well-grounded in codebase evidence. All three conditions from the initial review have been resolved. The implementation is additive, follows established patterns, and includes full Playwright coverage with deterministic test setup.
