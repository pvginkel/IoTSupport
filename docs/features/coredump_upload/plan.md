# Plan: Coredump Upload & Firmware ZIP Support

## 0) Research Log & Findings

**Areas researched:**

- **IoT blueprint (`app/api/iot.py`):** All device-facing endpoints live here, registered under `/api/iot/` via `api_bp`. Authentication is handled by a `before_request` hook that validates device JWTs and stores a `DeviceAuthContext` in `flask.g`. When OIDC is disabled (testing), endpoints fall back to a `device_key` query parameter. The new coredump endpoint will follow this same pattern.

- **Firmware service (`app/services/firmware_service.py`):** A stateless singleton that manages firmware binaries on the filesystem at `ASSETS_DIR/firmware-{model_code}.bin`. It parses the ESP32 AppInfo structure to extract version strings. The service stores one file per model with no versioning. The ZIP feature will need to add versioned storage alongside the existing flat-file layout.

- **Pipeline API (`app/api/pipeline.py`):** Exposes `POST /api/pipeline/models/<code>/firmware` for CI/CD uploads and two template script endpoints (`upload.sh`, `upload.ps1`). The firmware upload endpoint accepts raw binary or multipart uploads and delegates to `DeviceModelService.upload_firmware()`.

- **Device model service (`app/services/device_model_service.py`):** Orchestrates firmware upload by calling `firmware_service.save_firmware()`, updating `model.firmware_version`, and publishing MQTT notifications to all devices of that model.

- **Configuration (`app/config.py`):** `ASSETS_DIR` is already an environment variable (`Path | None`). `COREDUMPS_DIR` needs to be added as a new config variable following the same pattern.

- **Service container (`app/services/container.py`):** `FirmwareService` is a singleton receiving `config.provided.assets_dir`. A new `CoredumpService` will be added as a singleton receiving `config.provided.coredumps_dir`.

- **Upload script templates (`app/templates/upload_firmware.sh.j2`, `upload_firmware.ps1.j2`):** Currently upload a single `.bin` file. Need to be updated to create a ZIP containing `.bin`, `.elf`, `.map`, and `sdkconfig`, then upload the ZIP.

- **Test patterns (`tests/conftest.py`, `tests/api/test_iot.py`, `tests/api/test_pipeline.py`):** Tests use a `container` fixture backed by an in-memory SQLite database. Device creation uses mock Keycloak. Firmware tests create synthetic ESP32 binaries. The coredump and ZIP features will follow these patterns.

**Conflicts identified and resolved:**

- The current firmware path is `ASSETS_DIR/firmware-{model_code}.bin` (flat). The ZIP will be stored at `ASSETS_DIR/{model_code}/firmware-{version}.zip` (versioned, per-model subdirectory). These two layouts coexist without conflict; the firmware download logic will check for the versioned ZIP first, then fall back to the legacy flat `.bin`.

- The `iot_bp` is nested under `api_bp` (prefix `/api`), so the coredump endpoint path is `/api/iot/coredump`. The `before_request` device auth hook already covers all routes in this blueprint.

---

## 1) Intent & Scope

**User intent**

Add two related capabilities to the IoT Support Backend: (1) a device-facing endpoint for ESP32 coredump uploads stored on the filesystem with JSON sidecar metadata, and (2) extend the firmware upload pipeline to accept ZIP bundles containing ELF/MAP/sdkconfig alongside the .bin, preserving versioned firmware artifacts for future coredump analysis.

**Prompt quotes**

"a device-facing endpoint for ESP32 coredump uploads with filesystem storage"

"extend the firmware upload pipeline to accept ZIP files in addition to raw .bin files"

"A valid ZIP must contain exactly: `{model_code}.bin`, `{model_code}.elf`, `{model_code}.map`, `sdkconfig`, `version.json`"

"Coredumps are stored in per-device directories: `COREDUMPS_DIR/{device_key}/coredump_YYYYMMDDTHHMMSSZ.dmp`"

"No database model -- filesystem only"

"1MB maximum upload size"

"firmware version recorded in the coredump sidecar JSON links the coredump to the versioned ZIP"

**In scope**

- New `POST /api/iot/coredump` endpoint with raw binary body
- New `CoredumpService` for filesystem-based coredump storage with JSON sidecar
- New `COREDUMPS_DIR` configuration variable
- Extend `FirmwareService` to accept and validate ZIP bundles
- Versioned ZIP storage at `ASSETS_DIR/{model_code}/firmware-{version}.zip`
- Backward-compatible `.bin` extraction from versioned ZIP for device firmware downloads
- Updated pipeline upload scripts (sh and ps1) to package and upload ZIPs

**Out of scope**

- Coredump parsing or analysis (deferred to a future phase)
- Admin UI for browsing coredumps
- Cleanup/retention policy for old coredumps or firmware ZIPs
- Database model for coredumps

