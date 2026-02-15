# Code Review: Migrate Firmware and Coredump Storage to S3

## 1) Summary & Decision

**Readiness**

This is a well-executed, large-scope migration that moves firmware and coredump storage from the local filesystem to S3. The diff spans 23 files with +1225/-945 lines, touching models, services, schemas, API endpoints, migrations, CLI tooling, and their tests. The implementation follows the approved plan closely, adheres to the project's S3 golden rules, and demonstrates strong architectural judgment (FirmwareService Singleton-to-Factory conversion, CoredumpService decoupled from FirmwareService, two-phase column removal). All 172 affected tests pass. Ruff and mypy produce zero new errors. Three findings are noted below -- one Major (stale docstring referencing removed behavior) and two Minor -- but none block the change.

**Decision**

`GO-WITH-CONDITIONS` -- The implementation is fundamentally sound. The one Major finding (stale docstring) and two Minor findings should be addressed before merge but require no structural changes.

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- `plan.md Section 2 (FirmwareService S3 refactor)` <-> `app/services/firmware_service.py:73-198` -- FirmwareService is now a Factory with `db: Session`, `s3_service`, and `max_firmwares`. ZIP-only uploads, artifact renaming to generic names, and DB version tracking all implemented as planned.
- `plan.md Section 2 (CoredumpService S3 refactor)` <-> `app/services/coredump_service.py:44-188` -- CoredumpService receives `s3_service` directly instead of `coredumps_dir` and `firmware_service`. S3 key layout `coredumps/{device_key}/{id}.dmp` is correctly implemented.
- `plan.md Section 3 (firmware_versions table)` <-> `app/models/firmware_version.py:14-58` -- New model with `id`, `device_model_id` (FK CASCADE), `version`, `uploaded_at`, `created_at`, and unique constraint `(device_model_id, version)`.
- `plan.md Section 3 (coredumps.filename nullable)` <-> `alembic/versions/006_firmware_versions_and_nullable_filename.py:53-58` -- Migration 006 makes `filename` nullable using `batch_alter_table`.
- `plan.md Section 3 (drop filename column)` <-> `alembic/versions/007_drop_coredumps_filename.py:27-28` -- Migration 007 drops the column with a clear header comment about sequencing.
- `plan.md Section 4 (CLI migrate-to-s3)` <-> `app/startup.py:212-276` and `app/services/migration_service.py:1-299` -- CLI command with `--dry-run` support, firmware ZIP extraction with generic names, coredump ID-based rekeying, and idempotent execution.
- `plan.md Section 5 (Firmware retention pruning)` <-> `app/services/firmware_service.py:328-394` -- `_enforce_retention` queries excess versions, protects those with PENDING coredumps, and does best-effort S3 deletion.
- `plan.md Section 5 (Coredump parsing thread)` <-> `app/services/coredump_service.py:284-414` -- Downloads `.dmp` and `.elf` directly from S3 via `self.s3_service`. Deterministic S3 key `firmware/{model_code}/{firmware_version}/firmware.elf`.
- `plan.md Section 2 (S3Service extensions)` <-> `app/services/s3_service.py:233-287` -- `list_objects(prefix)` and `delete_prefix(prefix)` added with paginator support.
- `plan.md Section 4 (container wiring)` <-> `app/services/container.py:160-174` -- FirmwareService is `providers.Factory` with `db=db_session, s3_service=s3_service, max_firmwares=...`; CoredumpService Singleton receives `s3_service` directly; `firmware_service` and `coredumps_dir` removed from CoredumpService constructor.
- `plan.md Section 3 (AppEnvironment/AppSettings)` <-> `app/app_config.py:31-42,81-92` -- `ASSETS_DIR` and `COREDUMPS_DIR` moved to "Legacy" section; `MAX_FIRMWARES` added with default 5.
- `plan.md Section 4 (coredump upload response)` <-> `app/api/iot.py:70-82` -- Returns `{"status": "ok", "coredump_id": <int>}` instead of `filename`.
- `plan.md Section 3 (schema changes)` <-> `app/schemas/coredump.py:12-14` -- `filename` field removed from `CoredumpBaseSchema`.

