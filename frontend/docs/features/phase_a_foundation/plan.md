# Phase A: Foundation & Test Infrastructure - Technical Plan

## 0) Research Log & Findings

### Discovery Work

Reviewed the following reference sources to inform this plan:

1. **ElectronicsInventory Frontend** (`/work/ElectronicsInventory/frontend`):
   - `package.json` - Dependencies, scripts, and tooling configuration
   - `vite.config.ts` - Vite setup with API proxy, test mode handling, and backend health checks
   - `src/main.tsx` - Entry point with test mode infrastructure setup
   - `src/App.tsx` - Router provider and correlation context
   - `src/routes/__root.tsx` - Root layout with QueryClient, Toast, sidebar, and app shell
   - `src/components/layout/sidebar.tsx` - Sidebar navigation component with test IDs
   - `src/lib/config/test-mode.ts` - Test mode detection guard
   - `tests/support/fixtures.ts` - Playwright fixtures with per-worker service isolation
   - `scripts/generate-api.js` - OpenAPI code generation pipeline

2. **Project Documentation**:
   - `docs/product_brief.md` - Product context and workflows
   - `docs/implementation_plan.md` - Phase A breakdown and file structure
   - `docs/playwright_implementation_plan.md` - Complete Playwright architecture
   - `docs/contribute/architecture/application_overview.md` - Architecture patterns

3. **Change Brief**:
   - `docs/features/phase_a_foundation/change_brief.md` - Phase A scope and success criteria

### Key Findings

1. **Proven Architecture**: ElectronicsInventory uses React 19 + TanStack Router/Query with generated OpenAPI hooks. IoT Support will replicate this stack with adaptations for simpler data model (JSON files vs SQLite).

2. **Per-Worker Service Isolation**: Playwright tests run completely isolated services per worker using `get-port` for dynamic allocation and temp directories for backend storage.

3. **Test Event System**: Test mode detection (`VITE_TEST_MODE=true`) gates instrumentation hooks that emit structured events to Playwright via `window.__playwright_emitTestEvent`.

4. **No SSE Gateway**: IoT Support omits SSE gateway (ElectronicsInventory has 3 services per worker; IoT Support has 2).

5. **API Generation Pipeline**: `scripts/generate-api.js` fetches OpenAPI spec and generates TypeScript types + TanStack Query hooks using `openapi-typescript`.

6. **Tailwind CSS 4**: Both projects use Tailwind CSS 4 via `@tailwindcss/vite` plugin (no separate `tailwind.config.ts` file).

### Conflicts Resolved

1. **Port Numbers**: ElectronicsInventory uses 3000/5000/3001. IoT Support uses 3200 (frontend) and 3201 (backend) per implementation plan.

2. **Branding**: ElectronicsInventory shows "Electronics" in sidebar. IoT Support shows "IoT Support" per change brief.

3. **Navigation Items**: ElectronicsInventory has 7 nav items. IoT Support starts with single "Device Configs" item per change brief.

4. **Backend Health Endpoint**: ElectronicsInventory uses `/api/health/readyz`. Need to verify IoT Support backend health endpoint (assume `/api/health` per Playwright plan).

---

## 1) Intent & Scope

### User Intent

Set up the complete IoT Support frontend foundation including project scaffolding, dark mode app shell with sidebar navigation, and full Playwright test infrastructure with per-worker service isolation. This phase establishes the testable foundation before any feature work begins.

### Prompt Quotes

From the change brief and implementation plan:
- "Initialize package.json with React 19, TypeScript, Vite, TanStack Router/Query, Tailwind CSS 4, Radix UI, Monaco Editor, openapi-fetch"
- "Create dark mode app shell with fixed sidebar"
- "Per-worker service isolation (backend + frontend per worker)"
- "Test event system (isTestMode, event emitter, event capture)"
- "`pnpm check` passes, `pnpm build` succeeds, `pnpm playwright test tests/smoke.spec.ts` passes"

### In Scope

- Complete `package.json` with all dependencies matching ElectronicsInventory patterns
- Vite configuration with API proxy to `localhost:3201`, dev server on port 3200, test mode handling
- TypeScript strict mode, ESLint, Prettier configuration
- API generation pipeline (`scripts/generate-api.js`) adapted from ElectronicsInventory
- Dark mode app shell with fixed sidebar showing "IoT Support" branding
- Single "Device Configs" navigation item in sidebar
- Basic routing: root redirects to `/devices`, placeholder device list page
- Test IDs on all shell components for Playwright selectors
- Complete Playwright infrastructure:
  - Per-worker service manager (backend + frontend)
  - Service startup with health check polling
  - Test event system (detection, emission, capture)
  - API factories for config CRUD
  - Page objects for device interactions
  - Log collectors with failure attachments
  - Smoke tests validating setup

### Out of Scope

- Feature implementation (device list, editor, delete) - deferred to Phase B
- Toast system - deferred to Phase B
- Error handling utilities - deferred to Phase B
- Monaco Editor integration - deferred to Phase B
- Form components - deferred to Phase B
- SSE gateway (not needed for IoT Support)
- Production deployment configuration

### Assumptions / Constraints

1. **Backend API Contract**: Backend exposes OpenAPI spec at `http://localhost:3201/api/docs` and health endpoint at `/api/health`.
2. **Backend Storage**: Backend accepts `ESP32_CONFIGS_DIR` environment variable pointing to JSON file storage directory.
3. **ElectronicsInventory as Reference**: All architectural patterns mirror ElectronicsInventory unless explicitly simplified.
4. **Dark Mode Only**: No light mode toggle in Phase A (app shell is dark by default).
5. **Desktop First**: Responsive mobile behavior deferred; sidebar is always visible on desktop.
6. **Test Mode Tree-Shaking**: Production builds exclude test instrumentation via Vite `define` config.

