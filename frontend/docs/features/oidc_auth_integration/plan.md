# OIDC Authentication Integration - Technical Plan

## Blocking Issues

The following backend dependencies must be resolved before the Playwright test slice can proceed:

1. **Test Authentication Mechanism** - Backend must provide a way for Playwright tests to authenticate without going through the real OIDC flow. Required endpoints:
   - `POST /api/testing/auth/session` - Create an authenticated session with controllable user fields (`name`, `email`, `roles`, `subject`). Accepts JSON body with user properties and sets the session cookie.
   - `POST /api/testing/auth/clear` - Clear the current session (for test isolation between specs).
   - These endpoints should only be available when the backend is running in test mode.

2. **Error Simulation for Auth** - Backend should support triggering deterministic error responses:
   - `POST /api/testing/auth/force-error?status=500` - Configure `/api/auth/self` to return the specified status code on the next request (for testing error/retry flows).

Without these backend capabilities, the auth-related Playwright tests cannot be written deterministically per the project's `testing/no-route-mocks` policy.

---

## 0) Research Log & Findings

### Areas Searched

- **Generated API hooks**: Found `useGetAuthSelf` in `src/lib/api/generated/hooks.ts:113-124` returns `UserInfoResponseSchema_a535b8c` with fields: `email`, `name` (nullable), `roles`, `subject`
- **Root layout**: Current layout in `src/routes/__root.tsx` uses `QueryClientProvider`, `ToastProvider`, and `AppShellFrame` with sidebar toggle state
- **Sidebar component**: `src/components/layout/sidebar.tsx` contains navigation items, collapsible state, and header with "IoT Support" text
- **Context patterns**: `src/contexts/toast-context.tsx` shows the existing provider pattern with `createContext`, `useContext`, and provider component
- **Test instrumentation**: `src/lib/test/event-emitter.ts` shows `emitTestEvent` pattern; `src/types/test-events.ts` defines event types including `ui_state` and `list_loading`
- **Query client**: `src/lib/query-client.ts` shows centralized error handling and retry logic
- **Favicon location**: `public/favicon.png` exists and will be used as logo
- **Existing Playwright tests**: `tests/e2e/devices/` shows page object pattern and fixture usage

### Key Patterns Identified

1. **Context providers** wrap the app in `__root.tsx` with children rendered via `<Outlet />`
2. **Generated hooks** return snake_case data; custom hooks in `src/hooks/` typically transform to camelCase
3. **Test instrumentation** uses `isTestMode()` guard and `emitTestEvent()` for Playwright synchronization
4. **Data attributes** follow `feature.section.element` naming (e.g., `app-shell.sidebar.toggle`)

### Conflicts Resolved

- The `/api/auth/login` and `/api/auth/logout` endpoints perform redirects (302) - they cannot be called via TanStack Query hooks. Direct `window.location.href` assignment is required.
- The `useGetAuthSelf` hook returns `UserInfoResponseSchema_a535b8c` but we need to transform to camelCase and handle the nullable `name` field.

---

## 1) Intent & Scope

**User intent**

Integrate OIDC authentication into the frontend so that all routes are protected. On app load, the frontend checks authentication status via `/api/auth/self`. If unauthenticated, the user is redirected to the OIDC login flow. The layout must be restructured to display a top bar with hamburger, logo, app title, and user dropdown, with the left menu collapsing completely when toggled.

**Prompt quotes**

- "Call /api/auth/self on app load to check authentication status"
- "Redirect to /api/auth/login?redirect=<current_path> when 401 is received"
- "Entire app is protected - no public routes"
- "Auth Gate/Provider pattern - suspend all rendering until auth response received"
- "New top bar layout: hamburger | logo (favicon) | 'IoT Support' | spacer | user full name ▾"
- "Left menu collapses completely when hamburger is clicked"
- "Logout redirects directly to /api/auth/logout (no confirmation dialog)"

**In scope**

- AuthProvider/AuthContext with user state and loading management
- AuthGate component that suspends rendering until auth check completes
- Redirect to OIDC login on 401 with path preservation
- Error screen with retry for non-401 errors
- Restructured layout: top bar + collapsible left menu
- User dropdown with logout option
- Mobile experience with overlay menu
- Playwright test coverage for auth flows

