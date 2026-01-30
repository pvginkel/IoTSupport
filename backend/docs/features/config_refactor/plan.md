# Configuration System Refactor - Technical Plan

## 0) Research Log & Findings

### Areas Researched

**Current Configuration System (`app/config.py`)**
- The `Settings` class inherits from `pydantic_settings.BaseSettings` and loads directly from environment variables
- Uses UPPER_CASE field names matching environment variables
- Contains mixed concerns: environment loading, property derivation, validation
- Has mutable override mechanism (`set_engine_options_override`) for tests
- Uses `@lru_cache` on `get_settings()` for singleton behavior
- Contains properties like `keycloak_admin_url`, `keycloak_console_base_url`, and `is_production` that derive values

**Configuration Usage Patterns**
- Services receive `Settings` via dependency injection through `ServiceContainer`
- Container wires `config.provided.FIELD_NAME` for specific fields (e.g., `MQTT_URL`, `ASSETS_DIR`)
- API modules access config via `Provide[ServiceContainer.config]`
- All field access uses UPPER_CASE names throughout the codebase

**Fernet Key Derivation**
- Currently in `DeviceService.__init__()` (`app/services/device_service.py:77-84`)
- If `FERNET_KEY` not set, derives from `SECRET_KEY` using SHA256
- The `_derive_fernet_key()` helper function is defined in the same file

**Test Fixtures**
- Tests in `tests/conftest.py` construct `Settings` directly with `_env_file=None`
- Use `set_engine_options_override()` for SQLite pool configuration
- Model copying with `settings.model_copy()` for per-test isolation

**Cookie Secure Flag**
- Logic in `app/utils/auth.py:get_cookie_secure()` derives from `BASEURL` if not explicitly set

### Key Findings

1. **Field naming transition**: All existing code uses UPPER_CASE field names. The refactor to lowercase will require updating ~80+ usage sites across API modules and services.

2. **Test isolation pattern**: Tests use `model_copy()` to create independent settings instances. Current tests mutate `DATABASE_URL` after copying, which conflicts with frozen models. Solution: use `model_copy(update={"database_url": "..."})` pattern instead of direct attribute assignment.

3. **Engine options override**: Only used in tests for SQLite static pool configuration. Can be replaced by making `sqlalchemy_engine_options` a regular field.

4. **get_settings() usage**: Used in `run.py`, `app/__init__.py`, and `app/database.py`. The DI container already provides singleton behavior, so `@lru_cache` is redundant.

5. **Derivation logic scattered**: DEVICE_BASEURL fallback is in two places (`device_service.py` and `iot.py`), cookie secure derivation is in `utils/auth.py`, Fernet derivation is in `device_service.py`.

---

## 1) Intent & Scope

**User intent**

Refactor the configuration system to cleanly separate environment variable loading from application settings. Introduce `DEVICE_BASEURL` environment variable that defaults to `BASEURL` if not set, and centralize all derivation/fallback logic in a single transformation step.

**Prompt quotes**

- "Add `DEVICE_BASEURL` environment variable that defaults to `BASEURL` if not set"
- "Create `Environment` class (pydantic-settings) for raw environment variable loading with UPPER_CASE fields"
- "Refactor `Settings` class to be a clean Pydantic BaseModel with lowercase fields and no env loading"
- "Implement `Settings.load()` classmethod that loads Environment, transforms values, validates, and returns Settings"
- "Centralize all fallback/derivation logic in the transformation"
- "Move Fernet key derivation logic from DeviceService into Settings.load()"
- "Remove `get_settings()` with `@lru_cache` - rely on DI container singleton"
- "Update all usages of config throughout the codebase to use new lowercase field names"

**In scope**

- Create new `Environment` class for raw env var loading
- Refactor `Settings` to Pydantic `BaseModel` with lowercase fields
- Implement `Settings.load()` transformation classmethod
- Centralize derivation logic (DEVICE_BASEURL, FERNET_KEY, OIDC_AUDIENCE, keycloak URLs, cookie secure)
- Move Fernet key derivation from `DeviceService` to `Settings.load()`
- Make `sqlalchemy_engine_options` a regular field
- Remove `set_engine_options_override()` mechanism
- Remove `@lru_cache` `get_settings()` function
- Update all config field access to lowercase names
- Update test fixtures to construct Settings directly

**Out of scope**

