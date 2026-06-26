# Troubleshooting

Use this checklist when Playwright runs fail or behave inconsistently.

## Managed Services Fail to Start

- Ensure the backend repository exists at `../backend/`.
- Run `./scripts/testing-server.sh` manually to view stdout/stderr.
- Verify ports 3100 (frontend) and 5100 (backend) are free.
- Confirm `.env.test` does not overwrite `FRONTEND_URL`/`BACKEND_URL` with incorrect values.

## Tests Hang on Startup

- Check that `VITE_TEST_MODE` is set to `true` (managed services handle this). Without it, test event emitters stay silent and helpers may wait forever.
- Inspect `test-results/` and `playwright-report/` for traces.
- Ensure `PLAYWRIGHT_MANAGED_SERVICES` is not `false` when you expect automatic orchestration.

## Unexpected `console.error`

- Re-run the spec with `pnpm playwright test -g "<test name>"` to isolate.
- Use `expectConsoleError(page, <pattern>)` if the error is expected (e.g., blocked delete).
- Inspect frontend console output for stack traces; instrumentation often mirrors the same payload via the `error` test event.

## Dirty Database Collisions

- Confirm factories use randomized names (`testData.types.randomTypeName()` etc.).
- If collisions persist, add clearer prefixes (e.g., `types.randomTypeName('EditFlow')`).
- Remember that tests never clean up; design flows to tolerate existing data.

## Missing Test Events

- Verify the relevant instrumentation is guarded by `isTestMode()` and lives in the UI code path being executed.
- From within a Playwright spec, call `await testEvents.dumpEvents()` to inspect the buffered payloads; for manual repros, rely on UI signals because the bridge is Playwright-only.
- Inspect `src/lib/test/*` emitters if new components require additional hooks.

## Network Errors / 409 Conflicts

- Use `expectConflictError(page)` to await the `query_error` event and assert correlation IDs when applicable.
- Ensure the backend test endpoints are running (`/api/health/readyz`).
- Check if the API client in factories targets the correct `BACKEND_URL`.

## SSE or Long-Polling Timeouts

- Use the shared `sseTimeout` fixture for operations that legitimately exceed 10s.
- Verify the backend SSE endpoint is available in testing mode.
- Confirm the test listens for the `sse` test event where applicable.

## Flaky Selectors

- Replace brittle CSS or `:has-text` selectors with semantic roles or scoped locators.
- Move repeated interactions into page object methods for consistent waits.
- Consult [Selector Patterns](./selector_patterns.md) for best practices.

## Still Stuck?

- Run `pnpm playwright test --debug` to inspect the DOM in real time.
- Capture the buffered events (`await testEvents.dumpEvents()`) and compare against expected sequences in [Test Instrumentation](../architecture/test_instrumentation.md).
- Cross-check the `playwright.config.ts` settings for timeouts and managed services.

Related docs: [CI & Execution](./ci_and_execution.md), [Factories & Fixtures](./factories_and_fixtures.md), [Error Handling & Validation](./error_handling_and_validation.md).