---

## 1a) User Requirements Checklist

- [ ] Project initializes with pnpm and all dependencies install successfully
- [ ] Vite dev server runs on port 3200 with API proxy to localhost:3201
- [ ] Dark mode app shell displays with "IoT Support" branding
- [ ] Sidebar shows "Device Configs" navigation item with active state
- [ ] Root route redirects to /devices
- [ ] /devices route shows placeholder content
- [ ] Test mode detection works (isTestMode returns true when VITE_TEST_MODE=true)
- [ ] Playwright per-worker service isolation starts backend and frontend
- [ ] Backend health check polling works
- [ ] Frontend readiness polling works
- [ ] API factories can create and delete configs via backend API
- [ ] Test event bridge captures events emitted from frontend
- [ ] Smoke tests pass: frontend loads, backend health responds, app shell visible
- [ ] `pnpm check` passes (lint + typecheck)
- [ ] `pnpm build` succeeds

---

## 2) Affected Areas & File Map

### A1. Project Scaffolding

#### `package.json`
- **Why**: Define dependencies, scripts, and package manager version.
- **Evidence**: Copied from `/work/ElectronicsInventory/frontend/package.json:1-65`. IoT Support adds `@monaco-editor/react` for editor, removes SSE-related packages.

#### `vite.config.ts`
- **Why**: Configure Vite with React plugin, Tailwind plugin, API proxy, test mode handling.
- **Evidence**: Adapted from `/work/ElectronicsInventory/frontend/vite.config.ts:1-156`. Changes: proxy target to `localhost:3201`, dev server port to 3200, remove SSE gateway proxy.

#### `tsconfig.json` and `tsconfig.app.json`
- **Why**: TypeScript strict mode configuration with path aliases.
- **Evidence**: Standard React 19 + Vite setup. Pattern from ElectronicsInventory (inferred from imports like `@/lib/*`).

#### `eslint.config.js`
- **Why**: Linting rules for TypeScript and React hooks.
- **Evidence**: ElectronicsInventory uses ESLint 9 flat config with `@eslint/js`, `typescript-eslint`, and React plugins (from `package.json:46-57`).

#### `.prettierrc`
- **Why**: Code formatting consistency.
- **Evidence**: Standard Prettier config (2-space indent, single quotes, trailing commas).

#### `scripts/generate-api.js`
- **Why**: Fetch OpenAPI spec from backend and generate TypeScript types + TanStack Query hooks.
- **Evidence**: Copied from `/work/ElectronicsInventory/frontend/scripts/generate-api.js:1-100`. Adapts endpoint to `http://localhost:3201/api/docs`.

### A2. Core Application Setup

#### `src/main.tsx`
- **Why**: Application entry point with test mode infrastructure setup.
- **Evidence**: Pattern from `/work/ElectronicsInventory/frontend/src/main.tsx:1-26`. Sets up console policy and error instrumentation in test mode.

#### `src/App.tsx`
- **Why**: Router provider setup with test mode instrumentation.
- **Evidence**: Pattern from `/work/ElectronicsInventory/frontend/src/App.tsx:1-32`. Wraps app with TanStack Router and correlation context.

#### `src/index.css`
- **Why**: Global Tailwind CSS imports and dark mode base styles.
- **Evidence**: Standard Tailwind CSS 4 setup with `@import "tailwindcss"` directive.

#### `src/lib/query-client.ts`
- **Why**: Centralized TanStack Query client with default error handling.
- **Evidence**: Pattern from ElectronicsInventory (referenced in `__root.tsx:9`). Creates QueryClient with retry logic and error handling.

#### `src/lib/config/test-mode.ts`
- **Why**: Test mode detection guard for instrumentation.
- **Evidence**: Copied verbatim from `/work/ElectronicsInventory/frontend/src/lib/config/test-mode.ts:1-16`.

### A3. App Shell Components

#### `src/routes/__root.tsx`
- **Why**: Root layout with QueryClientProvider, ToastProvider placeholder, app shell frame.
- **Evidence**: Adapted from `/work/ElectronicsInventory/frontend/src/routes/__root.tsx:1-128`. Simplifies to single sidebar without SSE/Deployment providers (Phase A).

#### `src/components/layout/sidebar.tsx`
- **Why**: Navigation sidebar with "IoT Support" branding and "Device Configs" item.
- **Evidence**: Adapted from `/work/ElectronicsInventory/frontend/src/components/layout/sidebar.tsx:1-100`. Reduces navigation items to single entry: `{ to: '/devices', label: 'Device Configs', icon: Settings, testId: 'devices' }`.

#### `src/routes/index.tsx`
- **Why**: Root route that redirects to `/devices`.
- **Evidence**: Standard TanStack Router redirect using `beforeLoad` hook with `throw redirect({ to: '/devices' })`.

#### `src/routes/devices/index.tsx`
- **Why**: Placeholder device list page showing "Device Configs" heading.
- **Evidence**: New route file. Displays simple heading with test ID `device-list-placeholder`.

### A4. Routing Setup

#### `src/routeTree.gen.ts`
- **Why**: Generated route tree from TanStack Router CLI.
- **Evidence**: Auto-generated by `pnpm generate:routes` script (from `package.json:14`).

### A5. API Generation

#### `src/lib/api/generated/types.ts`
- **Why**: TypeScript types generated from OpenAPI spec.
- **Evidence**: Generated by `scripts/generate-api.js` using `openapi-typescript`.

#### `src/lib/api/generated/client.ts`
- **Why**: openapi-fetch client configured with base URL.
- **Evidence**: Generated by `scripts/generate-api.js` (from `/work/ElectronicsInventory/frontend/scripts/generate-api.js:52-69`).