- Changes to environment variable names (they remain UPPER_CASE in the environment)
- Changes to the DI container architecture
- Changes to production validation logic (just moves to Settings.load())
- Database migrations
- API contract changes

**Assumptions / constraints**

- All configuration access goes through DI container or explicit `Settings.load()` call
- Tests can construct `Settings` directly, bypassing `Settings.load()`
- No backwards compatibility needed (BFF pattern per CLAUDE.md)
- Fernet key derivation algorithm remains unchanged (SHA256 of SECRET_KEY)

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Add `DEVICE_BASEURL` environment variable that defaults to `BASEURL` if not set
- [ ] Create `Environment` class (pydantic-settings) for raw environment variable loading with UPPER_CASE fields
- [ ] Refactor `Settings` class to be a clean Pydantic BaseModel with lowercase fields and no env loading
- [ ] Implement `Settings.load()` classmethod that loads Environment, transforms values, validates, and returns Settings
- [ ] Centralize all fallback/derivation logic in the transformation (DEVICE_BASEURL, FERNET_KEY, OIDC_AUDIENCE, keycloak URLs, cookie secure flag)
- [ ] Move Fernet key derivation logic from DeviceService into Settings.load()
- [ ] Make `sqlalchemy_engine_options` a regular field on Settings
- [ ] Remove `set_engine_options_override` mechanism - tests construct Settings directly
- [ ] Remove `get_settings()` with `@lru_cache` - rely on DI container singleton
- [ ] Update all usages of config throughout the codebase to use new lowercase field names
- [ ] Update test fixtures to construct Settings directly with test values

---

## 2) Affected Areas & File Map

### Core Configuration

- Area: `app/config.py`
- Why: Complete rewrite - split into Environment and Settings classes, add load() classmethod, remove get_settings()
- Evidence: `app/config.py:23-321` — entire Settings class and get_settings function

### Application Factory

- Area: `app/__init__.py`
- Why: Update get_settings() call to Settings.load(), update field access to lowercase
- Evidence: `app/__init__.py:12,23` — `from app.config import get_settings` and `settings = get_settings()`

### Entry Point

- Area: `run.py`
- Why: Update get_settings() call to Settings.load(), update FLASK_ENV access
- Evidence: `run.py:9,18,24` — `from app.config import get_settings`, `settings = get_settings()`, `settings.FLASK_ENV`

### Database Module

- Area: `app/database.py`
- Why: Update get_settings() call to Settings.load(), update DATABASE_URL access
- Evidence: `app/database.py:13,55,57` — `from app.config import get_settings`, `settings = get_settings()`, `settings.DATABASE_URL`

### Service Container

- Area: `app/services/container.py`
- Why: Update config.provided field references to lowercase
- Evidence: `app/services/container.py:40-43,90` — `config.provided.MQTT_URL`, `config.provided.ASSETS_DIR`
- Before/After example:
```python
# Before
mqtt_service = providers.Singleton(
    MqttService,
    mqtt_url=config.provided.MQTT_URL,
    mqtt_username=config.provided.MQTT_USERNAME,
    mqtt_password=config.provided.MQTT_PASSWORD,
)
firmware_service = providers.Singleton(
    FirmwareService,
    assets_dir=config.provided.ASSETS_DIR,
)

# After
mqtt_service = providers.Singleton(
    MqttService,
    mqtt_url=config.provided.mqtt_url,
    mqtt_username=config.provided.mqtt_username,
    mqtt_password=config.provided.mqtt_password,
)
firmware_service = providers.Singleton(
    FirmwareService,
    assets_dir=config.provided.assets_dir,
)
```

### Device Service

- Area: `app/services/device_service.py`
- Why: Remove Fernet key derivation (moved to Settings.load()), update field access to lowercase
- Evidence: `app/services/device_service.py:33-44,77-84,460-465` — `_derive_fernet_key()`, Fernet initialization, provisioning package

### Auth Service

- Area: `app/services/auth_service.py`
- Why: Update field access to lowercase
- Evidence: `app/services/auth_service.py:58-61,103,151,158,160` — OIDC_ENABLED, OIDC_ISSUER_URL, etc.

### Keycloak Admin Service

- Area: `app/services/keycloak_admin_service.py`
- Why: Update field access to lowercase, use pre-computed keycloak_admin_url
- Evidence: `app/services/keycloak_admin_service.py:57-61,65,87-91` — Keycloak config fields

