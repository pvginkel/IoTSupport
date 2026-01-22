# Database Configuration Storage - Technical Plan

## 0) Research Log & Findings

### Areas Researched

**Current Implementation (IoT Support Backend)**
- Reviewed `app/services/config_service.py`: File-based storage using JSON files named by MAC address (dash-separated format)
- Reviewed `app/api/configs.py`: Current endpoints use MAC address in URL paths for CRUD operations
- Reviewed `app/schemas/config.py`: Pydantic schemas for request/response validation
- Reviewed `app/services/container.py`: Simple DI container without database session management
- Reviewed `app/__init__.py`: Application factory without database initialization
- Reviewed `tests/conftest.py`: Test fixtures using temporary filesystem directories

**Reference Implementation (ElectronicsInventory)**
- Reviewed `app/extensions.py`: Flask-SQLAlchemy initialization pattern
- Reviewed `app/database.py`: Database utilities including Alembic migration helpers, connection checks, and upgrade functions
- Reviewed `app/exceptions.py`: Domain exceptions including `RecordNotFoundException`, `InvalidOperationException`, `RecordExistsException`
- Reviewed `app/services/base.py`: Simple `BaseService` class with `db` session injection
- Reviewed `app/services/container.py`: `ServiceContainer` with `ContextLocalSingleton` for `db_session`, `session_maker` dependency
- Reviewed `app/__init__.py`: Application factory with Flask-SQLAlchemy initialization, session management, and teardown handling
- Reviewed `alembic/env.py`: Alembic environment configuration with environment variable URL override
- Reviewed `alembic.ini`: Alembic configuration file structure
- Reviewed `app/models/box.py`: SQLAlchemy model example with typed annotations
- Reviewed `app/services/box_service.py`: Service example inheriting from `BaseService`
- Reviewed `tests/conftest.py`: Test fixtures using SQLite in-memory with template database pattern
- Reviewed `app/services/test_data_service.py`: Test data loading from JSON files
- Reviewed `app/cli.py`: CLI commands for database operations

### Key Findings

1. **Session Management Pattern**: ElectronicsInventory uses `ContextLocalSingleton` for `db_session` provider, allowing context-local session creation with automatic cleanup via `container.db_session.reset()`.

2. **BaseService Simplicity**: The `BaseService` class is minimal - just stores the session in `self.db`. Services inherit and use `self.db` for all database operations.

3. **Test Database Strategy**: Uses SQLite in-memory with a "template" database pattern - migrations applied once to a template connection, then cloned for each test using `sqlite3.Connection.backup()`.

4. **MAC Address Format Change**: Requirements specify changing from dash-separated (`aa-bb-cc-dd-ee-ff`) to colon-separated (`aa:bb:cc:dd:ee:ff`) format throughout.

5. **API Restructuring**: Moving from MAC-based URLs to surrogate ID-based URLs for CRUD operations, while keeping the MAC-based `.json` endpoint for ESP32 device access.

### Conflicts Resolved

- **ESP32_CONFIGS_DIR removal**: The existing filesystem configuration and health check methods will be removed entirely since they are specific to file-based storage.
- **MAC validation regex**: Will be updated from dash-separated to colon-separated pattern.
- **Test fixtures**: Will transition from `config_dir` temp directory fixtures to database session fixtures.

---

## 1) Intent & Scope

**User intent**

Migrate device configuration storage from filesystem-based JSON files to PostgreSQL database storage. This involves copying the complete database infrastructure from the ElectronicsInventory backend and adapting it for this application, creating a new `Config` model with surrogate IDs, updating API endpoints to use ID-based URLs, and changing the MAC address format from dash-separated to colon-separated.

**Prompt quotes**

"Migrate device configuration storage from filesystem-based JSON files to PostgreSQL database storage"
"Copy the complete database infrastructure from the ElectronicsInventory backend"
"Create a Config model with surrogate ID (auto-increment primary key)"
"Change MAC address format from dash-separated to colon-separated everywhere"
"Keep GET /api/configs/<mac>.json endpoint for ESP32 device access (MAC lookup, kept)"

**In scope**

