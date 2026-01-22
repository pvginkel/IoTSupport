# Device Provisioning MDM - Technical Plan

## 0) Research Log & Findings

### Areas Researched

**Service Layer Patterns**: Examined `app/services/config_service.py`, `app/services/auth_service.py`, `app/services/mqtt_service.py`, and `app/services/asset_upload_service.py`. Services are either Factory-based (using `BaseService` with injected `db: Session`) or Singleton-based (for stateful services like MQTT, Auth). Factory services receive database sessions via constructor injection and use `self.db` for queries.

**API Layer Patterns**: Examined `app/api/configs.py`, `app/api/__init__.py`. Endpoints use Flask blueprints, SpectTree for OpenAPI validation, `@handle_api_errors` decorator, and `@inject` with `Provide[ServiceContainer.service_name]` for dependency injection. Authentication is handled in `before_request` hook at blueprint level.

**Model Patterns**: Examined `app/models/config.py`. Models use SQLAlchemy 2.0 style with `Mapped[Type]` annotations, `mapped_column()`, timestamps via `server_default=func.now()`. Tables use surrogate integer primary keys with auto-increment.

**Migration Patterns**: Examined `alembic/versions/001_create_config_table.py`. Migrations follow sequential numbering (001, 002, etc.) with descriptive names, use `op.create_table()` / `op.create_index()` pattern.

**Authentication Patterns**: Examined `app/services/auth_service.py`, `app/utils/auth.py`. JWT validation uses PyJWKClient with JWKS caching. `AuthContext` dataclass holds subject, email, name, roles. The `@public` decorator marks endpoints that skip authentication.

**MQTT Patterns**: Examined `app/services/mqtt_service.py`. Singleton service with paho-mqtt v5, fire-and-forget publishing with QoS 1, Prometheus metrics for publish operations.

**Testing Patterns**: Examined `tests/conftest.py`, `tests/services/test_config_service.py`, `tests/api/test_configs.py`. Uses pytest fixtures with SQLite in-memory database, `container` fixture for DI access, `make_config` factory fixture for test data setup.

**Container Patterns**: Examined `app/services/container.py`. Uses `dependency-injector` with `providers.Factory` for per-request services and `providers.Singleton` for persistent services.

### Key Findings

1. **No existing background job scheduler**: The codebase has no scheduler/cron framework. Will need to introduce one (APScheduler recommended for Flask compatibility).

2. **Keycloak Admin API not yet implemented**: The existing `OidcClientService` handles user authentication flows but not admin operations. A new `KeycloakAdminService` is needed.

3. **File storage pattern established**: `AssetUploadService` demonstrates atomic file writes with temp files and `os.replace()`.

4. **Device key pattern needs design**: Current system uses MAC addresses. New 8-character device keys require a secure generation algorithm.

5. **Rotation state machine is complex**: Requires careful transaction management and timeout handling.

---

## 1) Intent & Scope

**User intent**

Transform the IoT Support backend from a simple config file manager into a full MDM application with device provisioning, Keycloak-based device identity, and automated secret rotation.

**Prompt quotes**

- "Replace MAC address with device key"
- "Each device is registered as a Keycloak client"
- "Rotation states: OK, QUEUED, PENDING, TIMEOUT"
- "Hourly job... processes PENDING timeouts, rotates one device at a time"
- "Remove /api/configs endpoints entirely (no backwards compatibility)"

**In scope**

- New `DeviceModel` and `Device` SQLAlchemy models with relationships
- Keycloak admin API integration for client lifecycle management
- Device provisioning flow with secure key generation
- Automated secret rotation with state machine and timeout handling
- New `/api/device-models`, `/api/devices`, `/api/rotation` admin endpoints
- New `/iot` blueprint for device-authenticated endpoints
- Firmware upload/download with ESP32 AppInfo version extraction
- MQTT rotation notifications
- Prometheus metrics for rotation timing
- Complete removal of MAC-based config system

**Out of scope**

- Bluetooth provisioning
- Multiple firmware versions per model (rollback)
- Automatic device expiration/revocation
- Frontend implementation (backend APIs only)

**Assumptions / constraints**

- Keycloak is pre-configured with a realm and service account (`iotsupport-admin`) with `manage-clients` permission
- ESP32 devices will be updated to use new provisioning format
- Firmware binaries follow ESP-IDF AppInfo structure at documented offsets
- WiFi credentials are static across all devices (environment-configured)
- CRON schedule syntax follows standard format (5 fields)

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Remove all MAC address usage, replace with 8-character device key (`[a-z0-9]`)
- [ ] Create DeviceModel entity with: id, code (unique, immutable, `[a-z0-9_]+`), name, firmware_version, timestamps
- [ ] Create Device entity with: id, key, device_model_id (FK, required), config (JSON, required), rotation_state, secret_created_at, last_rotation_attempt_at, last_rotation_completed_at, timestamps
- [ ] Store firmware on filesystem as `firmware-<model_code>.bin`
- [ ] Extract firmware version using ESP32 AppInfo (offset 32, magic 0xABCD5432, version at offset 16 in structure)
- [ ] Integrate Keycloak admin API via service account for client management (create, regenerate secret, delete)
- [ ] Create Keycloak clients with ID format `iotdevice-<model_code>-<device_key>`
- [ ] Generate provisioning package as JSON .bin file with: device key, client ID, client secret, token URL, base URL, MQTT URL, WiFi credentials
- [ ] Implement `/api/device-models` CRUD endpoints with numeric IDs
- [ ] Implement `/api/device-models/<id>/firmware` upload/download endpoints
- [ ] Implement `/api/devices` CRUD endpoints with numeric IDs
- [ ] Implement `GET /api/devices/<id>/provisioning` to download provisioning package
- [ ] Implement `POST /api/devices/<id>/rotate` for manual single-device rotation
- [ ] Implement `GET /api/rotation/status` for fleet-wide stats
- [ ] Implement `POST /api/rotation/trigger` for manual fleet-wide rotation
- [ ] Implement `/iot` blueprint with device JWT authentication (extract key from client ID)
- [ ] Implement `GET /iot/config` returning raw JSON config
- [ ] Implement `GET /iot/firmware` returning raw firmware binary
- [ ] Implement `GET /iot/provisioning` for rotation (generates new secret, returns provisioning JSON)
- [ ] Implement rotation states: OK, QUEUED, PENDING, TIMEOUT
- [ ] Implement hourly rotation job that: checks CRON schedule, processes PENDING timeouts, rotates one device at a time
- [ ] Cache old secret before rotation, restore on timeout (5 min default)
- [ ] Publish MQTT to `iotsupport/<client_id>/rotation` (fire-and-forget, no retention)
- [ ] Track rotation metrics: MQTT->provisioning time, provisioning->config time
- [ ] Add environment variables: OIDC_TOKEN_URL, KEYCLOAK_ADMIN_URL, KEYCLOAK_REALM, KEYCLOAK_ADMIN_CLIENT_ID, KEYCLOAK_ADMIN_CLIENT_SECRET, WIFI_SSID, WIFI_PASSWORD, ROTATION_CRON, ROTATION_TIMEOUT_SECONDS, ROTATION_RETRY_INTERVAL_SECONDS
- [ ] Remove `/api/configs` endpoints entirely (no backwards compatibility)
- [ ] Write `docs/features/device_provisioning_mdm/frontend_impact.md` documenting frontend changes needed

