# Troubleshooting

Use this checklist when Playwright runs fail or behave inconsistently.

## Managed Services Fail to Start

- Read the error: it names the worker and the service, and says whether the process exited before it was ready (`process exited before ready (code=…)`) or never answered its readiness check (`Timed out waiting for readiness at …/health/readyz`, with the last response).
- Re-run with `PLAYWRIGHT_BACKEND_LOG_STREAM=true` and `PLAYWRIGHT_FRONTEND_LOG_STREAM=true` to see each service's output; a worker whose services never came up attaches no `backend.log` or `frontend.log`.
- Ensure the backend is at `../backend/` from `frontend/`, or that `BACKEND_ROOT` points at it.
- Run a server by hand to see its output: `cexec modern-app ../backend/scripts/testing-server.sh --port <port>` for the backend, and `cexec modern-app env BACKEND_URL=http://127.0.0.1:<port> ./scripts/testing-server.sh --port <other port>` from `frontend/` for the frontend.
- Workers pick free ports themselves, so a dev stack on 3100/3101 does not collide with them.
- Unset `PLAYWRIGHT_MANAGED_SERVICES=false`; global setup refuses it.

## Global Setup Fails

- The run's databases live on the PostgreSQL server at `TEST_DATABASE_ADMIN_URL`, by default the `postgres` sidecar at `localhost:5432`. Check that it is up.
- A failed `uv run cli load-test-data` prints its output; fix the backend's test data or migrations it points at.
- The backend's settings come from `backend/.env`, then `backend/.env.test`; the launcher forces `OIDC_ENABLED=false` for the seed and every worker's backend.

## Tests Hang on Startup

- Check that `VITE_TEST_MODE` is `true` in the frontend (`scripts/testing-server.sh` sets it). Without it, test event emitters stay silent and helpers wait until they time out.
- With `PLAYWRIGHT_PREVIEW_MODE=true`, `dist/` must come from `VITE_TEST_MODE=true pnpm build`; `scripts/testing-server.sh --preview` refuses a build without the Playwright bridges.
- Inspect `test-results/` and `playwright-report/` for screenshots and traces.

## Unexpected `console.error`

- Re-run the spec with `cexec modern-app pnpm playwright test -g "<test name>"` to isolate.
- Use `expectConsoleError(page, <pattern>)` if the error is expected. The `page` fixture already lets through the errors HTTP failures log (400, 401, 403, 404, 409, 500) and `Toast exception` lines.
- Inspect frontend console output for stack traces; instrumentation often mirrors the same payload via the `error` test event.

## Dirty Database Collisions

- Each worker's backend serves its own clone of the run's seed, but the tests of one worker share it, and every worker shares one Keycloak realm.
- Confirm factories use randomized names (`devices.randomDeviceName()`, `devices.randomDeviceEntityId()`, `deviceModels.randomModelCode()`); if collisions persist, add clearer prefixes (e.g., `devices.randomDeviceEntityId('sse_inject_test')`).
- Do not assume an empty list: assert on the rows your test created (`devicesPage.rowByKey(device.key)`).
- Remember that tests never clean up their records; design flows to tolerate existing data.

## Device Clients Left in Keycloak

- A device's Keycloak client is `iotdevice-<model code>-<key>`. The `devices` fixture's teardown deletes the clients matching `^iotdevice-playwright_w<N>_` through `/api/testing/keycloak-cleanup`, and ignores a failure or a 30s timeout.
- Create models through `deviceModels` (or let `devices.create()` make one) so their codes carry the worker's prefix.

## Missing Test Events

- Verify the relevant instrumentation is guarded by `isTestMode()` and lives in the UI code path being executed.
- From within a Playwright spec, log `await testEvents.dumpEvents()` to inspect the buffered payloads; for manual repros, rely on UI signals because the bridge is Playwright-only.
- Under StrictMode on the dev server, a scope can report once for a discarded mount; filter on the event's metadata as `devices-flashing.spec.ts` does.
- The buffer holds 500 events; a test that overflows it fails with `Test event buffer overflow!`.
- Inspect `src/lib/test/*` emitters if new components require additional hooks.

## Flash or Provision Device Fails

- Call `installFakeEspDevice(page, config?)` before the page loads; without it `navigator.serial` is the browser's own, whose port picker Playwright cannot drive.
- The `esptool-js` mock is aliased in only when `VITE_TEST_MODE=true`.
- `readFakeEspDevice(page)` shows what the fake device was asked for. [Factories & Fixtures → The Fake USB Device](./factories_and_fixtures.md#the-fake-usb-device) has its configuration.

## Network Errors / 409 Conflicts

- Use `expectConflictError(page)` to await the `query_error` event and assert correlation IDs when applicable.
- Ensure the worker's backend is ready (`/health/readyz`).
- Factories send their requests to the worker's frontend URL, through the Vite proxy; check the proxy if factory calls fail while the backend is up.

## SSE or Long-Polling Timeouts

- Use the shared `sseTimeout` fixture for operations that legitimately exceed 10s.
- Call `deploymentSse.ensureConnected()` before an assertion depends on the stream.
- For device logs, check the subscription through `/api/testing/devices/logs/subscriptions`; StrictMode can drop it, and `devices-logs-sse.spec.ts` re-creates it.
- Confirm the test listens for the `sse` test event where applicable (`waitForSseEvent`).
- SharedWorker specs carry `@preview` and skip on the dev server; run them with `PLAYWRIGHT_PREVIEW_MODE=true` (see [CI & Execution → Preview Mode](./ci_and_execution.md#preview-mode)).

## Flaky Selectors

- Replace brittle CSS or `:has-text` selectors with semantic roles or scoped locators.
- Move repeated interactions into page object methods for consistent waits.
- Consult [Selector Patterns](./selector_patterns.md) for best practices.

## Still Stuck?

- Run `cexec modern-app pnpm playwright test --debug` to inspect the DOM in real time, or `--trace on` to record a trace.
- Capture the buffered events (`await testEvents.dumpEvents()`) and compare against expected sequences in [Test Instrumentation](../architecture/test_instrumentation.md).
- Cross-check the `playwright.config.ts` settings for timeouts, workers and artifacts.

Related docs: [CI & Execution](./ci_and_execution.md), [Factories & Fixtures](./factories_and_fixtures.md), [Error Handling & Validation](./error_handling_and_validation.md).
