# OIDC Authentication Integration - Code Review

## 1) Summary & Decision

**Readiness**

The OIDC authentication integration implementation is well-structured and follows established project patterns. The core authentication flow (context, hook, gate) is correctly implemented with proper 401 detection, redirect handling, and error state management. The layout restructure (top bar, sidebar simplification) aligns with requirements. However, all Playwright tests are skipped due to documented backend dependencies, which means automated verification is absent. The implementation passes `pnpm check` (lint and type-check) successfully.

**Decision**

`GO-WITH-CONDITIONS` - The UI implementation is solid and ready for integration. The conditions are:
1. Backend must implement the `/api/testing/auth/*` endpoints before the auth feature can be considered complete with automated verification
2. One minor instrumentation phase mapping should be documented (using 'submit' for 'redirecting')

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- `Section 2: New Files - auth-context.tsx` - `src/contexts/auth-context.tsx:1-133` - Correctly implements AuthProvider with user state, loading management, logout action, and 401 redirect handling
- `Section 2: New Files - use-auth.ts` - `src/hooks/use-auth.ts:1-104` - Hook wraps `useGetAuthSelf`, transforms response, and distinguishes 401 from other errors
- `Section 2: New Files - auth-gate.tsx` - `src/components/auth/auth-gate.tsx:1-107` - Blocks rendering until auth resolves, shows loading/error states correctly
- `Section 2: New Files - top-bar.tsx` - `src/components/layout/top-bar.tsx:1-79` - Implements hamburger | logo | title | spacer | user dropdown layout
- `Section 2: New Files - user-dropdown.tsx` - `src/components/layout/user-dropdown.tsx:1-128` - User name display with "Unknown User" fallback and logout option
- `Section 2: Modified - __root.tsx` - `src/routes/__root.tsx:1-115` - Integrates AuthProvider and AuthGate, restructures layout
- `Section 2: Modified - sidebar.tsx` - `src/components/layout/sidebar.tsx:1-91` - Header removed, collapses to 0 width instead of icon-only
- `Section 9: Instrumentation` - `src/contexts/auth-context.tsx:66-116` - Emits `ui_state` events for loading, ready, error, and redirecting phases
- `Section 13: Test Plan` - `tests/e2e/auth/auth.spec.ts:1-242` - Test structure follows plan scenarios, all properly skipped with documented blockers

**Gaps / deviations**

- `Plan Section 9: auth.redirecting event` - Plan specifies `phase: 'redirecting'` but implementation uses `phase: 'submit'` with `metadata: { action: 'redirecting' }` (`src/contexts/auth-context.tsx:107-108`). This is noted in a comment as a workaround since 'redirecting' is not in `UiStateTestEvent.phase` union type. This is acceptable but should be documented for test authors.
- `Plan Section 2: api-error.ts modification` - Plan states "Add status property extraction for 401 detection" but no modification was needed - the existing `ApiError` class already has `status` property (`src/lib/api/api-error.ts:11`).

---

## 3) Correctness - Findings (ranked)

### Finding 1

- Title: `Minor` - Logo sizing approach may not achieve exactly 110% of text height
- Evidence: `src/components/layout/top-bar.tsx:55-61`
  ```tsx
  <img
    src="/favicon.png"
    alt="IoT Support Logo"
    className="h-[1.1em] w-[1.1em]"
    style={{ fontSize: '1rem' }}
    data-testid="app-shell.topbar.logo"
  />
  ```
- Impact: The `em` units on the `<img>` tag are relative to its own `font-size` (set to `1rem`), not the adjacent text's font size. Since the title text inherits from parent (likely also `1rem`), this works coincidentally but could break if text sizing changes.
- Fix: Remove the inline `style` attribute since the `em` unit will inherit from the parent container which contains both the logo and title text. Or use a fixed calculation based on expected text height.
- Confidence: Medium

### Finding 2

- Title: `Minor` - Dropdown click-outside handler type assertion
- Evidence: `src/components/layout/user-dropdown.tsx:34`
  ```tsx
  if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
  ```
- Impact: Type assertion `as Node` is safe here since `event.target` in DOM events is always a Node, but could be more defensive.
- Fix: Add null check: `event.target && !dropdownRef.current.contains(event.target as Node)`
- Confidence: Low (existing pattern is safe in practice)

### Finding 3

- Title: `Minor` - Auth context hook throws synchronously on missing provider
- Evidence: `src/contexts/auth-context.tsx:31-36`
  ```tsx
  export function useAuthContext(): AuthContextValue {
    const context = useContext(AuthContext)
    if (!context) {
      throw new Error('useAuthContext must be used within AuthProvider')
    }
    return context
  }
  ```
