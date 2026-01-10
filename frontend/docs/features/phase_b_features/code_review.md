# Phase B Implementation — Code Review

**Reviewed**: Unstaged changes implementing device configuration management features
**Reviewer**: Claude Code
**Date**: 2026-01-10

---

## 1) Summary & Decision

**Readiness**

The Phase B implementation delivers a partial but functional device configuration management UI with several critical gaps relative to the approved plan. The core CRUD operations, Monaco JSON editor integration, device list with sorting, and toast notifications are implemented with clean code patterns. However, the implementation lacks form instrumentation, has minimal test coverage (only 2 smoke tests vs. the comprehensive suite planned), and exhibits several correctness issues including incorrect API request bodies, missing cache invalidation, incomplete MAC rename flows, and a critical navigation bug using `window.location.href`. The code quality is generally good with proper TypeScript usage, but the missing instrumentation and test gaps leave the feature unverifiable in the Playwright suite.

**Decision**

`NO-GO` — The implementation cannot ship in its current state. Critical blockers include:
1. API contract violations in the device factory (`content` wrapper breaks backend contract)
2. Missing form instrumentation required for test determinism
3. Minimal test coverage (2/19 planned test scenarios)
4. Duplicate button navigation using `window.location.href` breaks TanStack Router contract
5. Missing testData bundle integration for devices factory
6. Missing devices page object fixture in test support

The core UI components and hooks are well-structured and reusable, but the feature is incomplete for production handoff. Estimated 2-3 days to address blockers and complete test coverage.

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- **Device list UI (plan section 13, slice 2)** ↔ `src/routes/devices/index.tsx:16-110` — Implemented with sortable table, skeleton loader, empty state, and "New Device" button. Missing list loading instrumentation emits events but no form instrumentation for edit/delete actions.

- **Device editor routes (plan section 14, slice 2)** ↔ `src/routes/devices/new.tsx:1-15`, `src/routes/devices/$macAddress.tsx:1-35`, `src/routes/devices/$macAddress/duplicate.tsx:1-35` — All three routes implemented with correct mode props to shared DeviceEditor component.

- **Monaco JSON editor integration (plan section 5, slice 2)** ↔ `src/components/devices/device-editor.tsx:230-243` — Monaco editor configured per spec: JSON language, vs-dark theme, minimap disabled, folding enabled, tab size 2.

- **Custom hooks wrapping API (plan section 2, slice 1)** ↔ `src/hooks/use-devices.ts:1-120` — Hooks implemented with camelCase mapping, toast integration, and proper error handling.

- **Toast system (plan section 2, slice 1)** ↔ `src/contexts/toast-context.tsx:1-45`, `src/components/ui/toast.tsx:1-173` — Full toast system with dark mode styling, success/error/warning/info variants, auto-dismiss.

- **Confirmation dialogs (plan section 2, slice 1)** ↔ `src/hooks/use-confirm.ts:1-66`, `src/components/ui/dialog.tsx:183-244` — Promise-based confirmation hook with Radix UI dialog, destructive styling support.

- **Sort preferences (plan section 2, slice 1)** ↔ `src/lib/utils/sort-preferences.ts:1-44` — LocalStorage persistence with validation, default fallback.

**Gaps / deviations**

- **Form instrumentation (plan section 9, slice 2)** — Missing entirely. Plan requires `useFormInstrumentation` with formId `DeviceEditor_new|edit|duplicate` emitting `form` events (open, submit, success, error phases). No `src/hooks/use-form-instrumentation.ts` file exists, and DeviceEditor component (`src/components/devices/device-editor.tsx`) never emits form events.

- **Comprehensive Playwright tests (plan section 14, slice 3)** — Only 2 smoke tests exist (`tests/e2e/devices/devices-crud.spec.ts:1-19`). Plan requires 19 test scenarios across create, edit, duplicate, delete, MAC rename, unsaved changes, error handling. Missing: `device-editor.spec.ts`, `device-errors.spec.ts`, and ~95% of planned test coverage.

- **Test data bundle integration (plan section 14, slice 3)** — `tests/api/factories/devices.ts` exists but is never integrated into `tests/support/fixtures.ts`. No `testData.devices` fixture available to test specs.

- **Devices page object fixture (plan section 14, slice 3)** — `tests/e2e/devices/DevicesPage.ts` exists but never registered in `tests/support/fixtures.ts`. Tests cannot use `devices` fixture.