**Out of scope**

- Backend OIDC implementation (already complete)
- Role-based access control within the app
- Session refresh/token renewal logic
- Remember me / persistent session preferences

**Assumptions / constraints**

- Backend `/api/auth/self` returns 200 with user info when authenticated, 401 when not
- Backend `/api/auth/login?redirect=<url>` initiates OIDC flow and returns to specified URL after success
- Backend `/api/auth/logout` clears session and redirects to `/`
- Favicon at `public/favicon.png` is suitable for use as logo
- Authentication state does not need background polling (cookie-based session managed by backend)

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Call /api/auth/self on app load to check authentication status
- [ ] Redirect to /api/auth/login?redirect=<current_path> when 401 is received
- [ ] Preserve full path in redirect parameter so user returns there after login
- [ ] Entire app is protected - no public routes
- [ ] New top bar layout: hamburger | logo (favicon) | "IoT Support" | spacer | user full name ▾
- [ ] Logo displayed at 110% of text height
- [ ] Logo and "IoT Support" text link to home/root route
- [ ] User dropdown menu contains only logout option
- [ ] Left menu collapses completely when hamburger is clicked (desktop)
- [ ] Maintain current dark zinc theme (bg-zinc-950, border-zinc-800)
- [ ] Display "Unknown User" if user's name field is null
- [ ] Logout redirects directly to /api/auth/logout (no confirmation dialog)
- [ ] Auth Gate/Provider pattern - suspend all rendering until auth response received
- [ ] Show error screen with retry option for non-401 errors (e.g., 500)
- [ ] Create proper mobile experience with top bar and overlay menu

---

## 2) Affected Areas & File Map

### New Files

- Area: `src/contexts/auth-context.tsx`
- Why: Provides auth state (user, loading, error) and logout action to the component tree
- Evidence: Pattern from `src/contexts/toast-context.tsx:28-69`

- Area: `src/hooks/use-auth.ts`
- Why: Custom hook wrapping `useGetAuthSelf` with camelCase transformation and 401 detection. The hook must detect 401 errors by checking `error instanceof ApiError && error.status === 401` to differentiate from server errors (500+).
- Evidence: Pattern from `src/hooks/use-devices.ts`; error detection via `src/lib/api/api-error.ts`

- Area: `src/components/layout/top-bar.tsx`
- Why: New top bar component with hamburger, logo, title, and user dropdown
- Evidence: Layout requirements from change brief

- Area: `src/components/layout/user-dropdown.tsx`
- Why: Dropdown menu showing user name and logout option
- Evidence: Requirement "User dropdown menu contains only logout option"

- Area: `src/components/auth/auth-gate.tsx`
- Why: Component that suspends rendering until auth state resolves, shows error screen for failures
- Evidence: Requirement "Auth Gate/Provider pattern - suspend all rendering until auth response received"

- Area: `tests/e2e/auth/auth.spec.ts`
- Why: Playwright tests for authentication flows
- Evidence: Test pattern from `tests/e2e/devices/devices-crud.spec.ts`

- Area: `tests/e2e/auth/AuthPage.ts`
- Why: Page object for auth-related test helpers
- Evidence: Pattern from `tests/e2e/devices/DevicesPage.ts`

### Modified Files

- Area: `src/routes/__root.tsx`
- Why: Integrate AuthProvider, restructure layout to use top bar + collapsible left menu
- Evidence: `src/routes/__root.tsx:12-99` current layout structure

- Area: `src/components/layout/sidebar.tsx`
- Why: Remove header section (moved to top bar), simplify to navigation-only component
- Evidence: `src/components/layout/sidebar.tsx:39-60` header section to remove

- Area: `src/lib/api/api-error.ts`
- Why: Add status property extraction for 401 detection
- Evidence: `src/lib/api/api-error.ts:22-31` existing status handling

- Area: `tests/support/fixtures.ts`
- Why: Add auth-related test fixtures if needed
- Evidence: `tests/support/fixtures.ts:24-97` fixture pattern