#### `src/lib/api/generated/hooks.ts`
- **Why**: TanStack Query hooks for all API endpoints.
- **Evidence**: Generated by `scripts/generate-api.js` (from `/work/ElectronicsInventory/frontend/scripts/generate-api.js:75-100`).

### A6. Test Infrastructure - Configuration

#### `playwright.config.ts`
- **Why**: Playwright configuration with per-worker isolation and reporter setup.
- **Evidence**: Pattern from `docs/playwright_implementation_plan.md:48-83`. Configures workers, retries, global setup, base URL.

#### `.env.test`
- **Why**: Test environment configuration for managed services mode.
- **Evidence**: From `docs/playwright_implementation_plan.md:86-95`. Sets `PLAYWRIGHT_MANAGED_SERVICES=true`.

#### `tests/support/global-setup.ts`
- **Why**: Load test environment and validate managed services mode.
- **Evidence**: From `docs/playwright_implementation_plan.md:100-119`. Loads `.env.test` and validates configuration.

### A7. Test Infrastructure - Service Management

#### `scripts/testing-server.sh`
- **Why**: Frontend test server script that accepts `--host` and `--port` arguments.
- **Evidence**: From `docs/playwright_implementation_plan.md:203-236`. Sets `VITE_TEST_MODE=true` and runs Vite with isolated cache.

#### `tests/support/process/servers.ts`
- **Why**: Start backend and frontend services with health check polling.
- **Evidence**: From `docs/playwright_implementation_plan.md:241-295`. Spawns backend/frontend processes and waits for health endpoints.

#### `tests/support/process/log-collector.ts`
- **Why**: Collect service logs and attach to test results on failure.
- **Evidence**: From `docs/playwright_implementation_plan.md:175-191`. Buffers stdout/stderr and provides attachment API.

### A8. Test Infrastructure - Fixtures

#### `tests/support/fixtures.ts`
- **Why**: Custom Playwright fixtures for service manager, API client, page objects, test events.
- **Evidence**: Pattern from `/work/ElectronicsInventory/frontend/tests/support/fixtures.ts:1-250` and `docs/playwright_implementation_plan.md:124-154`. Implements worker-scoped `_serviceManager` and test-scoped fixtures.

### A9. Test Infrastructure - Test Event System

#### `src/types/test-events.ts`
- **Why**: TypeScript definitions for test event payloads.
- **Evidence**: From `docs/playwright_implementation_plan.md:317-353`. Defines `TestEventKind`, `ListLoadingEvent`, `FormEvent`, etc.

#### `src/lib/test/event-emitter.ts`
- **Why**: Emit test events through `window.__playwright_emitTestEvent`.
- **Evidence**: From `docs/playwright_implementation_plan.md:366-387`. Guards emission behind `isTestMode()` check.

#### `tests/support/helpers/test-events.ts`
- **Why**: Playwright-side test event capture buffer with wait helpers.
- **Evidence**: From `docs/playwright_implementation_plan.md:391-434`. Implements `TestEventCapture` class with `waitForEvent` method.

#### `src/lib/test/console-policy.ts`
- **Why**: Setup console error/warning policy in test mode.
- **Evidence**: Referenced in `/work/ElectronicsInventory/frontend/src/main.tsx:6`. Ensures console errors are tracked.

#### `src/lib/test/error-instrumentation.ts`
- **Why**: Setup global error instrumentation in test mode.
- **Evidence**: Referenced in `/work/ElectronicsInventory/frontend/src/main.tsx:7`. Tracks unhandled errors.

#### `src/lib/test/router-instrumentation.ts`
- **Why**: Setup router navigation instrumentation in test mode.
- **Evidence**: Referenced in `/work/ElectronicsInventory/frontend/src/App.tsx:6`. Emits route change events.

### A10. Test Infrastructure - API Factories

#### `tests/api/client.ts`
- **Why**: OpenAPI client wrapper for test data creation.
- **Evidence**: From `docs/playwright_implementation_plan.md:438-451`. Creates client with configurable base URL.

#### `tests/api/factories/config-factory.ts`
- **Why**: Factory for creating/deleting device configs via API.
- **Evidence**: From `docs/playwright_implementation_plan.md:454-502`. Implements `randomMacAddress()`, `create()`, `createMany()`, `delete()`.

#### `tests/api/index.ts`
- **Why**: Export test data bundle for fixtures.
- **Evidence**: From `docs/playwright_implementation_plan.md:505-521`. Exports `createTestDataBundle()` with `configs` factory.

### A11. Test Infrastructure - Page Objects

#### `tests/support/page-objects/base-page.ts`
- **Why**: Base class for page objects with common navigation helpers.
- **Evidence**: From `docs/playwright_implementation_plan.md:529-542`. Provides `goto()` and `getByTestId()` methods.

#### `tests/support/page-objects/devices-page.ts`
- **Why**: Page object for device list interactions.
- **Evidence**: From `docs/playwright_implementation_plan.md:545-592`. Implements `gotoList()`, `waitForListLoaded()`, `getDeviceRow()`, etc.

#### `tests/support/page-objects/device-editor-page.ts`
- **Why**: Page object for device editor interactions (prepared for Phase B).
- **Evidence**: From `docs/playwright_implementation_plan.md:595-644`. Stub implementation for Phase A; full implementation in Phase B.

### A12. Test Infrastructure - Smoke Tests

#### `tests/smoke.spec.ts`
- **Why**: Validate that services start, frontend loads, and app shell displays.
- **Evidence**: From `docs/playwright_implementation_plan.md:700-723`. Three tests: frontend loads, backend health responds, device list loads (empty state).

