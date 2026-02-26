# Device Active Flag -- Code Review

## 1) Summary & Decision

**Readiness**

The implementation is well-structured, follows established project patterns, and delivers all plan commitments. Domain models, transforms, form state, table columns, and Playwright tests are consistent with the existing codebase. The switch toggle uses correct `role="switch"` + `aria-checked` semantics and the test-ID naming follows the `feature.section.element` convention. The most notable gap is the absence of a Playwright test that exercises the full save-then-verify round trip for the active toggle -- the plan explicitly called for this scenario (Section 13, bullet "Given the user has toggled Active, When the user saves, Then the success toast appears and the device list shows the updated active state"). There are also minor accessibility and style items. None are blockers.

**Decision**

`GO-WITH-CONDITIONS` -- Ship after adding the missing save-round-trip test and addressing the two accessibility items below.

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- Plan Section 2 / Slice 1 (domain models + mutation fix) -- `src/hooks/use-devices.ts:17-20,31-34,56-71,83-109,217-236` -- `active: boolean` added to `DeviceSummary`, `Device`, both transforms with `?? true` fallback, and `useUpdateDevice` now requires and sends `{ active, config }`.
- Plan Section 2 / Slice 2 (list table column) -- `src/components/devices/device-list-table.tsx:111,149-157` -- New "Active" column header and cell with `data-testid="devices.list.row.active"` and `data-active-state` attribute.
- Plan Section 2 / Slice 3 (edit form toggle) -- `src/components/devices/device-configuration-tab.tsx:78-104` -- Interactive toggle with `role="switch"`, `aria-checked`, `data-testid="devices.editor.active-toggle"`, positioned between Device Model and JSON editor.
- Plan Section 2 / Slice 4 (new device indicator) -- `src/components/devices/device-editor.tsx:130-156` -- Read-only toggle with `disabled`, `aria-disabled="true"`, hardcoded `aria-checked={true}`.
- Plan Section 2 / Slice 1 (form hook) -- `src/hooks/use-device-form.ts:22-23,36,52-53,67-76,144,176` -- `initialActive` option, `active` state, dirty tracking includes `active !== initialActive` in edit mode, `active` in save payload.
- Plan Section 2 / Slice 2 (sort preferences) -- `src/lib/utils/sort-preferences.ts:4,21` -- `'active'` added to column union and validation array.
- Plan Section 2 / Slice 5 (factory) -- `tests/api/factories/devices.ts:17,111,126-150,177` -- `active` on `CreatedDevice`, new `update()` method, `active` in `create()` and `get()` mappings.
- Plan Section 2 / Slice 5 (page object) -- `tests/e2e/devices/DevicesPage.ts:120-123,142-144` -- `activeCell(row)` and `activeToggle` locators.
- Plan Section 2 / Slice 5 (specs) -- `tests/e2e/devices/devices-crud.spec.ts:499-602` -- Five test cases across three describe blocks.

**Gaps / deviations**

- Plan Section 13, Surface "Device edit form" -- The scenario "Given the user has toggled Active, When the user saves, Then the success toast appears and the device list shows the updated active state" has no corresponding Playwright test. The existing tests verify the toggle flips `aria-checked` and that dirty state fires the unsaved-changes dialog, but none exercise the full save mutation and verify the backend persisted the new `active` value. (`tests/e2e/devices/devices-crud.spec.ts:536-587` -- no save+verify test)
- Plan Section 9, Signal `data-testid="devices.list.row.active"` -- Plan called for `data-active-state="true"|"false"`. Implementation correctly delivers this. No gap.
- OpenAPI cache (`openapi-cache/openapi.json`) -- The diff includes ~300 lines of unrelated schema additions (DeploymentTriggerRequestSchema, TaskEventRequestSchema, TaskStartRequestSchema, TestErrorResponseSchema, and expanded endpoint definitions). These are not part of the device active flag feature. This is not a blocker -- it is likely the result of regenerating from a newer backend -- but it inflates the changeset and could confuse reviewers.

---

## 3) Correctness -- Findings (ranked)