- Copy Flask-SQLAlchemy, Alembic, session management, BaseService, and test fixtures from ElectronicsInventory
- Create `Config` SQLAlchemy model with surrogate ID, MAC address, extracted fields, and JSON content
- Create Alembic migration for Config table
- Update ConfigService to use database instead of filesystem
- Update API endpoints to use surrogate IDs for CRUD operations
- Maintain MAC-based `.json` endpoint for ESP32 devices
- Update MAC address format to colon-separated throughout
- Maintain MQTT publishing on configuration changes
- Create test data JSON files for database loading
- Write comprehensive service and API tests

**Out of scope**

- Assets endpoint (`/api/assets`) - remains file-based as specified
- Data migration from existing files - assume clean installation
- ShutdownCoordinator - not needed for database implementation as specified

**Assumptions / constraints**

- PostgreSQL is the production database; SQLite is used for testing
- The frontend will be updated concurrently to handle the new API structure (BFF pattern, no backward compatibility needed)
- No existing data needs to be migrated - this is treated as a greenfield database implementation

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Copy Flask-SQLAlchemy setup and extensions from ElectronicsInventory/backend
- [ ] Copy Alembic migration framework configuration from ElectronicsInventory/backend
- [ ] Copy database session management with context-local sessions from ElectronicsInventory/backend
- [ ] Copy BaseService class pattern from ElectronicsInventory/backend
- [ ] Update ServiceContainer for dependency injection with database sessions
- [ ] Copy domain exceptions (RecordNotFoundException, InvalidOperationException, etc.)
- [ ] Copy database utility functions (init, upgrade, health checks)
- [ ] Copy test fixtures for database testing with SQLite
- [ ] Copy database scripts for creation, upgrade, and test data loading
- [ ] Create Config model with surrogate ID (auto-increment primary key)
- [ ] Config model has mac_address field (string, unique, not null, colon-separated format)
- [ ] Config model has nullable fields: device_name, device_entity_id, enable_ota
- [ ] Config model has content field (text, not null) for full JSON configuration
- [ ] Config model has created_at and updated_at timestamps
- [ ] Create Alembic migration for Config table
- [ ] Extract device_name, device_entity_id, enable_ota from JSON content on save
- [ ] MAC address is provided in request body, not extracted from content
- [ ] Change MAC address format from dash-separated to colon-separated everywhere
- [ ] Update GET /api/configs to return configs with IDs from database
- [ ] Create POST /api/configs endpoint to create new config
- [ ] Create GET /api/configs/<id> endpoint to get config by ID
- [ ] Create PUT /api/configs/<id> endpoint to update config by ID
- [ ] Create DELETE /api/configs/<id> endpoint to delete config by ID
- [ ] Keep GET /api/configs/<mac>.json endpoint for ESP32 device access (MAC lookup)
- [ ] Maintain MQTT publishing when configurations change
- [ ] Create sample test data JSON files for database loading
- [ ] Remove ESP32_CONFIGS_DIR environment variable and configuration
- [ ] Remove filesystem-based configuration storage from ConfigService
- [ ] Do not modify assets endpoint (remains file-based)
- [ ] Write comprehensive service tests for ConfigService
- [ ] Write comprehensive API tests for all config endpoints

---

## 2) Affected Areas & File Map

### New Files to Create

- Area: `app/extensions.py`
- Why: Flask-SQLAlchemy extension initialization, copied from ElectronicsInventory
- Evidence: `pvginkel/ElectronicsInventory.git:app/extensions.py:1-7` - defines `db = SQLAlchemy()`

- Area: `app/database.py`
- Why: Database utilities for connection checks, migrations, and upgrades
- Evidence: `pvginkel/ElectronicsInventory.git:app/database.py:1-261` - contains `init_db()`, `check_db_connection()`, `upgrade_database()`, `get_pending_migrations()`

- Area: `app/services/base.py`
- Why: BaseService class for services requiring database access
- Evidence: `pvginkel/ElectronicsInventory.git:app/services/base.py:1-16` - simple class with `__init__(self, db: Session)` storing session

- Area: `app/models/__init__.py`
- Why: Model module initialization to import all models for SQLAlchemy metadata registration
- Evidence: `pvginkel/ElectronicsInventory.git:app/models/__init__.py` - imports all model classes

- Area: `app/models/config.py`
- Why: New Config SQLAlchemy model with surrogate ID and all specified fields
- Evidence: Change brief specifies: id (auto-increment), mac_address (unique), device_name, device_entity_id, enable_ota, content, created_at, updated_at

- Area: `alembic/` directory
- Why: Alembic migration framework configuration
- Evidence: `pvginkel/ElectronicsInventory.git:alembic/env.py:1-103` - environment configuration for migrations

