# Device Detail UX Fixes — Technical Plan

## 0) Research Log & Findings

**Searched areas:**
- `src/hooks/use-provisioning.ts` — full provisioning workflow, cleanup function, abort controller lifecycle
- `src/hooks/use-device-form.ts` — save/cancel handlers, navigation after mutation, form instrumentation
- `src/routes/devices/$deviceId/index.tsx` — `beforeLoad` redirect for tab preference
- `src/routes/devices/$deviceId/logs.tsx` — logs tab route (no changes needed, just referenced)
- `src/routes/devices/$deviceId.tsx` — layout route with header and outlet
- `src/lib/utils/device-tab-preference.ts` — localStorage get/set helpers
- `src/components/devices/device-detail-header.tsx` — tab bar, `useEffect` for persisting tab, tab click handler
- `src/lib/test/form-instrumentation.ts` — form event lifecycle used by `use-device-form`
- `src/lib/test/provisioning-instrumentation.ts` — provisioning event lifecycle
- `tests/e2e/devices/devices-tabs.spec.ts` — existing tab navigation specs
- `tests/e2e/devices/devices-crud.spec.ts` — existing CRUD specs (edit saves navigate to `/devices`)
- `tests/e2e/devices/devices-provisioning.spec.ts` — provisioning modal specs
- `tests/e2e/devices/DevicesPage.ts` — page object for device specs

**Key findings:**

1. **Provisioning cleanup** (`use-provisioning.ts:119-148`): The `cleanup` function unconditionally fires `abortControllerRef.current.abort()` before disconnecting the transport and closing the port. On the success path (line 486), `cleanup()` is called after verification completes, meaning the abort signal fires even though no operations are pending. The abort signal can corrupt the transport's reader/writer lock teardown, preventing `port.close()` from succeeding.

2. **Tab persistence** (`$deviceId/index.tsx:7-15`): The `beforeLoad` hook reads from localStorage and throws `redirect()`. This mechanism is unreliable in TanStack Router's file-based routing for index routes because `beforeLoad` runs outside the React lifecycle. The `DeviceDetailHeader` already persists tab preference on click and on `location.pathname` change (lines 23-29), so the restore logic just needs to move into a component-level effect.

3. **Post-save navigation** (`use-device-form.ts:141`): The edit-mode `onSuccess` handler calls `navigate({ to: '/devices' })`, sending the user back to the device list. The requirement is to navigate to the device's logs tab instead, and update the tab preference in localStorage.

4. **No conflicts** found between the three fixes — they touch distinct code paths within each file.

---

## 1) Intent & Scope

**User intent**

Three targeted fixes/enhancements to the device detail experience. Two are regressions from recent commits (COM port not releasing after flash, tab preference not restoring across device navigation) and one is a new behavior (navigate to logs tab after saving device configuration in edit mode).

**Prompt quotes**

- "COM port must actually disconnect/release after a successful flash"
- "The abort controller must NOT be fired on the success path"
- "The selected device tab must be remembered when navigating between devices"
- "After saving device configuration in edit mode, navigate to the device's Logs tab"
- "The tab preference in localStorage must be updated to 'logs' when navigating to the logs tab after save"

**In scope**

- Split the `cleanup` function in `use-provisioning.ts` so the success path disconnects/closes without firing the abort controller
- Replace the `beforeLoad` redirect in `$deviceId/index.tsx` with a component-level `useEffect` + `useNavigate` redirect
- Change the edit-mode `onSuccess` handler in `use-device-form.ts` to navigate to `/devices/$deviceId/logs` and persist the 'logs' tab preference
- Update existing Playwright specs for the changed navigation behavior (edit device test currently expects `/devices` after save)
- Add a Playwright spec for tab preference persistence across device navigation

**Out of scope**

- Changes to new/duplicate device save navigation (those still go to `/devices`)
- Redesigning the tab persistence mechanism (the localStorage approach is retained)
- Any backend changes
- Provisioning workflow logic beyond the cleanup/abort split

**Assumptions / constraints**

