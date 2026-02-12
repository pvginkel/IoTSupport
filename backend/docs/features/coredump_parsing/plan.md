# Coredump Parsing & Management -- Technical Plan

## 0) Research Log & Findings

### Areas Researched

**Existing coredump implementation.** The current `CoredumpService` (`app/services/coredump_service.py:17-121`) is a lightweight singleton that writes `.dmp` binary files and `.json` sidecar metadata to the filesystem under `COREDUMPS_DIR/{device_key}/`. It validates content size (max 1 MB), device key format, and the presence of `COREDUMPS_DIR` configuration. It has no database interaction and no parsing capability.

**Upload endpoint.** `POST /iot/coredump` (`app/api/iot.py:353-419`) accepts raw binary with `chip` and `firmware_version` query params, resolves the device from auth context or query param, and delegates to `CoredumpService.save_coredump()`. The response is `{"status": "ok", "filename": "..."}` with HTTP 201.

**Container wiring.** `CoredumpService` is registered as a `providers.Singleton` in `app/services/container.py:103-106`, receiving only `coredumps_dir` from config. The container is wired to `app.api.iot` at `app/__init__.py:70`.

**Configuration.** `COREDUMPS_DIR` is already defined in `Environment` (`app/config.py:82-85`) and `Settings` (`app/config.py:264`). The new `PARSE_SIDECAR_XFER_DIR`, `PARSE_SIDECAR_URL`, and `MAX_COREDUMPS` variables need to be added to both classes.

**Device model.** `Device` (`app/models/device.py:30-104`) has no `coredumps` relationship currently. `DeviceModel` has `devices` with cascade delete. The pattern for adding a new relationship with cascade is well established.

**Firmware ZIP handling.** `FirmwareService` (`app/services/firmware_service.py:177-262`) demonstrates how to open firmware ZIPs, extract `.elf` files, and validate contents. The ZIP path is `ASSETS_DIR/{model_code}/firmware-{version}.zip` and the `.elf` inside is named `{model_code}.elf`.

**API patterns.** Admin endpoints under `/api/devices/<device_id>/` already exist for provisioning, rotation, logs, and keycloak-status (`app/api/devices.py`). The coredump admin endpoints will follow this established nesting pattern.

**Testing patterns.** Tests use `app`, `client`, `container`, `session` fixtures from `tests/conftest.py`. Service tests instantiate services from the container. API tests use `FlaskClient` with `app.app_context()`. The existing `tests/services/test_coredump_service.py` and `tests/api/test_iot.py::TestIotCoredump` will need updates.

### Key Findings and Resolutions

1. **IoT blueprint is nested under `/api`.** The `iot_bp` is registered on `api_bp` (`app/api/__init__.py:197`), so the upload URL is actually `/api/iot/coredump`, not `/iot/coredump`. The change brief refers to `POST /iot/coredump` but the actual route is `/api/iot/coredump`. This plan uses the actual path.

2. **Singleton vs Factory for CoredumpService.** The current service is a singleton with no DB access. The refactored service needs a DB session for record management but also needs filesystem access for the sidecar parsing flow. Since background parsing occurs in a thread (not in a request context), the service should remain a singleton and use the container's `db_session` pattern for session management (get session, try/commit, finally reset) as documented in `CLAUDE.md` for singletons that need database access.

3. **Background parsing approach.** The change brief says "background parsing after upload." Since the app has no task queue (like Celery), and the existing architecture uses threads for background work (e.g., `LogSinkService`), parsing will be done in a `threading.Thread` started after the upload response is sent. The thread will manage its own DB session via the container pattern.

4. **ELF extraction from firmware ZIP.** The firmware ZIP at `ASSETS_DIR/{model_code}/firmware-{version}.zip` contains `{model_code}.elf`. The parsing flow needs to extract this file and copy it to `PARSE_SIDECAR_XFER_DIR`.

5. **No Alembic migration needed.** The change brief explicitly states this. The new model will be picked up by `db.create_all()` in tests and by future migrations when deployed.

---

## 1) Intent & Scope

**User intent**

Evolve the existing coredump upload feature from a filesystem-only storage mechanism into a fully managed system with database tracking, automatic parsing via a sidecar container, per-device retention limits, and admin API endpoints for viewing and managing coredumps.

**Prompt quotes**

"Add database-backed coredump tracking, automatic parsing via a sidecar container, per-device retention limits, and admin API endpoints"

"Remove JSON sidecar file writing -- metadata stored in DB instead"

"Background parsing after upload: extract .elf from firmware ZIP, copy .dmp and .elf to PARSE_SIDECAR_XFER_DIR, call sidecar endpoint, update DB record"

"Retry parsing up to 3 times on failure; after 3 failures set parse_status=ERROR"

**In scope**

- New `coredumps` database table and SQLAlchemy model
- Configuration for sidecar integration (`PARSE_SIDECAR_XFER_DIR`, `PARSE_SIDECAR_URL`, `MAX_COREDUMPS`)
- Refactored `CoredumpService` with DB record management, retention enforcement, and background parsing
- Refactored upload endpoint to create DB records and trigger parsing
- Admin API endpoints for listing, viewing, downloading, and deleting coredumps
- Pydantic schemas for admin API request/response validation
- Comprehensive service and API tests

**Out of scope**

- Alembic migration (not yet in production)
- Frontend UI changes
- Sidecar container implementation (external service)
- Shutdown coordinator integration for background parsing (single short-lived HTTP call, not a long-running worker)

**Assumptions / constraints**