- Area: `alembic.ini`
- Why: Alembic configuration file
- Evidence: `pvginkel/ElectronicsInventory.git:alembic.ini:1-110` - contains script_location, sqlalchemy.url, logging config

- Area: `alembic/versions/001_create_config_table.py`
- Why: Initial migration to create configs table
- Evidence: Change brief requires Alembic migration for Config table

- Area: `app/cli.py`
- Why: CLI commands for database operations (upgrade-db, load-test-data)
- Evidence: `pvginkel/ElectronicsInventory.git:app/cli.py:1-355` - CLI entry point with subcommands

- Area: `app/data/test_data/configs.json`
- Why: Sample test data for database loading
- Evidence: Change brief: "Create sample test data JSON files for database loading"

- Area: `app/services/test_data_service.py`
- Why: Service for loading test data from JSON files
- Evidence: `pvginkel/ElectronicsInventory.git:app/services/test_data_service.py:1-924` - loads data in dependency order

- Area: `scripts/initialize-sqlite-database.sh`
- Why: Script for initializing SQLite database with optional test data
- Evidence: `pvginkel/ElectronicsInventory.git:scripts/initialize-sqlite-database.sh:1-70`

### Files to Modify

- Area: `app/__init__.py`
- Why: Add Flask-SQLAlchemy initialization, session management, and teardown handling
- Evidence: `/work/backend/app/__init__.py:16-70` - currently lacks database initialization

- Area: `app/config.py`
- Why: Add DATABASE_URL setting, remove ESP32_CONFIGS_DIR
- Evidence: `/work/backend/app/config.py:28-31` - currently has `ESP32_CONFIGS_DIR: Path`

- Area: `app/services/container.py`
- Why: Add session_maker dependency, db_session ContextLocalSingleton provider, update ConfigService to use db
- Evidence: `/work/backend/app/services/container.py:41-44` - currently `config_service` uses `config_dir`

- Area: `app/services/config_service.py`
- Why: Complete rewrite to use database instead of filesystem
- Evidence: `/work/backend/app/services/config_service.py:1-295` - currently file-based implementation

- Area: `app/schemas/config.py`
- Why: Update schemas for new API structure with surrogate IDs, MAC in request body
- Evidence: `/work/backend/app/schemas/config.py:1-57` - needs new schemas for POST create, ID-based operations

- Area: `app/api/configs.py`
- Why: Update endpoints for ID-based CRUD, add POST create endpoint, keep MAC-based .json endpoint
- Evidence: `/work/backend/app/api/configs.py:1-222` - current MAC-based URL structure

- Area: `app/api/health.py`
- Why: Replace filesystem health check with database health check
- Evidence: Health endpoint should verify database connectivity using `check_db_connection()` from `app/database.py`. Remove `is_config_dir_accessible()` check entirely since configs are now in database.

- Area: `app/exceptions.py`
- Why: Review existing `RecordExistsException` for 409 handling on duplicate MAC address
- Evidence: `/work/backend/app/exceptions.py:25-30` - `RecordExistsException` with `RECORD_EXISTS` error code will be used for duplicate MAC conflicts

- Area: `tests/conftest.py`
- Why: Add database session fixtures, template database pattern for SQLite testing
- Evidence: `/work/backend/tests/conftest.py:1-252` - currently filesystem-based fixtures

- Area: `tests/services/test_config_service.py`
- Why: Rewrite tests for database-backed ConfigService
- Evidence: `/work/backend/tests/services/test_config_service.py:1-430` - currently tests file operations

- Area: `tests/api/test_configs.py`
- Why: Update tests for new API structure with surrogate IDs
- Evidence: `/work/backend/tests/api/test_configs.py:1-459` - currently tests MAC-based URLs

- Area: `pyproject.toml`
- Why: Add dependencies (Flask-SQLAlchemy, alembic, psycopg) and CLI entry point
- Evidence: Need to add database dependencies and `iotsupport-cli` entry point

---

## 3) Data Model / Contracts

### Config Table

