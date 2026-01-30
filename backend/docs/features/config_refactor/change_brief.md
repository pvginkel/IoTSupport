# Configuration System Refactor

## Overview

Refactor the configuration system to separate environment variable loading from application configuration. This creates a clean separation between raw environment input and resolved application settings.

## Current State

The current `Settings` class in `app/config.py` mixes concerns:
- Loads environment variables via pydantic-settings
- Contains fallback logic scattered in properties (e.g., `keycloak_admin_url`)
- Has fallback logic at point-of-use in services (e.g., `OIDC_AUDIENCE or OIDC_CLIENT_ID`)
- Contains derivation logic in services (e.g., deriving Fernet key from SECRET_KEY)
- Uses `@lru_cache` on `get_settings()` for singleton behavior
- Has mutable override mechanism (`set_engine_options_override`) for tests

## Target State

Two distinct classes:

1. **`Environment`** (pydantic-settings BaseSettings)
   - Loads raw environment variables
   - UPPER_CASE field names matching env vars
   - `str | None` for optional fields
   - No transformation logic

2. **`Settings`** (Pydantic BaseModel, frozen)
   - Clean application configuration with resolved values
   - lowercase field names (Python convention)
   - No `Optional` for fields that have defaults after transformation
   - `Settings.load() -> Settings` classmethod that:
     - Loads `Environment`
     - Transforms/resolves all values
     - Runs production validation
     - Returns immutable `Settings` instance

## Key Transformations to Centralize

| Source | Target Field | Logic |
|--------|--------------|-------|
| `DEVICE_BASEURL`, `BASEURL` | `device_baseurl` | `DEVICE_BASEURL or BASEURL` |
| `FERNET_KEY`, `SECRET_KEY` | `fernet_key` | `FERNET_KEY or derive_from(SECRET_KEY)` |
| `OIDC_AUDIENCE`, `OIDC_CLIENT_ID` | `oidc_audience` | `OIDC_AUDIENCE or OIDC_CLIENT_ID` |
| `KEYCLOAK_BASE_URL`, `KEYCLOAK_REALM` | `keycloak_admin_url` | `f"{base}/admin/realms/{realm}"` |
| `KEYCLOAK_BASE_URL`, `KEYCLOAK_REALM` | `keycloak_console_base_url` | `f"{base}/admin/master/console/#/{realm}/clients"` |
| `BASEURL` | `oidc_cookie_secure` | `OIDC_COOKIE_SECURE if set else BASEURL.startswith("https://")` |
| Various | `sqlalchemy_engine_options` | Default pool config dict |

## Test Strategy

- Tests construct `Settings` directly with test values (bypassing `Settings.load()`)
- `sqlalchemy_engine_options` becomes a regular field tests can override
- Remove `set_engine_options_override` mechanism
- No need for `get_settings()` with `@lru_cache` - DI container holds singleton

## Trigger

User requested adding `DEVICE_BASEURL` environment variable, which revealed the need for a cleaner pattern for handling configuration defaults and derivations.