---

## 3) Data Model / Contracts

- Entity / contract: `UserInfo` (frontend model)
- Shape:
  ```typescript
  interface UserInfo {
    email: string | null
    name: string | null
    roles: string[]
    subject: string
  }
  ```
- Mapping: Direct 1:1 mapping from `UserInfoResponseSchema_a535b8c` (fields are already in expected casing)
- Evidence: `src/lib/api/generated/types.ts:445-466`

- Entity / contract: `AuthState` (context state)
- Shape:
  ```typescript
  interface AuthState {
    user: UserInfo | null
    isLoading: boolean
    isAuthenticated: boolean
    error: Error | null
  }
  ```
- Mapping: Derived from query state; `isAuthenticated` is true when user is non-null
- Evidence: New type for auth context

- Entity / contract: Query cache key
- Shape: `['getAuthSelf', params]` (where `params` is typically `undefined` for this endpoint)
- Mapping: Used by `useGetAuthSelf` hook; must match when invalidating queries
- Evidence: `src/lib/api/generated/hooks.ts:116` - `queryKey: ['getAuthSelf', params]`

---

## 4) API / Integration Surface

- Surface: `GET /api/auth/self` via `useGetAuthSelf`
- Inputs: None (relies on HTTP-only cookie)
- Outputs: 200 with `UserInfoResponseSchema` or 401 for unauthenticated
- Errors: 401 triggers redirect to login; 500+ shows error screen with retry
- Evidence: `src/lib/api/generated/hooks.ts:113-124`

- Surface: `GET /api/auth/login?redirect=<url>` (direct navigation)
- Inputs: `redirect` query parameter with current path
- Outputs: 302 redirect to OIDC provider
- Errors: N/A (browser handles redirect)
- Evidence: `src/lib/api/generated/types.ts:80-95`

- Surface: `GET /api/auth/logout` (direct navigation)
- Inputs: None
- Outputs: 302 redirect to root with session cleared
- Errors: N/A (browser handles redirect)
- Evidence: `src/lib/api/generated/types.ts:97-119`

---

## 5) Algorithms & UI Flows

### Authentication Check Flow

- Flow: App initialization authentication check
- Steps:
  1. App mounts, AuthProvider renders
  2. AuthProvider calls `/api/auth/self` via `useGetAuthSelf`
  3. While loading: AuthGate shows loading spinner, children are not rendered
  4. On 401: Capture current URL path, redirect to `/api/auth/login?redirect=<path>`
  5. On success: Store user in context, render children via AuthGate
  6. On non-401 error: Show error screen with retry button
- States / transitions: `loading` -> `authenticated` | `unauthenticated` | `error`
- Hotspots: Must block all child rendering until auth resolves to prevent flicker
- Evidence: Requirement "Auth Gate/Provider pattern - suspend all rendering until auth response received"

### Logout Flow

- Flow: User-initiated logout
- Steps:
  1. User clicks user name in top bar
  2. Dropdown appears with "Logout" option
  3. User clicks "Logout"
  4. Browser navigates to `/api/auth/logout`
  5. Backend clears session, redirects to `/`
  6. App reloads, auth check finds 401, redirects to login
- States / transitions: `authenticated` -> browser navigation -> (backend handles)
- Hotspots: No confirmation dialog required
- Evidence: Requirement "Logout redirects directly to /api/auth/logout (no confirmation dialog)"

### Sidebar Toggle Flow

- Flow: Desktop sidebar collapse/expand
- Steps:
  1. User clicks hamburger in top bar
  2. `sidebarCollapsed` state toggles
  3. Left menu collapses completely (width: 0) or expands (width: 64/256)
  4. Content area expands to fill available space
- States / transitions: `collapsed` <-> `expanded`
- Hotspots: Transition animation should be smooth (existing `transition-all duration-300`)
- Evidence: `src/components/layout/sidebar.tsx:32` existing transition classes

### Mobile Menu Flow

- Flow: Mobile menu toggle
- Steps:
  1. User clicks hamburger in top bar (mobile)
  2. `mobileMenuOpen` state toggles
  3. Overlay appears with menu content
  4. User taps outside or selects item to close