- Entity / contract: `configs` database table
- Shape:
  ```
  CREATE TABLE configs (
      id SERIAL PRIMARY KEY,
      mac_address VARCHAR(17) NOT NULL UNIQUE,  -- colon-separated: aa:bb:cc:dd:ee:ff
      device_name VARCHAR(255),
      device_entity_id VARCHAR(255),
      enable_ota BOOLEAN,
      content TEXT NOT NULL,  -- JSON string
      created_at TIMESTAMP NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMP NOT NULL DEFAULT NOW()
  );
  CREATE INDEX ix_configs_mac_address ON configs(mac_address);
  ```
- Refactor strategy: Complete replacement of file-based storage; no backward compatibility needed per BFF pattern
- Evidence: Change brief section "Data Model" specifies all fields

**Note on `updated_at`:** PostgreSQL does not support `ON UPDATE CURRENT_TIMESTAMP`. The SQLAlchemy model must use `onupdate=func.now()` in the column definition, or the `update_config()` method must explicitly set `config.updated_at = datetime.utcnow()` before flush.

### ConfigCreateRequestSchema (NEW)

- Entity / contract: Request body for POST /api/configs
- Shape:
  ```json
  {
    "mac_address": "aa:bb:cc:dd:ee:ff",
    "content": { ... }
  }
  ```
- Refactor strategy: New schema for create operation; MAC address in body, not URL
- Evidence: Change brief: "MAC address is provided in request body, not extracted from content"

### ConfigUpdateRequestSchema (MODIFIED)

- Entity / contract: Request body for PUT /api/configs/<id>
- Shape:
  ```json
  {
    "content": { ... }
  }
  ```
- Refactor strategy: Remove `allow_overwrite` field (PUT to existing ID always updates); MAC address not changeable via update
- Evidence: Change brief: ID-based update endpoint

### ConfigResponseSchema (MODIFIED)

- Entity / contract: Response for config operations
- Shape:
  ```json
  {
    "id": 1,
    "mac_address": "aa:bb:cc:dd:ee:ff",
    "device_name": "Living Room Sensor",
    "device_entity_id": "sensor.living_room",
    "enable_ota": true,
    "content": { ... },
    "created_at": "2024-01-21T12:00:00Z",
    "updated_at": "2024-01-21T12:00:00Z"
  }
  ```
- Refactor strategy: Add `id`, `created_at`, `updated_at` fields
- Evidence: `/work/backend/app/schemas/config.py:47-57` - current schema lacks these fields

### ConfigSummarySchema (MODIFIED)

- Entity / contract: Summary for list endpoint
- Shape:
  ```json
  {
    "id": 1,
    "mac_address": "aa:bb:cc:dd:ee:ff",
    "device_name": "Living Room Sensor",
    "device_entity_id": "sensor.living_room",
    "enable_ota": true
  }
  ```
- Refactor strategy: Add `id` field for linking to detail endpoints
- Evidence: `/work/backend/app/schemas/config.py:8-16` - current schema lacks `id`

---

## 4) API / Integration Surface

### GET /api/configs (MODIFIED)

- Surface: `GET /api/configs`
- Inputs: None
- Outputs: `{ "configs": [...], "count": N }` with summaries including `id` field
- Errors: 500 on database error
- Evidence: `/work/backend/app/api/configs.py:28-67` - current implementation

### POST /api/configs (NEW)

- Surface: `POST /api/configs`
- Inputs: `{ "mac_address": "aa:bb:cc:dd:ee:ff", "content": {...} }`
- Outputs: Full config response with `id`, 201 status
- Errors: 400 for invalid MAC format or invalid JSON; 409 for duplicate MAC address
- Evidence: Change brief: "Create POST /api/configs endpoint to create new config"

### GET /api/configs/<id> (NEW)

- Surface: `GET /api/configs/<id>`
- Inputs: Integer ID path parameter
- Outputs: Full config response
- Errors: 404 if config not found
- Evidence: Change brief: "Create GET /api/configs/<id> endpoint to get config by ID"

### PUT /api/configs/<id> (NEW)

- Surface: `PUT /api/configs/<id>`
- Inputs: Integer ID path parameter; `{ "content": {...} }` body
- Outputs: Updated config response
- Errors: 404 if config not found; 400 for invalid JSON content
- Evidence: Change brief: "Create PUT /api/configs/<id> endpoint to update config by ID"

### DELETE /api/configs/<id> (NEW)

- Surface: `DELETE /api/configs/<id>`
- Inputs: Integer ID path parameter
- Outputs: 204 No Content
- Errors: 404 if config not found
- Evidence: Change brief: "Create DELETE /api/configs/<id> endpoint to delete config by ID"