- The parse sidecar is a co-located container accessible via HTTP at `PARSE_SIDECAR_URL`, with a shared volume at `PARSE_SIDECAR_XFER_DIR`.
- Firmware ZIPs are already uploaded and contain `{model_code}.elf` as validated by `FirmwareService.save_firmware_zip()`.
- Scale is small (up to 200 devices, max 20 coredumps per device = 4000 coredumps maximum).
- Background parsing thread does not need graceful shutdown coordination because it is a short-lived HTTP call (seconds, not minutes).

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Add PARSE_SIDECAR_XFER_DIR environment variable (Path, for file transfer to sidecar)
- [ ] Add PARSE_SIDECAR_URL environment variable (str, base URL of parse sidecar)
- [ ] Add MAX_COREDUMPS environment variable (int, default 20, per-device limit)
- [ ] Create coredumps table linked to devices via FK with fields: id, device_id, filename, chip, firmware_version, size, parse_status, parsed_output, uploaded_at, parsed_at, created_at, updated_at
- [ ] Add coredumps relationship to Device model with cascade delete
- [ ] Remove JSON sidecar file writing from coredump upload -- metadata stored in DB instead
- [ ] Create DB record with parse_status=PENDING on coredump upload
- [ ] Enforce MAX_COREDUMPS per device by deleting oldest records + files when exceeded
- [ ] Background parsing after upload: extract .elf from firmware ZIP, copy .dmp and .elf to PARSE_SIDECAR_XFER_DIR, call sidecar endpoint, update DB record
- [ ] Sidecar call: GET {PARSE_SIDECAR_URL}/parse-coredump?core={name}&elf={name}&chip={chip}, response is {"output":"..."}
- [ ] Retry parsing up to 3 times on failure; after 3 failures set parse_status=ERROR with "Unable to parse coredump: {error}" as parsed_output
- [ ] Clean up xfer directory files after parsing (best-effort)
- [ ] Upload endpoint (POST /iot/coredump) creates DB record and triggers background parsing
- [ ] Admin API: GET /api/devices/{device_id}/coredumps -- list coredumps for device
- [ ] Admin API: GET /api/devices/{device_id}/coredumps/{coredump_id} -- detail with parsed output
- [ ] Admin API: GET /api/devices/{device_id}/coredumps/{coredump_id}/download -- download raw .dmp
- [ ] Admin API: DELETE /api/devices/{device_id}/coredumps/{coredump_id} -- delete single
- [ ] Admin API: DELETE /api/devices/{device_id}/coredumps -- delete all for device
- [ ] All coredump endpoints verify coredump belongs to specified device
- [ ] Comprehensive service tests for CoredumpService
- [ ] Comprehensive API tests for coredump endpoints
- [ ] No Alembic migration needed (not yet in production)

---

## 2) Affected Areas & File Map

- Area: `app/config.py` -- `Environment` class and `Settings` class
- Why: Add `PARSE_SIDECAR_XFER_DIR`, `PARSE_SIDECAR_URL`, `MAX_COREDUMPS` environment variables and corresponding settings fields.
- Evidence: `app/config.py:82-85` -- existing `COREDUMPS_DIR` pattern shows how to add new optional Path/str fields. `app/config.py:264` -- `Settings` class mirrors env vars as lowercase fields.

- Area: `app/models/coredump.py` (new file)
- Why: New SQLAlchemy model for the `coredumps` table with fields: id, device_id, filename, chip, firmware_version, size, parse_status, parsed_output, uploaded_at, parsed_at, created_at, updated_at.
- Evidence: `app/models/device.py:30-104` -- existing model pattern with `Mapped` typed columns, timestamps, and FK relationships.

- Area: `app/models/device.py` -- `Device` class
- Why: Add `coredumps` relationship with cascade delete to the Device model.
- Evidence: `app/models/device_model.py:51-56` -- pattern for `relationship("Device", back_populates=..., cascade="all, delete-orphan")`.

- Area: `app/models/__init__.py`
- Why: Export the new `Coredump` model and `ParseStatus` enum.
- Evidence: `app/models/__init__.py:1-7` -- exports `Device`, `DeviceModel`, `RotationState`, `Setting`.

- Area: `app/services/coredump_service.py` -- `CoredumpService` class
- Why: Major refactor: add DB record creation, remove JSON sidecar writing, add retention enforcement, add background parsing with sidecar HTTP calls, add CRUD methods for admin endpoints.
- Evidence: `app/services/coredump_service.py:17-121` -- current implementation writes .dmp + .json files only. The entire service needs restructuring.

- Area: `app/services/container.py` -- `ServiceContainer` class
- Why: Update `CoredumpService` singleton provider to pass all new dependencies. The refactored constructor signature will be: `__init__(self, coredumps_dir: Path | None, config: Settings, container: ServiceContainer, firmware_service: FirmwareService, metrics_service: MetricsService)`. The `container` reference is needed for the singleton DB session pattern (`container.db_session()` / `reset()`), `firmware_service` for ELF extraction from firmware ZIPs, `config` for `parse_sidecar_url`, `parse_sidecar_xfer_dir`, and `max_coredumps`, and `metrics_service` for recording `coredump_parse` operation metrics in the background thread.
- Evidence: `app/services/container.py:103-106` -- current singleton provider only passes `coredumps_dir`.

- Area: `app/schemas/coredump.py` (new file)
- Why: Pydantic schemas for coredump admin API responses (list summary, detail, etc.).
- Evidence: `app/schemas/device.py:1-60` -- existing schema patterns with `ConfigDict(from_attributes=True)` and `Field()`.

- Area: `app/api/coredumps.py` (new file)
- Why: Admin API endpoints for coredump management nested under `/devices/<device_id>/coredumps`.
- Evidence: `app/api/devices.py:36-440` -- pattern for device-nested endpoints with SpectTree validation, error handling, and metrics.