### A13. Instrumentation Hooks (Stubs for Phase A)

#### `src/lib/test/useListLoadingInstrumentation.ts`
- **Why**: Hook for emitting list loading events (stub for Phase A).
- **Evidence**: From `docs/playwright_implementation_plan.md:649-673`. Full implementation in Phase B when device list is built.

#### `src/lib/test/useFormInstrumentation.ts`
- **Why**: Helpers for emitting form events (stub for Phase A).
- **Evidence**: From `docs/playwright_implementation_plan.md:676-696`. Full implementation in Phase B when forms are built.

---

## 3) Data Model / Contracts

### Device Config Model

- **Entity**: Device configuration stored as JSON file on backend.
- **Shape** (backend snake_case):
  ```json
  {
    "mac_address": "aa-bb-cc-dd-ee-ff",
    "content": {
      "deviceName": "Test Device",
      "deviceEntityId": "test_device_123",
      "enableOTA": false
    }
  }
  ```
- **Mapping**: Generated API hooks use snake_case. Frontend domain models (Phase B) will convert to camelCase via custom hooks.
- **Evidence**: Backend API contract (assumed from Playwright plan). Generated types from `src/lib/api/generated/types.ts` will match OpenAPI spec.

### TanStack Query Cache Keys

- **GET /api/configs**: Query key `['configs']` (list all configs)
- **GET /api/configs/{mac_address}**: Query key `['configs', macAddress]` (single config)
- **PUT /api/configs/{mac_address}**: Mutation invalidates `['configs']` query
- **DELETE /api/configs/{mac_address}**: Mutation invalidates `['configs']` query
- **Evidence**: Standard TanStack Query patterns from generated hooks (`scripts/generate-api.js`).

### Test Event Payloads

- **ListLoadingEvent**:
  ```typescript
  {
    kind: 'list_loading',
    phase: 'loading' | 'ready' | 'error',
    listId: 'device-list',
    itemCount?: number,
    timestamp: number
  }
  ```
- **FormEvent** (Phase B):
  ```typescript
  {
    kind: 'form',
    action: 'open' | 'submit' | 'success' | 'error',
    formId: 'device-editor',
    error?: string,
    timestamp: number
  }
  ```
- **Evidence**: From `src/types/test-events.ts` (pattern from `docs/playwright_implementation_plan.md:317-353`).

---

## 4) API / Integration Surface

### Backend Health Check

- **Surface**: `GET /api/health`
- **Inputs**: None
- **Outputs**: HTTP 200 status (backend is ready)
- **Errors**: Timeout if backend not responding within 30 seconds
- **Evidence**: Health check polling in `tests/support/process/servers.ts` (from Playwright plan:300-313).

### OpenAPI Spec Fetch

- **Surface**: `GET /api/docs` (OpenAPI JSON spec)
- **Inputs**: None
- **Outputs**: OpenAPI 3.x specification JSON
- **Errors**: Script exits if spec fetch fails during `pnpm generate:api`
- **Evidence**: `scripts/generate-api.js` fetches spec from backend (pattern from ElectronicsInventory).

### Config CRUD (for test factories)

- **Surface**: `PUT /api/configs/{mac_address}`
- **Inputs**: `{ content: Record<string, unknown> }`
- **Outputs**: Created/updated config
- **Errors**: 400 for invalid MAC address or malformed content
- **Evidence**: `tests/api/factories/config-factory.ts` (from Playwright plan:474-490).

- **Surface**: `DELETE /api/configs/{mac_address}`
- **Inputs**: Path parameter `mac_address`
- **Outputs**: HTTP 204 (no content)
- **Errors**: 404 if config not found
- **Evidence**: `tests/api/factories/config-factory.ts` (from Playwright plan:497-500).

---

## 5) Algorithms & UI Flows

### App Shell Initialization Flow

- **Flow**: Application startup and shell rendering
- **Steps**:
  1. `main.tsx` detects test mode and sets up console policy + error instrumentation
  2. React renders `<App />` which creates TanStack Router
  3. Router mounts `__root.tsx` layout
  4. `__root.tsx` renders QueryClientProvider, ToastProvider placeholder, and AppShellFrame
  5. AppShellFrame renders Sidebar with "Device Configs" navigation item
  6. Router matches root path `/` and triggers redirect to `/devices`
  7. `/devices` route loads placeholder content with "Device Configs" heading
  8. Sidebar highlights "Device Configs" as active (via TanStack Router `activeProps`)
- **States / Transitions**:
  - Test mode: `VITE_TEST_MODE=true` → instrumentation enabled
  - Routing: Root `/` → Redirect → `/devices` → Placeholder content
- **Hotspots**: Router instrumentation emits route change events in test mode
- **Evidence**: Pattern from ElectronicsInventory `__root.tsx` and `sidebar.tsx`.

### Service Startup Flow (Playwright Worker)

- **Flow**: Per-worker service isolation setup
- **Steps**:
  1. Playwright worker starts, allocates unique ports via `get-port`
  2. Create temporary config directory: `/tmp/iot-support-worker-{N}-{random}/configs`
  3. Start backend service with `ESP32_CONFIGS_DIR` pointing to temp dir
  4. Poll backend health endpoint (`GET /api/health`) until 200 response (30s timeout)
  5. Start frontend service with `BACKEND_URL` pointing to worker's backend
  6. Poll frontend root (`GET /`) until 200 response (90s timeout)
  7. Attach log collectors to backend/frontend stdout/stderr
  8. Return service URLs to test fixtures
- **States / Transitions**:
  - Starting → Backend health poll → Backend ready → Frontend poll → Frontend ready → Services ready
- **Hotspots**: Health check timeouts can cause test failures if backend/frontend slow to start
- **Evidence**: `tests/support/fixtures.ts` service manager implementation (from Playwright plan:53-62, 241-295).

