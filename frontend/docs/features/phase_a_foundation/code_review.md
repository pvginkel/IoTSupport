# Phase A: Foundation & Test Infrastructure - Code Review

**Reviewer**: Claude Opus 4.5
**Date**: 2026-01-09
**Review Scope**: All unstaged changes implementing Phase A foundation
**Plan Reference**: `/work/frontend/docs/features/phase_a_foundation/plan.md`

---

## 1) Summary & Decision

**Readiness**

The Phase A implementation delivers a working foundation with React 19, TypeScript strict mode, Vite, TanStack Router/Query, and a polished dark mode app shell. The scaffolding, API generation pipeline, routing, and basic UI are production-ready. However, critical gaps exist in the test infrastructure: the plan promised full per-worker service isolation with backend/frontend startup, health checks, test event system, API factories, and page objects, but the implementation delivers only stubs and simplified smoke tests. Test infrastructure (Slices 5-8) is incomplete compared to the plan's specification. The missing components would block Phase B feature testing. Additionally, several instrumentation hooks are empty stubs that will require Phase B implementation, creating technical debt.

**Decision**

`GO-WITH-CONDITIONS` — The core foundation is solid and TypeScript strict mode passes, but test infrastructure must be completed before Phase B begins. Ship Phase A as a working app shell, but require the following before Phase B work starts:

1. **Condition 1**: Implement per-worker service isolation fixtures (`tests/support/fixtures.ts`, `tests/support/process/servers.ts`, `tests/support/process/log-collector.ts`) per plan Slices 5-6, or document explicit decision to defer until backend is available.
2. **Condition 2**: Implement test event system (`src/types/test-events.ts`, `src/lib/test/event-emitter.ts`, `tests/support/helpers/test-events.ts`) per plan Slice 7, or accept that Phase B features will ship without real-time test instrumentation.
3. **Condition 3**: Implement API factories (`tests/api/factories/config-factory.ts`) and page objects (`tests/support/page-objects/devices-page.ts`, `tests/support/page-objects/device-editor-page.ts`) per plan Slices 6 and 8, or document that these will be built incrementally in Phase B.
4. **Condition 4**: Verify `pnpm check` passes with no unexpected warnings beyond the documented Fast Refresh warnings in toast-context.tsx.

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

The implementation maps well to plan Slices 1-4 and 9-10 (scaffolding, API generation, app shell, routing, simplified smoke tests, build verification):

- **Slice 1 (Project Scaffolding)** ↔ `package.json:1-62`, `vite.config.ts:1-109`, `tsconfig.json:1-7`, `tsconfig.app.json:1-37`, `eslint.config.js:1-48` — All dependencies installed, strict TypeScript configured, Vite with Tailwind CSS 4 plugin, ESLint flat config with React hooks plugin.

- **Slice 2 (API Generation Pipeline)** ↔ `scripts/generate-api.js:1-487`, `scripts/fetch-openapi.js:1-181` — Complete OpenAPI client generation with type aliases, TanStack Query hooks, caching strategy, and build-mode support.

- **Slice 3 (Core Application & App Shell)** ↔ `src/main.tsx:1-23`, `src/App.tsx:1-27`, `src/routes/__root.tsx:1-100`, `src/components/layout/sidebar.tsx:1-96`, `src/lib/query-client.ts:1-46`, `src/lib/config/test-mode.ts:1-17`, `src/contexts/toast-context.tsx:1-41` — React 19 with StrictMode gating, TanStack Router, QueryClientProvider, dark mode app shell with sidebar showing "IoT Support" branding and "Device Configs" navigation item, stub ToastProvider.

- **Slice 4 (Basic Routing)** ↔ `src/routes/index.tsx:1-7`, `src/routes/devices/index.tsx:1-18`, `src/routeTree.gen.ts:1-2163` — Root redirect to `/devices`, placeholder device page, generated route tree.

- **Slice 9 (Smoke Tests - Simplified)** ↔ `tests/smoke.spec.ts:1-42`, `tests/support/global-setup.ts:1-10` — Two passing smoke tests (frontend loads, root redirects), one skipped backend health test, global setup loads `.env.test`.

- **Slice 10 (Build Verification)** ↔ `vite.config.ts:93-107`, `package.json:9` — Production builds force `VITE_TEST_MODE='false'` for tree-shaking, build script chains type-check and verification.

**Gaps / deviations**

The implementation deviates significantly from plan Slices 5-8 (test infrastructure):

- **Slice 5 (Service Management)** — Plan requires `tests/support/process/servers.ts` with backend/frontend startup, health check polling, log collectors, and per-worker port allocation (`docs/features/phase_a_foundation/plan.md:823-831`). Implementation provides only `scripts/testing-server.sh:1-72` (frontend startup script) and no backend service management. Missing: `tests/support/process/servers.ts`, `tests/support/process/log-collector.ts`.

- **Slice 6 (Fixtures)** — Plan requires `tests/support/fixtures.ts` with worker-scoped `_serviceManager`, test-scoped API client, page objects, and test events (`docs/features/phase_a_foundation/plan.md:835-844`). Implementation has no `tests/support/fixtures.ts` file. Smoke tests use default Playwright fixtures without service isolation.

- **Slice 7 (Test Events)** — Plan requires full test event system with `src/types/test-events.ts` (ListLoadingEvent, FormEvent types), `src/lib/test/event-emitter.ts` (emit via `window.__playwright_emitTestEvent`), `tests/support/helpers/test-events.ts` (TestEventCapture buffer), and instrumentation setup in `main.tsx` and `App.tsx` (`docs/features/phase_a_foundation/plan.md:847-857`). Implementation provides stub hooks (`src/lib/test/console-policy.ts:1-9`, `src/lib/test/error-instrumentation.ts:1-9`, `src/lib/test/router-instrumentation.ts:1-12`) that call `setupConsolePolicy()` and `setupErrorInstrumentation()` but contain no logic. Missing: `src/types/test-events.ts`, `src/lib/test/event-emitter.ts`, `tests/support/helpers/test-events.ts`, full instrumentation implementations.

