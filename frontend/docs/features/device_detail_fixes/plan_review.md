# Plan Review: Device Detail UX Fixes

## 1) Summary & Decision

**Readiness**

The plan is well-researched and demonstrates strong familiarity with the codebase. The three fixes are clearly scoped, the file map is accurate with verifiable line references, and the provisioning cleanup split is technically sound. However, the plan has a significant gap in how it handles test isolation for the tab preference feature: localStorage persists across tests within a Playwright worker, and neither the plan nor the existing fixture infrastructure clears it between specs. This means the tab preference redirect introduced in Fix 2 will cause existing tests to fail non-deterministically depending on execution order. Additionally, the plan's test scenarios for Fix 3 (edit save navigation) do not use the instrumentation-based wait pattern mandated by the Playwright developer guide, relying instead on the implicit `toHaveURL` assertion timing.

**Decision**

`GO-WITH-CONDITIONS` -- The plan is sound in intent and scope but requires addressing the localStorage isolation gap and strengthening the test wait strategy before implementation proceeds.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/commands/plan_feature.md` -- Pass -- The plan covers all 16 required headings (0 through 15 plus Confidence) with structured evidence. Section 11 (Security) is explicitly scoped out with justification (`plan.md:295-296`).
- `docs/contribute/testing/playwright_developer_guide.md` -- Partial Fail -- The guide mandates "Deterministic waits -- Assertions rely on UI visibility, network promises, or test-event signals -- never fixed sleeps" (developer guide line 19) and "Never start writing the spec until the UI emits the events you need" (line 130). The test plan at `plan.md:328` says "Wait for `form` event with `formId === 'DeviceEditor_edit'` and `phase === 'success'` before asserting URL", which is correct in principle. However, the existing `devices-crud.spec.ts` test being updated (line 176) does not use `waitTestEvent` today -- it asserts `await expect(page).toHaveURL('/devices')` directly. The plan does not explicitly call out adding a `waitTestEvent` call to the updated test, risking a race between mutation success and navigation.
- `docs/contribute/testing/factories_and_fixtures.md` -- Pass -- The plan uses existing factory infrastructure (`devices.create`) and does not introduce route interception. `plan.md:324-327` scenarios seed data through factories.
- `docs/contribute/architecture/application_overview.md` -- Pass -- The plan correctly uses existing hooks (`useDevice`, `useDeviceForm`, `useProvisioning`) and follows the domain-driven folder layout. No ad hoc fetch calls are introduced.
- `docs/product_brief.md` -- Pass -- The product brief describes device configuration editing and navigation (`product_brief.md:22-25`). The plan's changes (post-save navigation, tab persistence) align with the product's device management workflow.

**Fit with codebase**

- `useDeviceForm` hook -- `plan.md:91-93` -- The plan correctly identifies the edit-mode `onSuccess` handler at `use-device-form.ts:141` as navigating to `/devices`. The proposed change to navigate to `/devices/$deviceId/logs` aligns with the hook's existing navigation pattern (it already uses `navigate()` with typed routes). Confirmed fit.
- `ConfigurationTabRoute` / `$deviceId/index.tsx` -- `plan.md:87-89` -- The plan proposes replacing `beforeLoad` with a component-level `useEffect`. This is consistent with how the codebase handles side effects elsewhere (e.g., `device-detail-header.tsx:24-29` uses `useEffect` for tab persistence). However, the plan acknowledges a "flash of configuration tab content" risk (`plan.md:249-253`) -- this is an acceptable trade-off given the `beforeLoad` unreliability.
- `cleanup` / `disconnectPort` split in `use-provisioning.ts` -- `plan.md:83-85` -- The plan accurately describes the unconditional `abort()` call at line 122 of `use-provisioning.ts`. The proposed `disconnectPort()` helper mirrors the existing cleanup pattern (try/catch around disconnect and close) without the abort signal. Confirmed fit.
- `DeviceDetailHeader` tab persistence -- `plan.md:209-213` -- The plan correctly identifies that the header already persists tab preference on pathname change. The index route component only reads, never writes. No conflict between read and write paths. Confirmed fit.
- `DevicesPage` page object -- `plan.md:96-101` -- The plan references existing page object methods (`gotoEdit`, `clickTab`, tab locators). These are verified present in `tests/e2e/devices/DevicesPage.ts:15-84`. Confirmed fit.

---

## 3) Open Questions & Ambiguities

- Question: How will localStorage be isolated between Playwright tests to prevent the tab preference set by one test from affecting another?
- Why it matters: The `page` fixture in `tests/support/fixtures.ts:135-213` does not clear localStorage between tests. Tests within the same worker share a browser context. If the "tab preference persistence" test (Fix 2) sets preference to `'logs'`, the subsequent "configuration tab is active by default" test (`devices-tabs.spec.ts:5-14`) will fail because the index route will now redirect to the logs tab. The "deep-links work for all three tabs" test (`devices-tabs.spec.ts:62-78`) will also be affected when it navigates to `gotoEdit(device.id)` and expects the Configuration tab to be active.
- Needed answer: The plan must specify whether (a) each affected test should clear localStorage before running, (b) the `page` fixture should be updated to clear localStorage globally, or (c) individual tests should set the expected tab preference as a precondition. Option (c) is the most targeted and aligns with the "dirty database policy" of self-contained test data.

- Question: Should the `abortControllerRef` be nullified after `disconnectPort()` completes on the success path?
- Why it matters: The plan states at `plan.md:196` that "the abort controller ref may still be non-null after success" and at `plan.md:378` that the mitigation is to "nullify the abort controller ref after calling `disconnectPort()`." However, this nullification is not shown in the flow steps at `plan.md:137-145` (steps 1-8). The implementation could miss this if the steps are followed literally.
- Needed answer: Confirmed by cross-referencing `plan.md:196` with `plan.md:378` -- the intent is clear, but step 6 at `plan.md:143` should explicitly include "Nullify refs (`transportRef`, `portRef`, `abortControllerRef`)" to avoid ambiguity. This is a Minor issue since the plan text provides the answer elsewhere.

---

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Edit device post-save navigation to logs tab
- Scenarios:
  - Given a device exists, When the user edits the JSON config and saves, Then the URL changes to `/devices/<id>/logs` (`tests/e2e/devices/devices-crud.spec.ts`, to be updated)
  - Given a device exists, When the user edits and saves, Then the Logs tab is active with `aria-current="page"` (`tests/e2e/devices/devices-crud.spec.ts`, to be updated)
- Instrumentation: `form` event with `formId === 'DeviceEditor_edit'` and `phase === 'success'`; `devices.detail.tab.logs` testid for tab assertion.
- Backend hooks: `devices.create()` factory seeds the device.
- Gaps: The plan correctly identifies the instrumentation event at `plan.md:328` but the existing test at `devices-crud.spec.ts:173-176` does not use `waitTestEvent`. The updated test should add an explicit `waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success')` before asserting the URL. Without this, the URL assertion could race against the navigation triggered by `onSuccess`.
- Evidence: `plan.md:323-330`, `devices-crud.spec.ts:151-181`

