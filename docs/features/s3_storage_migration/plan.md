# Plan: Migrate Firmware and Coredump Storage to S3

## 0) Research Log & Findings

### Areas Researched

**FirmwareService** (`app/services/firmware_service.py`): The current service is filesystem-only. It stores firmware two ways: a legacy flat binary at `ASSETS_DIR/firmware-{model_code}.bin` and versioned ZIPs at `ASSETS_DIR/{model_code}/firmware-{version}.zip`. The service receives `assets_dir: Path` via constructor. It uses `atomic_write()` for filesystem writes and `shutil.rmtree()` for directory deletion. ZIP validation already extracts individual artifacts (`.bin`, `.elf`, `.map`, `sdkconfig`, `version.json`) and verifies them -- this validation logic is reusable and the exploded-to-S3 approach maps cleanly onto it.

**CoredumpService** (`app/services/coredump_service.py`): A singleton service that stores `.dmp` files under `COREDUMPS_DIR/{device_key}/` with timestamp-based filenames (e.g., `coredump_20260211T143000_123456Z.dmp`). It uses a container-based session pattern for background thread DB access. The parsing thread currently reads the `.dmp` from disk and extracts the `.elf` from a firmware ZIP on disk, copies both to `PARSE_SIDECAR_XFER_DIR`, and calls the sidecar HTTP endpoint. Retention is per-device via `MAX_COREDUMPS`.

**S3Service** (`app/services/s3_service.py`): Already provides `upload_file`, `download_file`, `delete_file`, `file_exists`, `copy_file`, `get_file_metadata`, and `ensure_bucket_exists`. It does NOT have a `list_objects` or `delete_prefix` method -- these will be needed for firmware version pruning and bulk deletion.

**DeviceModel** (`app/models/device_model.py`): Only stores `firmware_version` as a single string column (the current version). There is no history of stored versions. For MAX_FIRMWARES retention, we need a new `firmware_versions` table to track all stored versions per model so we can know what to prune.

**CoreDump model** (`app/models/coredump.py`): Has a `filename` column currently storing the timestamp-based name. After migration, this column's semantics change to store the S3 key suffix (`{db_id}.dmp`), or we can derive the S3 key entirely from `id` and `device_key` and drop the filename column. Since the S3 key is deterministic from `device_key` and `id`, we can eliminate `filename` and derive the key as `coredumps/{device_key}/{id}.dmp`.

**Container wiring** (`app/services/container.py`): FirmwareService is a Singleton receiving `assets_dir` from `app_config`. CoredumpService is a Singleton receiving `coredumps_dir` from `app_config`. Neither currently depends on S3Service. The S3Service is a Factory provider.

**AppSettings** (`app/app_config.py`): Currently has `assets_dir: Path | None`, `coredumps_dir: Path | None`, and `max_coredumps: int`. ASSETS_DIR and COREDUMPS_DIR will be removed; MAX_FIRMWARES will be added.

**Test Infrastructure** (`tests/conftest.py`, `tests/conftest_infrastructure.py`): Tests use `tmp_path` for `assets_dir` and `coredumps_dir`. S3 is already available in tests (the conftest verifies S3 connectivity at session start). Tests for FirmwareService are pure filesystem; tests for CoredumpService use filesystem + DB.

**Existing S3 usage pattern** (`app/services/cas_image_service.py`, `app/api/cas.py`): CAS images use S3 with the `cas/` prefix. The S3Service is injected as a Factory. This confirms the single-bucket, prefix-separation pattern.

### Conflicts Identified and Resolved

1. **No firmware version history table**: The current schema only tracks the latest firmware version on `device_models.firmware_version`. For MAX_FIRMWARES retention, we need to know what versions are stored. **Resolution**: Create a `firmware_versions` table to track each stored version per model, used for retention decisions and version listing.

2. **Coredump filename column**: Currently stores a timestamp-based name. After migration, the S3 key is derived from `device_key` + `id`. **Resolution**: Remove the `filename` column from the coredumps table via Alembic migration. The S3 key is deterministic: `coredumps/{device_key}/{id}.dmp`.

3. **S3Service lacks list/prefix-delete**: Needed for firmware retention pruning and model deletion. **Resolution**: Add `list_objects(prefix)` and `delete_prefix(prefix)` methods to S3Service.

4. **FirmwareService is a Singleton but needs both S3Service and DB access**: For MAX_FIRMWARES retention, FirmwareService needs to query the `firmware_versions` table to determine which versions to prune, and needs to check coredumps for `parse_status=PENDING` references. **Resolution**: Change FirmwareService from Singleton to Factory (it will need a DB session for firmware_versions and coredump queries). Alternatively, keep it Singleton and use the container pattern like CoredumpService. Since it interacts with the DB primarily during upload/delete (request-scoped operations), making it a Factory with a `db` session is cleaner and aligns with the project's patterns.

---

## 1) Intent & Scope

**User intent**

Migrate all persistent binary storage (firmware artifacts and coredump dumps) from local filesystem directories to S3-compatible object storage, eliminating the `ASSETS_DIR` and `COREDUMPS_DIR` environment variables. Firmware ZIPs are exploded into individual S3 objects rather than stored as ZIP bundles. A new `MAX_FIRMWARES` environment variable controls per-model version retention with safety guards against pruning firmware still needed by unparsed coredumps. Coredumps switch from timestamp-based filenames to database-ID-based S3 keys. A CLI migration command enables one-time cutover from filesystem to S3.

**Prompt quotes**

- "No ZIP wrapper stored in S3 -- ZIP is received on upload, validated, then exploded into individual objects"
- "Legacy flat binary concept (`firmware-{model_code}.bin`) eliminated entirely"
- "Coredumps stored in S3 as `coredumps/{device_key}/{db_id}.dmp` using the database primary key"
- "S3 golden rules enforced: creates flush+upload+commit, deletes commit+best-effort-S3-delete"
- "CLI migration command provided to move existing filesystem data to S3"

**In scope**

- Refactor FirmwareService to use S3Service for all storage operations
- Refactor CoredumpService to use S3Service for all storage operations
- Create `firmware_versions` table and Alembic migration
- Two-phase removal of `filename` column from coredumps: make nullable (migration 006), then drop (migration 007) after CLI migration runs
- Add `MAX_FIRMWARES` environment variable with retention logic
- Firmware retention guard against unparsed coredumps
- Add `list_objects` and `delete_prefix` methods to S3Service
- CLI migration command for filesystem-to-S3 cutover
- Remove `ASSETS_DIR` and `COREDUMPS_DIR` from config
- Remove `atomic_write` usage from firmware and coredump paths
- Update all existing tests to use S3
- Update coredump parsing thread to download from S3