### OIDC Client Service

- Area: `app/services/oidc_client_service.py`
- Why: Update field access to lowercase
- Evidence: `app/services/oidc_client_service.py:74-79,100,220,224,227,265-266,341-342` — OIDC config fields

### Rotation Service

- Area: `app/services/rotation_service.py`
- Why: Update field access to lowercase
- Evidence: `app/services/rotation_service.py:104,165,215,221,242,444` — ROTATION_CRON, ROTATION_TIMEOUT_SECONDS, etc.

### API Modules

- Area: `app/api/auth.py`
- Why: Update field access to lowercase
- Evidence: `app/api/auth.py:79,99,158,167,175,189,221,238,267,271,284,288,299,309,338,348,353,361,394,398,404,408,418` — OIDC cookie and auth config fields

- Area: `app/api/__init__.py`
- Why: Update field access to lowercase
- Evidence: `app/api/__init__.py:66,87,128,132,136,140,152,156,167,171` — OIDC cookie config fields

- Area: `app/api/iot.py`
- Why: Update field access to lowercase
- Evidence: `app/api/iot.py:52,324-329` — OIDC_ENABLED, provisioning fields

- Area: `app/api/testing.py`
- Why: Update field access to lowercase
- Evidence: `app/api/testing.py:101,105,134,146,150` — OIDC cookie config fields

- Area: `app/api/pipeline.py`
- Why: Update field access to lowercase
- Evidence: `app/api/pipeline.py:148,191` — OIDC_TOKEN_URL

### Utility Modules

- Area: `app/utils/auth.py`
- Why: Remove get_cookie_secure logic (moved to Settings), update field access to lowercase
- Evidence: `app/utils/auth.py:151,257,348-362` — OIDC cookie fields, get_cookie_secure()

- Area: `app/utils/device_auth.py`
- Why: Update field access to lowercase
- Evidence: `app/utils/device_auth.py:13` — Settings import (TYPE_CHECKING)

### Test Fixtures

- Area: `tests/conftest.py`
- Why: Update to construct Settings directly without set_engine_options_override, use lowercase fields
- Evidence: `tests/conftest.py:56-71,85-90,113-118` — _build_test_settings, template_connection, app fixture

- Area: `tests/api/test_testing.py`
- Why: Update to construct Settings directly, use lowercase fields
- Evidence: `tests/api/test_testing.py:38-52,61-66,88-93` — _build_testing_settings, fixtures

- Area: `tests/api/test_auth_endpoints.py`
- Why: Update Settings imports/usage to lowercase
- Evidence: `tests/api/test_auth_endpoints.py:7` — Settings import

- Area: `tests/api/test_auth_middleware.py`
- Why: Update Settings imports/usage to lowercase
- Evidence: `tests/api/test_auth_middleware.py:13` — Settings import

- Area: `tests/api/test_pipeline.py`
- Why: Update Settings imports/usage to lowercase
- Evidence: `tests/api/test_pipeline.py:10` — Settings import

- Area: `tests/services/test_auth_service.py`
- Why: Update Settings imports/usage to lowercase
- Evidence: `tests/services/test_auth_service.py:7` — Settings import

---

## 3) Data Model / Contracts

### Environment Class (new)

- Entity / contract: `Environment` (pydantic-settings BaseSettings)
- Shape:
```python
class Environment(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    # All UPPER_CASE fields matching env vars
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    FLASK_ENV: str = "development"
    DEBUG: bool = True
    DATABASE_URL: str = "postgresql+psycopg://..."
    BASEURL: str = "http://localhost:3200"
    DEVICE_BASEURL: str | None = None  # NEW
    FERNET_KEY: str | None = None
    OIDC_ENABLED: bool = False
    OIDC_ISSUER_URL: str | None = None
    OIDC_CLIENT_ID: str | None = None
    OIDC_CLIENT_SECRET: str | None = None
    OIDC_AUDIENCE: str | None = None
    OIDC_COOKIE_SECURE: bool | None = None
    # ... all other env vars
```
- Refactor strategy: New class, no backward compatibility needed
- Evidence: `app/config.py:23-208` — current Settings class field definitions

### Settings Class (refactored)