### Test Event Emission Flow

- **Flow**: Frontend emits test events that Playwright captures
- **Steps**:
  1. Frontend calls `emitTestEvent({ kind: 'list_loading', phase: 'loading', listId: 'device-list' })`
  2. `emitTestEvent` checks `isTestMode()` guard; returns early if false
  3. If test mode, adds `timestamp` and calls `window.__playwright_emitTestEvent(payload)`
  4. Playwright page fixture exposes `__playwright_emitTestEvent` function via `page.exposeFunction`
  5. Exposed function pushes event to `TestEventCapture` buffer
  6. Test calls `testEvents.waitForEvent('list_loading', filter, timeout)` to assert event
  7. `waitForEvent` polls buffer every 100ms until matching event found or timeout
- **States / Transitions**:
  - Event emitted → Buffered → Awaited → Matched → Test continues
- **Hotspots**: Event buffer overflow (500 events max) throws error
- **Evidence**: `src/lib/test/event-emitter.ts` and `tests/support/helpers/test-events.ts` (from Playwright plan:366-434).

---

## 6) Derived State & Invariants

### Active Navigation Item

- **Derived Value**: Active sidebar navigation item based on current route
- **Source**: TanStack Router `useMatch()` hook provides current route path
- **Writes / Cleanup**: Sidebar `<Link>` components apply `active` class when route matches
- **Guards**: None (router handles active state automatically)
- **Invariant**: Exactly one navigation item must be active when route is `/devices`
- **Evidence**: ElectronicsInventory sidebar pattern (`/work/ElectronicsInventory/frontend/src/components/layout/sidebar.tsx:81-86`).

### Test Mode Status

- **Derived Value**: `isTestMode()` boolean based on `VITE_TEST_MODE` environment variable
- **Source**: Vite `import.meta.env.VITE_TEST_MODE` compiled at build time
- **Writes / Cleanup**: Test mode gates all instrumentation hook calls (no writes)
- **Guards**: Production builds force `VITE_TEST_MODE` to `'false'` for tree-shaking
- **Invariant**: Test instrumentation code must never execute in production builds
- **Evidence**: `vite.config.ts` `define` block (from ElectronicsInventory:139-143) and `test-mode.ts:10`.

### Service URLs Per Worker

- **Derived Value**: Backend and frontend URLs dynamically allocated per worker
- **Source**: `get-port` package provides unique ports, combined with `127.0.0.1` host
- **Writes / Cleanup**: Service manager stores URLs and disposes services on worker teardown
- **Guards**: Port allocation excludes already-used ports to prevent conflicts
- **Invariant**: Each worker must have isolated backend/frontend URLs; no cross-worker access
- **Evidence**: Playwright fixtures service manager (from Playwright plan:53-62, 160-165).

---

## 7) State Consistency & Async Coordination

### TanStack Query Cache Invalidation

- **Source of Truth**: TanStack Query cache for server state (configs list)
- **Coordination**: Mutations invalidate query cache after successful API calls
- **Async Safeguards**: Query client default config includes retry logic and stale time settings
- **Instrumentation**: None in Phase A (list loading instrumentation added in Phase B)
- **Evidence**: `src/lib/query-client.ts` setup pattern from ElectronicsInventory (`__root.tsx:9`).

### Test Event Buffer Synchronization

- **Source of Truth**: `TestEventCapture` buffer stores events in order of emission
- **Coordination**: Page fixture exposes event emitter before test navigation begins
- **Async Safeguards**: Buffer overflow throws error if 500 events exceeded
- **Instrumentation**: All test events include `timestamp` for debugging race conditions
- **Evidence**: `tests/support/helpers/test-events.ts` implementation (from Playwright plan:391-434).

### Service Health Polling

- **Source of Truth**: HTTP health endpoints determine service readiness
- **Coordination**: Sequential startup (backend first, then frontend)
- **Async Safeguards**: Health check polling with 200ms intervals and configurable timeouts (30s backend, 90s frontend)
- **Instrumentation**: Log collectors capture service stdout/stderr for debugging
- **Evidence**: `tests/support/process/servers.ts` startup flow (from Playwright plan:300-313).

---

## 8) Errors & Edge Cases

### Backend Unreachable During Dev

- **Failure**: Vite proxy cannot reach backend at `localhost:3201`
- **Surface**: Vite dev server startup
- **Handling**: `backendProxyStatusPlugin` logs warning but allows dev server to start
- **Guardrails**: Plugin probes `/api/health` endpoint with 2s timeout; warns if unreachable
- **Evidence**: ElectronicsInventory `vite.config.ts:43-84`.

### OpenAPI Spec Fetch Failure

- **Failure**: `scripts/generate-api.js` cannot fetch spec from backend
- **Surface**: `pnpm generate:api` script
- **Handling**: Script exits with error message; developer must start backend
- **Guardrails**: Fetch has timeout; clear error message directs user to start backend
- **Evidence**: ElectronicsInventory `scripts/generate-api.js` fetch logic (referenced at line 1-100).

### Playwright Service Startup Timeout

- **Failure**: Backend or frontend fails to respond to health check within timeout
- **Surface**: Playwright worker fixture setup
- **Handling**: Worker throws error; logs attached to test results for debugging
- **Guardrails**: Health check polling with clear timeout errors; log collectors capture service stderr
- **Evidence**: `tests/support/process/servers.ts` (from Playwright plan:300-313).

### Test Event Buffer Overflow

- **Failure**: Frontend emits more than 500 test events during a single test
- **Surface**: `TestEventCapture` buffer
- **Handling**: Throws error to prevent memory leak
- **Guardrails**: Hard cap at 500 events; error message indicates overflow
- **Evidence**: `tests/support/helpers/test-events.ts` (from Playwright plan:400-407).

