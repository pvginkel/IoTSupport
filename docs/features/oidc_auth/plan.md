# OIDC Authentication Integration - Technical Plan (Revised)

## 0) Research Log & Findings

**Discovery Work Summary**

I researched the following areas to inform this plan:

1. **Existing Architecture Patterns** - Examined `app/__init__.py`, `app/api/__init__.py`, and existing API endpoints to understand:
   - Flask blueprint registration pattern
   - Dependency injection container wiring
   - No existing `before_request` hooks in the codebase
   - Current error handling via `@handle_api_errors` decorator

2. **Configuration Management** - Reviewed `app/config.py`:
   - Uses Pydantic `BaseSettings` with `.env` file loading
   - Settings are singleton via `@lru_cache` in `get_settings()`
   - Container receives settings via `container.config.override(settings)`

3. **Exception Handling** - Analyzed `app/exceptions.py` and `app/utils/error_handling.py`:
   - All custom exceptions inherit from `BusinessLogicException`
   - `@handle_api_errors` decorator maps exceptions to HTTP status codes
   - Error responses include `error`, `details`, `code`, and `correlationId` fields

4. **Service Container Pattern** - Studied `app/services/container.py`:
   - Singletons used for stateful services (MetricsService, MqttService, AssetUploadService)
   - Factory providers for stateless/request-scoped services (ConfigService, ImageProxyService)
   - Container wired to API modules in application factory

5. **Metrics Infrastructure** - Reviewed `app/services/metrics_service.py`:
   - Singleton service with Prometheus Counter/Gauge/Histogram metrics
   - Metrics defined in `initialize_metrics()` with idempotency check
   - No background threads in MetricsService (unlike ElectronicsInventory)

6. **Testing Patterns** - Examined `tests/conftest.py` and `tests/api/test_health.py`:
   - Fixtures for `app`, `client`, `container`, and `test_settings`
   - Prometheus registry cleared before/after each test for isolation
   - Tests create custom Settings instances to override config

**Areas of Special Interest**

- **BFF Authentication Pattern**: Backend handles all OIDC complexity; frontend only needs simple redirects
- **Confidential Client**: Backend authenticates to Keycloak with client secret, enabling refresh tokens and token revocation
- **Dual authentication flows**: Cookie-based for browser users (via BFF), Bearer token for M2M clients (direct)
- **PKCE for security**: Authorization code flow uses PKCE even though we're a confidential client (defense in depth)
- **State management**: Need to store PKCE verifier and redirect URL during auth flow

**Conflicts Identified and Resolutions**

1. **Conflict**: Health endpoint currently at `/api/health`, but should remain unauthenticated
   - **Resolution**: Use `@public` decorator to mark endpoints as exempt from authentication; before_request hook checks `view_func.is_public` attribute

2. **Conflict**: Metrics endpoint at root `/metrics` (not under `/api` blueprint), so not affected by `/api` before_request
   - **Resolution**: No change needed; metrics endpoint already outside `/api` blueprint scope

3. **Conflict**: Auth endpoints need to be accessible without authentication
   - **Resolution**: Register auth endpoints under `/api/auth/*` as a sub-blueprint; mark all auth endpoints with `@public` decorator

4. **Conflict**: AuthService needs to be singleton (caches JWKS) but also needs access to container for metrics
   - **Resolution**: Inject MetricsService into AuthService constructor; AuthService is singleton with MetricsService dependency

5. **Conflict**: State storage for PKCE verifier during auth flow
   - **Resolution**: Use signed cookies (stateless) to store encrypted state containing PKCE verifier and redirect URL

## 1) Intent & Scope

**User intent**

Add OpenID Connect authentication to the IoT Support Backend using a Backend-for-Frontend (BFF) pattern. The backend handles all OIDC complexity including authorization code flow, token exchange, and cookie management. Browser users authenticate via redirects to `/api/auth/login`, while M2M clients (like Jenkins) use Bearer tokens directly. Role-based access control enforces `admin` for full access and `asset-uploader` for restricted POST `/api/assets` access.

**Prompt quotes**

"Cookie-based token management for SPA users (read token from `access_token` cookie)"

"Bearer token support for M2M/API clients (read from Authorization header)"

"`admin` role grants full access to all authenticated endpoints"

"`asset-uploader` role grants access only to POST `/api/assets`"

"`@public` decorator to mark endpoints as anonymously accessible"

"OIDC discovery: fetch JWKS URL from `{issuer}/.well-known/openid-configuration`"

"No user table/storage - just validate token and check roles"

"`OIDC_ENABLED=False` disables authentication for development"

"Backend handles all OIDC interactions" (BFF pattern)

"Frontend only needs to: Call `/api/auth/self`, Redirect to `/api/auth/login`, Redirect to `/api/auth/logout`"

**In scope**

- Add OIDC configuration settings to `app/config.py` (BASEURL, issuer, client ID, client secret)
- Create `AuthenticationException` (401) and `AuthorizationException` (403) custom exceptions
- Implement `AuthService` singleton with JWKS discovery and caching (5-minute TTL)
- Implement `OidcClientService` for authorization code flow, token exchange, and refresh
- Create `/auth` blueprint with endpoints: `/api/auth/self`, `/api/auth/login`, `/api/auth/callback`, `/api/auth/logout`
- Add `@public` decorator for marking endpoints as anonymously accessible
- Implement Flask `before_request` hook for authentication enforcement on `/api` blueprint
- Role-based authorization: `admin` full access, `asset-uploader` restricted to POST `/api/assets`
- HttpOnly cookie management for access tokens
- Signed cookie state management for PKCE flow
- Extract email/name from token for `/api/auth/self` response
- Add Prometheus metrics for auth operations
- Comprehensive tests for AuthService, OidcClientService, and API integration
- Feature flag support via `OIDC_ENABLED` config

**Out of scope**