- States / transitions: `closed` <-> `open`
- Hotspots: Overlay must prevent body scroll
- Evidence: `src/routes/__root.tsx:54-69` existing mobile overlay pattern

---

## 6) Derived State & Invariants

- Derived value: `displayName`
  - Source: `user.name` from auth context
  - Writes / cleanup: None (read-only display)
  - Guards: If `name` is null, display "Unknown User"
  - Invariant: Display name is never empty/blank in the UI
  - Evidence: Requirement "Display 'Unknown User' if user's name field is null"

- Derived value: `isAuthenticated`
  - Source: `user !== null` from auth context
  - Writes / cleanup: Triggers redirect when false after initial load
  - Guards: Only redirect if not loading and not already on a redirect path
  - Invariant: Children never render when `isAuthenticated` is false
  - Evidence: Requirement "Entire app is protected - no public routes"

- Derived value: `loginRedirectUrl`
  - Source: Current `window.location.pathname + window.location.search`
  - Writes / cleanup: Passed as query param to `/api/auth/login`
  - Guards: Must be URL-encoded to preserve special characters
  - Invariant: User returns to exact path they were attempting to access
  - Evidence: Requirement "Preserve full path in redirect parameter"

---

## 7) State Consistency & Async Coordination

- Source of truth: `AuthContext` provides user state to all components
- Coordination: All components read from context; no local auth state duplication
- Async safeguards: Query is enabled only once on mount; retry is manual via error screen button
- Instrumentation: Emit `ui_state` events for auth phases: `loading`, `ready`, `error`
- Evidence: Pattern from `src/contexts/toast-context.tsx`

Query client configuration:
- Auth query does not auto-retry on 401 (existing behavior: no retry on 4xx)
- Auth query has standard staleTime (5 minutes) but effectively doesn't refetch since user stays authenticated
- Evidence: `src/lib/query-client.ts:14-28`

---

## 8) Errors & Edge Cases

- Failure: Network error during auth check
- Surface: AuthGate component
- Handling: Show error message with "Retry" button that refetches
- Guardrails: Error message is user-friendly; technical details in console
- Evidence: Requirement "Show error screen with retry option for non-401 errors"

- Failure: 500 server error from `/api/auth/self`
- Surface: AuthGate component
- Handling: Same as network error - show error screen with retry
- Guardrails: Do not redirect to login for server errors
- Evidence: Requirement "Show error screen with retry option for non-401 errors (e.g., 500)"

- Failure: 401 from `/api/auth/self`
- Surface: AuthProvider
- Handling: Redirect to `/api/auth/login?redirect=<current_path>`
- Guardrails: Not treated as an error; expected unauthenticated state
- Evidence: Requirement "Redirect to /api/auth/login?redirect=<current_path> when 401 is received"

- Failure: User has null name
- Surface: TopBar user dropdown trigger
- Handling: Display "Unknown User" instead of empty string
- Guardrails: Check for null/empty before rendering
- Evidence: Requirement "Display 'Unknown User' if user's name field is null"

---

## 9) Observability / Instrumentation

- Signal: `auth.loading`
- Type: `ui_state` test event
- Trigger: When auth check begins (query enters loading state)
- Labels / fields: `{ scope: 'auth', phase: 'loading' }`
- Consumer: Playwright `waitForUiState(page, 'auth', 'loading')`
- Evidence: Pattern from `src/types/test-events.ts:118-126`

- Signal: `auth.ready`
- Type: `ui_state` test event
- Trigger: When auth check succeeds and user is loaded
- Labels / fields: `{ scope: 'auth', phase: 'ready', metadata: { userId: user.subject } }`
- Consumer: Playwright `waitForUiState(page, 'auth', 'ready')`
- Evidence: Pattern from `src/types/test-events.ts:118-126`

- Signal: `auth.error`
- Type: `ui_state` test event
- Trigger: When auth check fails with non-401 error
- Labels / fields: `{ scope: 'auth', phase: 'error', metadata: { status: error.status } }`
- Consumer: Playwright `waitForUiState(page, 'auth', 'error')`
- Evidence: Pattern from `src/types/test-events.ts:118-126`

