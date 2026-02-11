# Code Review: Coredump Upload & Firmware ZIP Support

## 1) Summary & Decision

**Readiness**

The implementation is well-structured and closely follows the approved plan. All 46 new tests pass, the full suite (515 tests) shows zero regressions, ruff linting is clean, and mypy reports no type errors. The code follows the project's layered architecture, uses proper dependency injection, and includes thorough validation. Two issues require attention before shipping: the `delete_firmware()` method does not clean up versioned ZIP directories, and `firmware_exists()` only checks the legacy path, creating a potential inconsistency when the codebase transitions to ZIP-only storage. Neither rises to a blocker since the legacy `.bin` is always written alongside the ZIP, but both should be addressed to avoid latent bugs.

**Decision**

`GO-WITH-CONDITIONS` -- The two firmware lifecycle gaps (delete and exists not ZIP-aware) and a minor path-traversal hardening concern should be resolved before merging.


## 2) Conformance to Plan (with evidence)

**Plan alignment**

- `Plan Section 1: Coredump endpoint` <-> `/work/backend/app/api/iot.py:353-419` -- POST /api/iot/coredump endpoint implemented with query param validation, auth context resolution, and delegation to CoredumpService.
- `Plan Section 1: CoredumpService` <-> `/work/backend/app/services/coredump_service.py:18-127` -- Filesystem-only storage with JSON sidecar, atomic writes, 1MB limit, per-device directories.
- `Plan Section 1: COREDUMPS_DIR config` <-> `/work/backend/app/config.py:82-85` and `/work/backend/app/config.py:262-263` -- `COREDUMPS_DIR` added to both `Environment` and `Settings`.
- `Plan Section 2: FirmwareService ZIP support` <-> `/work/backend/app/services/firmware_service.py:190-295` -- `save_firmware_zip()` validates ZIP structure, extracts version, writes versioned ZIP and legacy `.bin`.
- `Plan Section 2: Firmware download fallback` <-> `/work/backend/app/services/firmware_service.py:110-148` -- `get_firmware_stream()` tries versioned ZIP first, falls back to legacy `.bin`.
- `Plan Section 2: DeviceModelService routing` <-> `/work/backend/app/services/device_model_service.py:220-232` -- `upload_firmware()` detects ZIP via `is_zip_content()` and routes accordingly.
- `Plan Section 2: Pipeline scripts` <-> `/work/backend/app/templates/upload_firmware.sh.j2:73-161` and `/work/backend/app/templates/upload_firmware.ps1.j2:74-137` -- Both scripts updated with ZIP packaging, version.json generation, and fallback to raw binary.
- `Plan Section 2: Container wiring` <-> `/work/backend/app/services/container.py:102-106` -- `CoredumpService` registered as a Singleton with `config.provided.coredumps_dir`.
- `Plan Section 9: Observability` <-> `/work/backend/app/api/iot.py:418` -- `metrics_service.record_operation("iot_upload_coredump", ...)` tracked.

**Gaps / deviations**

- `Plan Section 4: distinct pipeline_upload_firmware_zip metric` -- The plan called for a distinct `pipeline_upload_firmware_zip` operation metric when a ZIP is uploaded via the pipeline. The implementation uses the existing `pipeline_upload_firmware` metric for both ZIP and binary uploads (`/work/backend/app/api/pipeline.py:86`). This is a minor deviation; the single metric still tracks all firmware uploads and distinguishing ZIP vs binary can be added later if needed.
- `Plan Section 2: admin firmware upload (device_models.py)` -- The plan listed `/work/backend/app/api/device_models.py` as needing a change to detect ZIP content type. The implementation correctly delegates to `DeviceModelService.upload_firmware()` which handles the detection internally, so no API-layer change was needed. This is a simplification, not a gap.


## 3) Correctness -- Findings (ranked)

- Title: `Major -- delete_firmware() does not clean up versioned ZIP directory`
- Evidence: `/work/backend/app/services/firmware_service.py:297-311` -- `delete_firmware()` only removes the legacy flat `.bin` path: `path = self.get_firmware_path(model_code)` followed by `path.unlink()`. The versioned ZIP directory `ASSETS_DIR/{model_code}/` and its contents are left on disk.
- Impact: When a device model is deleted or its firmware is removed, versioned ZIP files accumulate on the filesystem indefinitely. At 200-device scale this is unlikely to cause disk pressure soon, but it is a correctness gap: the model is gone but its artifacts remain.
- Fix: Add cleanup of the versioned directory in `delete_firmware()`:
  ```python
  # Also clean up versioned ZIP directory if it exists
  model_dir = self.assets_dir / model_code
  if model_dir.exists() and model_dir.is_dir():
      import shutil
      try:
          shutil.rmtree(model_dir)
          logger.info("Deleted versioned firmware directory for model %s", model_code)
      except OSError as e:
          logger.warning("Failed to delete versioned dir for %s: %s", model_code, e)
  ```
