# Playwright Developer Guide

The Playwright suite drives the IoT Support frontend against the real backend in testing mode. This guide explains how the suite is structured, how to seed data safely, and how to extend coverage without breaking stability. [Testing Overview](./index.md) has the principles and the spec taxonomy; [Factories & Fixtures](./factories_and_fixtures.md) is the reference for every factory method, fixture and testing endpoint.

## Before You Start

1. Complete the [Getting Started](../getting_started.md) setup and ensure `kc project test frontend` passes.
2. Understand the [Environment Reference](../environment.md) to configure URLs and test mode.
3. Review the [Test Instrumentation](../architecture/test_instrumentation.md) taxonomy—tests frequently assert on emitted test-event payloads.
4. Confirm the UI flow you are touching emits the required instrumentation; add or adjust it *before* writing a spec so tests can rely on deterministic events.

## Core Principles

1. **API-first data setup** – Create prerequisite device models, devices, firmware and core dumps through the `deviceModels` and `devices` factories; UI interactions are only for the scenario under test.
2. **Real backend always** – Specs hit the live backend endpoints. Do not intercept, stub, or shortcut HTTP calls; the `testing/no-route-mocks` ESLint rule guards this policy. Missing behavior belongs in the backend as a `/api/testing/*` endpoint, not in Playwright helpers.
3. **One stand-in, for the hardware** – The USB serial port and the ESP32 behind it are faked for Flash device and Provision device, because no test can reach them. See [The Fake USB Device](#the-fake-usb-device).
4. **Dirty database policy** – Tests never reset or clean up their records. Each run builds a fresh seed database and each worker's backend serves its own clone of it, so use randomized identifiers, never rely on data seeded by another test, and ignore residual records.
5. **Feature-owned page objects** – Each feature folder under `tests/e2e/` holds the page object for its UI (`DevicesPage`, `RotationPage`, `AuthPage`).
6. **Deterministic waits** – Assertions rely on UI visibility, network promises, or test-event signals—never fixed sleeps.
7. **Console is the contract** – An unexpected `console.error` or page error fails the test; see [Console Error Policy](#console-error-policy).

## Suite Architecture

### API Client and Factories

`tests/api/client.ts` wraps `openapi-fetch`, typed from the generated API types. The factories under `tests/api/factories/` build on it: `DeviceModelsFactory` (`device-models.ts`) and `DevicesFactory` (`devices.ts`), handed to specs as the `deviceModels` and `devices` fixtures. Each fixture signs in an `editor` session first and talks to the worker's frontend URL, whose Vite proxy forwards `/api` to the worker's backend, so the factory shares the browser's cookies.

```typescript
const model = await deviceModels.create();
await deviceModels.seedFirmware(model.id, { version: '2.3.4' });
const device = await devices.create({ deviceModelId: model.id });
```

[Factories & Fixtures](./factories_and_fixtures.md) lists every method.

### Fixtures (`tests/support/fixtures.ts`)

Specs import `test` and `expect` from `tests/support/fixtures.ts`, which adds the app's `devices` and `deviceModels` factories to the template's `tests/support/fixtures-infrastructure.ts`:

- `frontendUrl` / `backendUrl` – The worker's Vite server (also Playwright's `baseURL`) and Flask backend.
- `backendLogs` / `frontendLogs` – Automatic; attach each worker server's output to the test as `backend.log` and `frontend.log`.
- `page` override – Registers the test-event bridge, fails the test on an unexpected `console.error` or page error, and emulates reduced motion.
- `testEvents` – The `TestEventCapture` over the bridge's buffer, for sequence assertions and `dumpEvents()` while debugging.
- `toastHelper`, `fileUploadHelper` – Toast assertions and file inputs.
- `deploymentSse` – Opens and reads the app's SSE connection; see [SSE Streams](#sse-streams).
- `auth` – `createSession(...)`, `clearSession()` and `forceError(status)` over `/api/testing/auth/*`.
- `appShell` – The `AppShellPage` page object.
- `sseTimeout` – 35s, for SSE-heavy waits.

Import fixtures from a spec under `tests/e2e/<feature>/` via:

```typescript
import { test, expect } from '../../support/fixtures';
```

### Service Lifecycle

Global setup (`tests/support/global-setup.ts`) builds the run's seed database on PostgreSQL with the backend's `load-test-data`. Each worker then clones the seed and starts its own backend and frontend on free ports (`tests/support/process/servers.ts`); the frontend runs in test mode and proxies `/api`, the SSE stream included, to the worker's backend. [CI & Execution → Per-Worker Managed Services](./ci_and_execution.md#per-worker-managed-services) has the startup sequence, health checks and log streaming.

### Helpers (`tests/support/helpers.ts`)

Utility functions that complement fixtures:

- `makeUnique(prefix?, length?)`, `makeUniqueToken(length?)` – Unique identifiers (the eslint-enforced replacement for `Date.now()`).
- `waitTestEvent(page, kind, filter?, timeout?)` – Await a test-event payload from the Playwright-managed buffer.
- `waitForUiState(page, scope, phase, timeout?)` – Await a `ui_state` event, such as the flash modal's `devices.flash-modal.flash` scope.
- `waitForListLoading(page, scope, phase, timeout?)` – Await a `list_loading` event, such as `devices.list`, `device-models.list`, `coredumps.list` or `rotation.dashboard`.
- `waitForElement(page, selector, timeout?)`
- `waitForFormValidationError(page, formId, field?)`
- `expectConflictError(page, correlationId?)` – Await a 409 `query_error` event.
- `expectConsoleError(page, pattern)` – Allow a known console error for the rest of the test.

`tests/support/helpers/test-events.ts` adds `waitForSseEvent(page, { streamId, phase?, event?, matcher?, timeoutMs? })`, `extractSseData(event)` and `emitTestEvent(page, payload)`.

### The Fake USB Device

`installFakeEspDevice(page, config?)` replaces the browser's Web Serial port with a fake one before the page loads, and Vite aliases `esptool-js` to a mock chip in test mode; `readFakeEspDevice(page)` reads back what was written and signalled. Every request still goes to the real backend. [Factories & Fixtures → The Fake USB Device](./factories_and_fixtures.md#the-fake-usb-device) has the configuration and [Firmware flashing → How it is tested](../../../../docs/firmware-flashing.md#how-it-is-tested) what each spec proves.

## Authoring Patterns

### Create Data First

```typescript
test('edits an existing device', async ({ page, devices }) => {
  const device = await devices.create({ deviceName: 'Original Name' });

  const devicesPage = new DevicesPage(page);
  await devicesPage.gotoEdit(device.id);
  await devicesPage.waitForEditorLoaded();

  await expect(devicesPage.headerDeviceKey).toContainText(device.key);
});
```

- Never drive prerequisite flows through the UI (no create-via-form followed by edit assertions).
- Use factory options to craft edge cases: `deviceModels.seedFirmware(model.id, { flashImages: false })` for a version without flash images, `{ chip: 'esp32c3' }` for a chip mismatch, `devices.createCoredump({ deviceId, parseStatus: 'PARSED' })` for a core dump.
- Seed data uniquely for each spec. If multiple tests need similar state, each must create its own records.

### Sign In

The `devices` and `deviceModels` fixtures sign in an `editor` session before the test runs. A spec that uses neither signs in itself:

```typescript
test('save button is disabled when no model is selected', async ({ page, auth }) => {
  await auth.createSession({ name: 'Test User', roles: ['editor'] });

  const devicesPage = new DevicesPage(page);
  await devicesPage.gotoNew();
  await devicesPage.waitForEditorLoaded();
  await expect(devicesPage.saveButton).toBeDisabled();
});
```

### Randomize Identifiers

The factories default to random names and codes; use their helpers when a spec needs to know the value up front.

```typescript
const entityId = devices.randomDeviceEntityId('sse_ready_test');
const device = await devices.create({ deviceEntityId: entityId });
```

Model codes carry the worker's `playwright_w<N>` prefix, which the `devices` fixture's Keycloak cleanup matches, so create models through the factory. The eslint rule forbids `Date.now()`; rely on `makeUnique` (or the factory helpers) for uniqueness. When a real timestamp is required, add a targeted disable comment with justification in the diff.

### Console Error Policy

The `page` fixture fails the test on any `console.error` or uncaught page error it does not recognize. It already lets through the errors that HTTP failures log (400, 401, 403, 404, 409 and 500 among them), `/api/auth/` failures, and `Form submission error` and `Toast exception` messages. If a test intentionally triggers another console error, register its pattern before the action that logs it:

```typescript
await expectConsoleError(page, /<pattern of the expected error>/);
```

The pattern stays allowed for the rest of the test.

### Test-Event Assertions

Never start writing the spec until the UI emits the events you need—instrumentation drives every deterministic wait. Prefer UI assertions first, but when behavior is exposed via instrumentation (forms, lists, the flash and provisioning workflows, SSE), use helpers for precision.

```typescript
await waitForListLoading(page, 'devices.list', 'ready');

const flashed = await waitForUiState(page, 'devices.flash-modal.flash', 'ready');
expect(flashed.metadata).toMatchObject({ outcome: 'success', firmwareVersion: '2.3.4' });

const ended = await waitTestEvent<ProvisioningTestEvent>(
  page,
  'provisioning',
  event => event.deviceId === device.id && (event.phase === 'complete' || event.phase === 'error')
);
```

For a form, wait on its `formId` (`DeviceEditor_new`, `DeviceEditor_edit`, `DeviceEditor_duplicate`, `DeviceModelEditor_new`, `DeviceModelEditor_edit`) while triggering the action:

```typescript
const [, success] = await Promise.all([
  waitTestEvent<FormTestEvent>(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'submit'),
  waitTestEvent<FormTestEvent>(page, 'form', evt => evt.formId === 'DeviceEditor_edit' && evt.phase === 'success'),
  devicesPage.save(),
]);
```

The event types come from `@/lib/test/test-events` and, for `provisioning`, `@/types/provisioning-events`. React's StrictMode mounts components twice on the dev server, so a scope can report once for the discarded mount: `devices-flashing.spec.ts` filters out the images scope's `ready` event whose `metadata.status` is `'aborted'`.

Avoid over-asserting—validate the critical transitions (submit → success, toast levels, workflow outcome) required by the scenario and lean on UI checks for the rest.

The event schema is documented in [Test Instrumentation](../architecture/test_instrumentation.md).

### No Fixed Waits

Follow the [No-Sleep Patterns](./no_sleep_patterns.md) reference. Use `Promise.all` with `waitForResponse`, scoped `expect` checks, or `expect(...).toPass()` when polling a testing endpoint, instead of `waitForTimeout`.

### Backend Extensions for Complex Flows

- When a scenario needs state the public API cannot seed or an event it cannot trigger on demand, add a testing endpoint to the backend (`backend/app/api/testing*.py`, answering only in testing mode). The suite seeds firmware through `/api/testing/device-models/{model_id}/firmware`, core dumps through `/api/testing/coredumps` and device logs through `/api/testing/devices/logs/seed`, injects live log lines through `/api/testing/devices/logs/inject`, and nudges the rotation dashboard through `/api/testing/rotation/nudge`.
- Wrap an endpoint a spec calls repeatedly in a factory method, so specs seed state through fixtures rather than ad hoc requests.
- If the backend cannot yet support the scenario, pause the Playwright work and extend the backend first. Route interception is not an acceptable fallback.

### SSE Streams

The app keeps one SSE connection to the backend's `GET /api/sse/stream`, through the worker's Vite proxy; device logs, the rotation dashboard and the deployment banner all ride on it.

- Call `await deploymentSse.ensureConnected()` before an assertion depends on the stream. It waits for the connection the app opens on mount and opens one itself when that does not come up, then returns `{ isConnected, requestId }`.
- `deploymentSse.getRequestId()` gives the connection's request id for endpoints keyed on it, such as `POST /api/device-logs/subscribe`. `deploymentSse.resetRequestId()` after navigation gives the next connection a fresh id.
- The Logs tab subscribes on mount, but StrictMode's second mount can race its own unsubscribe; `devices-logs-sse.spec.ts` re-creates the subscription after switching to the tab, and polls `/api/testing/devices/logs/subscriptions` with `expect(...).toPass()` until it is active.
- Trigger a deployment update with `POST /api/testing/deployments/version` and `{ request_id, version }`. It answers 202 with `{ request_id, delivered, status }`, `status` being `delivered` or `queued`. The banner compares each version with the first one it received, so send a baseline, wait for it with `deploymentSse.waitForCurrentVersion(baseline)`, then send the update.
- The `deploymentSse` fixture disconnects on teardown.
- The dev server never takes the SharedWorker path; a test-mode production build takes it when the URL carries `__sharedWorker`. The specs for that path carry the `@preview` tag and skip unless `PLAYWRIGHT_PREVIEW_MODE=true` (see [CI & Execution → Preview Mode](./ci_and_execution.md#preview-mode)).

### App Shell Instrumentation

- The `AppShellPage` page object (`tests/support/page-objects/app-shell-page.ts`) exposes helpers for the sidebar, mobile menu, deployment banner, and toast viewport. Prefer using it over ad hoc selectors.
- Sidebar links carry `data-testid="app-shell.sidebar.link.<slug>"` (`app-shell.sidebar.link.devices`, for one) and reflect active state via `data-active="true"`. Collapse state is surfaced by `data-state` on `app-shell.sidebar`; the root layout tracks the mobile menu state with `data-mobile-menu-state`.
- Global toasts render under `data-testid="app-shell.toast.item"` inside the viewport `data-testid="app-shell.toast.viewport"`. Assert toasts via these selectors or the `toastHelper` fixture rather than querying by role.
- The deployment banner reload CTA is addressable via `data-testid="deployment.banner.reload"` and relies on the real backend SSE trigger.

## Suite Conventions

- **Specs**: Name files `*.spec.ts` (`devices-crud.spec.ts`, `rotation-sse.spec.ts`) and colocate them with their feature folder under `tests/e2e/<feature>/`.
- **Page Objects**: A class beside the specs (`tests/e2e/devices/DevicesPage.ts`) with `goto*()` navigation, locators and actions; specs construct their own (`new DevicesPage(page)`). Keep assertions inside tests unless they are part of the action contract.
- **Test IDs**: Add `data-testid` attributes when semantic roles are insufficient. Follow the `feature.section.element` naming scheme (e.g., `devices.list.row`, `devices.editor.flash-device`).
- **Instrumentation Hooks**: Instrument a new form with `useFormInstrumentation` (`src/hooks/use-form-instrumentation.ts`) and a new list with `useListLoadingInstrumentation` (`src/lib/test/query-instrumentation.ts`); both emit only in test mode. Guard any other emitter with `isTestMode()`.

## Expanding Coverage

1. Update or add factories if new backend endpoints are required.
2. Introduce or extend a page object in `tests/e2e/<feature>/`.
3. Write scenarios that create preconditions through factories, exercise the UI flow, and assert via UI + test-event signals.
4. Run `cexec modern-app pnpm playwright test tests/e2e/<feature>/<file>.spec.ts` from `frontend/` before committing.
5. Run `kc project lint frontend` to ensure lint (including `testing/no-route-mocks`), type-check and knip pass.

For a checklist-style walkthrough, see [How to Add an E2E Test](../howto/add_e2e_test.md).

## Additional References

- [Selector Patterns](./selector_patterns.md)
- [Factories & Fixtures](./factories_and_fixtures.md)
- [CI & Execution](./ci_and_execution.md)
- [Troubleshooting](./troubleshooting.md)
