# OIDC Authentication - Change Brief

## Summary

Add OpenID Connect (OIDC) authentication to the IoT Support Backend using a Backend-for-Frontend (BFF) pattern. The backend handles all OIDC complexity including authorization code flow with PKCE, token exchange, and cookie management. This simplifies the frontend to just redirects and API calls.

## Authentication Flows

1. **Browser Users (SPA)**: Authenticate via `/api/auth/login` which redirects to Keycloak. After login, an HttpOnly cookie stores the access token. Frontend checks auth status via `/api/auth/self`.

2. **Machine-to-Machine (Jenkins)**: Continue using Bearer tokens obtained via client credentials flow. No changes to existing M2M integration.

3. **ESP32 Devices**: Config and asset GET endpoints remain public (no authentication required).

## Role-Based Access Control

- `admin` role: Full access to all authenticated endpoints
- `asset-uploader` role: Access only to POST `/api/assets`

## Key Components

- **AuthService**: JWT validation with JWKS discovery and caching
- **OidcClientService**: OIDC authorization code flow, token exchange
- **Auth Middleware**: `before_request` hook on `/api` blueprint with `@public` decorator support
- **Auth Endpoints**: `/api/auth/self`, `/api/auth/login`, `/api/auth/callback`, `/api/auth/logout`

## Configuration

- `BASEURL`: Frontend URL (used to derive redirect URI and cookie security)
- `OIDC_ENABLED`: Feature flag (False disables auth for development)
- `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`: Keycloak connection
- Cookie settings with sensible defaults inferred from BASEURL

## Out of Scope

- User storage/management (handled by Keycloak)
- Token refresh (initial implementation; may add later)
- SSO logout to Keycloak (clears local cookie only)
- Device authentication (endpoints remain public)
