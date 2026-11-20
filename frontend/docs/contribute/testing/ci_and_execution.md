# CI & Execution

This guide covers how Playwright runs locally and in CI, including managed services, environment variables, and execution policies.

## Running Locally

`kc project` verbs are run from the repository root (it reads the manifest of
the directory it runs in); `cexec` mirrors your working directory, so the pnpm
forms below are run from `frontend/`.

```bash
# Install node dependencies and the Chromium browser once
kc project setup frontend

# Default run (headless)
kc project test frontend

# Focus on a single file
cexec modern-app pnpm playwright test tests/e2e/devices/devices-crud.spec.ts

# Focus on a single test
cexec modern-app pnpm playwright test -g 'edits an existing device'

# Debug mode (headed, under the Playwright Inspector)
cexec modern-app pnpm playwright test --debug
```

From the repository root, `cexec modern-app uv run run-suite --suite frontend` runs the suite the way CI does: it installs and builds the frontend, runs Playwright, then runs the preview pass ([Preview Mode](#preview-mode)). `--frontend-args "tests/e2e/devices/devices-crud.spec.ts"` narrows it to a spec.

`kc project lint frontend` runs `pnpm check`—`eslint` (including the `testing/no-route-mocks` rule), `tsc -b --noEmit` and `knip`—and validates the frontend's architecture model.

## Local Run Expectations

Before handing off work (plans or implementation), make sure the tooling that catches regressions has already passed locally:

1. Run `kc project lint frontend` and resolve any lint, type or knip failures.
2. Re-run every Playwright spec file you edited (`cexec modern-app pnpm playwright test tests/...`) plus any suites that exercise shared flows you touched.
3. Fix flakes or failures immediately—do not defer them to reviewers or CI.
4. Note the exact commands and pass/fail status in your final summary so handoffs stay auditable.

Playwright is configured in `playwright.config.ts` with `headless: true`; `--debug` runs headed.

## Per-Worker Managed Services

Each Playwright worker starts its own isolated backend and frontend on free ports (`get-port`), from the worker-scoped fixture in `tests/support/fixtures-infrastructure.ts` and the launchers in `tests/support/process/servers.ts`.

Service startup sequence (per worker):
1. **Database** – The worker clones the run's seed database into its own, `<run prefix>_w<parallel index>` (`tests/support/helpers/pg-admin.ts`).
2. **Backend** – Started via `../backend/scripts/testing-server.sh --host 127.0.0.1 --port <port> --database-url <worker database>`, which runs the backend with `FLASK_ENV=testing`. The launcher sets `OIDC_ENABLED=false`, the `DEVICE_MQTT_URL`, `WIFI_SSID` and `WIFI_PASSWORD` that Provision device's NVS blob needs, and `FRONTEND_VERSION_URL`.
3. **Frontend** – Started via `./scripts/testing-server.sh --host 127.0.0.1 --port <port>` with `VITE_TEST_MODE=true` and `BACKEND_URL` set to the worker's backend. Vite proxies `/api`, the SSE stream included, to it.

Health checks:
- Backend: polls `GET /health/readyz` until HTTP 200.
- Frontend: polls `/` until HTTP 200.

Each service gets 120s to become ready, and the worker's whole startup 300s. When the worker finishes, it stops the frontend, then the backend, and drops its database.

Global setup refuses `PLAYWRIGHT_MANAGED_SERVICES=false`: the suite always runs its own services.

## Preview Mode

`PLAYWRIGHT_PREVIEW_MODE=true` makes each worker's frontend `scripts/testing-server.sh --preview`, which serves the production build in `dist/` with `vite preview`. That build must be made with `VITE_TEST_MODE=true pnpm build`; the script refuses a `dist/` without the Playwright bridges. Specs that only a production build can exercise—the SSE SharedWorker path in `tests/infrastructure/sse/`—carry the `@preview` tag and skip without it. `run-suite`'s preview pass rebuilds the frontend in test mode and runs the `@preview` specs this way; it is skipped when the selected specs hold none.

## Global Setup

`tests/support/global-setup.ts` runs once before the suite:
- Throws if `PLAYWRIGHT_MANAGED_SERVICES=false` is set.
- Builds the run's seed database (`iot_support_e2e_<run id>_seed`) on the PostgreSQL server the backend suite uses (`TEST_DATABASE_ADMIN_URL`, the `postgres` sidecar by default), with the backend's `uv run cli load-test-data`. It first drops the databases that dead runs left behind.

`tests/support/global-teardown.ts` drops the run's databases, best effort.

## Execution Policies

- **Browser**: Chromium only (`devices['Desktop Chrome']`).
- **Retries**: `retries: 0` in the config; tests must be deterministic. CI runs with `--retries 2`.
- **Parallelism**: `workers: 2` with `fullyParallel: true`, so the tests of one file are spread over both workers too. `--workers=<n>` (or `run-suite --workers <n>`) overrides it; every worker starts its own services.
- **Timeouts**: Global `expect` timeout is 10s. Use the shared `sseTimeout` fixture for longer SSE waits (35s).
- **Artifacts**: Screenshots on failure, traces on first retry, no video. `PLAYWRIGHT_RETAIN_VIDEO=true` records video and keeps it for failed tests. Results go to `test-results/`, the HTML report to `playwright-report/`.
- **Tags**: Tests tagged `@slow` are left out unless `INCLUDE_SLOW_TESTS` is set. With `CI` set, a `test.only` left in a spec fails the run.

## Environment Overrides

`playwright.config.ts` loads `frontend/.env.test` through `dotenv` when the file exists. It is gitignored and the repository ships none; create it for local overrides:

```bash
# Stream each worker's service output to the terminal (optional)
PLAYWRIGHT_BACKEND_LOG_STREAM=true
PLAYWRIGHT_FRONTEND_LOG_STREAM=true
```

The other variables the suite reads:

- `PLAYWRIGHT_RETAIN_VIDEO`, `PLAYWRIGHT_PREVIEW_MODE`, `INCLUDE_SLOW_TESTS` – see above.
- `TEST_DATABASE_ADMIN_URL` – the PostgreSQL server for the run's databases; defaults to `postgresql+psycopg://postgres:postgres@localhost:5432/postgres`.
- `BACKEND_ROOT` – where the backend lives, relative to `frontend/`; defaults to `../backend`.

The backend takes its own settings from `backend/.env`, with `backend/.env.test` over it (`testing-server.sh`). Service URLs are managed by the worker fixtures and should not be overridden.

## CI Integration

- The `IoTSupport` Jenkins job (`Jenkinsfile`) runs the suite in a Kubernetes Job through the `JenkinsPipelineUtils` library's `modernApp.test`: `uv run --no-sync run-suite --output-mode full --junitxml-dir /work/results --retries 2`, beside the sidecars the `Jenkinsfile` lists.
- `run-suite` runs Playwright with `--reporter=list,junit` and `PLAYWRIGHT_BACKEND_LOG_STREAM=true`, so the backend's output lands in the build log, then runs the preview pass.
- Jenkins archives the build log and the JUnit reports and publishes the JUnit report. Playwright's `test-results/` (screenshots, traces) stays in the Job's pod, which is deleted after the run.
- Treat failing `console.error` output as blocking unless deliberately silenced via helpers.

## Debugging Tips

- Use `cexec modern-app pnpm playwright test --debug` to launch the inspector and step through tests.
- Use `--trace on` to record a trace without a retry, and open it from the HTML report.
- Use the `testEvents` fixture (e.g., `console.log(await testEvents.dumpEvents())`) to inspect emitted payloads.
- Enable log streaming to see real-time service output: `cexec modern-app env PLAYWRIGHT_BACKEND_LOG_STREAM=true pnpm playwright test`.
- Service logs are attached to each test result as `backend.log` and `frontend.log`.
- When managed services fail to start, enable log streaming: a worker whose services never came up has no test to attach its logs to. See [Troubleshooting](./troubleshooting.md#managed-services-fail-to-start).

Related docs: [Environment Reference](../environment.md), [Playwright Developer Guide](./playwright_developer_guide.md), [Troubleshooting](./troubleshooting.md).