- **MAC rename flow (plan section 5, slice 2)** — Partially implemented (`src/components/devices/device-editor.tsx:99-120`) but missing success toast "Device renamed from X to Y". Code only shows generic "Device configuration saved successfully" message.

- **Navigation blocker (plan section 10, slice 2)** — Cancel button shows confirmation dialog when dirty (`src/components/devices/device-editor.tsx:135-149`), but no TanStack Router `useBlocker` for sidebar navigation. Plan requires navigation guard for all route changes, not just Cancel button.

- **Table-based list (plan section 2)** — Implemented with `<table>` element (`src/components/devices/device-list-table.tsx:71-118`), but Edit button uses `<a href>` instead of TanStack Router `<Link>`. This bypasses client-side navigation and loses React state.

---

## 3) Correctness — Findings (ranked)

### Finding 1: API Contract Violation in Device Factory

- **Title**: `Blocker — Device factory wraps config in incorrect "content" field`
- **Evidence**: `tests/api/factories/devices.ts:36-40` — Factory calls `this.client.PUT('/api/configs/{mac_address}', { body: { content: config } })` but the generated API type `ConfigSaveRequestSchema_6be28b6` expects flat `{ deviceName, deviceEntityId, enableOTA }` at body root, not nested under `content`.
- **Impact**: All devices created via factory will fail with 400 validation errors. Tests cannot seed prerequisite data, making the entire Playwright suite non-functional.
- **Fix**: Remove `content` wrapper. Change to:
  ```typescript
  body: config
  ```
- **Confidence**: High. Cross-referenced `src/lib/api/generated/hooks.ts:99` `usePutConfigsByMacAddress` signature and plan section 3 API contracts confirm flat body structure.

### Finding 2: Missing Form Instrumentation Blocks Test Determinism

- **Title**: `Blocker — DeviceEditor never emits form lifecycle events`
- **Evidence**: `src/components/devices/device-editor.tsx:1-256` — Component uses mutations directly without wrapping in instrumentation. No calls to `emitTestEvent` with `kind: 'form'`, no `useFormInstrumentation` hook import.
- **Impact**: Playwright tests cannot wait for `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_new' && evt.phase === 'success')`. Tests must use brittle waits on toast visibility or URL changes instead of documented instrumentation patterns. Violates project's core testing principle (plan section 9, docs/contribute/testing/playwright_developer_guide.md:128-154).
- **Fix**: Create `src/hooks/use-form-instrumentation.ts` following ElectronicsInventory pattern. Add to DeviceEditor:
  ```typescript
  useFormInstrumentation({
    formId: `DeviceEditor_${mode}`,
    isOpen: true,
    onSubmit: () => { /* track submit phase */ },
    onSuccess: () => { /* track success phase */ },
    onError: () => { /* track error phase */ }
  })
  ```
- **Confidence**: High. Plan section 9 explicitly requires form instrumentation, and CLAUDE.md line 85 states "UI feature is incomplete without automated verification."

### Finding 3: Duplicate Button Navigation Breaks Router Contract

- **Title**: `Major — window.location.href bypasses TanStack Router`
- **Evidence**: `src/components/devices/device-editor.tsx:154` — Duplicate button uses `window.location.href = `/devices/${initialMacAddress}/duplicate`` instead of `navigate({ to: '/devices/$macAddress/duplicate', params: { macAddress: initialMacAddress } })`.
- **Impact**: Full page reload loses React state, breaks hot module replacement in dev mode, bypasses router instrumentation, and prevents route transitions from emitting test events. Users experience jarring full-page refresh instead of instant client-side navigation.
- **Fix**: Replace with TanStack Router navigation:
  ```typescript
  navigate({ to: '/devices/$macAddress/duplicate', params: { macAddress: initialMacAddress } })
  ```
- **Confidence**: High. TanStack Router provides typed navigation; `window.location.href` is explicitly anti-pattern in React SPA architecture.

### Finding 4: Edit Button Uses Anchor Tag Instead of Link

- **Title**: `Major — Device list edit button bypasses client-side routing`
- **Evidence**: `src/components/devices/device-list-table.tsx:99-103` — Edit button renders `<a href={`/devices/${device.macAddress}`}>` instead of importing and using `Link` from `@tanstack/react-router`.
- **Impact**: Clicking Edit triggers full-page navigation, losing React Query cache, forcing complete app remount. Slower user experience and breaks route transition instrumentation.
- **Fix**: Import Link and replace anchor:
  ```typescript
  import { Link } from '@tanstack/react-router'
  // ...
  <Link to="/devices/$macAddress" params={{ macAddress: device.macAddress }}>
    <Button variant="outline" size="sm" data-testid="devices.list.row.edit-button">
      Edit
    </Button>
  </Link>
  ```