### GET /api/configs/<mac>.json (KEPT, MODIFIED)

- Surface: `GET /api/configs/<mac>.json`
- Inputs: MAC address path parameter (colon-separated format)
- Outputs: Raw JSON content with Cache-Control: no-cache header
- Errors: 404 if config not found; 400 for invalid MAC format
- Evidence: `/work/backend/app/api/configs.py:70-100` - current implementation; change brief: "Keep GET /api/configs/<mac>.json endpoint for ESP32 device access"

### REMOVED Endpoints

- `GET /api/configs/<mac>` - replaced by `GET /api/configs/<id>`
- `PUT /api/configs/<mac>` - replaced by `POST /api/configs` and `PUT /api/configs/<id>`
- `DELETE /api/configs/<mac>` - replaced by `DELETE /api/configs/<id>`

---

## 5) Algorithms & State Machines

### Config Create Flow

- Flow: Creating a new device configuration
- Steps:
  1. Validate MAC address format (colon-separated, lowercase)
  2. Validate content is valid JSON
  3. Check for existing config with same MAC address
  4. If exists, raise RecordExistsException (maps to 409 Conflict)
  5. Extract optional fields from content: device_name, device_entity_id, enable_ota
  6. Create Config record with all fields
  7. Flush to database to get ID
  8. Publish MQTT notification with MAC address
  9. Return created config with ID
- States / transitions: None (single operation)
- Hotspots: MAC uniqueness check must happen before insert to provide clear error
- Evidence: Change brief: "Extract device_name, device_entity_id, enable_ota from JSON content on save"

### Config Update Flow

- Flow: Updating an existing configuration by ID
- Steps:
  1. Look up config by ID
  2. If not found, raise RecordNotFoundException
  3. Validate content is valid JSON
  4. Extract optional fields from content: device_name, device_entity_id, enable_ota
  5. Update config record fields
  6. Flush changes
  7. Publish MQTT notification with MAC address
  8. Return updated config
- States / transitions: None
- Hotspots: Content extraction must handle missing optional fields gracefully
- Evidence: `/work/backend/app/services/config_service.py:158-201` - current save logic

### ESP32 Config Lookup Flow

- Flow: ESP32 device requesting its configuration
- Steps:
  1. Normalize MAC address to lowercase
  2. Normalize MAC separator format (accept both dash and colon separators, convert to colon format for database lookup)
  3. Validate MAC address format after normalization
  4. Query config by mac_address
  5. If not found, raise RecordNotFoundException
  6. Parse content JSON string
  7. Return raw JSON dict
- States / transitions: None
- Hotspots: Must be fast for device boot; consider adding index on mac_address (already unique)
- Evidence: `/work/backend/app/api/configs.py:70-100` - current raw endpoint

**Note:** The `.json` endpoint accepts both dash-separated (`aa-bb-cc-dd-ee-ff`) and colon-separated (`aa:bb:cc:dd:ee:ff`) MAC formats for backward compatibility with existing ESP32 devices. Input is normalized to colon format before database lookup.

### Health Check Flow

- Flow: Kubernetes liveness/readiness probe checking application health
- Steps:
  1. Call `check_db_connection()` with Flask-SQLAlchemy engine
  2. If database connection succeeds, return 200 with `{"status": "healthy", "database": "connected"}`
  3. If database connection fails, return 503 with `{"status": "unhealthy", "database": "disconnected", "error": "<message>"}`
- States / transitions: None
- Hotspots: Should be fast; use simple connection check, not complex query
- Evidence: `pvginkel/ElectronicsInventory.git:app/database.py:42-49` - `check_db_connection()` implementation

---

## 6) Derived State & Invariants

- Derived value: `device_name`
  - Source: Extracted from `content` JSON field `deviceName` on every save
  - Writes / cleanup: Updated in database whenever content is saved
  - Guards: Optional field - stored as NULL if not present in content
  - Invariant: Always reflects current content state (denormalized for query efficiency)
  - Evidence: `/work/backend/app/services/config_service.py:84-88` - current extraction

- Derived value: `device_entity_id`
  - Source: Extracted from `content` JSON field `deviceEntityId` on every save
  - Writes / cleanup: Updated in database whenever content is saved
  - Guards: Optional field - stored as NULL if not present in content
  - Invariant: Always reflects current content state (denormalized for query efficiency)
  - Evidence: `/work/backend/app/services/config_service.py:84-88` - current extraction

