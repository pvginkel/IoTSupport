# Playwright Developer Guide

The Playwright suite drives the production frontend against the real backend in testing mode. This guide explains how the suite is structured, how to seed data safely, and how to extend coverage without breaking stability.

## Before You Start

1. Complete the [Getting Started](../getting_started.md) setup and ensure `pnpm playwright test` passes locally.
2. Understand the [Environment Reference](../environment.md) to configure URLs and test mode.
3. Review the [Test Instrumentation](../architecture/test_instrumentation.md) taxonomy—tests frequently assert on emitted test-event payloads.
4. Confirm the UI flow you are touching emits the required instrumentation; add or adjust it *before* writing a spec so tests can rely on deterministic events.

## Core Principles

1. **API-first data setup** – Always create prerequisite data with factories; UI interactions are only for the scenario under test.
2. **Real backend always** – Specs must hit the live backend endpoints. Do not intercept, stub, or shortcut HTTP calls; the `testing/no-route-mocks` ESLint rule guards this policy. Missing behavior belongs in the backend, not in Playwright helpers—the only suppression lives next to the shared AI analysis mock and documents its backend gap.
3. **Dirty database policy** – Tests never reset or clean up. Use randomized identifiers so reruns tolerate existing data, never rely on data seeded by another test, and ignore any concerns about residual records—databases are rebuilt between runs. If volume ever reveals performance issues, treat that as a backend optimization problem.
4. **Feature-owned page objects** – Each feature folder exposes actions/locators tailored to that UI.
5. **Deterministic waits** – Assertions rely on UI visibility, network promises, or test-event signals—never fixed sleeps.
6. **Console is the contract** – Unexpected `console.error` fails the test unless explicitly marked as expected via helpers.

## Suite Architecture

### API Client (`tests/api/client.ts`)

A Node-compatible OpenAPI client backed by `openapi-fetch`. The helper accepts an optional `{ baseUrl }` override so worker fixtures can point each Playwright worker at its dedicated backend.

```typescript
import { createApiClient, apiRequest } from '../api/client';

const client = createApiClient({ baseUrl: backendUrlFromFixture });
const { data } = await apiRequest(() => client.GET('/api/types'));
```

### Factories (`tests/api/factories/*`)

Factories wrap the API client with domain-specific helpers and randomized data generators. They power the `testData` fixture.

```typescript
const factory = testData.types;
const type = await factory.create();               // defaults with random name
const other = await factory.create({ name: factory.randomTypeName('Capacitor') });
```

Attachments are available via `testData.attachments` so specs can seed documents, covers, and previews against the real `/api/parts/:id/attachments/**` endpoints without inline stubs.

`createTestDataBundle(apiClient, { backendUrl })` accepts the worker backend URL so attachment helpers can build deterministic media URLs without reading global environment variables.

See [Factories & Fixtures](./factories_and_fixtures.md) for a catalog of available methods.

### Fixtures (`tests/support/fixtures.ts`)

Custom fixtures extend Playwright's base test:

- `frontendUrl` / `backendUrl` – Provided by the worker-scoped service manager. In managed mode every worker boots its own backend + Vite proxy; when `PLAYWRIGHT_MANAGED_SERVICES=false` they fall back to the externally supplied URLs.
- `backendLogs` – Captures per-worker backend stdout/stderr and publishes them as `backend.log` attachments for each spec (enable live streaming with `PLAYWRIGHT_BACKEND_LOG_STREAM=true`).
- `testData` – Bundled factories for `types`, `parts`, etc.
- `types` – Page object for the Types feature (`tests/e2e/types/TypesPage.ts`).
- `page` override – Registers the Playwright test-event bridge, enforces console error policy (unexpected errors fail the test), and disables animations for determinism.
- `testEvents` – Provides access to the circular buffer of test-event payloads (`TestEventCapture`) for sequence assertions and debugging dumps.
- `sseTimeout` – Shared SSE-aware timeout (35s) for long polling scenarios.

Import fixtures via:

```typescript
import { test, expect } from '../support/fixtures';
```

### Service Lifecycle

`PLAYWRIGHT_MANAGED_SERVICES` defaults to `"true"`, which instructs the `tests/support/process/*` helpers to launch an isolated backend + frontend pipeline for each Playwright worker:

- **Backend** – Global setup seeds a SQLite database via `../backend/scripts/initialize-sqlite-database.sh --db <seed> --load-test-data`, and each worker copies that file before `tests/support/process/servers.ts` calls `startBackend` to shell into `../backend/scripts/testing-server.sh --sqlite-db=<worker-db>`, waits for `/api/health/readyz`, and exposes the per-worker origin.
- **Frontend** – `tests/support/process/servers.ts` calls `startFrontend` to run `pnpm exec vite --host 127.0.0.1 --port <random>` with `BACKEND_URL=<worker-backend> VITE_TEST_MODE=true` so UI calls automatically target the worker backend.
- **Logging** – `backendLogs` pipes stdout/stderr through `split2`, tags every line with the worker index, and writes a `backend.log` attachment for each spec. Set `PLAYWRIGHT_BACKEND_LOG_STREAM=true` locally to tee the log stream to your terminal.

Set `PLAYWRIGHT_MANAGED_SERVICES=false` when you need to point the suite at pre-managed infrastructure (for example, shared staging). In that mode the worker fixtures skip process orchestration and reuse the `FRONTEND_URL`/`BACKEND_URL` you provide; optional `webServer` commands in `playwright.config.ts` remain available if you prefer the legacy global servers.

### Helpers (`tests/support/helpers.ts`)

Utility functions that complement fixtures:

- `makeUnique(prefix)` – Standard prefix-shortId generator (eslint-enforced replacement for `Date.now()`).
- `waitTestEvent(page, kind, filter?, timeout?)` – Await specific test-event payloads from the Playwright-managed buffer.
- `waitForUiState(page, scope, phase)` – Await structured `ui_state` events for deterministic workflow checkpoints (form submissions, etc.).
- `waitForListLoading(page, scope, phase)` – Await list loading lifecycle events (`list_loading`) emitted by test-mode instrumentation (`types.list`, `parts.list`, etc.).
- `waitForFormValidationError(page, formId, field?)`
- `expectConflictError(page, correlationId?)`
- `expectConsoleError(page, pattern)` – Allow known console errors for a test.

## Authoring Patterns

### Create Data First

```typescript
test('edits an existing type', async ({ testData, types }) => {
  const existing = await testData.types.create();

  await types.goto();
  await types.cardByName(existing.name).click();
  await types.rename(existing.name, testData.types.randomTypeName());
});
```

- Never drive prerequisite flows through the UI (no create-via-form followed by edit assertions).
- Use factory overrides to craft edge cases (duplicate names, dependency chains, etc.).
- Seed data uniquely for each spec. If multiple tests need similar state, each must create its own records.

### Randomize Identifiers

All factories support random helpers; use them to avoid collisions on dirty databases.

```typescript
const name = testData.types.randomTypeName('Resistor');
await testData.types.create({ name });
```

The eslint rule forbids `Date.now()`; rely on `makeUnique` (or domain helpers that wrap it) for uniqueness. When a real timestamp is required, add a targeted disable comment with justification in the diff.

### Console Error Policy

Fixtures treat any `console.error` as a failure. If a test intentionally triggers an error (e.g., blocked delete), mark it as expected.

```typescript
await expectConsoleError(page, /cannot delete type/i);
await types.attemptDelete(blockedType.name);
```

### Test-Event Assertions

Never start writing the spec until the UI emits the events you need—instrumentation drives every deterministic wait. Prefer UI assertions first, but when behavior is exposed via instrumentation (forms, toasts, SSE), use helpers for precision.

```typescript
await waitTestEvent(page, 'form', evt =>
  evt.formId === 'TypeForm_edit' && evt.phase === 'success'
);

await waitForListLoading(page, 'parts.list', 'ready');
```

For multi-step flows, capture sequences explicitly:

```typescript
const [submit, success] = await Promise.all([
  waitTestEvent(page, 'form', evt => evt.phase === 'submit' && evt.formId === formId),
  waitTestEvent(page, 'form', evt => evt.phase === 'success' && evt.formId === formId),
  page.getByRole('button', { name: /save/i }).click(),
]);

expect(success.timestamp > submit.timestamp).toBeTruthy();
```

Avoid over-asserting—validate the critical transitions (submit → success, toast levels, API status) required by the scenario and lean on UI checks for the rest.