**Assumptions / constraints**

- Scale: up to 200 devices, coredumps are infrequent crash artifacts; disk pressure is not a concern.
- The ESP32 `.bin` inside a ZIP has the same AppInfo header format used by the existing `extract_version()` method.
- The coredump endpoint uses the same device JWT authentication as all other `/iot` endpoints.
- `COREDUMPS_DIR` may be on a different volume than `ASSETS_DIR`.

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] New `POST /iot/coredump` endpoint accepts raw binary body containing the coredump
- [ ] `chip` is a required query string parameter on the coredump endpoint
- [ ] `firmware_version` is a required query string parameter on the coredump endpoint
- [ ] New `COREDUMPS_DIR` environment variable controls coredump storage location
- [ ] Coredumps stored in per-device directories: `COREDUMPS_DIR/{device_key}/`
- [ ] Coredump files named with ISO 8601 timestamps: `coredump_YYYYMMDDTHHMMSSZ.dmp`
- [ ] JSON sidecar file alongside each coredump (same name, `.json` extension) containing chip, firmware_version, device_key, model_code, uploaded_at
- [ ] 1MB maximum upload size enforced
- [ ] No database model for coredumps -- filesystem storage only
- [ ] Firmware upload pipeline endpoint extended to accept ZIP files
- [ ] ZIP must contain `{model_code}.bin`, `{model_code}.elf`, `{model_code}.map`, `sdkconfig`, `version.json` -- reject if structure is invalid
- [ ] `version.json` in ZIP contains build metadata: `git_commit`, `idf_version`, `firmware_version`
- [ ] Firmware version extracted from `.bin` inside the ZIP
- [ ] ZIP stored as `ASSETS_DIR/{model_code}/firmware-{version}.zip` preserving historical versions
- [ ] Plain `.bin` uploads still supported for backward compatibility
- [ ] Device firmware download serves `.bin` extracted from versioned ZIP when available, falls back to legacy loose `.bin`
- [ ] Pipeline upload scripts (sh and ps1 templates) updated to package build artifacts into ZIP and upload

---

## 2) Affected Areas & File Map

- Area: `app/config.py` -- `Environment` class, `Settings` class, `Settings.load()`
- Why: Add `COREDUMPS_DIR` environment variable and corresponding settings field.
- Evidence: `app/config.py:76-79` -- `ASSETS_DIR` field pattern; `app/config.py:255` -- `assets_dir` in Settings.

- Area: `app/services/coredump_service.py` (new file)
- Why: New service for saving coredump binaries and JSON sidecar metadata to the filesystem.
- Evidence: `app/services/firmware_service.py:35-49` -- FirmwareService pattern (singleton with directory path, mkdir on init).

- Area: `app/services/firmware_service.py` -- `FirmwareService`
- Why: Add `save_firmware_zip()` for ZIP validation/extraction/versioned storage. Modify `get_firmware_stream(model_code, firmware_version=None)` to accept an optional `firmware_version` parameter: when provided, check for versioned ZIP at `ASSETS_DIR/{model_code}/firmware-{firmware_version}.zip` first; when `None` or ZIP absent, fall back to legacy flat `.bin`. FirmwareService is a stateless singleton with no DB access, so the caller must supply `firmware_version`.
- Evidence: `app/services/firmware_service.py:52-61` -- `get_firmware_path()` flat layout; `app/services/firmware_service.py:74-96` -- `get_firmware_stream()` reads from flat path; `app/services/firmware_service.py:98-136` -- `save_firmware()` writes to flat path.

- Area: `app/services/container.py` -- `ServiceContainer`
- Why: Register `CoredumpService` as a singleton provider wired to `config.provided.coredumps_dir`. Declaration: `coredump_service = providers.Singleton(CoredumpService, coredumps_dir=config.provided.coredumps_dir)`.
- Evidence: `app/services/container.py:101-105` -- `firmware_service` singleton pattern with `config.provided.assets_dir`.

- Area: `app/api/iot.py` -- `iot_bp`
- Why: (1) Add `POST /coredump` endpoint that reads raw binary body, validates query params, and delegates to `CoredumpService`. (2) Modify `GET /firmware` endpoint to look up the device model's `firmware_version` and pass it to `firmware_service.get_firmware_stream()` so the versioned ZIP can be located.
- Evidence: `app/api/iot.py:172-219` -- `get_firmware()` endpoint pattern with device auth context, metrics, and error handling; `app/api/iot.py:203` -- current call `firmware_service.get_firmware_stream(model_code)` needs to also pass `firmware_version`.

- Area: `app/api/pipeline.py` -- `upload_firmware()`
- Why: Modify to detect ZIP content type and route to the new ZIP upload path in `DeviceModelService`.
- Evidence: `app/api/pipeline.py:28-86` -- current firmware upload reads raw body or multipart file.

