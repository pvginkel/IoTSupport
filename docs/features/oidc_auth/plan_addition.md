# OIDC Authentication - Plan Addition

## Overview

This document describes additional requirements identified after the initial implementation. The changes introduce a Backend-for-Frontend (BFF) authentication pattern that moves all OIDC complexity to the backend.

## Problem with Current Approach

The initial implementation assumed the frontend would:
1. Implement OIDC authorization code flow itself
2. Handle token acquisition and refresh
3. Set the `access_token` cookie

This has drawbacks:
- Frontend needs an OIDC client library
- Tokens are exposed to JavaScript (XSS risk if not HttpOnly)
- OIDC complexity spread across frontend and backend
- Harder to change auth providers later

## New Approach: BFF Authentication Pattern

The backend handles all OIDC interactions. The frontend only needs to:
1. Call `/auth/self` to check if authenticated and get user info
2. Redirect to `/auth/login` when not authenticated
3. Redirect to `/auth/logout` to log out

### New Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/self` | GET | Returns current user info or 401 if not authenticated |
| `/auth/login` | GET | Initiates OIDC flow, redirects to Keycloak |
| `/auth/callback` | GET | Keycloak redirects here after login |
| `/auth/logout` | GET | Clears session, optionally logs out of Keycloak |

### GET /auth/self

Returns information about the current authenticated user.

**Response (200 OK):**
```json
{
  "subject": "user-uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "roles": ["admin"]
}
```

**Response (401 Unauthorized):**
```json
{
  "error": "Not authenticated",
  "code": "AUTHENTICATION_REQUIRED"
}
```

**Frontend usage:**
```javascript
async function checkAuth() {
  const response = await fetch('/auth/self');
  if (response.status === 401) {
    // Not logged in - redirect to login
    window.location = '/auth/login?redirect=' + encodeURIComponent(window.location.href);
    return null;
  }
  return await response.json();
}
```

### GET /auth/login

Initiates OIDC authorization code flow.

**Query Parameters:**
- `redirect` (required): URL to redirect to after successful login

**Behavior:**
1. Stores `redirect` URL in session/state
2. Generates PKCE code verifier and challenge
3. Redirects browser to Keycloak authorization endpoint

**Example:**
```
GET /auth/login?redirect=https://app.example.com/dashboard

302 Redirect to:
https://keycloak/realms/iot/protocol/openid-connect/auth?
  client_id=iot-backend&
  response_type=code&
  redirect_uri=https://api.example.com/auth/callback&
  scope=openid+profile+email&
  state=<random>&
  code_challenge=<pkce_challenge>&
  code_challenge_method=S256
```

### GET /auth/callback

Handles the OIDC callback from Keycloak.

**Query Parameters (from Keycloak):**
- `code`: Authorization code
- `state`: State parameter for CSRF protection

**Behavior:**
1. Validates state parameter
2. Exchanges authorization code for tokens (using client secret)
3. Sets `access_token` as HttpOnly cookie
4. Optionally stores refresh token server-side
5. Redirects to original `redirect` URL from login

**Cookie Settings:**
```
Set-Cookie: access_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/
```

### GET /auth/logout

Logs out the user.

**Query Parameters:**
- `redirect` (optional): URL to redirect to after logout (default: `/`)

**Behavior:**
1. Clears `access_token` cookie
2. Revokes tokens at Keycloak (if configured)
3. Optionally redirects to Keycloak logout endpoint for SSO logout
4. Redirects to `redirect` URL

## Confidential Client Configuration

The backend authenticates to Keycloak using a client secret (confidential client).

### Advantages

1. **Refresh tokens** - Keycloak issues refresh tokens to confidential clients
   - Access tokens can be short-lived (5 minutes)
   - Backend refreshes silently without user interaction
   - Sessions can last days/weeks

2. **Secure token exchange** - Authorization code alone is useless without the secret

3. **Token revocation** - Backend can invalidate tokens at Keycloak (real logout)

4. **Token introspection** - Backend can verify token validity with Keycloak

### New Configuration

```bash
# Existing
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://keycloak/realms/iot
OIDC_AUDIENCE=iot-backend

# New - confidential client
OIDC_CLIENT_ID=iot-backend
OIDC_CLIENT_SECRET=<secret-from-keycloak>
OIDC_REDIRECT_URI=https://api.example.com/auth/callback

# New - token settings
OIDC_SCOPES=openid profile email
OIDC_ACCESS_TOKEN_COOKIE_NAME=access_token
OIDC_COOKIE_SECURE=true
OIDC_COOKIE_SAMESITE=Lax
```

### Keycloak Client Configuration

