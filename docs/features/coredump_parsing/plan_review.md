# Coredump Parsing & Management -- Plan Review

## 1) Summary & Decision

**Readiness**

The plan is thorough, well-researched, and implementation-ready. It demonstrates strong understanding of the codebase patterns (singleton vs factory services, container wiring, blueprint registration, firmware ZIP structure, filesystem storage). The data model is sound, the API surface is cleanly defined with proper error modes, and the test plan provides comprehensive scenario coverage. After revisions addressing the three Major issues from the initial review (eager loading overhead, inconsistent parse_status handling, background thread session race condition), the plan is now internally consistent. The background thread data-passing approach (section 5, step 11) cleanly avoids the transaction isolation race, the `lazy="select"` choice (section 3, `plan.md:207`) avoids polluting unrelated queries, and the sidecar-missing behavior (section 8, `plan.md:415-419`) is now clearly documented as a single consistent policy.

**Decision**

`GO` -- All previously identified Major issues have been resolved. The plan is precise enough for a competent developer to implement without ambiguity. Remaining Minor items are noted below but do not block implementation.


## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md` (layered architecture) -- Pass -- `plan.md:108-165` -- Plan correctly separates model, service, schema, and API layers into distinct files.
- `CLAUDE.md` (enum as text, not native ENUM) -- Pass -- `plan.md:170-179` -- `ParseStatus` uses `native_enum=False` per guidelines.
- `CLAUDE.md` (singleton DB session pattern) -- Pass -- `plan.md:27,340-341` -- Background thread uses `container.db_session()` / `commit()` / `reset()` pattern.
- `CLAUDE.md` (error handling: fail fast) -- Pass -- `plan.md:395-437` -- Enumerates failure modes with explicit handling and typed exceptions.
- `CLAUDE.md` (shutdown coordinator) -- Pass -- `plan.md:473-479` -- Justifies skipping shutdown integration for ephemeral daemon threads.
- `CLAUDE.md` (S3 storage consistency adapted to filesystem) -- Pass -- `plan.md:387-388` -- File written before DB record; DB is source of truth; orphaned files are acceptable.
- `docs/product_brief.md` (device scale) -- Pass -- `plan.md:74` -- Correctly scopes to 200 devices, 4000 max coredumps.
- `docs/commands/plan_feature.md` (all 16 sections present) -- Pass -- All sections from Research Log through Confidence are present and populated.

**Fit with codebase**

- `CoredumpService` singleton pattern -- `plan.md:27,130-132` -- Correctly identifies the service as a singleton needing the container DB session pattern. Constructor signature is now fully specified with all five dependencies (`coredumps_dir`, `config`, `container`, `firmware_service`, `metrics_service`).
- `container.py` wiring -- `plan.md:130-132` -- Dependencies are explicitly enumerated. The self-reference pattern (`container=providers.Self()`) is used elsewhere in DI frameworks for this purpose and is implementable.
- `app/__init__.py` wire_modules -- `plan.md:150-152` -- Correctly identifies the need to add `app.api.coredumps` to the wiring list at `app/__init__.py:63-77`.
- `tests/conftest.py` test settings -- `plan.md:611` -- Notes that `_build_test_settings` needs new config fields (`parse_sidecar_xfer_dir`, `parse_sidecar_url`, `max_coredumps`).
- `Device.coredumps` relationship -- `plan.md:202-211` -- Uses `lazy="select"` with explicit `selectinload` in coredump endpoints, avoiding overhead on unrelated device queries.


## 3) Open Questions & Ambiguities

- Question: Should `coredumps_bp` be registered on `devices_bp` or directly on `api_bp`?
- Why it matters: Affects how `device_id` is parsed from the URL and how the blueprint prefix is configured. The plan mentions both options at `plan.md:147` without committing.
- Needed answer: A minor implementation decision. Both approaches work; the developer should pick whichever aligns with how other nested resources are handled (likely a new blueprint on `api_bp` with `url_prefix="/devices/<int:device_id>/coredumps"`).

- Question: What happens to pre-existing `.dmp` + `.json` files on disk from before the DB tracking was added?
- Why it matters: Since the app is not in production (`plan.md:65`), this is low-impact, but existing development/test coredumps will become orphans.
- Needed answer: Acknowledged as a non-issue for the current deployment stage. No action required.


## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: `CoredumpService.save_coredump()` (refactored -- DB record creation + retention)
- Scenarios:
  - Given a configured service with DB, When saving a valid coredump, Then `.dmp` file written, DB record created with parse_status=PENDING (`tests/services/test_coredump_service.py::test_save_creates_record`)
  - Given MAX_COREDUMPS exceeded, When saving, Then oldest record and file deleted (`tests/services/test_coredump_service.py::test_retention_enforcement`)
  - Given a configured service, When saving, Then no `.json` sidecar file created (`tests/services/test_coredump_service.py::test_no_json_sidecar`)
- Instrumentation: Existing `iot_upload_coredump` counter/histogram at `app/api/iot.py:418-419`.
- Persistence hooks: New `Coredump` model, `Device.coredumps` relationship, test settings updates.
- Gaps: None.
- Evidence: `plan.md:517-527`

- Behavior: `CoredumpService.parse_coredump()` (new -- background parsing)
- Scenarios:
  - Given sidecar success, Then parse_status=PARSED, xfer files cleaned (`tests/services/test_coredump_service.py::test_parse_success`)
  - Given 3 sidecar failures, Then parse_status=ERROR with message (`tests/services/test_coredump_service.py::test_parse_retries_exhausted`)
  - Given no firmware ZIP, Then parse_status=ERROR immediately (`tests/services/test_coredump_service.py::test_parse_no_firmware`)
  - Given no sidecar config, Then status stays PENDING (`tests/services/test_coredump_service.py::test_parse_skipped_no_config`)