- The `Transport.disconnect()` method in the ESPLoader library cleanly releases reader/writer locks when no abort signal has been fired. This assumption is documented in the change brief and aligns with the Web Serial API spec.
- TanStack Router's `useNavigate` within a `useEffect` on the index route component reliably triggers navigation before the user sees a flash of the default tab content.
- The `deviceId` is always available in the `use-device-form` hook when `mode === 'edit'` (enforced by the existing guard at line 128-133).

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] COM port must actually disconnect/release after a successful flash — the serial port should no longer be locked after provisioning completes
- [ ] The abort controller must NOT be fired on the success path — only fire abort when explicitly cancelling (user abort or error path)
- [ ] The selected device tab (configuration/logs/coredumps) must be remembered when navigating between devices — if user is on the Logs tab, navigating to another device should show the Logs tab
- [ ] After saving device configuration in edit mode, navigate to the device's Logs tab (not back to the device list)
- [ ] The tab preference in localStorage must be updated to 'logs' when navigating to the logs tab after save

---

## 2) Affected Areas & File Map

- Area: `src/hooks/use-provisioning.ts` — `cleanup` function
- Why: Must split cleanup into two paths: one for success (disconnect + close only) and one for abort/error (abort signal + disconnect + close).
- Evidence: `src/hooks/use-provisioning.ts:119-148` — `cleanup` unconditionally calls `abortControllerRef.current.abort()` at line 122; success path calls `cleanup()` at line 486.

- Area: `src/routes/devices/$deviceId/index.tsx` — route module
- Why: Replace `beforeLoad` redirect with component-level navigation so tab preference is reliably restored.
- Evidence: `src/routes/devices/$deviceId/index.tsx:7-15` — `beforeLoad` reads `getDeviceTabPreference()` and throws `redirect()`.

- Area: `src/hooks/use-device-form.ts` — edit-mode `onSuccess` handler
- Why: Change post-save navigation from `/devices` to `/devices/$deviceId/logs` and update localStorage tab preference.
- Evidence: `src/hooks/use-device-form.ts:138-141` — `onSuccess` calls `navigate({ to: '/devices' })`.