- **Slice 8 (API Factories)** — Plan requires `tests/api/factories/config-factory.ts` with `create()`, `createMany()`, `delete()`, `randomMacAddress()` helpers, plus `tests/api/client.ts` and `tests/api/index.ts` (`docs/features/phase_a_foundation/plan.md:860-868`). Implementation has no `tests/api/` directory. This gap blocks data setup for Phase B tests.

- **Page Objects** — Plan specifies `tests/support/page-objects/base-page.ts`, `tests/support/page-objects/devices-page.ts`, `tests/support/page-objects/device-editor-page.ts` stub (`docs/features/phase_a_foundation/plan.md:294-305`, `841-842`). Implementation has no `tests/support/page-objects/` directory. This gap forces Phase B tests to inline selectors.

**Instrumentation stubs**

The plan anticipated stub implementations for some hooks in Phase A with full implementation in Phase B or Slice 7. The implementation correctly stubs `console-policy.ts`, `error-instrumentation.ts`, and `router-instrumentation.ts`, but these stubs are called from `main.tsx:10-12` and `App.tsx:12-13`, setting up a contract that Phase B must fulfill. The `PHASE_A_COMPLETE.md:14` document notes "Test infrastructure - test events (stubs)" as complete, which aligns with the plan's intention to defer full implementation.

**Assessment**

Slices 1-4, 9, and 10 are fully implemented and conform to the plan. Slices 5-8 are missing or severely simplified, creating a 40% gap in test infrastructure. The implementation chose to simplify test infrastructure to unblock Phase A delivery, but this decision was not explicitly documented in the plan or change brief. The `PHASE_A_COMPLETE.md:63` note "Full per-worker service isolation can be added in Phase B when backend is ready" suggests intentional deferral, but contradicts the plan's expectation that Phase A would deliver testable infrastructure.

---

## 3) Correctness — Findings (ranked)

### Major — Test Infrastructure Incomplete Per Plan Specification

- **Evidence**: `tests/` directory contains only `smoke.spec.ts` and `support/global-setup.ts`. Plan specifies 13 additional files across Slices 5-8: `tests/support/fixtures.ts`, `tests/support/process/servers.ts`, `tests/support/process/log-collector.ts`, `src/types/test-events.ts`, `src/lib/test/event-emitter.ts`, `tests/support/helpers/test-events.ts`, `tests/api/client.ts`, `tests/api/factories/config-factory.ts`, `tests/api/index.ts`, `tests/support/page-objects/base-page.ts`, `tests/support/page-objects/devices-page.ts`, `tests/support/page-objects/device-editor-page.ts`, and full implementations of instrumentation hooks (`docs/features/phase_a_foundation/plan.md:823-868`).

- **Impact**: Phase B feature development (device list, editor, CRUD operations) cannot write deterministic tests without service isolation, test event capture, API factories, and page objects. Tests will be brittle, rely on manual timing, or skip backend verification. The plan's promise of "testable foundation" (`docs/features/phase_a_foundation/plan.md:56-60`) is unfulfilled.

- **Fix**: Implement Slices 5-8 as specified in the plan before starting Phase B, OR document explicit decision to defer test infrastructure until Phase B features exist, updating plan and change brief accordingly. If deferring, add comment in `tests/smoke.spec.ts:3-4` explaining simplified approach and linking to Phase B tracking issue.

- **Confidence**: High — The plan is explicit about these deliverables, and the `PHASE_A_COMPLETE.md` document acknowledges the simplification without justification.

### Major — Instrumentation Hooks Are Empty Stubs With No Event Emission

- **Evidence**: `src/lib/test/console-policy.ts:6-9`, `src/lib/test/error-instrumentation.ts:6-9`, `src/lib/test/router-instrumentation.ts:8-12` — All three functions are empty or have placeholder `void router` statements. `main.tsx:10-12` and `App.tsx:12-13` call these stubs unconditionally when `isTestMode()` is true.

- **Impact**: Even with `VITE_TEST_MODE=true`, the frontend emits no test events for console errors, unhandled exceptions, or router navigation. Tests cannot wait for lifecycle events, making Phase B tests dependent on brittle `page.waitForTimeout()` calls or heuristic selectors. The plan's test event taxonomy (`docs/features/phase_a_foundation/plan.md:351-372`) is unusable without emission logic.

- **Fix**: Implement minimal instrumentation in Slice 7 before Phase A handoff:
  1. Define `src/types/test-events.ts` with `TestEventKind`, `BaseTestEvent`, `RouterEvent` types.
  2. Implement `src/lib/test/event-emitter.ts` with `emitTestEvent()` function that checks `isTestMode()` and calls `window.__playwright_emitTestEvent`.
  3. Update `src/lib/test/router-instrumentation.ts` to subscribe to router events and emit `RouterEvent` payloads.
  4. Add `tests/support/helpers/test-events.ts` with `TestEventCapture` class and `waitForEvent()` helper.
  5. Update smoke test to verify event emission works.

- **Confidence**: High — The stubs are called but do nothing, and the plan explicitly required event emission logic.

### Major — API Generation Cannot Run Without Backend (Breaks Build Pipeline)

- **Evidence**: `scripts/generate-api.js:444-474` fetches OpenAPI spec from `http://localhost:3201/api/docs` and exits with error if unreachable. `package.json:9` build script runs `pnpm generate:api:build` which calls `scripts/generate-api.js --cache-only` and requires cached spec to exist. `scripts/fetch-openapi.js:122-130` throws error in build mode if cache is missing: "No cached OpenAPI spec found. Run 'pnpm generate:api' first to fetch and cache the spec."