- User registration or management (handled by OIDC provider)
- User table or persistent user storage
- Token revocation checking beyond standard JWT expiration
- Multiple OIDC providers or tenant isolation
- Fine-grained permissions beyond role-based checks
- Rate limiting or brute-force protection
- Server-side session storage (using stateless signed cookies instead)
- Refresh token persistence (tokens refreshed on-demand when access token expires)

**Assumptions / constraints**

- OIDC provider (Keycloak) is already deployed and accessible
- Issuer URL serves standard `/.well-known/openid-configuration` endpoint
- Backend is configured as a confidential client in Keycloak with client secret
- JWT tokens contain standard OIDC claims: `iss`, `aud`, `exp`, `sub`, `email`, `name`
- Roles are available in JWT claims (`realm_access.roles` and/or `resource_access.<client>.roles`)
- M2M clients obtain tokens via client credentials flow and send via `Authorization: Bearer <token>`
- Clock skew tolerance of 30 seconds is sufficient for token validation
- JWKS endpoint is stable and available (graceful degradation if unreachable)
- Application runs in trusted network; HTTPS termination handled by ingress/nginx
- Flask's `itsdangerous` library used for signed cookies (already a Flask dependency)

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Cookie-based token management for SPA users (read token from `access_token` cookie)
- [ ] Bearer token support for M2M/API clients (read from Authorization header)
- [ ] `admin` role grants full access to all authenticated endpoints
- [ ] `asset-uploader` role grants access only to POST `/api/assets`
- [ ] `@public` decorator to mark endpoints as anonymously accessible
- [ ] Health endpoint (`/api/health`) remains unauthenticated
- [ ] OIDC discovery: fetch JWKS URL from `{issuer}/.well-known/openid-configuration`
- [ ] No user table/storage - just validate token and check roles
- [ ] Extract email from token for logging/metrics
- [ ] `OIDC_ENABLED=False` disables authentication for development
- [ ] AuthenticationException returns 401 Unauthorized
- [ ] AuthorizationException returns 403 Forbidden
- [ ] GET `/api/auth/self` returns current user info or 401 if not authenticated
- [ ] GET `/api/auth/login` initiates OIDC flow with PKCE, redirects to Keycloak
- [ ] GET `/api/auth/callback` handles Keycloak callback, exchanges code for tokens, sets HttpOnly cookie
- [ ] GET `/api/auth/logout` clears cookie and optionally logs out of Keycloak
- [ ] Backend uses confidential client (client secret) for token exchange
- [ ] M2M clients (Jenkins) continue to use Bearer token authentication unchanged

## 2) Affected Areas & File Map

- Area: `pyproject.toml`
- Why: Add `pyjwt[crypto]` and `httpx` dependencies for JWT validation and OIDC HTTP calls
- Evidence: `pyproject.toml:12-27` — existing dependencies like `cryptography`, `pydantic`, `flask`

---

- Area: `app/config.py`
- Why: Add OIDC configuration settings (BASEURL, issuer URL, client ID, client secret, cookie settings)
- Evidence: `app/config.py:13-21` — existing `Settings` class with Flask, ESP32, asset, CORS, and MQTT config

---

- Area: `app/exceptions.py`
- Why: Add `AuthenticationException` (401) and `AuthorizationException` (403) custom exceptions
- Evidence: `app/exceptions.py:4-14` — existing `BusinessLogicException` base class with `message` and `error_code`

---

- Area: `app/utils/error_handling.py`
- Why: Add exception handlers for `AuthenticationException` and `AuthorizationException` to return 401/403
- Evidence: `app/utils/error_handling.py:66-143` — existing exception handlers for domain exceptions with specific status codes

---

- Area: `app/services/auth_service.py` (NEW)
- Why: Implement JWT validation with JWKS discovery and caching; extract roles and email from claims
- Evidence: `app/services/container.py:1-49` — pattern for singleton services with constructor injection

---

- Area: `app/services/oidc_client_service.py` (NEW)
- Why: Implement OIDC authorization code flow with PKCE, token exchange, and token refresh
- Evidence: `app/services/container.py:1-49` — pattern for singleton services

---

- Area: `app/services/container.py`
- Why: Register `AuthService` and `OidcClientService` as singletons with MetricsService dependency
- Evidence: `app/services/container.py:19-28` — existing singleton providers for MetricsService and MqttService

---

- Area: `app/utils/auth.py` (NEW)
- Why: Implement `@public` decorator and helper functions for token extraction and role checking
- Evidence: `app/api/__init__.py:1-20` — blueprint pattern; no existing auth utilities

---

- Area: `app/api/__init__.py`
- Why: Register Flask `before_request` hook for authentication enforcement; register auth sub-blueprint
- Evidence: `app/api/__init__.py:3-19` — main API blueprint definition and sub-blueprint registration

---

- Area: `app/api/auth.py` (NEW)
- Why: Implement auth sub-blueprint with `/api/auth/*` endpoints; all marked `@public`
- Evidence: `app/api/health.py:1-29` — pattern for endpoints with `@public` decorator

---

- Area: `app/api/health.py`
- Why: Add `@public` decorator to mark health endpoint as unauthenticated
- Evidence: `app/api/health.py:14-29` — existing health check endpoint without auth

---

- Area: `app/services/metrics_service.py`
- Why: Add Prometheus metrics for auth operations (validation counter, duration histogram, JWKS refresh counter)
- Evidence: `app/services/metrics_service.py:22-90` — existing metric definitions using Counter, Gauge, Histogram

---

- Area: `app/__init__.py`
- Why: Wire AuthService and OidcClientService to container; add `app.api.auth` to wired modules
- Evidence: `app/__init__.py:36-44` — existing container wiring for API modules

---

- Area: `tests/conftest.py`
- Why: Add fixtures for JWT token generation (valid/expired/invalid signature) and mock OIDC discovery
- Evidence: `tests/conftest.py:1-141` — existing fixtures for `app`, `client`, `container`, `test_settings`

---