- Area: `app/api/device_models.py` -- `upload_firmware()`
- Why: Same change as pipeline -- detect ZIP and route accordingly.
- Evidence: `app/api/device_models.py:200-245` -- admin firmware upload endpoint.

- Area: `app/services/device_model_service.py` -- `DeviceModelService.upload_firmware()`
- Why: Route to either `firmware_service.save_firmware()` or `firmware_service.save_firmware_zip()` based on content type.
- Evidence: `app/services/device_model_service.py:205-250` -- current upload_firmware method.

- Area: `app/__init__.py` -- `create_app()`
- Why: Wire `app.api.iot` is already wired; no change needed. But container wiring list may need updating if new API modules are added.
- Evidence: `app/__init__.py:62-76` -- wire_modules list already includes `app.api.iot`.

- Area: `app/templates/upload_firmware.sh.j2`
- Why: Update script to create ZIP from build artifacts and upload instead of raw `.bin`.
- Evidence: `app/templates/upload_firmware.sh.j2:93-98` -- current raw binary upload with `--data-binary`.

- Area: `app/templates/upload_firmware.ps1.j2`
- Why: Same update for PowerShell script.
- Evidence: `app/templates/upload_firmware.ps1.j2:74-83` -- current raw binary upload with `ReadAllBytes`.

- Area: `tests/services/test_coredump_service.py` (new file)
- Why: Service tests for `CoredumpService`.
- Evidence: `tests/services/test_device_model_service.py` -- existing service test pattern.

- Area: `tests/services/test_firmware_service.py` (new file)
- Why: Service tests for ZIP validation, versioned storage, and `.bin` extraction from ZIP.
- Evidence: `tests/api/test_pipeline.py:17-44` -- `_create_test_firmware()` helper for building synthetic binaries.

- Area: `tests/api/test_iot.py`
- Why: Add API tests for `POST /api/iot/coredump` endpoint.
- Evidence: `tests/api/test_iot.py:38-88` -- existing IoT endpoint test patterns.

- Area: `tests/api/test_pipeline.py`
- Why: Add tests for ZIP firmware upload via pipeline.
- Evidence: `tests/api/test_pipeline.py:14-81` -- existing pipeline firmware upload tests.

- Area: `tests/conftest.py`
- Why: Add `coredumps_dir` to test settings; optionally add helper fixtures for coredump tests.
- Evidence: `tests/conftest.py:56-58` -- `assets_dir` setup in `_build_test_settings`.

---

## 3) Data Model / Contracts

- Entity / contract: `COREDUMPS_DIR` configuration
- Shape:
  ```
  Environment:  COREDUMPS_DIR: Path | None (default None)
  Settings:     coredumps_dir: Path | None
  ```
- Refactor strategy: Additive -- new field, no backward compatibility concern.
- Evidence: `app/config.py:76-79` -- `ASSETS_DIR` pattern.

- Entity / contract: Coredump sidecar JSON
- Shape:
  ```json
  {
    "chip": "esp32s3",
    "firmware_version": "1.2.3",
    "device_key": "abc12345",
    "model_code": "tempsensor",
    "uploaded_at": "2026-02-11T14:30:00Z"
  }
  ```
- Refactor strategy: New artifact, filesystem only, no database or API contract. Not returned by any endpoint.
- Evidence: Change brief -- "A JSON sidecar file stores metadata: chip, firmware_version, device_key, model_code, uploaded_at."

- Entity / contract: Firmware ZIP structure
- Shape:
  ```
  {model_code}.bin       (required -- ESP32 firmware binary)
  {model_code}.elf       (required -- ELF debug symbols)
  {model_code}.map       (required -- linker map file)
  sdkconfig              (required -- ESP-IDF SDK configuration)
  version.json           (required -- build metadata)
  ```
- Refactor strategy: ZIP support is additive. The `upload_firmware` method detects content type (ZIP vs raw binary) and routes accordingly. Plain `.bin` continues to work.
- Evidence: Change brief -- "A valid ZIP must contain exactly: `{model_code}.bin`, `{model_code}.elf`, `{model_code}.map`, `sdkconfig`, `version.json`."

- Entity / contract: `version.json` build metadata (inside ZIP)
- Shape:
  ```json
  {
    "git_commit": "a1b2c3d4e5f6...",
    "idf_version": "v5.2.1",
    "firmware_version": "1.2.3"
  }
  ```
- Refactor strategy: New artifact inside the ZIP. Generated by the upload scripts from build environment data.
- Evidence: Change brief -- "`version.json` contains build metadata: `git_commit`, `idf_version`, `firmware_version`."

- Entity / contract: Versioned firmware ZIP storage path
- Shape: `ASSETS_DIR/{model_code}/firmware-{version}.zip`
- Refactor strategy: New directory hierarchy. Legacy flat path `ASSETS_DIR/firmware-{model_code}.bin` remains in use for backward compatibility on reads.
- Evidence: `app/services/firmware_service.py:52-61` -- current flat path `ASSETS_DIR/firmware-{model_code}.bin`.