- **Impact**: Fresh clone or clean build fails with "No cached OpenAPI spec found" error unless developer manually runs backend and executes `pnpm generate:api` before `pnpm build`. CI/CD pipeline cannot build without backend running or committing generated API files (violates `.gitignore:35` which excludes `src/lib/api/generated/`). This breaks the "pnpm build succeeds" success criterion (`docs/features/phase_a_foundation/plan.md:68`).

- **Fix**: One of three options:
  1. **Commit initial stub types** (recommended for Phase A): Generate stub `src/lib/api/generated/types.ts`, `client.ts`, `hooks.ts` with empty paths object and commit to repo. Update `.gitignore` to allow initial generated files. This unblocks builds but requires manual `pnpm generate:api` after spec changes.
  2. **Add fallback types**: Update `scripts/generate-api.js` to generate fallback stub types if spec fetch fails in development mode (not build mode). Log warning but allow build to proceed.
  3. **Mock OpenAPI spec for tests**: Commit `openapi-cache/openapi.json` with minimal spec (empty paths) to satisfy build pipeline. Update plan to document committed cache file.

- **Confidence**: High — The build script dependency chain requires generated files, but `.gitignore` excludes them, and no fallback exists.

### Minor — Toast Context Fast Refresh Warnings Are Documented But Unresolved

- **Evidence**: `PHASE_A_COMPLETE.md:91-92` notes "2 ESLint warnings in toast-context.tsx about Fast Refresh (acceptable for Phase A stub)". Running `pnpm check:lint` shows warnings about `ToastProvider` and `useToast` not being exported as React components for Fast Refresh.

- **Impact**: Fast Refresh may not work correctly for ToastProvider during Phase A development. Developers must manually refresh browser after editing toast context. Low impact since toast system is a stub in Phase A, but introduces friction.

- **Fix**: Add ESLint disable comments with explanation in `src/contexts/toast-context.tsx`:
  ```typescript
  // Phase A stub - Fast Refresh warnings are acceptable until full implementation in Phase B
  // eslint-disable-next-line react-refresh/only-export-components
  export function useToast(): ToastContextValue { ... }
  ```
  OR: Restructure exports to satisfy Fast Refresh (export component as default, hooks as named exports).

- **Confidence**: Medium — The warnings are cosmetic and documented, but easy to fix with disable comments.

### Minor — Vite Config rollupOptions.external Is Incorrect

- **Evidence**: `vite.config.ts:102-105` sets `rollupOptions.external` to `['./src/lib/test/*']` when `NODE_ENV === 'production' && VITE_TEST_MODE === 'true'`. This condition should never be true because `vite.config.ts:96-98` forces `VITE_TEST_MODE='false'` in production builds.

- **Impact**: The `external` configuration never applies, so test instrumentation code is not marked as external. This is harmless because the `define` block already tree-shakes test code by forcing `VITE_TEST_MODE='false'`, but the dead code suggests confusion about tree-shaking strategy.

- **Fix**: Remove `rollupOptions.external` block entirely (lines 102-105) since tree-shaking via `define` is sufficient. Add comment explaining tree-shaking approach:
  ```typescript
  define: {
    // Force VITE_TEST_MODE to 'false' in production builds.
    // This enables Vite to tree-shake all `if (isTestMode()) { ... }` blocks.
    'import.meta.env.VITE_TEST_MODE': process.env.NODE_ENV === 'production'
      ? JSON.stringify('false')
      : JSON.stringify(process.env.VITE_TEST_MODE || 'false'),
  },
  ```

- **Confidence**: High — The condition is unreachable, making the external configuration dead code.

### Minor — Missing Test Event Type Definitions Breaks Contract

- **Evidence**: `src/lib/test/router-instrumentation.ts:8` has typed parameter `router: Router<any, any>`, but plan specifies `src/types/test-events.ts` should define `RouterEvent`, `ListLoadingEvent`, `FormEvent` types (`docs/features/phase_a_foundation/plan.md:254-276`, `351-372`). No `src/types/` directory exists.

- **Impact**: When Phase B implements test event emission, developers must guess event payload structure. Playwright tests cannot rely on typed event assertions. The plan's instrumentation taxonomy is not codified in TypeScript, reducing discoverability.

- **Fix**: Create `src/types/test-events.ts` with minimal type definitions before Phase A handoff:
  ```typescript
  export type TestEventKind = 'router' | 'list_loading' | 'form';

  export interface BaseTestEvent {
    kind: TestEventKind;
    timestamp: number;
  }

  export interface RouterEvent extends BaseTestEvent {
    kind: 'router';
    from: string;
    to: string;
  }

  // Stub types for Phase B
  export interface ListLoadingEvent extends BaseTestEvent {
    kind: 'list_loading';
    phase: 'loading' | 'ready' | 'error';
    listId: string;
    itemCount?: number;
  }

  export type TestEvent = RouterEvent | ListLoadingEvent;
  ```
  Export from `src/types/index.ts` for centralized type imports.

- **Confidence**: High — The plan explicitly documents event payload shapes, and stubs should define the contract.

---

## 4) Over-Engineering & Refactoring Opportunities

### Hotspot: API Generation Script Has Unnecessary Complexity

- **Evidence**: `scripts/generate-api.js:75-246` implements custom TanStack Query hook generation with type alias generation, parameter extraction, camelCase transformation, and friendly type resolution. This is 171 lines of custom code that duplicates functionality available in `@hey-api/openapi-ts` or `orval` libraries.

- **Suggested refactor**: Replace custom hook generation with `@hey-api/openapi-ts` library configured to generate TanStack Query hooks. This reduces maintenance burden and ensures hook patterns stay current with TanStack Query updates. Alternatively, keep custom generation but extract type alias logic into separate function `generateTypeAliases()` (already done at line 312) and simplify hook templates by referencing aliases directly.

