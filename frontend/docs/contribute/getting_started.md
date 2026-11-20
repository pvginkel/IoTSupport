# Getting Started

This guide walks new contributors through installing dependencies, generating the API client and route tree, running the app against the backend, and validating the Playwright tooling. Follow it sequentially before branching into feature work or test authoring.

## Prerequisites

Node, pnpm, uv and the Playwright system libraries all come from the `modern-app`
tool container, so there is nothing to install by hand — run pnpm through
`cexec modern-app`, or use the `kc project` verbs, which do it for you.

- **Backend** — it lives in `backend/` of this same repository (see [backend/README.md](../../../backend/README.md)). The dev stack runs it beside the frontend, and the Playwright suite starts its own copies of it.
- **PostgreSQL** — the dev backend's database, and the server the Playwright suite builds its run's databases on (`TEST_DATABASE_ADMIN_URL`; the `postgres` sidecar by default).

> Refer to [Environment Reference](./environment.md) for the ports, environment variables and configuration files used by both dev and test workflows.

## Install & Generate

`kc project` reads the manifest of the directory it runs in, so its verbs are
run from the repository root; `cexec` mirrors your working directory, so pnpm
commands are run wherever you are standing.

```bash
# The environment checks the repository out for you; start at its root
cd /work/IoTSupport

# The backend: uv sync, backend/.env and .env.test, the dev database
kc project setup backend

# The frontend: node dependencies and the Playwright Chromium
kc project setup frontend

# Generate the git-ignored API client and route tree
cd frontend
cexec modern-app pnpm generate:api:build   # src/lib/api/generated/ from the committed openapi-cache/openapi.json
cexec modern-app pnpm generate:routes      # src/routeTree.gen.ts
```

`pnpm build` (`kc project build frontend`) runs both generators first; `pnpm dev`, `pnpm check` and `pnpm playwright test` do not, so run them once on a fresh checkout, and `generate:routes` again whenever a route file is added, renamed or removed.

After a backend API change, refresh the committed spec and the client from `frontend/`:

```bash
cexec modern-app pnpm generate:api:with-backend
```

It runs `../scripts/regenerate-openapi.py --frontend`, which starts a backend on a free port, runs `pnpm generate:api` against it—rewriting `openapi-cache/openapi.json` and `src/lib/api/generated/`—and stops it. With the dev stack's backend running on 3101, `cexec modern-app pnpm generate:api` does the same against it. Commit the refreshed `openapi-cache/openapi.json` with the backend change: `backend/tests/test_openapi_cache.py` fails while it is stale. The generated client is never edited by hand.

## Run the App Locally

```bash
# From the repository root: the backend on :3101 and the frontend on :3100
scripts/dev.py
```

`scripts/dev.py` runs `Procfile.dev` under honcho in the `modern-app` container: the backend restarts on a code change, and the Vite dev server at `http://localhost:3100` proxies `/api`, the SSE stream included, to the backend. Each service logs to `logs/<service>.log`. Stop it with `^C`, or `scripts/dev.py stop` from another shell—never `kill`. The "Dev Services" task in `IoTSupport.code-workspace` runs the same command.

To run the frontend alone against a backend that is already up:

```bash
# from frontend/: the Vite dev server on :3100, proxying to BACKEND_URL (default http://localhost:3101)
cexec modern-app pnpm dev
```

The dev server runs with test mode off. `VITE_TEST_MODE=true` in its environment turns it on—test-event emitters, the `esptool-js` mock, no file watching; see [Environment Reference → Test Mode](./environment.md#test-mode). `scripts/testing-server.sh` serves the frontend the way a Playwright worker does; [Troubleshooting](./testing/troubleshooting.md#managed-services-fail-to-start) shows how to run it by hand.

### Useful Scripts

```bash
# from the repository root
kc project lint frontend    # pnpm check (ESLint, TypeScript, knip) and the architecture model check
kc project build frontend   # pnpm build: the generators, vite build, verify:build, then pnpm check

# from frontend/
cexec modern-app pnpm check     # ESLint, tsc -b --noEmit, knip
cexec modern-app pnpm preview   # Serve the production build in dist/ on :3100, with the dev server's proxy rules
```

## Validate Playwright Setup

```bash
# From the repository root: the suite, headless
kc project test frontend
```

Each Playwright worker starts its own backend and frontend on free ports, so the suite runs beside a dev stack on 3100/3101. Global setup first builds the run's seed database with the backend's test data. From the repository root, `cexec modern-app uv run run-suite --suite frontend` runs the suite the way CI does. See [CI & Execution](./testing/ci_and_execution.md) for full details.

## Next Steps

- Learn how the test suite is structured: [Testing Overview](./testing/index.md)
- Review instrumentation requirements: [Test Instrumentation](./architecture/test_instrumentation.md)
- Follow the workflow for new E2E coverage: [Add an E2E Test](./howto/add_e2e_test.md)