- Derived value: `enable_ota`
  - Source: Extracted from `content` JSON field `enableOTA` on every save
  - Writes / cleanup: Updated in database whenever content is saved
  - Guards: Optional field - stored as NULL if not present in content
  - Invariant: Always reflects current content state (denormalized for query efficiency)
  - Evidence: `/work/backend/app/services/config_service.py:84-88` - current extraction

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: Each API request operates within a single database transaction managed by Flask teardown handler
- Atomic requirements: Config create/update with MQTT notification should be atomic at DB level; MQTT failure should not roll back DB (best-effort notification)
- Retry / idempotency: POST create is not idempotent (duplicate MAC returns 409); PUT update is idempotent
- Ordering / concurrency controls: MAC address unique constraint prevents duplicate creation; `updated_at` timestamp tracks last modification but no optimistic locking required for this simple use case
- Evidence: `pvginkel/ElectronicsInventory.git:app/__init__.py:200-218` - teardown handler pattern with commit/rollback

**Important:** ConfigService methods must NOT call `db.commit()` directly - transaction boundaries are managed by Flask request teardown. Use `db.flush()` only when immediate ID assignment is needed (e.g., after create to return the new config with its ID). ConfigService remains a Factory provider with `db=db_session` injection, matching the ElectronicsInventory pattern for database services.

---

## 8) Errors & Edge Cases

- Failure: Duplicate MAC address on create
- Surface: POST /api/configs
- Handling: 409 Conflict with `RECORD_EXISTS` error code (using existing `RecordExistsException`)
- Guardrails: Database unique constraint on mac_address; service checks before insert for clear error message
- Evidence: Change brief implies POST creates new config; duplicate should fail; `/work/backend/app/exceptions.py:25-30`

- Failure: Invalid MAC address format
- Surface: POST /api/configs, GET /api/configs/<mac>.json
- Handling: 400 Bad Request with `INVALID_OPERATION` error code
- Guardrails: Regex validation for colon-separated format `^[0-9a-f]{2}(:[0-9a-f]{2}){5}$`
- Evidence: `/work/backend/app/services/config_service.py:20` - current dash-separated pattern

- Failure: Config not found by ID
- Surface: GET/PUT/DELETE /api/configs/<id>
- Handling: 404 Not Found with `RECORD_NOT_FOUND` error code
- Guardrails: Service raises RecordNotFoundException when query returns None
- Evidence: `/work/backend/app/services/config_service.py:126-127` - current pattern

- Failure: Config not found by MAC
- Surface: GET /api/configs/<mac>.json
- Handling: 404 Not Found with `RECORD_NOT_FOUND` error code
- Guardrails: Service raises RecordNotFoundException when query returns None
- Evidence: `/work/backend/app/services/config_service.py:126-127` - current pattern

- Failure: Invalid JSON content in request
- Surface: POST /api/configs, PUT /api/configs/<id>
- Handling: 400 Bad Request via Pydantic validation
- Guardrails: Pydantic schema validates content is dict type
- Evidence: `/work/backend/app/schemas/config.py:40` - `content: dict[str, Any]`

- Failure: Database connection failure
- Surface: All config endpoints
- Handling: 500 Internal Server Error
- Guardrails: Health endpoint checks database connectivity
- Evidence: `pvginkel/ElectronicsInventory.git:app/database.py:42-49` - `check_db_connection()`

---

## 9) Observability / Telemetry

- Signal: `config_operation_duration_seconds`
- Type: histogram
- Trigger: Every config API operation (list, get, get_raw, create, update, delete)
- Labels / fields: `operation`, `status` (success/error)
- Consumer: Existing Prometheus metrics infrastructure
- Evidence: `/work/backend/app/api/configs.py:67` - `metrics_service.record_operation("list", status, duration)`

- Signal: `config_count`
- Type: gauge
- Trigger: After create/delete operations update the count
- Labels / fields: None
- Consumer: Existing Prometheus metrics infrastructure
- Evidence: `/work/backend/app/api/configs.py:44` - `metrics_service.update_config_count(len(configs))`

- Signal: Database health status
- Type: Boolean health check
- Trigger: Health endpoint calls
- Labels / fields: None
- Consumer: Kubernetes liveness/readiness probes
- Evidence: `pvginkel/ElectronicsInventory.git:app/database.py:42-49` - `check_db_connection()`