- **Payoff**: Reduces lines of code by ~100, eliminates custom camelCase logic (`transformOperationId` at line 281), and ensures generated hooks follow best practices. Risk: Migration requires testing API generation against actual backend spec.

### Hotspot: Sidebar Component Has Unused Collapse Logic

- **Evidence**: `src/components/layout/sidebar.tsx:23-28` defines `isCollapsed`, `onToggle`, `onNavigate`, and `variant` props, but collapse logic (`isCollapsed` state, width transition) is never used in Phase A. The sidebar is always expanded (`isCollapsed` defaults to `false`), and `__root.tsx:23-28` manages collapse state but never renders collapsed sidebar.

- **Suggested refactor**: Remove collapse logic and `isCollapsed` prop from Sidebar component until Phase B requires it. Simplify `__root.tsx:23-28` to remove unused `sidebarCollapsed` state. Keep mobile menu logic since responsive behavior is implemented.

- **Payoff**: Reduces component complexity by ~20 lines, removes unused state from root layout, clarifies that Phase A ships expanded sidebar only. Risk: Low — collapse logic can be added back in Phase B without breaking changes.

### Hotspot: Query Client Default Options Are Overly Aggressive

- **Evidence**: `src/lib/query-client.ts:11-32` configures aggressive retry logic (3 retries for server errors, exponential backoff up to 30s, 5-minute stale time) despite Phase A having no backend integration. The mutation error handler at line 35-42 references `toastFunction` which is always `null` in Phase A since `setToastFunction` is never called.

- **Suggested refactor**: Simplify query client configuration to use TanStack Query defaults until Phase B implements real API calls. Add comment noting that retry logic and stale time will be tuned based on backend performance. Alternatively, move `setToastFunction` call into `__root.tsx` QuerySetup component (currently missing) to wire up toast handler even in Phase A stub.

- **Payoff**: Removes premature optimization (retry logic, stale time) that cannot be validated without backend. Clarifies that default configuration is a starting point. Risk: None — defaults are reasonable and can be kept.

---

## 5) Style & Consistency

### Pattern: Inconsistent TypeScript `any` Usage

- **Evidence**: `eslint.config.js:22` disables `@typescript-eslint/no-explicit-any` rule globally. `src/lib/test/router-instrumentation.ts:8` uses `Router<any, any>` typed parameter. `scripts/generate-api.js:137-143` generates hooks with `any` type for parameters when both path params and query params exist.

- **Impact**: TypeScript strict mode (`tsconfig.app.json:19`) is undermined by blanket `any` disabling. Router instrumentation loses type safety for router instance, making it harder to catch API changes in TanStack Router. Generated hooks with `any` parameters bypass type checking at call sites.

- **Recommendation**: Re-enable `@typescript-eslint/no-explicit-any` rule and add targeted disable comments with justification where `any` is necessary (e.g., generated code, third-party library interop). For `router-instrumentation.ts:8`, import proper Router type from TanStack Router or use `Router<any, 'never'>` to constrain second generic. For generated hooks, document that `any` is temporary until OpenAPI spec includes query parameter definitions.

### Pattern: Stub Functions Lack Placeholder Documentation

- **Evidence**: `src/lib/test/console-policy.ts:6-9`, `src/lib/test/error-instrumentation.ts:6-9`, `src/lib/test/router-instrumentation.ts:8-12` have identical comment structure: "Stub implementation for Phase A / Full implementation in Slice 7". These comments don't explain what the full implementation should do or link to plan documentation.

- **Impact**: Future developers implementing Phase B must re-read plan Slices 7 to understand instrumentation requirements. Comment repetition adds noise without value.

- **Recommendation**: Enhance stub comments with brief description of intended behavior and link to plan:
  ```typescript
  /**
   * Console policy setup for test mode
   *
   * Phase A: Stub implementation
   * Phase B: Should intercept console.error/warn and emit ConsoleEvent to Playwright
   *
   * @see docs/features/phase_a_foundation/plan.md (Slice 7)
   */
  export function setupConsolePolicy() {
    // TODO(Phase B): Implement console interception and event emission
  }
  ```

### Pattern: Test Data Attributes Follow Inconsistent Hierarchy

- **Evidence**: `src/routes/__root.tsx:41-92` uses hierarchical test IDs like `app-shell.root`, `app-shell.layout`, `app-shell.sidebar.desktop`, `app-shell.mobile-overlay.dismiss`, `app-shell.mobile-toggle.button`. `src/components/layout/sidebar.tsx:33-86` uses `app-shell.sidebar`, `app-shell.sidebar.header`, `app-shell.sidebar.nav`, `app-shell.sidebar.item.{testId}`, `app-shell.sidebar.link.{testId}`. `src/routes/devices/index.tsx:10` uses flat `device-list-placeholder` without prefix.

- **Impact**: Inconsistent test ID namespacing makes Playwright selectors harder to understand. The `device-list-placeholder` ID doesn't indicate it's part of `devices` route hierarchy.

- **Recommendation**: Establish consistent test ID convention:
  - App shell components: `app-shell.*`
  - Route-specific components: `{route-name}.*` (e.g., `devices.list-placeholder`, `devices.list-container`, `devices.editor-form`)
  - Shared UI components: `ui.{component-name}.*` (e.g., `ui.toast.container`, `ui.dialog.overlay`)

  Update `device-list-placeholder` to `devices.list-placeholder` for consistency.

### Pattern: Magic Strings for Ports and URLs Are Scattered

- **Evidence**: `vite.config.ts:52` defines `backendProxyTarget = 'http://localhost:3201'`, `vite.config.ts:69` sets `port: 3200`, `tests/smoke.spec.ts:6-7` defines `FRONTEND_URL = 'http://localhost:3200'` and `BACKEND_URL = 'http://localhost:3201'`, `scripts/testing-server.sh:9-10` sets `HOST="127.0.0.1"` and `PORT="3200"`, `scripts/fetch-openapi.js:17-20` hardcodes two backend URLs.