- Confidence: High

- Title: `Major -- firmware_exists() only checks legacy path`
- Evidence: `/work/backend/app/services/firmware_service.py:99-108` -- `firmware_exists()` returns `self.get_firmware_path(model_code).exists()` which only checks the legacy flat `.bin`. Since `save_firmware_zip()` always writes the legacy `.bin` too, this works today. However, if the legacy write were ever removed (or if a future cleanup deletes only the flat file), `firmware_exists()` would return `False` even when a valid versioned ZIP exists.
- Impact: Low immediate risk because the dual-write ensures the legacy file always exists after a ZIP upload. But this creates a fragile coupling: any future change to stop writing the legacy `.bin` would silently break `firmware_exists()` and all callers that depend on it.
- Fix: Extend `firmware_exists()` to also check for the versioned directory:
  ```python
  def firmware_exists(self, model_code: str) -> bool:
      if self.get_firmware_path(model_code).exists():
          return True
      model_dir = self.assets_dir / model_code
      return model_dir.exists() and any(model_dir.glob("firmware-*.zip"))
  ```
- Confidence: Medium (no immediate breakage, but latent risk)

- Title: `Minor -- No input sanitization on device_key used in filesystem paths`
- Evidence: `/work/backend/app/services/coredump_service.py:81` -- `device_dir = self.coredumps_dir / device_key`. The `device_key` comes from `device.key` (looked up from the database) or `device_ctx.device_key` (from JWT). Since device keys are auto-generated 8-character alphanumeric strings, path traversal is unlikely in practice. However, the service does not validate that `device_key` contains only safe characters.
- Impact: If a device key were ever manipulated (compromised JWT, test data with unusual characters), a path traversal like `../../etc` could write outside `COREDUMPS_DIR`. The risk is low because keys are server-generated and validated on device creation.
- Fix: Add a simple guard at the top of `save_coredump()`:
  ```python
  if not device_key.isalnum():
      raise ValidationException("Invalid device key format")
  ```
- Confidence: Low (defense-in-depth; the existing key generation prevents this)

- Title: `Minor -- Sidecar JSON write is not atomic`
- Evidence: `/work/backend/app/services/coredump_service.py:115` -- `json_path.write_text(json.dumps(sidecar, indent=2))`. The `.dmp` file uses atomic write (temp file + `os.replace`), but the `.json` sidecar uses a direct `write_text()`. If the process crashes mid-write, the JSON could be truncated.
- Impact: A corrupted sidecar file. The coredump binary itself would be intact. Since coredumps are crash artifacts for offline analysis, a truncated sidecar is a minor inconvenience, not data loss.
- Fix: Use the same atomic write pattern for the JSON sidecar, or accept the risk given the low probability and low impact.
- Confidence: Medium


## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: Duplicated atomic write pattern in `save_firmware_zip()`
- Evidence: `/work/backend/app/services/firmware_service.py:260-286` -- The `mkstemp` / `os.write` / `os.close` / `os.replace` block is repeated twice: once for the versioned ZIP write and once for the legacy `.bin` write. The same pattern also appears in `save_firmware()` at lines 172-186.
- Suggested refactor: Extract a private `_atomic_write(target_path: Path, content: bytes, dir: Path) -> None` helper method. This eliminates the three copies of the try/except/unlink boilerplate.
- Payoff: Reduces duplication from ~30 lines to ~10. Makes the cleanup-on-failure logic a single point of maintenance.

- Hotspot: Duplicated `_create_test_firmware()` in test files
- Evidence: `/work/backend/tests/api/test_pipeline.py:153-172` (class method) and `/work/backend/tests/services/test_firmware_service.py:15-39` (module function) -- Both files contain identical implementations of `_create_test_firmware()`.
- Suggested refactor: Move to a shared test utility (e.g., `tests/testing_utils.py` or a conftest fixture) and import in both test files.
- Payoff: Single source of truth for test firmware generation; easier to update if the AppInfo format changes.


