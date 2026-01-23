# Code Review: Device Provisioning MDM Frontend Update

## 1) Summary & Decision

**Readiness**

The implementation successfully migrates from a MAC-address-based device configuration system to a device/device-model architecture with rotation management. The code follows established project patterns, maintains type safety, implements proper React Query cache invalidation, and includes comprehensive form instrumentation. However, there are several gaps relative to the plan including missing tests for the new functionality and incomplete instrumentation in the device model editor.

**Decision**

`GO-WITH-CONDITIONS` - The core implementation is sound and type-safe, but the change is incomplete according to the plan. Conditions for GO:
1. Add `useFormInstrumentation` to `DeviceModelEditor` component
2. Create Playwright specs for device models and rotation dashboard
3. Add rotation dashboard route registration to ensure navigation works

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- `Slice 0: Test Infrastructure Migration` - `/work/frontend/tests/api/factories/devices.ts:1-158` - Factory fully migrated to use `/api/devices` endpoints with `device_model_id`, adds dependency on `DeviceModelsFactory`
- `Slice 1: API Regeneration & Hook Foundation` - `/work/frontend/src/hooks/use-devices.ts`, `/work/frontend/src/hooks/use-device-models.ts`, `/work/frontend/src/hooks/use-rotation.ts` - All hooks implemented with proper snake_case to camelCase transformations
- `Slice 1: Form Instrumentation Hook` - `/work/frontend/src/lib/test/form-instrumentation.ts:1-176` - Complete implementation with `trackSubmit`, `trackSuccess`, `trackError`, `trackValidationError`
- `Slice 2: Navigation & Routing` - `/work/frontend/src/components/layout/sidebar.tsx:23-25` - Navigation updated with Device Models and Rotation links
- `Slice 3: Device Models UI` - `/work/frontend/src/routes/device-models/`, `/work/frontend/src/components/device-models/` - Complete CRUD implementation
- `Slice 4: Devices UI Update` - `/work/frontend/src/components/devices/device-editor.tsx`, `/work/frontend/src/components/devices/device-list-table.tsx` - Updated with model selector, rotation badges, provisioning download
- `Slice 5: Rotation Dashboard` - `/work/frontend/src/routes/rotation.tsx`, `/work/frontend/src/components/rotation/rotation-dashboard.tsx` - Dashboard implemented with health groupings and trigger button
- `Monaco Schema Validation` - `/work/frontend/src/lib/utils/monaco-schema.ts:1-123` - URI-based schema association implemented

**Gaps / deviations**

- `Plan: Device Model Editor must use useFormInstrumentation` - Missing form instrumentation in `device-model-editor.tsx`. The plan specifically calls out adding `useFormInstrumentation` to device model forms in Slice 3 (`device-model-editor.tsx:1-346`)
- `Plan: Playwright specs for device models CRUD` - Directory `tests/e2e/device-models/` does not exist. Plan Slice 6 requires `device-models.spec.ts`
- `Plan: Playwright specs for rotation dashboard` - Directory `tests/e2e/rotation/` does not exist. Plan Slice 6 requires `rotation.spec.ts`
- `Plan: Rotation status polling` - `/work/frontend/src/hooks/use-rotation.ts:107-119` - `useRotationStatus` does not implement `refetchInterval` for polling as specified in Plan Section 10

---

## 3) Correctness - Findings (ranked)

- Title: `Major - Missing Form Instrumentation in DeviceModelEditor`
- Evidence: `/work/frontend/src/components/device-models/device-model-editor.tsx:1-346` - No `useFormInstrumentation` hook usage
- Impact: Playwright tests cannot deterministically wait for form lifecycle events (submit/success/error) in device model create/edit flows
- Fix: Add `useFormInstrumentation({ formId: mode === 'edit' ? 'DeviceModelEditor_edit' : 'DeviceModelEditor_new' })` and call `trackSubmit`/`trackSuccess`/`trackError` in `handleSave`
- Confidence: High

- Title: `Minor - Provisioning Download Error Does Not Use Toast Context Properly`
- Evidence: `/work/frontend/src/hooks/use-devices.ts:274-289` - `downloadDeviceProvisioning` is a standalone async function that throws errors
- Impact: Errors in provisioning download are caught in component and shown via toast, but there's no correlation ID tracking for debugging
- Fix: Consider wrapping in a hook pattern like other mutations for consistency, or document the manual approach
- Confidence: Medium