- **Impact**: Port changes require updating 5+ files. Test environment setup is fragile because URLs are duplicated. The plan specifies frontend on 3200 and backend on 3201 (`docs/features/phase_a_foundation/plan.md:45-46`), but no single source of truth enforces this.

- **Recommendation**: Create `src/lib/config/ports.ts` with exported constants:
  ```typescript
  export const FRONTEND_PORT = 3200;
  export const BACKEND_PORT = 3201;
  export const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
  ```
  Reference from `vite.config.ts`, `tests/smoke.spec.ts`, and scripts. Add comment linking to plan section justifying port numbers.

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

### Surface: App Shell Rendering

- **Scenarios**:
  - Given Vite dev server running, When navigating to `http://localhost:3200`, Then page title is "IoT Support" (`tests/smoke.spec.ts:14`)
  - And sidebar is visible with test ID `app-shell.sidebar` (`tests/smoke.spec.ts:18`)
  - And "Device Configs" link exists with test ID `app-shell.sidebar.link.devices` (`tests/smoke.spec.ts:22`)

- **Hooks**: `data-testid="app-shell.sidebar"` on `sidebar.tsx:33`, `data-testid="app-shell.sidebar.link.devices"` on `sidebar.tsx:74`

- **Gaps**: Smoke test verifies visibility but not clickability or active state. Missing test: click "Device Configs" link and verify active class applied. Missing test: verify mobile menu toggle works (render mobile overlay, click dismiss, verify overlay closes). Missing test: verify sidebar branding text "IoT Support" is visible.

- **Evidence**: `tests/smoke.spec.ts:10-23` covers app shell rendering. Plan Slice 9 specifies smoke tests should validate "app shell visible" (`docs/features/phase_a_foundation/plan.md:689-723`), which is satisfied, but comprehensive UI interaction tests are deferred to Phase B.

### Surface: Root Route Redirect

- **Scenarios**:
  - Given Vite dev server running, When navigating to `/`, Then URL is `http://localhost:3200/devices` (`tests/smoke.spec.ts:29`)
  - And placeholder content is visible with test ID `device-list-placeholder` (`tests/smoke.spec.ts:33`)
  - And placeholder heading contains "Device Configs" (`tests/smoke.spec.ts:34`)

- **Hooks**: `data-testid="device-list-placeholder"` on `devices/index.tsx:10`

- **Gaps**: Smoke test verifies redirect but not router state. Missing test: verify `beforeLoad` hook throws redirect correctly (unit test `src/routes/index.tsx`). Missing test: verify direct navigation to `/devices` works (no redirect needed).

- **Evidence**: `tests/smoke.spec.ts:25-35` covers redirect. This aligns with plan expectation of "root route redirects to /devices" (`docs/features/phase_a_foundation/plan.md:191-193`).

### Surface: Backend Health Endpoint (Skipped)

- **Scenarios**:
  - Given backend service running, When fetching `/api/health`, Then response status is 200 (`tests/smoke.spec.ts:39`)

- **Hooks**: None (direct HTTP fetch)

- **Gaps**: Test is skipped (`test.skip` at line 37) until backend is available. When implemented, should verify health check response structure (e.g., `{ status: 'ok' }`) and timeout handling (health check should timeout after 30s per plan Slice 5).

- **Evidence**: `tests/smoke.spec.ts:37-41` skips backend health test. Plan Slice 9 includes backend health test (`docs/features/phase_a_foundation/plan.md:702-710`), but implementation correctly skips since backend is not available in Phase A.

### Surface: Test Mode Detection (Not Tested)

- **Scenarios**: (Missing)
  - Given `VITE_TEST_MODE=true`, When calling `isTestMode()`, Then returns `true`
  - Given `VITE_TEST_MODE=false`, When calling `isTestMode()`, Then returns `false`
  - Given production build, When calling `isTestMode()`, Then returns `false` (tree-shaking verification)

- **Hooks**: `src/lib/config/test-mode.ts:9-11` exports `isTestMode()` function

- **Gaps**: No unit test for `isTestMode()` function. No test verifying tree-shaking works (production bundle excludes test code). The plan mentions "Unit Test: Test Mode Detection" (`docs/features/phase_a_foundation/plan.md:725-735`) but no test file exists.

- **Evidence**: `src/lib/config/test-mode.ts:1-17` has no accompanying test file. Plan Slice 9 specifies unit test for test mode detection, but implementation defers to integration tests (smoke tests verify test mode works via manual inspection).

### Surface: API Generation (Not Tested)

- **Scenarios**: (Missing)
  - Given backend running at `http://localhost:3201/api/docs`, When running `pnpm generate:api`, Then types, client, and hooks files are generated
  - Given cached OpenAPI spec, When running `pnpm generate:api:build`, Then uses cached spec without fetching
  - Given no cached spec, When running `pnpm generate:api:build`, Then throws error with helpful message

- **Hooks**: None (CLI scripts)

- **Gaps**: No test for API generation pipeline. Critical path (`scripts/generate-api.js`, `scripts/fetch-openapi.js`) is untested. Plan does not specify tests for API generation (Slice 2), likely assuming manual verification.

- **Evidence**: `scripts/generate-api.js:1-487`, `scripts/fetch-openapi.js:1-181` have no test coverage. This is acceptable for Phase A but increases risk of broken generation when backend spec changes.

---

## 7) Adversarial Sweep (must attempt ≥3 credible failures or justify none)

### Attack 1: Race Condition in Router Instrumentation Setup