---

## 4) API / Integration Surface

- Surface: `POST /api/iot/coredump?chip=<chip>&firmware_version=<version>`
- Inputs: Raw binary body (coredump data, max 1MB). Query string parameters: `chip` (string, required), `firmware_version` (string, required). Device identity from JWT auth context.
- Outputs: `201 Created` with JSON body `{"status": "ok", "filename": "<coredump_filename>"}`. Side effect: coredump `.dmp` and `.json` sidecar written to `COREDUMPS_DIR/{device_key}/`.
- Errors: `400` if body is empty, exceeds 1MB, or required query params are missing. `401` if device not authenticated. `500` if filesystem write fails.
- Evidence: `app/api/iot.py:172-219` -- existing firmware download endpoint pattern.

- Surface: `POST /api/pipeline/models/<code>/firmware` (modified)
- Inputs: Raw binary body (`.bin` or `.zip`). Content detection by inspecting the first 4 bytes for ZIP magic (`PK\x03\x04`).
- Outputs: Same `DeviceModelFirmwareResponseSchema` as before. Side effect: if ZIP, validates structure, extracts `.bin` version, stores ZIP at versioned path, and also saves legacy flat `.bin`.
- Errors: `400` if ZIP structure is invalid (missing required files). Existing errors unchanged.
- Evidence: `app/api/pipeline.py:28-86` -- current upload endpoint.

- Surface: `POST /api/device-models/<id>/firmware` (modified)
- Inputs: Same as pipeline endpoint -- supports both `.bin` and `.zip`.
- Outputs: Same response schema.
- Errors: Same as pipeline.
- Evidence: `app/api/device_models.py:200-245` -- admin firmware upload.

- Surface: `GET /api/iot/firmware` (modified behavior)
- Inputs: Unchanged (device auth via JWT or query param).
- Outputs: Returns `.bin` extracted from the versioned ZIP at `ASSETS_DIR/{model_code}/firmware-{version}.zip` if available; falls back to legacy `ASSETS_DIR/firmware-{model_code}.bin`. The endpoint now looks up the device model to obtain `firmware_version` and passes it to `firmware_service.get_firmware_stream(model_code, firmware_version)`.
- Errors: Unchanged.
- Evidence: `app/api/iot.py:172-219` -- currently calls `firmware_service.get_firmware_stream(model_code)` without version; must be updated to look up `device.device_model.firmware_version` and pass it through.

- Surface: `GET /api/pipeline/upload.sh` and `GET /api/pipeline/upload.ps1` (modified)
- Inputs: Unchanged.
- Outputs: Updated script content that generates `version.json` (with `git_commit`, `idf_version`, `firmware_version`) and packages `.bin`, `.elf`, `.map`, `sdkconfig`, and `version.json` into a ZIP before uploading.
- Errors: Unchanged.
- Evidence: `app/templates/upload_firmware.sh.j2:93-98`, `app/templates/upload_firmware.ps1.j2:74-83`.

---

## 5) Algorithms & State Machines

- Flow: Coredump upload
- Steps:
  1. `before_request` hook authenticates the device JWT and populates `DeviceAuthContext` (existing).
  2. Endpoint extracts `chip` and `firmware_version` from query string; validates both are present.
  3. Reads raw binary body from `request.get_data()`.
  4. Validates body is non-empty and does not exceed 1MB.
  5. Resolves device key and model code from auth context (or query param in test mode).
  6. Delegates to `CoredumpService.save_coredump(device_key, model_code, chip, firmware_version, content)`.
  7. Service creates `COREDUMPS_DIR/{device_key}/` directory if it does not exist.
  8. Generates filename: `coredump_{now_utc_iso8601}.dmp` (format: `YYYYMMDDTHHMMSS_{microseconds}Z` to avoid sub-second collisions).
  9. Writes binary content to `.dmp` file atomically (temp file + rename).
  10. Writes JSON sidecar to matching `.json` file.
  11. Returns filename to the API layer.
  12. API returns `201` with filename in response body.
- States / transitions: None.
- Hotspots: Filesystem I/O is synchronous but coredumps are infrequent; no performance concern at 200-device scale.
- Evidence: `app/services/firmware_service.py:116-134` -- atomic write pattern (mkstemp + replace).