### Port Allocation Conflict

- **Failure**: `get-port` cannot allocate unique port for worker services
- **Surface**: Worker fixture setup
- **Handling**: Port allocation excludes already-used ports; retries until available port found
- **Guardrails**: `get-port` library handles retry logic; unlikely to fail with 2 workers
- **Evidence**: Playwright plan service startup (from line 160-165).

---

## 9) Observability / Instrumentation

### Test Event Bridge

- **Signal**: Test events emitted via `window.__playwright_emitTestEvent`
- **Type**: Instrumentation event
- **Trigger**: Frontend components call `emitTestEvent()` when `isTestMode()` is true
- **Labels / Fields**: `kind`, `timestamp`, event-specific fields (e.g., `phase`, `listId`)
- **Consumer**: Playwright tests call `testEvents.waitForEvent()` to assert behavior
- **Evidence**: `src/lib/test/event-emitter.ts` and `tests/support/helpers/test-events.ts`.

### Service Log Collectors

- **Signal**: Backend and frontend stdout/stderr streams
- **Type**: Console log
- **Trigger**: Service processes emit logs during startup and operation
- **Labels / Fields**: Worker index, service name (backend/frontend)
- **Consumer**: Playwright attaches logs to test results on failure; `PLAYWRIGHT_*_LOG_STREAM=true` streams logs in real-time
- **Evidence**: `tests/support/process/log-collector.ts` (from Playwright plan:175-191).

### Router Instrumentation

- **Signal**: Route change events
- **Type**: Instrumentation event
- **Trigger**: TanStack Router navigation emits route change via `setupRouterInstrumentation()`
- **Labels / Fields**: `kind: 'route'`, `from`, `to`, `timestamp`
- **Consumer**: Tests can assert navigation occurred (Phase B)
- **Evidence**: `src/lib/test/router-instrumentation.ts` (referenced in App.tsx).

### Console Policy

- **Signal**: Console errors and warnings
- **Type**: Console log
- **Trigger**: Global console interceptors in test mode
- **Labels / Fields**: Error message, stack trace
- **Consumer**: Playwright page fixture throws on unexpected console errors
- **Evidence**: `src/lib/test/console-policy.ts` and page fixture console listener (from ElectronicsInventory:191-225).

### Data Test IDs

- **Signal**: `data-testid` attributes on interactive elements
- **Type**: DOM attribute
- **Trigger**: Component render
- **Labels / Fields**: Hierarchical test IDs (e.g., `app-shell.sidebar`, `app-shell.sidebar.link.devices`)
- **Consumer**: Playwright selectors via `page.getByTestId()`
- **Evidence**: Sidebar component (adapted from ElectronicsInventory:39-78).

---

## 10) Lifecycle & Background Work

### Router Setup on Mount

- **Hook / Effect**: Router instrumentation setup in `App.tsx`
- **Trigger Cadence**: Once on application mount
- **Responsibilities**: Attach router navigation listeners when `isTestMode()` is true
- **Cleanup**: Router unmount (never happens in SPA)
- **Evidence**: `src/App.tsx` pattern from ElectronicsInventory (line 13-15).

### QueryClient Setup on Mount

- **Hook / Effect**: `setToastFunction` effect in `__root.tsx` QuerySetup component
- **Trigger Cadence**: Once on root layout mount (Phase B - stubbed in Phase A)
- **Responsibilities**: Register toast handler for React Query global error handling
- **Cleanup**: None (toast handler remains for app lifetime)
- **Evidence**: ElectronicsInventory `__root.tsx:16-30`.

### Service Manager Lifecycle (Playwright)

- **Hook / Effect**: Worker-scoped fixture `_serviceManager`
- **Trigger Cadence**: Once per worker at worker startup
- **Responsibilities**: Start backend + frontend services, allocate ports, create temp dirs, poll health
- **Cleanup**: `disposeServices()` kills processes, removes temp directories on worker teardown
- **Evidence**: Playwright fixtures (from Playwright plan:53-62).

### Log Collector Attachment (Playwright)

- **Hook / Effect**: Test-scoped fixtures `backendLogs`, `frontendLogs`
- **Trigger Cadence**: Once per test
- **Responsibilities**: Attach log collectors to test results; stream logs if `PLAYWRIGHT_*_LOG_STREAM=true`
- **Cleanup**: `attachment.stop()` detaches collectors on test teardown
- **Evidence**: ElectronicsInventory fixtures (line 115-149).

---

## 11) Security & Permissions

Not applicable for Phase A. Backend does not implement authentication or authorization. All API endpoints are public. Security concerns deferred to Phase B or later phases.

---

## 12) UX / UI Impact

### App Shell Layout

- **Entry Point**: All routes display within app shell frame
- **Change**: New dark mode app shell with fixed sidebar
- **User Interaction**: User sees "IoT Support" branding in sidebar and "Device Configs" navigation item
- **Dependencies**: TanStack Router for layout wrapping, Tailwind CSS for dark mode styles
- **Evidence**: `src/routes/__root.tsx` and `src/components/layout/sidebar.tsx`.

### Navigation Sidebar

- **Entry Point**: Persistent sidebar on left side of screen
- **Change**: Single navigation item ("Device Configs") with active state highlighting
- **User Interaction**: Clicking "Device Configs" navigates to `/devices`; active item highlighted
- **Dependencies**: TanStack Router `<Link>` component with `activeProps`
- **Evidence**: Sidebar component pattern from ElectronicsInventory.

### Placeholder Device List Page