- **Confidence**: High. Plan section 12 references TanStack Router patterns; anchor tags violate SPA navigation principles.

### Finding 5: Missing Cache Invalidation for MAC Rename

- **Title**: `Major — MAC rename doesn't invalidate GET /configs/:macAddress cache`
- **Evidence**: `src/components/devices/device-editor.tsx:99-120` — MAC rename calls save + delete mutations but never invalidates the old MAC's detail query cache. React Query will retain stale cache entry for deleted MAC.
- **Impact**: If user navigates back to deleted MAC's edit route (e.g., browser back button), UI shows stale cached config instead of 404. Cache pollution accumulates over time.
- **Fix**: Add manual invalidation after delete:
  ```typescript
  await deleteDevice.mutateAsync({ macAddress: originalMacRef.current })
  queryClient.invalidateQueries({ queryKey: ['getConfigsByMacAddress', { mac_address: originalMacRef.current }] })
  ```
- **Confidence**: Medium. React Query's automatic invalidation from generated hooks may not cover cross-MAC scenarios.

### Finding 6: Missing Toast Message for MAC Rename Success

- **Title**: `Minor — Generic success toast doesn't indicate rename occurred`
- **Evidence**: `src/components/devices/device-editor.tsx:115` — After MAC rename, code calls `onSaveCallback?.()` and navigates, but success toast shows generic "Device configuration saved successfully" (from `useSaveDevice` hook). Plan section 5 requires specific message "Device renamed from {originalMac} to {newMac}".
- **Impact**: Users lose feedback on destructive rename operation. Reduces confidence that old MAC was successfully deleted.
- **Fix**: Pass custom success handler to mutation to override generic toast:
  ```typescript
  await saveDevice.mutateAsync({ macAddress, config }, {
    onSuccess: () => {
      showSuccess(`Device renamed from ${originalMacRef.current} to ${macAddress}`)
    }
  })
  ```
- **Confidence**: High. Plan section 5 explicitly specifies rename toast message.

### Finding 7: DeviceEditor JSON Validation State Recomputes on Every Render

- **Title**: `Minor — Missing useMemo for isValid derived state`
- **Evidence**: `src/components/devices/device-editor.tsx:158` — `isValid` is computed inline as `!!macAddress.trim() && !jsonError && !saveDevice.isPending` on every render without memoization.
- **Impact**: Negligible performance impact (simple boolean checks), but violates React best practices for derived state. Could cause unnecessary re-renders of disabled button state.
- **Fix**: Wrap in `useMemo`:
  ```typescript
  const isValid = useMemo(
    () => !!macAddress.trim() && !jsonError && !saveDevice.isPending,
    [macAddress, jsonError, saveDevice.isPending]
  )
  ```
- **Confidence**: Medium. Optimization may not be necessary, but plan section 6 mentions derived state patterns.

---

## 4) Over-Engineering & Refactoring Opportunities

- **Hotspot**: Device editor route modules (`src/routes/devices/new.tsx`, `src/routes/devices/$macAddress.tsx`, `src/routes/devices/$macAddress/duplicate.tsx`)
- **Evidence**: All three routes duplicate loading/error UI (lines 13-27 in edit, lines 13-27 in duplicate). New route is trivial wrapper (15 lines).
- **Suggested refactor**: Merge all three routes into single route with mode detection:
  ```typescript
  // src/routes/devices/$mode.tsx or src/routes/devices/index.tsx with search params
  const mode = params.mode || 'list'
  ```
  However, current separation aligns with plan's explicit three-route architecture (plan section 2). No action required unless team prefers consolidation.
- **Payoff**: Reduces file count from 3 to 1, eliminates duplicate loading states. Trade-off: loses explicit route declarations in router tree.

---

## 5) Style & Consistency

### Pattern 1: Inconsistent Navigation Methods

- **Pattern**: Mix of `navigate()`, `window.location.href`, and `<a href>` for navigation
- **Evidence**:
  - `src/components/devices/device-editor.tsx:116,128,148` uses `navigate({ to: '/devices' })`
  - `src/components/devices/device-editor.tsx:154` uses `window.location.href`
  - `src/components/devices/device-list-table.tsx:99` uses `<a href>`