- Flow: Firmware ZIP upload
- Steps:
  1. API layer receives upload content (raw body or multipart file).
  2. Detects whether content is a ZIP by checking first 4 bytes for ZIP magic (`PK\x03\x04` = `\x50\x4b\x03\x04`).
  3. If ZIP: calls `firmware_service.save_firmware_zip(model_code, content)`.
  4. Service opens ZIP in memory using `zipfile.ZipFile(BytesIO(content))`.
  5. Validates ZIP contains exactly `{model_code}.bin`, `{model_code}.elf`, `{model_code}.map`, `sdkconfig`, `version.json`; raises `ValidationException` if any are missing or extra files are present.
  6. Reads `{model_code}.bin` from ZIP and extracts firmware version via `extract_version()`.
  7. Creates `ASSETS_DIR/{model_code}/` directory if needed.
  8. Writes ZIP atomically to `ASSETS_DIR/{model_code}/firmware-{version}.zip`.
  9. Also writes/overwrites the legacy flat `.bin` at `ASSETS_DIR/firmware-{model_code}.bin` for backward compatibility with any older code paths.
  10. Returns version string.
  11. If not ZIP: falls through to existing `save_firmware()` logic (raw `.bin`).
- States / transitions: None.
- Hotspots: ZIP processing is in-memory; firmware binaries are typically under 2MB, well within memory limits.
- Evidence: `app/services/firmware_service.py:98-136` -- existing `save_firmware()`.

- Flow: Firmware download with ZIP fallback
- Steps:
  1. Caller obtains `firmware_version` from the database before calling `FirmwareService`. For the IoT endpoint (`app/api/iot.py`), this means looking up the device model via `device_service.get_device_by_key()` to get `device.device_model.firmware_version`. For the admin download, `DeviceModelService.get_firmware_stream()` already has the model.
  2. `get_firmware_stream(model_code, firmware_version)` is called with the version.
  3. If `firmware_version` is provided, check for versioned ZIP at `ASSETS_DIR/{model_code}/firmware-{firmware_version}.zip`.
  4. If ZIP exists: open it, extract `{model_code}.bin`, return as `BytesIO`.
  5. If ZIP does not exist (or `firmware_version` was None): fall back to legacy flat path `ASSETS_DIR/firmware-{model_code}.bin`.
  6. If neither exists: raise `RecordNotFoundException`.
- States / transitions: None.
- Hotspots: ZIP extraction on every download adds I/O. At 200 devices and infrequent firmware pulls, this is acceptable. If needed later, the `.bin` could be cached on disk after first extraction.
- Evidence: `app/services/firmware_service.py:74-96` -- current `get_firmware_stream()`.

---

## 6) Derived State & Invariants

- Derived value: Coredump filename timestamp
  - Source: Current UTC time at the moment `CoredumpService.save_coredump()` is called.
  - Writes / cleanup: Determines the `.dmp` and `.json` filenames on disk.
  - Guards: Timestamp is generated server-side (not from client), ensuring consistency.
  - Invariant: Each coredump file pair (`.dmp` + `.json`) has exactly the same base name.
  - Evidence: Change brief -- "coredump_YYYYMMDDTHHMMSSZ.dmp" (implementation uses microsecond precision to avoid collisions).

- Derived value: Versioned ZIP storage path
  - Source: `firmware_version` extracted from the `.bin` inside the uploaded ZIP.
  - Writes / cleanup: ZIP is written to `ASSETS_DIR/{model_code}/firmware-{version}.zip`. The legacy flat `.bin` is also updated.
  - Guards: Version extraction uses the proven `extract_version()` method; if extraction fails, the upload is rejected. The version is also written to `DeviceModel.firmware_version` in the database.
  - Invariant: The ZIP at the versioned path always contains a `.bin` whose AppInfo version matches the `{version}` in the filename.
  - Evidence: `app/services/firmware_service.py:154-202` -- `extract_version()`.

- Derived value: Firmware stream source selection
  - Source: `DeviceModel.firmware_version` (from database) and filesystem state (`ASSETS_DIR/{model_code}/firmware-{version}.zip` existence).
  - Writes / cleanup: No writes; read-only derivation for choosing the stream source.
  - Guards: Falls back to legacy `.bin` if versioned ZIP is absent, ensuring devices always get firmware even during migration.
  - Invariant: If a versioned ZIP exists for the current `firmware_version`, the `.bin` extracted from it is identical to what was in the uploaded ZIP.
  - Evidence: `app/services/firmware_service.py:74-96` -- current `get_firmware_stream()`.

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: Coredump upload is filesystem-only -- no database transaction involved. The `.dmp` file is written atomically (temp file + `os.replace`), then the `.json` sidecar is written. If the sidecar write fails, the `.dmp` file remains (orphaned but harmless; a future cleanup could handle this).

- Atomic requirements: For firmware ZIP upload, the database update (`model.firmware_version`) and MQTT notification happen within the existing request-scoped SQLAlchemy session (committed by `teardown_request`). The ZIP file is written to disk before the database update. If the database commit fails, the ZIP on disk is orphaned but harmless. This matches the existing firmware upload pattern.

- Retry / idempotency: Coredump uploads produce unique filenames (ISO timestamp with microsecond precision). No idempotency key is needed. Firmware ZIP uploads overwrite the same versioned path if re-uploaded with the same version, which is idempotent.