- Entity / contract: `Settings` (Pydantic BaseModel, NOT frozen - tests need model_copy mutation)
- Shape:
```python
class Settings(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # Note: Not frozen=True because tests need model_copy(update={...}) to work with mutable copies

    # All lowercase fields with resolved values
    secret_key: str
    flask_env: str
    debug: bool
    database_url: str
    baseurl: str
    device_baseurl: str  # Resolved: DEVICE_BASEURL or BASEURL
    fernet_key: str  # Resolved: FERNET_KEY or derived from SECRET_KEY
    oidc_enabled: bool
    oidc_issuer_url: str | None
    oidc_client_id: str | None
    oidc_client_secret: str | None
    oidc_audience: str | None  # Resolved: OIDC_AUDIENCE or OIDC_CLIENT_ID
    oidc_cookie_secure: bool  # Resolved: explicit or inferred from BASEURL
    keycloak_admin_url: str | None  # Resolved: computed from base + realm
    keycloak_console_base_url: str | None  # Resolved: computed from base + realm
    sqlalchemy_engine_options: dict[str, Any]  # Regular field, not property
    # ... all other fields

    @classmethod
    def load(cls) -> "Settings":
        """Load from environment, transform, validate, return frozen instance."""
        ...
```
- Refactor strategy: Complete refactor of existing class, no backward compatibility needed
- Evidence: `app/config.py:23-321` — current Settings class

---

## 4) API / Integration Surface

No external API changes. This is an internal refactoring.

The only integration change is how the application bootstraps:

- Surface: Application startup (`app/__init__.py`, `run.py`)
- Inputs: Environment variables
- Outputs: Configured `Settings` instance passed to DI container
- Errors: `ConfigurationError` on validation failure in production mode
- Evidence: `app/__init__.py:17-28` — create_app function

---

## 5) Algorithms & State Machines

### Settings.load() Transformation Flow

- Flow: Environment to Settings transformation
- Steps:
  1. Load `Environment` from environment variables (pydantic-settings handles .env file)
  2. Compute `device_baseurl`: use `DEVICE_BASEURL` if set, else `BASEURL`
  3. Compute `fernet_key`: use `FERNET_KEY` if set, else derive from `SECRET_KEY` via SHA256
  4. Compute `oidc_audience`: use `OIDC_AUDIENCE` if set, else `OIDC_CLIENT_ID`
  5. Compute `oidc_cookie_secure`: use `OIDC_COOKIE_SECURE` if set, else `BASEURL.startswith("https://")`
  6. Compute `keycloak_admin_url`: if base and realm set, compute `f"{base}/admin/realms/{realm}"`
  7. Compute `keycloak_console_base_url`: if base and realm set, compute `f"{base}/admin/master/console/#/{realm}/clients"`
  8. Build default `sqlalchemy_engine_options` dict
  9. Strip trailing slashes from URL fields
  10. Construct Settings instance (validation happens via Pydantic model validation)
  11. Return Settings instance

Note: Production validation (`validate_production_config()`) is NOT called in `Settings.load()`. It remains in `create_app()` where it is called conditionally based on `FLASK_ENV != "testing"`. This preserves the current behavior where:
- Production apps validate required settings on startup
- Tests can construct minimal Settings without triggering validation
- The validation logic itself moves to Settings but is called by the app factory
- States / transitions: None (single-pass transformation)
- Hotspots: Fernet key derivation uses SHA256 which is fast; no performance concerns
- Evidence: `app/config.py:153-165` — current property implementations, `app/services/device_service.py:33-44` — Fernet derivation

---

## 6) Derived State & Invariants

- Derived value: `device_baseurl`
  - Source: `DEVICE_BASEURL` env var (may be None) + `BASEURL` env var (required)
  - Writes / cleanup: None (read-only after construction)
  - Guards: Must be non-empty after derivation; BASEURL is required
  - Invariant: `device_baseurl` is always a valid URL string
  - Evidence: `app/services/device_service.py:461`, `app/api/iot.py:325`

- Derived value: `fernet_key`
  - Source: `FERNET_KEY` env var (may be None) + `SECRET_KEY` env var (has default)
  - Writes / cleanup: None (read-only after construction)
  - Guards: In production, explicit `FERNET_KEY` is required (validation step)
  - Invariant: `fernet_key` is always a valid Fernet-compatible key (32-byte base64)
  - Evidence: `app/services/device_service.py:77-84`