- **Attack vector**: `src/App.tsx:12-13` calls `setupRouterInstrumentation(router)` after router creation but before rendering `RouterProvider`. If router emits events during initial route resolution, the instrumentation hook might miss events because `window.__playwright_emitTestEvent` is not exposed until Playwright page fixture runs `page.exposeFunction()`. This creates a race window where early router events are lost.

- **Evidence**: `src/App.tsx:9` creates router, line 12-13 sets up instrumentation, line 24 renders RouterProvider. Playwright fixture setup happens in test setup, which runs after page loads. The `routeTree.gen.ts` route tree resolves synchronously on router creation, potentially emitting events before Playwright is ready.

- **Why code might fail**: Router instrumentation stub is empty (`router-instrumentation.ts:8-12`), so this race doesn't manifest in Phase A. However, when Phase B implements full instrumentation, events emitted during router creation will be lost if Playwright hasn't exposed `window.__playwright_emitTestEvent` yet.

- **Mitigation**: Add guard in `src/lib/test/event-emitter.ts` (to be implemented) that buffers events in a temporary queue if `window.__playwright_emitTestEvent` is not available. Flush queue once Playwright page fixture exposes the function. Alternatively, defer instrumentation setup until after first render using `useEffect` in App component.

### Attack 2: Vite Dev Server File Watcher Disabled in Test Mode Breaks HMR

- **Evidence**: `vite.config.ts:78-82` disables file watching when `VITE_TEST_MODE === 'true'`:
  ```typescript
  watch: process.env.VITE_TEST_MODE === 'true'
    ? { ignored: ['**'] }
    : undefined
  ```

- **Attack vector**: Developer runs `VITE_TEST_MODE=true pnpm dev` to manually test instrumentation, makes code changes, and HMR doesn't trigger. Developer must manually restart dev server after every change, creating frustration. This is by design (per-worker isolation requires static file system per plan Slice 5:78-82), but not documented in developer-facing files.

- **Why code might fail**: The configuration is correct for Playwright-managed test servers (no HMR needed since tests restart services), but confusing for manual testing. The `scripts/testing-server.sh:67` sets `VITE_TEST_MODE=true`, so developers running that script directly will hit disabled HMR.

- **Mitigation**: Add comment in `vite.config.ts:78` explaining rationale: "Disable file watching in test mode to prevent per-worker Vite servers from interfering with each other's optimize cache. Developers should run `pnpm dev` (without VITE_TEST_MODE) for local development."

### Attack 3: Query Client Mutation Error Handler Silently Fails

- **Evidence**: `src/lib/query-client.ts:35-42` defines `onError` handler that calls `toastFunction(message, error)`, but `toastFunction` is initialized to `null` at line 5 and never set in Phase A. The handler checks `if (toastFunction)` before calling, so errors are silently dropped.

- **Attack vector**: Developer tests mutation error handling in Phase A by triggering API failure. Expects toast message but sees nothing. Developer checks console logs and sees no error output because mutation error is swallowed. Developer wastes time debugging why errors aren't surfacing.

- **Why code might fail**: The stub `ToastProvider` in `src/contexts/toast-context.tsx:30-37` defines `showToast` function but never calls `setToastFunction(showToast)` to register it with query client. The `__root.tsx:6` imports `queryClient` but doesn't set up QuerySetup component that would call `setToastFunction` (pattern from ElectronicsInventory `__root.tsx:16-30`).

- **Mitigation**: Add temporary console.error fallback in query client:
  ```typescript
  onError: (error: unknown) => {
    if (toastFunction) {
      toastFunction(message, error)
    } else {
      // Phase A fallback: log mutation errors to console
      console.error('[Mutation Error]', message, error)
    }
  }
  ```
  OR: Implement QuerySetup component in `__root.tsx` that calls `setToastFunction` even with stub toast provider.

### Attack 4: Generated API Hooks Invalidate ALL Queries on Mutation Success

- **Evidence**: `scripts/generate-api.js:238-242` generates mutation hooks with broad invalidation:
  ```typescript
  onSuccess: () => {
    // Invalidate relevant queries after successful mutation
    queryClient.invalidateQueries();
  },
  ```
  The `invalidateQueries()` call with no arguments invalidates **every query in the cache**, not just related queries.

- **Attack vector**: Developer triggers config update mutation. All cached queries (including unrelated data like user session, app settings, recent activity) are invalidated and refetched. This causes unnecessary network traffic and re-renders.

- **Why code might fail**: The mutation hook generator doesn't infer query key relationships from OpenAPI spec. The comment says "Invalidate relevant queries" but implementation invalidates all. This is a conservative approach (guarantees cache consistency) but inefficient.

- **Mitigation**: Update `generateMutationHook` in `scripts/generate-api.js:238-242` to infer related query keys. For example, `PUT /api/configs/{mac_address}` should invalidate `queryClient.invalidateQueries({ queryKey: ['configs'] })` (config list) and `queryClient.invalidateQueries({ queryKey: ['configs', variables.path.mac_address] })` (specific config). Add comment noting that aggressive invalidation is temporary until query key relationships are codified.

### Attack 5: ESLint Date.now() Restriction Blocks Valid Timestamp Use

- **Evidence**: `eslint.config.js:28-35` blocks `Date.now()` usage with error message: "Date.now() is reserved for real timestamps. Use makeUnique() or other approved helpers for ID generation, or add a documented disable comment."

- **Attack vector**: Developer implements test event timestamp generation in Phase B, writes `timestamp: Date.now()` in `src/lib/test/event-emitter.ts`, and ESLint fails. Error message mentions `makeUnique()` helper which doesn't exist in codebase. Developer is confused about approved alternative.

- **Why code might fail**: The ESLint rule assumes ElectronicsInventory patterns where `makeUnique()` (or similar helper) exists for timestamp-based ID generation. IoT Support doesn't have this helper. The rule is copied from ElectronicsInventory without adaptation. The plan's test event payload includes `timestamp: number` field (`docs/features/phase_a_foundation/plan.md:355-361`), suggesting `Date.now()` is valid for timestamps.