1. **Client ID**: `iot-backend`
2. **Client Type**: Confidential (Client authentication: ON)
3. **Authentication flow**: Standard flow (authorization code)
4. **Valid redirect URIs**: `https://api.example.com/auth/callback`
5. **Roles**: Create `admin` and `asset-uploader` roles

## Machine-to-Machine Authentication (Jenkins)

M2M clients like Jenkins use the existing Bearer token authentication. No changes needed.

### How It Works

1. Jenkins is configured as a separate confidential client in Keycloak
2. "Service Account Enabled" is turned on for this client
3. The `asset-uploader` role is assigned to the service account
4. Jenkins uses client credentials flow to get a token:

```bash
# Get token
TOKEN=$(curl -s -X POST \
  https://keycloak/realms/iot/protocol/openid-connect/token \
  -d "grant_type=client_credentials" \
  -d "client_id=jenkins-asset-uploader" \
  -d "client_secret=<secret>" \
  | jq -r '.access_token')

# Upload asset
curl -X POST https://api.example.com/api/assets \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@firmware.bin" \
  -F "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  -F "signature=<base64-signature>"
```

### Token Characteristics

- `sub` claim: Client ID (not a user UUID)
- `email` claim: Typically absent
- Roles: From service account role mappings
- Validated identically to user tokens

The existing authorization logic already handles this:
- Token has `asset-uploader` role → Can POST to `/api/assets`
- No email in token → `AuthContext.email` is `None` (already supported)

## Frontend Simplification

With BFF pattern, the frontend becomes much simpler:

```javascript
// auth.js
const AUTH_SELF_URL = '/auth/self';
const AUTH_LOGIN_URL = '/auth/login';
const AUTH_LOGOUT_URL = '/auth/logout';

export async function getCurrentUser() {
  const response = await fetch(AUTH_SELF_URL, { credentials: 'include' });
  if (response.status === 401) {
    return null;
  }
  return await response.json();
}

export function redirectToLogin() {
  const redirect = encodeURIComponent(window.location.href);
  window.location.href = `${AUTH_LOGIN_URL}?redirect=${redirect}`;
}

export function logout() {
  window.location.href = `${AUTH_LOGOUT_URL}?redirect=${encodeURIComponent('/')}`;
}

// App initialization
const user = await getCurrentUser();
if (!user) {
  redirectToLogin();
} else {
  console.log(`Welcome, ${user.name}`);
}
```

No OIDC library needed. No token handling. No refresh logic.

## Implementation Slices

### Slice 1: Auth Blueprint Setup

**Files:**
- `app/api/auth.py` (new) - Auth endpoints blueprint
- `app/api/__init__.py` - Register auth blueprint (outside `/api` prefix)
- `app/config.py` - Add new OIDC client configuration

### Slice 2: OIDC Client Service

**Files:**
- `app/services/oidc_client_service.py` (new) - Handles OIDC flows
  - Authorization URL generation with PKCE
  - Token exchange with client secret
  - Token refresh
  - Token revocation

### Slice 3: Session/State Management

**Files:**
- Decide on state storage for PKCE verifier and redirect URL
- Options: Signed cookie, server-side session, or stateless with encrypted state parameter

### Slice 4: Auth Endpoints Implementation

**Files:**
- `app/api/auth.py` - Implement `/auth/self`, `/auth/login`, `/auth/callback`, `/auth/logout`

### Slice 5: Cookie Management

**Files:**
- `app/utils/auth.py` - Cookie setting/clearing utilities
- Update to read from HttpOnly cookie (already implemented)

### Slice 6: Refresh Token Handling (Optional)

**Files:**
- Decide on refresh token storage (server-side session or second cookie)
- Implement automatic refresh before access token expiry

### Slice 7: Tests

**Files:**
- `tests/api/test_auth_endpoints.py` (new)
- `tests/services/test_oidc_client_service.py` (new)

## Summary of Changes

| Component | Current | New |
|-----------|---------|-----|
| OIDC flow | Frontend handles | Backend handles |
| Token storage | Cookie set by frontend | HttpOnly cookie set by backend |
| Client type | Public (assumed) | Confidential |
| Refresh tokens | Not supported | Supported |
| Token revocation | Not supported | Supported |
| Frontend auth code | OIDC library needed | Simple redirects only |
| M2M auth | Bearer token | No change |

## Open Questions

1. **State storage**: Use signed cookies (stateless) or server-side sessions for PKCE state?
2. **Refresh token storage**: Store in server-side session or encrypted cookie?
3. **Keycloak logout**: Redirect to Keycloak logout for full SSO logout, or just clear local cookie?
4. **Token refresh strategy**: Refresh proactively before expiry, or on 401 response?