- Derived value: `oidc_cookie_secure`
  - Source: `OIDC_COOKIE_SECURE` env var (may be None) + `BASEURL` env var
  - Writes / cleanup: None (read-only after construction)
  - Guards: None (always derivable)
  - Invariant: `oidc_cookie_secure` is always a boolean
  - Evidence: `app/utils/auth.py:348-362`

- Derived value: `keycloak_admin_url`
  - Source: `KEYCLOAK_BASE_URL` + `KEYCLOAK_REALM` env vars
  - Writes / cleanup: None (read-only after construction)
  - Guards: Both must be set for derivation; otherwise None
  - Invariant: Either None or a valid URL string
  - Evidence: `app/config.py:153-158`

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: Not applicable - Settings is immutable-by-convention after construction (not enforced via `frozen=True` to support test fixture patterns)
- Atomic requirements: Settings.load() must complete atomically or fail entirely (no partial state)
- Retry / idempotency: Settings.load() is idempotent given same environment
- Ordering / concurrency controls: Settings is safe for concurrent read access; production code should treat it as immutable
- Evidence: `app/config.py:23` — BaseSettings inheritance implies construction-time validation

---

## 8) Errors & Edge Cases

- Failure: `SECRET_KEY` is default value in production
- Surface: `Settings.load()` during application startup
- Handling: Raise `ConfigurationError` with message listing the issue
- Guardrails: `validate_production_config()` method called in load() when not testing
- Evidence: `app/config.py:228-236` — current SECRET_KEY validation

- Failure: `FERNET_KEY` not set in production
- Surface: `Settings.load()` during application startup
- Handling: Raise `ConfigurationError` with message listing the issue
- Guardrails: Production validation in load()
- Evidence: `app/config.py:237-241` — current FERNET_KEY validation

- Failure: Required Keycloak settings missing in production
- Surface: `Settings.load()` during application startup
- Handling: Raise `ConfigurationError` listing missing settings
- Guardrails: Production validation in load()
- Evidence: `app/config.py:243-254` — current Keycloak validation

- Failure: Invalid Fernet key derivation (malformed SECRET_KEY)
- Surface: `Settings.load()` during Fernet key computation
- Handling: Let cryptography library raise appropriate exception
- Guardrails: SHA256 handles any string input; base64 encoding always succeeds
- Evidence: `app/services/device_service.py:33-44` — derivation handles any string

---

## 9) Observability / Telemetry

No new metrics or telemetry for this refactoring. The configuration loading happens at startup before metrics are initialized.

Existing startup logging will continue to work:
- Signal: Log message "KeycloakAdminService initialized with URL: {keycloak_admin_url}"
- Type: Structured log
- Trigger: Service initialization after Settings.load()
- Labels / fields: keycloak_admin_url value
- Consumer: Application logs
- Evidence: `app/services/keycloak_admin_service.py:65` — existing log statement

---

## 10) Background Work & Shutdown

No background workers affected by this change. Settings is loaded once at startup and used throughout the application lifecycle.

---

## 11) Security & Permissions

- Concern: Sensitive configuration values (secrets, passwords)
- Touchpoints: `Settings.load()` transformation, `Environment` loading
- Mitigation: Settings is immutable-by-convention (not technically frozen to support test fixtures); production code should never mutate; secrets remain in memory only
- Residual risk: Configuration values visible in memory dumps (acceptable, same as current state)
- Evidence: `app/config.py:34,94-97,144-147,179-180` — SECRET_KEY, OIDC_CLIENT_SECRET, KEYCLOAK_ADMIN_CLIENT_SECRET, WIFI_PASSWORD

---

## 12) UX / UI Impact

Not applicable - this is a backend-only refactoring with no user-facing changes.

---

## 13) Deterministic Test Plan

### Settings.load() Unit Tests

