# Requirements Verification Report: Coredump Upload & Firmware ZIP Support

## Verification Summary

This report verifies that each requirement from the User Requirements Checklist (section 1a of `docs/features/coredump_upload/plan.md`) has been implemented and tested.

---

## Requirement Verification

### 1. New `POST /iot/coredump` endpoint accepts raw binary body containing the coredump

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/api/iot.py:353-420` — Endpoint defined with `@iot_bp.route("/coredump", methods=["POST"])`, reads raw binary body via `request.get_data()`, delegates to `coredump_service.save_coredump()`
- Tests: `tests/api/test_iot.py:335-372` — `test_upload_coredump_success()` verifies coredump upload and file persistence

---

### 2. `chip` is a required query string parameter on the coredump endpoint

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/api/iot.py:377-379` — Validates `chip = request.args.get("chip")` and raises `ValidationException("Missing required query parameter: chip")` if missing
- Tests: `tests/api/test_iot.py:373-388` — `test_upload_coredump_missing_chip()` verifies 400 response when chip is omitted

---

### 3. `firmware_version` is a required query string parameter on the coredump endpoint

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/api/iot.py:381-383` — Validates `firmware_version = request.args.get("firmware_version")` and raises `ValidationException("Missing required query parameter: firmware_version")` if missing
- Tests: `tests/api/test_iot.py:389-404` — `test_upload_coredump_missing_firmware_version()` verifies 400 response when firmware_version is omitted

---

### 4. New `COREDUMPS_DIR` environment variable controls coredump storage location

**Status**: ✅ PASS

**Evidence**:
- Configuration: `app/config.py:82-85` — `COREDUMPS_DIR: Path | None` field added to `Environment` class
- Configuration: `app/config.py:264` — `coredumps_dir: Path | None = None` field added to `Settings` class
- Configuration: `app/config.py:494` — `coredumps_dir=env.COREDUMPS_DIR` passed in `Settings.load()`
- Tests: `tests/conftest.py:61-62` — Test setup creates and configures `coredumps_dir`

---

### 5. Coredumps stored in per-device directories: `COREDUMPS_DIR/{device_key}/`

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/coredump_service.py:81-82` — Creates per-device directory: `device_dir = self.coredumps_dir / device_key; device_dir.mkdir(parents=True, exist_ok=True)`
- Tests: `tests/services/test_coredump_service.py:163-186` — `test_save_coredump_multiple_devices()` verifies coredumps from different devices go to separate directories

---

### 6. Coredump files named with ISO 8601 timestamps: `coredump_YYYYMMDDTHHMMSSZ.dmp`

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/coredump_service.py:84-88` — Generates timestamp `now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}Z"` and creates filename `f"coredump_{timestamp}.dmp"` (note: microsecond precision added to avoid collisions)
- Tests: `tests/services/test_coredump_service.py:15-34` — `test_save_coredump_creates_files()` verifies filename format starts with `"coredump_"` and ends with `".dmp"`
- Tests: `tests/services/test_coredump_service.py:145-162` — `test_save_coredump_unique_filenames()` verifies consecutive saves produce unique filenames

---

### 7. JSON sidecar file alongside each coredump (same name, `.json` extension) containing chip, firmware_version, device_key, model_code, uploaded_at

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/coredump_service.py:107-115` — Creates sidecar dict with all required fields and writes as JSON with matching base name
- Tests: `tests/services/test_coredump_service.py:36-45` — `test_save_coredump_creates_files()` verifies `.json` sidecar exists with correct metadata (chip, firmware_version, device_key, model_code, uploaded_at)

---

### 8. 1MB maximum upload size enforced

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/coredump_service.py:14-15` — `MAX_COREDUMP_SIZE = 1_048_576` defined
- Implementation: `app/services/coredump_service.py:77-78` — Validates `if len(content) > MAX_COREDUMP_SIZE: raise ValidationException("Coredump exceeds maximum size of 1MB")`
- Tests: `tests/services/test_coredump_service.py:79-91` — `test_save_coredump_exceeds_max_size_raises()` verifies size limit enforcement
- Tests: `tests/services/test_coredump_service.py:93-109` — `test_save_coredump_exactly_max_size_succeeds()` verifies exactly 1MB is accepted
- Tests: `tests/api/test_iot.py:421-438` — `test_upload_coredump_exceeds_max_size()` verifies 400 response for oversized uploads

---

### 9. No database model for coredumps -- filesystem storage only

**Status**: ✅ PASS

**Evidence**:
- No database model exists for coredumps
- Implementation: `app/services/coredump_service.py:1-127` — Service is filesystem-only, no database session used
- No migrations created for coredumps
- Tests: All coredump tests use only filesystem operations with `tmp_path`

---

### 10. Firmware upload pipeline endpoint extended to accept ZIP files

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/device_model_service.py:205-255` — `upload_firmware()` detects ZIP via `is_zip_content()` and routes to `save_firmware_zip()` or `save_firmware()` accordingly
- Implementation: `app/api/pipeline.py:28-87` — Pipeline endpoint accepts both `.bin` and `.zip` content
- Tests: `tests/api/test_pipeline.py:196-217` — `test_upload_firmware_zip_success()` verifies ZIP upload returns 200 with correct version

---

### 11. ZIP must contain `{model_code}.bin`, `{model_code}.elf`, `{model_code}.map`, `sdkconfig`, `version.json` -- reject if structure is invalid

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/firmware_service.py:40` — `REQUIRED_ZIP_FILES` set defines exact required files
- Implementation: `app/services/firmware_service.py:216-233` — Validates ZIP contains exactly required files, rejects if missing or extra files present
- Tests: `tests/services/test_firmware_service.py:132-184` — Tests for each missing file (.elf, .map, sdkconfig, version.json, .bin) verify validation
- Tests: `tests/services/test_firmware_service.py:175-184` — `test_save_firmware_zip_extra_files()` verifies rejection of unexpected files
- Tests: `tests/api/test_pipeline.py:219-242` — `test_upload_firmware_zip_invalid_structure()` verifies 400 response for malformed ZIP