- Signal: `auth.redirecting`
- Type: `ui_state` test event
- Trigger: Immediately before `window.location.href` assignment for login redirect (on 401)
- Labels / fields: `{ scope: 'auth', phase: 'redirecting', metadata: { targetUrl: string } }`
- Consumer: Playwright `waitForUiState(page, 'auth', 'redirecting')` - allows tests to verify redirect was triggered without following the actual navigation
- Evidence: New event; required because Playwright cannot intercept browser redirects per `testing/no-route-mocks` policy

- Signal: Data attributes for UI elements
- Type: `data-testid` attributes
- Trigger: Static on render
- Labels / fields:
  - `app-shell.topbar` - top bar container
  - `app-shell.topbar.hamburger` - hamburger button
  - `app-shell.topbar.logo` - logo image
  - `app-shell.topbar.title` - "IoT Support" text
  - `app-shell.topbar.user` - user dropdown trigger
  - `app-shell.topbar.user.name` - user name text
  - `app-shell.topbar.user.dropdown` - dropdown menu
  - `app-shell.topbar.user.logout` - logout button
  - `auth.gate.loading` - loading screen
  - `auth.gate.error` - error screen
  - `auth.gate.error.retry` - retry button
- Consumer: Playwright locators
- Evidence: Pattern from `src/components/layout/sidebar.tsx:33-34`

---

## 10) Lifecycle & Background Work

- Hook / effect: `useGetAuthSelf` query
- Trigger cadence: On mount (once)
- Responsibilities: Fetch user info from `/api/auth/self`
- Cleanup: Query client handles cancellation on unmount
- Evidence: `src/lib/api/generated/hooks.ts:113-124`

- Hook / effect: Redirect effect in AuthProvider
- Trigger cadence: When query completes with 401 status
- Responsibilities: Capture current path, navigate to login URL
- Cleanup: None needed (navigation replaces page)
- Evidence: Will use `window.location.href` assignment

No background polling or revalidation for auth state - cookie-based session is managed by the backend.

---

## 11) Security & Permissions

- Concern: Authentication enforcement
- Touchpoints: `AuthGate` wraps all content in `__root.tsx`
- Mitigation: Children do not render until auth check completes successfully
- Residual risk: None - authentication is enforced at the root level
- Evidence: Requirement "Entire app is protected - no public routes"