- Behavior: Tab preference persistence across device navigation
- Scenarios:
  - Given device A and device B exist, When the user opens device A and clicks the Logs tab, Then navigates back and opens device B, Then the Logs tab should be active on device B (`tests/e2e/devices/devices-tabs.spec.ts`, new spec)
  - Given device A and device B exist, When the user opens device A and clicks the Core Dumps tab, Then navigates back and opens device B, Then the Core Dumps tab should be active on device B (`tests/e2e/devices/devices-tabs.spec.ts`, new spec)
  - Given a device exists, When the user navigates to `/devices/<id>` with no stored preference, Then Configuration tab is shown (`tests/e2e/devices/devices-tabs.spec.ts`, new spec)
- Instrumentation: `devices.detail.tab.logs`, `devices.detail.tab.coredumps` testids with `aria-current` attribute.
- Backend hooks: `devices.create()` factory.
- Gaps: **Major** -- The third scenario ("no stored preference") is under-specified. Since localStorage is not cleared between tests, the spec must explicitly clear the `iot-support-device-tab` key before navigating. Without this, the test result depends on execution order. The plan does not address this.
- Evidence: `plan.md:332-339`, `src/lib/utils/device-tab-preference.ts:1` (storage key)

- Behavior: Provisioning COM port release (no abort on success)
- Scenarios:
  - The provisioning success path calls `disconnectPort()` which does not fire the abort controller
- Instrumentation: None automatable (Web Serial API requires hardware).
- Backend hooks: None.
- Gaps: None -- justified exclusion from Playwright coverage at `plan.md:341-346`. Web Serial `requestPort()` cannot be automated.
- Evidence: `plan.md:341-346`

---

## 5) Adversarial Sweep

**Major -- localStorage bleed between Playwright specs breaks existing tab tests**