- Impact: This follows the exact pattern from `toast-context.tsx:16-22`, so it is consistent. However, if a component mistakenly uses `useAuthContext` outside the provider tree, the error is thrown during render which is correct behavior.
- Fix: None needed - this matches project conventions.
- Confidence: High (verified against existing pattern)

---

## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: None identified
- The implementation is appropriately scoped. The auth context, hook, and gate are separated by responsibility:
  - `use-auth.ts` handles data fetching and 401 detection
  - `auth-context.tsx` handles state distribution and redirect logic
  - `auth-gate.tsx` handles conditional rendering
- This separation follows the project's existing patterns (e.g., `use-devices.ts` + `toast-context.tsx`).

---

## 5) Style & Consistency

- Pattern: Auth hook follows existing hook conventions
- Evidence: `src/hooks/use-auth.ts:70-103` mirrors pattern from `src/hooks/use-devices.ts:36-48`
  ```tsx
  export function useAuth(): UseAuthResult {
    const query = useGetAuthSelf(undefined, {
      retry: false,
      staleTime: Infinity,
      refetchOnWindowFocus: false,
    })
    // ...
  }
  ```
- Impact: Consistent with project conventions
- Recommendation: None needed

- Pattern: Context provider follows toast-context pattern
- Evidence: `src/contexts/auth-context.tsx:63-132` mirrors structure from `src/contexts/toast-context.tsx:28-69`
- Impact: Maintains consistency across the codebase
- Recommendation: None needed

- Pattern: ESLint disable for react-refresh rule
- Evidence: `src/contexts/auth-context.tsx:1`
  ```tsx
  /* eslint-disable react-refresh/only-export-components */
  ```
- Impact: Same pattern as `toast-context.tsx:1` - necessary for context files that export both provider and hook
- Recommendation: None needed

- Pattern: Test instrumentation uses existing event types
- Evidence: `src/contexts/auth-context.tsx:71-93` uses `UiStateTestEvent` with scope `'auth'` and standard phases
- Impact: Aligns with `src/types/test-events.ts:118-126` taxonomy
- Recommendation: None needed

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: Authentication flows (login redirect, error handling, user display)
- Scenarios:
  - Given user is not authenticated, When app loads, Then redirect event emitted (`tests/e2e/auth/auth.spec.ts:46-61`)
  - Given backend returns 500, When app loads, Then error screen with retry (`tests/e2e/auth/auth.spec.ts:78-102`)
  - Given user authenticated with name, When app loads, Then name displayed (`tests/e2e/auth/auth.spec.ts:104-129`)
  - Given user authenticated with null name, When app loads, Then "Unknown User" displayed (`tests/e2e/auth/auth.spec.ts:118-128`)
- Hooks: `data-testid="auth.gate.loading"`, `data-testid="auth.gate.error"`, `data-testid="auth.gate.error.retry"`, `data-testid="app-shell.topbar.user.name"`, `ui_state` events with scope `'auth'`
- Gaps: **All tests are skipped** - blocked on backend implementing:
  - `POST /api/testing/auth/session`
  - `POST /api/testing/auth/clear`
  - `POST /api/testing/auth/force-error`
- Evidence: `tests/e2e/auth/auth.spec.ts:1-20` documents blocking issues

- Surface: App shell layout (sidebar toggle, mobile menu)
- Scenarios:
  - Given sidebar expanded, When hamburger clicked, Then sidebar collapses to 0 width (`tests/e2e/auth/auth.spec.ts:163-175`)
  - Given mobile viewport, When hamburger clicked, Then overlay menu appears (`tests/e2e/auth/auth.spec.ts:190-201`)
- Hooks: `data-testid="app-shell.topbar.hamburger"`, `data-testid="app-shell.sidebar"` with `data-state`, `data-testid="app-shell.mobile-overlay"`
- Gaps: Same backend dependency blocker
- Evidence: `tests/e2e/auth/auth.spec.ts:162-241`

- Surface: Page object for test helpers
- Scenarios: Provides locators and actions for all auth-related elements
- Hooks: Comprehensive locator coverage for auth gate, top bar, user dropdown, sidebar
- Gaps: None - page object is complete
- Evidence: `tests/e2e/auth/AuthPage.ts:14-192`

---

## 7) Adversarial Sweep

### Attempted Attack 1: Stale closure in redirect effect

- Evidence: `src/contexts/auth-context.tsx:97-116`
  ```tsx
  useEffect(() => {
    if (isUnauthenticated) {
      const loginUrl = buildLoginUrl()
      // ...emit event...
      window.location.href = loginUrl
    }
  }, [isUnauthenticated])
  ```
- Why code held up: The effect only depends on `isUnauthenticated` boolean. The `buildLoginUrl()` function reads `window.location` at call time, so it always captures the current URL. No stale closure risk since there's no captured state that could become stale.

### Attempted Attack 2: Race condition between loading states