---

## 2) Affected Areas & File Map

### New Files to Create

- Area: `app/models/device_model.py`
- Why: New DeviceModel entity for hardware types
- Evidence: Pattern from `app/models/config.py:11-48` - SQLAlchemy model structure

- Area: `app/models/device.py`
- Why: New Device entity with rotation state tracking
- Evidence: Pattern from `app/models/config.py:11-48` - SQLAlchemy model structure

- Area: `app/schemas/device_model.py`
- Why: Pydantic schemas for DeviceModel CRUD
- Evidence: Pattern from `app/schemas/config.py:10-85` - schema naming conventions

- Area: `app/schemas/device.py`
- Why: Pydantic schemas for Device CRUD and provisioning
- Evidence: Pattern from `app/schemas/config.py:10-85` - schema naming conventions

- Area: `app/schemas/rotation.py`
- Why: Pydantic schemas for rotation status and triggers
- Evidence: Pattern from `app/schemas/config.py:10-85` - schema naming conventions

- Area: `app/services/device_model_service.py`
- Why: Business logic for device model CRUD and firmware management
- Evidence: Pattern from `app/services/config_service.py:24-265` - Factory service pattern

- Area: `app/services/device_service.py`
- Why: Business logic for device CRUD, provisioning, and key generation
- Evidence: Pattern from `app/services/config_service.py:24-265` - Factory service pattern

- Area: `app/services/keycloak_admin_service.py`
- Why: Keycloak admin API integration for client lifecycle
- Evidence: Pattern from `app/services/auth_service.py:29-297` - Singleton service with HTTP client

- Area: `app/services/rotation_service.py`
- Why: Rotation state machine and background job logic
- Evidence: Pattern from `app/services/mqtt_service.py:18-319` - Singleton with background operations

- Area: `app/services/firmware_service.py`
- Why: Firmware file management and version extraction
- Evidence: Pattern from `app/services/asset_upload_service.py:20-263` - File I/O service

- Area: `app/api/device_models.py`
- Why: REST endpoints for DeviceModel management
- Evidence: Pattern from `app/api/configs.py:1-243` - Blueprint structure

- Area: `app/api/devices.py`
- Why: REST endpoints for Device management
- Evidence: Pattern from `app/api/configs.py:1-243` - Blueprint structure

- Area: `app/api/rotation.py`
- Why: REST endpoints for rotation management
- Evidence: Pattern from `app/api/configs.py:1-243` - Blueprint structure

- Area: `app/api/iot.py`
- Why: Device-authenticated endpoints for config/firmware/provisioning
- Evidence: Pattern from `app/api/configs.py:109-141` - Raw endpoint pattern

- Area: `app/utils/device_auth.py`
- Why: Device JWT authentication utilities (extract key from client ID)
- Evidence: Pattern from `app/utils/auth.py:24-274` - Auth utilities

- Area: `alembic/versions/002_device_provisioning.py`
- Why: Create device_models and devices tables, drop configs table
- Evidence: Pattern from `alembic/versions/001_create_config_table.py:1-52`

- Area: `tests/services/test_device_model_service.py`
- Why: Unit tests for device model service
- Evidence: Pattern from `tests/services/test_config_service.py:1-391`

- Area: `tests/services/test_device_service.py`
- Why: Unit tests for device service
- Evidence: Pattern from `tests/services/test_config_service.py:1-391`

- Area: `tests/services/test_keycloak_admin_service.py`
- Why: Unit tests for Keycloak admin integration
- Evidence: Pattern from `tests/services/test_auth_service.py`

- Area: `tests/services/test_rotation_service.py`
- Why: Unit tests for rotation state machine
- Evidence: Pattern from `tests/services/test_config_service.py:1-391`

- Area: `tests/services/test_firmware_service.py`
- Why: Unit tests for firmware parsing
- Evidence: Pattern from `tests/services/test_asset_upload_service.py`

- Area: `tests/api/test_device_models.py`
- Why: API tests for device model endpoints
- Evidence: Pattern from `tests/api/test_configs.py:1-702`

- Area: `tests/api/test_devices.py`
- Why: API tests for device endpoints
- Evidence: Pattern from `tests/api/test_configs.py:1-702`

- Area: `tests/api/test_rotation.py`
- Why: API tests for rotation endpoints
- Evidence: Pattern from `tests/api/test_configs.py:1-702`

- Area: `tests/api/test_iot.py`
- Why: API tests for device-authenticated endpoints
- Evidence: Pattern from `tests/api/test_configs.py:402-498`

- Area: `docs/features/device_provisioning_mdm/frontend_impact.md`
- Why: Document frontend changes required
- Evidence: User requirement

### Files to Modify

- Area: `app/config.py`
- Why: Add new environment variables for Keycloak admin, WiFi, rotation settings
- Evidence: `app/config.py:14-165` - Settings class

- Area: `app/services/container.py`
- Why: Register new services in DI container
- Evidence: `app/services/container.py:1-83` - ServiceContainer