**Evidence:** `plan.md:149-159` (Fix 2 flow) + `tests/support/fixtures.ts:135-213` (page fixture) + `tests/e2e/devices/devices-tabs.spec.ts:5-14,62-78` (existing tests)

**Why it matters:** The tab preference redirect fires on every mount of the index route component. The page fixture does not clear localStorage between specs. Test execution order within a worker is deterministic but fragile: if the new "tab persistence across devices" spec runs before "configuration tab is active by default" (`devices-tabs.spec.ts:5`), the stored preference from the persistence test will cause the configuration-tab test to fail because the index route will redirect to the logs tab. Similarly, the "deep-links work for all three tabs" test (`devices-tabs.spec.ts:62`) navigates to `gotoEdit(device.id)` which hits the index route and would redirect. This is a CI-breaking regression that the plan does not anticipate.

**Fix suggestion:** Add a `localStorage.removeItem('iot-support-device-tab')` call (via `page.evaluate`) at the beginning of each affected test, or add a `beforeEach` hook in the tab navigation test describe block. Alternatively, update the `page` fixture to clear localStorage between tests with `await page.evaluate(() => localStorage.clear())` before yielding the page. The latter approach is more robust and aligns with the project's convention of not relying on cross-test state.

**Confidence:** High

---

**Major -- Missing explicit `waitTestEvent` in updated edit-save test creates a race condition**

**Evidence:** `plan.md:328` ("Wait for `form` event with `formId === 'DeviceEditor_edit'` and `phase === 'success'` before asserting URL") + `devices-crud.spec.ts:173-176` (current test) + `docs/contribute/testing/playwright_developer_guide.md:130` ("Never start writing the spec until the UI emits the events you need")

**Why it matters:** The current test at `devices-crud.spec.ts:173` calls `await devicesPage.save()` (which clicks the save button) and then immediately asserts `await expect(page).toHaveURL('/devices')`. The plan changes the expected URL to `/devices/<id>/logs` but does not explicitly require adding a `waitTestEvent` call before the URL assertion. Playwright's `toHaveURL` has auto-retry, but the navigation is triggered inside a mutation `onSuccess` callback, which is asynchronous. If the mutation response is slow, the URL assertion could time out or, worse, succeed against the wrong intermediate URL. The plan's instrumentation section (line 328) describes the correct approach but does not mandate it in the updated test -- the developer could read Section 13 (Test Plan) and skip the instrumentation step.

**Fix suggestion:** Update the test plan at Section 13 to show the concrete test structure:
```
await devicesPage.save();
await waitTestEvent(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success');
await expect(page).toHaveURL(`/devices/${device.id}/logs`);
await expect(devicesPage.tabLogs).toHaveAttribute('aria-current', 'page');
```

**Confidence:** High

---

**Minor -- `disconnectPort()` flow steps omit nullifying `abortControllerRef`**

**Evidence:** `plan.md:137-145` (Fix 1 flow, steps 1-8) vs. `plan.md:196` ("the abort controller ref may still be non-null") vs. `plan.md:378` ("Nullify the abort controller ref after calling `disconnectPort()`")

**Why it matters:** Step 6 at `plan.md:143` says "Nullify refs (`transportRef`, `portRef`)" but omits `abortControllerRef`. The Risks section at `plan.md:378` identifies this as a mitigation action. The Derived State section at `plan.md:196` acknowledges the ref stays non-null. These three sections are internally inconsistent. An implementer following the steps literally would leave the abort controller ref dangling, which is the exact risk the plan identifies at `plan.md:376-378`.

**Fix suggestion:** Update step 6 at `plan.md:143` to: "Nullify refs (`transportRef`, `portRef`, `abortControllerRef`)".

**Confidence:** High

---

**Minor -- `useEffect` flash on index route is acknowledged but mitigation is incomplete**

**Evidence:** `plan.md:249-253` (Flash of configuration tab content) + `src/routes/devices/$deviceId/index.tsx:27-29` (null check)

**Why it matters:** The plan states that "the `useEffect` fires synchronously on the first commit" (`plan.md:251`). This is technically incorrect -- `useEffect` fires after the browser paints (it is not synchronous with commit). The actual behavior is: React renders the component, the browser paints the result, and then `useEffect` runs. For a cached device, the `ConfigurationTabRoute` component would render `<DeviceConfigurationTab device={device} />`, the browser would paint it, and then the `useEffect` redirect would fire. This could result in a visible flash. The plan's claim that "the user sees nothing" (`plan.md:251`) depends on the device not being in cache, which is not the common case when navigating from the device list (where TanStack Query pre-populates the cache).