- **Entry Point**: Route `/devices`
- **Change**: Simple heading "Device Configs" with test ID
- **User Interaction**: User sees placeholder content (no list, no data)
- **Dependencies**: TanStack Router route file
- **Evidence**: New route file `src/routes/devices/index.tsx`.

---

## 13) Deterministic Test Plan

### Smoke Test: Frontend Loads

- **Surface**: Application root
- **Scenarios**:
  - Given services are running
  - When test navigates to frontend URL
  - Then page title contains "IoT Support"
  - And sidebar is visible with test ID `app-shell.sidebar`
- **Instrumentation / Hooks**: `data-testid="app-shell.sidebar"` on sidebar component
- **Gaps**: None
- **Evidence**: `tests/smoke.spec.ts` (from Playwright plan:706-709).

### Smoke Test: Backend Health Responds

- **Surface**: Backend health endpoint
- **Scenarios**:
  - Given backend service is running
  - When test fetches `{backendUrl}/api/health`
  - Then response status is 200
- **Instrumentation / Hooks**: None (direct HTTP fetch in test)
- **Gaps**: None
- **Evidence**: `tests/smoke.spec.ts` (from Playwright plan:711-714).

### Smoke Test: Device List Placeholder Loads

- **Surface**: Device list page
- **Scenarios**:
  - Given frontend is running
  - When test navigates to `/devices` via page object
  - Then placeholder content is visible
  - And page does not emit list loading events (no data fetching in Phase A)
- **Instrumentation / Hooks**: `data-testid="device-list-placeholder"` on placeholder content
- **Gaps**: Full list loading test deferred to Phase B (requires API integration)
- **Evidence**: `tests/smoke.spec.ts` and `tests/support/page-objects/devices-page.ts`.

### Unit Test: Test Mode Detection

- **Surface**: `isTestMode()` function
- **Scenarios**:
  - Given `VITE_TEST_MODE=true` environment variable
  - When test mode function is called
  - Then it returns `true`
  - And instrumentation hooks emit events
- **Instrumentation / Hooks**: Manual verification via smoke tests
- **Gaps**: No dedicated unit test for `isTestMode()` (verified via integration)
- **Evidence**: `src/lib/config/test-mode.ts`.

### Integration Test: Service Isolation

- **Surface**: Playwright worker fixtures
- **Scenarios**:
  - Given multiple workers running in parallel
  - When each worker starts services
  - Then each worker has unique backend URL
  - And each worker has unique frontend URL
  - And workers do not interfere with each other
- **Instrumentation / Hooks**: Service URLs logged to test metadata
- **Gaps**: None
- **Evidence**: Worker fixture implementation ensures port isolation.

### Integration Test: API Factory Creates Config

- **Surface**: `ConfigTestFactory.create()`
- **Scenarios**:
  - Given backend service is running
  - When test calls `testData.configs.create({ macAddress: 'aa-bb-cc-dd-ee-ff', content: {...} })`
  - Then config is created via `PUT /api/configs/aa-bb-cc-dd-ee-ff`
  - And backend stores config in worker's temp directory
  - And factory returns created config object
- **Instrumentation / Hooks**: API client logs requests (test mode only)
- **Gaps**: None (verified in smoke tests or Phase B tests)
- **Evidence**: `tests/api/factories/config-factory.ts`.

### Integration Test: Test Event Capture

- **Surface**: Test event bridge
- **Scenarios**:
  - Given page fixture with test event bridge
  - When frontend emits test event via `emitTestEvent({ kind: 'list_loading', phase: 'loading', listId: 'test' })`
  - Then test can await event via `testEvents.waitForEvent('list_loading')`
  - And event payload matches emitted data
- **Instrumentation / Hooks**: `window.__playwright_emitTestEvent` exposed function
- **Gaps**: None
- **Evidence**: `tests/support/helpers/test-events.ts`.

---

## 14) Implementation Slices

### Slice 1: Project Scaffolding & Configuration

- **Goal**: Initialize project with dependencies and build tooling
- **Touches**:
  - `package.json`, `pnpm-lock.yaml`
  - `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`
  - `eslint.config.js`, `.prettierrc`
  - `src/index.css`, `public/` directory
- **Dependencies**: None (first slice)
- **Verification**: `pnpm install` succeeds, `pnpm check` passes (with placeholder files)

### Slice 2: API Generation Pipeline

- **Goal**: Set up OpenAPI code generation
- **Touches**:
  - `scripts/generate-api.js`
  - `scripts/fetch-openapi.js` (helper for caching)
  - `.gitignore` (ignore `openapi-cache/`)
- **Dependencies**: Backend running on `localhost:3201` with `/api/docs` endpoint
- **Verification**: `pnpm generate:api` succeeds, `src/lib/api/generated/` contains types and hooks

### Slice 3: Core Application & App Shell

- **Goal**: Render dark mode app shell with sidebar
- **Touches**:
  - `src/main.tsx`, `src/App.tsx`
  - `src/routes/__root.tsx`
  - `src/components/layout/sidebar.tsx`
  - `src/lib/query-client.ts`
  - `src/lib/config/test-mode.ts`
  - Placeholder toast context (stub)
- **Dependencies**: Slice 1 and 2 complete
- **Verification**: `pnpm dev` starts, navigating to `localhost:3200` shows sidebar

### Slice 4: Basic Routing

- **Goal**: Set up TanStack Router with redirect and placeholder page
- **Touches**:
  - `src/routes/index.tsx` (root redirect)
  - `src/routes/devices/index.tsx` (placeholder page)
  - `pnpm generate:routes` script integration
- **Dependencies**: Slice 3 complete
- **Verification**: Navigating to `/` redirects to `/devices`, placeholder content visible

### Slice 5: Test Infrastructure - Service Management