- Area: `app/__init__.py`
- Why: Wire new API modules, register new blueprints
- Evidence: `app/__init__.py:56-104` - blueprint registration

- Area: `app/api/__init__.py`
- Why: Register new API blueprints, update before_request for IoT auth
- Evidence: `app/api/__init__.py:90-104` - blueprint imports

- Area: `app/models/__init__.py`
- Why: Export new model classes
- Evidence: `app/models/__init__.py` - model exports

- Area: `app/services/metrics_service.py`
- Why: Add rotation metrics (timing, state counts)
- Evidence: `app/services/metrics_service.py:18-272` - metric definitions

- Area: `app/services/mqtt_service.py`
- Why: Add rotation topic publishing method
- Evidence: `app/services/mqtt_service.py:227-251` - topic publishing

- Area: `tests/conftest.py`
- Why: Add fixtures for device models, devices, firmware files
- Evidence: `tests/conftest.py:186-268` - test fixtures

### Files to Remove

- Area: `app/api/configs.py`
- Why: Remove entire MAC-based config API
- Evidence: User requirement "Remove /api/configs endpoints entirely"

- Area: `app/services/config_service.py`
- Why: Remove MAC-based config service
- Evidence: User requirement "Remove all MAC address usage"

- Area: `app/models/config.py`
- Why: Remove Config model (replaced by Device)
- Evidence: User requirement "Remove all MAC address usage"

- Area: `app/schemas/config.py`
- Why: Remove config schemas
- Evidence: User requirement "Remove /api/configs endpoints entirely"

- Area: `tests/services/test_config_service.py`
- Why: Remove tests for deleted service
- Evidence: Service being removed

- Area: `tests/api/test_configs.py`
- Why: Remove tests for deleted endpoints
- Evidence: Endpoints being removed

---

## 3) Data Model / Contracts

- Entity / contract: `DeviceModel` (SQLAlchemy model)
- Shape:
  ```
  id: int (PK, auto-increment)
  code: str (unique, immutable, max 50, pattern [a-z0-9_]+)
  name: str (max 255)
  firmware_version: str | None (max 50, extracted from binary)
  created_at: datetime
  updated_at: datetime

  Relationships:
  - devices: list[Device] (one-to-many, cascade delete)
  ```
- Refactor strategy: New entity, no migration of existing data
- Evidence: Pattern from `app/models/config.py:11-48`

- Entity / contract: `Device` (SQLAlchemy model)
- Shape:
  ```
  id: int (PK, auto-increment)
  key: str (unique, 8 chars, pattern [a-z0-9])
  device_model_id: int (FK to device_models.id, NOT NULL)
  config: Text (JSON string, NOT NULL)
  rotation_state: str (enum: OK, QUEUED, PENDING, TIMEOUT, default OK)
  cached_secret: str | None (max 255, for timeout recovery)
  secret_created_at: datetime | None
  last_rotation_attempt_at: datetime | None
  last_rotation_completed_at: datetime | None
  created_at: datetime
  updated_at: datetime

  Relationships:
  - device_model: DeviceModel (many-to-one)
  ```
- Refactor strategy: New entity, no migration from Config (clean break)
- Evidence: Pattern from `app/models/config.py:11-48`

- Entity / contract: `RotationState` (Python Enum)
- Shape:
  ```python
  class RotationState(str, Enum):
      OK = "OK"
      QUEUED = "QUEUED"
      PENDING = "PENDING"
      TIMEOUT = "TIMEOUT"
  ```
- Refactor strategy: Store as string column (CLAUDE.md prohibits native ENUM)
- Evidence: `CLAUDE.md` "Do not create PostgreSQL native ENUM types"

- Entity / contract: `ProvisioningPackage` (Pydantic schema / JSON output)
- Shape:
  ```json
  {
    "device_key": "a1b2c3d4",
    "client_id": "iotdevice-thermostat-a1b2c3d4",
    "client_secret": "generated-secret",
    "token_url": "https://auth.example.com/realms/iot/protocol/openid-connect/token",
    "base_url": "https://iot.example.com",
    "mqtt_url": "mqtts://mqtt.example.com:8883",
    "wifi_ssid": "HomeNetwork",
    "wifi_password": "secret123"
  }
  ```
- Refactor strategy: New contract, devices download as `.bin` file
- Evidence: Change brief "Provisioning Package Contents"

- Entity / contract: Firmware file storage
- Shape: Files stored at `{ASSETS_DIR}/firmware-{model_code}.bin`
- Refactor strategy: Reuse existing ASSETS_DIR path
- Evidence: `app/services/asset_upload_service.py:198` - file storage pattern

---

## 4) API / Integration Surface

### Device Models API

- Surface: `GET /api/device-models`
- Inputs: None
- Outputs: `{ "device_models": [...], "count": int }`
- Errors: 500 on database error
- Evidence: Pattern from `app/api/configs.py:29-64`

- Surface: `POST /api/device-models`
- Inputs: `{ "code": str, "name": str }`
- Outputs: `{ "id": int, "code": str, "name": str, ... }` (201)
- Errors: 400 invalid code format, 409 code exists
- Evidence: Pattern from `app/api/configs.py:66-107`

- Surface: `GET /api/device-models/<int:id>`
- Inputs: Path parameter `id`
- Outputs: DeviceModel with devices count
- Errors: 404 not found
- Evidence: Pattern from `app/api/configs.py:143-170`

- Surface: `PUT /api/device-models/<int:id>`
- Inputs: `{ "name": str }`
- Outputs: Updated DeviceModel
- Errors: 404 not found, 400 validation
- Evidence: Pattern from `app/api/configs.py:172-210`

- Surface: `DELETE /api/device-models/<int:id>`
- Inputs: Path parameter `id`
- Outputs: 204 No Content
- Errors: 404 not found, 409 has devices
- Evidence: Pattern from `app/api/configs.py:212-243`

- Surface: `POST /api/device-models/<int:id>/firmware`
- Inputs: Multipart file upload
- Outputs: `{ "id": int, "firmware_version": str }` (200)
- Errors: 404 model not found, 400 invalid firmware format
- Evidence: Pattern from `app/api/assets.py`