**Fix suggestion:** Consider rendering `null` from the component body when the tab preference is not `'configuration'` (read synchronously during render, before the effect fires), then let the `useEffect` handle the navigation. This eliminates the flash entirely. The synchronous read of `getDeviceTabPreference()` during render is safe since localStorage is synchronous.

**Confidence:** Medium

---

## 6) Derived-Value & State Invariants (table)

- Derived value: `shouldRedirectFromIndex`
  - Source dataset: `getDeviceTabPreference()` reading from localStorage (unfiltered -- returns one of three valid string literals)
  - Write / cleanup triggered: `replace` navigation to a different tab route; no cache mutations
  - Guards: Only fires on mount via `useEffect` (empty or stable deps). `replace: true` prevents history stack growth.
  - Invariant: The redirect must not fire on subsequent re-renders or when already on a non-index tab. Since the `useEffect` runs only when the index route component mounts (which only happens when the URL matches `/devices/$deviceId/` exactly), this invariant holds.
  - Evidence: `plan.md:178-183`

- Derived value: `postSaveDestination`
  - Source dataset: `deviceId` prop (always defined when `mode === 'edit'`, guarded at `use-device-form.ts:128-133`)
  - Write / cleanup triggered: `setDeviceTabPreference('logs')` writes to localStorage; `navigate()` triggers route transition
  - Guards: `deviceId === undefined` guard returns early with `trackError`. `isNavigatingRef` bypass prevents blocker interference.
  - Invariant: `deviceId` must be a valid number when `mode === 'edit'`. The existing guard enforces this. The localStorage write happens before navigation, ensuring the header's `useEffect` observes the correct preference when the logs route mounts.
  - Evidence: `plan.md:185-190`, `use-device-form.ts:128-141`

- Derived value: `abortControllerActive`
  - Source dataset: `abortControllerRef.current` -- created at provisioning start (`use-provisioning.ts:250`), consumed by `cleanup` and `abort`
  - Write / cleanup triggered: `cleanup()` fires `.abort()` and nullifies the ref. The new `disconnectPort()` does NOT touch the abort controller.
  - Guards: On the success path, `disconnectPort()` is called instead of `cleanup()`. The abort controller ref remains non-null after `disconnectPort()` unless explicitly nullified (see adversarial finding above).
  - Invariant: The abort signal must never fire on the success path. After `disconnectPort()` completes, the abort controller ref should be nullified to prevent accidental use. The plan identifies this at `plan.md:196` but the flow steps at `plan.md:143` do not enforce it.
  - Evidence: `plan.md:192-197`, `use-provisioning.ts:88,119-148,250-251`

---

## 7) Risks & Mitigations (top 3)

- Risk: localStorage bleed between Playwright tests causes non-deterministic failures in existing tab navigation specs when the tab preference redirect is enabled.
- Mitigation: Either clear localStorage in a `beforeEach` hook for tab-related tests or update the `page` fixture to clear localStorage between specs globally. The plan must specify the isolation strategy before implementation.
- Evidence: `plan.md:332-339`, `tests/support/fixtures.ts:135-213`, `tests/e2e/devices/devices-tabs.spec.ts:5-14`

- Risk: The race between mutation `onSuccess` navigation and Playwright URL assertion could cause flaky tests if the `waitTestEvent` call is omitted from the updated edit-save test.
- Mitigation: Update the test plan to mandate the `waitTestEvent` call before URL assertion, matching the pattern documented in `docs/contribute/testing/playwright_developer_guide.md:133-147`.
- Evidence: `plan.md:328`, `devices-crud.spec.ts:173-176`

- Risk: Visible flash of Configuration tab content before the `useEffect` redirect fires when navigating to a device with a non-default tab preference and the device is already cached.
- Mitigation: Return `null` from the component body when the synchronously-read tab preference is not `'configuration'`, before the `useEffect` fires the navigation. This eliminates the flash without relying on effect timing. Accept if the flash is imperceptible in practice.
- Evidence: `plan.md:249-253`, `src/routes/devices/$deviceId/index.tsx:20-32`

---

## 8) Confidence

Confidence: Medium -- The plan is technically sound for the three fixes individually, but the omission of a localStorage isolation strategy for Playwright tests is a real CI-breaking risk that must be resolved before implementation. With that condition addressed, confidence rises to High.
