# Plan Review: Migrate Firmware and Coredump Storage to S3

## 1) Summary & Decision

**Readiness**

The plan is thorough, well-researched, and demonstrates strong alignment with the project's architecture and conventions. It correctly identifies the affected areas, proposes reasonable data model changes, and includes a comprehensive test plan. The S3 golden rules are properly applied throughout. An initial review identified four Major issues (DI wiring conflict, golden-rule ordering note, artifact naming contradiction, and migration sequencing conflict), all of which have been resolved in the current revision of the plan. The DI wiring is addressed by having CoredumpService's parsing thread use S3Service directly. The artifact naming is consistently set to generic names. The migration is split into two Alembic steps (006 makes `filename` nullable; 007 drops it after CLI migration). The coredump upload flow explicitly documents the ordering change from the current filesystem implementation.

**Decision**

`GO` -- All previously identified Major issues have been resolved. The plan is implementation-ready with clear boundaries, consistent naming, correct transaction ordering, and a safe migration strategy.

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md` S3 Storage Consistency -- Pass -- `plan.md:96,408-412` -- "S3 golden rules enforced: creates flush+upload+commit, deletes commit+best-effort-S3-delete". The plan explicitly cites and follows these rules for firmware upload (flush DB, upload S3, commit) and for deletes (commit DB, then best-effort S3 delete). The coredump upload flow at `plan.md:336` includes an explicit note about the order change from the current filesystem implementation.
- `CLAUDE.md` native_enum=False -- Pass -- `plan.md:204-213` -- The `firmware_versions` table schema uses `str(50)` for version, consistent with the project's avoidance of native PostgreSQL ENUMs.
- `CLAUDE.md` Layering (API -> Service -> Model) -- Pass -- `plan.md:110-198` -- File map correctly separates API changes (endpoints), service changes (business logic), and model changes (schema).
- `CLAUDE.md` Testing Requirements -- Pass -- `plan.md:539-619` -- Comprehensive test plan covering service tests, API tests, and CLI tests with Given/When/Then scenarios.
- `CLAUDE.md` Error Handling (fail fast) -- Pass -- `plan.md:422-458` -- Error cases enumerate specific failure modes with appropriate surfacing behavior.
- `CLAUDE.md` Deprecation/BFF pattern -- Pass -- `plan.md:245,532` -- Breaking changes made freely (removing `filename` field, rejecting raw .bin uploads), consistent with BFF pattern.
- `docs/product_brief.md` -- Pass -- `plan.md:37-79` -- The migration scope correctly aligns with the product brief's firmware and coredump storage concerns. No product-level features are altered.
- `docs/commands/plan_feature.md` template -- Pass -- All required sections (0-16) are present and populated.

**Fit with codebase**

- `FirmwareService` singleton -> factory -- `plan.md:124-126, 140-142` -- The plan correctly changes FirmwareService from Singleton to Factory and addresses the DI cascade: CoredumpService no longer depends on FirmwareService, and its parsing thread uses S3Service directly for `.elf` downloads. This is explicitly stated in the container wiring entry (`plan.md:140-142`), the coredump service entry (`plan.md:128-130`), and the parsing thread algorithm (`plan.md:349`).
- `CoredumpService._enforce_retention` -- `plan.md:339` -- The plan describes "delete DB record, then best-effort S3 delete" for coredump retention, which correctly follows the golden rule. The current code at `coredump_service.py:222-227` deletes the file first, then deletes the DB record. The plan's S3 approach inverts this correctly.
- `DeviceModelService.upload_firmware` -- `plan.md:132-134` -- The plan notes that `upload_firmware` calls `firmware_service.save_firmware_zip`. Currently (`device_model_service.py:229-232`), it routes between ZIP and raw .bin. The plan correctly eliminates the raw .bin path.
- `app/startup.py:62-63` -- `plan.md:196-198` -- The plan correctly identifies the post-init container assignment for CoredumpService. This pattern remains necessary since CoredumpService is still a Singleton with background thread DB access.
- Artifact naming -- `plan.md:125,314,349,674` -- Consistently uses generic names (`firmware.bin`, `firmware.elf`, etc.) across all sections. The parsing thread downloads `firmware.elf` from S3 and writes it locally as `{model_code}.elf` for the sidecar.

## 3) Open Questions & Ambiguities

All previously open questions have been resolved in the current plan revision:

- The DI wiring concern is resolved at `plan.md:78,129,140-142,349,675`: CoredumpService receives S3Service directly and its parsing thread bypasses FirmwareService.
- The artifact naming is resolved at `plan.md:125,314,674`: generic names consistently used throughout.
- The migration sequencing is resolved at `plan.md:56,164-170,227,358-365,645-648,676`: two-phase column removal with explicit deployment note.

No remaining open questions block implementation.

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: FirmwareService.save_firmware (S3-based upload with version tracking)
- Scenarios:
  - Given a valid ZIP, When `save_firmware` is called, Then 5 S3 objects created and firmware_versions record exists (`tests/services/test_firmware_service.py::test_save_firmware_zip_creates_s3_objects`)
  - Given S3 upload fails mid-way, When `save_firmware` is called, Then exception raised and no firmware_versions record committed (`tests/services/test_firmware_service.py::test_save_firmware_s3_failure_rolls_back`)
- Instrumentation: `firmware_upload` operation metric (existing `record_operation` at `app/api/device_models.py:244-245`), `firmware_retention_pruned` structured log (new)
- Persistence hooks: Alembic 006 creates `firmware_versions` table; container.py changes FirmwareService to Factory with `db_session` and `s3_service`
- Gaps: None
- Evidence: `plan.md:541-555`, `plan.md:309-320`

- Behavior: Firmware retention pruning (MAX_FIRMWARES with PENDING coredump guard)
- Scenarios:
  - Given excess versions, When retention runs, Then oldest non-protected versions pruned (`tests/services/test_firmware_service.py::test_retention_prunes_oldest`)
  - Given excess versions all protected by PENDING coredumps, When retention runs, Then no versions pruned (`tests/services/test_firmware_service.py::test_retention_skips_pending_protected`)
- Instrumentation: `firmware_retention_pruned` structured log
- Persistence hooks: firmware_versions records deleted, S3 prefix deletion (best-effort)
- Gaps: None
- Evidence: `plan.md:557-565`, `plan.md:322-331`

- Behavior: CoredumpService.save_coredump (S3-based upload)
- Scenarios:
  - Given valid content, When `save_coredump` called, Then CoreDump record created (flushed before S3 upload per golden rule), S3 object exists, coredump_id returned (`tests/services/test_coredump_service.py::test_save_coredump_creates_s3_object`)
  - Given S3 upload fails, When `save_coredump` called, Then exception raised, DB record not committed (`tests/services/test_coredump_service.py::test_save_coredump_s3_failure_rolls_back`)
- Instrumentation: `coredump_s3_upload` structured log
- Persistence hooks: Alembic 006 makes `filename` nullable; Alembic 007 drops `filename` after CLI migration
- Gaps: None
- Evidence: `plan.md:567-578`, `plan.md:333-343`

- Behavior: Coredump parsing thread (S3 downloads via self.s3_service)
- Scenarios:
  - Given sidecar configured, When parsing runs, Then `.dmp` downloaded from S3 and `.elf` downloaded from S3 via `self.s3_service` (`tests/services/test_coredump_service.py::test_parsing_downloads_from_s3`)
  - Given `.elf` not in S3, When parsing runs, Then parse_status set to ERROR (`tests/services/test_coredump_service.py::test_parsing_missing_elf_error`)
- Instrumentation: `coredump_parse` operation metric (existing, unchanged)
- Persistence hooks: DB session usage via container pattern (unchanged); S3Service injected into CoredumpService constructor
- Gaps: None
- Evidence: `plan.md:580-589`, `plan.md:345-356`

- Behavior: CLI `migrate-to-s3`
- Scenarios:
  - Given ASSETS_DIR with ZIPs, When migration runs, Then artifacts uploaded to S3 with generic names, firmware_versions records created
  - Given orphaned `.dmp` files, When migration runs, Then skipped with warning
  - Given S3 unreachable, When migration runs, Then exits non-zero
- Instrumentation: `migrate_to_s3` structured log
- Persistence hooks: Creates firmware_versions records, uploads to S3, sets `filename = NULL` on migrated coredump records
- Gaps: None
- Evidence: `plan.md:611-619`, `plan.md:358-368`

## 5) Adversarial Sweep (must find >=3 credible issues or declare why none exist)

All four previously identified Major issues have been resolved in the current plan revision. The adversarial checks attempted and their closure status:

- Checks attempted: Golden-rule transaction ordering in coredump upload (flush before S3 upload)
- Evidence: `plan.md:336` -- explicit NOTE documents the order change from the current filesystem-first implementation
- Why the plan holds: The plan clearly states "flush DB first (to obtain the `id` needed for the S3 key), then upload to S3, then let the request session commit on teardown" with a bold note that this is an intentional reversal of the current ordering.

- Checks attempted: FirmwareService Factory / CoredumpService Singleton DI lifecycle conflict
- Evidence: `plan.md:129,140-142,349` -- CoredumpService receives `s3_service` directly; `firmware_service` removed from its constructor; parsing thread uses `self.s3_service`
- Why the plan holds: The plan explicitly removes the FirmwareService dependency from CoredumpService and routes S3 downloads through the directly-injected S3Service. The S3 key is deterministic (`firmware/{model_code}/{firmware_version}/firmware.elf`) so no DB query or FirmwareService method is needed.

- Checks attempted: Firmware artifact naming consistency across upload, download, and parsing
- Evidence: `plan.md:125,259,265,314,349,361,674` -- all references use generic names (`firmware.bin`, `firmware.elf`, etc.)
- Why the plan holds: Generic naming is applied consistently across firmware upload (step 4), firmware download (API surface), parsing thread (step 3), CLI migration (step 2), and the resolved open question (Section 15). The sidecar receives the `.elf` with its model-specific local name (`{model_code}.elf`) at the xfer directory level, which is independent of the S3 object name.

- Checks attempted: Alembic migration / CLI migration column-drop ordering
- Evidence: `plan.md:164-170,227,362-365,645-648,676` -- two-phase approach with migration 006 (make nullable) and 007 (drop column)
- Why the plan holds: Migration 006 makes `filename` nullable without dropping it. The CLI `migrate-to-s3` uses the still-present column to match files to records, then sets `filename = NULL` on migrated records. Migration 007 drops the column only after the CLI has run in all environments. The deployment note at `plan.md:365` makes this sequencing explicit.

- Checks attempted: S3Service lifecycle in CoredumpService Singleton (S3Service is a Factory provider)
- Evidence: `container.py:46` -- S3Service is `providers.Factory`
- Why the plan holds: When dependency-injector injects a Factory into a Singleton, it creates one instance at Singleton construction time. Since S3Service is stateless (its S3 client is lazily initialized and shared via a property), holding a single instance is safe. Unlike FirmwareService (which holds a DB session that becomes stale), S3Service has no request-scoped state. The plan should note that S3Service may need to be a Singleton provider if the Factory lifecycle causes issues, but this is a Minor implementation detail.

- Checks attempted: Partial S3 upload failure during firmware upload (3 of 5 artifacts uploaded)
- Evidence: `plan.md:659-661` -- Risk explicitly identified with mitigation (best-effort cleanup or accept orphans)
- Why the plan holds: The risk is acknowledged and mitigated. S3 orphans from partial uploads are overwritten by subsequent successful uploads, and the DB transaction rolls back so no `firmware_versions` record exists for the partial upload.

## 6) Derived-Value & Persistence Invariants (stacked entries)

- Derived value: Firmware S3 key prefix (`firmware/{model_code}/{version}/`)
  - Source dataset: Unfiltered -- derived from `DeviceModel.code` and firmware binary AppInfo version string
  - Write / cleanup triggered: S3 objects created on upload; S3 prefix deleted (best-effort) on retention pruning or model deletion
  - Guards: All 5 S3 uploads must succeed before commit (exception rolls back transaction). Deletion is best-effort.
  - Invariant: Every `firmware_versions` DB record must have corresponding S3 objects under its prefix. Orphaned S3 objects are acceptable; missing S3 objects for an existing DB record would cause download failures.
  - Evidence: `plan.md:374-379`

- Derived value: Coredump S3 key (`coredumps/{device_key}/{id}.dmp`)
  - Source dataset: Unfiltered -- derived from `Device.key` and `CoreDump.id` (primary key)
  - Write / cleanup triggered: S3 object created on upload; S3 object deleted (best-effort) on record deletion or retention
  - Guards: DB record flushed to get `id` before S3 upload (golden rule, explicitly noted as order change at `plan.md:336`); S3 upload must succeed before commit. Deletion is best-effort after commit.
  - Invariant: Every CoreDump DB record must have a corresponding S3 object. Missing S3 objects would cause download failures (surfaced as 404).
  - Evidence: `plan.md:381-386`

- Derived value: Pruneable firmware versions (filtered set)
  - Source dataset: Filtered -- all `firmware_versions` for a model, excluding newest MAX_FIRMWARES and those referenced by PENDING coredumps
  - Write / cleanup triggered: Deletes firmware_versions DB records and S3 prefixes for excess versions
  - Guards: PENDING coredump guard prevents deleting firmware needed for parsing. Without this guard, pruning could make PENDING coredumps permanently unparseable.
  - Invariant: Any firmware version referenced by a PENDING coredump must not be pruned, even if it exceeds MAX_FIRMWARES.
  - Evidence: `plan.md:388-393`

- Derived value: `DeviceModel.firmware_version` (current active version pointer)
  - Source dataset: Unfiltered -- set to the version extracted from the most recently uploaded firmware ZIP
  - Write / cleanup triggered: Updated on DeviceModel; used by IoT firmware download to determine which S3 prefix to serve from
  - Guards: Only updated after successful S3 upload of all artifacts
  - Invariant: Must always point to a version that has corresponding S3 objects. The current version is always in the newest MAX_FIRMWARES, so retention cannot prune it.
  - Evidence: `plan.md:395-400`, `device_model_service.py:235`

## 7) Risks & Mitigations (top 3)

- Risk: S3 multi-object upload failure mid-way during firmware upload (e.g., 3 of 5 artifacts uploaded, then S3 error) leaves orphaned S3 objects with no corresponding DB record.
- Mitigation: Accept orphans since a subsequent successful upload for the same version overwrites them. Optionally, add best-effort cleanup of already-uploaded artifacts before re-raising the exception. DB transaction rolls back so no `firmware_versions` record exists for the partial upload.
- Evidence: `plan.md:659-661`

- Risk: CLI migration takes longer than expected on large firmware collections, extending planned downtime.
- Mitigation: Test migration on staging with representative data volume. Log progress per-file. Consider adding a `--dry-run` flag to estimate time before committing to the actual migration.
- Evidence: `plan.md:663-665`

- Risk: S3Service injected as Factory into CoredumpService Singleton could theoretically cause lifecycle issues if the S3 client's lazy initialization has thread-safety concerns.
- Mitigation: S3Service is effectively stateless after initialization -- its `_s3_client` is lazily created once and reused. The `boto3` S3 client is thread-safe for operations. If issues arise during testing, promote S3Service to a Singleton provider.
- Evidence: `container.py:46`, `s3_service.py:28-43`

## 8) Confidence

Confidence: High -- All previously identified Major issues have been resolved in the current plan revision. The plan is internally consistent, follows established codebase patterns, and provides sufficient detail for a competent developer to implement without guessing.