- Surface: `GET /api/device-models/<int:id>/firmware`
- Inputs: Path parameter `id`
- Outputs: Binary firmware file (application/octet-stream)
- Errors: 404 model not found, 404 no firmware uploaded
- Evidence: Pattern from `app/api/assets.py`

### Devices API

- Surface: `GET /api/devices`
- Inputs: Optional query params `model_id`, `rotation_state`
- Outputs: `{ "devices": [...], "count": int }`
- Errors: 500 on database error
- Evidence: Pattern from `app/api/configs.py:29-64`

- Surface: `POST /api/devices`
- Inputs: `{ "device_model_id": int, "config": str (JSON) }`
- Outputs: Device with provisioning URL (201)
- Errors: 400 invalid config JSON, 404 model not found, 502 Keycloak error
- Evidence: Pattern from `app/api/configs.py:66-107`

- Surface: `GET /api/devices/<int:id>`
- Inputs: Path parameter `id`
- Outputs: Device with full details
- Errors: 404 not found
- Evidence: Pattern from `app/api/configs.py:143-170`

- Surface: `PUT /api/devices/<int:id>`
- Inputs: `{ "config": str (JSON) }`
- Outputs: Updated Device
- Errors: 404 not found, 400 invalid config
- Evidence: Pattern from `app/api/configs.py:172-210`

- Surface: `DELETE /api/devices/<int:id>`
- Inputs: Path parameter `id`
- Outputs: 204 No Content
- Errors: 404 not found, 502 Keycloak error
- Evidence: Pattern from `app/api/configs.py:212-243`

- Surface: `GET /api/devices/<int:id>/provisioning`
- Inputs: Path parameter `id`
- Outputs: Provisioning package as `.bin` file download
- Errors: 404 not found, 502 Keycloak error (if secret fetch fails)
- Evidence: Change brief "provisioning package as downloadable .bin file"

- Surface: `POST /api/devices/<int:id>/rotate`
- Inputs: Path parameter `id`
- Outputs: `{ "status": "queued" | "already_pending" }`
- Errors: 404 not found
- Evidence: Change brief "manual single-device rotation"

### Rotation API

- Surface: `GET /api/rotation/status`
- Inputs: None
- Outputs: `{ "counts_by_state": {...}, "pending_device_id": int | null, "last_rotation_completed_at": datetime | null }`
- Errors: 500 on database error
- Evidence: Change brief "Fleet-wide stats"

- Surface: `POST /api/rotation/trigger`
- Inputs: None
- Outputs: `{ "queued_count": int }`
- Errors: 500 on database error
- Evidence: Change brief "manual fleet-wide rotation"

### IoT Device API

- Surface: `GET /iot/config`
- Inputs: JWT Bearer token (device key extracted from `azp` claim)
- Outputs: Raw JSON config (application/json)
- Errors: 401 invalid/expired token, 404 device not found
- Evidence: Pattern from `app/api/configs.py:109-141`

- Surface: `GET /iot/firmware`
- Inputs: JWT Bearer token
- Outputs: Binary firmware file for device's model
- Errors: 401 invalid token, 404 no firmware
- Evidence: Change brief "Returns firmware binary for the device's model"

- Surface: `GET /iot/provisioning`
- Inputs: JWT Bearer token
- Outputs: Provisioning JSON (new secret generated, old secret overwritten in Keycloak)
- Errors: 401 invalid token, 502 Keycloak error
- Evidence: Change brief "Returns new provisioning data during rotation"

### MQTT Topic

- Surface: MQTT topic `iotsupport/<client_id>/rotation`
- Inputs: N/A (published by backend)
- Outputs: Empty payload, QoS 1, no retain
- Errors: Fire-and-forget (errors logged only)
- Evidence: Change brief "Publish MQTT to iotsupport/<client_id>/rotation"

---

## 5) Algorithms & State Machines

- Flow: Device Key Generation
- Steps:
  1. Generate 8 random bytes using `secrets.token_bytes(8)`
  2. Convert to lowercase alphanumeric: `base64.b32encode()[:8].lower()` or custom mapping
  3. Validate uniqueness in database
  4. Retry up to 3 times if collision (extremely unlikely)
- States / transitions: N/A
- Hotspots: Collision probability is ~1 in 2.8 trillion at 200 devices
- Evidence: Change brief "8-character device keys [a-z0-9]"

- Flow: Device Provisioning
- Steps:
  1. Validate device_model_id exists
  2. Validate config is valid JSON
  3. Generate unique device key
  4. Create Keycloak client `iotdevice-<model_code>-<key>`
  5. Create Device record with rotation_state=OK, secret_created_at=now
  6. Flush database
  7. Return device with provisioning package
- States / transitions: N/A
- Hotspots: Keycloak API latency (external call)
- Evidence: Change brief "Device Provisioning Flow"

- Flow: Rotation State Machine
- Steps:
  1. Check current state
  2. Apply transition based on action
  3. Update timestamps and cached secret as needed
- States / transitions:
  ```
  OK -> QUEUED (via CRON trigger or manual trigger)
  QUEUED -> PENDING (when selected for rotation, secret regenerated)
  PENDING -> OK (when device fetches config with new JWT)
  PENDING -> TIMEOUT (when timeout exceeded, old secret restored)
  TIMEOUT -> PENDING (when retry selected, secret regenerated again)
  ```
- Hotspots: Concurrent access - use row-level locking or optimistic concurrency
- Evidence: Change brief "Rotation States"

- Flow: Hourly Rotation Job
- Steps:
  1. Check if CRON schedule matches using `croniter` library (compare last_scheduled_at with current time; `croniter.get_next()` determines next scheduled time)
  2. If schedule triggered: set all OK devices to QUEUED, update last_scheduled_at
  3. Check PENDING devices: if `now - last_rotation_attempt_at > ROTATION_TIMEOUT_SECONDS`:
     - Restore cached_secret to Keycloak
     - Set state to TIMEOUT
     - Clear cached_secret
  4. If any PENDING device exists and not timed out: exit (one rotation at a time)
  5. Select next device to rotate:
     - First: QUEUED device with oldest secret_created_at
     - Fallback: TIMEOUT device
  6. If device selected:
     - Cache current secret in cached_secret column
     - Call Keycloak to regenerate client secret
     - Set state to PENDING
     - Set last_rotation_attempt_at to now
     - Publish MQTT to `iotsupport/<client_id>/rotation`