- Instrumentation: `coredump_parse` counter/histogram via `record_operation()`.
- Persistence hooks: DB record update via container session pattern in background thread.
- Gaps: None.
- Evidence: `plan.md:529-539`

- Behavior: Admin API CRUD endpoints (new)
- Scenarios:
  - GET list/detail/download, DELETE single/all with ownership validation and 404s.
- Instrumentation: Per-endpoint operation metrics.
- Persistence hooks: Schemas, blueprint, wiring.
- Gaps: None.
- Evidence: `plan.md:554-603`

- Behavior: Upload endpoint refactor (`POST /api/iot/coredump`)
- Scenarios:
  - Upload creates DB record with PENDING status; no `.json` sidecar on disk.
- Instrumentation: Existing metric.
- Persistence hooks: Updated `app/api/iot.py`.
- Gaps: Background parsing tested only in service tests (acceptable).
- Evidence: `plan.md:597-603`


## 5) Adversarial Sweep

**Minor -- Blueprint registration nesting unresolved**

**Evidence:** `plan.md:146-148` -- "Register the new coredumps_bp blueprint under devices_bp (or directly on api_bp with nesting)"

**Why it matters:** The "or" leaves ambiguity for the developer. Both approaches work but have different implications for URL prefix configuration and `device_id` parameter access.

**Fix suggestion:** Commit to one approach. Registering on `api_bp` with `url_prefix="/devices/<int:device_id>/coredumps"` is simplest and follows the flat blueprint pattern in `app/api/__init__.py:192-200`.

**Confidence:** Low (does not block implementation)


**Minor -- Pre-existing orphan coredump files on disk**

**Evidence:** `plan.md:88` -- "Remove JSON sidecar file writing from coredump upload"

**Why it matters:** Any `.dmp` + `.json` files on disk from before this change will not have corresponding DB records. At the current stage (not in production, `plan.md:65`), this is harmless.

**Fix suggestion:** No action required. Optionally note in the plan that existing files can be cleaned up manually if needed.

**Confidence:** Low


- Checks attempted: Transaction isolation between upload request and background thread; singleton session lifecycle in background thread; retention enforcement race condition; eager loading overhead on Device queries; consistent parse_status handling for missing sidecar config; container dependency completeness.
- Evidence: `plan.md:335-341` (thread spawning and data passing), `plan.md:207` (lazy="select"), `plan.md:415-419` (consistent PENDING behavior), `plan.md:130-132` (complete constructor signature), `plan.md:390` (thread only writes, doesn't read initial record).
- Why the plan holds: The revised plan passes all data to the background thread as arguments (eliminating the transaction isolation race), uses lazy loading to avoid query overhead, documents a single consistent behavior for missing sidecar config, and specifies the complete set of constructor dependencies.


## 6) Derived-Value & Persistence Invariants

- Derived value: Per-device coredump count
  - Source dataset: Unfiltered count of `Coredump` records matching `device_id` (all parse statuses).
  - Write / cleanup triggered: When count > `MAX_COREDUMPS`, oldest records and `.dmp` files are deleted.
  - Guards: Retention enforcement runs within the request transaction (same session as INSERT). Count and delete happen before commit.
  - Invariant: At commit time, a device never has more than `MAX_COREDUMPS` coredump records.
  - Evidence: `plan.md:362-366`

- Derived value: Coredump parse status
  - Source dataset: Result of sidecar HTTP call (background thread, separate session).
  - Write / cleanup triggered: Updates `parse_status`, `parsed_output`, `parsed_at`. Cleans up xfer directory files.
  - Guards: Background thread retries up to 3 times, catches all exceptions, always reaches terminal state (PARSED or ERROR). Xfer cleanup is best-effort.
  - Invariant: Every coredump that enters background parsing reaches either PARSED or ERROR. Coredumps without sidecar config remain PENDING.
  - Evidence: `plan.md:369-374,343`

- Derived value: Coredump file path on disk
  - Source dataset: `COREDUMPS_DIR / device.key / coredump.filename` -- server-generated filename with microsecond precision.
  - Write / cleanup triggered: File created on upload, deleted on retention enforcement or explicit admin delete.
  - Guards: Filename uses microsecond timestamp to avoid collision. Device key validated as alphanumeric.
  - Invariant: Every Coredump record has a corresponding `.dmp` file (unless manually removed or OS error). DB record is source of truth; disk cleanup is best-effort.
  - Evidence: `plan.md:376-381`


## 7) Risks & Mitigations (top 3)

- Risk: Background parsing thread fails silently and coredumps stay PENDING indefinitely when sidecar is configured but broken.
- Mitigation: `coredump_parse` metric with `status=error` enables alerting. Comprehensive logging in thread. Future CLI re-parse command noted as enhancement.
- Evidence: `plan.md:638-640,450-455`

- Risk: Sidecar container not running or misconfigured, causing all parses to fail with ERROR status.
- Mitigation: Parsing is gracefully degraded -- uploads still succeed, raw dumps are downloadable. Metric-based alerting detects the issue.
- Evidence: `plan.md:642-644`

- Risk: Orphaned `.dmp` files on disk if DB record deletion succeeds but file deletion fails (or vice versa).
- Mitigation: File deletion is best-effort with logging. Maximum disk impact bounded at 4 GB (200 devices * 20 dumps * 1 MB). DB record is source of truth.
- Evidence: `plan.md:646-648,387-388`


## 8) Confidence

Confidence: High -- The plan is internally consistent, all previously identified Major issues have been resolved, the data model and API surface are cleanly specified, and the test plan provides comprehensive scenario coverage. The remaining Minor items (blueprint nesting, orphan files) are implementation details that do not affect correctness.