- Concern: Session management
- Touchpoints: HTTP-only cookies managed by backend
- Mitigation: Frontend cannot access or modify auth tokens; relies on cookie-based auth
- Residual risk: Standard XSS considerations (mitigated by React's escaping)
- Evidence: Backend handles OIDC token storage

- Concern: Redirect URL manipulation
- Touchpoints: `redirect` query parameter to `/api/auth/login`
- Mitigation: Backend should validate redirect URL is same-origin
- Residual risk: Relies on backend validation
- Evidence: Standard OIDC security practice

---

## 12) UX / UI Impact

- Entry point: All routes (entire app)
- Change: Users must authenticate before seeing any content
- User interaction: On first visit, user sees loading state briefly, then is redirected to OIDC provider
- Dependencies: Backend OIDC endpoints
- Evidence: Requirement "Entire app is protected - no public routes"

- Entry point: Top bar (new component)
- Change: New horizontal bar at top with hamburger, logo, title, and user dropdown
- User interaction: Hamburger toggles sidebar; user dropdown shows logout option
- Dependencies: `favicon.png` for logo
- Evidence: Requirement "New top bar layout: hamburger | logo (favicon) | 'IoT Support' | spacer | user full name ▾"

- Entry point: Left menu (sidebar)
- Change: Collapses completely (0 width) when toggled instead of showing icons-only
- User interaction: Click hamburger to show/hide entire menu
- Dependencies: None
- Evidence: Requirement "Left menu collapses completely when hamburger is clicked"

- Entry point: Mobile layout
- Change: Top bar with hamburger, logo, title, user dropdown; overlay menu
- User interaction: Hamburger opens overlay; tap outside or select item to close
- Dependencies: None
- Evidence: Requirement "Create proper mobile experience with top bar and overlay menu"

---

## 13) Deterministic Test Plan

### Auth Loading State

- Surface: Auth gate component
- Scenarios:
  - Given user is not authenticated, When app loads, Then loading indicator displays before redirect
- Instrumentation / hooks: `data-testid="auth.gate.loading"`, `ui_state` event with `scope: 'auth', phase: 'loading'`
- Backend hooks: None required for loading state verification
- Gaps: None
- Evidence: Pattern from `tests/e2e/devices/DevicesPage.ts:175-180`

### Login Redirect on 401

- Surface: AuthProvider redirect logic
- Scenarios:
  - Given user session is not present, When app loads, Then `auth.redirecting` event is emitted with correct target URL
  - Given redirect target URL includes query params, When redirect triggers, Then full path is preserved in redirect parameter
- Instrumentation / hooks: `ui_state` event with `scope: 'auth', phase: 'redirecting'`, `metadata.targetUrl` contains encoded redirect
- Backend hooks: `POST /api/testing/auth/clear` to ensure no session exists
- Gaps: None - redirect can be verified via instrumentation event without following actual navigation
- Evidence: Requirement "Redirect to /api/auth/login?redirect=<current_path> when 401 is received"

### Auth Error and Retry

- Surface: Auth gate component
- Scenarios:
  - Given backend returns 500 error, When app loads, Then error screen displays with retry button
  - Given error screen is displayed, When user clicks retry, Then auth check is performed again
- Instrumentation / hooks: `data-testid="auth.gate.error"`, `data-testid="auth.gate.error.retry"`, `ui_state` event with `scope: 'auth', phase: 'error'`
- Backend hooks: `POST /api/testing/auth/force-error?status=500` to trigger deterministic 500 response
- Gaps: Depends on backend implementing `/api/testing/auth/force-error` endpoint (see Blocking Issues)
- Evidence: Requirement "Show error screen with retry option for non-401 errors"

### Authenticated User Display

- Surface: Top bar user dropdown
- Scenarios:
  - Given user is authenticated with name "John Doe", When app loads, Then top bar displays "John Doe"
  - Given user is authenticated with null name, When app loads, Then top bar displays "Unknown User"
- Instrumentation / hooks: `data-testid="app-shell.topbar.user.name"`, `ui_state` event with `scope: 'auth', phase: 'ready'`
- Backend hooks: `POST /api/testing/auth/session` with `{ name: "John Doe" }` or `{ name: null }` to control user fields
- Gaps: Depends on backend implementing `/api/testing/auth/session` endpoint (see Blocking Issues)
- Evidence: Requirement "Display 'Unknown User' if user's name field is null"

### Logout Flow

- Surface: User dropdown
- Scenarios:
  - Given user is authenticated, When user clicks user name, Then dropdown menu appears
  - Given dropdown is open, When user clicks logout, Then browser navigates to logout endpoint
- Instrumentation / hooks: `data-testid="app-shell.topbar.user"`, `data-testid="app-shell.topbar.user.dropdown"`, `data-testid="app-shell.topbar.user.logout"`
- Backend hooks: `POST /api/testing/auth/session` to establish authenticated state before test
- Gaps: None once backend test auth is available (see Blocking Issues)
- Evidence: Requirement "Logout redirects directly to /api/auth/logout"

### Sidebar Toggle (Desktop)

- Surface: Top bar and sidebar
- Scenarios:
  - Given sidebar is expanded, When user clicks hamburger, Then sidebar collapses to 0 width
  - Given sidebar is collapsed, When user clicks hamburger, Then sidebar expands to full width
- Instrumentation / hooks: `data-testid="app-shell.topbar.hamburger"`, `data-testid="app-shell.sidebar"` with `data-state="collapsed|expanded"`
- Gaps: None
- Evidence: Existing `data-state` pattern in `src/components/layout/sidebar.tsx:34`

### Mobile Menu Toggle

- Surface: Top bar and mobile overlay
- Scenarios:
  - Given on mobile viewport, When user clicks hamburger, Then overlay menu appears
  - Given overlay menu is open, When user clicks outside, Then overlay closes
  - Given overlay menu is open, When user clicks navigation item, Then overlay closes and navigates
- Instrumentation / hooks: `data-testid="app-shell.topbar.hamburger"`, `data-testid="app-shell.mobile-overlay"`, `data-mobile-menu-state`
- Gaps: None
- Evidence: Existing pattern in `src/routes/__root.tsx:42`

### Top Bar Layout

- Surface: Top bar component
- Scenarios:
  - Given user is authenticated, When app loads, Then top bar contains hamburger, logo, title, and user dropdown in correct order
- Instrumentation / hooks: `data-testid="app-shell.topbar.*"`
- Backend hooks: `POST /api/testing/auth/session` to establish authenticated state
- Gaps: Logo sizing at "110% of text height" deferred to visual regression testing (not implemented in this slice); precise CSS measurement is brittle in Playwright
- Evidence: Requirement "Logo displayed at 110% of text height"

---

## 14) Implementation Slices

- Slice: Auth context and hook
- Goal: Establish auth state management foundation
- Touches: `src/contexts/auth-context.tsx`, `src/hooks/use-auth.ts`
- Dependencies: None; can be developed independently

- Slice: Auth gate component
- Goal: Block rendering until auth resolves, show error/retry UI
- Touches: `src/components/auth/auth-gate.tsx`
- Dependencies: Requires auth context

- Slice: Layout restructure - top bar
- Goal: Create top bar with hamburger, logo, title
- Touches: `src/components/layout/top-bar.tsx`, `src/routes/__root.tsx`
- Dependencies: None for basic layout

- Slice: User dropdown
- Goal: Add user display and logout functionality to top bar
- Touches: `src/components/layout/user-dropdown.tsx`, `src/components/layout/top-bar.tsx`
- Dependencies: Requires auth context for user info

- Slice: Sidebar simplification
- Goal: Remove header from sidebar, adjust collapse behavior
- Touches: `src/components/layout/sidebar.tsx`, `src/routes/__root.tsx`
- Dependencies: Top bar must be in place first

- Slice: Integration and instrumentation
- Goal: Wire all components together, add test instrumentation
- Touches: `src/routes/__root.tsx`, all new components
- Dependencies: All previous slices complete

- Slice: Playwright tests
- Goal: Verify auth flows and layout behavior
- Touches: `tests/e2e/auth/auth.spec.ts`, `tests/e2e/auth/AuthPage.ts`, `tests/support/fixtures.ts`
- Dependencies: Full implementation complete; **blocked until backend implements `/api/testing/auth/*` endpoints** (see Blocking Issues section)

---

## 15) Risks & Open Questions

### Risks

- Risk: Backend test auth endpoints may not be implemented in time
- Impact: Playwright test slice is blocked; UI feature ships without automated verification
- Mitigation: Backend endpoints specified in Blocking Issues section; coordinate with backend team before starting Playwright slice; UI slices can proceed independently

- Risk: OIDC redirect may break Playwright test isolation
- Impact: Tests may leave browser in unexpected state after following redirects
- Mitigation: Use `auth.redirecting` instrumentation event to verify redirect intent without following; use `POST /api/testing/auth/clear` between tests

- Risk: Logo sizing at "110% of text height" may vary across browsers/fonts
- Impact: Minor visual inconsistencies
- Mitigation: Use relative units (em) and accept minor variance; defer verification to visual regression testing

### Open Questions

- Question: Should the user dropdown show email if name is null?
- Why it matters: "Unknown User" may be less useful than showing email
- Owner / follow-up: Product decision - requirement says "Unknown User" but email could be fallback

- Question: What should happen if `/api/auth/logout` fails?
- Why it matters: User may be stuck in limbo state
- Owner / follow-up: Backend handles redirect even on error; frontend assumes success

---

## 16) Confidence

Confidence: High - The requirements are clear, the patterns are well-established in the codebase, and the backend auth endpoints are already implemented. The Playwright test auth dependency is now documented in the Blocking Issues section with specific backend endpoint requirements. UI implementation slices can proceed independently while backend test support is coordinated.