- States / transitions: See above
- Hotspots: Single-threaded processing prevents race conditions; Keycloak API latency
- Evidence: Change brief "Hourly Job"

- Flow: Device Rotation Completion
- Steps:
  1. Device calls `GET /iot/config` with new JWT
  2. Extract token `iat` (issued-at) claim
  3. If `iat > device.last_rotation_attempt_at` and state is PENDING:
     - Set state to OK
     - Set last_rotation_completed_at to now
     - Clear cached_secret
     - Record completion metrics
  4. Return config JSON
- States / transitions: PENDING -> OK
- Hotspots: Token clock skew (use tolerance)
- Evidence: Change brief "Device calls GET /iot/config with new JWT"

- Flow: ESP32 AppInfo Version Extraction
- Steps:
  1. Read firmware binary
  2. Seek to offset 32 (24-byte image header + 8-byte segment header)
  3. Read 4-byte magic word
  4. Verify magic == 0xABCD5432 (little-endian)
  5. Seek to offset 32 + 16 = 48 for version field
  6. Read 32 bytes, decode as UTF-8, strip null terminators
  7. Return version string
- States / transitions: N/A
- Hotspots: Invalid firmware format (must handle gracefully)
- Evidence: Change brief "ESP32 AppInfo (offset 32, magic 0xABCD5432, version at offset 16)"

---

## 6) Derived State & Invariants

- Derived value: `keycloak_client_id`
  - Source: Computed from `device_model.code` and `device.key`
  - Writes / cleanup: Used when creating/deleting Keycloak clients
  - Guards: Device key immutability enforced at model level
  - Invariant: `client_id == f"iotdevice-{device.device_model.code}-{device.key}"`
  - Evidence: Change brief "Client ID format: iotdevice-<model_code>-<device_key>"

- Derived value: `rotation_overdue` (computed property)
  - Source: `secret_created_at` compared against rotation interval
  - Writes / cleanup: UI display only (no persistence)
  - Guards: N/A (read-only computation)
  - Invariant: Calculation uses consistent interval from ROTATION_CRON
  - Evidence: Change brief "late (orange), very late (red)"

- Derived value: `firmware_path` (computed)
  - Source: Derived from `ASSETS_DIR` and `device_model.code`
  - Writes / cleanup: File written on firmware upload, deleted on model delete
  - Guards: Model code immutability prevents path drift
  - Invariant: `path == ASSETS_DIR / f"firmware-{model.code}.bin"`
  - Evidence: Change brief "firmware-<model_code>.bin"

- Derived value: `device_count_by_model` (aggregate)
  - Source: Count of devices per model
  - Writes / cleanup: Prevents model deletion when count > 0
  - Guards: FK constraint + delete validation
  - Invariant: Model deletion only allowed when device_count == 0
  - Evidence: Delete should "only if no devices"

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: Per-request database session via Flask teardown
- Atomic requirements:
  - Device creation: DB insert + Keycloak client creation must succeed together
    - Strategy: Create Keycloak client first, then DB insert. On DB failure, attempt to delete the Keycloak client (best-effort cleanup). Log warning if cleanup fails, as orphaned clients may block future device creation with same key.
    - Recovery: Add startup reconciliation that queries Keycloak for clients matching `iotdevice-*` pattern and removes any without matching database records.
  - Device deletion: Keycloak client deletion + DB delete
    - Strategy: Delete DB record first (fails if FK violated), then Keycloak (best-effort)
  - Rotation secret regeneration: Keycloak call + DB state update
    - Strategy: Cache secret in DB (encrypted, see Security section), call Keycloak, update DB state
  - Firmware upload: File write + DB version update
    - Strategy: Write temp file, update DB, rename atomically
- Retry / idempotency:
  - Device creation: Keycloak client ID is deterministic, can check existence before create
  - Rotation trigger: Setting QUEUED is idempotent (already QUEUED = no-op)
  - MQTT publish: Fire-and-forget, device handles duplicates
- Ordering / concurrency controls:
  - Rotation job: Single-threaded processing, one device at a time
  - Device selection: `ORDER BY secret_created_at ASC LIMIT 1 FOR UPDATE`
  - Concurrent API requests: Optimistic locking via `updated_at` check or serialize via row lock
- Evidence: `app/__init__.py:92-110` - session management pattern

---

## 8) Errors & Edge Cases

- Failure: Keycloak unavailable during device creation
- Surface: `POST /api/devices`
- Handling: 502 Bad Gateway with error message, device not created
- Guardrails: HTTP timeout (10s), retry at service level (1 retry)
- Evidence: Pattern from `app/services/oidc_client_service.py:104-156`

- Failure: Keycloak unavailable during rotation
- Surface: Rotation job
- Handling: Log error, keep device in current state, retry on next job run
- Guardrails: Job runs hourly, provides natural retry
- Evidence: Change brief "Hourly Job"

- Failure: Device doesn't complete rotation within timeout
- Surface: Rotation job
- Handling: Restore old secret in Keycloak, set state to TIMEOUT
- Guardrails: ROTATION_TIMEOUT_SECONDS default 300s, retry on next job
- Evidence: Change brief "Timeout Handling"

- Failure: Invalid firmware binary format
- Surface: `POST /api/device-models/<id>/firmware`
- Handling: 400 Bad Request with "Invalid firmware format: magic number mismatch"
- Guardrails: Validate magic number before accepting upload
- Evidence: Change brief "magic 0xABCD5432"

- Failure: Device model code contains invalid characters
- Surface: `POST /api/device-models`
- Handling: 400 Bad Request with validation error
- Guardrails: Pydantic regex validator `^[a-z0-9_]+$`
- Evidence: Change brief "code (unique, immutable, [a-z0-9_]+)"

- Failure: Duplicate device model code
- Surface: `POST /api/device-models`
- Handling: 409 Conflict with "DeviceModel for {code} already exists"
- Guardrails: Unique constraint on `code` column
- Evidence: Pattern from `app/services/config_service.py:137-142`