- Surface: `Settings.load()` classmethod
- Test file: `tests/test_config.py` (new file)
- Scenarios:
  - Given environment with all required values, When Settings.load() called, Then returns Settings with correct lowercase fields (`tests/test_config.py::test_load_all_values`)
  - Given DEVICE_BASEURL not set, When Settings.load() called, Then device_baseurl equals baseurl (`tests/test_config.py::test_device_baseurl_fallback`)
  - Given DEVICE_BASEURL set, When Settings.load() called, Then device_baseurl equals DEVICE_BASEURL value (`tests/test_config.py::test_device_baseurl_explicit`)
  - Given FERNET_KEY not set, When Settings.load() called, Then fernet_key is derived from secret_key (`tests/test_config.py::test_fernet_key_derivation`)
  - Given FERNET_KEY set, When Settings.load() called, Then fernet_key equals FERNET_KEY value (`tests/test_config.py::test_fernet_key_explicit`)
  - Given OIDC_AUDIENCE not set but OIDC_CLIENT_ID set, When Settings.load() called, Then oidc_audience equals oidc_client_id (`tests/test_config.py::test_oidc_audience_fallback`)
  - Given OIDC_COOKIE_SECURE not set and BASEURL starts with https, When Settings.load() called, Then oidc_cookie_secure is True (`tests/test_config.py::test_cookie_secure_https`)
  - Given OIDC_COOKIE_SECURE not set and BASEURL starts with http, When Settings.load() called, Then oidc_cookie_secure is False (`tests/test_config.py::test_cookie_secure_http`)
  - Given KEYCLOAK_BASE_URL and KEYCLOAK_REALM set, When Settings.load() called, Then keycloak_admin_url is computed correctly (`tests/test_config.py::test_keycloak_admin_url`)
  - Given KEYCLOAK_BASE_URL not set, When Settings.load() called, Then keycloak_admin_url is None (`tests/test_config.py::test_keycloak_admin_url_none`)
  - Given production mode with default SECRET_KEY, When Settings.load() called, Then raises ConfigurationError (`tests/test_config.py::test_production_validation_secret_key`)
  - Given production mode without FERNET_KEY, When Settings.load() called, Then raises ConfigurationError (`tests/test_config.py::test_production_validation_fernet_key`)
  - Given testing mode, When Settings.load() called, Then validation is skipped (`tests/test_config.py::test_testing_mode_skips_validation`)
- Fixtures / hooks: Environment variable mocking via `monkeypatch.setenv()`, temporary .env files via `tmp_path`
- Gaps: None
- Evidence: `tests/conftest.py:50-71` — existing test settings construction patterns

### Environment Class Unit Tests

- Surface: `Environment` class (pydantic-settings)
- Test file: `tests/test_config.py`
- Scenarios:
  - Given .env file present, When Environment constructed, Then loads values from file (`tests/test_config.py::test_environment_loads_env_file`)
  - Given env vars set, When Environment constructed, Then env vars override .env file (`tests/test_config.py::test_environment_env_var_priority`)
  - Given extra env vars present, When Environment constructed, Then ignores extras (`tests/test_config.py::test_environment_ignores_extra`)
- Fixtures / hooks: `tmp_path` for .env file, `monkeypatch.setenv()` for env vars
- Gaps: None
- Evidence: `app/config.py:26-31` — current SettingsConfigDict

### Direct Settings Construction Tests

- Surface: `Settings` constructor (for test usage)
- Test file: `tests/test_config.py`
- Scenarios:
  - Given all required fields provided, When Settings constructed directly, Then instance is created with provided values (`tests/test_config.py::test_settings_direct_construction`)
  - Given sqlalchemy_engine_options provided, When Settings constructed, Then options are used directly (`tests/test_config.py::test_settings_engine_options`)
  - Given Settings instance, When model_copy with update called, Then new instance has updated values (`tests/test_config.py::test_settings_model_copy_update`)
- Fixtures / hooks: None needed
- Gaps: None
- Evidence: `tests/conftest.py:56-71` — existing direct construction pattern

### Test Fixture Migration Pattern

The test fixtures in `tests/conftest.py` must be updated to use `model_copy(update={...})` instead of direct attribute assignment:

```python
# Before (direct attribute assignment - will fail with frozen model)
settings = _build_test_settings(session_tmp_path).model_copy()
settings.DATABASE_URL = "sqlite://"
settings.set_engine_options_override({
    "poolclass": StaticPool,
    "creator": lambda: conn,
})

# After (model_copy with update dict)
base_settings = _build_test_settings(session_tmp_path)
settings = base_settings.model_copy(update={
    "database_url": "sqlite://",
    "sqlalchemy_engine_options": {
        "poolclass": StaticPool,
        "creator": lambda: conn,
    },
})
```

Note: `model_copy(update={...})` returns a new instance, which is the correct pattern for immutable-by-convention models. The model is not frozen (no `frozen=True`) to allow this pattern to work.

### Service Integration Tests