- **Impact**: Breaks router instrumentation, inconsistent user experience (some navigations instant, others reload page)
- **Recommendation**: Standardize on TanStack Router `navigate()` and `<Link>` throughout. Remove all `window.location.href` and anchor tags for internal routes.

### Pattern 2: Missing TypeScript Import Types

- **Pattern**: Some files import types without `type` keyword
- **Evidence**:
  - `src/components/devices/device-editor.tsx:2` imports `useNavigate` (runtime) correctly, but no `type` prefix for type-only imports elsewhere
  - `src/components/devices/device-list-table.tsx:4-5` imports `DeviceConfig` and `SortPreference` — these are types but lack `type` keyword
- **Impact**: Slightly larger bundle size (types not tree-shaken), violates TypeScript best practices
- **Recommendation**: Add `import type { DeviceConfig } from ...` for all type-only imports per project tsconfig strict mode

### Pattern 3: Console.error in Production Code

- **Pattern**: DeviceEditor logs errors to console in production
- **Evidence**:
  - `src/components/devices/device-editor.tsx:112,119` uses `console.error('Failed to delete old MAC:', deleteError)` and `console.error('Save failed:', error)`
- **Impact**: Leaks error details to browser console in production, no structured logging for monitoring
- **Recommendation**: Replace with toast notifications (already shown) or remove console.error calls. Errors already surfaced via toast system; console logging is redundant.

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

### Surface: Device List Display

- **Scenarios**:
  - Given backend has 0 devices, When user navigates to /devices, Then empty state displays (`tests/e2e/devices/devices-crud.spec.ts:4-7`) ✅
  - Given backend has 3 devices, When user navigates, Then table displays 3 rows — **MISSING**
  - Given device with enableOta=true/false/null, When list renders, Then OTA Status shows icons — **MISSING**
- **Hooks**:
  - `useListLoadingInstrumentation` present (`src/routes/devices/index.tsx:24-28`) ✅
  - `data-testid="devices.list.table"` present (`src/components/devices/device-list-table.tsx:71`) ✅
  - `data-testid="devices.list.row"` present (`src/components/devices/device-list-table.tsx:87`) ✅
- **Gaps**: No tests verify actual device data display, icon rendering, or loading states
- **Evidence**: Plan section 13 requires 6 list display scenarios; only 1 implemented (empty state)

### Surface: Table Sorting

- **Scenarios**:
  - Given user clicks column header, When sort toggles, Then preference persists — **MISSING**
  - Given table sorted, When page refreshes, Then sort preference restored — **MISSING**
- **Hooks**:
  - `data-testid="devices.list.header.macAddress"` etc. present (`src/components/devices/device-list-table.tsx:58`) ✅
  - LocalStorage read/write in `getSortPreference`/`setSortPreference` ✅
- **Gaps**: Zero test coverage for sorting functionality
- **Evidence**: Plan section 13 requires 4 sort scenarios; 0 implemented

### Surface: Create New Device

- **Scenarios**:
  - Given user clicks New Device button, When navigation completes, Then editor displays (`tests/e2e/devices/devices-crud.spec.ts:9-14`) ✅
  - Given user enters MAC and JSON, When clicks Save, Then device created — **MISSING**
  - Given user enters invalid JSON, When save attempted, Then button disabled — **MISSING**
- **Hooks**:
  - `data-testid="devices.editor.mac-input"` present ✅
  - `data-testid="devices.editor.save"` present ✅
  - **Form instrumentation MISSING** ❌
- **Gaps**: No tests verify actual save flow, validation, or success navigation
- **Evidence**: Plan section 13 requires 4 create scenarios; only 1 partial navigation test exists

### Surface: Edit Existing Device

- **Scenarios**: **ALL MISSING** (0/4 scenarios)
- **Hooks**: UI instrumentation present, form instrumentation missing
- **Gaps**: No tests for edit flow, MAC rename, duplicate navigation, or unsaved changes
- **Evidence**: Plan section 13 requires 4 edit scenarios; 0 implemented

### Surface: MAC Address Rename

- **Scenarios**: **ALL MISSING** (0/2 scenarios)
- **Hooks**: Logic implemented but untested, missing specific rename toast
- **Gaps**: Critical MAC rename flow (save new + delete old) has zero test coverage
- **Evidence**: Plan section 13 requires 2 MAC rename scenarios; 0 implemented