- Failure: Delete model with existing devices
- Surface: `DELETE /api/device-models/<id>`
- Handling: 409 Conflict with "Cannot delete model with existing devices"
- Guardrails: Check device count before delete
- Evidence: Change brief "Delete (only if no devices)"

- Failure: Device JWT expired or invalid
- Surface: `/iot/*` endpoints
- Handling: 401 Unauthorized
- Guardrails: Standard JWT validation with clock skew tolerance
- Evidence: Pattern from `app/services/auth_service.py:125-262`

- Failure: Config JSON invalid
- Surface: `POST /api/devices`, `PUT /api/devices/<id>`
- Handling: 400 Bad Request with "config must be valid JSON"
- Guardrails: Pydantic field_validator
- Evidence: Pattern from `app/schemas/config.py:37-45`

---

## 9) Observability / Telemetry

- Signal: `iot_rotation_state_count`
- Type: Gauge
- Trigger: Updated by rotation job and on state changes
- Labels / fields: `state` (OK, QUEUED, PENDING, TIMEOUT)
- Consumer: Dashboard, alert on TIMEOUT count > threshold
- Evidence: Pattern from `app/services/metrics_service.py:35-43`

- Signal: `iot_rotation_duration_seconds`
- Type: Histogram
- Trigger: On rotation completion (PENDING -> OK)
- Labels / fields: `phase` (mqtt_to_provisioning, provisioning_to_config, total)
- Consumer: Dashboard, latency analysis
- Evidence: Pattern from `app/services/metrics_service.py:39-43`

- Signal: `iot_rotation_job_runs_total`
- Type: Counter
- Trigger: On each rotation job execution
- Labels / fields: `result` (success, error, skipped)
- Consumer: Alert on error rate
- Evidence: Pattern from `app/services/metrics_service.py:29-33`

- Signal: `iot_keycloak_operations_total`
- Type: Counter
- Trigger: On each Keycloak admin API call
- Labels / fields: `operation` (create_client, regenerate_secret, delete_client), `status` (success, error)
- Consumer: Dashboard, alert on error rate
- Evidence: Pattern from `app/services/metrics_service.py:45-50`

- Signal: `iot_device_count`
- Type: Gauge
- Trigger: On device create/delete
- Labels / fields: `model_code`
- Consumer: Dashboard, capacity planning
- Evidence: Pattern from `app/services/metrics_service.py:35-37`

- Signal: Structured log: "Rotation started"
- Type: Structured log
- Trigger: When device enters PENDING state
- Labels / fields: device_key, client_id, previous_state
- Consumer: Log aggregation, debugging
- Evidence: Pattern from `app/services/auth_service.py:183-188`

- Signal: Structured log: "Rotation completed"
- Type: Structured log
- Trigger: When device completes rotation (PENDING -> OK)
- Labels / fields: device_key, duration_seconds
- Consumer: Log aggregation, debugging
- Evidence: Pattern from `app/services/auth_service.py:183-188`

---

## 10) Background Work & Shutdown

- Worker / job: Rotation Job
- Trigger cadence: Hourly (configurable via ROTATION_RETRY_INTERVAL_SECONDS, default 3600)
- Responsibilities:
  - Check CRON schedule for fleet-wide queue trigger
  - Process PENDING timeouts
  - Select and rotate one device
  - Update metrics
- Shutdown handling:
  - Register with shutdown coordinator via `PREPARE_SHUTDOWN` notification
  - On PREPARE_SHUTDOWN: stop accepting new rotation work, set shutdown flag
  - Register waiter to wait for current rotation to complete (if any)
  - Max wait: 30 seconds before forced termination
- Evidence: `CLAUDE.md` "Graceful Shutdown Integration"

- Worker / job: APScheduler Background Thread
- Trigger cadence: Startup, runs scheduler loop
- Responsibilities: Execute scheduled jobs
- Deployment strategy: Use APScheduler's SQLAlchemy job store with the application database to ensure only one instance executes the rotation job across multiple workers. Configure `misfire_grace_time=60` to coalesce missed executions. Alternative: If database job store proves unreliable, fall back to Kubernetes CronJob triggering `POST /api/rotation/process` endpoint (requires adding this internal endpoint).
- Shutdown handling:
  - Call `scheduler.shutdown(wait=True)` on app shutdown
  - Integration with Flask app teardown
- Evidence: APScheduler Flask integration pattern

---

## 11) Security & Permissions

- Concern: Device JWT authentication for `/iot/*` endpoints
- Touchpoints: `/iot/config`, `/iot/firmware`, `/iot/provisioning`
- Mitigation: Validate JWT signature via JWKS, verify `aud` claim matches, extract device key from `azp` (authorized party) claim which contains client ID
- Residual risk: Compromised device secret allows impersonation until rotation
- Evidence: Pattern from `app/services/auth_service.py:125-262`

- Concern: Admin API authentication for `/api/*` endpoints
- Touchpoints: All `/api/device-models/*`, `/api/devices/*`, `/api/rotation/*`
- Mitigation: Existing OIDC authentication with admin role requirement
- Residual risk: None beyond existing auth model
- Evidence: `app/api/__init__.py:20-88`

- Concern: Keycloak admin credentials storage
- Touchpoints: `KEYCLOAK_ADMIN_CLIENT_SECRET` environment variable
- Mitigation: Kubernetes secret, not logged, not exposed in API
- Residual risk: Container compromise exposes secret
- Evidence: Standard practice for service account credentials

- Concern: WiFi credentials in provisioning package
- Touchpoints: `WIFI_PASSWORD` environment variable, provisioning download
- Mitigation: HTTPS-only download, admin authentication required
- Residual risk: Physical access to flashed device exposes credentials
- Evidence: Change brief "WiFi SSID and password"

- Concern: Provisioning package download rate limiting
- Touchpoints: `GET /api/devices/<id>/provisioning`, `GET /iot/provisioning`
- Mitigation: Authentication required for both endpoints
- Residual risk: Authenticated user can download unlimited times
- Evidence: Consider future rate limiting