- Surface: Services using Settings
- Scenarios:
  - Given DeviceService with Settings containing fernet_key, When encrypting/decrypting secrets, Then operations succeed
  - Given AuthService with Settings, When validating tokens, Then uses lowercase oidc_* fields correctly
  - Given KeycloakAdminService with Settings, When making API calls, Then uses lowercase keycloak_* fields correctly
- Fixtures / hooks: Existing service test fixtures
- Gaps: None - existing tests will validate after field name updates
- Evidence: `tests/services/test_auth_service.py`, service tests throughout `tests/services/`

### API Integration Tests

- Surface: API endpoints using Settings
- Scenarios:
  - Given authenticated request, When processing cookies, Then uses lowercase oidc_cookie_* fields
  - Given IoT provisioning request, When building package, Then uses lowercase device_baseurl field
- Fixtures / hooks: Existing API test fixtures
- Gaps: None - existing tests will validate after field name updates
- Evidence: `tests/api/test_auth_endpoints.py`, `tests/api/test_iot.py`

---

## 14) Implementation Slices

### Slice 1: Create Environment and Settings classes

- Goal: New configuration architecture without breaking existing code
- Touches: `app/config.py`
- Dependencies: None; can add new classes alongside existing code initially

### Slice 2: Implement Settings.load() with all transformations

- Goal: Central transformation logic including Fernet derivation
- Touches: `app/config.py` (Settings.load method)
- Dependencies: Slice 1

### Slice 3: Update application bootstrap

- Goal: Application uses new Settings.load() instead of get_settings()
- Touches: `app/__init__.py`, `run.py`, `app/database.py`
- Dependencies: Slice 2

### Slice 4: Update service layer to lowercase fields

- Goal: All services use lowercase field names
- Touches: `app/services/device_service.py`, `app/services/auth_service.py`, `app/services/keycloak_admin_service.py`, `app/services/oidc_client_service.py`, `app/services/rotation_service.py`, `app/services/container.py`
- Dependencies: Slice 2

### Slice 5: Update API layer to lowercase fields

- Goal: All API modules use lowercase field names
- Touches: `app/api/auth.py`, `app/api/__init__.py`, `app/api/iot.py`, `app/api/testing.py`, `app/api/pipeline.py`
- Dependencies: Slice 2

### Slice 6: Update utility modules

- Goal: Auth utilities use lowercase fields, remove get_cookie_secure duplication
- Touches: `app/utils/auth.py`, `app/utils/device_auth.py`
- Dependencies: Slice 2

### Slice 7: Update test fixtures and cleanup

- Goal: Tests construct Settings directly, remove old mechanisms
- Touches: `tests/conftest.py`, `tests/api/test_testing.py`, other test files
- Dependencies: Slices 3-6

### Slice 8: Remove deprecated code

- Goal: Remove get_settings(), set_engine_options_override(), old properties
- Touches: `app/config.py`
- Dependencies: Slice 7

---

## 15) Risks & Open Questions

### Risks

- Risk: Large number of files to update may introduce typos or missed references
- Impact: Test failures or runtime errors
- Mitigation: Use grep/search to find all UPPER_CASE field references; run full test suite after each slice

- Risk: Tests may have hidden dependencies on current Settings behavior
- Impact: Test failures requiring additional fixes
- Mitigation: Run tests incrementally during implementation; address failures as they arise

- Risk: Settings.load() called multiple times could mask environment changes
- Impact: Unexpected behavior if environment changes after first load
- Mitigation: Document that Settings.load() reads environment once; DI container holds singleton

### Open Questions

None - requirements are clear and implementation path is well-defined. The following items were clarified during plan review:

1. **Frozen vs mutable Settings**: Settings is NOT frozen (`frozen=True`) to support test fixture pattern of `model_copy(update={...})`. Production code treats it as immutable by convention.

2. **Production validation location**: `validate_production_config()` remains in `create_app()`, not moved into `Settings.load()`. This preserves the current conditional validation based on FLASK_ENV.

3. **Test file locations**: New unit tests for Settings.load() and Environment go in `tests/test_config.py`.

---

## 16) Confidence

Confidence: High - The refactoring is well-scoped, follows established patterns, and all code paths are testable. The change brief provides clear requirements, and the codebase has good test coverage to catch regressions. Plan review identified and resolved three key concerns: frozen Settings vs test mutability, container wiring syntax, and test file locations.