---

### 12. `version.json` in ZIP contains build metadata: `git_commit`, `idf_version`, `firmware_version`

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/firmware_service.py:235-249` — Validates `version.json` is valid JSON and contains all required fields (git_commit, idf_version, firmware_version)
- Tests: `tests/services/test_firmware_service.py:209-247` — Tests verify version.json validation and required fields
- Script template: `app/templates/upload_firmware.sh.j2:129-135` — Shell script generates version.json with required fields
- Script template: `app/templates/upload_firmware.ps1.j2:105-109` — PowerShell script generates version.json with required fields

---

### 13. Firmware version extracted from `.bin` inside the ZIP

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/firmware_service.py:251-254` — Extracts `.bin` from ZIP and calls `extract_version()` on it
- Implementation: `app/services/firmware_service.py:313-361` — `extract_version()` parses ESP32 AppInfo header to extract version string
- Tests: `tests/services/test_firmware_service.py:109-130` — `test_save_firmware_zip_valid()` verifies version is correctly extracted and matches AppInfo
- Tests: `tests/services/test_firmware_service.py:186-207` — `test_save_firmware_zip_invalid_bin()` verifies validation of binary format

---

### 14. ZIP stored as `ASSETS_DIR/{model_code}/firmware-{version}.zip` preserving historical versions

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/firmware_service.py:87-97` — `get_versioned_zip_path()` returns `self.assets_dir / model_code / f"firmware-{firmware_version}.zip"`
- Implementation: `app/services/firmware_service.py:256-272` — `save_firmware_zip()` creates model subdirectory and writes ZIP to versioned path
- Tests: `tests/services/test_firmware_service.py:109-130` — `test_save_firmware_zip_valid()` verifies ZIP is stored at `ASSETS_DIR/{code}/firmware-{version}.zip`
- Tests: `tests/api/test_pipeline.py:243-271` — `test_upload_firmware_zip_creates_versioned_file()` verifies versioned ZIP exists on disk

---

### 15. Plain `.bin` uploads still supported for backward compatibility

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/device_model_service.py:228-232` — Routes to `save_firmware()` if not ZIP
- Implementation: `app/services/firmware_service.py:150-188` — `save_firmware()` continues to support raw `.bin` uploads
- Tests: `tests/api/test_pipeline.py:273-293` — `test_upload_plain_bin_still_works()` verifies plain `.bin` upload still works
- Tests: Existing firmware upload tests continue to pass, verifying backward compatibility

---

### 16. Device firmware download serves `.bin` extracted from versioned ZIP when available, falls back to legacy loose `.bin`

**Status**: ✅ PASS

**Evidence**:
- Implementation: `app/services/firmware_service.py:110-148` — `get_firmware_stream()` accepts optional `firmware_version` parameter, tries versioned ZIP first, falls back to legacy flat `.bin`
- Implementation: `app/api/iot.py:207-208` — Device firmware endpoint looks up device model and passes `firmware_version` to `get_firmware_stream()`
- Implementation: `app/services/device_model_service.py:273-276` — Admin firmware download also passes `firmware_version` to `get_firmware_stream()`
- Tests: `tests/services/test_firmware_service.py:275-339` — Multiple tests verify ZIP fallback behavior:
  - `test_get_stream_from_versioned_zip()` — Extracts .bin from ZIP when available
  - `test_get_stream_fallback_to_legacy()` — Falls back to legacy .bin when ZIP doesn't exist
  - `test_get_stream_with_no_version_uses_legacy()` — Uses legacy path when version is None

---

### 17. Pipeline upload scripts (sh and ps1 templates) updated to package build artifacts into ZIP and upload

**Status**: ✅ PASS

**Evidence**:
- Shell script: `app/templates/upload_firmware.sh.j2:110-154` — Packages firmware into ZIP when all artifacts are available:
  - Generates version.json with git_commit, idf_version, firmware_version
  - Uses `zip` command to create ZIP with .bin, .elf, .map, sdkconfig, version.json
  - Falls back to raw .bin upload if artifacts not available
- PowerShell script: `app/templates/upload_firmware.ps1.j2:86-128` — Same ZIP packaging logic:
  - Generates version.json with required fields
  - Uses `Compress-Archive` to create ZIP with all artifacts
  - Falls back to raw .bin upload if artifacts not available
- Tests: `tests/api/test_pipeline.py` includes helper `_create_test_zip()` and tests verify script endpoints return updated scripts

---

## Summary

**Total Requirements**: 17  
**Passed**: 17  
**Failed**: 0

All requirements have been successfully implemented with:
- Functional implementations in services, API endpoints, and configuration
- Comprehensive unit and integration tests covering both happy paths and error cases
- Proper configuration management with environment variables
- Backward compatibility for legacy firmware uploads
- Updated CI/CD scripts with ZIP packaging support

The implementation is production-ready and follows the established codebase patterns for dependency injection, error handling, and testing.
