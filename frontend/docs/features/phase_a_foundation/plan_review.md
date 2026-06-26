# Phase A: Foundation & Test Infrastructure - Plan Review

## 1) Summary & Decision

**Readiness**

The plan is comprehensive, well-researched, and closely follows the proven ElectronicsInventory patterns. It demonstrates thorough understanding of the Playwright per-worker isolation model, test event system, and TanStack Router/Query architecture. Research findings are documented with specific file references, and most open questions have been pre-resolved. The plan correctly identifies the backend health endpoint (`/api/health`) and config storage mechanism (`ESP32_CONFIGS_DIR`). However, there is one significant issue with the backend testing script compatibility that requires verification before implementation can proceed safely.

**Decision**

`GO-WITH-CONDITIONS` — The plan is implementation-ready but has one condition: verify that the backend `testing-server.sh` properly respects `ESP32_CONFIGS_DIR` environment variable (currently the script contains legacy SQLite references from ElectronicsInventory). Additionally, three minor clarifications should be addressed early in implementation to avoid blockers.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/product_brief.md` — Pass — `plan.md:46-49`, `plan.md:64-67`
  - Plan correctly implements routes `/` redirect to `/devices`, dark mode interface, sidebar with "Device Configs" navigation
  - Quote: "Sidebar shows 'Device Configs' navigation item with active state" aligns with product brief lines 36-39

- `docs/implementation_plan.md` — Pass — `plan.md:63-96`
  - Plan follows Phase A scope exactly: scaffolding, app shell, Playwright infrastructure before feature work
  - Quote: "Phase A must be fully working before Phase B begins" (implementation_plan.md:9)

- `docs/playwright_implementation_plan.md` — Pass — `plan.md:219-312`
  - All Playwright phases (1-10) are represented in the plan's affected areas and slices
  - Per-worker isolation, test events, API factories match the architecture diagram (playwright_implementation_plan.md:9-31)

- `docs/contribute/architecture/application_overview.md` — Pass — `plan.md:159-177`
  - Plan follows domain-driven folder layout (`src/components/<domain>`, `src/hooks`, `src/lib/{api,test,utils}`)
  - Generated API hooks and custom wrapper pattern documented at `plan.md:205-217`

- `docs/contribute/testing/playwright_developer_guide.md` — Pass — `plan.md:448-463`
  - Test event emission flow matches documented pattern (developer_guide.md:130-152)
  - API-first data setup principle followed via config factories

- `CLAUDE.md` — Pass — `plan.md:104-106`
  - Test mode tree-shaking via Vite `define` config aligns with CLAUDE.md guideline 3 ("Keep instrumentation behind `isTestMode()`")

**Fit with codebase**

- `TanStack Router file-based routing` — `plan.md:193-196` — Confirmed alignment with `src/routes/` structure from application_overview.md:8

- `Generated API hooks` — `plan.md:205-217` — Follows pattern: generated types at `src/lib/api/generated/`, custom hooks wrap queries

- `Test mode detection` — `plan.md:177-178` — Uses same `isTestMode()` pattern as ElectronicsInventory reference

- `Playwright fixtures structure` — `plan.md:247-251` — Matches `tests/support/fixtures.ts` pattern from factories_and_fixtures.md:30-47

---

## 3) Open Questions & Ambiguities

- Question: Does the backend `testing-server.sh` properly support `ESP32_CONFIGS_DIR` environment variable?
- Why it matters: The plan assumes backend can be started with `ESP32_CONFIGS_DIR` pointing to a temp directory (`plan.md:437-439`), but `/work/backend/scripts/testing-server.sh` contains legacy ElectronicsInventory references (`--sqlite-db`, "Electronics Inventory backend") and does not explicitly handle `ESP32_CONFIGS_DIR`
- Needed answer: **RESEARCHED** - The backend Flask app reads `ESP32_CONFIGS_DIR` from environment via Pydantic Settings (`/work/backend/app/config.py:25-27`). The `testing-server.sh` script just needs to have `ESP32_CONFIGS_DIR` set in the environment before calling `flask run`. The script cosmetic issues (wrong product name) do not affect functionality. **RESOLVED** - environment variable passthrough works as designed.

- Question: What is the exact OpenAPI spec format at `/api/docs`?
- Why it matters: Plan references `GET /api/docs` returning OpenAPI JSON (`plan.md:387-392`), but actual endpoint redirects to Swagger UI
- Needed answer: **RESEARCHED** - `/work/backend/app/utils/spectree_config.py:27` shows `path="api/docs"` for SpectTree. The raw JSON spec is typically at `/api/docs/openapi.json` per SpectTree conventions. The `generate-api.js` script must be updated to fetch from correct endpoint. **PARTIALLY RESOLVED** - need to verify exact JSON endpoint path during Slice 2 implementation.

- Question: Console error filtering strategy - how to handle expected errors?
- Why it matters: Plan mentions "expected error registration pattern from ElectronicsInventory" (`plan.md:937-940`) but does not detail implementation
- Needed answer: Referenced at `playwright_developer_guide.md:119-126` via `expectConsoleError(page, /pattern/)` helper. Plan should implement this helper in Slice 7. **RESOLVED**.

---

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: App shell renders with sidebar navigation
- Scenarios:
  - Given services are running, When test navigates to frontend URL, Then sidebar is visible with test ID `app-shell.sidebar` (`tests/smoke.spec.ts`)
- Instrumentation: `data-testid="app-shell.sidebar"`, `data-testid="app-shell.sidebar.link.devices"`
- Backend hooks: None required - static UI test
- Gaps: None
- Evidence: `plan.md:690-700`

- Behavior: Root route redirects to /devices
- Scenarios:
  - Given frontend is running, When test navigates to `/`, Then URL changes to `/devices` (`tests/smoke.spec.ts`)
- Instrumentation: Router instrumentation emits route events (optional for Phase A)
- Backend hooks: None required
- Gaps: Smoke test does not explicitly verify redirect (only final state). Consider adding redirect assertion.
- Evidence: `plan.md:192-193`, `plan.md:713-723`

- Behavior: Backend health endpoint responds
- Scenarios:
  - Given backend service is running, When test fetches `{backendUrl}/api/health`, Then response status is 200 (`tests/smoke.spec.ts`)
- Instrumentation: None (direct HTTP fetch)
- Backend hooks: `/api/health` endpoint (verified exists at `/work/backend/app/api/health.py`)
- Gaps: None
- Evidence: `plan.md:702-711`

- Behavior: Device list placeholder loads
- Scenarios:
  - Given frontend is running, When test navigates to `/devices`, Then placeholder content is visible with test ID `device-list-placeholder` (`tests/smoke.spec.ts`)
- Instrumentation: `data-testid="device-list-placeholder"` on placeholder component
- Backend hooks: None required (no data fetching in Phase A placeholder)
- Gaps: None
- Evidence: `plan.md:713-723`

- Behavior: Service isolation per worker
- Scenarios:
  - Given multiple workers running in parallel, When each worker starts services, Then each worker has unique backend/frontend URLs
- Instrumentation: Service URLs in worker fixture metadata
- Backend hooks: Port allocation via `get-port`
- Gaps: No explicit test for isolation - validated implicitly by parallel test runs
- Evidence: `plan.md:737-748`

- Behavior: API factory creates/deletes configs
- Scenarios:
  - Given backend service is running, When factory calls `PUT /api/configs/{mac}`, Then config is created
  - When factory calls `DELETE /api/configs/{mac}`, Then config is removed
- Instrumentation: None (API-level validation)
- Backend hooks: `PUT /api/configs/{mac_address}`, `DELETE /api/configs/{mac_address}`
- Gaps: No dedicated test - validated during smoke test setup or Phase B tests
- Evidence: `plan.md:750-761`

---

## 5) Adversarial Sweep

**Major — Backend testing script may require adaptation**

**Evidence:** `/work/backend/scripts/testing-server.sh:82-84` — `"Starting Electronics Inventory backend in testing mode..."`

**Why it matters:** The backend testing script contains hardcoded references to "Electronics Inventory" and includes `--sqlite-db` argument handling that is not relevant to IoT Support's JSON file storage. While the script will functionally work (Flask reads `ESP32_CONFIGS_DIR` from environment), the cosmetic issues could cause confusion during debugging and the SQLite-specific code paths are dead weight.

**Fix suggestion:** Before Slice 5, verify backend team has updated `testing-server.sh` to:
1. Update echo messages to say "IoT Support"
2. Remove `--sqlite-db` argument parsing (not applicable)
3. Optionally add `--config-dir` argument for explicit temp directory override

**Confidence:** Medium — Functional impact is low but maintenance burden exists.

---

**Major — Vite proxy configuration for backend during dev may fail silently**

**Evidence:** `plan.md:529-533` — "Vite proxy cannot reach backend at `localhost:3201`... `backendProxyStatusPlugin` logs warning but allows dev server to start"

**Why it matters:** Plan correctly identifies this edge case, but the mitigation (logging a warning) may not be sufficient for new developers who don't notice the warning. If `pnpm dev` succeeds but API calls fail, debugging could be frustrating.

**Fix suggestion:** In `vite.config.ts`, add a more prominent startup banner when backend probe fails:
```typescript
console.warn('\n⚠️  Backend not responding at localhost:3201');
console.warn('    Run backend first: cd ../backend && ./scripts/dev-server.sh\n');
```

**Confidence:** Medium — Developer experience issue, not a functional blocker.

---

**Minor — Missing explicit test for test event emission/capture**

**Evidence:** `plan.md:763-773` — "Integration Test: Test Event Capture" lists scenario but not included in `tests/smoke.spec.ts`

**Why it matters:** The test event system is critical infrastructure. While it will be implicitly validated in Phase B when list loading events are used, having an explicit smoke test for event emission would catch regressions earlier.

**Fix suggestion:** Add a fourth smoke test to `tests/smoke.spec.ts`:
```typescript
test('test event bridge captures events', async ({ page, testEvents }) => {
  await page.goto('/devices');
  // Trigger a navigation event (router instrumentation emits)
  const events = testEvents.getEvents();
  expect(events.length).toBeGreaterThan(0);
});
```

**Confidence:** Low — Nice-to-have, not blocking.

---

**Minor — Toast system stub may cause TypeScript errors**

**Evidence:** `plan.md:182-184` — "Create `__root.tsx` layout with QueryClientProvider, ToastProvider placeholder, app shell frame"

**Why it matters:** If ToastProvider is stubbed but QueryClient's `onError` handler tries to call toast functions, TypeScript strict mode or runtime errors may occur. The plan mentions "Placeholder toast context (stub)" in Slice 3 but does not detail implementation.

**Fix suggestion:** Ensure ToastProvider stub exports no-op functions that match expected signature:
```typescript
export const ToastContext = createContext({
  showToast: (_: ToastOptions) => {},
  dismissToast: (_: string) => {},
});
```
This prevents errors when error handling code calls toast functions before Phase B.

**Confidence:** Medium — Could cause early integration issues if not handled.

---

## 6) Derived-Value & State Invariants

- Derived value: Active navigation item
  - Source dataset: Current route path from TanStack Router
  - Write / cleanup triggered: CSS class toggle on sidebar links (no persistent state)
  - Guards: Router `activeProps` mechanism handles automatically
  - Invariant: Exactly one navigation item has active styling when on `/devices` route
  - Evidence: `plan.md:467-476`

- Derived value: Test mode flag (`isTestMode()`)
  - Source dataset: `import.meta.env.VITE_TEST_MODE` (compile-time constant)
  - Write / cleanup triggered: Gates all instrumentation code paths
  - Guards: Production builds force `VITE_TEST_MODE='false'` via Vite `define` config
  - Invariant: Test instrumentation must never execute in production bundles
  - Evidence: `plan.md:478-485`

- Derived value: Service URLs per worker
  - Source dataset: `get-port` allocated ports combined with `127.0.0.1` host
  - Write / cleanup triggered: Service manager creates/destroys processes; temp directories cleaned on worker teardown
  - Guards: Port exclusion list prevents conflicts; temp dir uses random suffix
  - Invariant: Each worker has unique, non-overlapping backend and frontend URLs
  - Evidence: `plan.md:487-494`

- Derived value: Test event buffer contents
  - Source dataset: Events emitted by frontend via `window.__playwright_emitTestEvent`
  - Write / cleanup triggered: Buffer appends events; clears between tests via `testEvents.clear()`
  - Guards: Hard cap at 500 events throws overflow error
  - Invariant: Buffer must not exceed capacity; events maintain chronological order
  - Evidence: `plan.md:507-514`

---

## 7) Risks & Mitigations (top 3)

- Risk: Backend testing script contains ElectronicsInventory-specific code that may confuse developers or require adaptation
- Mitigation: Verify with backend team that `testing-server.sh` has been updated for IoT Support before starting Slice 5; cosmetic issues do not block functionality but should be cleaned up
- Evidence: `plan.md:891-896`, `/work/backend/scripts/testing-server.sh:82-84`

- Risk: OpenAPI spec endpoint may not be at expected path, breaking API generation
- Mitigation: During Slice 2, test `scripts/generate-api.js` against running backend to confirm spec fetch succeeds; update endpoint path from `/api/docs` to `/api/docs/openapi.json` if needed
- Evidence: `plan.md:897-902`, `/work/backend/app/utils/spectree_config.py:27`

- Risk: Port allocation conflicts in CI environment with parallel jobs
- Mitigation: Use `get-port` with exclusion lists as documented; CI configuration should limit workers to 1 (`process.env.CI ? 1 : 2` in playwright.config.ts) to reduce contention
- Evidence: `plan.md:903-908`, `playwright_implementation_plan.md:57`

---

## 8) Confidence

Confidence: High — The plan is thorough, well-researched, and based on proven patterns from ElectronicsInventory. All major architectural decisions are supported by evidence from reference implementations. The conditions identified are minor and can be resolved during early implementation slices without blocking subsequent work. The implementation order (scaffolding -> app shell -> Playwright infra -> smoke tests) is logical and allows incremental validation.
