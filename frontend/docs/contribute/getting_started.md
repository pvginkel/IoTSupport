# Getting Started

This guide walks new contributors through cloning the repository, installing dependencies, wiring up the backend, and validating the Playwright tooling locally. Follow it sequentially before branching into feature work or test authoring.

## Prerequisites

Node, pnpm and the Playwright system libraries all come from the `modern-app`
tool container, so there is nothing to install by hand — run pnpm through
`cexec modern-app`, or use the `kc project` verbs, which do it for you.

- **Backend service** running locally — it lives in `backend/` of this same repository (see [backend/README.md](../../../backend/README.md))

> Refer to [Environment Reference](./environment.md) for the full list of environment variables and port expectations used by both dev and test workflows.

## Clone & Install

`kc project` reads the manifest of the directory it runs in, so its verbs are
run from the repository root; `cexec` mirrors your working directory, so pnpm
commands are run wherever you are standing.

```bash
# The environment clones the repository for you; start at its root
cd /work/IoTSupport

# Install node dependencies and the Playwright browser
kc project setup frontend

# Generate the type-safe API client from the backend spec
cd frontend
cexec modern-app pnpm generate:api

# Optional: Generate route typing used by TanStack Router
cexec modern-app pnpm generate:routes
```

If the backend API spec changes, run `cexec modern-app pnpm generate:api` again to keep generated hooks and types in sync.

## Configure Environment

1. Copy `.env.example` to `.env` and adjust values as needed.
2. For Playwright, create `.env.test` if you need overrides (see [Environment Reference](./environment.md)).
3. Ensure the backend exposes `http://localhost:5100` when run in testing mode; the Playwright fixtures default to that URL.

## Run the App Locally

```bash
# Start the Vite dev server (http://localhost:3100)
cexec modern-app pnpm dev
```

To run the whole stack — backend, frontend and SSE gateway together — use the repo's dev runner instead: `scripts/dev.py` from the repository root, or the "Dev Services" task in the VS Code workspace.

The dev server uses your `.env` values and does **not** automatically enable test instrumentation. To exercise test-mode behaviors locally, run through the Playwright managed services via `scripts/testing-server.sh` or set `VITE_TEST_MODE=true` manually.

### Useful Scripts

```bash
# from the repository root
kc project lint frontend    # ESLint rules and TypeScript project check
kc project build frontend   # Production build

# from frontend/
cexec modern-app pnpm preview   # Preview the production build
```

## Validate Playwright Setup

```bash
# Both are run from the repository root.

# Install node dependencies and the Playwright browser binaries
kc project setup frontend

# Launch the managed services (frontend+backend) and run the suite headless
kc project test frontend
```

Playwright uses `scripts/testing-server.sh` to start the frontend on port **3100** and the backend on port **5100** when `PLAYWRIGHT_MANAGED_SERVICES` is not set to `false`. See [CI & Execution](./testing/ci_and_execution.md) for full details.

## Next Steps

- Learn how the test suite is structured: [Testing Overview](./testing/)
- Review instrumentation requirements: [Test Instrumentation](./architecture/test_instrumentation.md)
- Follow the workflow for new E2E coverage: [Add an E2E Test](./howto/add_e2e_test.md)