- Ordering / concurrency controls: No locking needed. Concurrent coredump uploads from different devices write to different directories. Concurrent firmware uploads for the same model are serialized by the request-scoped database session and atomic file writes.

- Evidence: `app/services/firmware_service.py:116-134` -- atomic write pattern; `app/__init__.py:109-127` -- teardown_request commit/rollback.

---

## 8) Errors & Edge Cases

- Failure: Empty coredump body
- Surface: `POST /api/iot/coredump`
- Handling: 400 with `ValidationException("No coredump content provided")`.
- Guardrails: Check `len(content) == 0` before processing.
- Evidence: `app/api/pipeline.py:66-68` -- existing empty content check pattern.

- Failure: Coredump body exceeds 1MB
- Surface: `POST /api/iot/coredump`
- Handling: 400 with `ValidationException("Coredump exceeds maximum size of 1MB")`.
- Guardrails: Check `len(content) > 1_048_576` in service layer.
- Evidence: Change brief -- "1MB maximum upload size."

- Failure: Missing `chip` or `firmware_version` query parameter
- Surface: `POST /api/iot/coredump`
- Handling: 400 with `ValidationException("Missing required query parameter: chip")` (or `firmware_version`).
- Guardrails: Validate before reading body.
- Evidence: Change brief -- "required query string parameters."

- Failure: `COREDUMPS_DIR` not configured
- Surface: `CoredumpService` initialization
- Handling: Service is created with `None` path; upload attempts raise `InvalidOperationException("upload coredump", "COREDUMPS_DIR is not configured")`.
- Guardrails: Lazy guard in the save method rather than startup failure, since coredump support is intentionally optional -- not all deployments need coredump collection. Unlike `ASSETS_DIR` (which is required for core firmware functionality), `COREDUMPS_DIR` is **not** added to `validate_production_config()`. This is a deliberate design choice: deployments that do not need coredump support should not be forced to configure a directory.
- Evidence: `app/config.py:76-79` -- `ASSETS_DIR` is also `Path | None`; `app/config.py:363-367` -- `ASSETS_DIR` is validated for production but `COREDUMPS_DIR` is intentionally excluded.

- Failure: ZIP missing required files
- Surface: `POST /api/pipeline/models/<code>/firmware` or admin firmware upload
- Handling: 400 with `ValidationException("Invalid firmware ZIP: missing {model_code}.elf")`.
- Guardrails: Enumerate ZIP contents and validate against required set before any writes.
- Evidence: Change brief -- "Reject the upload if the ZIP violates this structure."

- Failure: ZIP contains extra unexpected files
- Surface: Firmware upload endpoints
- Handling: 400 with `ValidationException("Invalid firmware ZIP: unexpected files: {list}")`.
- Guardrails: Compare ZIP namelist to exact required set.
- Evidence: Change brief -- "must contain exactly."

- Failure: Filesystem write failure (disk full, permissions)
- Surface: Both coredump and firmware upload
- Handling: Let the `OSError` propagate; `@handle_api_errors` catches it as a generic 500.
- Guardrails: Atomic writes prevent partial files. Monitoring via existing error metrics.
- Evidence: `app/utils/error_handling.py:174-178` -- generic exception handler.

---

## 9) Observability / Telemetry

- Signal: `iot_upload_coredump` operation
- Type: Counter + Histogram (via existing `record_operation()`)
- Trigger: Every `POST /api/iot/coredump` request, on completion or error.
- Labels / fields: `operation="iot_upload_coredump"`, `status="success"|"error"`
- Consumer: Prometheus `/metrics` endpoint, existing dashboards.
- Evidence: `app/api/iot.py:117-119` -- `metrics_service.record_operation()` pattern.

- Signal: `pipeline_upload_firmware_zip` operation
- Type: Counter + Histogram (via existing `record_operation()`)
- Trigger: When a ZIP firmware upload is processed (distinct from raw `.bin` uploads).
- Labels / fields: `operation="pipeline_upload_firmware_zip"`, `status="success"|"error"`
- Consumer: Same Prometheus pipeline.
- Evidence: `app/api/pipeline.py:84-86` -- existing `pipeline_upload_firmware` metric.

- Signal: Structured log on coredump save
- Type: Structured log (INFO level)
- Trigger: After successful coredump write.
- Labels / fields: `device_key`, `model_code`, `chip`, `firmware_version`, `filename`
- Consumer: Application log aggregation.
- Evidence: `app/services/firmware_service.py:127` -- existing info log on firmware save.

---

## 10) Background Work & Shutdown

No background workers are introduced by this feature. Both coredump uploads and firmware ZIP processing are synchronous request-scoped operations. No shutdown integration is needed.

---

## 11) Security & Permissions