- Area: `tests/services/test_auth_service.py` (NEW)
- Why: Comprehensive unit tests for AuthService (JWKS caching, token validation, role extraction, error cases)
- Evidence: `tests/services/test_config_service.py:1-*` — pattern for service tests with dependency injection

---

- Area: `tests/services/test_oidc_client_service.py` (NEW)
- Why: Unit tests for OidcClientService (PKCE generation, token exchange, refresh)
- Evidence: `tests/services/test_config_service.py:1-*` — pattern for service tests

---

- Area: `tests/api/test_auth_endpoints.py` (NEW)
- Why: Integration tests for auth endpoints (/api/auth/self, /api/auth/login, /api/auth/callback, /api/auth/logout)
- Evidence: `tests/api/test_health.py:1-90` — pattern for API tests using FlaskClient

---

- Area: `tests/api/test_auth_middleware.py` (NEW)
- Why: Integration tests for authentication middleware (cookie/Bearer, role-based access, public endpoints, disabled auth)
- Evidence: `tests/api/test_health.py:1-90` — pattern for API tests using FlaskClient

## 3) Data Model / Contracts

- Entity / contract: OIDC Configuration Settings
- Shape:
  ```python
  # Base URL (frontend URL, proxies backend)
  BASEURL: str = "http://localhost:3200"          # Used to infer redirect URI and cookie security

  # Feature flag
  OIDC_ENABLED: bool = False

  # OIDC provider settings
  OIDC_ISSUER_URL: str | None = None              # e.g., "https://auth.example.com/realms/iot"
  OIDC_CLIENT_ID: str | None = None               # e.g., "iot-backend"
  OIDC_CLIENT_SECRET: str | None = None           # Confidential client secret
  OIDC_SCOPES: str = "openid profile email"       # Space-separated scopes

  # Token validation settings
  OIDC_AUDIENCE: str | None = None                # Expected "aud" claim (defaults to client_id)
  OIDC_CLOCK_SKEW_SECONDS: int = 30               # Tolerance for exp/nbf validation

  # Role settings
  OIDC_ADMIN_ROLE: str = "admin"                  # Role for full access
  OIDC_ASSET_ROLE: str = "asset-uploader"         # Role for POST /api/assets only

  # Cookie settings
  OIDC_COOKIE_NAME: str = "access_token"          # Cookie containing JWT
  OIDC_COOKIE_SECURE: bool | None = None          # Secure flag; inferred from BASEURL if None
  OIDC_COOKIE_SAMESITE: str = "Lax"               # SameSite attribute

  # Derived at runtime (not configurable):
  # - Redirect URI: f"{BASEURL}/api/auth/callback"
  # - Cookie Secure default: BASEURL.startswith("https://")
  ```
- Refactor strategy: No backwards compatibility needed; auth is net-new feature; when disabled (`OIDC_ENABLED=False`), all endpoints remain unauthenticated as before
- Evidence: `app/config.py:13-62` — existing Settings class using Pydantic Field with defaults

---

- Entity / contract: AuthContext Dataclass
- Shape:
  ```python
  @dataclass
  class AuthContext:
      subject: str              # JWT "sub" claim (user/client ID)
      email: str | None         # JWT "email" claim (may be None for M2M)
      name: str | None          # JWT "name" claim (may be None for M2M)
      roles: set[str]           # Combined roles from realm_access and resource_access
  ```
- Refactor strategy: New dataclass; stored in `flask.g.auth_context` during request lifecycle; no persistence
- Evidence: `flask.g` is standard Flask request context for request-scoped data

---

- Entity / contract: AuthState (for PKCE flow)
- Shape:
  ```python
  @dataclass
  class AuthState:
      code_verifier: str        # PKCE code verifier (stored in signed cookie)
      redirect_url: str         # Original URL to redirect after login
      nonce: str                # Random nonce for CSRF protection
  ```
- Refactor strategy: Serialized to JSON and stored in signed cookie during auth flow; cleared after callback
- Evidence: Flask's `itsdangerous` for signed cookies

---

- Entity / contract: GET /api/auth/self Response
- Shape:
  ```json
  {
    "subject": "user-uuid",
    "email": "user@example.com",
    "name": "John Doe",
    "roles": ["admin"]
  }
  ```
- Refactor strategy: New endpoint; returns user info extracted from validated JWT
- Evidence: Standard pattern for "who am I" endpoints in BFF architectures

---

- Entity / contract: OIDC Discovery Response (external)
- Shape:
  ```json
  {
    "issuer": "https://auth.example.com/realms/iot",
    "jwks_uri": "https://auth.example.com/realms/iot/protocol/openid-connect/certs",
    "authorization_endpoint": "https://auth.example.com/realms/iot/protocol/openid-connect/auth",
    "token_endpoint": "https://auth.example.com/realms/iot/protocol/openid-connect/token",
    "end_session_endpoint": "https://auth.example.com/realms/iot/protocol/openid-connect/logout"
  }
  ```
- Refactor strategy: External contract from OIDC provider; fetch once at startup and cache endpoints
- Evidence: Standard OIDC discovery spec (RFC 8414)

---

- Entity / contract: Token Exchange Request (to Keycloak)
- Shape:
  ```
  POST /protocol/openid-connect/token
  Content-Type: application/x-www-form-urlencoded

  grant_type=authorization_code
  &code=<authorization_code>
  &redirect_uri=<redirect_uri>
  &client_id=<client_id>
  &client_secret=<client_secret>
  &code_verifier=<pkce_verifier>
  ```
- Refactor strategy: External contract; OidcClientService sends this to exchange authorization code for tokens
- Evidence: OAuth 2.0 token endpoint spec (RFC 6749)

---

- Entity / contract: Token Exchange Response (from Keycloak)
- Shape:
  ```json
  {
    "access_token": "<jwt>",
    "refresh_token": "<jwt>",
    "token_type": "Bearer",
    "expires_in": 300,
    "refresh_expires_in": 1800
  }
  ```
- Refactor strategy: External contract; access_token stored in HttpOnly cookie; refresh_token optionally stored for silent refresh
- Evidence: OAuth 2.0 token response spec (RFC 6749)