**Gaps / deviations**

- `plan.md Section 2 (ASSETS_DIR/COREDUMPS_DIR removal)` -- The plan says "Remove ASSETS_DIR and COREDUMPS_DIR from config." The implementation keeps them as "Legacy" fields with a comment explaining they are used only by the CLI migration command. This is a reasonable deviation -- the fields are needed for the migration path and are clearly documented.
- `plan.md Section 5 (coredump upload ordering note)` -- The plan includes a bold NOTE about the intentional order change (DB flush before S3 upload). The code at `app/services/coredump_service.py:153-173` implements this correctly with clear step comments, matching the golden rule.

## 3) Correctness -- Findings (ranked)

- Title: `Major -- Stale docstring in DeviceModelService.get_firmware_stream references legacy fallback`
- Evidence: `app/services/device_model_service.py:254-258` -- `"""...Passes the model's firmware_version to FirmwareService so it can try the versioned ZIP before falling back to the legacy flat .bin."""`
- Impact: Developer confusion. The docstring describes behavior that no longer exists -- there is no legacy flat .bin fallback. FirmwareService now downloads directly from S3 at `firmware/{model_code}/{version}/firmware.bin`.
- Fix: Update the docstring to: `"""Get firmware stream for a device model. Returns a BytesIO for use with Flask's send_file. Downloads the .bin from S3 via FirmwareService."""`
- Confidence: High

  **Reasoning**: The method body at `app/services/device_model_service.py:269-273` calls `self.firmware_service.get_firmware_stream(model.code, firmware_version=model.firmware_version)` which, in the new FirmwareService (`app/services/firmware_service.py:123-145`), no longer has any legacy fallback. The docstring is factually wrong.

- Title: `Minor -- Redundant logger import inside delete_prefix method`
- Evidence: `app/services/s3_service.py:272-273` -- `import logging` and `logger = logging.getLogger(__name__)` are defined locally inside `delete_prefix()`.
- Impact: No functional issue -- the module already has a module-level logger defined. The local import/definition is redundant and inconsistent with the rest of the file.
- Fix: Remove the two lines and use the module-level `logger` that already exists.
- Confidence: High

- Title: `Minor -- Coredump retention S3 deletion described as "after DB commit" but actually happens after flush, before commit`
- Evidence: `app/services/coredump_service.py:228` -- Comment says `# Best-effort S3 deletion after DB commit` but the preceding code at line 226 does `session.flush()`, not `session.commit()`. The actual commit happens at teardown_request.
- Impact: Misleading comment. The golden rule for deletes states "deletes commit+best-effort-S3-delete." In this request-scoped context, the flush makes the deletes visible within the transaction, but the S3 deletion happens before the final commit. If a later error causes a rollback, the S3 objects are already gone. However, since this is a retention path (best-effort), the practical impact is negligible -- orphaned S3 objects are acceptable by policy.
- Fix: Change comment to `# Best-effort S3 deletion after DB flush (commit happens at teardown)`.
- Confidence: Medium

  **Reasoning**: The `_enforce_retention` method is called within `save_coredump`, which runs in a request-scoped session. The session commits at `teardown_request`. The S3 deletions at lines 229-234 happen after `flush()` but before the final commit. If a subsequent operation in the same request fails, the transaction rolls back but the S3 objects are already deleted. Since the CLAUDE.md policy explicitly states "S3 cleanup is best-effort" and orphans are acceptable, this is not a correctness bug -- but the comment should be precise.

## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: Coredump delete operations have duplicated S3 deletion logic
- Evidence: `app/services/coredump_service.py:547-552` (`delete_coredump`), `app/services/coredump_service.py:573-579` (`delete_all_coredumps`), and `app/services/coredump_service.py:229-234` (`_enforce_retention`) all have identical try/except patterns for S3 deletion.
- Suggested refactor: Extract a `_best_effort_s3_delete(self, device_key: str, coredump_id: int) -> None` helper.
- Payoff: Reduces 3 copies of the same pattern to 1, making it easier to update if the logging or error handling changes.

## 5) Style & Consistency

- Pattern: S3 golden rule adherence is consistent across all write paths
- Evidence: `app/services/firmware_service.py:176-187` (firmware: flush DB, then upload to S3), `app/services/coredump_service.py:153-173` (coredump: flush DB, then upload to S3), `app/services/firmware_service.py:210-229` (delete firmware: delete DB, flush, then best-effort S3 delete), `app/services/coredump_service.py:541-552` (delete coredump: delete DB, flush, then best-effort S3 delete).
- Impact: Positive. All four storage operation patterns correctly follow the golden rules documented in CLAUDE.md.
- Recommendation: None -- this is well done.

- Pattern: FirmwareService no longer inherits from BaseService despite having a `self.db` attribute
- Evidence: `app/services/firmware_service.py:73-94` -- Class has `self.db = db` in constructor but does not inherit from any base.
- Impact: None -- the project has no `BaseService` class. The CLAUDE.md mentions it conceptually but no implementation exists. The pattern is consistent with other Factory services in the codebase (e.g., `DeviceModelService`, `DeviceService`).
- Recommendation: None -- consistent with codebase patterns.

## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: FirmwareService (S3-based save, delete, retention)
- Scenarios:
  - Given a valid ZIP, When `save_firmware` is called, Then 5 S3 objects are created and firmware_versions record exists (`tests/services/test_firmware_service.py::TestFirmwareServiceSave::test_save_firmware_valid_zip`)
  - Given raw .bin content, When `save_firmware` is called, Then ValidationException is raised (`tests/services/test_firmware_service.py::TestFirmwareServiceSave::test_save_firmware_non_zip_rejected`)
  - Given ZIP missing required files, When `save_firmware` is called, Then ValidationException is raised (6 tests for various missing files and extra files)
  - Given same version re-uploaded, When `save_firmware` is called, Then exactly one firmware_versions record exists (`tests/services/test_firmware_service.py::TestFirmwareServiceSave::test_save_firmware_zip_overwrites_same_version`)
  - Given firmware in S3, When `get_firmware_stream` is called, Then valid .bin BytesIO returned (`tests/services/test_firmware_service.py::TestFirmwareServiceGetStream::test_get_stream_from_s3`)
  - Given no firmware_version, When `get_firmware_stream` is called, Then RecordNotFoundException (`tests/services/test_firmware_service.py::TestFirmwareServiceGetStream::test_get_stream_no_version_raises`)
  - Given firmware exists, When `delete_firmware` is called, Then DB records and S3 objects removed (`tests/services/test_firmware_service.py::TestFirmwareServiceDelete::test_delete_firmware_removes_s3_and_db`)
  - Given no firmware, When `delete_firmware` is called, Then no error (`tests/services/test_firmware_service.py::TestFirmwareServiceDelete::test_delete_firmware_no_firmware_no_error`)
  - Given `firmware_exists`, When firmware is uploaded, Then returns True (`tests/services/test_firmware_service.py::TestFirmwareServiceExists::test_firmware_exists_after_upload`)
- Hooks: Container provides `firmware_service()` as Factory; S3Service (real, test bucket); `_create_model` helper creates DeviceModel records directly
- Gaps: None
- Evidence: `tests/services/test_firmware_service.py` (25 tests)

