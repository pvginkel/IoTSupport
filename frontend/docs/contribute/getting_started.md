# Getting Started

This guide walks new contributors through cloning the repository, installing dependencies, wiring up the backend, and validating the Playwright tooling locally. Follow it sequentially before branching into feature work or test authoring.

## Prerequisites

- **Node.js 18+** (matches Playwright requirements and Vite config)
- **pnpm** package manager (`npm install -g pnpm` if needed)
- **Backend service** from the companion repository running locally (see `../backend/README.md`)
- Optional: Docker, if you prefer containerized backend services

> Refer to [Environment Reference](./environment.md) for the full list of environment variables and port expectations used by both dev and test workflows.

## Clone & Install

```bash
# Clone both repos (frontend and backend)
git clone <repository-url>
cd frontend

# Install node dependencies
pnpm install

# Generate the type-safe API client from the backend spec
pnpm generate:api

# Optional: Generate route typing used by TanStack Router
pnpm generate:routes
```

If the backend API spec changes, run `pnpm generate:api` again to keep generated hooks and types in sync.

## Configure Environment

1. Copy `.env.example` to `.env` and adjust values as needed.
2. For Playwright, create `.env.test` if you need overrides (see [Environment Reference](./environment.md)).
3. Ensure the backend exposes `http://localhost:5100` when run in testing mode; the Playwright fixtures default to that URL.

## Run the App Locally

```bash
# Start the Vite dev server (defaults to http://localhost:3000)
pnpm dev
```

The dev server uses your `.env` values and does **not** automatically enable test instrumentation. To exercise test-mode behaviors locally, run through the Playwright managed services via `scripts/testing-server.sh` or set `VITE_TEST_MODE=true` manually.

### Useful Scripts

```bash
pnpm check         # ESLint rules and TypeScript project check
pnpm build         # Production build
pnpm preview       # Preview the production build
```

## Validate Playwright Setup

```bash
# Install Playwright browser binaries (one-time)
pnpm exec playwright install

# Launch the managed services (frontend+backend) and run the suite headless
pnpm playwright test
```

Playwright uses `scripts/testing-server.sh` to start the frontend on port **3100** and the backend on port **5100** when `PLAYWRIGHT_MANAGED_SERVICES` is not set to `false`. See [CI & Execution](./testing/ci_and_execution.md) for full details.

## Next Steps

- Learn how the test suite is structured: [Testing Overview](./testing/)
- Review instrumentation requirements: [Test Instrumentation](./architecture/test_instrumentation.md)
- Follow the workflow for new E2E coverage: [Add an E2E Test](./howto/add_e2e_test.md)