**Out of scope**

- Changes to the CAS image system (already on S3)
- Changes to the PARSE_SIDECAR_XFER_DIR (remains filesystem-based)
- Frontend changes (binary download endpoints remain the same from the caller's perspective)
- Changes to the rotation system or Keycloak integration

**Assumptions / constraints**

- S3 service is already configured and available in all environments
- The migration CLI command runs during brief planned downtime (no live migration needed)
- The single S3 bucket (`iot-support-attachments`) is shared across `firmware/`, `coredumps/`, and `cas/` prefixes
- FirmwareService becomes a Factory service (request-scoped) to enable DB access for version tracking and retention. CoredumpService (Singleton) no longer depends on FirmwareService; it uses S3Service directly for `.elf` downloads in the parsing thread

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Firmware artifacts stored as individual S3 objects under `firmware/{model_code}/{version}/` (firmware.bin, firmware.elf, firmware.map, sdkconfig, version.json)
- [ ] No ZIP wrapper stored in S3 -- ZIP is received on upload, validated, then exploded into individual objects
- [ ] Legacy flat binary concept (`firmware-{model_code}.bin`) eliminated entirely
- [ ] `MAX_FIRMWARES` environment variable added (default 5) controlling per-model firmware version retention
- [ ] Firmware retention guards against pruning versions referenced by unparsed coredumps (parse_status=PENDING)
- [ ] Coredumps stored in S3 as `coredumps/{device_key}/{db_id}.dmp` using the database primary key
- [ ] Timestamp-based coredump filename generation eliminated
- [ ] `ASSETS_DIR` and `COREDUMPS_DIR` environment variables removed
- [ ] `PARSE_SIDECAR_XFER_DIR` remains filesystem-based (sidecar handoff, not persistent storage)
- [ ] Coredump parsing thread downloads .dmp and .elf from S3, writes to xfer directory for sidecar
- [ ] S3 golden rules enforced: creates flush+upload+commit, deletes commit+best-effort-S3-delete
- [ ] `atomic_write` utility usage removed from firmware and coredump paths (S3 PUTs are inherently atomic)
- [ ] Single bucket with prefix separation: `firmware/`, `coredumps/`, `cas/` (existing)
- [ ] CLI migration command provided to move existing filesystem data to S3
- [ ] All existing firmware service tests updated for S3
- [ ] All existing coredump service tests updated for S3
- [ ] All existing API tests updated for S3
- [ ] FirmwareService refactored to use S3Service instead of filesystem operations
- [ ] CoredumpService refactored to use S3Service instead of filesystem operations
- [ ] Alembic migration 006 for schema changes (create firmware_versions table, make coredumps.filename nullable)
- [ ] Alembic migration 007 to drop coredumps.filename column (after CLI migrate-to-s3 has run)

---

## 2) Affected Areas & File Map

- Area: `app/services/s3_service.py` -- `S3Service`
- Why: Add `list_objects(prefix)` and `delete_prefix(prefix)` methods needed for firmware version management and model deletion.
- Evidence: `app/services/s3_service.py:16-262` -- existing service has upload/download/delete/copy/exists but no prefix listing or batch deletion.

- Area: `app/models/firmware_version.py` (new)
- Why: New model to track stored firmware versions per device model, enabling MAX_FIRMWARES retention and version enumeration.
- Evidence: `app/models/device_model.py:37` -- only `firmware_version: Mapped[str | None]` exists (single current version, no history).

- Area: `app/models/coredump.py` -- `CoreDump`
- Why: Remove the `filename` column. S3 key is derived deterministically from `device_key` and `id`.
- Evidence: `app/models/coredump.py:48` -- `filename: Mapped[str] = mapped_column(String(255), nullable=False)`.

- Area: `app/services/firmware_service.py` -- `FirmwareService`
- Why: Complete rewrite from filesystem to S3. Change from Singleton to Factory (needs DB session for firmware_versions tracking). Eliminate legacy flat binary, ZIP storage, and atomic_write usage. Add MAX_FIRMWARES retention with coredump safety guard. Artifact naming in S3 uses generic names (`firmware.bin`, `firmware.elf`, `firmware.map`, `sdkconfig`, `version.json`) since the S3 key path already encodes `model_code` and `version`.
- Evidence: `app/services/firmware_service.py:51-344` -- all methods use `self.assets_dir`, `Path` operations, `atomic_write`.

- Area: `app/services/coredump_service.py` -- `CoredumpService`
- Why: Replace filesystem operations with S3 uploads/downloads. Eliminate timestamp-based filenames. Update parsing thread to download from S3. The parsing thread downloads the `.elf` directly via S3Service (not through FirmwareService) since FirmwareService becomes a Factory and cannot be held by the Singleton CoredumpService. The S3 key for the `.elf` is deterministic: `firmware/{model_code}/{firmware_version}/firmware.elf`.
- Evidence: `app/services/coredump_service.py:104-192` (`save_coredump` uses `atomic_write`, timestamp filename), `app/services/coredump_service.py:278-405` (parsing thread reads from filesystem).

- Area: `app/services/device_model_service.py` -- `DeviceModelService`
- Why: Update `upload_firmware` to pass DB session context for firmware_versions tracking. Update `delete_device_model` for S3-based firmware deletion.
- Evidence: `app/services/device_model_service.py:205-255` (`upload_firmware` calls `firmware_service.save_firmware_zip`), `app/services/device_model_service.py:175-203` (`delete_device_model` calls `firmware_service.delete_firmware`).

- Area: `app/app_config.py` -- `AppEnvironment`, `AppSettings`
- Why: Remove `ASSETS_DIR` and `COREDUMPS_DIR` env vars and settings fields. Add `MAX_FIRMWARES` env var and settings field.
- Evidence: `app/app_config.py:35-37` (`ASSETS_DIR`, `COREDUMPS_DIR`), `app/app_config.py:83-85` (`assets_dir`, `coredumps_dir`).

- Area: `app/services/container.py` -- `ServiceContainer`
- Why: Change FirmwareService from Singleton to Factory with `db_session` and `s3_service`. Update CoredumpService to inject `s3_service` directly (instead of `coredumps_dir`) so the parsing thread can download `.dmp` and `.elf` files from S3 without going through FirmwareService. Remove `firmware_service` from CoredumpService's constructor dependencies since FirmwareService is now a Factory and cannot be held by a Singleton. Remove `assets_dir` and `coredumps_dir` from provider arguments.
- Evidence: `app/services/container.py:161-173` (FirmwareService Singleton with `assets_dir`, CoredumpService Singleton with `coredumps_dir`).

- Area: `app/api/device_models.py` -- firmware upload/download endpoints
- Why: Adapt download endpoint to serve binary from S3 BytesIO stream (already returns BytesIO, minor changes).
- Evidence: `app/api/device_models.py:248-280` (`download_firmware` uses `send_file` with BytesIO).

- Area: `app/api/coredumps.py` -- coredump download endpoint
- Why: Change from `send_file(path)` to `send_file(BytesIO)` since coredumps are now in S3.
- Evidence: `app/api/coredumps.py:101-140` (`download_coredump` uses `send_file` with filesystem path).

- Area: `app/api/iot.py` -- device firmware download and coredump upload
- Why: Update firmware download to use S3-based stream. Coredump upload response no longer returns `filename`.
- Evidence: `app/api/iot.py:173-224` (`get_firmware`), `app/api/iot.py:353-436` (`upload_coredump` returns `filename`).

- Area: `app/schemas/coredump.py` -- coredump response schemas
- Why: Remove `filename` field from all coredump schemas.
- Evidence: `app/schemas/coredump.py:15` -- `filename: str = Field(...)`.

- Area: `app/cli.py` and `app/startup.py` -- CLI migration command
- Why: Add `migrate-to-s3` CLI command for one-time filesystem-to-S3 data migration.
- Evidence: `app/cli.py:19-179` (existing CLI structure), `app/startup.py:128-162` (`register_cli_commands`).

- Area: `alembic/versions/006_*.py` (new)
- Why: Migration to create `firmware_versions` table and make `filename` column nullable on `coredumps` (but NOT drop it yet -- the CLI migration needs it to match files to records).
- Evidence: `alembic/versions/005_create_coredumps_table.py` -- current latest migration is 005.

- Area: `alembic/versions/007_*.py` (new)
- Why: Migration to drop the `filename` column from `coredumps` after the CLI `migrate-to-s3` command has been run in all environments. This must run AFTER the data migration is complete.
- Evidence: Sequencing requirement from migration 006 and CLI `migrate-to-s3`.

- Area: `app/utils/fs.py` -- `atomic_write`
- Why: No longer imported by firmware or coredump paths. May remain for other uses, but imports are removed from both services.
- Evidence: `app/utils/fs.py:8-31` -- the utility itself, `app/services/firmware_service.py:6` and `app/services/coredump_service.py:22` -- import sites.

- Area: `tests/services/test_firmware_service.py`
- Why: Complete rewrite for S3 operations instead of filesystem.
- Evidence: `tests/services/test_firmware_service.py:1-388` -- all tests use `tmp_path` and filesystem assertions.

- Area: `tests/services/test_coredump_service.py`
- Why: Complete rewrite for S3 operations instead of filesystem.
- Evidence: `tests/services/test_coredump_service.py:1-786` -- all tests use filesystem paths and `coredumps_dir`.

- Area: `tests/api/test_coredumps.py`
- Why: Update test helpers and assertions for S3-based coredump storage.
- Evidence: `tests/api/test_coredumps.py:1-340` -- helpers write files to `coredumps_dir`.

- Area: `tests/api/test_device_models.py`
- Why: Firmware upload tests may need S3 assertions instead of filesystem.
- Evidence: `tests/api/test_device_models.py:173-290` -- firmware upload tests.

- Area: `tests/conftest.py`
- Why: Remove `assets_dir` and `coredumps_dir` from `test_app_settings`. Add `max_firmwares` setting.
- Evidence: `tests/conftest.py:63-110` -- `test_app_settings` fixture creates `tmp_path` directories.

- Area: `app/startup.py`
- Why: Remove `container.coredump_service().container = container` if CoredumpService no longer needs it (it still does for background thread DB access).
- Evidence: `app/startup.py:62-63` -- post-init container assignment.

---

## 3) Data Model / Contracts

- Entity / contract: `firmware_versions` table (new)
- Shape:
  ```
  firmware_versions
  ├── id: int (PK, autoincrement)
  ├── device_model_id: int (FK -> device_models.id, CASCADE)
  ├── version: str(50) (firmware version string)
  ├── uploaded_at: datetime
  ├── created_at: datetime (server_default=now())
  └── UNIQUE(device_model_id, version)
  ```
- Refactor strategy: New table, no backwards compatibility needed. DeviceModel.firmware_version continues to represent the "current/active" version.
- Evidence: `app/models/device_model.py:37` -- only `firmware_version` exists today; no version history.

- Entity / contract: `coredumps` table (changed)
- Shape:
  ```
  coredumps (existing, modified)
  ├── ... (all existing columns)
  ├── Migration 006: ALTER COLUMN filename SET NULLABLE (keep column for CLI migration lookup)
  └── Migration 007: DROP COLUMN filename (after CLI migrate-to-s3 has run)
  ```
  S3 key derived as: `coredumps/{device.key}/{coredump.id}.dmp`
- Refactor strategy: Two-phase column removal. Migration 006 makes `filename` nullable so new coredump records (created by the S3-based service) can omit it. The CLI `migrate-to-s3` uses the `filename` column to match filesystem files to DB records. After the CLI has run in all environments, migration 007 drops the column.
- Evidence: `app/models/coredump.py:48` -- `filename` column.

- Entity / contract: `AppEnvironment` / `AppSettings` (changed)
- Shape:
  ```
  Remove: ASSETS_DIR, COREDUMPS_DIR (and assets_dir, coredumps_dir)
  Add:    MAX_FIRMWARES: int = 5 (and max_firmwares: int = 5)
  ```
- Refactor strategy: Direct removal and addition. No backwards compatibility.
- Evidence: `app/app_config.py:35-37` (env vars), `app/app_config.py:83-85` (settings fields).

- Entity / contract: Coredump upload API response (changed)
- Shape:
  ```json
  // Before: {"status": "ok", "filename": "coredump_20260211T...Z.dmp"}
  // After:  {"status": "ok", "coredump_id": 42}
  ```
- Refactor strategy: Replace `filename` with `coredump_id` in response. No backwards compatibility needed (BFF pattern).
- Evidence: `app/api/iot.py:428` -- `return {"status": "ok", "filename": filename}, 201`.

- Entity / contract: Coredump response schemas (changed)
- Shape: Remove `filename` field from `CoredumpBaseSchema`, `CoredumpSummarySchema`, `CoredumpDetailSchema`.
- Refactor strategy: Direct removal.
- Evidence: `app/schemas/coredump.py:15` -- `filename: str = Field(...)`.

---

## 4) API / Integration Surface

- Surface: `POST /api/device-models/{model_id}/firmware`
- Inputs: Multipart file upload or raw body (ZIP or raw .bin -- raw .bin support will be removed since all uploads must now be ZIPs)
- Outputs: `DeviceModelFirmwareResponseSchema` (unchanged: `{id, code, firmware_version}`). Side effects: individual artifacts renamed to generic names and uploaded to S3 under `firmware/{model_code}/{version}/` (e.g., `firmware.bin`, `firmware.elf`, `firmware.map`, `sdkconfig`, `version.json`), firmware_versions DB record created, retention pruning applied, MQTT notification sent.
- Errors: 400 (invalid ZIP, missing files, non-ZIP content), 404 (model not found). S3 upload failure causes transaction rollback (golden rule).
- Evidence: `app/api/device_models.py:200-245`, `app/services/device_model_service.py:205-255`.

- Surface: `GET /api/device-models/{model_id}/firmware`
- Inputs: model_id path parameter
- Outputs: Binary stream (firmware .bin) downloaded from S3 at `firmware/{model_code}/{version}/firmware.bin`. (Note: the artifact is now stored as `firmware.bin` rather than `{model_code}.bin` -- a simplification since model_code is in the path.)
- Errors: 404 (model not found, firmware not uploaded, S3 key missing)
- Evidence: `app/api/device_models.py:248-280`.

- Surface: `GET /iot/firmware`
- Inputs: Device auth context (JWT)
- Outputs: Binary stream (firmware .bin) from S3
- Errors: 401 (auth failure), 404 (firmware not found)
- Evidence: `app/api/iot.py:173-224`.

- Surface: `POST /iot/coredump`
- Inputs: Raw binary body, `chip` and `firmware_version` query params
- Outputs: `{"status": "ok", "coredump_id": <int>}` (changed from `filename` to `coredump_id`)
- Errors: 400 (missing params, empty content, too large), 401 (auth failure). S3 upload failure causes transaction rollback.
- Evidence: `app/api/iot.py:353-436`.

- Surface: `GET /api/devices/{device_id}/coredumps/{coredump_id}/download`
- Inputs: device_id, coredump_id path parameters
- Outputs: Binary stream from S3 via `send_file(BytesIO)`
- Errors: 404 (not found, wrong device, S3 key missing)
- Evidence: `app/api/coredumps.py:101-140`.

- Surface: `DELETE /api/devices/{device_id}/coredumps/{coredump_id}`
- Inputs: device_id, coredump_id path parameters
- Outputs: 204 No Content. Side effects: DB record deleted (committed), then best-effort S3 delete.
- Errors: 404 (not found)
- Evidence: `app/api/coredumps.py:143-176`.

- Surface: `DELETE /api/devices/{device_id}/coredumps` (delete all)
- Inputs: device_id path parameter
- Outputs: 204 No Content. Side effects: All DB records deleted, then best-effort S3 deletes.
- Errors: 404 (device not found)
- Evidence: `app/api/coredumps.py:179-209`.

- Surface: CLI `migrate-to-s3` (new)
- Inputs: None (reads ASSETS_DIR and COREDUMPS_DIR from environment for source, S3 config for destination)
- Outputs: Progress logging, summary of migrated files
- Errors: Exits non-zero on S3 connectivity failure or critical migration error
- Evidence: `app/cli.py:19-179` -- existing CLI structure for reference.

---

## 5) Algorithms & State Machines

- Flow: Firmware Upload (S3)
- Steps:
  1. Receive ZIP content, validate ZIP structure (required files, version.json fields)
  2. Extract `.bin` from ZIP, parse ESP32 AppInfo to get version string
  3. Flush device_model update (`firmware_version = version`) and create `firmware_versions` record
  4. Rename artifacts from model-specific names (e.g., `{model_code}.bin`) to generic names and upload each to S3: `firmware/{model_code}/{version}/firmware.bin`, `firmware/{model_code}/{version}/firmware.elf`, `firmware/{model_code}/{version}/firmware.map`, `firmware/{model_code}/{version}/sdkconfig`, `firmware/{model_code}/{version}/version.json`. Generic names are used because the S3 path already encodes `model_code`.
  5. If any S3 upload fails, raise exception (transaction rolls back via golden rule)
  6. Run retention: query `firmware_versions` for this model ordered by `uploaded_at` desc, identify versions beyond MAX_FIRMWARES limit, filter out versions referenced by coredumps with `parse_status=PENDING`, delete excess firmware_version records and S3 prefixes (best-effort)
  7. Publish MQTT firmware notification for each device of this model
- States / transitions: None
- Hotspots: Step 4 involves 5 sequential S3 PUT operations per upload. For the expected scale (up to 200 devices, infrequent firmware uploads), this is acceptable.
- Evidence: `app/services/firmware_service.py:181-266` (current save_firmware_zip), `app/services/device_model_service.py:205-255` (upload_firmware).

- Flow: Firmware Retention Pruning
- Steps:
  1. Query all `firmware_versions` for the model, ordered `uploaded_at` desc
  2. Keep the newest MAX_FIRMWARES versions
  3. For each excess version: query coredumps where `firmware_version = excess_version` and `parse_status = 'PENDING'`; if any exist, skip this version (preserve it)
  4. Delete the firmware_versions DB record for pruneable versions, flush
  5. Best-effort delete S3 prefix `firmware/{model_code}/{version}/`
- States / transitions: None
- Hotspots: The coredump cross-reference query runs once per excess version. With MAX_FIRMWARES=5 and typically 1-2 excess versions per upload, this is negligible.
- Evidence: Change brief lines 9-10 (retention requirement).

- Flow: Coredump Upload (S3)
- Steps:
  1. Validate content (non-empty, under 1MB, valid device key)
  2. Create CoreDump DB record with `parse_status=PENDING`, flush to get `id`. **NOTE:** This is an intentional order change from the current filesystem implementation, which writes the file first then flushes the DB record. The S3 golden rule requires: flush DB first (to obtain the `id` needed for the S3 key), then upload to S3, then let the request session commit on teardown.
  3. Upload to S3: `coredumps/{device_key}/{id}.dmp`
  4. If S3 upload fails, raise exception (transaction rolls back, DB record never committed)
  5. Enforce per-device retention (delete oldest beyond MAX_COREDUMPS: delete DB record, then best-effort S3 delete)
  6. Return `coredump_id`
- States / transitions: None
- Hotspots: Single S3 PUT per upload. Retention deletes are best-effort.
- Evidence: `app/services/coredump_service.py:104-192` (current save_coredump).

- Flow: Coredump Parsing Thread (S3-aware)
- Steps:
  1. Sleep 0.5s for request session to commit
  2. Download `.dmp` from S3 via `self.s3_service`: key `coredumps/{device_key}/{coredump_id}.dmp`
  3. Download `.elf` from S3 via `self.s3_service`: key `firmware/{model_code}/{firmware_version}/firmware.elf`. **NOTE:** The parsing thread uses S3Service directly (not FirmwareService) because FirmwareService is a Factory and CoredumpService is a Singleton -- the parsing thread cannot hold a valid FirmwareService reference. The S3 key is deterministic so no DB query is needed.
  4. Write both files to `PARSE_SIDECAR_XFER_DIR` (using `{model_code}.elf` as the local filename for the sidecar, matching the sidecar's expected naming)
  5. Call sidecar HTTP endpoint with retries
  6. Update DB record with parse result
  7. Clean up xfer directory files
- States / transitions: None
- Hotspots: Two S3 downloads per parse. Acceptable for the expected coredump volume.
- Evidence: `app/services/coredump_service.py:278-405` (current parsing thread).

- Flow: CLI migrate-to-s3
- Steps:
  1. Verify S3 connectivity (ensure_bucket_exists)
  2. If ASSETS_DIR is set and exists: iterate model directories, for each versioned ZIP extract artifacts, rename to generic names (`firmware.bin`, `firmware.elf`, `firmware.map`, `sdkconfig`, `version.json`), and upload to S3 under `firmware/{model_code}/{version}/`; create firmware_versions DB records; for legacy .bin files, skip (they are eliminated)
  3. If COREDUMPS_DIR is set and exists: iterate device_key directories, for each `.dmp` file look up the corresponding CoreDump DB record by matching on device_id and the `filename` column (which is still present -- made nullable by migration 006 but not yet dropped), upload to S3 as `coredumps/{device_key}/{db_id}.dmp`
  4. After all uploads succeed, set `filename = NULL` on migrated coredump records to signal completion
  5. Print summary of migrated files
  6. **Deployment note:** After running `migrate-to-s3` in all environments, apply Alembic migration 007 to drop the `filename` column entirely.
- States / transitions: None
- Hotspots: Migration is a one-time operation. For large firmware collections, the sequential upload may take time but is acceptable.
- Evidence: Change brief lines 26-27 (migration requirement).

---

## 6) Derived State & Invariants

- Derived value: Firmware S3 key prefix
  - Source: `model_code` (from DeviceModel.code) and `version` (from firmware binary AppInfo)
  - Writes / cleanup: S3 objects created under `firmware/{model_code}/{version}/` on upload; deleted on retention pruning or model deletion
  - Guards: Upload must succeed for all 5 artifacts before commit. Deletion is best-effort after commit.
  - Invariant: Every `firmware_versions` DB record must have a corresponding set of S3 objects under its prefix. If S3 deletion fails, orphaned objects are acceptable (best-effort).
  - Evidence: `app/services/firmware_service.py:181-266`, CLAUDE.md S3 golden rules.

- Derived value: Coredump S3 key
  - Source: `device_key` (from Device.key) and `coredump.id` (from CoreDump PK)
  - Writes / cleanup: S3 object created at `coredumps/{device_key}/{id}.dmp` on upload; deleted best-effort on coredump deletion or retention pruning
  - Guards: S3 upload must succeed before DB commit (golden rule). Deletion is best-effort after commit.
  - Invariant: Every CoreDump DB record must have a corresponding S3 object. If S3 deletion fails, orphaned objects are acceptable.
  - Evidence: `app/services/coredump_service.py:104-192`, CLAUDE.md S3 golden rules.

- Derived value: Pruneable firmware versions (filtered set driving persistent deletes)
  - Source: All `firmware_versions` for a model, filtered by: (a) not in the newest MAX_FIRMWARES, and (b) not referenced by any coredump with `parse_status=PENDING`
  - Writes / cleanup: Prunes firmware_versions DB records and S3 prefixes
  - Guards: The PENDING coredump guard prevents deleting firmware needed for parsing. Without this guard, a pruned version could make a coredump unparseable.
  - Invariant: Any firmware version referenced by a PENDING coredump must not be pruned, even if it exceeds MAX_FIRMWARES.
  - Evidence: Change brief line 9 (retention guards against unparsed coredumps).

- Derived value: DeviceModel.firmware_version (current/active version)
  - Source: Set during upload_firmware to the version extracted from the uploaded ZIP
  - Writes / cleanup: Updated on DeviceModel; used by IoT firmware download to determine which version to serve
  - Guards: Only updated after successful S3 upload of all artifacts
  - Invariant: Must always point to a version that has corresponding S3 objects
  - Evidence: `app/models/device_model.py:37`, `app/services/device_model_service.py:233-234`.

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: Firmware upload runs within a request-scoped SQLAlchemy session. The session auto-commits via `teardown_request`. Coredump upload similarly uses the request-scoped session. The parsing thread uses the container's ContextLocalSingleton session pattern with explicit commit/rollback/reset.

- Atomic requirements:
  - **Firmware upload**: DB writes (firmware_versions insert, device_model update) are flushed first, then S3 uploads. If any S3 upload fails, the exception propagates, and the request-scoped session rolls back on teardown. This matches the golden rule: "creates flush+upload+commit."
  - **Coredump upload**: CoreDump record is flushed (to get ID), then S3 upload. If S3 fails, transaction rolls back.
  - **Firmware deletion (model delete)**: DB delete is committed first, then S3 prefix deletion is best-effort. Matches golden rule: "deletes commit+best-effort-S3-delete."
  - **Coredump deletion**: DB delete is flushed/committed, then S3 delete is best-effort.

- Retry / idempotency: Re-uploading the same firmware version overwrites the firmware_versions record (upsert by unique constraint on `device_model_id, version`) and re-uploads S3 objects. S3 PUT is inherently idempotent. The CLI migration command should be idempotent: re-running it re-uploads objects that already exist (S3 PUT overwrites).

- Ordering / concurrency controls: No explicit locking. Concurrent firmware uploads for the same model are serialized by the database unique constraint on `(device_model_id, version)`. Concurrent coredump uploads for the same device are safe because each gets a unique DB `id`. Retention pruning runs within the upload transaction, so concurrent uploads could theoretically prune each other's versions, but the MAX_FIRMWARES default of 5 and the PENDING guard provide sufficient safety margin.

- Evidence: `app/services/coredump_service.py:437-469` (singleton DB pattern), CLAUDE.md S3 Storage Consistency section.

---

## 8) Errors & Edge Cases

- Failure: S3 upload fails during firmware upload
- Surface: FirmwareService.save_firmware (called from DeviceModelService.upload_firmware)
- Handling: InvalidOperationException propagates up to the API handler, `@handle_api_errors` returns 500. Transaction rolls back (firmware_versions record not committed).
- Guardrails: S3 connectivity is verified at application startup. Metrics record the failure.
- Evidence: `app/services/s3_service.py:99-100` (raises InvalidOperationException on upload failure).

- Failure: S3 download fails during coredump download
- Surface: CoredumpService.get_coredump_stream (new method) or API endpoint
- Handling: InvalidOperationException from S3Service, surfaced as 500 or 404 depending on error code (NoSuchKey -> 404).
- Guardrails: The coredump DB record's existence is verified first; S3 key is deterministic from DB data.
- Evidence: `app/services/s3_service.py:124-127` (NoSuchKey handling).

- Failure: S3 delete fails during retention pruning
- Surface: FirmwareService._enforce_retention or CoredumpService._enforce_retention
- Handling: Log and swallow. S3 cleanup is best-effort per CLAUDE.md.
- Guardrails: Orphaned S3 objects are harmless; they consume storage but don't affect correctness.
- Evidence: CLAUDE.md S3 Storage Consistency section ("Log and swallow storage errors because S3 cleanup is best-effort").

- Failure: Firmware version referenced by PENDING coredump is subject to pruning
- Surface: FirmwareService._enforce_retention
- Handling: Skip the version -- do not prune it. Log that retention was limited by PENDING coredumps.
- Guardrails: Query `CoreDump.firmware_version == version AND CoreDump.parse_status == 'PENDING'` before deleting.
- Evidence: Change brief line 9 ("Retention must guard against pruning versions still referenced by unparsed coredumps").

- Failure: CLI migration encounters coredump file without matching DB record
- Surface: CLI `migrate-to-s3` command
- Handling: Log a warning and skip the orphaned file. Do not upload orphaned files to S3.
- Guardrails: Migration logs all skipped files for manual review.
- Evidence: Change brief lines 26-27 (migration is one-time cutover).

- Failure: Raw .bin upload (non-ZIP) attempted after migration
- Surface: DeviceModelService.upload_firmware
- Handling: Reject with ValidationException. All uploads must now be ZIPs since individual artifacts are stored separately in S3.
- Guardrails: The `is_zip_content()` check at the top of upload_firmware; if content is not a ZIP, raise ValidationException("Firmware must be uploaded as a ZIP bundle").
- Evidence: `app/services/device_model_service.py:229-232` (current ZIP/bin routing).

---

## 9) Observability / Telemetry

- Signal: `firmware_upload`
- Type: Operation metric (counter + histogram via `record_operation`)
- Trigger: On successful or failed firmware upload in DeviceModelService
- Labels / fields: `operation="upload_firmware"`, `status="success"|"error"`, `duration`
- Consumer: Existing Prometheus `/metrics` endpoint
- Evidence: `app/api/device_models.py:244-245` -- existing `record_operation` call.

- Signal: `firmware_retention_pruned`
- Type: Structured log (INFO level)
- Trigger: When retention prunes firmware versions after upload
- Labels / fields: `model_code`, `pruned_count`, `skipped_pending_count`
- Consumer: Log aggregation
- Evidence: New, modeled after `app/services/coredump_service.py:228-233` (retention logging).

- Signal: `coredump_s3_upload`
- Type: Structured log (INFO level)
- Trigger: After successful coredump S3 upload
- Labels / fields: `device_key`, `coredump_id`, `s3_key`, `size`
- Consumer: Log aggregation
- Evidence: `app/services/coredump_service.py:182-190` (existing logging).

- Signal: `coredump_parse` (existing, unchanged)
- Type: Operation metric
- Trigger: After parse attempt completes (success or error)
- Labels / fields: `operation="coredump_parse"`, `status`, `duration`
- Consumer: Prometheus
- Evidence: `app/services/coredump_service.py:366-368` (existing).

- Signal: `migrate_to_s3`
- Type: Structured log (INFO level)
- Trigger: During CLI migration, per-file and summary
- Labels / fields: `source_path`, `s3_key`, `migrated_count`, `skipped_count`
- Consumer: CLI stdout / log aggregation
- Evidence: New CLI command.

---

## 10) Background Work & Shutdown

- Worker / job: Coredump parsing thread
- Trigger cadence: Event-driven (spawned per coredump upload when sidecar is configured)
- Responsibilities: Downloads `.dmp` and `.elf` from S3 (changed from filesystem), copies to xfer dir, calls sidecar, updates DB. The change from filesystem to S3 download is transparent to the thread's lifecycle.
- Shutdown handling: Thread is daemon -- will be killed on process exit. No change to existing shutdown behavior. The DB session pattern (commit/rollback/reset in finally) remains.
- Evidence: `app/services/coredump_service.py:270-276` (thread spawn), `app/services/coredump_service.py:278-405` (thread body).

No new background workers are introduced. The CLI migration command is a one-time foreground operation.

---

## 11) Security & Permissions

- Concern: S3 credentials and bucket access
- Touchpoints: S3Service, all firmware and coredump operations
- Mitigation: S3 credentials are already managed via environment variables (`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`). No change to the credential management model. The same bucket and credentials used for CAS images are reused.
- Residual risk: If S3 bucket permissions are misconfigured, firmware and coredump operations fail. This is an existing operational risk already present for CAS images.
- Evidence: `app/config.py:176-199` (S3 environment variables).

---

## 12) UX / UI Impact

- Entry point: Admin firmware upload
- Change: Raw `.bin` uploads are no longer accepted -- only ZIP bundles. The frontend already sends ZIPs for firmware upload.
- User interaction: No change for users already uploading ZIPs. Users attempting raw .bin upload will receive a 400 error.
- Dependencies: Frontend firmware upload component must send ZIP format.
- Evidence: `app/api/device_models.py:200-245` (upload endpoint accepts both, will be restricted to ZIP only).

- Entry point: Coredump list/detail views
- Change: `filename` field removed from API responses. Frontend should not display filename.
- User interaction: The coredump download endpoint still works (uses coredump_id in URL path, not filename).
- Dependencies: Frontend coredump components need to stop displaying `filename` if they do.
- Evidence: `app/schemas/coredump.py:15` (filename field removed).

---

## 13) Deterministic Test Plan

- Surface: FirmwareService (S3-based)
- Scenarios:
  - Given a valid ZIP, When `save_firmware` is called, Then 5 S3 objects are created under `firmware/{model_code}/{version}/` and a firmware_versions DB record exists
  - Given a valid ZIP, When `save_firmware` is called, Then the version string is extracted from the .bin and returned
  - Given a ZIP missing required files, When `save_firmware` is called, Then ValidationException is raised and no S3 objects are created
  - Given a ZIP with invalid .bin, When `save_firmware` is called, Then ValidationException is raised
  - Given a non-ZIP content, When `save_firmware` is called, Then ValidationException is raised
  - Given a model_code and version, When `get_firmware_stream` is called, Then a BytesIO containing the .bin is returned from S3
  - Given a non-existent S3 key, When `get_firmware_stream` is called, Then RecordNotFoundException is raised
  - Given `firmware_exists(model_code)` is called, When firmware is stored in S3, Then returns True
  - Given `firmware_exists(model_code)` is called, When no firmware exists, Then returns False
  - Given `delete_firmware(model_code)` is called, Then all S3 objects under `firmware/{model_code}/` are deleted (best-effort) and firmware_versions records are removed
- Fixtures / hooks: S3Service (real, using test bucket), DB session, `_create_test_zip` helper (reuse from existing tests)
- Gaps: None
- Evidence: `tests/services/test_firmware_service.py:1-388` -- existing tests to be rewritten.

- Surface: Firmware retention (MAX_FIRMWARES)
- Scenarios:
  - Given MAX_FIRMWARES=3 and 3 versions exist, When a 4th is uploaded, Then the oldest version is pruned from DB and S3
  - Given MAX_FIRMWARES=3 and 4 versions exist where the oldest is referenced by a PENDING coredump, When retention runs, Then that version is preserved and the next-oldest is pruned instead
  - Given MAX_FIRMWARES=3 and all excess versions are referenced by PENDING coredumps, When retention runs, Then no versions are pruned (retention is skipped for protected versions)
  - Given MAX_FIRMWARES=5 and only 2 versions exist, When retention runs, Then nothing is pruned
- Fixtures / hooks: DB session with firmware_versions and coredump records, S3Service, AppSettings with configurable max_firmwares
- Gaps: None
- Evidence: New feature, modeled after `tests/services/test_coredump_service.py:214-288` (existing retention tests).

- Surface: CoredumpService (S3-based)
- Scenarios:
  - Given valid content, When `save_coredump` is called, Then a CoreDump DB record is created and an S3 object exists at `coredumps/{device_key}/{id}.dmp`
  - Given empty content, When `save_coredump` is called, Then ValidationException is raised
  - Given oversized content (>1MB), When `save_coredump` is called, Then ValidationException is raised
  - Given a saved coredump, When `get_coredump_stream` is called, Then a BytesIO is returned with the .dmp data from S3
  - Given a saved coredump, When `delete_coredump` is called, Then the DB record is removed and S3 deletion is attempted
  - Given MAX_COREDUMPS=3 and 3 exist, When a 4th is saved, Then the oldest is pruned (DB + best-effort S3)
  - Given `delete_all_coredumps`, When called, Then all DB records and S3 objects for the device are removed
- Fixtures / hooks: S3Service (real), DB session, `create_test_device` helper
- Gaps: None
- Evidence: `tests/services/test_coredump_service.py:52-288` -- existing tests to be rewritten.

- Surface: Coredump parsing thread (S3-aware)
- Scenarios:
  - Given sidecar is configured, When parsing runs, Then `.dmp` is downloaded from S3 and `.elf` is downloaded from S3 to xfer dir
  - Given firmware .elf not in S3, When parsing runs, Then parse_status is set to ERROR
  - Given sidecar returns success, When parsing completes, Then parse_status is PARSED with output
  - Given sidecar fails all retries, When parsing completes, Then parse_status is ERROR
  - Given xfer files exist after parsing, When parsing completes, Then xfer files are cleaned up
- Fixtures / hooks: S3Service with uploaded firmware .elf and coredump .dmp, mock sidecar HTTP, DB session
- Gaps: None
- Evidence: `tests/services/test_coredump_service.py:461-746` -- existing parsing tests to be rewritten.

- Surface: Coredump API endpoints (S3-aware)
- Scenarios:
  - Given a saved coredump in S3, When `GET /api/devices/{id}/coredumps/{id}/download` is called, Then binary data is returned from S3
  - Given coredump not in S3, When download is called, Then 404 is returned
  - Given a coredump exists, When `DELETE /api/devices/{id}/coredumps/{id}` is called, Then 204 and S3 object is deleted
  - Given coredumps exist, When `DELETE /api/devices/{id}/coredumps` is called, Then 204 and all S3 objects are deleted
  - Given coredumps listed, When `GET /api/devices/{id}/coredumps` is called, Then response does not contain `filename` field
- Fixtures / hooks: S3Service, FlaskClient, test device with coredumps in S3
- Gaps: None
- Evidence: `tests/api/test_coredumps.py:1-340` -- existing tests to be rewritten.

- Surface: Device model firmware API (S3-aware)
- Scenarios:
  - Given firmware uploaded as ZIP, When `POST /api/device-models/{id}/firmware` is called, Then response includes firmware_version and S3 objects exist
  - Given firmware exists in S3, When `GET /api/device-models/{id}/firmware` is called, Then .bin binary is streamed from S3
  - Given raw .bin uploaded (not ZIP), When firmware upload is called, Then 400 is returned
- Fixtures / hooks: S3Service, FlaskClient, test device model
- Gaps: None
- Evidence: `tests/api/test_device_models.py:173-290` -- existing firmware tests.

- Surface: CLI `migrate-to-s3`
- Scenarios:
  - Given ASSETS_DIR with versioned ZIPs, When migration runs, Then artifacts are uploaded to S3 and firmware_versions records are created
  - Given COREDUMPS_DIR with .dmp files and matching DB records, When migration runs, Then .dmp files are uploaded to S3 as `coredumps/{device_key}/{id}.dmp`
  - Given orphaned .dmp files with no DB record, When migration runs, Then they are skipped with a warning
  - Given S3 is unreachable, When migration runs, Then it exits with non-zero code
- Fixtures / hooks: tmp_path with sample filesystem data, S3Service, DB with test records
- Gaps: CLI migration tests can use Click's CliRunner with a test app context.
- Evidence: `app/cli.py:19-179` (existing CLI patterns).

---

## 14) Implementation Slices

- Slice: Schema & S3Service extensions
- Goal: Database schema changes and S3Service additions land first, unblocking service work.
- Touches: `alembic/versions/006_*.py` (create firmware_versions, make coredumps.filename nullable), `app/models/firmware_version.py`, `app/models/coredump.py` (filename becomes Optional), `app/services/s3_service.py`
- Dependencies: None. Can be merged independently.

- Slice: FirmwareService S3 refactor
- Goal: Firmware storage moves entirely to S3 with version tracking and retention.
- Touches: `app/services/firmware_service.py`, `app/services/device_model_service.py`, `app/services/container.py`, `app/app_config.py`, `app/api/device_models.py`, `app/api/iot.py`, `tests/services/test_firmware_service.py`, `tests/api/test_device_models.py`, `tests/conftest.py`
- Dependencies: Slice 1 (schema + S3Service extensions).

- Slice: CoredumpService S3 refactor
- Goal: Coredump storage moves entirely to S3 with parsing thread S3 downloads. CoredumpService receives `s3_service` instead of `firmware_service` and `coredumps_dir`. Parsing thread downloads `.elf` directly from S3 via `self.s3_service`.
- Touches: `app/services/coredump_service.py`, `app/services/container.py`, `app/api/coredumps.py`, `app/api/iot.py`, `app/schemas/coredump.py`, `tests/services/test_coredump_service.py`, `tests/api/test_coredumps.py`, `tests/conftest.py`
- Dependencies: Slice 1 (schema + S3Service extensions).

- Slice: CLI migration command
- Goal: One-time migration tooling for existing deployments.
- Touches: `app/cli.py`, `app/startup.py`
- Dependencies: Slices 2 and 3 (services must be refactored first so the migration can create compatible data).

- Slice: Drop filename column (migration 007)
- Goal: Remove the `filename` column from `coredumps` table after CLI migration has run in all environments.
- Touches: `alembic/versions/007_*.py`, `app/models/coredump.py` (remove filename field entirely)
- Dependencies: Slice 4 (CLI migration must have run in all environments first).

- Slice: Cleanup
- Goal: Remove dead code and unused config.
- Touches: `app/utils/fs.py` (remove `atomic_write` import from firmware/coredump paths), `docs/product_brief.md` (update storage description)
- Dependencies: All prior slices.

---

## 15) Risks & Open Questions

- Risk: S3 multi-object upload failure mid-way during firmware upload (e.g., 3 of 5 artifacts uploaded, then S3 error)
- Impact: Orphaned S3 objects for partial firmware version. DB transaction rolls back, so no firmware_versions record exists, but S3 objects remain.
- Mitigation: On upload failure, attempt best-effort cleanup of any uploaded artifacts before re-raising. Alternatively, accept orphans since a subsequent successful upload overwrites them.

- Risk: Migration CLI encounters large firmware collections, taking extended downtime
- Impact: Deployment downtime exceeds expectations
- Mitigation: Test migration on staging with representative data volume. Log progress per-file. Consider adding `--dry-run` flag to estimate time.

- Risk: Concurrent firmware uploads for the same model could conflict during retention
- Impact: Two uploads could each try to prune different versions, leading to more pruning than expected
- Mitigation: The DB unique constraint on `(device_model_id, version)` prevents duplicate version records. Retention queries within a transaction see consistent state. The worst case is pruning one extra version, which is acceptable.

All open questions have been resolved autonomously:

- **Q: Should raw .bin uploads still be supported?** Resolved: No. The change brief explicitly eliminates the legacy flat binary concept. All uploads must be ZIPs.
- **Q: Should the firmware artifacts in S3 use `{model_code}.bin` or `firmware.bin`?** Resolved: Use generic names (`firmware.bin`, `firmware.elf`, `firmware.map`, `sdkconfig`, `version.json`) since the S3 key path already encodes `model_code` (e.g., `firmware/{model_code}/{version}/firmware.elf`). The sidecar receives the `.elf` file locally with its model-specific name (`{model_code}.elf`) regardless of the S3 object name.
- **Q: Does FirmwareService need to become a Factory?** Resolved: Yes. It needs DB session access for firmware_versions tracking and coredump PENDING guard queries. Making it a Factory aligns with the project's pattern for services that need request-scoped DB access. As a consequence, CoredumpService (which is a Singleton) can no longer receive FirmwareService via constructor injection. The parsing thread instead uses S3Service directly to download the `.elf`, constructing the deterministic S3 key from `model_code` and `firmware_version`.
- **Q: Should the coredump `filename` column be dropped or repurposed?** Resolved: Drop it via a two-phase approach. Migration 006 makes the column nullable (new S3-based records omit it). The CLI `migrate-to-s3` uses the column to match filesystem files to DB records. Migration 007 drops the column after the CLI has run in all environments.

---

## 16) Confidence

Confidence: High -- The change is well-scoped with clear boundaries. The existing S3Service and test infrastructure provide solid foundations. The codebase patterns for service refactoring, DB migrations, and S3 golden rules are well-documented and consistently applied. All open questions have been resolved from the codebase and change brief.