- Title: **Major -- Missing save-round-trip Playwright test for active toggle**
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:536-587` -- The "Active Toggle - Edit Form" describe block has three tests: `shows active toggle reflecting device state`, `reflects inactive state from API and allows toggling`, `toggling active alone marks form as dirty`. None of them click save and verify the mutation succeeded.
- Impact: The plan (Section 13) explicitly requires verifying that "the success toast appears and the device list shows the updated active state" after saving. Without this test, there is no E2E proof that the `useUpdateDevice` mutation correctly sends `active` to the backend.
- Fix: Add a test that: (1) creates a device, (2) opens the edit form, (3) toggles active off, (4) saves, (5) waits for the form success event via `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success')`, (6) navigates back to the list and asserts `data-active-state="false"` on the device row.
- Confidence: High

- Title: **Minor -- Label not programmatically associated with toggle switch**
- Evidence: `src/components/devices/device-configuration-tab.tsx:80-82` and `src/components/devices/device-editor.tsx:132-134` -- The `<label>` elements are visual-only (no `htmlFor`/`id` pairing) and the `<button role="switch">` lacks `aria-label` or `aria-labelledby`.
- Impact: Screen readers will announce the button without a programmatic label. While the adjacent text "Active" / "Inactive" is visually clear, assistive technology cannot reliably associate it. The existing `Device Model` label in `device-editor.tsx:103` uses `htmlFor="device-model"` for the select, so this is an inconsistency within the same component.
- Fix: Add `id="active-toggle"` to the button and `htmlFor="active-toggle"` to the label, or add `aria-label="Active"` to the button. Since the same pattern appears in two files, prefer `aria-label` as the simpler change.
- Confidence: High

- Title: **Minor -- OTA status test uses brittle positional `td.nth(5)` selector**
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:55,59` -- After adding the Active column, the OTA test was updated from `rowTrue.locator('text=...')` to `rowTrue.locator('td').nth(5).locator('text=...')`. This couples the test to column ordering. If another column is inserted before OTA, the index silently breaks.
- Impact: Maintenance burden. The existing OTA column cell does not have a `data-testid` attribute, which means there is no stable selector. This is a pre-existing gap that was surfaced rather than introduced by this change.
- Fix: Add `data-testid="devices.list.row.ota"` to the OTA `<td>` element and update the test to use that selector instead of `.nth(5)`. This is a follow-up improvement, not a blocker for this PR.
- Confidence: High

---

## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: Duplicated switch toggle markup across two components
- Evidence: `src/components/devices/device-configuration-tab.tsx:83-103` and `src/components/devices/device-editor.tsx:135-155` -- Both render near-identical `<button role="switch">` markup with the same Tailwind classes, description text, and layout structure. The only differences are interactivity (disabled vs not) and label text.
- Suggested refactor: Extract a shared `ActiveToggle` component (or simply a `SwitchToggle` primitive) that accepts `checked`, `onChange`, `disabled`, `label`, and `description` props. This aligns with the plan's note (Section 0, Finding 4) that "if reuse emerges later, it can be extracted" -- reuse has now emerged within the same changeset.
- Payoff: Single place to maintain accessibility attributes, Tailwind classes, and toggle behavior. Reduces the risk of the two copies drifting apart.

---

## 5) Style & Consistency

- Pattern: Active column uses HTML numeric character entities while OTA column uses literal Unicode characters
- Evidence: `src/components/devices/device-list-table.tsx:140-141` (OTA: literal `✓` / `✕`) vs `src/components/devices/device-list-table.tsx:155-156` (Active: `&#10003;` / `&#10005;`). Both render identically since U+2713 = decimal 10003 and U+2715 = decimal 10005.
- Impact: No functional difference, but visual inconsistency in source code makes it harder to scan the file and spot differences between the two columns.
- Recommendation: Use literal Unicode characters in the Active column to match the OTA column, or convert both to named entities / a shared constant if consistency is preferred.