- Area: `app/api/iot.py` -- `upload_coredump()` function
- Why: Refactor to pass `device_id` to the service, create DB record, and trigger background parsing instead of just saving to filesystem.
- Evidence: `app/api/iot.py:353-419` -- current upload endpoint delegates to `coredump_service.save_coredump()`.

- Area: `app/api/__init__.py`
- Why: Register the new `coredumps_bp` blueprint under `devices_bp` (or directly on `api_bp` with nesting) and add to container wiring.
- Evidence: `app/api/__init__.py:180-200` -- blueprint registration pattern. `app/__init__.py:63-77` -- container wiring list.

- Area: `app/__init__.py` -- `create_app()`
- Why: Add `app.api.coredumps` to the container wiring modules list.
- Evidence: `app/__init__.py:63-77` -- wire_modules list.

- Area: `tests/services/test_coredump_service.py`
- Why: Complete rewrite to test the refactored CoredumpService with DB records, retention enforcement, background parsing (mocked sidecar), CRUD operations.
- Evidence: `tests/services/test_coredump_service.py:1-231` -- current tests focus on filesystem-only operations.

- Area: `tests/api/test_iot.py` -- `TestIotCoredump` class
- Why: Update upload tests to verify DB record creation instead of JSON sidecar files.
- Evidence: `tests/api/test_iot.py:332-458` -- current tests check `.json` sidecar files and filesystem writes.

- Area: `tests/api/test_coredumps.py` (new file)
- Why: API tests for the new admin coredump endpoints.
- Evidence: `tests/api/test_devices.py` and `tests/api/test_iot.py` -- existing API test patterns.

---

## 3) Data Model / Contracts

- Entity / contract: `ParseStatus` enum
- Shape:
  ```
  class ParseStatus(str, Enum):
      PENDING = "PENDING"
      PARSED = "PARSED"
      ERROR = "ERROR"
  ```
- Refactor strategy: New enum, no back-compat needed. Stored as text column (native_enum=False per CLAUDE.md).
- Evidence: `app/models/device.py:15-27` -- `RotationState` enum pattern with `str, Enum` base.

- Entity / contract: `coredumps` table (new)
- Shape:
  ```
  | Column           | Type         | Constraints                          |
  |------------------|-------------|--------------------------------------|
  | id               | Integer     | PK, auto-increment                   |
  | device_id        | Integer     | FK -> devices.id, NOT NULL, ON DELETE CASCADE |
  | filename         | String(255) | NOT NULL (e.g., coredump_20260211T143000_123456Z.dmp) |
  | chip             | String(50)  | NOT NULL (e.g., esp32s3)             |
  | firmware_version | String(50)  | NOT NULL                             |
  | size             | Integer     | NOT NULL (bytes)                     |
  | parse_status     | String(20)  | NOT NULL, default "PENDING"          |
  | parsed_output    | Text        | NULL (populated after parse)         |
  | uploaded_at      | DateTime    | NOT NULL                             |
  | parsed_at        | DateTime    | NULL (set when parse completes)      |
  | created_at       | DateTime    | NOT NULL, server_default=now         |
  | updated_at       | DateTime    | NOT NULL, server_default=now, onupdate |
  ```
- Refactor strategy: Brand new table, no migration needed (not in production).
- Evidence: `app/models/device.py:40-85` -- column definition patterns. `CLAUDE.md` -- "Use native_enum=False ... prefer plain string columns."

- Entity / contract: `Device.coredumps` relationship (new field on existing model)
- Shape:
  ```python
  coredumps: Mapped[list["Coredump"]] = relationship(
      "Coredump", back_populates="device",
      cascade="all, delete-orphan", lazy="select",
  )
  ```
- Refactor strategy: Add relationship to existing model. No back-compat concern. Uses `lazy="select"` (default lazy loading) instead of `lazy="selectin"` to avoid eagerly loading coredumps on every device query across the application. Admin coredump endpoints that need the relationship should use explicit `selectinload(Device.coredumps)` in their queries.
- Evidence: `app/models/device_model.py:51-56` -- pattern for cascade relationships. The `DeviceModel.devices` relationship uses `selectin` because devices are almost always needed when loading a model, but coredumps are only needed in the dedicated coredump admin endpoints.

- Entity / contract: Configuration additions
- Shape:
  ```
  # Environment (UPPER_CASE)
  PARSE_SIDECAR_XFER_DIR: Path | None = None
  PARSE_SIDECAR_URL: str | None = None
  MAX_COREDUMPS: int = 20

  # Settings (lowercase)
  parse_sidecar_xfer_dir: Path | None = None
  parse_sidecar_url: str | None = None
  max_coredumps: int = 20
  ```
- Refactor strategy: New optional fields with sensible defaults. No migration.
- Evidence: `app/config.py:76-85` -- `COREDUMPS_DIR` / `ASSETS_DIR` pattern for optional Path. `app/config.py:209` -- `ROTATION_TIMEOUT_SECONDS` pattern for int with default.

- Entity / contract: Coredump list response schema
- Shape:
  ```json
  {
    "coredumps": [
      {
        "id": 1,
        "device_id": 42,
        "filename": "coredump_20260211T143000_123456Z.dmp",
        "chip": "esp32s3",
        "firmware_version": "1.2.3",
        "size": 65536,
        "parse_status": "PARSED",
        "uploaded_at": "2026-02-11T14:30:00Z",
        "parsed_at": "2026-02-11T14:30:05Z",
        "created_at": "2026-02-11T14:30:00Z"
      }
    ],
    "count": 1
  }
  ```
- Refactor strategy: New schema, no back-compat.
- Evidence: `app/schemas/device.py:51-60` -- `DeviceSummarySchema` pattern.

