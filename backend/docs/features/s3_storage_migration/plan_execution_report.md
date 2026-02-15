# Plan Execution Report: Migrate Firmware and Coredump Storage to S3

## Status

**DONE** — The plan was implemented successfully. All requirements verified, all code review findings resolved, full test suite passing.

## Summary

All five implementation slices from the plan were completed:

1. **S3Service extensions** — Added `list_objects(prefix)` and `delete_prefix(prefix)` to `app/services/s3_service.py`.
2. **Data model changes** — Created `FirmwareVersion` model, added migration 006 (create table + make `coredumps.filename` nullable), added migration 007 (drop `filename` column post-migration).
3. **FirmwareService rewrite** — Converted from filesystem-based Singleton to S3-based Factory. ZIP-only uploads with artifact extraction, generic S3 key naming, version tracking via `firmware_versions` table, retention pruning with PENDING coredump guard.
4. **CoredumpService refactor** — Replaced filesystem paths with S3 operations. Coredumps keyed as `coredumps/{device_key}/{id}.dmp`. Parsing thread downloads `.dmp` and `.elf` from S3.
5. **CLI migration command** — `migrate-to-s3` command with `--dry-run` support, idempotent execution, firmware ZIP extraction, coredump ID-based rekeying.

Supporting changes: DI container wiring, API endpoint updates, schema changes, configuration updates, and comprehensive test rewrites.

## Code Review Summary

**Verdict**: `GO-WITH-CONDITIONS` (all conditions resolved)

| Severity | Count | Resolved |
|----------|-------|----------|
| Blocker  | 0     | N/A      |
| Major    | 1     | Yes      |
| Minor    | 2     | Yes      |

**Resolved findings:**

1. **Major — Stale docstring** in `DeviceModelService.get_firmware_stream` referencing legacy fallback behavior. Fixed: updated docstring to describe current S3-based behavior (`app/services/device_model_service.py:254-258`).
2. **Minor — Redundant logger import** inside `S3Service.delete_prefix()`. Fixed: moved `import logging` and `logger` to module level (`app/services/s3_service.py:4,16`).
3. **Minor — Misleading comment** in coredump retention saying "after DB commit" when it's after flush. Fixed: changed to "after DB flush" (`app/services/coredump_service.py:228`).

**Question from review** — Whether migration 007 should be in this changeset or deferred. Answer: Keep it in the changeset. The deployment process involves brief downtime with manual steps (apply 006, run `migrate-to-s3` CLI, apply 007). The migration file header clearly documents the sequencing requirement. Splitting into a separate PR adds no safety and complicates the deployment.

## Verification Results

**Ruff** (after fixes):
```
All checks passed!
```

**Mypy** (after fixes):
```
Found 98 errors in 8 files (checked 105 source files)
```
All 98 errors are pre-existing in unrelated files. Zero new errors introduced.

**Pytest** (after fixes):
```
494 passed, 203 warnings in 50.58s
```
All tests pass. Warnings are pre-existing `datetime.utcnow()` deprecations in unrelated test files.

**Requirements verification**: 21/21 checklist items PASS (see `requirements_verification.md`).

## Files Changed

### New files
- `app/models/firmware_version.py` — FirmwareVersion SQLAlchemy model
- `app/services/migration_service.py` — One-time filesystem-to-S3 migration service
- `alembic/versions/006_firmware_versions_and_nullable_filename.py` — Create firmware_versions table, make filename nullable
- `alembic/versions/007_drop_coredumps_filename.py` — Drop filename column (post-migration)
- `tests/services/test_migration_service.py` — 13 migration service tests
- `docs/features/s3_storage_migration/change_brief.md`
- `docs/features/s3_storage_migration/plan.md`
- `docs/features/s3_storage_migration/plan_review.md`
- `docs/features/s3_storage_migration/requirements_verification.md`
- `docs/features/s3_storage_migration/code_review.md`

### Modified files
- `app/services/s3_service.py` — Added `list_objects`, `delete_prefix`, module-level logger
- `app/services/firmware_service.py` — Complete rewrite: S3-based Factory
- `app/services/coredump_service.py` — Refactored: S3-based storage
- `app/services/device_model_service.py` — ZIP-only uploads, updated docstrings
- `app/services/container.py` — FirmwareService as Factory, CoredumpService wiring updated
- `app/models/device_model.py` — Added `firmware_versions` relationship
- `app/models/coredump.py` — Made `filename` nullable
- `app/models/__init__.py` — Added FirmwareVersion export
- `app/app_config.py` — Added `MAX_FIRMWARES`, legacy section for old paths
- `app/startup.py` — Added `migrate-to-s3` CLI command
- `app/api/iot.py` — Coredump upload returns `coredump_id`
- `app/api/coredumps.py` — S3-based download
- `app/api/device_models.py` — S3 streaming for firmware
- `app/schemas/coredump.py` — Removed `filename` field
- `CLAUDE.md` — Added S3 Storage Consistency golden rules
- `tests/conftest.py` — Removed filesystem fixtures, added `max_firmwares`
- `tests/services/test_firmware_service.py` — Complete rewrite
- `tests/services/test_coredump_service.py` — Rewritten for S3
- `tests/api/test_coredumps.py` — Updated for S3
- `tests/api/test_device_models.py` — Updated for ZIP uploads
- `tests/api/test_iot.py` — Updated for S3
- `tests/api/test_testing.py` — Removed filename expectations
- `tests/api/test_pipeline.py` — Updated for S3

## Outstanding Work & Suggested Improvements

No outstanding work required. All plan requirements implemented, all review findings resolved, all tests passing.

**Suggested follow-up improvements** (non-blocking):

- **Refactor duplicated S3 delete pattern**: The code review noted that `coredump_service.py` has three copies of the best-effort S3 deletion try/except pattern (`delete_coredump`, `delete_all_coredumps`, `_enforce_retention`). Extracting a `_best_effort_s3_delete(device_key, coredump_id)` helper would reduce duplication.
- **Runtime guard in migration 007**: Consider adding a check in the Alembic migration that verifies no rows have a non-null `filename` before dropping the column, providing a clearer error if `migrate-to-s3` hasn't been run.