- Concern: Authentication on coredump endpoint
- Touchpoints: `POST /api/iot/coredump` -- protected by the existing `iot_bp.before_request` hook that validates device JWTs.
- Mitigation: Device identity is extracted from the JWT `azp` claim, not from user-supplied parameters. The `device_key` in the auth context determines the storage directory, preventing devices from writing to other devices' directories.
- Residual risk: A compromised device could upload arbitrarily many coredumps, filling disk. Acceptable at 200-device scale; disk monitoring is recommended.
- Evidence: `app/api/iot.py:41-61` -- `before_request_device_auth()`.

- Concern: Upload size limit (DoS prevention)
- Touchpoints: `POST /api/iot/coredump`
- Mitigation: 1MB size check in the service layer. Flask reads the full body into memory, but 1MB is small.
- Residual risk: Flask reads body before the endpoint can reject it. For devices on a trusted network, this is acceptable.
- Evidence: Change brief -- "1MB maximum upload size."

---

## 12) UX / UI Impact

- Entry point: Pipeline upload scripts (`upload.sh`, `upload.ps1`)
- Change: Scripts will now generate `version.json` and package `.bin`, `.elf`, `.map`, `sdkconfig`, and `version.json` into a ZIP before uploading instead of uploading the raw `.bin`.
- User interaction: CI/CD pipelines that consume these scripts will automatically switch to ZIP uploads. No manual intervention required since the scripts are served dynamically from the backend.
- Dependencies: Build environments must produce `.elf`, `.map`, and `sdkconfig` files alongside the `.bin`. Standard ESP-IDF builds already produce all of these.
- Evidence: `app/templates/upload_firmware.sh.j2`, `app/templates/upload_firmware.ps1.j2`.

---

## 13) Deterministic Test Plan

- Surface: `CoredumpService`
- Scenarios:
  - Given a valid device key, model code, chip, firmware version, and binary content, When `save_coredump()` is called, Then a `.dmp` file and `.json` sidecar are created in `COREDUMPS_DIR/{device_key}/` with correct content.
  - Given content exceeding 1MB, When `save_coredump()` is called, Then `ValidationException` is raised.
  - Given empty content, When `save_coredump()` is called, Then `ValidationException` is raised.
  - Given `coredumps_dir` is None, When `save_coredump()` is called, Then `InvalidOperationException` is raised.
  - Given a device directory that does not yet exist, When `save_coredump()` is called, Then the directory is created and the files are written.
  - Given a successful save, When the `.json` sidecar is read back, Then it contains the correct chip, firmware_version, device_key, model_code, and uploaded_at fields.
- Fixtures / hooks: `tmp_path` for `coredumps_dir`; direct `CoredumpService` instantiation with test path.
- Gaps: None.
- Evidence: `tests/conftest.py:56-58` -- `assets_dir` pattern for temp directory.

- Surface: `FirmwareService` ZIP support
- Scenarios:
  - Given a valid ZIP containing `{code}.bin`, `{code}.elf`, `{code}.map`, `sdkconfig`, `version.json`, When `save_firmware_zip()` is called, Then the ZIP is stored at `ASSETS_DIR/{code}/firmware-{version}.zip` and the legacy `.bin` is also updated.
  - Given a ZIP missing the `.elf` file, When `save_firmware_zip()` is called, Then `ValidationException` is raised.
  - Given a ZIP with extra files, When `save_firmware_zip()` is called, Then `ValidationException` is raised.
  - Given a ZIP whose `.bin` has an invalid AppInfo header, When `save_firmware_zip()` is called, Then `ValidationException` is raised.
  - Given a model with a versioned ZIP on disk, When `get_firmware_stream()` is called, Then the `.bin` is extracted from the ZIP and returned.
  - Given a model with no versioned ZIP but a legacy `.bin`, When `get_firmware_stream()` is called, Then the legacy `.bin` is returned.
  - Given a model with neither ZIP nor legacy `.bin`, When `get_firmware_stream()` is called, Then `RecordNotFoundException` is raised.
- Fixtures / hooks: `tmp_path` for `assets_dir`; synthetic ESP32 binaries using existing `_create_test_firmware()` helper; Python `zipfile` for building test ZIPs.
- Gaps: None.
- Evidence: `tests/api/test_pipeline.py:17-44` -- `_create_test_firmware()` helper.

- Surface: `POST /api/iot/coredump` endpoint
- Scenarios:
  - Given an authenticated device with valid query params and body, When POST is made, Then 201 is returned with filename in response.
  - Given a missing `chip` query param, When POST is made, Then 400 is returned.
  - Given a missing `firmware_version` query param, When POST is made, Then 400 is returned.
  - Given an empty body, When POST is made, Then 400 is returned.
  - Given a body exceeding 1MB, When POST is made, Then 400 is returned.
  - Given no device authentication (OIDC disabled, no device_key param), When POST is made, Then 401 is returned.
  - Given a valid upload in test mode (OIDC disabled, device_key param), When POST is made, Then coredump files are written to the correct directory.
