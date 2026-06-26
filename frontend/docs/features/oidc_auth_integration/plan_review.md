# Plan Review: OIDC Authentication Integration (Revised)

## 1) Summary & Decision

**Readiness**

The revised plan demonstrates strong alignment with the project's architecture patterns and has addressed the critical gaps identified in the initial review. The Blocking Issues section now explicitly documents backend test auth requirements with specific endpoint contracts. The plan correctly identifies the generated API hooks, context provider patterns, test instrumentation requirements, and includes the new `auth.redirecting` event needed for deterministic redirect testing. The query cache key has been corrected, and 401 detection logic is now specified.

**Decision**

`GO` — The plan is implementation-ready. All major concerns have been addressed: (1) backend test requirements are documented in the Blocking Issues section, (2) the query cache key is correct, (3) the `auth.redirecting` instrumentation event enables deterministic testing without route mocking, and (4) the 401 detection logic is specified. The Playwright test slice is explicitly marked as blocked pending backend support, which aligns with project policy.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/commands/plan_feature.md` — Pass — Plan follows all 16 required sections with proper template usage
- `docs/product_brief.md` — Pass — `plan.md:46-50` correctly identifies this as adding authentication to a previously no-auth app
- `docs/contribute/architecture/application_overview.md` — Pass — `plan.md:116-118` follows context provider pattern per `application_overview.md:54-58`
- `docs/contribute/testing/playwright_developer_guide.md` — Pass — `plan.md:3-15` includes Blocking Issues section per `playwright_developer_guide.md:161-164`
- `docs/contribute/testing/index.md` — Pass — `index.md:50-51` requirement for Blocking Issues section is satisfied at `plan.md:3-15`

**Fit with codebase**

- `src/contexts/toast-context.tsx` — `plan.md:116-118` — Pattern alignment confirmed; AuthContext follows same createContext/useContext/Provider structure
- `src/routes/__root.tsx` — `plan.md:146-148` — Correctly identifies integration point; layout restructure scope is accurate
- `src/lib/api/generated/hooks.ts:113-124` — `plan.md:193-195` — Query cache key now correctly documented as `['getAuthSelf', params]`
- `src/components/layout/sidebar.tsx` — `plan.md:150-152` — Header section removal scope is accurate per lines 39-60
- `tests/support/fixtures.ts` — `plan.md:158-160` — Fixture extension point correctly identified

---

## 3) Open Questions & Ambiguities

- Question: Should the user dropdown show email if name is null?
- Why it matters: "Unknown User" may be less useful than showing email address
- Needed answer: Product decision; plan correctly defers to requirement stating "Unknown User" but notes email could be fallback

This question does not block implementation as the plan specifies a clear default behavior.

---

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Auth loading state display
- Scenarios:
  - Given backend is slow to respond, When app loads, Then loading indicator is visible (`tests/e2e/auth/auth.spec.ts`)
- Instrumentation: `data-testid="auth.gate.loading"`, `ui_state` event `{ scope: 'auth', phase: 'loading' }`
- Backend hooks: None required
- Gaps: None
- Evidence: `plan.md:465-473`

---

- Behavior: Login redirect on 401
- Scenarios:
  - Given user session is not present, When app loads, Then `auth.redirecting` event is emitted with correct target URL
  - Given redirect target URL includes query params, When redirect triggers, Then full path is preserved
- Instrumentation: `ui_state` event `{ scope: 'auth', phase: 'redirecting', metadata: { targetUrl } }`
- Backend hooks: `POST /api/testing/auth/clear`
- Gaps: None - redirect verified via instrumentation event
- Evidence: `plan.md:475-484`

---

- Behavior: Auth error with retry
- Scenarios:
  - Given backend returns 500, When app loads, Then error screen displays
  - Given error screen visible, When retry clicked, Then auth check re-executes
- Instrumentation: `data-testid="auth.gate.error"`, `data-testid="auth.gate.error.retry"`, `ui_state` event `{ scope: 'auth', phase: 'error' }`
- Backend hooks: `POST /api/testing/auth/force-error?status=500`
- Gaps: Depends on backend endpoint (documented in Blocking Issues)
- Evidence: `plan.md:486-495`

---

- Behavior: Authenticated user display
- Scenarios:
  - Given user authenticated with name, When app loads, Then top bar shows name
  - Given user authenticated with null name, When app loads, Then top bar shows "Unknown User"
- Instrumentation: `data-testid="app-shell.topbar.user.name"`, `ui_state` event `{ scope: 'auth', phase: 'ready' }`
- Backend hooks: `POST /api/testing/auth/session`
- Gaps: Depends on backend endpoint (documented in Blocking Issues)
- Evidence: `plan.md:497-506`

---

- Behavior: Logout flow
- Scenarios:
  - Given user authenticated, When logout clicked, Then browser navigates to `/api/auth/logout`
- Instrumentation: `data-testid="app-shell.topbar.user.logout"`
- Backend hooks: `POST /api/testing/auth/session`
- Gaps: None once backend test auth available
- Evidence: `plan.md:508-517`

---

- Behavior: Sidebar collapse to zero width
- Scenarios:
  - Given sidebar expanded, When hamburger clicked, Then sidebar width becomes 0
- Instrumentation: `data-testid="app-shell.topbar.hamburger"`, `data-testid="app-shell.sidebar"` with `data-state`
- Backend hooks: None required
- Gaps: None
- Evidence: `plan.md:519-527`

---

## 5) Adversarial Sweep (must find >=3 credible issues or declare why none exist)

- Checks attempted:
  - Backend test auth mechanism specification
  - Query cache key accuracy
  - Redirect instrumentation for deterministic testing
  - 401 detection logic specification
  - Context provider pattern alignment
  - Mobile menu state handling
  - Error boundary and retry logic

- Evidence:
  - `plan.md:3-15` — Blocking Issues section with concrete endpoint contracts
  - `plan.md:193-195` — Corrected query cache key
  - `plan.md:368-373` — New `auth.redirecting` event specification
  - `plan.md:120-122` — 401 detection logic documented

- Why the plan holds: The major issues identified in the initial review have been addressed:
  1. Backend test requirements are now explicit with endpoint contracts
  2. Query cache key matches the generated hook
  3. Redirect flow is testable via `auth.redirecting` event
  4. 401 detection logic is specified as `error instanceof ApiError && error.status === 401`

---

## 6) Derived-Value & State Invariants (table)

- Derived value: `isAuthenticated`
  - Source dataset: `user !== null` from AuthContext (unfiltered)
  - Write / cleanup triggered: Triggers redirect when false after loading completes
  - Guards: Only redirects when `!isLoading && !isAuthenticated`
  - Invariant: Children of AuthGate never render when `isAuthenticated === false`
  - Evidence: `plan.md:286-291`

---

- Derived value: `displayName`
  - Source dataset: `user.name ?? 'Unknown User'` (unfiltered)
  - Write / cleanup triggered: None (read-only display)
  - Guards: Null-coalescing to fallback string
  - Invariant: Display string is never empty/null in rendered UI
  - Evidence: `plan.md:279-284`

---

- Derived value: `loginRedirectUrl`
  - Source dataset: `window.location.pathname + window.location.search` (unfiltered)
  - Write / cleanup triggered: Passed to `/api/auth/login?redirect=` as query param
  - Guards: Must be URL-encoded
  - Invariant: User returns to exact attempted path after successful login
  - Evidence: `plan.md:293-298`

---

- Derived value: `sidebarCollapsed` state
  - Source dataset: Local React state (boolean toggle)
  - Write / cleanup triggered: Controls sidebar width (0 vs full width)
  - Guards: None
  - Invariant: State and visual width always match
  - Evidence: `plan.md:251-261`

---

## 7) Risks & Mitigations (top 3)

- Risk: Backend test auth endpoints may not be implemented in time
- Mitigation: Blocking Issues section documents concrete requirements; UI slices proceed independently; backend coordination happens in parallel
- Evidence: `plan.md:595-597`

---

- Risk: OIDC redirect may break Playwright test isolation
- Mitigation: `auth.redirecting` event allows verification without following redirect; `POST /api/testing/auth/clear` provides test isolation
- Evidence: `plan.md:599-601`

---

- Risk: Logo sizing varies across browsers/fonts
- Mitigation: Use relative units (em); defer precise verification to visual regression testing
- Evidence: `plan.md:603-605`

---

## 8) Confidence

Confidence: High — The plan addresses all critical issues from the initial review. Backend test requirements are explicitly documented with concrete endpoint contracts. The new `auth.redirecting` instrumentation event enables deterministic testing of the redirect flow. The UI implementation path is well-defined with clear slice boundaries. The Playwright test slice is correctly marked as blocked pending backend support, which aligns with project policy for features requiring backend coordination.