---

## 10) Background Work & Shutdown

No background workers are introduced by this change. Database connections are managed per-request with session cleanup in Flask teardown.

- Worker / job: None
- Trigger cadence: N/A
- Responsibilities: N/A
- Shutdown handling: Flask teardown handler commits/rollbacks and closes session; connection pool handles cleanup
- Evidence: `pvginkel/ElectronicsInventory.git:app/__init__.py:200-218` - teardown pattern

---

## 11) Security & Permissions

No changes to security model. The application operates in a trusted homelab environment with no authentication requirement as specified in the product brief.

---

## 12) UX / UI Impact

This change requires frontend updates to use the new API structure:

- Entry point: Configuration management UI
- Change: API calls must use surrogate IDs for CRUD operations; MAC address moved to request body for create
- User interaction: No visible UX change expected - same functionality, different API structure
- Dependencies: Frontend must be updated to:
  - Use POST /api/configs with MAC in body for create
  - Use GET/PUT/DELETE /api/configs/<id> for read/update/delete
  - Handle new `id` field in responses
- Evidence: `/work/backend/CLAUDE.md` - BFF pattern, frontend updated concurrently

**Frontend Impact Note**: Create `docs/features/database_config_storage/frontend_impact.md` documenting the API changes for the frontend developer.

---

## 13) Deterministic Test Plan

### ConfigService Tests

- Surface: ConfigService
- Scenarios:
  - Given empty database, When list_configs called, Then returns empty list
  - Given configs exist, When list_configs called, Then returns all configs sorted by MAC
  - Given config exists, When get_config_by_id called with valid ID, Then returns config
  - Given no config exists, When get_config_by_id called, Then raises RecordNotFoundException
  - Given empty database, When create_config called with valid data, Then creates config and returns with ID
  - Given config exists with MAC, When create_config called with same MAC, Then raises RecordExistsException
  - Given invalid MAC format, When create_config called, Then raises InvalidOperationException
  - Given config exists, When update_config called with valid data, Then updates and returns config
  - Given no config exists, When update_config called, Then raises RecordNotFoundException
  - Given config exists, When delete_config called, Then deletes config
  - Given no config exists, When delete_config called, Then raises RecordNotFoundException
  - Given config exists, When get_config_by_mac called with valid MAC, Then returns config content
  - Given no config with MAC, When get_config_by_mac called, Then raises RecordNotFoundException
  - Given content has deviceName, When create/update called, Then device_name field extracted
  - Given content lacks deviceName, When create/update called, Then device_name is NULL
- Fixtures / hooks: `session` fixture providing database session, `container` fixture providing service container
- Gaps: None
- Evidence: `/work/backend/tests/services/test_config_service.py` - existing test structure

### Config API Tests

- Surface: Config API endpoints
- Scenarios:
  - Given empty database, When GET /api/configs, Then returns 200 with empty list
  - Given configs exist, When GET /api/configs, Then returns 200 with summaries including IDs
  - Given valid request, When POST /api/configs, Then returns 201 with created config
  - Given duplicate MAC, When POST /api/configs, Then returns 409
  - Given invalid MAC format, When POST /api/configs, Then returns 400
  - Given config exists, When GET /api/configs/<id>, Then returns 200 with full config
  - Given no config, When GET /api/configs/<id>, Then returns 404
  - Given config exists, When PUT /api/configs/<id>, Then returns 200 with updated config
  - Given no config, When PUT /api/configs/<id>, Then returns 404
  - Given config exists, When DELETE /api/configs/<id>, Then returns 204
  - Given no config, When DELETE /api/configs/<id>, Then returns 404
  - Given config exists, When GET /api/configs/<mac>.json, Then returns 200 with raw JSON
  - Given no config, When GET /api/configs/<mac>.json, Then returns 404
  - Given uppercase MAC, When GET /api/configs/<MAC>.json, Then normalizes and returns config
  - Given dash-separated MAC, When GET /api/configs/aa-bb-cc-dd-ee-ff.json, Then normalizes to colon format and returns config (backward compatibility)
  - Given successful create, Then MQTT notification published
  - Given successful update, Then MQTT notification published
  - Given delete, Then no MQTT notification published
- Fixtures / hooks: `client` fixture, `session` fixture, `container` fixture
- Gaps: None
- Evidence: `/work/backend/tests/api/test_configs.py` - existing test structure