- Evidence: `src/contexts/auth-context.tsx:66-94` and `src/components/auth/auth-gate.tsx:85-106`
- Checks attempted: Can auth state transition from loading -> authenticated while effect emitting loading event?
- Why code held up: React batches state updates, and the effect runs after render. The `isLoading`, `isAuthenticated`, `error` states come from React Query which manages transitions atomically. The sequential if/else-if structure in the effect ensures only one event type is emitted per state.

### Attempted Attack 3: Query cache inconsistency on refetch

- Evidence: `src/hooks/use-auth.ts:71-78`
  ```tsx
  const query = useGetAuthSelf(undefined, {
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
  ```
- Checks attempted: Can retry button in AuthGate cause cache inconsistency?
- Why code held up: `staleTime: Infinity` means the data never goes stale automatically. Manual `refetch()` from the retry button triggers a fresh network request. The query key `['getAuthSelf', undefined]` is stable. No cache mutation occurs outside React Query's control.

### Attempted Attack 4: Click-outside cleanup on unmount

- Evidence: `src/components/layout/user-dropdown.tsx:32-43`
  ```tsx
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])
  ```
- Why code held up: Effect only adds listener when `isOpen` is true, and cleanup function removes it. If component unmounts while open, React runs cleanup. No memory leak or dangling listener.

---

## 8) Invariants Checklist

- Invariant: Children never render until auth state resolves
  - Where enforced: `src/components/auth/auth-gate.tsx:85-106`
  - Failure mode: Could break if AuthGate renders children during loading or unauthenticated state
  - Protection: Sequential if/else structure returns early for loading and error states; `!isAuthenticated` check shows loading during redirect
  - Evidence: Lines 89-102 return loading/error screens before reaching children render at line 105

- Invariant: 401 errors are not treated as errors in UI
  - Where enforced: `src/hooks/use-auth.ts:82-93`
  - Failure mode: Could show error screen for 401 if `isUnauthorizedError` check fails
  - Protection: `isUnauthorizedError()` checks both `ApiError` instance and raw objects with `status` property; `effectiveError` is null when 401
  - Evidence: Lines 83, 93 ensure 401 produces `error: null` in return value

- Invariant: User display name is never empty
  - Where enforced: `src/components/layout/user-dropdown.tsx:13-18`
  - Failure mode: Could show empty string if name is whitespace-only
  - Protection: `getDisplayName()` checks `name && name.trim()` before returning, falls back to "Unknown User"
  - Evidence: `tests/e2e/auth/auth.spec.ts:118-128` documents test scenario for null name

- Invariant: Logout navigates without confirmation
  - Where enforced: `src/contexts/auth-context.tsx:54-57` and `src/components/layout/user-dropdown.tsx:59-62`
  - Failure mode: Could add unintended confirmation dialog
  - Protection: `performLogout()` directly assigns `window.location.href`; `handleLogout()` calls `logout()` without any confirm step
  - Evidence: Plan requirement "Logout redirects directly to /api/auth/logout (no confirmation dialog)"

---

## 9) Questions / Needs-Info

- Question: When will backend implement `/api/testing/auth/*` endpoints?
- Why it matters: All Playwright tests are skipped until these endpoints exist. The feature cannot be considered complete without automated verification per project standards.
- Desired answer: Timeline or tracking issue for backend implementation

- Question: Should the instrumentation event for redirect use a dedicated phase?
- Why it matters: Currently using `phase: 'submit'` with `metadata: { action: 'redirecting' }` as workaround since 'redirecting' is not in the `UiStateTestEvent.phase` union
- Desired answer: Either add 'redirecting' to the phase union in `test-events.ts`, or confirm the workaround is acceptable long-term

---

## 10) Risks & Mitigations (top 3)

- Risk: No automated test coverage until backend test endpoints implemented
- Mitigation: Backend team should prioritize `/api/testing/auth/*` endpoints; manual testing validates UI flows in the interim
- Evidence: `tests/e2e/auth/auth.spec.ts:1-20` blocking issue documentation

- Risk: Logo sizing may vary across browsers/font configurations
- Mitigation: Accept minor variance as documented in plan; defer visual regression testing
- Evidence: `src/components/layout/top-bar.tsx:55-61`, `plan.md` Section 15 Risks

- Risk: Redirect loop if OIDC provider returns 401 after successful authentication
- Mitigation: Backend must ensure `/api/auth/callback` properly sets session cookie before redirecting; frontend has no loop protection
- Evidence: `src/contexts/auth-context.tsx:97-116` unconditionally redirects on `isUnauthenticated`

---

## 11) Confidence

Confidence: High - The implementation follows established project patterns, passes all static checks, and the test structure is well-designed even though tests are blocked. The plan-to-code mapping is complete with only minor deviations documented. The adversarial sweep found no credible failure modes.
