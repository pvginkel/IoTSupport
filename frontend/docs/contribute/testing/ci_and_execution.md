# CI & Execution

This guide covers how Playwright runs locally and in CI, including managed services, environment variables, and execution policies.

## Running Locally

`kc project` verbs are run from the repository root (it reads the manifest of
the directory it runs in); `cexec` mirrors your working directory, so the pnpm
forms below are run from `frontend/`.

```bash
# Install browser dependencies once
kc project setup frontend

# Default run (headless)
kc project test frontend

# Focus on a single file
cexec modern-app pnpm playwright test tests/e2e/types/types-workflow.spec.ts

# Focus on a single test
cexec modern-app pnpm playwright test -g 'workflow with multiple types'

# Debug mode (headed inspector)
cexec modern-app pnpm playwright test --debug
```

Linting and type-checking are part of the default build now—run `kc project lint frontend` locally to execute `eslint` (including the `testing/no-route-mocks` rule) and `tsc --noEmit` before pushing changes.

## Local Run Expectations

Before handing off work (plans or implementation), make sure the tooling that catches regressions has already passed locally:

1. Run `kc project lint frontend` and resolve any lint or type failures.
2. Re-run every Playwright spec file you edited (`cexec modern-app pnpm playwright test tests/...`) plus any suites that exercise shared flows you touched.
3. Fix flakes or failures immediately—do not defer them to reviewers or CI.
4. Note the exact commands and pass/fail status in your final summary so handoffs stay auditable.

Playwright is configured in `playwright.config.ts` with `headless: true` by default. Debug mode is the only supported headed execution.

## Per-Worker Managed Services

Playwright now uses per-worker managed services exclusively. Each worker starts its own isolated backend and frontend on dynamically allocated ports.

Service startup sequence (per worker):
1. **Backend** – Started via `../backend/scripts/testing-server.sh --database-url <worker-db>`, on the worker's own PostgreSQL database, cloned from the run's seed (`<run>_w<parallel index>`).
2. **Frontend** – Started via `./scripts/testing-server.sh` with `VITE_TEST_MODE=true`, proxying to the worker's backend, the SSE stream included.

Health checks:
- Backend: polls `GET /api/health/readyz` until HTTP 200.
- Frontend: polls base URL until HTTP 200.

The external services mode (`PLAYWRIGHT_MANAGED_SERVICES=false`) has been removed. All tests now use per-worker isolation.

## Global Setup

`tests/support/global-setup.ts` runs once before the suite:
- Loads `.env.test`.
- Throws an error if `PLAYWRIGHT_MANAGED_SERVICES=false` is detected (external services mode has been removed).
- Builds the run's seed database (`iot_support_e2e_<run id>_seed`) on the PostgreSQL server the backend suite uses (`TEST_DATABASE_ADMIN_URL`, the `postgres` sidecar by default), with the backend's `load-test-data`. Each worker clones it, and global teardown drops the run's databases (`tests/support/helpers/pg-admin.ts`).

## Execution Policies

- **Browser**: Chromium only (`devices['Desktop Chrome']`).
- **Retries**: Disabled; tests must be deterministic.
- **Parallelism**: Fully parallel locally; CI limits to 1 worker for stability.
- **Timeouts**: Global `expect` timeout is 10s. Use the shared `sseTimeout` fixture for longer SSE waits (35s).
- **Artifacts**: Videos retained on failure, screenshots on failure, traces on first retry.

## Environment Overrides

Use `.env.test` to configure log streaming:

```bash
# Enable log streaming for debugging (optional)
PLAYWRIGHT_BACKEND_LOG_STREAM=true
PLAYWRIGHT_FRONTEND_LOG_STREAM=true
```

Service URLs are managed automatically by worker fixtures and should not be overridden.

## CI Integration

- Suites run headless with per-worker managed services.
- Artifacts (`test-results/`, `playwright-report/`) should be collected for debugging.
- Service logs (`backend.log`, `frontend.log`) are attached to each test result.
- Treat failing `console.error` output as blocking unless deliberately silenced via helpers.

## Debugging Tips

- Use `cexec modern-app pnpm playwright test --debug` to launch the inspector and step through tests.
- Use the `testEvents` fixture (e.g., `await testEvents.dumpEvents()`) to inspect emitted payloads when debugging locally.
- Enable log streaming to see real-time service output: `cexec modern-app env PLAYWRIGHT_BACKEND_LOG_STREAM=true pnpm playwright test`.
- Service logs are automatically attached to test results as `backend.log` and `frontend.log`.
- When managed services fail to start, check the attached logs in the HTML report or enable log streaming for real-time output.

Related docs: [Environment Reference](../environment.md), [Playwright Developer Guide](./playwright_developer_guide.md), [Troubleshooting](./troubleshooting.md).