- Pattern: Consistent use of `?? true` fallback for `active` in transforms
- Evidence: `src/hooks/use-devices.ts:71` (`transformDeviceSummary`) and `src/hooks/use-devices.ts:109` (`transformDeviceResponse`) -- Both use `apiDevice.active ?? true` for defensive fallback.
- Impact: Positive. This is consistent with the plan (Section 8) and protects against older backends that may not yet include the field.
- Recommendation: None -- this is good practice. Noting it as a positive pattern.

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: Device list -- Active column display
- Scenarios:
  - Given a newly created device (default active=true), When the list loads, Then the Active cell shows `data-active-state="true"` and a green check mark (`tests/e2e/devices/devices-crud.spec.ts:500-515`)
  - Given a device set to active=false via API, When the list loads, Then the Active cell shows `data-active-state="false"` and a red cross (`tests/e2e/devices/devices-crud.spec.ts:517-533`)
- Hooks: `data-testid="devices.list.row.active"`, `data-active-state`, `waitForListLoaded()`
- Gaps: None for display. The Active column's display states are fully covered.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:499-534`

- Surface: Device edit form -- Active toggle interaction
- Scenarios:
  - Given an active device, When the edit form loads, Then `aria-checked="true"` (`tests/e2e/devices/devices-crud.spec.ts:537-546`)
  - Given an inactive device (set via API), When the edit form loads, Then `aria-checked="false"`, and toggling flips the value (`tests/e2e/devices/devices-crud.spec.ts:548-567`)
  - Given a clean edit form, When the user toggles active only, Then the form is dirty and Cancel shows the unsaved-changes dialog (`tests/e2e/devices/devices-crud.spec.ts:569-586`)
- Hooks: `data-testid="devices.editor.active-toggle"`, `aria-checked`, `unsavedChangesDialog`
- Gaps: **Missing save-then-verify round trip.** No test saves the toggled active state and confirms the backend accepted it, the success toast appeared, and the list reflected the change. See Finding #1 in Section 3.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:536-587`

- Surface: New device form -- Active indicator
- Scenarios:
  - Given the new device form, When it loads, Then the active toggle is visible, `aria-checked="true"`, and disabled (`tests/e2e/devices/devices-crud.spec.ts:589-602`)