- Concern: Cached secret storage for timeout recovery
- Touchpoints: `Device.cached_secret` column, rotation timeout handling
- Mitigation: Encrypt cached_secret using Fernet symmetric encryption with key derived from `SECRET_KEY` environment variable. Secret is encrypted before storage and decrypted only when needed for Keycloak restore. Secret is cleared (set to NULL) immediately after timeout processing completes.
- Residual risk: Application memory compromise during rotation window exposes decrypted secret; SECRET_KEY compromise allows decryption of all cached secrets. Acceptable because: (1) rotation window is short (5 min default), (2) SECRET_KEY compromise already implies full session compromise.
- Evidence: Pattern from Django's `Fernet` field encryption

---

## 12) UX / UI Impact

- Entry point: Device Models page (new)
- Change: New CRUD interface for managing device hardware types
- User interaction: List models, create model with code/name, upload firmware, view devices per model
- Dependencies: `/api/device-models` endpoints
- Evidence: New feature

- Entry point: Devices page (replaces Configs page)
- Change: Replace MAC-based config list with device-based management
- User interaction: List devices with rotation status, create device selecting model, edit config JSON, download provisioning, trigger rotation
- Dependencies: `/api/devices` endpoints
- Evidence: Change brief replaces configs

- Entry point: Rotation Dashboard (new)
- Change: Fleet-wide rotation status visualization
- User interaction: View counts by state, see pending rotation, trigger manual rotation
- Dependencies: `/api/rotation/status`, `/api/rotation/trigger` endpoints
- Evidence: Change brief "Dashboard Support"

- Entry point: Device detail modal/page
- Change: Show rotation state, timing metrics, re-download provisioning
- User interaction: View secret age, rotation history, trigger single-device rotation
- Dependencies: `/api/devices/<id>`, `/api/devices/<id>/rotate` endpoints
- Evidence: Change brief "Per-device details"

---

## 13) Deterministic Test Plan

- Surface: DeviceModelService
- Scenarios:
  - Given no models, When create_model("thermostat", "Smart Thermostat"), Then model created with id and timestamps
  - Given model exists, When create_model with same code, Then RecordExistsException raised
  - Given model with devices, When delete_model, Then InvalidOperationException raised
  - Given model exists, When upload_firmware with valid ESP32 binary, Then firmware_version extracted and stored
  - Given model exists, When upload_firmware with invalid binary (wrong magic), Then ValidationException raised
- Fixtures / hooks: `make_device_model` factory fixture
- Gaps: None
- Evidence: Pattern from `tests/services/test_config_service.py`

- Surface: DeviceService
- Scenarios:
  - Given model exists, When create_device(model_id, config_json), Then device created with 8-char key, Keycloak client created
  - Given no model, When create_device with invalid model_id, Then RecordNotFoundException raised
  - Given device exists, When update_device with new config, Then config updated
  - Given device exists, When delete_device, Then device deleted, Keycloak client deleted
  - Given device in OK state, When trigger_rotation, Then state becomes QUEUED
  - Given device in PENDING state, When trigger_rotation, Then state unchanged (already rotating)
  - Given Keycloak client created, When DB insert fails, Then Keycloak client cleanup attempted, ExternalServiceException raised
  - Given Keycloak client created and DB fails and cleanup fails, Then warning logged, ExternalServiceException raised with context
- Fixtures / hooks: `make_device` factory fixture, mock KeycloakAdminService with configurable failure modes
- Gaps: None
- Evidence: Pattern from `tests/services/test_config_service.py`

- Surface: KeycloakAdminService
- Scenarios:
  - Given valid credentials, When create_client(client_id), Then client created with secret returned
  - Given existing client, When create_client with same id, Then return existing secret (idempotent)
  - Given existing client, When regenerate_secret(client_id), Then new secret returned
  - Given client exists, When delete_client(client_id), Then client deleted
  - Given invalid credentials, When any operation, Then ExternalServiceException raised
- Fixtures / hooks: Mock httpx responses
- Gaps: Integration test against real Keycloak deferred (requires test Keycloak instance)
- Evidence: Pattern from `tests/services/test_auth_service.py`

- Surface: RotationService
- Scenarios:
  - Given devices in OK state, When process_rotation_job with CRON matched, Then all set to QUEUED
  - Given device in QUEUED state, When process_rotation_job, Then oldest selected, set to PENDING, MQTT published
  - Given device in PENDING state, When process_rotation_job within timeout, Then no action (wait for completion)
  - Given device in PENDING state past timeout, When process_rotation_job, Then secret restored, state set to TIMEOUT
  - Given device in TIMEOUT state, When process_rotation_job, Then retry rotation (re-select)
  - Given two concurrent job executions, When both attempt device selection, Then only one succeeds due to FOR UPDATE lock
  - Given Keycloak unavailable during secret restore, When timeout processing, Then state remains PENDING, error logged, retry on next job
- Fixtures / hooks: Mock MqttService, mock KeycloakAdminService, frozen time, concurrent execution test using threading
- Gaps: None
- Evidence: Change brief "Rotation States"

- Surface: FirmwareService
- Scenarios:
  - Given valid ESP32 binary with AppInfo, When extract_version, Then version string returned
  - Given binary with wrong magic number, When extract_version, Then ValidationException raised
  - Given binary too short, When extract_version, Then ValidationException raised
  - Given model code, When get_firmware_path, Then correct path returned
  - Given firmware file exists, When save_firmware, Then file replaced atomically
- Fixtures / hooks:
  - `make_valid_firmware(version: str) -> bytes`: Factory that constructs minimal valid ESP32 binary with AppInfo header (magic 0xABCD5432 at offset 32, version string at offset 48)
  - `make_invalid_firmware_magic() -> bytes`: Binary with wrong magic number
  - `make_truncated_firmware() -> bytes`: Binary shorter than required header length
- Gaps: None
- Evidence: Pattern from `tests/services/test_asset_upload_service.py`

- Surface: Device Models API
- Scenarios:
  - Given empty database, When GET /api/device-models, Then 200 with empty list
  - Given valid payload, When POST /api/device-models, Then 201 with created model
  - Given invalid code format, When POST /api/device-models, Then 400 validation error
  - Given model exists, When GET /api/device-models/<id>, Then 200 with model details
  - Given model with devices, When DELETE /api/device-models/<id>, Then 409 conflict