- Area: `tests/e2e/devices/devices-crud.spec.ts` — "edits an existing device" test
- Why: The existing test asserts `await expect(page).toHaveURL('/devices')` after save; must change to expect `/devices/<id>/logs`.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:176` — `await expect(page).toHaveURL('/devices')`.

- Area: `tests/e2e/devices/devices-tabs.spec.ts` — tab persistence tests
- Why: Add a new spec verifying that tab preference persists across device navigation (open device A on Logs, navigate to device B, expect Logs tab active).
- Evidence: `tests/e2e/devices/devices-tabs.spec.ts` — existing tests cover basic tab navigation but not cross-device persistence.

---

## 3) Data Model / Contracts

- Entity / contract: `device-tab-preference` (localStorage)
- Shape: String value, one of `'configuration' | 'logs' | 'coredumps'`, stored under key `'iot-support-device-tab'`.
- Mapping: No API mapping — purely client-side state read/written by `getDeviceTabPreference()` / `setDeviceTabPreference()`.
- Evidence: `src/lib/utils/device-tab-preference.ts:1-25`

No API contract changes. No new query cache keys or data shapes.

---

## 4) API / Integration Surface

No new API endpoints or mutations. The three fixes are purely frontend concerns:

- The provisioning fix changes only the order and conditionality of serial port teardown calls (Web Serial API, not backend).
- The tab preference fix uses only localStorage.
- The post-save navigation fix changes the target of `navigate()` but the mutation itself (`updateDevice.mutate`) is unchanged.

Existing surfaces remain intact:

- Surface: `PATCH /api/devices/:id` via `useUpdateDevice` hook
- Inputs: `{ id, config }` — unchanged
- Outputs: Invalidates devices query cache on success — unchanged
- Errors: Surfaces through `onError` callback and form instrumentation — unchanged
- Evidence: `src/hooks/use-device-form.ts:135-148`

---

## 5) Algorithms & UI Flows

- Flow: Provisioning success cleanup (Fix 1)
- Steps:
  1. Provisioning verification completes successfully (phase: `verifying`, progress 98%)
  2. Call new `disconnectPort()` helper (does NOT fire abort controller)
  3. `disconnectPort()` pauses 100ms for in-flight operations to settle
  4. `disconnectPort()` calls `transportRef.current.disconnect()` to release reader/writer locks
  5. `disconnectPort()` calls `portRef.current.close()` to release the serial port
  6. Nullify refs (`transportRef`, `portRef`, `abortControllerRef`)
  7. Update state to `success` phase
  8. Emit `trackComplete` instrumentation event
- States / transitions: `verifying` -> port disconnect -> `success`
- Hotspots: The 100ms grace period mirrors the existing `cleanup` delay. If the transport's internal state machine is already idle after verification, the delay is harmless. If the transport still has pending micro-tasks, the delay prevents premature close.
- Evidence: `src/hooks/use-provisioning.ts:484-494`

- Flow: Tab preference restore on index route mount (Fix 2)
- Steps:
  1. User navigates to `/devices/$deviceId` (the index route)
  2. Index route component (`ConfigurationTabRoute`) mounts
  3. During render, read `getDeviceTabPreference()` synchronously from localStorage
  4. If preference is not `'configuration'`, return `null` from the component (prevents flash of wrong tab content)
  5. `useEffect` fires after paint: if preference is `'logs'`, call `navigate({ to: '/devices/$deviceId/logs', params, replace: true })`
  6. If preference is `'coredumps'`, call `navigate({ to: '/devices/$deviceId/coredumps', params, replace: true })`
  7. If preference is `'configuration'` (or absent), do nothing — already on the correct route, render normally
- States / transitions: Component mount -> synchronous read -> null render (if redirect needed) -> useEffect navigate
- Hotspots: The synchronous localStorage read during render prevents any flash. Using `replace: true` avoids polluting browser history.
- Evidence: `src/routes/devices/$deviceId/index.tsx:6-32`

- Flow: Navigate to logs tab after saving device config (Fix 3)
- Steps:
  1. User edits device configuration and clicks Save
  2. `handleSave` fires `updateDevice.mutate()`
  3. `onSuccess` callback fires
  4. Call `setDeviceTabPreference('logs')` to persist preference
  5. Call `navigate({ to: '/devices/$deviceId/logs', params: { deviceId: String(deviceId) } })`
  6. User lands on the logs tab for the device they just saved
- States / transitions: Edit form -> mutation success -> navigate to logs
- Hotspots: The `isNavigatingRef` is already set to `true` before `trackSubmit` (line 124), which bypasses the navigation blocker. This remains correct because the form is no longer dirty after a successful save.
- Evidence: `src/hooks/use-device-form.ts:127-148`

---

## 6) Derived State & Invariants

- Derived value: `shouldRedirectFromIndex`
  - Source: `getDeviceTabPreference()` — reads from localStorage, returns `'configuration' | 'logs' | 'coredumps'`
  - Writes / cleanup: Triggers a `replace` navigation if the preference is not `'configuration'`. No cache mutations.
  - Guards: Only fires on mount (empty dependency array or stable deps). `replace: true` prevents history stack growth.
  - Invariant: The redirect must not fire on subsequent re-renders or when already on a non-index tab. The `useEffect` runs only when the index route component mounts, which only happens when the URL matches `/devices/$deviceId/` exactly.
  - Evidence: `src/routes/devices/$deviceId/index.tsx` (to be changed)

- Derived value: `postSaveDestination` (edit mode)
  - Source: `deviceId` prop passed to `useDeviceForm` (always defined when `mode === 'edit'`)
  - Writes / cleanup: `setDeviceTabPreference('logs')` writes to localStorage; `navigate()` triggers route transition
  - Guards: The `deviceId === undefined` guard at line 128-133 ensures the ID is present before the mutation fires. The `isNavigatingRef` bypass is set before the mutation to prevent the blocker from interfering.
  - Invariant: `deviceId` must be a valid number when `mode === 'edit'`. The existing guard enforces this.
  - Evidence: `src/hooks/use-device-form.ts:127-141`

- Derived value: `abortControllerActive` (provisioning)
  - Source: `abortControllerRef.current` — created at start of provisioning, consumed by `cleanup` and `abort`
  - Writes / cleanup: `cleanup()` fires `.abort()` and nullifies the ref. The new `disconnectPort()` does NOT touch the abort controller.
  - Guards: On the success path, `disconnectPort()` is called instead of `cleanup()`. The abort controller ref may still be non-null after success, but it is harmless because no listeners remain attached. The `abort()` public method still calls the full `cleanup()` for user-initiated cancellation.
  - Invariant: The abort signal must never fire on the success path. After `disconnectPort()` completes, the abort controller ref should be nullified to prevent accidental use.
  - Evidence: `src/hooks/use-provisioning.ts:88,119-148`

---

## 7) State Consistency & Async Coordination

- Source of truth: Serial port lifecycle (`portRef`, `transportRef`, `abortControllerRef`) in `use-provisioning.ts`
- Coordination: The success path now uses `disconnectPort()` (transport disconnect + port close only), while the abort/error paths continue using `cleanup()` (abort + disconnect + close). Both paths nullify the same refs, so no ref can be stale after either path completes.
- Async safeguards: The 100ms grace period in `disconnectPort()` matches the existing `cleanup()` delay. The `signal.aborted` checks throughout the provisioning workflow remain intact and continue to guard against races between user abort and workflow progression.
- Instrumentation: No changes to provisioning instrumentation events. `trackComplete` still fires after `disconnectPort()` on success. `trackError` still fires after `cleanup()` on failure.
- Evidence: `src/hooks/use-provisioning.ts:119-148,484-494,497-519`

- Source of truth: Tab preference in localStorage, read by index route component
- Coordination: `DeviceDetailHeader` persists the tab on every pathname change (useEffect at line 24-29) and on tab click (onClick handler at line 169). The index route reads the preference on mount. These two writes are non-conflicting because the index route only reads, never writes.
- Async safeguards: The `useEffect` in the index route fires after mount; `replace: true` navigation prevents double-entry in history. No query cache involvement.
- Instrumentation: No new instrumentation needed for tab persistence. The existing tab navigation tests cover the active-tab `aria-current` attribute.
- Evidence: `src/components/devices/device-detail-header.tsx:23-29,169`; `src/routes/devices/$deviceId/index.tsx`

- Source of truth: `useDeviceForm` mutation state, navigation target
- Coordination: `onSuccess` now calls `setDeviceTabPreference('logs')` before `navigate()`. The header's `useEffect` will then observe the `/logs` pathname and confirm the preference (no-op since it's already 'logs').
- Async safeguards: `isNavigatingRef.current = true` set before `trackSubmit` prevents the navigation blocker from interfering. The mutation's `onError` resets this ref.
- Instrumentation: The existing `DeviceEditor_edit` form instrumentation (`trackSubmit`, `trackSuccess`, `trackError`) is unchanged. Tests can still wait on the `form` event with `phase === 'success'` to know the save completed.
- Evidence: `src/hooks/use-device-form.ts:124-148`

---

## 8) Errors & Edge Cases

- Failure: `transport.disconnect()` throws during success cleanup
- Surface: `use-provisioning.ts` — `disconnectPort()` helper
- Handling: Wrap in try/catch and ignore the error (same pattern as existing `cleanup()`). The provisioning has already succeeded; a disconnect failure is cosmetic.
- Guardrails: The port ref is still nullified even if disconnect throws, preventing resource leaks on subsequent provisioning attempts.
- Evidence: `src/hooks/use-provisioning.ts:130-136` (existing pattern)

- Failure: `port.close()` throws during success cleanup
- Surface: `use-provisioning.ts` — `disconnectPort()` helper
- Handling: Wrap in try/catch and ignore. The user may need to manually release the port via browser settings, but this is no worse than the current broken behavior.
- Guardrails: Port ref is nullified regardless. The success state is still emitted.
- Evidence: `src/hooks/use-provisioning.ts:139-145` (existing pattern)

- Failure: `localStorage` is unavailable when reading tab preference
- Surface: `device-tab-preference.ts` — `getDeviceTabPreference()`
- Handling: Already handled — the function catches exceptions and returns `'configuration'` as the default.
- Guardrails: No change needed.
- Evidence: `src/lib/utils/device-tab-preference.ts:8-16`

- Failure: `deviceId` is undefined in edit-mode `onSuccess`
- Surface: `use-device-form.ts` — edit-mode save handler
- Handling: Cannot happen — the guard at line 128-133 returns early and emits `trackError` if `deviceId` is undefined. The mutation only fires if `deviceId` is defined.
- Guardrails: Existing guard is sufficient.
- Evidence: `src/hooks/use-device-form.ts:128-133`

- Failure: Flash of configuration tab content before redirect
- Surface: `$deviceId/index.tsx` — component-level redirect
- Handling: The component reads `getDeviceTabPreference()` synchronously during render (localStorage reads are synchronous). If the preference is not `'configuration'`, the component returns `null` immediately — before the `useEffect` fires. The `useEffect` then navigates to the correct tab route with `replace: true`. This eliminates any visible flash of the wrong tab content, even when the device is already cached.
- Guardrails: The synchronous read during render is safe because localStorage is a synchronous API. The `null` return prevents React from painting any configuration tab content.
- Evidence: `src/routes/devices/$deviceId/index.tsx:27-29`

---

## 9) Observability / Instrumentation

No new instrumentation signals are required. The existing instrumentation covers all affected flows:

- Signal: `TestEventKind.PROVISIONING` with `phase: 'complete'`
- Type: Instrumentation event
- Trigger: After successful provisioning cleanup (now via `disconnectPort()` instead of `cleanup()`)
- Labels / fields: `{ deviceId }`
- Consumer: Playwright provisioning specs (not directly affected since Web Serial requires hardware)
- Evidence: `src/lib/test/provisioning-instrumentation.ts:53-55`; `src/hooks/use-provisioning.ts:494`

- Signal: `TestEventKind.FORM` with `formId: 'DeviceEditor_edit'`, `phase: 'success'`
- Type: Instrumentation event
- Trigger: After `updateDevice.mutate` succeeds — unchanged
- Labels / fields: `{ deviceId }`
- Consumer: Playwright CRUD specs can wait on this event to know save completed before asserting URL
- Evidence: `src/hooks/use-device-form.ts:139`; `src/lib/test/form-instrumentation.ts:49-53`

---

## 10) Lifecycle & Background Work

- Hook / effect: Tab preference redirect in `ConfigurationTabRoute`
- Trigger cadence: On mount (once per navigation to the index route)
- Responsibilities: Reads localStorage, conditionally navigates to the preferred tab with `replace: true`
- Cleanup: None needed — single-fire effect with no subscriptions or timers
- Evidence: `src/routes/devices/$deviceId/index.tsx` (new effect to be added)

- Hook / effect: Tab persistence in `DeviceDetailHeader`
- Trigger cadence: On `location.pathname` change
- Responsibilities: Derives current tab from pathname, writes to localStorage via `setDeviceTabPreference()`
- Cleanup: None — `useEffect` with no cleanup return. Runs synchronously on pathname change.
- Evidence: `src/components/devices/device-detail-header.tsx:23-29` (unchanged)

---

## 11) Security & Permissions

Not applicable. These fixes do not change authentication, authorization, or data exposure. The provisioning API call continues to use `credentials: 'include'` and is unchanged.

---

## 12) UX / UI Impact

- Entry point: Device configuration editor — Save button (edit mode)
- Change: After saving, the user is navigated to `/devices/$deviceId/logs` instead of `/devices`
- User interaction: The user saves their device configuration changes and immediately sees the device's live log stream, providing instant feedback that the device is operating with the new configuration
- Dependencies: The logs tab route and `DeviceLogsTab` component are unchanged
- Evidence: `src/hooks/use-device-form.ts:138-141`

- Entry point: Device detail — index route (Configuration tab)
- Change: When navigating to a device, the previously selected tab is restored instead of always showing Configuration
- User interaction: If a user was reviewing logs on device A, opening device B will also show the logs tab, maintaining workflow continuity
- Dependencies: `device-tab-preference.ts` localStorage helpers (unchanged)
- Evidence: `src/routes/devices/$deviceId/index.tsx:7-15`

- Entry point: Provisioning modal — success state
- Change: No visible UX change. The serial port now releases properly after successful flash, which was the original intended behavior
- User interaction: After provisioning completes, the serial port is no longer locked. The user does not need to manually disconnect via browser settings
- Dependencies: Web Serial API, ESPLoader transport library
- Evidence: `src/hooks/use-provisioning.ts:484-494`

---

## 13) Deterministic Test Plan

- Surface: Edit device save navigation
- Scenarios:
  - Given a device exists, When the user edits the JSON config and saves, Then the URL changes to `/devices/<id>/logs` (not `/devices`)
  - Given a device exists, When the user edits the JSON config and saves, Then the Logs tab is active (`aria-current="page"`)
  - Given a device exists, When the user edits and saves, Then the tab preference in localStorage is 'logs' (verified indirectly: opening another device should show Logs tab)
- Instrumentation / hooks: Wait for `form` event with `formId === 'DeviceEditor_edit'` and `phase === 'success'` before asserting URL. Use `devices.detail.tab.logs` testid for tab assertion.
- Concrete test structure for the updated edit-save test:
  ```
  await devicesPage.save();
  await waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success');
  await expect(page).toHaveURL(`/devices/${device.id}/logs`);
  await expect(devicesPage.tabLogs).toHaveAttribute('aria-current', 'page');
  ```
- Gaps: None.
- Evidence: `tests/e2e/devices/devices-crud.spec.ts:151-181` (existing test to update)

- Surface: Tab preference persistence across device navigation
- Scenarios:
  - Given device A and device B exist, When the user opens device A and clicks the Logs tab, Then navigates back and opens device B, Then the Logs tab should be active on device B
  - Given device A and device B exist, When the user opens device A and clicks the Core Dumps tab, Then navigates back and opens device B, Then the Core Dumps tab should be active on device B
  - Given device A exists, When the user navigates directly to `/devices/<id>` with no stored preference, Then the Configuration tab is shown (default behavior)
- Instrumentation / hooks: Use `devices.detail.tab.logs` and `devices.detail.tab.coredumps` testids with `aria-current` attribute assertion.
- localStorage isolation: Each tab persistence test must clear the `iot-support-device-tab` localStorage key before navigating, using `page.evaluate(() => localStorage.removeItem('iot-support-device-tab'))`. This prevents bleed from other tests that may have set the preference. Existing tab tests that expect "configuration tab is active by default" must also clear this key in a `beforeEach` or at the start of the test.
- Gaps: None.
- Evidence: `tests/e2e/devices/devices-tabs.spec.ts` (new specs to add)

- Surface: Provisioning COM port release
- Scenarios:
  - The provisioning success path calls `disconnectPort()` which does not fire the abort controller
- Instrumentation / hooks: Cannot be tested in Playwright (Web Serial API requires hardware interaction and user gesture for port selection). The fix is verified by code review and manual testing.
- Gaps: No Playwright coverage for COM port release — justified because Web Serial `requestPort()` cannot be automated. Existing provisioning modal UI tests remain valid and unaffected.
- Evidence: `tests/e2e/devices/devices-provisioning.spec.ts` (existing tests unchanged)

---

## 14) Implementation Slices

- Slice: Fix 1 — Provisioning cleanup split
- Goal: COM port releases correctly after successful flash
- Touches: `src/hooks/use-provisioning.ts`
- Dependencies: None. Self-contained change.

- Slice: Fix 2 — Tab preference restore
- Goal: Selected device tab persists across device navigation
- Touches: `src/routes/devices/$deviceId/index.tsx`
- Dependencies: None. The `device-tab-preference.ts` utility and `device-detail-header.tsx` persistence logic are unchanged.

- Slice: Fix 3 — Post-save navigation to logs
- Goal: Edit-mode save navigates to logs tab with preference update
- Touches: `src/hooks/use-device-form.ts`
- Dependencies: None. The logs route already exists.

- Slice: Tests — Update and add Playwright specs
- Goal: Verify all three fixes with deterministic Playwright coverage
- Touches: `tests/e2e/devices/devices-crud.spec.ts`, `tests/e2e/devices/devices-tabs.spec.ts`
- Dependencies: Fixes 2 and 3 must be implemented first so the navigation assertions match.

---

## 15) Risks & Open Questions

- Risk: `transport.disconnect()` may still fail if the abort controller was used earlier in the workflow (e.g., a signal check fired between verification and cleanup)
- Impact: COM port stays locked — same as current broken behavior
- Mitigation: Nullify the abort controller ref after calling `disconnectPort()` on the success path so no stale signal can propagate. The abort controller is not needed after success.

- Risk: Brief flash of Configuration tab content before redirect fires on the index route
- Impact: Minor visual flicker when navigating to a device with a non-default tab preference
- Mitigation: The `ConfigurationTabRoute` component returns `null` when device is not yet loaded, which covers the common case. For the cached-device case, the `useEffect` fires on the first commit and the redirect is near-instantaneous.

- Risk: Existing Playwright test (`devices-crud.spec.ts` "edits an existing device") will fail if not updated simultaneously with Fix 3
- Impact: CI failure
- Mitigation: Ship all three fixes and test updates in a single commit/PR.

All questions have been resolved autonomously per the user's instruction.

---

Confidence: High — all three fixes are small, well-scoped changes to existing code paths with clear evidence from the codebase. The provisioning fix is a straightforward extract-and-split of the cleanup function. The tab persistence fix replaces a known-unreliable `beforeLoad` redirect with a standard React pattern. The post-save navigation fix is a one-line URL change plus a `setDeviceTabPreference` call. Playwright coverage is achievable without new infrastructure.
