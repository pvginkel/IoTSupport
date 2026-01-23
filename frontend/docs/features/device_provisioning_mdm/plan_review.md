# Plan Review: Device Provisioning MDM

## 1) Summary & Decision

**Readiness**

The updated plan demonstrates thorough research, detailed data contracts, and clear implementation slices. The previous review conditions have been addressed: form instrumentation is now explicitly planned in Slice 1 before form component work begins (lines 999-1006), Monaco schema validation has been updated to use URI-based association instead of global defaults (lines 696-712, 1028-1029), test factory migration has been moved to Slice 0 to establish a green CI baseline (lines 986-996), and the model name map strategy for device list display has been documented (lines 639-646). The plan aligns well with the codebase patterns and testing requirements.

**Decision**

`GO` — All previous review conditions have been adequately addressed. The plan is implementation-ready with clear slices, proper instrumentation sequencing, and documented strategies for the key technical challenges (Monaco schema isolation, client-side model joins).

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/contribute/testing/playwright_developer_guide.md` — Pass — `plan.md:986-996` — "Slice 0: Test Infrastructure Migration (FIRST)... Fix broken test factories before any UI work... Verification: Run `pnpm playwright test tests/e2e/devices/` to confirm existing tests pass"
  - The plan correctly prioritizes factory updates before UI changes, matching the guide's "API-first data setup" requirement.

- `docs/contribute/testing/factories_and_fixtures.md` — Pass — `plan.md:961-980` — Factory scenarios document proper extension of the factory bundle with new domain factories for device models.
  - The plan follows the established factory pattern (create, randomHelpers, delete methods).

- `docs/contribute/architecture/application_overview.md` — Pass — `plan.md:145-161` — "Custom hooks in `src/hooks/` adapt API responses to frontend domain models (snake_case to camelCase)"
  - Plan correctly documents camelCase transformation in data model section (lines 319, 339, 358-359, 407).

- `docs/contribute/testing/playwright_developer_guide.md` (instrumentation) — Pass — `plan.md:799-824` — Form events documented with `useFormInstrumentation` hook planned for Slice 1
  - The plan now explicitly creates the instrumentation hook before the form components that consume it.

**Fit with codebase**

- `useListLoadingInstrumentation` — `plan.md:769-795` — Confirmed alignment: plan documents scope patterns (`deviceModels.list`, `devices.list`, `rotation.dashboard`) consistent with existing `types.list`, `parts.list` patterns in `query-instrumentation.ts:132-236`.

- `FormTestEvent` interface — `plan.md:799-824` — Confirmed alignment: the planned `useFormInstrumentation` hook correctly targets the existing `FormTestEvent` interface at `src/types/test-events.ts:44-55` with phases `open`, `submit`, `success`, `error`.

- Monaco Editor integration — `plan.md:696-712` — Confirmed alignment: URI-based schema association avoids global state pollution, addressing the concern about multiple editors or navigation between devices with different models.

- Device hooks rewrite — `plan.md:145-161` — Confirmed necessary: current `use-devices.ts` imports `useGetConfigs`, `usePostConfigs` from old `/api/configs` endpoints (verified at `src/hooks/use-devices.ts:3-11`), which no longer exist per the change brief.

---

## 3) Open Questions & Ambiguities

- Question: How will the device model factory ensure models are available before device creation in Playwright specs?
- Why it matters: Device creation requires `device_model_id`; if specs create devices without first creating models, tests will fail.
- Needed answer: **Resolved by research** — The plan addresses this at lines 965-966: "Factory accepts model override, creates model first if not provided." This follows the existing `PartTestFactory` pattern in `factories_and_fixtures.md:22-23` where dependent entities are auto-created.

- Question: What is the expected file naming convention for the provisioning download?
- Why it matters: Users need predictable filenames for their device flashing workflows.
- Needed answer: Plan documents this as an open question (lines 1103-1107) with a reasonable follow-up: "Check backend Content-Disposition header; align with IoT team conventions." This is appropriately deferred as a non-blocking detail.

- Question: Should rotation status polling continue when the browser tab is backgrounded?
- Why it matters: Unnecessary polling wastes resources; stopping it could cause stale UI when user returns.
- Needed answer: **Resolved by research** — TanStack Query's default `refetchOnWindowFocus: true` handles this appropriately. The plan's 30s `refetchInterval` (lines 839-845) combined with default focus behavior provides a good UX without wasted polling.

---

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Device Models CRUD
- Scenarios:
  - Given no models exist, When user views list, Then empty state shown (`tests/e2e/device-models/device-models.spec.ts`)
  - Given user creates model with code "sensor_v1", When save clicked, Then model appears in list
  - Given model exists with device_count>0, When user views list, Then delete button is disabled
  - Given user enters invalid JSON Schema, When editing config_schema, Then save button disabled
- Instrumentation: `deviceModels.list` loading events, `DeviceModelForm_create`/`DeviceModelForm_edit` form events, `data-testid` selectors listed at lines 828-829
- Backend hooks: Device model factory at `tests/api/factories/device-models.ts`
- Gaps: None
- Evidence: `plan.md:921-933`

- Behavior: Device Creation with Model Selection
- Scenarios:
  - Given device models exist, When user creates device selecting model, Then device appears with auto-generated key
  - Given device with model that has config_schema, When user edits config, Then Monaco shows validation
- Instrumentation: `devices.list` loading events, `DeviceForm_create` form events, `devices.editor.model-selector` testid
- Backend hooks: Device factory updated to use `/api/devices` with `device_model_id`
- Gaps: None
- Evidence: `plan.md:934-946`

- Behavior: Rotation Dashboard
- Scenarios:
  - Given devices exist in various states, When user views dashboard, Then counts shown correctly
  - Given no pending rotation, When user clicks trigger, Then devices queued and count shown
- Instrumentation: `rotation.dashboard` loading events, trigger button `data-testid`
- Backend hooks: Rotation trigger API returns `queued_count`
- Gaps: Testing actual rotation completion requires backend time manipulation (documented as deferred at line 957)
- Evidence: `plan.md:948-958`

- Behavior: Provisioning Download
- Scenarios:
  - Given device exists, When user clicks download provisioning, Then .bin file downloads
- Instrumentation: Download button `data-testid="devices.editor.download-provisioning"` (line 831)
- Backend hooks: `GET /api/devices/{id}/provisioning` endpoint
- Gaps: Binary download verification in Playwright may require `download` event handling
- Evidence: `plan.md:940-941`

---

## 5) Adversarial Sweep (must find >=3 credible issues or declare why none exist)

**Minor — Device List Dual-Query Loading State**

**Evidence:** `plan.md:639-646` — "Device list component queries both `['getDevices']` and `['getDeviceModels']`; model name lookup uses a memoized map keyed by model ID."

**Why it matters:** The device list page must wait for both queries before rendering model names. If only `devices.list` instrumentation fires when devices load but models are still loading, Playwright assertions may see "Unknown" model names momentarily.

**Fix suggestion:** Ensure `useListLoadingInstrumentation` for `devices.list` only emits `ready` after both queries have resolved. The existing `useListLoadingInstrumentation` hook accepts `isLoading` and `isFetching` — pass the combined loading state: `isLoading: devicesQuery.isLoading || modelsQuery.isLoading`.

**Confidence:** Medium

---

**Minor — Monaco Schema Cleanup on Fast Navigation**

**Evidence:** `plan.md:696-712` — "cleanup in `useEffect` return to remove schema associations on unmount/model change"

**Why it matters:** If a user navigates quickly between devices with different models, React 18+ concurrent features could batch unmount/mount operations, potentially causing a brief window where the old schema is still registered alongside the new one.

**Fix suggestion:** Use a unique model URI per editor instance (e.g., include a component instance ID), and ensure `setDiagnosticsOptions` is called with only the current schema (not appending). The current plan at lines 703-712 shows the right pattern. During implementation, verify Monaco's `setDiagnosticsOptions` replaces rather than merges schemas.

**Confidence:** Low (Monaco likely handles this correctly, but worth verifying)

---

**Minor — Rotation Dashboard Counts vs Lists Consistency**

**Evidence:** `plan.md:527-529` — "Outputs: `{ healthy: DashboardDevice[], warning: DashboardDevice[], critical: DashboardDevice[], counts: Record<string, number> }`"

**Why it matters:** If counts and lists come from the same response but a device transitions state between list population and count calculation on the backend, the UI could show mismatched data (e.g., counts say 5 warning but list shows 4).

**Fix suggestion:** The backend likely calculates both atomically. During implementation, verify the dashboard endpoint returns consistent data. If inconsistency is observed, derive counts client-side from list lengths.

**Confidence:** Low (likely not an issue if backend is atomic)

---

## 6) Derived-Value & State Invariants (table)

- Derived value: `canDeleteModel`
  - Source dataset: `deviceModel.deviceCount` from single model query
  - Write / cleanup triggered: Enables/disables delete button (display only, no write)
  - Guards: `deviceCount === 0` required for delete
  - Invariant: Delete button state must re-evaluate when device count changes (cache invalidation on device create/delete)
  - Evidence: `plan.md:619-626`

- Derived value: `configSchema` (Monaco validation schema)
  - Source dataset: `device.deviceModel.configSchema` from device detail or selected model from dropdown
  - Write / cleanup triggered: Monaco schema association registered on mount, removed on unmount via `useEffect`
  - Guards: Only apply when schema is non-null; use URI-based association per editor
  - Invariant: Schema must match currently selected/loaded model; stale schemas cause incorrect validation
  - Evidence: `plan.md:628-635`

- Derived value: `modelNameMap` (device list display)
  - Source dataset: Full device models list from `useDeviceModels()`
  - Write / cleanup triggered: Display lookup only, no persistent writes
  - Guards: Handle deleted model gracefully (show ID or "Unknown")
  - Invariant: Map must refresh when models created/deleted to avoid stale lookups
  - Evidence: `plan.md:639-646`

- Derived value: `isDirty` (form dirty state)
  - Source dataset: Compare current form values against initial values
  - Write / cleanup triggered: Enables navigation blocker dialog
  - Guards: Blocker only active when `isDirty === true`
  - Invariant: Must reset after successful save
  - Evidence: `plan.md:658-664`

---

## 7) Risks & Mitigations (top 3)

- Risk: Test factory migration may uncover additional broken assumptions in existing device specs beyond endpoint changes
- Mitigation: Slice 0 explicitly includes "run full device test suite to confirm green baseline before proceeding" (line 995)
- Evidence: `plan.md:986-996`

- Risk: Monaco JSON Schema meta-validation for config_schema editor requires correct draft-07 meta-schema loading
- Mitigation: Plan documents "Use official JSON Schema draft-07 meta-schema" (line 1076); backend validation serves as backstop
- Evidence: `plan.md:1073-1077`

- Risk: Client-side model name join for device list could show stale names if models are renamed while device list is open
- Mitigation: TanStack Query's `staleTime` and automatic background refetch handle this; explicit invalidation on model update ensures fresh data
- Evidence: `plan.md:677-685`

---

## 8) Confidence

Confidence: High — The plan addresses all previous review conditions with specific implementation details. Slice ordering ensures test infrastructure is green before UI work begins. Form instrumentation is properly sequenced before form components. Monaco schema isolation strategy is well-documented. The adversarial sweep found only minor issues that do not block implementation.