- Title: `Minor - Monaco Schema Configuration Race Condition`
- Evidence: `/work/frontend/src/components/devices/device-editor.tsx:106-117` - `useEffect` depends on `fullDeviceModel?.configSchema` which may arrive after editor mounts
- Impact: Schema validation may not apply on initial render if device model query returns after Monaco mounts
- Fix: The current implementation handles this correctly by re-running the effect when `fullDeviceModel` changes; no fix needed but consider adding a loading state until schema is available for better UX
- Confidence: Low

- Title: `Minor - Sort Preference Storage Key Collision Risk`
- Evidence: `/work/frontend/src/lib/utils/sort-preferences.ts:1` - Uses `'iot-support-device-sort'` key
- Impact: Device models list uses local state sorting while devices list uses localStorage. Inconsistent persistence behavior between lists.
- Fix: Either persist device models sort preferences similarly or document the intentional difference
- Confidence: Low

---

## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: Monaco Schema Configuration Module
- Evidence: `/work/frontend/src/lib/utils/monaco-schema.ts:34-36` - Uses module-level `configuredSchemas` Map for tracking
- Suggested refactor: The module-level cache could cause issues if different editors need different schemas. Consider returning a cleanup function from `configureMonacoSchemaValidation` or using React state.
- Payoff: Cleaner schema management when navigating between devices with different models

- Hotspot: Duplicated Sort Type Definitions
- Evidence: `/work/frontend/src/routes/device-models/index.tsx:16-20` vs `/work/frontend/src/lib/utils/sort-preferences.ts`
- Suggested refactor: Extract device models sort preference type to a shared location for consistency
- Payoff: Type reuse and consistent sorting patterns across list views

---

## 5) Style & Consistency

- Pattern: Inconsistent List Loading Instrumentation Scope Naming
- Evidence: `/work/frontend/src/routes/device-models/index.tsx:34` uses `'device-models.list'` (with hyphen) vs existing pattern likely using dots
- Impact: Playwright helpers may need to handle both naming conventions
- Recommendation: Verify existing scope naming convention and align; recommend `'deviceModels.list'` for consistency with camelCase domain model names

- Pattern: Form ID Naming Convention
- Evidence: `/work/frontend/src/components/devices/device-editor.tsx:55` uses `'DeviceEditor_edit'` with underscore
- Impact: Consistent form ID format across all editors helps Playwright test authoring
- Recommendation: Document and enforce form ID naming pattern: `{ComponentName}_{mode}`

- Pattern: Error Handling in Mutation Hooks
- Evidence: `/work/frontend/src/hooks/use-devices.ts:123` explicitly types `error: unknown` in onError callback
- Impact: Good pattern that ensures type safety
- Recommendation: This is a positive pattern; continue using explicit `unknown` typing in error handlers

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: Device List with Model Selector
- Scenarios:
  - Given device models exist, When user creates device selecting model, Then device appears with auto-generated key (`tests/e2e/devices/devices-crud.spec.ts:104-147`)
  - Given device exists, When user edits config, Then changes saved (`tests/e2e/devices/devices-crud.spec.ts:176-215`)
  - Given device list displays, When viewing row, Then rotation state badge shows (`tests/e2e/devices/devices-crud.spec.ts:21-48`)
- Hooks: `devices.list` loading events, `DeviceForm_*` form events (via `useFormInstrumentation`), `data-device-key` selectors
- Gaps: Tests for rotation state badge colors not explicitly verified
- Evidence: `/work/frontend/tests/e2e/devices/devices-crud.spec.ts`

- Surface: Device Models CRUD
- Scenarios:
  - Given no models exist, When user views list, Then empty state shown - **NOT TESTED**
  - Given user creates model with code/name, When save clicked, Then model appears in list - **NOT TESTED**
  - Given model exists with device_count=0, When user clicks delete, Then model removed from list - **NOT TESTED**
  - Given model exists with device_count>0, When user views list, Then delete shows warning - **NOT TESTED**
- Hooks: `device-models.list` loading events, form instrumentation missing
- Gaps: **No Playwright specs exist for device models** - `tests/e2e/device-models/` directory missing
- Evidence: Directory does not exist

- Surface: Rotation Dashboard
- Scenarios:
  - Given devices exist in various states, When user views dashboard, Then counts shown correctly - **NOT TESTED**
  - Given user clicks trigger, Then devices queued and count shown - **NOT TESTED**
  - Given device is pending, When viewing dashboard, Then link to pending device shown - **NOT TESTED**