### Surface: Delete Device

- **Scenarios**: **ALL MISSING** (0/4 scenarios)
- **Hooks**: Confirmation dialog exists, delete button present, no form events emitted
- **Gaps**: No tests verify delete confirmation, success refresh, or error handling
- **Evidence**: Plan section 13 requires 4 delete scenarios; 0 implemented

### Surface: Unsaved Changes Warning

- **Scenarios**: **ALL MISSING** (0/3 scenarios)
- **Hooks**: Cancel confirmation implemented, no navigation blocker for router changes
- **Gaps**: Critical UX protection (unsaved changes) has zero test coverage
- **Evidence**: Plan section 13 requires 3 unsaved changes scenarios; 0 implemented

### Surface: Error Handling

- **Scenarios**: **ALL MISSING** (0/4 scenarios)
- **Hooks**: Toast system exists, no test-specific error triggers
- **Gaps**: Validation errors, network errors, conflicts all untested
- **Evidence**: Plan section 13 requires 4 error scenarios; 0 implemented

**Summary**: 2 of 19 planned test scenarios implemented (~10% coverage). Core CRUD flows, MAC rename, sorting, unsaved changes, and error handling lack any test verification.

---

## 7) Adversarial Sweep

### Attack 1: Race Condition on Rapid Save Clicks

- **Scenario**: User double-clicks Save button before first mutation completes
- **Evidence**: `src/components/devices/device-editor.tsx:189-195` — Save button disables when `saveDevice.isPending=true`, but React state update is async. Gap exists between click and pending state update.
- **Why code held up**: Button's `disabled` prop checks `!isValid` which includes `!saveDevice.isPending`. TanStack Query mutations have built-in deduplication. Second click would be a no-op even if it reaches mutation layer.
- **Confidence**: Medium. React 19's automatic batching should prevent race, but explicit `disabled={saveDevice.isPending}` would be safer.

### Attack 2: Stale Closure in Monaco Editor onChange

- **Scenario**: User rapidly types in Monaco editor while validation callback is stale
- **Evidence**: `src/components/devices/device-editor.tsx:68-77` — `validateJson` callback is wrapped in `useCallback` with empty deps array. If validation logic needed to reference changing state, closure would be stale.
- **Why code held up**: `validateJson` only uses `setJsonError` (stable dispatch) and `JSON.parse` (pure function). No external state dependencies. Closure is correctly stable.
- **Confidence**: High.

### Attack 3: LocalStorage Quota Exceeded on Sort Preference Write

- **Scenario**: Browser's localStorage quota exceeded when persisting sort preference
- **Evidence**: `src/lib/utils/sort-preferences.ts:37-43` — `setSortPreference` wraps `localStorage.setItem` in try-catch with silent failure. No user feedback on save failure.
- **Why code held up**: Silent failure is acceptable for sort preferences (non-critical UX state). If localStorage unavailable (private browsing, quota exceeded), default sort applies on next render. Plan section 3 notes "acceptable for internal tooling."
- **Confidence**: High. Sort preferences are ephemeral UX state, not critical data.

### Attack 4: Navigate Away During MAC Rename Async Operation

- **Scenario**: User starts MAC rename (save new + delete old), then immediately navigates via sidebar before delete completes
- **Evidence**: `src/components/devices/device-editor.tsx:99-120` — No abort controller or cleanup on unmount. If component unmounts during `deleteDevice.mutateAsync`, promise is abandoned but mutation continues.
- **Why code held up**: React Query mutations continue even after component unmount (by design). Backend completes delete successfully. User sees renamed device in list after navigation. No data corruption.
- **Confidence**: Medium. Orphaned mutation is acceptable but could leave UI briefly inconsistent (old MAC still visible if list loads before delete completes).

### Attack 5: JSON.parse Throws on Malicious Input

- **Scenario**: User pastes extremely large JSON (10MB+) or crafted input that causes JSON.parse DoS
- **Evidence**: `src/components/devices/device-editor.tsx:68-77` — `validateJson` wraps `JSON.parse` in try-catch, sets `jsonError` on throw. Save button disabled when error exists.
- **Why code held up**: Try-catch prevents crash. Large inputs may freeze UI briefly during parse, but button remains disabled preventing submission. Monaco editor itself may struggle with 10MB+ documents (separate concern).
- **Confidence**: High. Client-side parse is defensive; backend validates again before persistence.