- Hooks: `data-testid="devices.editor.active-toggle"`, `aria-checked`, `toBeDisabled()`
- Gaps: None -- the read-only nature is verified through the disabled assertion.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:589-602`

---

## 7) Adversarial Sweep (must attempt >= 3 credible failures or justify none)

- Title: **Minor -- Stale closure risk in handleSave if active state changes during save**
- Evidence: `src/hooks/use-device-form.ts:176` -- The `handleSave` callback captures `active` in its dependency array, which means it always reads the current value at the time of the call. However, because `isPending` disables the toggle button (`src/components/devices/device-configuration-tab.tsx:89`), the user cannot change `active` while a mutation is in flight.
- Impact: None, because the toggle is disabled during save. The closure captures the correct value at call time.
- Fix: None needed.
- Confidence: High

- Title: **Minor -- Race between column add and sort preference deserialization**
- Evidence: `src/lib/utils/sort-preferences.ts:21` -- The validation array now includes `'active'`. If a user had previously saved `active` as their sort column (impossible before this change) and then rolled back the frontend, the old code would reject the unknown column and fall back to `DEFAULT_SORT`. Since the code adds `'active'` to the validation list in the same change that introduces the column, there is no forward-compatibility issue.
- Impact: None in practice.
- Fix: None needed.
- Confidence: High

- Title: **No issue -- Query cache consistency after active toggle save**
- Evidence: `src/hooks/use-devices.ts:207-208` -- After a successful update, both `getDevices` and `getDevicesByDeviceId` query keys are invalidated. This ensures the list and detail views re-fetch fresh data from the backend.
- Impact: No stale cache risk. The form's local `active` state is abandoned after the user navigates away on success (`src/hooks/use-device-form.ts:147-152`), and the next visit initializes from the query cache.
- Fix: None needed.
- Confidence: High

---

## 8) Invariants Checklist (table)

- Invariant: The update mutation always sends `active` alongside `config`
  - Where enforced: `src/hooks/use-devices.ts:220` -- The `mutate` signature requires `variables: { id: number; config: string; active: boolean }`, making omission a TypeScript compile error.
  - Failure mode: If a caller passes only `{ id, config }`, TypeScript rejects the call. At runtime, `variables.active` would be `undefined`, which the backend would reject as a 422.
  - Protection: TypeScript strict mode type checking; the generated `DeviceUpdateSchema_d48fbce` also requires `active: boolean` (`src/lib/api/generated/types.ts:2058`).
  - Evidence: `src/hooks/use-devices.ts:219-226`, `src/hooks/use-device-form.ts:144`

- Invariant: `isDirty` reflects active state changes in edit mode only
  - Where enforced: `src/hooks/use-device-form.ts:68-76` -- The `useMemo` checks `active !== initialActive` only when `mode === 'edit'`. In new/duplicate mode, `active` is not included in the dirty calculation because the toggle is disabled and cannot change.
  - Failure mode: If `active` were tracked in new mode and the user could change it, `isDirty` would fire the navigation blocker incorrectly. Since the toggle is `disabled`, this cannot happen.
  - Protection: The `disabled` prop on the new-form toggle (`src/components/devices/device-editor.tsx:141`) and the mode-branching in `isDirty`.
  - Evidence: `src/hooks/use-device-form.ts:68-76`, `src/components/devices/device-editor.tsx:141`

- Invariant: Every device row displays an active indicator (no missing/undefined state)
  - Where enforced: `src/hooks/use-devices.ts:71` and `src/hooks/use-devices.ts:109` -- Transforms use `apiDevice.active ?? true`, guaranteeing the field is always a boolean. The table cell (`src/components/devices/device-list-table.tsx:154-156`) renders a ternary on the boolean with no third branch.
  - Failure mode: If the API returned `active: undefined`, the `?? true` fallback ensures the device appears as active. If `active` were somehow a non-boolean truthy/falsy value, JavaScript ternary would still resolve, though the `data-active-state` attribute would be "true" or "false" based on `String(device.active)`.
  - Protection: The `?? true` fallback and the TypeScript `active: boolean` type on `DeviceSummary`.
  - Evidence: `src/hooks/use-devices.ts:71`, `src/components/devices/device-list-table.tsx:149-157`

---

## 9) Questions / Needs-Info

- Question: Is the unrelated OpenAPI schema drift (Deployment, Task, TestError schemas) intentional in this changeset, or should it be split into a separate commit?
- Why it matters: The `openapi-cache/openapi.json` diff includes ~300 lines of additions unrelated to the device active flag (DeploymentTriggerRequestSchema, TaskEventRequestSchema, TaskStartRequestSchema, TestErrorResponseSchema, and expanded endpoint specs). Bundling unrelated schema changes inflates the diff and makes it harder to review and bisect.
- Desired answer: Confirmation that the OpenAPI cache was regenerated from a newer backend that includes both the active field and these other additions, and that including them is acceptable.

---

## 10) Risks & Mitigations (top 3)

- Risk: Missing save-round-trip test leaves the critical mutation path unverified by E2E coverage.
- Mitigation: Add a Playwright test that toggles active, saves, waits for the form success event, and verifies the list reflects the change. This should block merge.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:536-587` (existing toggle tests that stop short of saving)

- Risk: Duplicated toggle markup in two components will drift over time (accessibility fixes, style changes applied to one but not the other).
- Mitigation: Extract a shared `ActiveToggle` or `SwitchToggle` component as a fast follow-up. Not required for this PR, but track it.
- Evidence: `src/components/devices/device-configuration-tab.tsx:83-103`, `src/components/devices/device-editor.tsx:135-155`

- Risk: Positional `td.nth(5)` selector in OTA tests is fragile and will break if columns are reordered or added before OTA.
- Mitigation: Add `data-testid="devices.list.row.ota"` to the OTA column cell in a follow-up and update the test selector. This is a pre-existing issue surfaced by this change.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:55,59`, `src/components/devices/device-list-table.tsx:139`

---

## 11) Confidence

Confidence: High -- The implementation is clean, follows documented patterns, and the only material gap is a missing test scenario that is straightforward to add. The correctness of the data flow from API through transforms to UI and back through the mutation is sound and type-checked at every boundary.