- Fixtures / hooks: `make_device_model` fixture
- Gaps: None
- Evidence: Pattern from `tests/api/test_configs.py`

- Surface: Devices API
- Scenarios:
  - Given model exists, When POST /api/devices, Then 201 with device, Keycloak client created
  - Given device exists, When GET /api/devices/<id>/provisioning, Then binary file downloaded
  - Given device in OK state, When POST /api/devices/<id>/rotate, Then 200, state is QUEUED
- Fixtures / hooks: `make_device` fixture, mock Keycloak
- Gaps: None
- Evidence: Pattern from `tests/api/test_configs.py`

- Surface: IoT Endpoints
- Scenarios:
  - Given valid device JWT, When GET /iot/config, Then 200 with raw JSON config
  - Given valid device JWT, When GET /iot/firmware, Then 200 with binary firmware
  - Given device in PENDING state, When GET /iot/config with new JWT, Then rotation completed, state is OK
  - Given expired JWT, When GET /iot/config, Then 401 unauthorized
  - Given invalid JWT, When GET /iot/config, Then 401 unauthorized
  - Given JWT with malformed azp claim (not matching iotdevice-* pattern), When GET /iot/config, Then 401 unauthorized
  - Given JWT with valid format but non-existent device key, When GET /iot/config, Then 404 not found
- Fixtures / hooks: Device JWT generation fixture with configurable azp claim
- Gaps: None
- Evidence: Pattern from `tests/api/test_configs.py:402-498`

---

## 14) Implementation Slices

- Slice: 1. Data Model Foundation
- Goal: Create DeviceModel and Device tables, remove Config
- Touches: `app/models/device_model.py`, `app/models/device.py`, `alembic/versions/002_*`, remove `app/models/config.py`
- Dependencies: Must be first, blocks all other slices

- Slice: 2. Keycloak Admin Service
- Goal: Enable Keycloak client CRUD operations
- Touches: `app/services/keycloak_admin_service.py`, `app/config.py` (new env vars), `tests/services/test_keycloak_admin_service.py`
- Dependencies: After slice 1 (needs device model for client ID)

- Slice: 3. Device Model Service & API
- Goal: DeviceModel CRUD without firmware
- Touches: `app/services/device_model_service.py`, `app/schemas/device_model.py`, `app/api/device_models.py`, tests
- Dependencies: After slice 1

- Slice: 4. Firmware Service
- Goal: Firmware upload/download with version extraction
- Touches: `app/services/firmware_service.py`, extend `app/api/device_models.py`, tests
- Dependencies: After slice 3

- Slice: 5. Device Service & API
- Goal: Device CRUD with Keycloak integration, provisioning
- Touches: `app/services/device_service.py`, `app/schemas/device.py`, `app/api/devices.py`, tests
- Dependencies: After slices 2, 3

- Slice: 6. IoT Blueprint
- Goal: Device-authenticated endpoints
- Touches: `app/api/iot.py`, `app/utils/device_auth.py`, tests
- Dependencies: After slice 5

- Slice: 7. Rotation State Machine
- Goal: Rotation service with state transitions (no background job yet)
- Touches: `app/services/rotation_service.py`, `app/schemas/rotation.py`, extend `app/api/devices.py`, tests
- Dependencies: After slice 5

- Slice: 8. Background Rotation Job
- Goal: Scheduled rotation with APScheduler
- Touches: `app/services/rotation_service.py` (add scheduler), `app/__init__.py` (startup hook), tests
- Dependencies: After slice 7

- Slice: 9. Rotation Metrics & Dashboard API
- Goal: Prometheus metrics, rotation status endpoint
- Touches: `app/services/metrics_service.py`, `app/api/rotation.py`, tests
- Dependencies: After slice 8

- Slice: 10. Cleanup & Documentation
- Goal: Remove old configs API, write frontend impact doc
- Touches: Remove `app/api/configs.py`, `app/services/config_service.py`, `app/schemas/config.py`, tests; write `frontend_impact.md`
- Dependencies: After all other slices

---

## 15) Risks & Open Questions

- Risk: Product brief misalignment with MDM architecture
- Impact: Stakeholder confusion, incorrect expectations about application scope
- Mitigation: Update `docs/product_brief.md` before implementation to reflect: (1) authentication is now required for admin APIs, (2) database is now required for device/model storage, (3) Keycloak integration is a core dependency. This is a prerequisite for implementation.

- Risk: Keycloak API changes between versions
- Impact: Service failures, stuck rotations
- Mitigation: Pin Keycloak version in deployment, add Keycloak version check at startup

- Risk: APScheduler job doesn't run in multi-worker deployment
- Impact: Rotation stalls
- Mitigation: Use APScheduler SQLAlchemy job store with `misfire_grace_time=60` to ensure single execution across workers

- Risk: Clock drift between server and Keycloak causes JWT validation failures
- Impact: Devices unable to authenticate
- Mitigation: Use OIDC_CLOCK_SKEW_SECONDS tolerance (existing pattern)

- Risk: Large fleet rotation takes too long
- Impact: Old secrets remain active longer than desired
- Mitigation: Monitor rotation throughput metrics, adjust ROTATION_RETRY_INTERVAL_SECONDS

- Risk: Cached secret column creates security liability
- Impact: Attacker with DB access gets previous secrets
- Mitigation: Clear cached_secret immediately after use, consider encryption at rest

- Question: Should device key be displayed in UI or kept secret?
- Why it matters: UX decision affects provisioning workflow
- Owner / follow-up: Product decision - key is in provisioning file, not truly secret

- Question: How long should rotation interval be for first deployment?
- Why it matters: Affects operational complexity and security posture
- Owner / follow-up: Use conservative default (first Saturday of month)

- Question: Should firmware version comparison trigger automatic device update?
- Why it matters: Could add OTA push capability
- Owner / follow-up: Out of scope per change brief, document for future enhancement

---

## 16) Confidence

Confidence: High - The change brief is detailed, existing codebase patterns are clear, and the state machine is well-defined. Main complexity is in Keycloak integration and rotation job scheduling, both of which have well-established library support (httpx, APScheduler).