- Entity / contract: Coredump detail response schema
- Shape:
  ```json
  {
    "id": 1,
    "device_id": 42,
    "filename": "coredump_20260211T143000_123456Z.dmp",
    "chip": "esp32s3",
    "firmware_version": "1.2.3",
    "size": 65536,
    "parse_status": "PARSED",
    "parsed_output": "Guru Meditation Error: Core  0 panic'ed (LoadProhibited)...",
    "uploaded_at": "2026-02-11T14:30:00Z",
    "parsed_at": "2026-02-11T14:30:05Z",
    "created_at": "2026-02-11T14:30:00Z",
    "updated_at": "2026-02-11T14:30:05Z"
  }
  ```
- Refactor strategy: New schema, no back-compat.
- Evidence: `app/schemas/device.py` -- response schema patterns.

---

## 4) API / Integration Surface

- Surface: `POST /api/iot/coredump` (refactored)
- Inputs: Raw binary body, query params: `chip` (required), `firmware_version` (required), `device_key` (when OIDC disabled). Device identity from JWT auth context.
- Outputs: `{"status": "ok", "filename": "..."}` with HTTP 201. Side effects: DB record created with `parse_status=PENDING`, background thread launched to parse.
- Errors: 400 (missing params, empty body, exceeds 1 MB, coredumps_dir not configured), 401 (no auth), 404 (unknown device key).
- Evidence: `app/api/iot.py:353-419` -- current endpoint implementation.

- Surface: `GET /api/devices/{device_id}/coredumps` (new)
- Inputs: Path param `device_id` (int).
- Outputs: `{"coredumps": [...], "count": N}` with HTTP 200. Each entry is a summary (no `parsed_output`).
- Errors: 404 (device not found).
- Evidence: `app/api/devices.py:39-73` -- `list_devices` pattern.

- Surface: `GET /api/devices/{device_id}/coredumps/{coredump_id}` (new)
- Inputs: Path params `device_id` (int), `coredump_id` (int).
- Outputs: Full coredump detail including `parsed_output` with HTTP 200.
- Errors: 404 (device not found, coredump not found, coredump does not belong to device).
- Evidence: `app/api/devices.py:114-142` -- `get_device` pattern.

- Surface: `GET /api/devices/{device_id}/coredumps/{coredump_id}/download` (new)
- Inputs: Path params `device_id` (int), `coredump_id` (int).
- Outputs: Raw `.dmp` binary as `application/octet-stream` attachment.
- Errors: 404 (device not found, coredump not found, coredump does not belong to device, file not on disk).
- Evidence: `app/api/iot.py:173-224` -- firmware download using `send_file` pattern.

- Surface: `DELETE /api/devices/{device_id}/coredumps/{coredump_id}` (new)
- Inputs: Path params `device_id` (int), `coredump_id` (int).
- Outputs: HTTP 204 (no content).
- Errors: 404 (device not found, coredump not found, coredump does not belong to device).
- Evidence: `app/api/devices.py:180-209` -- `delete_device` pattern.

- Surface: `DELETE /api/devices/{device_id}/coredumps` (new)
- Inputs: Path param `device_id` (int).
- Outputs: HTTP 204 (no content).
- Errors: 404 (device not found).
- Evidence: `app/api/devices.py:180-209` -- delete pattern.

- Surface: `GET {PARSE_SIDECAR_URL}/parse-coredump` (external, outbound)
- Inputs: Query params: `core` (filename), `elf` (filename), `chip` (string).
- Outputs: `{"output": "..."}` with HTTP 200.
- Errors: Non-200 response or connection failure triggers retry (up to 3 attempts).
- Evidence: Change brief specification.

---

## 5) Algorithms & State Machines

- Flow: Coredump upload and background parsing
- Steps:
  1. Device uploads raw binary to `POST /api/iot/coredump` with `chip` and `firmware_version` query params.
  2. Endpoint resolves device identity (JWT auth context or `device_key` query param), looks up the `Device` record to obtain `device_id` and model code.
  3. Service validates content (non-empty, <= 1 MB, alphanumeric device key).
  4. Service generates timestamped filename and writes `.dmp` file atomically to `COREDUMPS_DIR/{device_key}/`.
  5. Service creates a `Coredump` DB record with `parse_status=PENDING`, `uploaded_at=now`, `size=len(content)`.
  6. Service flushes the session to persist the record and obtain the coredump ID.
  7. Service enforces `MAX_COREDUMPS` per device: queries count of coredumps for `device_id`, if count exceeds limit, deletes the oldest records and their `.dmp` files.
  8. Service returns the filename and the coredump ID to the endpoint.
  9. Endpoint returns `{"status": "ok", "filename": "..."}` with HTTP 201.
  10. The request teardown handler commits the transaction (persisting the Coredump record) and closes the session (`app/__init__.py:109-127`).
  11. Flask's `after_request`/response lifecycle completes. The background thread is spawned from the endpoint layer using `threading.Thread(daemon=True)`. All data needed for parsing is passed as arguments to the thread function (coredump_id, device_key, model_code, chip, firmware_version, filename) so the thread does not need to read the initial record from the DB. This eliminates the race condition where the thread's separate session cannot see uncommitted data.
  12. Background thread: locate firmware ZIP at `ASSETS_DIR/{model_code}/firmware-{firmware_version}.zip`, extract `{model_code}.elf`. Note: the thread uses `model_code` and `firmware_version` passed as arguments, not looked up from the DB.
  13. Background thread: copy `.dmp` from `COREDUMPS_DIR/{device_key}/{filename}` and `.elf` to `PARSE_SIDECAR_XFER_DIR`.
  14. Background thread: call `GET {PARSE_SIDECAR_URL}/parse-coredump?core={dmp_name}&elf={elf_name}&chip={chip}`.
  15. On success (HTTP 200 with `{"output": "..."}`): acquire a DB session via the container singleton pattern, update the Coredump record (looked up by coredump_id) with `parse_status=PARSED`, `parsed_output=output`, `parsed_at=now`, commit, and reset the session.
  16. On failure: retry up to 3 times. After 3 failures: acquire a DB session, set `parse_status=ERROR`, `parsed_output="Unable to parse coredump: {error}"`, commit, and reset the session.
  17. Best-effort cleanup: remove `.dmp` and `.elf` files from `PARSE_SIDECAR_XFER_DIR`.