- **Goal**: Per-worker backend and frontend services with health checks
- **Touches**:
  - `scripts/testing-server.sh`
  - `tests/support/process/servers.ts`
  - `tests/support/process/log-collector.ts`
  - `.env.test`, `playwright.config.ts`, `tests/support/global-setup.ts`
- **Dependencies**: Slice 1-4 complete, backend testing script exists
- **Verification**: Manually run startup script; health checks succeed

### Slice 6: Test Infrastructure - Fixtures

- **Goal**: Playwright fixtures with service manager, API client, page objects
- **Touches**:
  - `tests/support/fixtures.ts`
  - `tests/api/client.ts`, `tests/api/index.ts`
  - `tests/support/page-objects/base-page.ts`
  - `tests/support/page-objects/devices-page.ts`
  - `tests/support/page-objects/device-editor-page.ts` (stub)
- **Dependencies**: Slice 5 complete
- **Verification**: Smoke test skeleton runs (no assertions yet)

### Slice 7: Test Infrastructure - Test Events

- **Goal**: Test event emission and capture system
- **Touches**:
  - `src/types/test-events.ts`
  - `src/lib/test/event-emitter.ts`
  - `src/lib/test/console-policy.ts`
  - `src/lib/test/error-instrumentation.ts`
  - `src/lib/test/router-instrumentation.ts`
  - `tests/support/helpers/test-events.ts`
  - Update `src/main.tsx` and `src/App.tsx` to setup instrumentation
- **Dependencies**: Slice 6 complete
- **Verification**: Test can emit and capture events

### Slice 8: Test Infrastructure - API Factories

- **Goal**: Config creation/deletion via API for test data
- **Touches**:
  - `tests/api/factories/config-factory.ts`
  - Update `tests/api/index.ts` to export `createTestDataBundle`
- **Dependencies**: Slice 6 complete, backend API available
- **Verification**: Factory can create and delete config via API

### Slice 9: Smoke Tests

- **Goal**: End-to-end smoke tests validating setup
- **Touches**:
  - `tests/smoke.spec.ts`
- **Dependencies**: Slice 1-8 complete
- **Verification**: `pnpm playwright test tests/smoke.spec.ts` passes

### Slice 10: Build Verification

- **Goal**: Ensure production build excludes test code
- **Touches**:
  - Update `vite.config.ts` to force `VITE_TEST_MODE='false'` in production builds
  - Update `package.json` build script to include verification
- **Dependencies**: Slice 1-9 complete
- **Verification**: `pnpm build` succeeds, bundle size acceptable, test code tree-shaken

---

## 15) Risks & Open Questions

### Risks

#### Backend Health Endpoint Path

- **Risk**: Backend may use `/api/health/readyz` instead of `/api/health`
- **Impact**: Service startup health checks fail; tests cannot run
- **Mitigation**: Verify backend health endpoint path before implementing service management; update polling logic if needed

#### OpenAPI Spec Availability

- **Risk**: Backend may not expose OpenAPI spec at `/api/docs` or spec may be incomplete
- **Impact**: API generation fails; frontend cannot integrate with backend
- **Mitigation**: Coordinate with backend team to ensure spec endpoint is available and includes all CRUD operations

#### Port Conflicts in CI

- **Risk**: GitHub Actions or CI environment may have port restrictions
- **Impact**: Service allocation fails in CI; tests timeout
- **Mitigation**: Use `get-port` for dynamic allocation; ensure CI environment allows localhost binding on ephemeral ports

#### Vite Cache Isolation

- **Risk**: Multiple workers may conflict on Vite cache directory
- **Impact**: Frontend startup race conditions; HMR corruption
- **Mitigation**: Use `VITE_CACHE_DIR` environment variable to isolate cache per worker (from Playwright plan:229-232)

#### Test Event Buffer Overflow

- **Risk**: Frontend emits too many events during test (>500)
- **Impact**: Test fails with buffer overflow error
- **Mitigation**: Buffer size of 500 is generous for Phase A (minimal instrumentation); monitor in Phase B when list and form events increase

### Open Questions

#### Backend Configuration Directory Cleanup

- **Question**: Does backend require explicit cleanup of config directory, or can temp directory be deleted immediately after worker disposal?
- **Why it matters**: Worker teardown may leave orphaned backend processes if cleanup is insufficient
- **Owner / Follow-up**: Backend team to confirm backend gracefully handles config directory removal

#### TanStack Router Route Generation Timing

- **Question**: Should `pnpm generate:routes` run before every dev server start, or only when route files change?
- **Why it matters**: Affects developer workflow; auto-generation may slow down startup
- **Owner / Follow-up**: Test developer ergonomics during Slice 4; add to predev script if needed

#### Console Error Filtering

- **Question**: Should Playwright page fixture allow specific console errors (e.g., expected validation errors), or fail on all errors?
- **Why it matters**: Affects test brittleness; some errors are expected (e.g., failed fetch during retry)
- **Owner / Follow-up**: Implement expected error registration pattern from ElectronicsInventory (`__registerExpectedError` at line 187-189)

#### Tailwind CSS 4 Configuration

- **Question**: Does Tailwind CSS 4 require a `tailwind.config.ts` file, or is `@tailwindcss/vite` plugin sufficient?
- **Why it matters**: Missing config may cause compilation errors
- **Owner / Follow-up**: ElectronicsInventory has no `tailwind.config.ts`; Vite plugin is sufficient for Phase A

---

## 16) Confidence

Confidence: High — This plan follows proven ElectronicsInventory patterns with clear adaptations for IoT Support's simpler architecture (no SSE gateway, JSON file storage). All Playwright infrastructure is documented in detail, and reference implementations exist for every component. Main risk is backend API contract alignment, which can be validated in Slice 2.