- Fixtures / hooks: `client` fixture, `create_test_device()` helper from `test_iot.py`, `tmp_path`-based `COREDUMPS_DIR` in test settings.
- Gaps: None.
- Evidence: `tests/api/test_iot.py:12-36` -- `create_test_device()` helper; `tests/api/test_iot.py:38-67` -- existing endpoint test pattern.

- Surface: Pipeline firmware upload (ZIP path)
- Scenarios:
  - Given a device model and a valid firmware ZIP, When POST is made to `/api/pipeline/models/<code>/firmware`, Then 200 is returned with firmware version extracted from the `.bin` inside the ZIP.
  - Given a ZIP with wrong structure, When POST is made, Then 400 is returned.
  - Given a plain `.bin` upload (backward compat), When POST is made, Then 200 is returned as before.
- Fixtures / hooks: Existing `container` fixture, `_create_test_firmware()` helper, Python `zipfile` for building test ZIPs.
- Gaps: None.
- Evidence: `tests/api/test_pipeline.py:46-65` -- existing firmware upload test.

- Surface: Pipeline upload scripts (sh and ps1)
- Scenarios:
  - Given a request to `/api/pipeline/upload.sh`, When script is returned, Then it contains ZIP packaging logic (generates `version.json` and references `zip` command with all five required files).
  - Given a request to `/api/pipeline/upload.ps1`, When script is returned, Then it contains ZIP packaging logic (generates `version.json` and references `Compress-Archive` or equivalent with all five required files).
- Fixtures / hooks: Existing `client` fixture.
- Gaps: None.
- Evidence: `tests/api/test_pipeline.py:198-284` -- existing script content tests.

---

## 14) Implementation Slices

- Slice: Configuration + CoredumpService + coredump endpoint
- Goal: Devices can upload coredumps to the backend.
- Touches: `app/config.py`, `app/services/coredump_service.py` (new), `app/services/container.py`, `app/api/iot.py`, `tests/conftest.py`, `tests/services/test_coredump_service.py` (new), `tests/api/test_iot.py`.
- Dependencies: None -- fully independent of the ZIP feature.

- Slice: FirmwareService ZIP support + firmware download fallback
- Goal: Firmware uploads can be ZIPs; downloads extract `.bin` from ZIP.
- Touches: `app/services/firmware_service.py`, `tests/services/test_firmware_service.py` (new).
- Dependencies: None -- service-level only.

- Slice: API integration for ZIP uploads
- Goal: Both pipeline and admin firmware upload endpoints accept ZIPs.
- Touches: `app/services/device_model_service.py`, `app/api/pipeline.py`, `app/api/device_models.py`, `tests/api/test_pipeline.py`, `tests/api/test_device_models.py`.
- Dependencies: Slice 2 (FirmwareService ZIP support).

- Slice: Pipeline script updates
- Goal: CI/CD scripts package build artifacts into ZIP.
- Touches: `app/templates/upload_firmware.sh.j2`, `app/templates/upload_firmware.ps1.j2`, `tests/api/test_pipeline.py`.
- Dependencies: Slice 3 (endpoints accept ZIPs).

---

## 15) Risks & Open Questions

- Risk: Concurrent coredump uploads from the same device in a very short time window could produce identical filenames.
- Impact: Second upload overwrites the first coredump silently.
- Mitigation: Use microsecond-precision timestamps in the filename (format: `YYYYMMDDTHHMMSS_{microseconds}Z`) to reduce the collision window to sub-microsecond. At 200 devices with infrequent crashes, this is effectively impossible.

- Risk: Disk space exhaustion from accumulated coredumps and versioned firmware ZIPs.
- Impact: Filesystem fills up, blocking further uploads and potentially affecting other services.
- Mitigation: Defer to operational monitoring. Document that a retention policy should be added in a future phase.

- Risk: `get_firmware_stream()` now needs `firmware_version` from the database model to locate the versioned ZIP, but the current method signature only takes `model_code`.
- Impact: Requires a method signature change and updates to call sites (IoT endpoint, DeviceModelService).
- Mitigation: Extend `get_firmware_stream(model_code, firmware_version=None)` to accept an optional `firmware_version` parameter. The IoT endpoint must be updated to look up the device model via `device_service.get_device_by_key()` and pass `device.device_model.firmware_version`. The admin download goes through `DeviceModelService.get_firmware_stream()` which already has the model and passes `model.firmware_version`. When `firmware_version` is None, skip the ZIP check and fall back to legacy `.bin` only.

---

## 16) Confidence

Confidence: High -- Both features are additive with clear filesystem-based storage patterns, no database migrations, and well-established test patterns to follow. The codebase already handles similar I/O (firmware binary storage) and the coredump endpoint follows the existing IoT blueprint conventions exactly.
