# Backend Changes Required for OIDC Frontend Integration

## Overview

The frontend OIDC authentication integration is complete, but Playwright tests cannot run without backend support for test authentication. This document specifies the required backend endpoints.

These endpoints should **only be available when the backend is running in test mode** (e.g., via environment variable or test configuration).

---

## Required Endpoints

### 1. Create Test Session

**Endpoint**: `POST /api/testing/auth/session`

**Purpose**: Create an authenticated session with controllable user fields, bypassing the real OIDC flow.

**Request Body**:
```json
{
  "subject": "test-user-123",
  "name": "Test User",
  "email": "test@example.com",
  "roles": ["user"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `subject` | string | Yes | The user's subject identifier (sub claim) |
| `name` | string | No | User's display name. If omitted or null, tests can verify "Unknown User" fallback |
| `email` | string | No | User's email address |
| `roles` | string[] | No | User's roles. Defaults to empty array if omitted |

**Response**:
- `201 Created` on success
- Sets the same session cookie that the real OIDC callback would set

**Example Usage**:
```typescript
// In Playwright test
await request.post('/api/testing/auth/session', {
  data: {
    subject: 'user-001',
    name: 'Alice Smith',
    email: 'alice@example.com',
    roles: ['admin']
  }
});

// Now /api/auth/self will return this user info
await page.goto('/');
await expect(page.getByTestId('app-shell.topbar.user.name')).toHaveText('Alice Smith');
```

---

### 2. Clear Test Session

**Endpoint**: `POST /api/testing/auth/clear`

**Purpose**: Clear the current session for test isolation between specs.

**Request Body**: None

**Response**:
- `204 No Content` on success
- Clears/invalidates the session cookie

**Example Usage**:
```typescript
// In Playwright test beforeEach or afterEach
await request.post('/api/testing/auth/clear');

// Now /api/auth/self will return 401
```

---

### 3. Force Auth Error

**Endpoint**: `POST /api/testing/auth/force-error`

**Purpose**: Configure `/api/auth/self` to return a specific error status on the next request. Used for testing error handling and retry flows.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | integer | Yes | HTTP status code to return (e.g., 500, 503) |

**Response**:
- `204 No Content` on success

**Behavior**:
- After this endpoint is called, the next request to `/api/auth/self` returns the specified status code
- Subsequent requests resume normal behavior (the forced error is single-shot)
- The forced error should return a standard error response body

**Example Usage**:
```typescript
// Force a 500 error on the next auth check
await request.post('/api/testing/auth/force-error?status=500');

await page.goto('/');

// Verify error screen is shown
await expect(page.getByTestId('auth.gate.error')).toBeVisible();
await expect(page.getByTestId('auth.gate.error.message')).toContainText('error');

// Click retry - this request succeeds because the forced error was consumed
await page.getByTestId('auth.gate.error.retry').click();

// Now auth succeeds
await expect(page.getByTestId('app-shell.topbar.user.name')).toBeVisible();
```

---

## Implementation Notes

### Session Consistency

The test session should use the same mechanism as the real OIDC flow:
- Same cookie name and attributes
- Same session storage (if applicable)
- `/api/auth/self` should return the same `UserInfoResponseSchema` structure

### Error Response Format

When forcing errors, return the standard error response format:

```json
{
  "error": "Internal Server Error",
  "message": "Simulated error for testing"
}
```

---

## Frontend Test Scenarios Enabled

Once these endpoints are implemented, the following test scenarios can be unskipped:

| Scenario | Endpoints Used |
|----------|----------------|
| Auth loading state | `POST /api/testing/auth/session` |
| Login redirect on 401 | `POST /api/testing/auth/clear` |
| Path preservation in redirect | `POST /api/testing/auth/clear` |
| Error screen on 500 | `POST /api/testing/auth/force-error?status=500` |
| Retry button functionality | `POST /api/testing/auth/force-error?status=500` + `POST /api/testing/auth/session` |
| User name display | `POST /api/testing/auth/session` with name |
| "Unknown User" fallback | `POST /api/testing/auth/session` without name |
| Logout flow | `POST /api/testing/auth/session` |
| Sidebar toggle | `POST /api/testing/auth/session` |
| Mobile menu | `POST /api/testing/auth/session` |
| Top bar layout | `POST /api/testing/auth/session` |

---

## Existing Test Infrastructure

The frontend already has test infrastructure that expects these endpoints:

**Fixture**: `tests/e2e/auth/AuthPage.ts`
- Page object with locators for all auth UI elements
- Action helpers for login, logout, and session management

**Test File**: `tests/e2e/auth/auth.spec.ts`
- All test scenarios defined and ready
- Currently marked `.skip` with blocking issue documentation

Once backend endpoints are available, remove the `.skip` annotations and tests should pass.

---

## Questions

1. **Session storage**: Does the backend use server-side sessions, JWTs, or another mechanism? The test endpoints should match the real implementation.

2. **Cookie attributes**: What are the exact cookie name, path, domain, and security attributes? Test endpoints should set identical cookies.

3. **Error codes**: Are there other error codes besides 500 that the frontend should handle? (e.g., 503 for maintenance mode)