- Hooks: `rotation.dashboard` loading events, trigger button `data-testid`
- Gaps: **No Playwright specs exist for rotation** - `tests/e2e/rotation/` directory missing
- Evidence: Directory does not exist

---

## 7) Adversarial Sweep (must attempt >=3 credible failures or justify none)

- Title: `Major - Device Model Fetch Race in Device Editor`
- Evidence: `/work/frontend/src/components/devices/device-editor.tsx:62-63` - `useDeviceModel(initialDeviceModelId)` fetches model in edit mode
- Impact: If the device detail query returns before the model query (both happen on mount), the Monaco schema validation may not be configured until the model query completes, leading to brief period without validation
- Fix: The current implementation handles this via the `useEffect` at line 106-117 which re-runs when `fullDeviceModel` changes. The schema will apply once loaded. No critical issue.
- Confidence: Medium

- Title: `Minor - Monaco Global Schema Pollution`
- Evidence: `/work/frontend/src/lib/utils/monaco-schema.ts:86-100` - `setDiagnosticsOptions` replaces global schemas
- Impact: If two editors are mounted simultaneously (e.g., user opens multiple tabs), schema configuration may interfere. The `configuredSchemas` Map prevents re-registration of same schema but doesn't prevent overwriting with different schemas.
- Fix: The current implementation uses model URI matching which should isolate schemas per model ID. However, the `fileMatch: [modelUri, '*.json']` at line 92 could cause broad matching.
- Confidence: Medium

- Checks attempted: Query cache invalidation correctness, effect cleanup, navigation race conditions
- Evidence: `/work/frontend/src/hooks/use-devices.ts:153-169` properly invalidates both list and detail caches; `/work/frontend/src/components/devices/device-editor.tsx:69-90` uses `useBlocker` and `beforeunload` with proper cleanup
- Why code held up: Cache invalidation is comprehensive (list + detail queries), navigation blocking uses React Router's `useBlocker` with `withResolver: true` for proper async handling, and the `isNavigatingRef` prevents false positives when intentionally navigating after save

---

## 8) Invariants Checklist (table)

- Invariant: Device model cannot be changed after device creation
  - Where enforced: `/work/frontend/src/components/devices/device-editor.tsx:340-345` - Model selector disabled in edit mode, model displayed as read-only text
  - Failure mode: User modifies device model on existing device, causing data inconsistency
  - Protection: UI shows read-only display in edit mode; backend would reject model change on PUT
  - Evidence: `/work/frontend/src/components/devices/device-editor.tsx:340` - `{mode === 'edit' ? (` conditional rendering

- Invariant: Device key is immutable and auto-generated
  - Where enforced: `/work/frontend/src/components/devices/device-editor.tsx:315-324` - Key displayed as read-only in edit mode, no input field in create mode
  - Failure mode: User attempts to modify or specify key, causing duplicate or invalid keys
  - Protection: UI shows read-only display; key not included in create/update mutation payloads
  - Evidence: `/work/frontend/src/hooks/use-devices.ts:172-179` - create mutation only sends `deviceModelId` and `config`

- Invariant: Device model with devices cannot be deleted
  - Where enforced: `/work/frontend/src/routes/device-models/index.tsx:48-57` - handleDelete shows informational dialog when deviceCount > 0
  - Failure mode: Model deleted while devices reference it, causing orphaned device references
  - Protection: Frontend shows "Cannot Delete Model" dialog; backend returns 409 Conflict
  - Evidence: `/work/frontend/src/routes/device-models/index.tsx:50-55`

- Invariant: JSON config must be valid JSON before save
  - Where enforced: `/work/frontend/src/components/devices/device-editor.tsx:124-135` - `validateJson` called on every change and before save
  - Failure mode: Invalid JSON saved, causing parse errors or data corruption
  - Protection: Save button disabled when `jsonError` is non-null; validation runs on change and save
  - Evidence: `/work/frontend/src/components/devices/device-editor.tsx:186` - `isValid` includes `!jsonError`

---

## 9) Questions / Needs-Info

- Question: Should rotation dashboard polling interval be configurable or fixed at 30 seconds?
- Why it matters: Plan Section 10 specifies 30s polling for rotation status, but implementation doesn't include refetchInterval
- Desired answer: Confirm whether polling is still required and at what interval; current implementation requires manual refresh