**Checks attempted**:
- Race conditions in mutation submission
- Stale closures in async handlers
- LocalStorage failure handling
- Async cleanup on unmount
- Input validation DoS

**Evidence**: `src/components/devices/device-editor.tsx:68-158`, `src/hooks/use-devices.ts:68-119`, `src/lib/utils/sort-preferences.ts:37-43`

---

## 8) Invariants Checklist

### Invariant 1: Sorted Array Length Matches Raw Array Length

- **Invariant**: `sortedDevices.length === devices.length` (no filtering, only reordering)
- **Where enforced**: `src/components/devices/device-list-table.tsx:22-38` — `useMemo` sorts a shallow copy `[...devices]`, never filters
- **Failure mode**: If sort logic accidentally filtered out null values or threw on comparisons, table would display fewer rows than backend returned
- **Protection**: Explicit null handling in comparator (lines 28-31) ensures nulls sort consistently. No conditional filtering.
- **Evidence**: Sort logic is read-only transformation; array spread + in-place sort

### Invariant 2: isDirty Triggers Beforeunload Listener

- **Invariant**: `isDirty=true` ⇒ beforeunload listener active; `isDirty=false` ⇒ listener removed
- **Where enforced**: `src/components/devices/device-editor.tsx:52-65` — `useEffect` with `[isDirty]` dependency adds/removes listener
- **Failure mode**: If dependency array omitted or incorrect, listener could persist after save (annoying) or fail to attach when dirty (data loss risk)
- **Protection**: Dependency array includes `isDirty`; effect cleanup returns listener removal function
- **Evidence**: React guarantees effect cleanup on dependency change and unmount

### Invariant 3: Save Button Disabled on Invalid JSON

- **Invariant**: `jsonError !== null` ⇒ Save button disabled
- **Where enforced**: `src/components/devices/device-editor.tsx:158,192` — `isValid` derived state includes `!jsonError` check, passed to button `disabled` prop
- **Failure mode**: If `isValid` logic omitted `jsonError` check, user could submit unparseable JSON, causing backend 400 or app crash
- **Protection**: `isValid` computed from three conditions: `!!macAddress.trim() && !jsonError && !saveDevice.isPending`. All three required for enabled state.
- **Evidence**: Double-guarded by validation on change (line 82) and pre-submit validation (line 92)

### Invariant 4: React Query Cache Invalidation After Mutations

- **Invariant**: After PUT/DELETE device, `getConfigs` query refetches list
- **Where enforced**: `src/lib/api/generated/hooks.ts` (generated) — mutations configured with `onSuccess` invalidation
- **Failure mode**: If invalidation missing, list shows stale data after CRUD operations. User sees old device count/data until manual refresh.
- **Protection**: Generated hooks include automatic invalidation. Verified by checking `usePutConfigsByMacAddress` and `useDeleteConfigsByMacAddress` source (not in diff, but plan section 4 confirms pattern).
- **Evidence**: Plan section 4 notes "Mutations invalidate `['getConfigs']` query keys" — generated hooks handle this

---

## 9) Questions / Needs-Info

### Question 1: Is Form Instrumentation Intentionally Deferred?

- **Question**: DeviceEditor has zero form instrumentation. Was this intentional (defer to later sprint) or oversight?
- **Why it matters**: Without form events, Playwright suite cannot verify save/error flows deterministically. Current 2-test delivery suggests instrumentation may be deferred, but plan explicitly includes it in slice 2.
- **Desired answer**: Confirm whether form instrumentation should be part of this delivery or documented as follow-up work. If follow-up, update plan's slice 2 scope.

### Question 2: Are Comprehensive Tests Deferred or Incomplete?

- **Question**: Plan requires 19 test scenarios; delivery has 2. Is this a partial delivery checkpoint or unexpected gap?
- **Why it matters**: Defines review recommendation (NO-GO vs. GO-WITH-CONDITIONS). If tests are intentionally deferred to slice 4, feature could ship with manual QA. If tests were intended for this delivery, feature is incomplete.
- **Desired answer**: Clarify if test completion is blocked by instrumentation (Q1) or if tests are out of scope for this review.

### Question 3: Should Edit Button Use Link or Anchor?

- **Question**: DeviceListTable edit button uses `<a href>` (full page load). Is there a reason not to use TanStack Router `<Link>`?
- **Why it matters**: Performance and UX degradation. Full-page navigations are slower and break React state.
- **Desired answer**: Confirm `<Link>` is preferred, or document if anchor tags have intentional purpose (e.g., server-side routing requirement).