## 5) Style & Consistency

- Pattern: Inline `from flask import request` inside the coredump endpoint
- Evidence: `/work/backend/app/api/iot.py:374` -- `from flask import request` is imported inside the function body, while other endpoints in the same file import `request` at the module level via `from flask import Blueprint, Response, send_file`. The existing `get_config` endpoint also uses an inline import of `request` (line 92), so this is consistent with the pre-existing pattern in `iot.py`.
- Impact: None -- this follows the file's established pattern. Noting for awareness only.
- Recommendation: No change needed. If a future cleanup unifies imports, do it across all endpoints in `iot.py` at once.

- Pattern: `is_zip_content()` is a module-level function while all other firmware logic is in the class
- Evidence: `/work/backend/app/services/firmware_service.py:43-52` -- `is_zip_content()` is defined outside `FirmwareService`, and imported separately in `device_model_service.py` (`from app.services.firmware_service import is_zip_content`).
- Impact: Minor inconsistency. The function is stateless and does not need `self`, so a standalone function is reasonable. However, it could also be a `@staticmethod` on `FirmwareService` to keep all firmware-related logic co-located.
- Recommendation: Acceptable as-is. If the function grows or gains dependencies, move it into the class.


## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: CoredumpService
- Scenarios:
  - Given valid inputs, When `save_coredump()` is called, Then `.dmp` and `.json` files are created with correct content (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_creates_files`)
  - Given a new device key, When `save_coredump()` is called, Then the device directory is created (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_creates_device_directory`)
  - Given empty content, When `save_coredump()` is called, Then ValidationException is raised (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_empty_content_raises`)
  - Given oversized content, When `save_coredump()` is called, Then ValidationException is raised (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_exceeds_max_size_raises`)
  - Given exactly 1MB content, When `save_coredump()` is called, Then it succeeds (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_exactly_max_size_succeeds`)
  - Given `coredumps_dir` is None, When `save_coredump()` is called, Then InvalidOperationException is raised (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_no_coredumps_dir_raises`)
  - Given consecutive saves, When filenames are compared, Then all are unique (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_unique_filenames`)
  - Given multiple devices, When coredumps are saved, Then files go to separate directories (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_multiple_devices`)
  - Given a successful save, When sidecar is read, Then `uploaded_at` is valid ISO 8601 (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_sidecar_has_correct_uploaded_at`)
  - Given a new coredumps directory path, When service is initialized, Then directory is created (`tests/services/test_coredump_service.py::TestCoredumpServiceInit::test_init_creates_directory`)
  - Given None coredumps_dir, When service is initialized, Then no error is raised (`tests/services/test_coredump_service.py::TestCoredumpServiceInit::test_init_with_none_does_not_fail`)
- Hooks: `tmp_path` fixture, direct `CoredumpService` instantiation
- Gaps: None.
- Evidence: 11 tests covering all public methods and edge cases.

- Surface: FirmwareService ZIP support
- Scenarios:
  - Given a valid firmware ZIP, When `save_firmware_zip()` is called, Then versioned ZIP and legacy `.bin` are created (`tests/services/test_firmware_service.py::TestFirmwareServiceZipSave::test_save_firmware_zip_valid`)
  - Given ZIPs missing each of the 5 required files, When `save_firmware_zip()` is called, Then ValidationException is raised (5 separate tests in `TestFirmwareServiceZipSave`)
  - Given a ZIP with extra files, When `save_firmware_zip()` is called, Then ValidationException is raised (`tests/services/test_firmware_service.py::TestFirmwareServiceZipSave::test_save_firmware_zip_extra_files`)
  - Given a ZIP with invalid `.bin`, When `save_firmware_zip()` is called, Then ValidationException is raised (`tests/services/test_firmware_service.py::TestFirmwareServiceZipSave::test_save_firmware_zip_invalid_bin`)
  - Given a ZIP with malformed version.json, When `save_firmware_zip()` is called, Then ValidationException is raised (`tests/services/test_firmware_service.py::TestFirmwareServiceZipSave::test_save_firmware_zip_invalid_version_json`)
  - Given a ZIP with version.json missing fields, When `save_firmware_zip()` is called, Then ValidationException is raised (`tests/services/test_firmware_service.py::TestFirmwareServiceZipSave::test_save_firmware_zip_version_json_missing_fields`)
  - Given non-ZIP content, When `save_firmware_zip()` is called, Then ValidationException is raised (`tests/services/test_firmware_service.py::TestFirmwareServiceZipSave::test_save_firmware_zip_not_a_zip`)
  - Given same version re-uploaded, When `save_firmware_zip()` is called twice, Then it overwrites without error (`tests/services/test_firmware_service.py::TestFirmwareServiceZipSave::test_save_firmware_zip_overwrites_same_version`)
  - Given a versioned ZIP on disk, When `get_firmware_stream()` is called, Then `.bin` is extracted from ZIP (`tests/services/test_firmware_service.py::TestFirmwareServiceGetStream::test_get_stream_from_versioned_zip`)
  - Given only legacy `.bin`, When `get_firmware_stream()` is called with version, Then legacy is returned (`tests/services/test_firmware_service.py::TestFirmwareServiceGetStream::test_get_stream_falls_back_to_legacy_bin`)
  - Given only legacy `.bin`, When `get_firmware_stream()` is called without version, Then legacy is returned (`tests/services/test_firmware_service.py::TestFirmwareServiceGetStream::test_get_stream_no_version_uses_legacy`)
  - Given no firmware at all, When `get_firmware_stream()` is called, Then RecordNotFoundException is raised (`tests/services/test_firmware_service.py::TestFirmwareServiceGetStream::test_get_stream_neither_zip_nor_legacy_raises`)
- Hooks: `tmp_path` fixture, direct `FirmwareService` instantiation, `_create_test_firmware()` and `_create_test_zip()` helpers
- Gaps: None.
- Evidence: 17 tests covering `is_zip_content()`, `save_firmware_zip()`, and `get_firmware_stream()`.

- Surface: POST /api/iot/coredump endpoint
- Scenarios:
  - Given an authenticated device with valid params, When POST is made, Then 201 with filename and files on disk (`tests/api/test_iot.py::TestIotCoredump::test_upload_coredump_success`)
  - Given missing `chip` param, When POST is made, Then 400 (`tests/api/test_iot.py::TestIotCoredump::test_upload_coredump_missing_chip`)
  - Given missing `firmware_version` param, When POST is made, Then 400 (`tests/api/test_iot.py::TestIotCoredump::test_upload_coredump_missing_firmware_version`)
  - Given empty body, When POST is made, Then 400 (`tests/api/test_iot.py::TestIotCoredump::test_upload_coredump_empty_body`)
  - Given body > 1MB, When POST is made, Then 400 (`tests/api/test_iot.py::TestIotCoredump::test_upload_coredump_exceeds_max_size`)
  - Given no authentication, When POST is made, Then 401 (`tests/api/test_iot.py::TestIotCoredump::test_upload_coredump_no_auth`)
  - Given invalid device key, When POST is made, Then 404 (`tests/api/test_iot.py::TestIotCoredump::test_upload_coredump_invalid_device_key`)
- Hooks: `client` fixture, `create_test_device()` helper, `test_settings` fixture for filesystem assertions
- Gaps: None.
- Evidence: 7 API-level tests.

- Surface: Pipeline firmware ZIP upload
- Scenarios:
  - Given a valid firmware ZIP, When POST to pipeline endpoint, Then 200 with extracted version (`tests/api/test_pipeline.py::TestPipelineFirmwareZipUpload::test_upload_firmware_zip_success`)
  - Given a ZIP with invalid structure, When POST to pipeline endpoint, Then 400 (`tests/api/test_pipeline.py::TestPipelineFirmwareZipUpload::test_upload_firmware_zip_invalid_structure`)
  - Given a valid ZIP, When POST to pipeline endpoint, Then versioned ZIP and legacy `.bin` exist on disk (`tests/api/test_pipeline.py::TestPipelineFirmwareZipUpload::test_upload_firmware_zip_creates_versioned_file`)
  - Given a plain `.bin`, When POST to pipeline endpoint, Then 200 as before (`tests/api/test_pipeline.py::TestPipelineFirmwareZipUpload::test_upload_plain_bin_still_works`)
- Hooks: `container` fixture, `_create_test_firmware()` and `_create_test_zip()` helpers
- Gaps: None.
- Evidence: 4 API-level tests.

- Surface: Pipeline upload scripts (sh and ps1)
- Scenarios:
  - Given a request to upload.sh, When script is returned, Then it contains ZIP packaging references (`tests/api/test_pipeline.py::TestPipelineUploadScript::test_get_upload_script_contains_zip_packaging`)
  - Given a request to upload.ps1, When script is returned, Then it contains ZIP packaging references (`tests/api/test_pipeline.py::TestPipelineUploadScriptPowerShell::test_get_upload_script_contains_zip_packaging`)
- Hooks: `client` fixture
- Gaps: None.
- Evidence: 2 script content tests.

**Total: 46 new tests, all passing.**


## 7) Adversarial Sweep

- Title: `Major -- delete_firmware() orphans versioned ZIP directory`
- Evidence: `/work/backend/app/services/firmware_service.py:297-311` -- Only `self.get_firmware_path(model_code)` is deleted. The `ASSETS_DIR/{model_code}/` directory with versioned ZIPs is never cleaned up.
- Impact: Disk space leak. When device models are deleted (via `DeviceModelService.delete_device_model()`), the versioned firmware ZIPs remain on disk indefinitely.
- Fix: Extend `delete_firmware()` to also remove the versioned directory (see Finding in Section 3).
- Confidence: High

  Step-by-step failure reasoning:
  1. Admin creates device model "tempsensor" and uploads firmware ZIP.
  2. `save_firmware_zip()` writes `ASSETS_DIR/tempsensor/firmware-1.0.0.zip` and `ASSETS_DIR/firmware-tempsensor.bin`.
  3. Admin deletes device model "tempsensor".
  4. `DeviceModelService.delete_device_model()` calls `firmware_service.delete_firmware("tempsensor")`.
  5. `delete_firmware()` removes `ASSETS_DIR/firmware-tempsensor.bin` only.
  6. `ASSETS_DIR/tempsensor/firmware-1.0.0.zip` remains on disk, orphaned.

- Title: `Minor -- get_firmware_stream() silently falls back on corrupted ZIP`
- Evidence: `/work/backend/app/services/firmware_service.py:137-141` -- When a versioned ZIP exists but is corrupted (`BadZipFile`) or the `.bin` entry is missing (`KeyError`), the code logs a warning and falls through to the legacy `.bin`. This means a corrupted ZIP goes unnoticed as long as the legacy file exists.
- Impact: The device gets firmware, but the admin is unaware that the versioned ZIP is corrupted. In practice, this is a defensive pattern that ensures device availability, which is arguably correct for an IoT system.
- Fix: Acceptable as-is for availability. Consider adding a counter metric for ZIP extraction failures so the issue is observable.
- Confidence: Medium

- Checks attempted: Path traversal in coredump device_key, transaction safety in firmware upload, DI wiring completeness, migration requirements, `time.time()` usage
- Evidence: `/work/backend/app/services/coredump_service.py:81` -- `device_key` used directly in path (noted as Minor above). `/work/backend/app/services/device_model_service.py:236` -- `self.db.flush()` after firmware save ensures DB consistency before MQTT notification. `/work/backend/app/services/container.py:102-106` -- `coredump_service` properly wired. `/work/backend/app/__init__.py:70` -- `app.api.iot` already in wire list. No database schema changes so no migration needed. All timing uses `time.perf_counter()`.
- Why code held up: The DI wiring is correct, no database migration is needed (filesystem-only storage), timing measurements use `perf_counter()`, and the firmware upload path correctly flushes the DB session before MQTT notification.


## 8) Invariants Checklist

- Invariant: Every coredump `.dmp` file has a corresponding `.json` sidecar with the same base name.
  - Where enforced: `/work/backend/app/services/coredump_service.py:88-115` -- `base_name` is used to derive both `dmp_filename` and `json_filename`.
  - Failure mode: If the process crashes after writing the `.dmp` but before writing the `.json`, the sidecar will be missing.
  - Protection: The `.dmp` is written atomically first. The plan explicitly acknowledges this risk as acceptable (plan Section 7: "If the sidecar write fails, the `.dmp` file remains (orphaned but harmless)").
  - Evidence: `tests/services/test_coredump_service.py::test_save_coredump_creates_files` verifies both files exist after a successful save.

- Invariant: A versioned ZIP at `ASSETS_DIR/{model_code}/firmware-{version}.zip` always contains a `.bin` whose AppInfo version matches `{version}` in the filename.
  - Where enforced: `/work/backend/app/services/firmware_service.py:252-254` -- The version is extracted from the `.bin` inside the ZIP via `extract_version()`, and that same version string is used to construct the filename at line 261.
  - Failure mode: Could only break if the ZIP were replaced on disk by an external process.
  - Protection: Atomic write (`os.replace`) prevents partial ZIP files. Test `test_save_firmware_zip_valid` verifies the version round-trips correctly.
  - Evidence: `/work/backend/tests/services/test_firmware_service.py:109-130`

- Invariant: When a firmware ZIP is uploaded, both the versioned ZIP and the legacy `.bin` are written.
  - Where enforced: `/work/backend/app/services/firmware_service.py:256-286` -- ZIP written first, then legacy `.bin`.
  - Failure mode: If the legacy `.bin` write fails after the ZIP succeeds, the ZIP exists but the legacy path does not. The exception propagates, but the ZIP is already on disk.
  - Protection: Both writes use atomic temp file + replace. Test `test_save_firmware_zip_valid` and `test_upload_firmware_zip_creates_versioned_file` both verify both files exist.
  - Evidence: `/work/backend/tests/services/test_firmware_service.py:119-125` and `/work/backend/tests/api/test_pipeline.py:261-268`

- Invariant: The firmware download endpoint always returns a valid `.bin`, whether from a versioned ZIP or legacy path.
  - Where enforced: `/work/backend/app/services/firmware_service.py:128-148` -- Tries ZIP extraction first, falls back to legacy, raises `RecordNotFoundException` if neither exists.
  - Failure mode: If both the ZIP and legacy file are deleted while the DB still has `firmware_version` set, the device gets a 404.
  - Protection: `delete_firmware()` is best-effort and only called during model deletion (which removes the DB record too). Tests `test_get_stream_from_versioned_zip`, `test_get_stream_falls_back_to_legacy_bin`, and `test_get_stream_neither_zip_nor_legacy_raises` cover all paths.
  - Evidence: `/work/backend/tests/services/test_firmware_service.py:275-339`


## 9) Questions / Needs-Info

- Question: Should `delete_firmware()` clean up versioned ZIP directories?
- Why it matters: Without cleanup, deleting a device model leaks firmware ZIPs on disk. The plan's "out of scope" section mentions deferring retention policy, but basic cleanup on explicit delete is a different concern.
- Desired answer: Confirm that `delete_firmware()` should remove the `ASSETS_DIR/{model_code}/` directory alongside the legacy `.bin`.

- Question: Is the shell script's firmware version extraction reliable enough?
- Why it matters: `/work/backend/app/templates/upload_firmware.sh.j2:117` uses `strings -t d` with `awk` to extract the version from the binary. This is a best-effort heuristic that may pick up the wrong string if the binary layout changes. However, the backend re-extracts the version from the `.bin` inside the ZIP using the proper `extract_version()` method, so the version.json value is not authoritative -- it is metadata for human reference.
- Desired answer: Confirm that the `firmware_version` field in `version.json` is informational only, and the authoritative version comes from `extract_version()` on the server side.


## 10) Risks & Mitigations (top 3)

- Risk: `delete_firmware()` does not remove versioned ZIP directories, causing orphaned files on disk.
- Mitigation: Extend `delete_firmware()` to also clean up the `ASSETS_DIR/{model_code}/` directory. Add a test for this behavior.
- Evidence: `/work/backend/app/services/firmware_service.py:297-311`

- Risk: Legacy `.bin` write failure after successful ZIP write leaves inconsistent state (ZIP exists, legacy does not).
- Mitigation: The exception propagates, so the caller (and ultimately the HTTP response) signals failure. The orphaned ZIP is harmless -- `get_firmware_stream()` will find and serve it. Accept this as tolerable; adding rollback of the ZIP write would add complexity for a rare failure case.
- Evidence: `/work/backend/app/services/firmware_service.py:274-286`

- Risk: Upload scripts' ZIP file names may not match the expected `{model_code}.bin/elf/map` convention if the build output uses different naming.
- Mitigation: The scripts use `zip -j` (strip directory paths) and assume the build artifacts match the model code in filename. If they do not, the backend's ZIP validation will reject the upload with a clear error message. Document this naming requirement in the pipeline setup guide.
- Evidence: `/work/backend/app/templates/upload_firmware.sh.j2:139` and `/work/backend/app/services/firmware_service.py:222-226`


## 11) Confidence

Confidence: High -- The implementation closely follows the plan, all 46 new tests pass alongside the full 515-test suite, linting and type checking are clean, and the two Major findings are straightforward to address without architectural changes.
