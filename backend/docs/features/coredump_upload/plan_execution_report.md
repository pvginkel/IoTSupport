# Plan Execution Report: Coredump Upload & Firmware ZIP Support

## Status

Status: DONE — The plan was implemented successfully, all requirements verified, code review findings resolved.

## Summary

All 17 requirements from the User Requirements Checklist have been implemented, tested, and verified. The implementation adds two capabilities:

1. **Coredump Upload** — A new `POST /api/iot/coredump` endpoint accepts raw binary coredump uploads from ESP32 devices. Coredumps are stored on the filesystem in per-device directories with JSON sidecar metadata files. The endpoint enforces a 1MB size limit and requires `chip` and `firmware_version` query parameters.

2. **Firmware ZIP Support** — The firmware upload pipeline now accepts ZIP bundles containing `.bin`, `.elf`, `.map`, `sdkconfig`, and `version.json` files. ZIPs are validated for structure, the firmware version is extracted from the embedded `.bin`, and the archive is stored as `ASSETS_DIR/{model_code}/firmware-{version}.zip`. Legacy `.bin` uploads continue to work. Device firmware downloads prefer the versioned ZIP when available, falling back to the legacy loose `.bin`.

### Files Created

- `app/services/coredump_service.py` — CoredumpService for filesystem-based coredump storage
- `tests/services/test_coredump_service.py` — 13 tests for CoredumpService
- `tests/services/test_firmware_service.py` — 28 tests for FirmwareService ZIP support
- `docs/features/coredump_upload/change_brief.md` — Feature description
- `docs/features/coredump_upload/plan.md` — Implementation plan
- `docs/features/coredump_upload/plan_review.md` — Plan review
- `docs/features/coredump_upload/requirements_verification.md` — Requirements verification (17/17 PASS)
- `docs/features/coredump_upload/code_review.md` — Code review
- `docs/features/coredump_upload/plan_execution_report.md` — This report

### Files Modified

- `app/config.py` — Added `COREDUMPS_DIR` environment variable
- `app/services/firmware_service.py` — Added ZIP support, `_atomic_write` helper, versioned storage, ZIP-aware `firmware_exists()` and `delete_firmware()`
- `app/services/container.py` — Wired CoredumpService as Singleton
- `app/api/iot.py` — Added `POST /coredump` endpoint, updated firmware download to pass version
- `app/services/device_model_service.py` — ZIP detection and routing in `upload_firmware()`
- `app/templates/upload_firmware.sh.j2` — ZIP packaging with version.json generation
- `app/templates/upload_firmware.ps1.j2` — ZIP packaging with version.json generation
- `tests/conftest.py` — Added `coredumps_dir` config, shared `create_test_firmware()` helper
- `tests/api/test_iot.py` — 7 new tests for coredump endpoint
- `tests/api/test_pipeline.py` — 6 new tests for ZIP upload + script content, deduplicated test helper

## Code Review Summary

The code review resulted in a **GO-WITH-CONDITIONS** decision. All findings were resolved:

| Severity | Finding | Resolution |
|----------|---------|------------|
| Major | `delete_firmware()` doesn't clean up versioned ZIP directories | Added `shutil.rmtree()` cleanup of `ASSETS_DIR/{model_code}/` directory. Added 3 tests. |
| Major | `firmware_exists()` only checks legacy path | Extended to also check for versioned ZIP files via `model_dir.glob("firmware-*.zip")`. Added 3 tests. |
| Minor | No input sanitization on `device_key` in filesystem paths | Added `isalnum()` guard as defense-in-depth. Added 2 tests. |
| Minor | Sidecar JSON write is not atomic | Changed to use temp file + `os.replace()` pattern. |
| Refactoring | Duplicated atomic write pattern in `firmware_service.py` | Extracted `_atomic_write()` static method, consolidated 3 copies. |
| Refactoring | Duplicated `_create_test_firmware()` across test files | Moved to shared `create_test_firmware()` in `tests/conftest.py`, removed 2 duplicates. |

## Verification Results

### Linting (`poetry run ruff check .`)

```
(no output — all clean)
```

### Type Checking (`poetry run mypy .`)

```
Success: no issues found in 95 source files
```

### Test Suite (`poetry run pytest`)

```
523 passed, 165 warnings in 17.29s
```

All 523 tests pass. The 8 new tests added during code review resolution bring the total from 515 to 523.

### Requirements Verification

All 17 requirements from the User Requirements Checklist passed verification with concrete code and test evidence. See `requirements_verification.md` for details.

## Outstanding Work & Suggested Improvements

No outstanding work required. All issues identified during code review have been resolved.

**Suggested future improvements** (not blocking):

- **Coredump retention policy**: Consider adding automatic cleanup of old coredumps (e.g., keep only the last N per device, or delete after M days). This was explicitly out of scope per the plan.
- **Coredump analysis**: The storage foundation is in place. A future phase can add ESP32 coredump parsing using the ELF from the versioned ZIP to produce human-readable stack traces.
- **ZIP extraction failure metric**: The `get_firmware_stream()` method silently falls back to legacy `.bin` when a versioned ZIP is corrupted. Adding a Prometheus counter for ZIP extraction failures would improve observability.