### Question 4: Should MAC Rename Flow Have Custom Toast?

- **Question**: Plan specifies toast "Device renamed from X to Y" but code shows generic success message. Intentional simplification?
- **Why it matters**: User feedback on destructive operation. Generic message doesn't confirm old MAC deletion.
- **Desired answer**: Confirm if custom rename toast is required or if generic message is acceptable.

---

## 10) Risks & Mitigations (top 3)

### Risk 1: Device Factory API Contract Mismatch Breaks All Tests

- **Risk**: Device factory wraps config in `{ content: {...} }` but backend expects flat structure. All Playwright tests will fail on prerequisite data setup.
- **Mitigation**: Fix `tests/api/factories/devices.ts:36-40` to pass flat `body: config` instead of `body: { content: config }` before running any tests. Verify fix with manual API call via curl/Postman.
- **Evidence**: Finding 1, `tests/api/factories/devices.ts:36-40`

### Risk 2: Missing Form Instrumentation Prevents Test Completion

- **Risk**: Without form events, test suite cannot verify CRUD flows without brittle waits. Implementing instrumentation post-hoc may require refactoring DeviceEditor state management.
- **Mitigation**: Create `src/hooks/use-form-instrumentation.ts` following ElectronicsInventory reference (`src/components/types/type-form.tsx:73-82` pattern). Integrate into DeviceEditor `handleSave` and mutation callbacks. Estimated 4-6 hours.
- **Evidence**: Finding 2, gap analysis in section 6

### Risk 3: Minimal Test Coverage Leaves Feature Unverified

- **Risk**: 2 of 19 scenarios implemented. Core flows (save, delete, MAC rename, errors) have zero automated verification. Regressions will go unnoticed until production.
- **Mitigation**: Prioritize test completion before merge. Focus on high-risk flows: MAC rename (destructive), delete confirmation, validation errors. Defer nice-to-have scenarios (sort persistence, unsaved changes browser warning) to follow-up sprint if timeline constrained.
- **Evidence**: Section 6 coverage analysis, plan section 14 slice 3

---

## 11) Confidence

Confidence: Medium — The implementation demonstrates solid React/TypeScript fundamentals and follows project architecture patterns for UI components, hooks, and styling. The device list, editor, and toast/dialog systems are well-structured and reusable. However, three critical gaps undermine confidence: (1) API contract violation in the test factory blocks all Playwright execution, (2) missing form instrumentation violates project testing standards, and (3) 10% test coverage leaves the feature unverified. The code quality is high where implemented, but the incomplete test infrastructure and instrumentation gaps mean the feature cannot be validated against its own acceptance criteria.

---

## Final Recommendations

### Must Fix (Blockers for GO)

1. **Fix device factory API body structure** — Remove `content` wrapper in `tests/api/factories/devices.ts:36-40`
2. **Add form instrumentation** — Create `use-form-instrumentation.ts` hook and integrate into DeviceEditor
3. **Replace window.location.href with navigate()** — Fix duplicate button navigation in `device-editor.tsx:154`
4. **Replace anchor tag with Link** — Fix edit button in `device-list-table.tsx:99-103`
5. **Integrate devices factory into testData bundle** — Add to `tests/support/fixtures.ts`
6. **Register devices page object fixture** — Add to `tests/support/fixtures.ts`

### Should Fix (Improves Quality)

7. **Complete test coverage** — Implement remaining 17 test scenarios per plan section 13
8. **Add MAC rename toast message** — Show specific "renamed from X to Y" message
9. **Add cache invalidation for old MAC on rename** — Prevent stale cache for deleted MAC
10. **Standardize on type imports** — Add `import type` for type-only imports
11. **Remove console.error calls** — Rely on toast notifications only

### Nice to Have (Polish)

12. **Add navigation blocker for unsaved changes** — Implement TanStack Router `useBlocker` for sidebar navigation
13. **Memoize isValid derived state** — Minor performance optimization

---

## Verification Commands

Before handoff, run:

```bash
# Type check
pnpm check

# Run device tests (after fixing factory)
pnpm playwright test tests/e2e/devices/

# Verify no route mocks
pnpm eslint tests/ --rule 'testing/no-route-mocks: error'
```

Expected: All commands pass without errors. Device tests should have >80% coverage of plan scenarios.