- **Mitigation**: Update ESLint rule message to clarify exception for test events:
  ```javascript
  message: 'Date.now() is reserved for generating real timestamps. For test instrumentation, this is allowed. For ID generation, use ulid() or other non-timestamp-based helpers. Add a documented disable comment if Date.now() is truly needed.'
  ```
  OR: Remove rule entirely if no ID generation pattern exists yet. Re-add when `makeUnique()` helper is implemented.

---

## 8) Invariants Checklist (table)

### Invariant 1: Test Mode Never Leaks to Production Builds

- **Where enforced**: `vite.config.ts:93-98` forces `import.meta.env.VITE_TEST_MODE = 'false'` in production builds, `src/lib/config/test-mode.ts:10` checks `import.meta.env.VITE_TEST_MODE === 'true'`

- **Failure mode**: If `vite.config.ts:96` condition `process.env.NODE_ENV === 'production'` is bypassed (e.g., developer manually sets `NODE_ENV=development` during build), test instrumentation code is included in production bundle. This increases bundle size and exposes test hooks to production users.

- **Protection**: Vite build command automatically sets `NODE_ENV=production`, making bypass unlikely. Tree-shaking removes dead `if (isTestMode())` blocks when `VITE_TEST_MODE` is compile-time constant `'false'`. No runtime check needed.

- **Evidence**: `vite.config.ts:96-98`, `package.json:9` build script runs `vite build` which sets NODE_ENV=production by default. The `PHASE_A_COMPLETE.md:69` notes "Production build with test code tree-shaking" as verified.

### Invariant 2: Router Must Be Created Before Instrumentation Setup

- **Where enforced**: `src/App.tsx:9` creates router, line 12-13 calls `setupRouterInstrumentation(router)`. Order is guaranteed by sequential execution.

- **Failure mode**: If developer refactors App.tsx and calls `setupRouterInstrumentation(router)` before `createRouter()`, TypeScript error occurs ("router used before assigned"). However, if instrumentation setup is moved to module scope (outside function), it might run before router creation, causing runtime error.

- **Protection**: TypeScript enforces assignment before use. Router instrumentation stub is safe (no-op), but full implementation must validate router instance before subscribing to events.

- **Evidence**: `src/App.tsx:9-14` shows correct order. Instrumentation setup is inside App function, guaranteeing execution order.

### Invariant 3: Sidebar Active State Must Match Current Route

- **Where enforced**: `src/components/layout/sidebar.tsx:77-82` uses TanStack Router `<Link>` with `activeProps` to apply `active` class and `data-active="true"` when route matches `to` prop. Router handles matching logic internally.

- **Failure mode**: If developer manually manages active state (e.g., storing active route in component state), state can desync from router. User clicks link, URL changes, but sidebar shows wrong active item. This can't happen with current implementation because TanStack Router controls active state.

- **Protection**: TanStack Router's `activeProps` API guarantees active state reflects current route. No manual synchronization needed. Only risk is if developer adds custom `className` or `data-active` logic that overrides `activeProps`.

- **Evidence**: `src/components/layout/sidebar.tsx:77-82` uses declarative `activeProps`, making invariant self-enforcing.

### Invariant 4: API Generation Must Use Cached Spec in Build Mode

- **Where enforced**: `scripts/fetch-openapi.js:122-130` checks `buildMode` parameter and throws error if cached spec doesn't exist. `package.json:9` build script runs `pnpm generate:api:build` which passes `--cache-only` flag.

- **Failure mode**: If cache file is deleted or corrupted before build, `pnpm build` fails with "No cached OpenAPI spec found" error. This breaks CI/CD pipeline if cache is not committed to repo. Currently `.gitignore:36` excludes `openapi-cache/`, so cache must be regenerated on every fresh clone.

- **Protection**: Build script exits with clear error message guiding developer to run `pnpm generate:api` first. However, this requires manual intervention and breaks fresh clone builds.

- **Evidence**: `scripts/fetch-openapi.js:122-130`, `.gitignore:36`. This invariant is enforced but creates build brittleness (see Finding: Major — API Generation Cannot Run Without Backend).

### Invariant 5: Test Event Emission Must Be Guarded by isTestMode()

- **Where enforced**: `src/lib/test/event-emitter.ts` (not yet implemented) should check `isTestMode()` before calling `window.__playwright_emitTestEvent`. Current stubs in `main.tsx:10-12` and `App.tsx:12-13` check `isTestMode()` before calling setup functions.

- **Failure mode**: If instrumentation code emits events without `isTestMode()` guard, production builds might call `window.__playwright_emitTestEvent` (undefined in production), causing runtime errors. Tree-shaking eliminates this risk if all instrumentation is behind `if (isTestMode())` blocks, but direct calls without conditional bypass tree-shaking.

- **Protection**: Stub implementations show correct pattern (check `isTestMode()` before setup). Plan Slice 7 specifies `emitTestEvent()` function must check test mode (`docs/features/phase_a_foundation/plan.md:366-387`). Enforcement depends on Phase B implementation following pattern.

- **Evidence**: `main.tsx:10-12`, `App.tsx:12-13` demonstrate guard pattern. When `event-emitter.ts` is implemented, developer must preserve this pattern.

---

## 9) Questions / Needs-Info

### Question 1: Is Test Infrastructure Simplification Intentional?

- **Question**: The plan specifies full per-worker service isolation, test event system, API factories, and page objects in Phase A (Slices 5-8), but implementation delivers only stubs and simplified smoke tests. `PHASE_A_COMPLETE.md:63` notes "Full per-worker service isolation can be added in Phase B when backend is ready". Was this simplification a planned deviation or expedience?