- Surface: Firmware retention (MAX_FIRMWARES + PENDING guard)
- Scenarios:
  - Given MAX_FIRMWARES=3 and 4 versions uploaded, When retention runs, Then oldest version pruned from DB and S3 (`tests/services/test_firmware_service.py::TestFirmwareRetention::test_retention_prunes_oldest`)
  - Given oldest excess version referenced by PENDING coredump, When retention runs, Then that version is preserved and next-oldest is pruned (`tests/services/test_firmware_service.py::TestFirmwareRetention::test_retention_protects_pending_coredumps`)
  - Given all excess versions protected by PENDING coredumps, When retention runs, Then all versions preserved (`tests/services/test_firmware_service.py::TestFirmwareRetention::test_retention_all_protected_no_prune`)
  - Given version count within limit, When retention runs, Then nothing pruned (`tests/services/test_firmware_service.py::TestFirmwareRetention::test_retention_within_limit_no_prune`)
- Hooks: Direct `FirmwareService` instantiation with `max_firmwares=3` or `max_firmwares=2`; CoreDump records with `ParseStatus.PENDING`; Device records for FK constraints
- Gaps: None
- Evidence: `tests/services/test_firmware_service.py::TestFirmwareRetention` (4 tests)

- Surface: CoredumpService (S3-based save, delete, retention, parsing)
- Scenarios:
  - Given valid content, When `save_coredump` is called, Then DB record created and S3 object exists (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_creates_s3_object_and_record`)
  - Given empty/oversized/invalid content, When `save_coredump` is called, Then ValidationException raised (3 tests)
  - Given consecutive saves, When multiple coredumps saved, Then unique IDs returned (`tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_unique_ids`)
  - Given MAX_COREDUMPS exceeded, When retention runs, Then oldest record and S3 object deleted (`tests/services/test_coredump_service.py::TestCoredumpServiceRetention::test_retention_deletes_oldest_when_exceeded`)
  - Given saved coredump, When `get_coredump_stream` is called, Then content matches (`tests/services/test_coredump_service.py::TestCoredumpServiceCRUD::test_get_coredump_stream_success`)
  - Given missing S3 object, When `get_coredump_stream` is called, Then RecordNotFoundException (`tests/services/test_coredump_service.py::TestCoredumpServiceCRUD::test_get_coredump_stream_not_found_raises`)
  - Given saved coredump, When `delete_coredump` is called, Then DB record and S3 object removed (`tests/services/test_coredump_service.py::TestCoredumpServiceCRUD::test_delete_coredump_removes_record_and_s3`)
  - Given missing S3 object, When `delete_coredump` is called, Then succeeds without error (`tests/services/test_coredump_service.py::TestCoredumpServiceCRUD::test_delete_coredump_s3_missing_succeeds`)
  - Given 5 coredumps, When `delete_all_coredumps` is called, Then all DB records and S3 objects removed (`tests/services/test_coredump_service.py::TestCoredumpServiceCRUD::test_delete_all_coredumps`)
- Hooks: Container provides `coredump_service()` as Singleton with S3Service; `create_test_device` helper
- Gaps: None
- Evidence: `tests/services/test_coredump_service.py` (23 tests)

- Surface: Coredump parsing thread (S3 downloads)
- Scenarios:
  - Given sidecar configured and firmware ELF in S3, When parsing runs, Then parse_status set to PARSED (`tests/services/test_coredump_service.py::TestCoredumpServiceParsing::test_parse_coredump_success`)
  - Given sidecar returns 500, When parsing runs, Then parse_status set to ERROR after retries (`tests/services/test_coredump_service.py::TestCoredumpServiceParsing::test_parse_coredump_sidecar_500`)
  - Given sidecar unreachable, When parsing runs, Then parse_status set to ERROR (`tests/services/test_coredump_service.py::TestCoredumpServiceParsing::test_parse_coredump_sidecar_unreachable`)
  - Given firmware ELF not in S3, When parsing runs, Then parse_status set to ERROR (`tests/services/test_coredump_service.py::TestCoredumpServiceParsing::test_parse_coredump_firmware_elf_not_found`)
  - Given xfer files created, When parsing completes, Then xfer files cleaned up (`tests/services/test_coredump_service.py::TestCoredumpServiceParsing::test_parse_coredump_cleans_up_xfer_files`)
- Hooks: S3 uploads for firmware ELF and coredump DMP; `unittest.mock.patch` for httpx responses; `tmp_path` for xfer directory
- Gaps: None
- Evidence: `tests/services/test_coredump_service.py::TestCoredumpServiceParsing` (6 tests)

- Surface: MigrationService (CLI migrate-to-s3)
- Scenarios:
  - Given ASSETS_DIR with versioned ZIPs, When migration runs, Then artifacts uploaded to S3 with generic names and firmware_versions records created (`tests/services/test_migration_service.py::TestMigrationServiceFirmware::test_migrate_firmware_zips`)
  - Given multiple firmware versions, When migration runs, Then all migrated (`tests/services/test_migration_service.py::TestMigrationServiceFirmware::test_migrate_multiple_firmware_versions`)
  - Given model directory with no DB record, When migration runs, Then skipped with warning (`tests/services/test_migration_service.py::TestMigrationServiceFirmware::test_migrate_firmware_no_matching_model`)
  - Given legacy flat .bin files, When migration runs, Then skipped (`tests/services/test_migration_service.py::TestMigrationServiceFirmware::test_migrate_firmware_skips_legacy_flat_bin`)
  - Given dry run, When migration runs, Then no S3 uploads or DB records created (`tests/services/test_migration_service.py::TestMigrationServiceFirmware::test_migrate_firmware_dry_run`)
  - Given migration run twice, When second run executes, Then idempotent (`tests/services/test_migration_service.py::TestMigrationServiceFirmware::test_migrate_firmware_idempotent`)
  - Given COREDUMPS_DIR with .dmp files, When migration runs, Then uploaded to S3 as ID-based keys and filename cleared (`tests/services/test_migration_service.py::TestMigrationServiceCoredumps::test_migrate_coredumps`)
  - Given orphaned .dmp file, When migration runs, Then skipped with warning (`tests/services/test_migration_service.py::TestMigrationServiceCoredumps::test_migrate_coredumps_orphaned_file`)
  - Given full migration (firmware + coredumps), When migration runs, Then both migrated (`tests/services/test_migration_service.py::TestMigrationServiceFullMigration::test_full_migration`)
- Hooks: `tmp_path` for filesystem setup; S3Service (real, test bucket); direct DB model creation
- Gaps: None
- Evidence: `tests/services/test_migration_service.py` (13 tests)

- Surface: API endpoints (coredumps, device models, IoT, pipeline)
- Scenarios:
  - All coredump API tests updated: list, get, download from S3, delete, delete-all (`tests/api/test_coredumps.py`, 14 tests)
  - Firmware upload tests updated to use ZIP content and verify S3 objects (`tests/api/test_device_models.py`, 18 tests)
  - IoT firmware download tests updated for S3 (`tests/api/test_iot.py`, 23 tests)
  - Pipeline firmware tests updated, raw .bin rejection test added (`tests/api/test_pipeline.py`, 27 tests)
  - Testing endpoint test updated to not expect `filename` field (`tests/api/test_testing.py`, 29 tests)
- Hooks: `_create_test_zip` helper consolidated in `tests/services/test_firmware_service.py` and shared across API tests
- Gaps: None
- Evidence: All 172 tests pass

## 7) Adversarial Sweep (must attempt >=3 credible failures or justify none)

- Checks attempted: Accessing `coredump.id` after `session.delete(coredump)` in retention and delete_all paths
- Evidence: `app/services/coredump_service.py:229-234` -- After `session.delete(coredump)` at line 224 and `session.flush()` at line 226, the code accesses `coredump.id` at line 231. Similarly at `app/services/coredump_service.py:574-575`.
- Why code held up: After `session.delete()` and `session.flush()`, the object is in the "deleted" state in SQLAlchemy's identity map. The `id` attribute is still accessible because it was loaded before deletion. SQLAlchemy does not clear scalar attributes on deleted objects. This is the standard pattern used throughout the codebase (e.g., the previous filesystem version deleted files using `coredump.filename` after `session.delete`).

- Checks attempted: S3Service injected as Factory into CoredumpService Singleton -- lifecycle mismatch
- Evidence: `app/services/container.py:46` -- `s3_service = providers.Factory(S3Service, settings=config)`. `app/services/container.py:168-174` -- CoredumpService Singleton receives `s3_service=s3_service`.
- Why code held up: When dependency-injector injects a Factory into a Singleton, it creates a single instance at Singleton construction time and holds it. S3Service is effectively stateless after initialization -- its `_s3_client` property lazily creates a boto3 client once and reuses it. The boto3 S3 client is thread-safe for concurrent operations. This is the same pattern already used by CAS image operations in the codebase.

- Checks attempted: Firmware retention S3 deletion interleaved with DB deletes (not batch)
- Evidence: `app/services/firmware_service.py:374-385` -- Inside the `for fv in excess:` loop, the code deletes the DB record at line 375, then immediately attempts S3 prefix deletion at line 380-382, then continues to the next version. The `self.db.flush()` only happens at line 388, after all deletes.
- Why code held up: The DB deletes at line 375 (`self.db.delete(fv)`) mark records for deletion but don't issue SQL until the flush at line 388. The S3 prefix deletions at lines 380-382 are best-effort and individually wrapped in try/except. If an S3 deletion fails, it logs a warning and continues. The final flush at line 388 issues all the DB DELETEs atomically. This ordering means S3 objects may be deleted before the DB DELETE is flushed, but since S3 cleanup is best-effort by policy, this is acceptable. The DB records are the source of truth -- if a subsequent error prevents the flush, the DB records survive and S3 objects become orphans (which is the acceptable failure mode).

- Checks attempted: Migration 007 applied before CLI migrate-to-s3 runs would break migration
- Evidence: `alembic/versions/007_drop_coredumps_filename.py:1-5` -- Header comment says "This migration should only be applied AFTER the CLI `migrate-to-s3` command has been run in all environments."
- Why code held up: The two-phase approach with migrations 006 (make nullable) and 007 (drop column) is explicitly documented. Migration 007 is shipped as code but should only be applied after the CLI migration. This is a standard deployment pattern. The MigrationService at `app/services/migration_service.py:255-257` queries `CoreDump.filename` which requires the column to exist. If 007 is applied prematurely, the migration CLI will fail with a clear SQL error. The sequencing is documented in the plan, the migration file header, and the CLI command docstring.

## 8) Invariants Checklist (stacked entries)

- Invariant: Every firmware_versions DB record must have corresponding S3 objects under `firmware/{model_code}/{version}/`
  - Where enforced: `app/services/firmware_service.py:176-187` -- DB flush before S3 upload; if S3 fails, exception propagates and transaction rolls back.
  - Failure mode: S3 upload succeeds for some artifacts but fails mid-way (e.g., 3 of 5 uploaded). DB record committed but some S3 objects missing.
  - Protection: `app/services/firmware_service.py:180-187` -- All 5 artifacts are uploaded sequentially. If any upload fails, the `InvalidOperationException` from S3Service propagates, the request handler's error handling kicks in, and the session rolls back at teardown. The firmware_versions record is never committed. Partial S3 objects are orphans that will be overwritten on the next successful upload.
  - Evidence: `tests/services/test_firmware_service.py::TestFirmwareServiceSave::test_save_firmware_valid_zip` verifies all 5 artifacts exist after a successful save.

- Invariant: Every CoreDump DB record must have a corresponding S3 object at `coredumps/{device_key}/{id}.dmp`
  - Where enforced: `app/services/coredump_service.py:153-173` -- DB flush to get ID, then S3 upload. If S3 fails, transaction rolls back.
  - Failure mode: S3 upload fails after DB flush. The unflushed record rolls back at teardown.
  - Protection: The golden rule ordering (flush -> upload -> commit-at-teardown) ensures the DB record is never committed without a successful S3 upload. The S3Service raises `InvalidOperationException` on upload failure, which propagates through `@handle_api_errors`.
  - Evidence: `tests/services/test_coredump_service.py::TestCoredumpServiceSave::test_save_coredump_creates_s3_object_and_record` verifies both DB record and S3 object exist.

- Invariant: Firmware versions referenced by PENDING coredumps must not be pruned by retention
  - Where enforced: `app/services/firmware_service.py:353-372` -- For each excess version, queries `CoreDump.firmware_version == fv.version AND CoreDump.parse_status == 'PENDING'`. If any exist, the version is skipped.
  - Failure mode: Concurrent coredump parse completes between the query and the delete, making the version pruneable after the check. The version would be incorrectly retained this cycle but pruned on the next upload -- not a data loss scenario.
  - Protection: The PENDING guard query runs within the same DB transaction as the retention logic. The worst case is over-retention (keeping a version longer than necessary), which is safe.
  - Evidence: `tests/services/test_firmware_service.py::TestFirmwareRetention::test_retention_protects_pending_coredumps` and `test_retention_all_protected_no_prune` verify the guard.

- Invariant: S3 key derivation is deterministic and consistent across all code paths
  - Where enforced: `app/services/coredump_service.py:80-90` (`_s3_key`), `app/services/firmware_service.py:96-102` (`_s3_prefix`, `_s3_key`), `app/services/coredump_service.py:334` (parsing thread ELF key).
  - Failure mode: Different code paths generate different S3 keys for the same resource.
  - Protection: All coredump S3 keys use `_s3_key(device_key, coredump_id)` which returns `coredumps/{device_key}/{coredump_id}.dmp`. All firmware keys use `_s3_key(model_code, version, artifact)` which returns `firmware/{model_code}/{version}/{artifact}`. The parsing thread constructs the ELF key directly as `f"firmware/{model_code}/{firmware_version}/firmware.elf"` which matches the FirmwareService key construction.
  - Evidence: Consistent key patterns verified across save, download, delete, retention, and parsing code paths.

## 9) Questions / Needs-Info

- Question: Should migration 007 be included in this changeset or deferred to a separate PR after the migration has run?
- Why it matters: Including 007 means Alembic will apply both migrations in sequence on a fresh deploy. For existing deployments, the operator must remember to run `migrate-to-s3` between applying 006 and 007. The comment in the migration file documents this, but it adds operational risk.
- Desired answer: Confirm whether the deployment process can handle the sequencing, or whether 007 should be split into a separate PR that is merged after the migration CLI has been run in production.

## 10) Risks & Mitigations (top 3)

- Risk: Migration 007 applied before CLI `migrate-to-s3` runs, breaking the migration command.
- Mitigation: The migration file header clearly documents the sequencing requirement. Consider adding a runtime check in the migration or the CLI command itself.
- Evidence: `alembic/versions/007_drop_coredumps_filename.py:1-5`

- Risk: Partial S3 upload failure during firmware upload leaves orphaned S3 objects with no corresponding DB record.
- Mitigation: Orphans are harmless (overwritten on next successful upload). The DB transaction rolls back, so no `firmware_versions` record exists for the partial upload. Acceptable by the project's S3 policy.
- Evidence: `app/services/firmware_service.py:180-187` (sequential uploads, exception propagation)

- Risk: S3Service Factory injected into CoredumpService Singleton could theoretically cause issues if S3Service has mutable state.
- Mitigation: S3Service is effectively stateless after lazy client initialization. The boto3 S3 client is thread-safe. This is the same pattern already used for other Singleton-held services in the codebase.
- Evidence: `app/services/container.py:46,168-174`

## 11) Confidence

Confidence: High -- The implementation is thorough, well-tested (172 tests, all passing), follows the approved plan closely, and correctly applies the S3 golden rules. The findings are minor and do not affect correctness. The migration path is well-designed with two-phase column removal and an idempotent CLI command.