---

## 14) Implementation Slices

- Slice: Database Infrastructure
- Goal: Copy and adapt database foundations from ElectronicsInventory
- Touches: `app/extensions.py`, `app/database.py`, `app/services/base.py`, `alembic/`, `alembic.ini`, `app/config.py` (add DATABASE_URL), `pyproject.toml`
- Dependencies: None; foundation for all subsequent slices

- Slice: Config Model and Migration
- Goal: Create Config SQLAlchemy model and Alembic migration
- Touches: `app/models/__init__.py`, `app/models/config.py`, `alembic/versions/001_create_config_table.py`
- Dependencies: Database Infrastructure slice complete

- Slice: Service Container and Session Management
- Goal: Update container for database session injection
- Touches: `app/services/container.py`, `app/__init__.py`
- Dependencies: Database Infrastructure slice complete

- Slice: ConfigService Rewrite
- Goal: Rewrite ConfigService to use database
- Touches: `app/services/config_service.py`
- Dependencies: Config Model, Service Container slices complete

- Slice: Schema Updates
- Goal: Update Pydantic schemas for new API structure
- Touches: `app/schemas/config.py`
- Dependencies: None; can be done in parallel with service work

- Slice: API Updates
- Goal: Update config endpoints for ID-based operations
- Touches: `app/api/configs.py`, `app/api/health.py`
- Dependencies: ConfigService, Schema slices complete

- Slice: Configuration Cleanup
- Goal: Remove ESP32_CONFIGS_DIR configuration setting
- Touches: `app/config.py`
- Dependencies: ConfigService rewrite complete (no longer uses config_dir)
- Note: No exception changes needed - existing `RecordExistsException` will be used for duplicate MAC conflicts

- Slice: Test Infrastructure
- Goal: Add database test fixtures
- Touches: `tests/conftest.py`
- Dependencies: Database Infrastructure slice complete

- Slice: Service Tests
- Goal: Rewrite ConfigService tests
- Touches: `tests/services/test_config_service.py`
- Dependencies: ConfigService, Test Infrastructure slices complete

- Slice: API Tests
- Goal: Update API tests for new structure
- Touches: `tests/api/test_configs.py`
- Dependencies: API Updates, Test Infrastructure slices complete

- Slice: CLI and Test Data
- Goal: Add CLI commands and test data loading
- Touches: `app/cli.py`, `app/services/test_data_service.py`, `app/data/test_data/configs.json`, `scripts/`
- Dependencies: Config Model slice complete

---

## 15) Risks & Open Questions

### Risks

- Risk: SQLite test compatibility with PostgreSQL production
- Impact: Tests may pass but production fails due to dialect differences
- Mitigation: Use standard SQL features; avoid PostgreSQL-specific syntax in model/queries

- Risk: MAC address format change breaks existing ESP32 devices
- Impact: Devices using dash-separated format in their requests would fail
- Mitigation: Document format change clearly; consider normalization to accept both formats in `.json` endpoint

- Risk: Missing test data causes incomplete test coverage
- Impact: Edge cases not tested could have bugs in production
- Mitigation: Create comprehensive test data JSON file covering all field combinations

### Open Questions

All questions resolved:

1. **MAC format acceptance in .json endpoint**: Will normalize input MAC (accept both colon and dash separators, convert to colon format internally) to maintain backward compatibility with existing ESP32 devices.

2. **Content validation depth**: Will validate content is valid JSON dict but not enforce schema - maintaining current flexibility per product brief.

3. **Timestamp timezone handling**: Will use UTC timestamps with server defaults for consistency. SQLAlchemy model will use `onupdate=func.now()` for automatic `updated_at` updates.

4. **Exception for duplicate MAC conflicts**: Will use existing `RecordExistsException` (error code `RECORD_EXISTS`) which maps to 409 status in the error handler. No new exception needed.

5. **ConfigService provider pattern**: ConfigService remains a Factory provider with `db=db_session` injection, following the established pattern from ElectronicsInventory for database-backed services.

6. **Transaction management**: ConfigService methods do NOT call `db.commit()` - Flask teardown handler manages transaction boundaries. Service uses `db.flush()` only for immediate ID assignment after create operations.

---

## 16) Confidence

Confidence: High - The implementation follows established patterns from ElectronicsInventory with clear requirements and no blocking ambiguities. The BFF pattern eliminates backward compatibility concerns.