- States / transitions: `parse_status`: PENDING -> PARSED (success), PENDING -> ERROR (3 failures). If sidecar configuration is missing, no background thread is spawned and status remains PENDING.
- Hotspots: The sidecar HTTP call may take several seconds. This runs in a background thread spawned after the request completes, so it does not block the upload response. At scale of 200 devices, concurrent parsing threads are unlikely to be a problem.
- Evidence: `app/services/coredump_service.py:38-121` -- current save logic. `app/services/firmware_service.py:83-93` -- ZIP path computation. `app/services/firmware_service.py:131-150` -- ZIP extraction pattern.

- Flow: Retention enforcement (MAX_COREDUMPS)
- Steps:
  1. After creating a new coredump record, query coredumps for this device_id ordered by `uploaded_at` ascending.
  2. If count > MAX_COREDUMPS, compute excess = count - MAX_COREDUMPS.
  3. Select the oldest `excess` records.
  4. For each: delete the `.dmp` file from `COREDUMPS_DIR/{device_key}/` (best-effort), then delete the DB record.
  5. Flush the session.
- States / transitions: None.
- Hotspots: At MAX_COREDUMPS=20, this deletes at most 1 record per upload (since we just added 1).
- Evidence: Change brief: "Enforce MAX_COREDUMPS per device by deleting oldest records + files when exceeded."

---

## 6) Derived State & Invariants

- Derived value: Per-device coredump count
  - Source: Count of `Coredump` records with matching `device_id` (unfiltered, all statuses).
  - Writes / cleanup: When count exceeds `MAX_COREDUMPS`, oldest records and their `.dmp` files are deleted.
  - Guards: Retention enforcement runs within the same transaction as the new record insertion. The count query and deletions happen before the transaction commits.
  - Invariant: A device never has more than `MAX_COREDUMPS` coredumps persisted (at commit time).
  - Evidence: Change brief requirement. `app/services/coredump_service.py` -- will be refactored.

- Derived value: Coredump parse status
  - Source: Result of sidecar HTTP call (background thread).
  - Writes / cleanup: Updates `parse_status`, `parsed_output`, `parsed_at` on the `Coredump` record. Cleans up xfer directory files.
  - Guards: Background thread acquires its own DB session, retries up to 3 times, catches all exceptions. The xfer cleanup is best-effort (logged, not raised).
  - Invariant: Every coredump eventually reaches either PARSED or ERROR status (assuming the background thread runs to completion).
  - Evidence: Change brief: "Retry parsing up to 3 times on failure; after 3 failures set parse_status=ERROR."

- Derived value: Coredump file path on disk
  - Source: `COREDUMPS_DIR / device.key / coredump.filename`.
  - Writes / cleanup: File is created during upload, deleted during retention enforcement or explicit delete. Also cleaned from xfer dir after parsing.
  - Guards: Filename is generated server-side with timestamp + microseconds to avoid collision. Device key is validated as alphanumeric.
  - Invariant: Every `Coredump` record with a valid `filename` has a corresponding `.dmp` file on disk (unless manually removed). Disk cleanup is best-effort.
  - Evidence: `app/services/coredump_service.py:86-100` -- filename generation and atomic write.

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: The upload flow (save file, create DB record, enforce retention) runs within the request-scoped session managed by Flask's `teardown_request` handler (`app/__init__.py:109-127`). The session is committed on successful request completion and rolled back on exception.
- Atomic requirements: The `.dmp` file write and DB record creation must be consistent. Since the file is written first (atomic via temp file + rename), and the DB record is created afterward within the same request transaction, a DB failure will leave an orphaned file (acceptable; not a correctness issue). The DB record is the source of truth.
- Retry / idempotency: Sidecar parsing retries up to 3 times in the background thread. No idempotency key needed since uploads generate unique filenames with microsecond timestamps.
- Ordering / concurrency controls: Background parsing thread uses its own DB session (via container singleton pattern) and only performs writes (updating parse_status, parsed_output, parsed_at). All data needed for parsing (coredump_id, device_key, model_code, chip, firmware_version, filename) is passed as arguments to the thread function, so the thread does not need to read the initial record and is not affected by transaction isolation timing. No locks needed -- concurrent uploads for the same device are unlikely and retention enforcement uses DB-level ordering, not in-memory state.
- Evidence: `app/__init__.py:109-127` -- session commit/rollback in teardown. `app/utils/fs.py:8-31` -- atomic_write pattern. `CLAUDE.md` -- singleton session pattern with `container.db_session()` / `reset()`.

---

## 8) Errors & Edge Cases

- Failure: Firmware ZIP not found for parsing
- Surface: Background parsing thread in `CoredumpService`.
- Handling: Log warning, set `parse_status=ERROR`, `parsed_output="Unable to parse coredump: firmware ZIP not found for {model_code} version {version}"`. No retry since the ZIP will not appear by itself.
- Guardrails: The firmware ZIP is uploaded separately. If it has not been uploaded yet, parsing fails gracefully.
- Evidence: `app/services/firmware_service.py:83-93` -- `get_versioned_zip_path()` path construction.