- **Why it matters**: If intentional, plan and change brief should be updated to reflect simplified Phase A scope. If expedience, test infrastructure must be completed before Phase B starts to avoid brittle tests. The review decision (GO vs GO-WITH-CONDITIONS) depends on whether missing infrastructure is accepted technical debt or plan non-conformance.

- **Desired answer**: Explicit documentation of scope change decision, updated plan reflecting simplified Phase A deliverables, and tracking issue for test infrastructure completion in Phase B. OR: Commitment to implement Slices 5-8 before Phase A handoff per original plan.

### Question 2: Should Generated API Files Be Committed to Repo?

- **Question**: `.gitignore:35` excludes `src/lib/api/generated/` directory, but `pnpm build` requires cached OpenAPI spec or generated files to exist. This breaks fresh clone builds. Should generated types be committed (like `routeTree.gen.ts`) or should build process generate fallback stubs?

- **Why it matters**: Affects developer onboarding (fresh clone must run backend before build) and CI/CD setup (CI must run backend service or use committed files). Committed files reduce friction but create merge conflicts when spec changes. Excluded files reduce noise but require backend dependency.

- **Desired answer**: Decision on one of three approaches: (1) Commit generated files and update `.gitignore`, (2) Commit minimal stub types for Phase A and regenerate in Phase B, (3) Implement fallback stub generation in `scripts/generate-api.js` when spec fetch fails. Document decision in plan.

### Question 3: What Is Expected Backend Health Endpoint Contract?

- **Question**: Plan assumes backend exposes `/api/health` endpoint (`docs/features/phase_a_foundation/plan.md:380-385`), but doesn't specify response format. Should response be empty (200 OK), JSON `{ status: 'ok' }`, or detailed health object? Vite backend proxy plugin probes `/api/health` at startup (`vite.config.ts:7`), and Playwright service startup will poll this endpoint (when implemented).

- **Why it matters**: Health check polling logic depends on response format. If backend returns 200 with empty body, polling logic should check `response.ok()`. If backend returns structured JSON, polling should validate shape. Mismatched expectations cause startup failures.

- **Desired answer**: Backend team confirms health endpoint response format. Update plan and Vite proxy plugin to match. Add example response in plan Section 4 (API / Integration Surface).

---

## 10) Risks & Mitigations (top 3)

### Risk 1: Phase B Feature Tests Cannot Be Written Without Test Infrastructure

- **Risk**: Phase B implements device list, editor, and CRUD operations but cannot write deterministic tests without service isolation, test events, API factories, and page objects. Tests resort to `page.waitForTimeout(1000)` and brittle selectors. Test suite becomes flaky and unmaintainable.

- **Mitigation**: Complete test infrastructure (Slices 5-8) before Phase B begins, OR pair Phase B feature work with incremental test infrastructure (implement fixtures and page objects for device list before implementing device editor). Document test infrastructure completion as Phase B prerequisite in plan.

- **Evidence**: Missing `tests/support/fixtures.ts`, `tests/support/process/servers.ts`, `tests/api/factories/config-factory.ts`, `tests/support/page-objects/devices-page.ts` per Finding: Major — Test Infrastructure Incomplete. Plan Sections 6-8 specify these deliverables.

### Risk 2: API Generation Build Dependency Blocks CI/CD

- **Risk**: Fresh repo clone cannot build without running backend and executing `pnpm generate:api`. CI/CD pipelines fail unless backend service is started in CI or generated files are committed. Developer onboarding friction increases (must start backend before first build).

- **Mitigation**: Implement one of three solutions from Finding: Major — API Generation Cannot Run Without Backend. Recommended: Commit initial stub types to repo, update `.gitignore` to allow `src/lib/api/generated/*.ts`, and document regeneration workflow. Alternative: Add fallback stub generation in `scripts/generate-api.js` that creates empty types if spec fetch fails.

- **Evidence**: `.gitignore:35` excludes generated files, `package.json:9` build script requires cached spec per `scripts/fetch-openapi.js:122-130`. Plan Section 2 (Slice 2) specifies API generation but doesn't address build-time dependency.

### Risk 3: Instrumentation Stubs Create False Sense of Test Mode Readiness

- **Risk**: Phase A setup calls `setupConsolePolicy()`, `setupErrorInstrumentation()`, `setupRouterInstrumentation()` in test mode, but functions are empty stubs. Developers assume test instrumentation is working and write tests that rely on events, but events are never emitted. Tests pass locally (due to timing luck) but fail in CI (due to race conditions).

- **Mitigation**: Add TODO comments and console warnings in stub functions to clarify incomplete implementation:
  ```typescript
  export function setupConsolePolicy() {
    if (import.meta.env.DEV) {
      console.warn('[Test Mode] console-policy stub is active; console errors are not tracked')
    }
    // TODO(Phase B): Implement console interception and ConsoleEvent emission
  }
  ```
  OR: Defer instrumentation setup calls until Phase B implements full logic (remove calls from `main.tsx` and `App.tsx`, add back when event system exists).

- **Evidence**: `src/lib/test/console-policy.ts:6-9`, `src/lib/test/error-instrumentation.ts:6-9`, `src/lib/test/router-instrumentation.ts:8-12` are empty stubs called from `main.tsx:10-12` and `App.tsx:12-13`. Finding: Major — Instrumentation Hooks Are Empty Stubs.

---

## 11) Confidence

**Confidence: High** — The core Phase A implementation (Slices 1-4, 9-10) is well-executed and production-ready. The code follows React 19 and TypeScript best practices, uses established libraries (TanStack Router/Query, Vite, Tailwind CSS 4), and ships a polished dark mode UI. The major gaps (test infrastructure Slices 5-8) are clearly documented in `PHASE_A_COMPLETE.md` and don't affect Phase A functionality. The findings focus on completeness relative to plan specification rather than code quality. With conditions addressed (test infrastructure completion or explicit deferral decision), this foundation supports Phase B development.