The event schema is documented in [Test Instrumentation](../architecture/test_instrumentation.md).

### No Fixed Waits

Follow the [No-Sleep Patterns](./no_sleep_patterns.md) reference. Use `Promise.all` with `waitForResponse` or scoped `expect` checks instead of `waitForTimeout`.

### Backend Extensions for Complex Flows

- When a scenario needs deterministic backend behavior (for example, AI analysis over SSE), add test-specific hooks to the service. The pattern is: seed a prebaked response through an API exposed for tests, then drive the UI using a sentinel input such as `test-response-12345` that instructs the backend to emit the prepared payload. Do not emulate the SSE stream in Playwright.
- If the backend cannot yet support the scenario, pause the Playwright work and extend the backend first. Route interception is not an acceptable fallback.
- Any temporary waiver must live alongside the shared AI analysis helper and use the `// eslint-disable-next-line testing/no-route-mocks -- <justified reason>` format so the lint rule documents the gap in-line.

### Deployment Version Stream (real backend only)

- Playwright runs disable the auto-connect path; use the `deploymentSse` fixture to opt into `/api/utils/version/stream` on a per-spec basis.
- Call `await deploymentSse.resetRequestId()` after navigation, then `await deploymentSse.ensureConnected()` to open the stream with a fresh id and `deploymentSse.getStatus()` when you need the latest `{ isConnected, requestId }` state.
- Trigger backend delivery with `POST /api/testing/deployments/version` using the streamed `requestId`. The response echoes `{ requestId, delivered, status }` so specs can assert whether the update arrived immediately or on reconnect.
- SSE payloads always include `correlation_id` matching the `request_id`; use it to tie Playwright assertions to backend telemetry instead of stubbing deployment updates.
- Disconnect via `await deploymentSse.disconnect()` once a spec finishes its streaming assertions so the provider stops listening before the next test.
- Local dev servers do not expose `version.json`; seed a baseline release via the testing trigger before asserting a follow-up update so the banner logic observes a genuine version change.

### App Shell Instrumentation

- The `AppShellPage` page object (`tests/support/page-objects/app-shell-page.ts`) exposes helpers for the sidebar, mobile menu, deployment banner, and toast viewport. Prefer using it over ad hoc selectors.
- Sidebar links carry `data-testid="app-shell.sidebar.link.<slug>"` and reflect active state via `data-active="true"`. Collapse state is surfaced by `data-state` on `app-shell.sidebar`; the root layout tracks the mobile menu state with `data-mobile-menu-state`.
- Global toasts render under `data-testid="app-shell.toast.item"` inside the viewport `data-testid="app-shell.toast.viewport"`. Every toast test should assert via these selectors rather than querying by role.
- The deployment banner reload CTA is addressable via `data-testid="deployment.banner.reload"` and still relies on the real backend SSE trigger.

## Suite Conventions

- **Specs**: Name files `*.spec.ts` and colocate with feature folders under `tests/e2e/<feature>/`.
- **Page Objects**: Export a class with a `goto()` method plus actions/locators; keep assertions inside tests unless they are part of the action contract.
- **Test IDs**: Add `data-testid` attributes when semantic roles are insufficient. When adding new IDs, follow the `feature.section.element` naming scheme (e.g., `types.form.submit`).
- **Instrumentation Hooks**: Emit `trackFormSubmit`, `trackFormSuccess`, etc., in frontend code when adding new forms. Always guard them with `isTestMode()`.

## Expanding Coverage

1. Update or add factories if new backend endpoints are required.
2. Introduce or extend a page object in `tests/e2e/<feature>/`.
3. Write scenarios that create preconditions through factories, exercise the UI flow, and assert via UI + test-event signals.
4. Run `pnpm playwright test tests/e2e/<feature>/<file>.spec.ts` locally before committing.
5. Run `pnpm check` to ensure lint (including `testing/no-route-mocks`) and type-check pass.

For a checklist-style walkthrough, see [How to Add an E2E Test](../howto/add_e2e_test.md).

## Additional References

- [Selector Patterns](./selector_patterns.md)
- [Factories & Fixtures](./factories_and_fixtures.md)
- [CI & Execution](./ci_and_execution.md)
- [Troubleshooting](./troubleshooting.md)