---

- Entity / contract: Error Response for Authentication Failures
- Shape:
  ```json
  {
    "error": "Authentication required",
    "details": {"message": "No valid token provided"},
    "code": "AUTHENTICATION_REQUIRED",
    "correlationId": "uuid"
  }
  ```
- Refactor strategy: New error codes added; existing error response format unchanged
- Evidence: `app/utils/error_handling.py:26-46` — existing error response builder

## 4) API / Integration Surface

- Surface: GET `/api/auth/self`
- Inputs: JWT token in `access_token` cookie
- Outputs: `{"subject": "...", "email": "...", "name": "...", "roles": [...]}`
- Errors: 401 `AUTHENTICATION_REQUIRED` if no valid token
- Evidence: BFF pattern requirement; frontend calls this to check auth status

---

- Surface: GET `/api/auth/login`
- Inputs: Query parameter `redirect` (required) - URL to redirect after login
- Outputs: 302 redirect to Keycloak authorization endpoint with PKCE challenge
- Errors: 400 if `redirect` parameter missing
- Evidence: BFF pattern; initiates OIDC authorization code flow

---

- Surface: GET `/api/auth/callback`
- Inputs: Query parameters `code` (authorization code) and `state` (CSRF token) from Keycloak
- Outputs: 302 redirect to original `redirect` URL; sets `access_token` HttpOnly cookie
- Errors: 400 if state invalid; 401 if token exchange fails
- Evidence: OIDC callback handler; exchanges code for tokens

---

- Surface: GET `/api/auth/logout`
- Inputs: Query parameter `redirect` (optional) - URL to redirect after logout (default: `/`)
- Outputs: 302 redirect to `redirect` URL; clears `access_token` cookie
- Errors: None (logout always succeeds)
- Evidence: BFF pattern; clears local session and optionally redirects to Keycloak logout

---

- Surface: GET/POST/PUT/DELETE `/api/configs/*`
- Inputs: JWT token in `access_token` cookie OR `Authorization: Bearer <token>` header
- Outputs: Existing response bodies unchanged; 401 if no token; 403 if insufficient role
- Errors: 401 `AUTHENTICATION_REQUIRED` (no token, expired, invalid); 403 `AUTHORIZATION_FAILED` (lacks required role)
- Evidence: `app/api/configs.py:*` — existing endpoints without auth

---

- Surface: POST `/api/assets`
- Inputs: JWT token with `admin` OR `asset-uploader` role; existing multipart form-data unchanged
- Outputs: Existing 200 response unchanged; 401 if no token; 403 if user lacks both roles
- Errors: 401 if unauthenticated; 403 if user has token but neither `admin` nor `asset-uploader` role
- Evidence: `app/api/assets.py:26-155` — existing endpoint; only endpoint with `asset-uploader` access

---

- Surface: GET `/api/health`
- Inputs: No authentication required (marked with `@public` decorator)
- Outputs: Existing response unchanged
- Errors: No auth-related errors; endpoint remains publicly accessible
- Evidence: `app/api/health.py:14-29` — existing health check endpoint

---

- Surface: GET `/metrics`
- Inputs: No authentication required (outside `/api` blueprint)
- Outputs: Prometheus metrics including new auth metrics
- Errors: No auth-related errors
- Evidence: `app/api/metrics.py:15-30` — endpoint on root blueprint

## 5) Algorithms & State Machines

- Flow: OIDC Discovery and Endpoint Caching
- Steps:
  1. On OidcClientService initialization (if `OIDC_ENABLED=True`), fetch OIDC discovery document from `{issuer}/.well-known/openid-configuration`
  2. Extract and cache: `authorization_endpoint`, `token_endpoint`, `end_session_endpoint`, `jwks_uri`
  3. Pass `jwks_uri` to AuthService for JWKS fetching
  4. If discovery fetch fails, retry 3 times with exponential backoff; fail app startup if all retries fail
- States / transitions: None (one-time initialization)
- Hotspots: Discovery fetch at startup adds ~100-500ms to app initialization
- Evidence: Standard OIDC discovery pattern

---

- Flow: JWKS Fetching and Caching
- Steps:
  1. On first token validation, fetch JWKS from `jwks_uri`
  2. Cache keys with 5-minute TTL timestamp
  3. On subsequent validations, use cached keys if TTL not expired
  4. If token has unknown `kid`, refresh JWKS immediately and retry validation once
  5. If JWKS fetch fails but stale cache exists, use stale cache and log warning
  6. If JWKS fetch fails and no cache exists, raise AuthenticationException
- States / transitions: None (TTL-based caching)
- Hotspots: JWKS fetch on cache miss adds ~100-500ms; cached validation ~1-5ms
- Evidence: PyJWT library pattern for JWKS caching

---