- Question: Should device models tests be blocking for this PR?
- Why it matters: The plan specifies Playwright specs in Slice 6, but no specs exist
- Desired answer: Clarify whether device model and rotation tests can be delivered as follow-up or must be included

- Question: What is the expected behavior when Monaco editor loads before device model schema is available?
- Why it matters: Schema validation applies via `useEffect` when model data arrives, but user may edit before schema loads
- Desired answer: Confirm whether showing a loading state until schema is available is desired UX

---

## 10) Risks & Mitigations (top 3)

- Risk: Missing Playwright test coverage for device models and rotation dashboard could allow regressions
- Mitigation: Create minimal happy-path specs for device models CRUD and rotation trigger before merge; add comprehensive coverage as fast-follow
- Evidence: `/work/frontend/tests/e2e/device-models/` and `/work/frontend/tests/e2e/rotation/` directories do not exist

- Risk: Form instrumentation missing in DeviceModelEditor prevents deterministic Playwright testing
- Mitigation: Add `useFormInstrumentation` hook to `device-model-editor.tsx` following the pattern in `device-editor.tsx:55`
- Evidence: `/work/frontend/src/components/device-models/device-model-editor.tsx` - no imports from `form-instrumentation.ts`

- Risk: Monaco schema configuration using module-level Map may cause stale schema issues across navigation
- Mitigation: Verify schema updates correctly when navigating between devices with different models; consider adding `clearMonacoSchemas()` call on component unmount
- Evidence: `/work/frontend/src/lib/utils/monaco-schema.ts:34-36` - `configuredSchemas` Map persists across component lifecycles

---

## 11) Confidence

Confidence: Medium - The core implementation is well-structured, type-safe, and follows project patterns. However, significant test coverage gaps (no device model or rotation Playwright specs) and missing form instrumentation in the device model editor reduce confidence in the change's completeness. The code quality is high, but the deliverable is incomplete per the plan's Definition of Done.

---

## Appendix: Files Reviewed

**Modified Files (Unstaged Changes)**
- `/work/frontend/src/hooks/use-devices.ts` - Complete rewrite for new API
- `/work/frontend/src/components/devices/device-editor.tsx` - Major update with model selector
- `/work/frontend/src/components/devices/device-list-table.tsx` - New columns and rotation badges
- `/work/frontend/src/components/layout/sidebar.tsx` - Navigation updates
- `/work/frontend/src/routes/devices/index.tsx` - Integration with device models
- `/work/frontend/src/routes/devices/new.tsx` - Model ID parameter support
- `/work/frontend/src/routes/devices/$deviceId.tsx` - Pass device model props
- `/work/frontend/src/routes/devices/$deviceId/duplicate.tsx` - Pass device model props
- `/work/frontend/src/lib/utils/sort-preferences.ts` - Migration from macAddress to key
- `/work/frontend/tests/api/factories/devices.ts` - Rewritten for new API
- `/work/frontend/tests/e2e/devices/DevicesPage.ts` - Updated selectors
- `/work/frontend/tests/e2e/devices/devices-crud.spec.ts` - Updated tests for new flow
- `/work/frontend/tests/support/fixtures.ts` - Added deviceModels fixture

**New Files (Untracked)**
- `/work/frontend/src/hooks/use-device-models.ts` - Device model hooks
- `/work/frontend/src/hooks/use-rotation.ts` - Rotation hooks
- `/work/frontend/src/lib/test/form-instrumentation.ts` - Form instrumentation
- `/work/frontend/src/lib/utils/monaco-schema.ts` - Monaco schema configuration
- `/work/frontend/src/components/ui/select.tsx` - Select component
- `/work/frontend/src/routes/device-models/index.tsx` - List route
- `/work/frontend/src/routes/device-models/new.tsx` - Create route
- `/work/frontend/src/routes/device-models/$modelId.tsx` - Edit route
- `/work/frontend/src/components/device-models/device-model-editor.tsx` - Editor component
- `/work/frontend/src/components/device-models/device-model-list-table.tsx` - Table component
- `/work/frontend/src/routes/rotation.tsx` - Dashboard route
- `/work/frontend/src/components/rotation/rotation-dashboard.tsx` - Dashboard component
- `/work/frontend/tests/api/factories/device-models.ts` - Device models factory