- Failure: ELF file not found in firmware ZIP
- Surface: Background parsing thread.
- Handling: Same as above -- `parse_status=ERROR` with descriptive message.
- Guardrails: `FirmwareService.save_firmware_zip()` validates ELF presence on upload, so this is unlikely but should be handled.
- Evidence: `app/services/firmware_service.py:239-241` -- `.elf` extraction from ZIP.

- Failure: Sidecar unreachable or returns non-200
- Surface: Background parsing thread.
- Handling: Retry up to 3 times with the same parameters. After 3 failures, set `parse_status=ERROR`, `parsed_output="Unable to parse coredump: {last_error}"`.
- Guardrails: Short timeout on sidecar HTTP request (e.g., 30 seconds). Logging on each retry attempt.
- Evidence: Change brief requirement for retry behavior.

- Failure: Sidecar configuration not set (PARSE_SIDECAR_URL or PARSE_SIDECAR_XFER_DIR missing)
- Surface: Upload endpoint (before spawning background thread).
- Handling: The background parsing thread is only spawned when both `PARSE_SIDECAR_URL` and `PARSE_SIDECAR_XFER_DIR` are configured. If either is missing, no thread is spawned and the coredump remains in `parse_status=PENDING`. This communicates "not yet configured for parsing" rather than "parsing failed." The PENDING status is correct because parsing may succeed later if the configuration is added and a re-parse mechanism is implemented.
- Guardrails: The check happens at the call site in the upload endpoint (or the service's `_maybe_start_parsing()` method), not inside the parsing thread itself. This avoids spawning a thread that immediately exits.
- Evidence: `app/config.py:76-85` -- optional Path fields. Section 10 (`plan.md:481`) -- thread is only spawned "when both PARSE_SIDECAR_URL and PARSE_SIDECAR_XFER_DIR are configured."

- Failure: Coredump belongs to a different device (admin API)
- Surface: Admin API endpoints.
- Handling: Return 404 with "Coredump not found" message.
- Guardrails: Service method queries by both `coredump_id` AND `device_id` to ensure ownership.
- Evidence: Change brief: "All coredump endpoints verify coredump belongs to specified device."

- Failure: .dmp file missing from disk during download
- Surface: Admin download endpoint.
- Handling: Return 404 with descriptive error.
- Guardrails: Check file existence before calling `send_file`.
- Evidence: `app/services/firmware_service.py:146-148` -- raises `RecordNotFoundException` when file missing.

- Failure: Concurrent retention enforcement
- Surface: Two simultaneous uploads for the same device.
- Handling: Each request independently counts and enforces the limit. At most, the device may briefly have MAX_COREDUMPS + 1 records between the two transactions. This is acceptable at the project's scale.
- Guardrails: The small fleet size (200 devices) makes true concurrent uploads per device extremely unlikely.
- Evidence: Product brief: "Expected scale: up to 200 devices."

---

## 9) Observability / Telemetry

- Signal: `iot_upload_coredump` operation metric
- Type: counter + histogram (via `record_operation`)
- Trigger: On every `POST /api/iot/coredump` request (already exists).
- Labels / fields: `operation="iot_upload_coredump"`, `status="success"|"error"`
- Consumer: Prometheus/Grafana dashboard.
- Evidence: `app/api/iot.py:418-419` -- existing `metrics_service.record_operation()` call.

- Signal: `coredump_parse` operation metric
- Type: counter + histogram (via `record_operation`)
- Trigger: After each background parse attempt completes (success or final error).
- Labels / fields: `operation="coredump_parse"`, `status="success"|"error"`
- Consumer: Prometheus/Grafana dashboard.
- Evidence: `app/services/metrics_service.py:110-128` -- `record_operation()` method.

- Signal: Structured log lines for parse lifecycle
- Type: structured log (INFO/WARNING/ERROR)
- Trigger: On parse start, retry, success, final failure, and xfer cleanup.
- Labels / fields: `device_key`, `coredump_id`, `filename`, `attempt`, `error`
- Consumer: Log aggregator (stdout in K8s).
- Evidence: `app/services/coredump_service.py:112-119` -- existing logging pattern.

- Signal: Admin coredump endpoint operation metrics
- Type: counter + histogram (via `record_operation`)
- Trigger: On every admin coredump endpoint call.
- Labels / fields: `operation="list_coredumps"|"get_coredump"|"download_coredump"|"delete_coredump"|"delete_all_coredumps"`, `status`
- Consumer: Prometheus/Grafana dashboard.
- Evidence: `app/api/devices.py:71-73` -- existing endpoint metrics pattern.

---

## 10) Background Work & Shutdown

- Worker / job: Background coredump parsing thread
- Trigger cadence: Event-driven -- spawned once per successful coredump upload, only when both `PARSE_SIDECAR_URL` and `PARSE_SIDECAR_XFER_DIR` are configured.
- Responsibilities: Extract `.elf` from firmware ZIP, copy files to xfer dir, call sidecar HTTP endpoint, update DB record, clean up xfer files. Uses its own DB session via the container singleton pattern.
- Shutdown handling: Not registered with `ShutdownCoordinator`. The thread is short-lived (a single HTTP request with timeout + up to 3 retries). Worst case, the process is killed mid-parse and the coredump stays in PENDING status -- no data corruption. The thread is set as a daemon thread so it does not prevent process exit.
- Evidence: `CLAUDE.md` -- "Services need shutdown integration if they: Run background threads." In this case, the thread is ephemeral (seconds, not minutes) and its failure mode is benign (PENDING status remains), so full shutdown integration is not warranted.

---

## 11) Security & Permissions

- Concern: Device authentication on upload endpoint
- Touchpoints: `POST /api/iot/coredump` -- requires device JWT via `/iot` blueprint `before_request` hook.
- Mitigation: Existing device auth middleware validates JWT. When OIDC is disabled (testing), device_key query param is used.
- Residual risk: None beyond existing auth surface.
- Evidence: `app/api/iot.py:42-62` -- `before_request_device_auth()` hook.

- Concern: Admin authentication on coredump management endpoints
- Touchpoints: `GET/DELETE /api/devices/{device_id}/coredumps/*` -- protected by `/api` blueprint `before_request` hook.
- Mitigation: Existing admin auth middleware validates user JWT/session.
- Residual risk: None beyond existing auth surface.
- Evidence: `app/api/__init__.py:25-101` -- `before_request_authentication()` hook on `api_bp`.

- Concern: Path traversal via device key in filesystem paths
- Touchpoints: `CoredumpService` filesystem operations.
- Mitigation: Existing alphanumeric validation of device key (`device_key.isalnum()`). Device keys are server-generated 8-char alphanumeric strings.
- Residual risk: Negligible -- defense-in-depth validation is already in place.
- Evidence: `app/services/coredump_service.py:82-83` -- existing validation.

---

## 12) UX / UI Impact

- Entry point: Device detail page in the frontend
- Change: The frontend will need a new coredumps tab/section that lists coredumps for a device, shows parsed output, and allows download/delete actions.
- User interaction: Admin views coredumps for a device, sees parse status (PENDING/PARSED/ERROR), reads parsed crash analysis, downloads raw dumps, and deletes old dumps.
- Dependencies: Frontend depends on the new admin API endpoints documented in section 4. A `docs/features/coredump_parsing/frontend_impact.md` document should be created (out of scope for this plan, but noted).
- Evidence: `CLAUDE.md` -- "Document frontend impact in docs/features/<FEATURE>/frontend_impact.md when the frontend dev needs update instructions."

---

## 13) Deterministic Test Plan

- Surface: CoredumpService -- `save_coredump()` (refactored)
- Scenarios:
  - Given a configured service with DB, When saving a valid coredump, Then a `.dmp` file is written, a DB record is created with parse_status=PENDING, and the filename is returned.
  - Given a configured service, When saving a coredump and MAX_COREDUMPS is exceeded, Then the oldest coredump record and its file are deleted.
  - Given a configured service, When saving a coredump with empty content, Then ValidationException is raised.
  - Given a configured service, When saving a coredump exceeding 1 MB, Then ValidationException is raised.
  - Given a service with coredumps_dir=None, When saving, Then InvalidOperationException is raised.
  - Given a configured service, When saving a coredump, Then no JSON sidecar file is created (verify removal of old behavior).
- Fixtures / hooks: `app`, `session`, `container` fixtures. Factory fixture `make_device_model` and `make_device` for creating prerequisite records. `tmp_path` for filesystem isolation.
- Gaps: None.
- Evidence: `tests/services/test_coredump_service.py` -- existing test file to refactor. `tests/conftest.py:270-310` -- `make_device_model` and `make_device` fixtures.

- Surface: CoredumpService -- `parse_coredump()` (new)
- Scenarios:
  - Given a PENDING coredump record and a configured sidecar, When parsing succeeds on first try, Then parse_status=PARSED, parsed_output is set, parsed_at is set, xfer files are cleaned up.
  - Given a PENDING coredump, When sidecar returns error 3 times, Then parse_status=ERROR, parsed_output contains "Unable to parse coredump: {error}".
  - Given a PENDING coredump, When sidecar fails twice then succeeds, Then parse_status=PARSED (retry works).
  - Given a PENDING coredump, When firmware ZIP is not found, Then parse_status=ERROR immediately (no retry).
  - Given a PENDING coredump, When PARSE_SIDECAR_URL is not configured, Then parsing is skipped (status stays PENDING).
  - Given a PENDING coredump, When xfer dir cleanup fails, Then parse completes normally (best-effort cleanup).
- Fixtures / hooks: `unittest.mock.patch` for `requests.get` (mock sidecar HTTP calls). `tmp_path` for xfer dir and coredumps dir. Firmware ZIP fixtures created with `zipfile` module.
- Gaps: None.
- Evidence: `tests/conftest.py:423-457` -- `create_test_firmware` helper for building firmware binaries.

- Surface: CoredumpService -- CRUD methods (new: `list_coredumps`, `get_coredump`, `get_coredump_path`, `delete_coredump`, `delete_all_coredumps`)
- Scenarios:
  - Given a device with 3 coredumps, When listing coredumps, Then all 3 are returned ordered by uploaded_at descending.
  - Given a device with coredumps, When getting a specific coredump that belongs to the device, Then it is returned with all fields.
  - Given a coredump belonging to device A, When getting it with device B's ID, Then RecordNotFoundException is raised.
  - Given a coredump, When getting its file path, Then the correct COREDUMPS_DIR/{device_key}/{filename} path is returned.
  - Given a coredump with a file on disk, When deleting it, Then the DB record and file are both removed.
  - Given a coredump whose file is already missing from disk, When deleting it, Then the DB record is removed and no error is raised (best-effort file cleanup).
  - Given a device with 5 coredumps, When deleting all, Then all 5 DB records and their files are removed.
- Fixtures / hooks: Same as above.
- Gaps: None.
- Evidence: `app/services/device_service.py:39-61` -- service constructor pattern with DB.

- Surface: Admin API -- `GET /api/devices/{device_id}/coredumps`
- Scenarios:
  - Given a device with coredumps, When GET list, Then 200 with coredump summaries (no parsed_output).
  - Given a device with no coredumps, When GET list, Then 200 with empty array.
  - Given an invalid device_id, When GET list, Then 404.
- Fixtures / hooks: `client`, `app`, `container`. Use `make_device` and directly create coredump records.
- Gaps: None.
- Evidence: `tests/api/test_iot.py:14-37` -- `create_test_device` helper pattern.

- Surface: Admin API -- `GET /api/devices/{device_id}/coredumps/{coredump_id}`
- Scenarios:
  - Given a coredump belonging to the device, When GET detail, Then 200 with full detail including parsed_output.
  - Given a coredump belonging to another device, When GET detail, Then 404.
  - Given a non-existent coredump_id, When GET detail, Then 404.
- Fixtures / hooks: Same as above.
- Gaps: None.
- Evidence: `tests/api/test_devices.py` -- existing device endpoint tests.

- Surface: Admin API -- `GET /api/devices/{device_id}/coredumps/{coredump_id}/download`
- Scenarios:
  - Given a coredump with a file on disk, When GET download, Then 200 with binary content and correct content-type.
  - Given a coredump whose file is missing, When GET download, Then 404.
  - Given a coredump belonging to another device, When GET download, Then 404.
- Fixtures / hooks: Same as above, plus writing test files to coredumps_dir.
- Gaps: None.
- Evidence: `tests/api/test_iot.py:92-158` -- firmware download test pattern.

- Surface: Admin API -- `DELETE /api/devices/{device_id}/coredumps/{coredump_id}`
- Scenarios:
  - Given a coredump belonging to the device, When DELETE, Then 204, DB record removed, file removed.
  - Given a coredump belonging to another device, When DELETE, Then 404.
- Fixtures / hooks: Same as above.
- Gaps: None.
- Evidence: `tests/api/test_devices.py` -- device delete test pattern.

- Surface: Admin API -- `DELETE /api/devices/{device_id}/coredumps`
- Scenarios:
  - Given a device with coredumps, When DELETE all, Then 204, all records and files removed.
  - Given a device with no coredumps, When DELETE all, Then 204 (no-op, idempotent).
  - Given an invalid device_id, When DELETE all, Then 404.
- Fixtures / hooks: Same as above.
- Gaps: None.

- Surface: IoT upload endpoint (refactored) -- `POST /api/iot/coredump`
- Scenarios:
  - Given a valid device, When uploading a coredump, Then 201 with filename, DB record exists with parse_status=PENDING, .dmp file on disk.
  - Given a valid device and upload, Then no .json sidecar file is created (regression check for old behavior removal).
- Fixtures / hooks: Existing `test_iot.py` fixtures.
- Gaps: Background parsing is not tested in API tests (it runs asynchronously). Parsing logic is covered in service tests.
- Evidence: `tests/api/test_iot.py:332-458` -- existing upload tests to update.

---

## 14) Implementation Slices

- Slice: Configuration and Data Model
- Goal: Add new config vars and create the Coredump model + Device relationship so the DB schema is ready.
- Touches: `app/config.py`, `app/models/coredump.py` (new), `app/models/device.py`, `app/models/__init__.py`, `tests/conftest.py` (add new config fields to test settings).
- Dependencies: None -- this is the foundation slice.

- Slice: CoredumpService Refactor -- Core CRUD
- Goal: Refactor the service to create DB records on upload, enforce retention, and provide CRUD methods. Remove JSON sidecar writing.
- Touches: `app/services/coredump_service.py`, `app/services/container.py`, `tests/services/test_coredump_service.py`.
- Dependencies: Slice 1 (model exists).

- Slice: Upload Endpoint Refactor
- Goal: Update `POST /api/iot/coredump` to pass device_id and trigger DB record creation. Update IoT API tests.
- Touches: `app/api/iot.py`, `tests/api/test_iot.py`.
- Dependencies: Slice 2 (service refactored).

- Slice: Background Parsing
- Goal: Implement background parsing thread with sidecar HTTP call, retries, and xfer cleanup. Add parsing tests.
- Touches: `app/services/coredump_service.py`, `tests/services/test_coredump_service.py`.
- Dependencies: Slice 2 (CRUD methods exist).

- Slice: Admin API Endpoints and Schemas
- Goal: Implement admin coredump endpoints with schemas, blueprint registration, and container wiring. Add API tests.
- Touches: `app/schemas/coredump.py` (new), `app/api/coredumps.py` (new), `app/api/__init__.py`, `app/__init__.py`, `tests/api/test_coredumps.py` (new).
- Dependencies: Slice 2 (service CRUD methods exist).

---

## 15) Risks & Open Questions

- Risk: Background parsing thread fails silently and coredumps stay in PENDING forever.
- Impact: Admin sees coredumps stuck in PENDING with no parsed output.
- Mitigation: Comprehensive logging in the parsing thread. Future enhancement could add a CLI command to re-trigger parsing for PENDING/ERROR coredumps.

- Risk: Sidecar container is not running or misconfigured, causing all parses to fail.
- Impact: All coredumps end up in ERROR state.
- Mitigation: `coredump_parse` metric with `status=error` label enables alerting. Parsing is gracefully degraded -- upload still succeeds and raw dumps are available for download.

- Risk: Orphaned files on disk if DB record is deleted but file deletion fails.
- Impact: Wasted disk space. At 20 coredumps * 1 MB * 200 devices = 4 GB max, this is manageable.
- Mitigation: File deletion is best-effort with logging. Future cleanup script could scan for orphaned files.

- Risk: The `Device.coredumps` relationship with default lazy loading could cause N+1 queries in admin coredump list endpoints.
- Impact: Slightly slower queries in coredump-specific endpoints.
- Mitigation: Use `lazy="select"` (default) on the relationship to avoid polluting unrelated device queries. Apply explicit `selectinload(Device.coredumps)` in the admin coredump endpoints where the relationship is actually needed.

All questions have been resolved autonomously based on codebase research. No blocking open questions remain.

---

## 16) Confidence

Confidence: High -- The change is well-scoped, follows established patterns in the codebase, and the requirements are unambiguous. All architectural decisions are grounded in existing code evidence.