- Flow: Authorization Code Flow with PKCE (Login)
- Steps:
  1. User visits `/api/auth/login?redirect=<url>`
  2. Generate PKCE code verifier (43-128 char random string) and code challenge (SHA256 hash)
  3. Generate random state nonce for CSRF protection
  4. Create `AuthState` with verifier, redirect URL, and nonce
  5. Serialize and sign `AuthState` into a cookie (using Flask's `itsdangerous`)
  6. Redirect to Keycloak authorization endpoint with: `client_id`, `response_type=code`, `redirect_uri`, `scope`, `state`, `code_challenge`, `code_challenge_method=S256`
- States / transitions: Browser state: "logging in" (has auth state cookie, awaiting callback)
- Hotspots: None (simple redirect)
- Evidence: OAuth 2.0 PKCE spec (RFC 7636)

---

- Flow: Token Exchange (Callback)
- Steps:
  1. Keycloak redirects to `/api/auth/callback?code=<code>&state=<state>`
  2. Extract and validate signed `AuthState` cookie; verify state nonce matches
  3. Exchange authorization code for tokens at Keycloak token endpoint (POST with client_id, client_secret, code, code_verifier, redirect_uri)
  4. Validate received access token using AuthService (signature, expiry, issuer, audience)
  5. Set `access_token` as HttpOnly cookie with configured security settings
  6. Clear auth state cookie
  7. Redirect to original `redirect_url` from AuthState
- States / transitions: Browser state: "logged in" (has access_token cookie)
- Hotspots: Token exchange HTTP call ~100-300ms
- Evidence: OAuth 2.0 token exchange pattern

---

- Flow: Request Authentication and Authorization
- Steps:
  1. Flask `before_request` hook runs for every request to `/api/*` endpoints
  2. If `OIDC_ENABLED=False`, skip authentication entirely and continue
  3. If endpoint has `is_public=True` attribute, skip authentication and continue
  4. Extract JWT token: first check `request.cookies.get(OIDC_COOKIE_NAME)`, then `Authorization` header with `Bearer` prefix
  5. If no token found, raise `AuthenticationException("No valid token provided")`
  6. Validate token via `AuthService.validate_token(token)` which returns `AuthContext`
  7. Store `AuthContext` in `flask.g.auth_context`
  8. Check authorization: if `admin` role present, allow all; if `asset-uploader` role and request is `POST /api/assets`, allow; else raise `AuthorizationException`
  9. Continue to API handler
- States / transitions: None (stateless per-request)
- Hotspots: Token validation ~1-5ms on cache hit
- Evidence: `app/api/__init__.py:3-19` — blueprint where before_request will be registered

---

- Flow: JWT Token Validation
- Steps:
  1. Receive raw JWT token string
  2. Decode JWT header (without verification) to extract `kid`
  3. Lookup signing key from cached JWKS using `kid`; if not found, refresh JWKS and retry once
  4. Validate JWT signature using public key
  5. Validate claims: `iss` matches issuer, `aud` matches audience, `exp` in future (with clock skew)
  6. Extract `sub`, `email` (optional), `name` (optional)
  7. Extract roles: union of `realm_access.roles` and `resource_access.<audience>.roles`
  8. Return `AuthContext(subject=sub, email=email, name=name, roles=roles_set)`
- States / transitions: None (stateless)
- Hotspots: Signature verification ~1-5ms
- Evidence: PyJWT library `jwt.decode()` with validation parameters

---

- Flow: Logout
- Steps:
  1. User visits `/api/auth/logout?redirect=<url>`
  2. Clear `access_token` cookie (set empty value with immediate expiry)
  3. Optionally redirect to Keycloak `end_session_endpoint` for SSO logout
  4. Redirect to `redirect` URL (or `/` if not specified)
- States / transitions: Browser state: "logged out" (no access_token cookie)
- Hotspots: None (simple redirect)
- Evidence: OIDC logout pattern

## 6) Derived State & Invariants

- Derived value: Cached JWKS keys with TTL expiry timestamp
  - Source: Fetched from OIDC provider's `jwks_uri` endpoint; all keys cached
  - Writes / cleanup: In-memory cache only; replaced atomically on refresh
  - Guards: Thread-safe access via lock; TTL checked before use; stale cache fallback
  - Invariant: JWKS cache must never be empty after first successful token validation
  - Evidence: `app/services/auth_service.py` (new file)

---

- Derived value: Cached OIDC discovery endpoints
  - Source: Fetched from `{issuer}/.well-known/openid-configuration` at startup
  - Writes / cleanup: Cached once at initialization; never refreshed during runtime
  - Guards: Startup validation ensures all required endpoints present
  - Invariant: If OidcClientService initialized successfully, all endpoints are valid URLs
  - Evidence: `app/services/oidc_client_service.py` (new file)

---

- Derived value: AuthContext in flask.g
  - Source: Extracted from validated JWT claims
  - Writes / cleanup: Set at request start; automatically cleared by Flask at request end
  - Guards: Only set after successful token validation; never persisted
  - Invariant: If `flask.g.auth_context` exists, the request is authenticated
  - Evidence: Flask request context lifecycle

---

- Derived value: AuthState in signed cookie
  - Source: Generated during `/api/auth/login`, contains PKCE verifier and redirect URL
  - Writes / cleanup: Created on login redirect; cleared after callback
  - Guards: Signed with app secret key; expires if callback not completed
  - Invariant: AuthState cookie only exists between login redirect and callback
  - Evidence: `itsdangerous` signed cookie pattern

## 7) Consistency, Transactions & Concurrency

- Transaction scope: No database transactions; authentication is stateless per-request
- Atomic requirements: JWKS cache updates must be atomic (replace entire cache under lock)
- Retry / idempotency: Token validation is idempotent; JWKS fetch retried once on unknown kid; token exchange retried 0 times (fail fast on callback)
- Ordering / concurrency controls: JWKS cache access protected by `threading.Lock`; Flask request context (`flask.g`) is thread-local
- Evidence: `app/services/auth_service.py` (new file) — singleton with thread-safe cache

## 8) Errors & Edge Cases

- Failure: No token provided (missing cookie and Authorization header)
- Surface: `before_request` hook
- Handling: Raise `AuthenticationException("No valid token provided")` → 401
- Guardrails: Check both cookie and header before failing; log with correlation ID
- Evidence: `app/utils/error_handling.py:66-88` — 401 response pattern

---

- Failure: Token expired
- Surface: `AuthService.validate_token()`
- Handling: PyJWT raises `ExpiredSignatureError` → `AuthenticationException("Token has expired")` → 401
- Guardrails: 30-second clock skew tolerance
- Evidence: PyJWT library behavior

---

- Failure: Invalid token signature
- Surface: `AuthService.validate_token()`
- Handling: PyJWT raises `InvalidSignatureError` → `AuthenticationException("Invalid token signature")` → 401
- Guardrails: Refresh JWKS once on unknown kid and retry
- Evidence: PyJWT library behavior

---

- Failure: Invalid issuer or audience
- Surface: `AuthService.validate_token()`
- Handling: PyJWT raises validation error → `AuthenticationException("Token issuer/audience mismatch")` → 401
- Guardrails: Log expected vs actual values
- Evidence: PyJWT `jwt.decode()` with validation

---

- Failure: OIDC discovery unreachable at startup
- Surface: `OidcClientService.__init__()`
- Handling: Retry 3 times with exponential backoff; fail app startup if all fail
- Guardrails: Validate required config before attempting fetch
- Evidence: Fail-fast on misconfiguration

---

- Failure: JWKS endpoint unreachable during runtime
- Surface: `AuthService._refresh_jwks()`
- Handling: Use stale cache if available and log warning; raise `AuthenticationException` if no cache
- Guardrails: Increment `iot_jwks_refresh_total{status="failed"}` metric
- Evidence: Graceful degradation pattern

---

- Failure: User has valid token but no recognized role
- Surface: `before_request` hook
- Handling: Raise `AuthorizationException("Insufficient permissions")` → 403
- Guardrails: Log user subject and roles
- Evidence: `app/utils/error_handling.py` — 403 response pattern

---

- Failure: Asset-uploader attempts non-asset endpoint
- Surface: `before_request` hook
- Handling: Raise `AuthorizationException("Insufficient permissions - asset-uploader role only permits uploading assets")` → 403
- Guardrails: Check exact path `/api/assets` and method `POST`
- Evidence: Role-based access control requirement

---

- Failure: Missing redirect parameter on /api/auth/login
- Surface: `/api/auth/login` endpoint
- Handling: Return 400 with error message "redirect parameter required"
- Guardrails: Validate redirect URL is relative or same-origin (prevent open redirect)
- Evidence: Standard OAuth security practice

---

- Failure: Invalid or expired auth state cookie on callback
- Surface: `/api/auth/callback` endpoint
- Handling: Return 400 with error message "Invalid or expired auth state"
- Guardrails: Signed cookie prevents tampering; short TTL prevents replay
- Evidence: CSRF protection via state parameter

---

- Failure: Token exchange fails (invalid code, expired code)
- Surface: `/api/auth/callback` endpoint
- Handling: Log error details; redirect to login with error parameter
- Guardrails: Log correlation ID and Keycloak error response
- Evidence: OAuth token exchange error handling

---

- Failure: OIDC_ENABLED=True but required config missing
- Surface: `OidcClientService.__init__()` or Settings validation
- Handling: Raise `ValueError` with clear message listing missing fields
- Guardrails: Validate at startup before any requests
- Evidence: Fail-fast on misconfiguration

## 9) Observability / Telemetry

- Signal: `iot_auth_validation_total`
- Type: Counter
- Trigger: Every token validation attempt
- Labels / fields: `status` (success, expired, invalid_signature, invalid_claims, no_token), `token_source` (cookie, bearer)
- Consumer: Grafana dashboard; alert on high failure rate
- Evidence: `app/services/metrics_service.py:28-33` — counter pattern

---

- Signal: `iot_auth_validation_duration_seconds`
- Type: Histogram
- Trigger: Token validation duration
- Labels / fields: `token_source` (cookie, bearer)
- Consumer: Grafana p50/p95/p99 dashboard
- Evidence: `app/services/metrics_service.py:39-43` — histogram pattern

---

- Signal: `iot_jwks_refresh_total`
- Type: Counter
- Trigger: Every JWKS refresh attempt
- Labels / fields: `trigger` (ttl_expiry, unknown_kid, startup), `status` (success, failed)
- Consumer: Grafana dashboard; alert on repeated failures
- Evidence: `app/services/metrics_service.py:28-33` — counter pattern

---

- Signal: `iot_oidc_token_exchange_total`
- Type: Counter
- Trigger: Every token exchange attempt in callback
- Labels / fields: `status` (success, failed)
- Consumer: Grafana dashboard for login success rate
- Evidence: New metric for BFF flow

---

- Signal: Structured log: "Token validation failed"
- Type: Structured log (ERROR level)
- Trigger: Failed token validation
- Labels / fields: `correlation_id`, `failure_reason`, `token_source`
- Consumer: Log aggregation for debugging
- Evidence: `app/utils/error_handling.py:23-24` — logging pattern

---

- Signal: Structured log: "Authentication successful"
- Type: Structured log (INFO level)
- Trigger: Successful token validation
- Labels / fields: `correlation_id`, `subject`, `email`, `roles`, `token_source`
- Consumer: Audit trail
- Evidence: `app/api/assets.py:83-87` — logging pattern

---

- Signal: Structured log: "OIDC login initiated"
- Type: Structured log (INFO level)
- Trigger: `/api/auth/login` endpoint called
- Labels / fields: `correlation_id`, `redirect_url`
- Consumer: Login flow debugging
- Evidence: New log for BFF flow

---

- Signal: Structured log: "OIDC callback completed"
- Type: Structured log (INFO level)
- Trigger: Successful `/api/auth/callback`
- Labels / fields: `correlation_id`, `subject`, `email`
- Consumer: Login success tracking
- Evidence: New log for BFF flow

## 10) Background Work & Shutdown

- Worker / job: None (no background threads)
- Trigger cadence: N/A
- Responsibilities: JWKS caching is synchronous on-demand; no background polling
- Shutdown handling: No shutdown hooks required; in-memory caches discarded on termination
- Evidence: `app/services/metrics_service.py:10-20` — pattern for services without background threads

## 11) Security & Permissions

- Concern: Authentication bypass via OIDC_ENABLED=False in production
- Touchpoints: `app/config.py`, `before_request` hook
- Mitigation: Document that OIDC_ENABLED must be True in production; log warning at startup if False
- Residual risk: Operator error; acceptable for trusted homelab
- Evidence: `app/config.py:23-25` — environment settings pattern

---

- Concern: Token leakage via non-HTTPS
- Touchpoints: Cookie transmission, Authorization header
- Mitigation: Document HTTPS requirement; `Secure` flag on cookie when `OIDC_COOKIE_SECURE=True`
- Residual risk: Operator misconfiguration; acceptable for trusted network
- Evidence: `docs/product_brief.md:38` — trusted network assumption

---

- Concern: CSRF on auth endpoints
- Touchpoints: `/api/auth/login`, `/api/auth/callback`
- Mitigation: State parameter with signed cookie; validate state matches on callback
- Residual risk: None if state validation implemented correctly
- Evidence: OAuth 2.0 state parameter spec

---

- Concern: Open redirect on /api/auth/login
- Touchpoints: `redirect` parameter
- Mitigation: Validate redirect URL is relative or same-origin; reject external URLs
- Residual risk: Implementation bug; test coverage required
- Evidence: OWASP open redirect prevention

---

- Concern: JWKS cache poisoning
- Touchpoints: JWKS fetch and cache
- Mitigation: Always fetch over HTTPS; validate response structure
- Residual risk: Compromised OIDC provider; acceptable (trust provider)
- Evidence: `app/services/auth_service.py` (new file)

---

- Concern: Client secret exposure
- Touchpoints: `OIDC_CLIENT_SECRET` in environment
- Mitigation: Secret managed via Kubernetes secrets; never logged
- Residual risk: Operator misconfiguration; standard secret management
- Evidence: Standard 12-factor app pattern

---

- Concern: Cookie security settings
- Touchpoints: `access_token` cookie
- Mitigation: HttpOnly (no JS access), Secure (HTTPS only), SameSite=Lax (CSRF protection)
- Residual risk: None if settings correct
- Evidence: Cookie security best practices

## 12) UX / UI Impact

- Entry point: N/A (backend-only change)
- Change: Frontend simplified to use `/api/auth/self`, `/api/auth/login`, `/api/auth/logout` endpoints
- User interaction: On 401, frontend redirects to `/api/auth/login`; on 403, shows "Insufficient permissions"
- Dependencies: Frontend must handle redirects and check `/api/auth/self` on load
- Evidence: `docs/features/oidc_auth/plan_addition.md:215-249` — frontend integration example

## 13) Deterministic Test Plan

- Surface: `AuthService.validate_token()`
- Scenarios:
  - Given valid JWT with admin role, When validate_token(), Then return AuthContext with admin in roles
  - Given valid JWT with asset-uploader role, When validate_token(), Then return AuthContext with asset-uploader in roles
  - Given valid JWT with both realm_access and resource_access roles, When validate_token(), Then return union of roles
  - Given valid JWT with email claim, When validate_token(), Then AuthContext.email is populated
  - Given valid JWT without email claim (M2M), When validate_token(), Then AuthContext.email is None
  - Given valid JWT with name claim, When validate_token(), Then AuthContext.name is populated
  - Given expired JWT, When validate_token(), Then raise AuthenticationException("Token has expired")
  - Given JWT with invalid signature, When validate_token(), Then raise AuthenticationException("Invalid token signature")
  - Given JWT with wrong issuer, When validate_token(), Then raise AuthenticationException
  - Given JWT with wrong audience, When validate_token(), Then raise AuthenticationException
  - Given JWT with unknown kid, When validate_token(), Then refresh JWKS and retry once
  - Given JWKS cache expired, When validate_token(), Then refresh JWKS before validation
  - Given JWKS fetch fails but stale cache exists, When validate_token(), Then use stale cache
  - Given JWKS fetch fails and no cache, When validate_token(), Then raise AuthenticationException
- Fixtures / hooks: Mock httpx for OIDC discovery and JWKS; JWT token factory fixture; mock time for TTL tests
- Gaps: None
- Evidence: `tests/services/test_config_service.py` — service test pattern

---

- Surface: `OidcClientService`
- Scenarios:
  - Given valid config, When initialized, Then fetch and cache discovery endpoints
  - Given discovery fetch fails, When initialized, Then retry 3 times then raise
  - Given valid state, When generate_authorization_url(), Then return URL with PKCE challenge
  - Given authorization code, When exchange_code_for_tokens(), Then return tokens
  - Given invalid code, When exchange_code_for_tokens(), Then raise exception
  - Given valid refresh token, When refresh_access_token(), Then return new access token
- Fixtures / hooks: Mock httpx for all OIDC HTTP calls
- Gaps: None
- Evidence: `tests/services/test_config_service.py` — service test pattern

---

- Surface: Flask `before_request` hook
- Scenarios:
  - Given OIDC_ENABLED=False, When request to /api/configs, Then allow without auth
  - Given @public endpoint, When request to /api/health, Then allow without auth
  - Given valid token in cookie, When request to /api/configs, Then authenticate and allow
  - Given valid token in Bearer header, When request to /api/configs, Then authenticate and allow
  - Given token in both cookie and header, When request, Then prefer cookie
  - Given no token, When request to /api/configs, Then return 401
  - Given expired token, When request, Then return 401
  - Given valid token with admin role, When any /api request, Then allow
  - Given valid token with asset-uploader role, When POST /api/assets, Then allow
  - Given valid token with asset-uploader role, When GET /api/configs, Then return 403
  - Given valid token with no recognized role, When request, Then return 403
- Fixtures / hooks: JWT token factory; FlaskClient
- Gaps: None
- Evidence: `tests/api/test_health.py` — API test pattern

---

- Surface: GET `/api/auth/self`
- Scenarios:
  - Given valid token in cookie, When GET /api/auth/self, Then return 200 with user info
  - Given no token, When GET /api/auth/self, Then return 401
  - Given expired token, When GET /api/auth/self, Then return 401
  - Given valid M2M token (no email/name), When GET /api/auth/self, Then return 200 with null email/name
- Fixtures / hooks: JWT token factory; FlaskClient
- Gaps: None
- Evidence: `tests/api/test_health.py` — API test pattern

---

- Surface: GET `/api/auth/login`
- Scenarios:
  - Given redirect parameter, When GET /api/auth/login, Then redirect to Keycloak with PKCE
  - Given no redirect parameter, When GET /api/auth/login, Then return 400
  - Given external redirect URL, When GET /api/auth/login, Then return 400 (open redirect protection)
  - Given valid request, When GET /api/auth/login, Then set auth state cookie
- Fixtures / hooks: Mock Keycloak authorization URL
- Gaps: None
- Evidence: OAuth flow testing pattern

---

- Surface: GET `/api/auth/callback`
- Scenarios:
  - Given valid code and state, When GET /api/auth/callback, Then exchange code, set cookie, redirect
  - Given invalid state, When GET /api/auth/callback, Then return 400
  - Given missing state cookie, When GET /api/auth/callback, Then return 400
  - Given token exchange fails, When GET /api/auth/callback, Then redirect to login with error
  - Given successful callback, When GET /api/auth/callback, Then clear auth state cookie
- Fixtures / hooks: Mock httpx for token exchange; signed cookie utilities
- Gaps: None
- Evidence: OAuth callback testing pattern

---

- Surface: GET `/api/auth/logout`
- Scenarios:
  - Given logged in user, When GET /api/auth/logout, Then clear cookie and redirect
  - Given redirect parameter, When GET /api/auth/logout, Then redirect to specified URL
  - Given no redirect parameter, When GET /api/auth/logout, Then redirect to /
- Fixtures / hooks: FlaskClient
- Gaps: None
- Evidence: Simple redirect testing

---

- Surface: Prometheus Metrics
- Scenarios:
  - Given successful validation, When validate_token(), Then increment success counter
  - Given failed validation, When validate_token(), Then increment failure counter with reason
  - Given JWKS refresh, When refresh triggered, Then increment refresh counter
  - Given token exchange, When callback completes, Then increment exchange counter
- Fixtures / hooks: Inspect prometheus_client registry
- Gaps: None
- Evidence: `tests/api/test_assets.py` — metrics testing pattern

---

- Surface: Error Response Format
- Scenarios:
  - Given AuthenticationException, When handled, Then return 401 with standard format
  - Given AuthorizationException, When handled, Then return 403 with standard format
- Fixtures / hooks: FlaskClient
- Gaps: None
- Evidence: `tests/api/test_configs.py` — error response testing

## 14) Implementation Slices

- Slice: Configuration and Exceptions
- Goal: Add OIDC settings and custom auth exceptions; establish error handling foundation
- Touches: `pyproject.toml`, `app/config.py`, `app/exceptions.py`, `app/utils/error_handling.py`
- Dependencies: None; prerequisite for all other slices

---

- Slice: AuthService (JWT Validation)
- Goal: Implement JWT validation with JWKS discovery and caching; return AuthContext
- Touches: `app/services/auth_service.py` (new), `app/services/container.py`, `tests/services/test_auth_service.py` (new)
- Dependencies: Slice 1

---

- Slice: OidcClientService (Token Exchange)
- Goal: Implement OIDC discovery, authorization URL generation with PKCE, token exchange
- Touches: `app/services/oidc_client_service.py` (new), `app/services/container.py`, `tests/services/test_oidc_client_service.py` (new)
- Dependencies: Slice 1

---

- Slice: Authentication Middleware
- Goal: Implement before_request hook and @public decorator for auth enforcement
- Touches: `app/utils/auth.py` (new), `app/api/__init__.py`, `app/api/health.py`, `app/__init__.py`
- Dependencies: Slice 2

---

- Slice: Auth Endpoints
- Goal: Implement /api/auth/self, /api/auth/login, /api/auth/callback, /api/auth/logout (all `@public`)
- Touches: `app/api/auth.py` (new), `app/api/__init__.py`, `app/__init__.py`, `tests/api/test_auth_endpoints.py` (new)
- Dependencies: Slice 2, Slice 3

---

- Slice: Metrics Integration
- Goal: Add Prometheus metrics for auth operations
- Touches: `app/services/metrics_service.py`, `app/services/auth_service.py`, `app/services/oidc_client_service.py`
- Dependencies: Slice 2, Slice 3

---

- Slice: Integration Tests
- Goal: End-to-end tests for complete auth flows
- Touches: `tests/api/test_auth_middleware.py` (new), `tests/conftest.py`
- Dependencies: All previous slices

## 15) Risks & Open Questions

- Risk: PKCE state stored in signed cookie could be large
- Impact: Cookie size limits (~4KB); may fail if redirect URL is very long
- Mitigation: Compress state or truncate/hash redirect URL; test with realistic URLs

---

- Risk: Token refresh strategy not fully specified
- Impact: Users may need to re-login more frequently than expected
- Mitigation: Initially implement simple flow (no automatic refresh); add refresh later if needed; access tokens typically valid 5+ minutes which covers most user sessions

---

- Risk: Keycloak logout (SSO) adds complexity
- Impact: User may remain logged into Keycloak even after local logout
- Mitigation: Initial implementation clears local cookie only; document SSO logout as future enhancement

---

- Risk: Race condition during JWKS refresh
- Impact: Multiple concurrent requests could trigger multiple JWKS fetches
- Mitigation: Use threading.Lock to serialize JWKS refresh; only one fetch at a time

---

- Risk: Open redirect vulnerability on /api/auth/login
- Impact: Attacker could redirect users to malicious site after login
- Mitigation: Validate redirect URL is relative or same-origin; reject absolute URLs to external domains

---

**Open Questions (Resolved)**

1. **State storage**: Use signed cookies (stateless) — resolved in favor of simplicity
2. **Refresh token storage**: Not storing refresh tokens initially; may add later — resolved
3. **Keycloak logout**: Clear local cookie only initially — resolved
4. **Token refresh strategy**: No automatic refresh initially — resolved

## 16) Confidence

Confidence: High — Plan is comprehensive with detailed flows for BFF pattern, clear test scenarios, and well-defined implementation slices. OIDC/OAuth patterns are well-established; PyJWT and Flask patterns are proven. Risks are identified with mitigations. No blocking unknowns remain.
