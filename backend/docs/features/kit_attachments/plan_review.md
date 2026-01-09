# Kit Attachments — Plan Review

## 1) Summary & Decision

**Readiness**

The updated plan addresses all five previously identified issues: ON DELETE CASCADE is now specified for Part/Kit → AttachmentSet FK (lines 279, 296), Part creation rollback test scenario added (line 912), attachment_sets.json and attachments.json added to file map (lines 152-158) and implementation slice 6 (line 1046), AttachmentSetService container dependencies specified (line 187), and use_alter=True annotation included in schema snippet (line 240). The plan is comprehensive, well-researched, and provides deterministic implementation guidance. The design correctly leverages real FKs with cascade behavior, eager creation invariants, and follows established S3 consistency patterns. Test coverage is thorough across service, API, and migration layers. The only remaining concerns are implementation details that don't block a GO decision.

**Decision**

`GO` — All blockers resolved, comprehensive test plan in place, and clear evidence of codebase fit. The plan can proceed to implementation with high confidence.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `@docs/commands/plan_feature.md` — Pass — `plan.md:0-1087` — Plan follows all required sections (Research Log, Intent & Scope, File Map, Data Model, API Surface, Algorithms, Derived Values, Consistency, Errors, Observability, Shutdown, Security, UX, Test Plan, Slices, Risks, Confidence) with proper templates and evidence citations.

- `@docs/product_brief.md` — Pass — `plan.md:62-76` — Scope aligns with product brief's documentation model (lines 64-69 of product brief): "Multiple items per part: PDFs, images, and links. PDFs and images are uploaded and viewable directly in the app." Plan extends this to kits as intended.

- `@CLAUDE.md` layered architecture — Pass — `plan.md:84-93` — Plan respects API → Service → Model separation. API layer delegates to AttachmentSetService (line 85), service contains business logic (line 130), models are declarative (lines 120-125).

- `@CLAUDE.md` S3 storage consistency — Pass — `plan.md:650-659, 699-703` — Plan follows flush-before-upload pattern (lines 292-297 cite existing pattern from document_service.py:292-323). Attachment row persisted before S3 upload ensures transaction rollback cleans orphaned rows on failure (line 654).

- `@CLAUDE.md` test data requirements — Pass — `plan.md:152-158, 202-208, 1046` — Plan explicitly adds attachment_sets.json and attachments.json to test data (lines 152-158), updates parts.json and kits.json with attachment_set_id (lines 202-208), and includes validation step in implementation slice 6 (line 1046).

- `@CLAUDE.md` dependency injection — Pass — `plan.md:186-189` — AttachmentSetService constructor dependencies specified: db_session, s3_service, image_service, settings. Matches pattern from document_service (container.py:171-180).

- `@CLAUDE.md` deprecation policy — Pass — `plan.md:34, 70-72, 197-200` — Plan correctly removes old endpoints entirely (no backwards compatibility) per CLAUDE.md lines 15-19: "Make breaking changes freely; no backwards compatibility needed. Remove replaced/unused code and endpoints entirely."

**Fit with codebase**

- `app/services/container.py` — `plan.md:186-189` — Plan specifies AttachmentSetService dependencies (db_session, s3_service, image_service, settings) matching DocumentService pattern (container.py:171-180). However, plan excludes html_handler, download_cache_service, and url_interceptor_registry which are only needed for URL processing. This is correct since URL attachment creation can still delegate to DocumentService.process_upload_url() for that complexity.

- `app/models/part.py` — `plan.md:162-165, 274-284` — Plan removes cover_attachment_id (currently at part.py:52-54) and adds attachment_set_id NOT NULL FK. The circular FK pattern using use_alter=True is explicitly documented (line 245), matching existing Part.cover_attachment_id pattern (part.py:53).

- `app/services/document_service.py` — `plan.md:50-51, 130` — Plan states "Remove existing PartAttachmentService" but the actual service is DocumentService. Research log (lines 49-50) correctly identifies and resolves this: "the service is DocumentService. The intent is clear: remove the part-specific attachment logic from DocumentService and replace with attachment-set logic." Assumption holds.

- `alembic/versions/` — `plan.md:149-151` — Plan specifies migration 020 as next revision. Last migration is 019_relax_pick_list_line_quantity_constraint.py, confirming 020 is correct.

- `app/data/test_data/` — `plan.md:152-158, 202-208` — Plan adds attachment_sets.json and attachments.json (new files) and updates parts.json, kits.json (existing files). Current test data directory has 15 JSON files; plan correctly identifies which need creation vs. modification.

---

## 3) Open Questions & Ambiguities

None. All ambiguities from previous review (ON DELETE behavior, test scenarios, test data, container wiring, circular FK handling) have been resolved with explicit plan updates.

---

## 4) Deterministic Backend Coverage (new/changed behavior only)

**Behavior: AttachmentSetService.create_attachment_set()**

- Scenarios:
  - Given service instance, When create_attachment_set called, Then returns AttachmentSet with ID and no cover (`tests/test_attachment_set_service.py::test_create_attachment_set`)
  - Given service instance, When create multiple sets, Then each has unique ID (`tests/test_attachment_set_service.py::test_create_multiple_sets`)
- Instrumentation: No metrics needed (simple creation)
- Persistence hooks: Database session flush to get ID (line 518)
- Gaps: None
- Evidence: `plan.md:852-859`

**Behavior: AttachmentSetService.create_file_attachment()**

- Scenarios:
  - Given attachment set exists, When create image attachment with valid file, Then attachment created with IMAGE type and S3 key (`tests/test_attachment_set_service.py::test_create_image_attachment`)
  - Given attachment set exists, When create PDF attachment with valid file, Then attachment created with PDF type and S3 key (`tests/test_attachment_set_service.py::test_create_pdf_attachment`)
  - Given attachment set with no cover, When create image attachment, Then attachment auto-set as cover (`tests/test_attachment_set_service.py::test_auto_set_cover`)
  - Given attachment set with existing cover, When create image attachment, Then cover unchanged (`tests/test_attachment_set_service.py::test_cover_unchanged`)
  - Given attachment set ID, When create attachment with invalid file type, Then raises InvalidOperationException (`tests/test_attachment_set_service.py::test_invalid_file_type`)
  - Given attachment set ID, When create attachment with file exceeding size limit, Then raises InvalidOperationException (`tests/test_attachment_set_service.py::test_file_size_limit`)
  - Given non-existent set ID, When create attachment, Then raises RecordNotFoundException (`tests/test_attachment_set_service.py::test_create_attachment_set_not_found`)
  - Given duplicate file content (same hash), When create attachment, Then S3 upload skipped (CAS deduplication) (`tests/test_attachment_set_service.py::test_cas_deduplication`)
- Instrumentation: attachment_created_total counter (line 746), attachment_upload_duration_seconds histogram (line 766), structured log on creation (line 782)
- Persistence hooks: Flush attachment before S3 upload (line 654), S3 upload after flush (line 656)
- Gaps: None
- Evidence: `plan.md:861-874`

**Behavior: AttachmentSetService.delete_attachment()**

- Scenarios:
  - Given attachment in set, When delete attachment, Then attachment removed from database (`tests/test_attachment_set_service.py::test_delete_attachment`)
  - Given attachment is cover, When delete attachment, Then cover reassigned to next oldest image or NULL (`tests/test_attachment_set_service.py::test_delete_cover_reassigns`)
  - Given attachment in set A, When delete using set B ID, Then raises InvalidOperationException (`tests/test_attachment_set_service.py::test_delete_ownership_check`)
  - Given non-existent attachment ID, When delete, Then raises RecordNotFoundException (`tests/test_attachment_set_service.py::test_delete_nonexistent`)
- Instrumentation: attachment_deleted_total counter (line 754), cover reassignment log (line 799)
- Persistence hooks: Delete row, flush, handle cover reassignment within transaction (line 655)
- Gaps: None
- Evidence: `plan.md:886-895`

**Behavior: PartService.create_part() with attachment set**

- Scenarios:
  - Given valid part data, When create part, Then part created with attachment_set_id populated and AttachmentSet exists (`tests/test_part_service.py::test_create_part_with_attachment_set`)
  - Given part creation fails after attachment set created, When transaction rolls back, Then both part and attachment set rolled back (`tests/test_part_service.py::test_part_creation_rollback_attachment_set`)
- Instrumentation: No new metrics (attachment set creation tracked separately)
- Persistence hooks: Create attachment set, flush, create part with FK, flush (line 576)
- Gaps: None
- Evidence: `plan.md:908-915`

**Behavior: KitService.create_kit() with attachment set**

- Scenarios:
  - Given valid kit data, When create kit, Then kit created with attachment_set_id populated and AttachmentSet exists (`tests/test_kit_service.py::test_create_kit_with_attachment_set`)
  - Given kit creation fails after attachment set created, When transaction rolls back, Then both kit and attachment set rolled back (`tests/test_kit_service.py::test_kit_creation_rollback_attachment_set`)
- Instrumentation: No new metrics
- Persistence hooks: Create attachment set, flush, create kit with FK, flush (line 590)
- Gaps: None
- Evidence: `plan.md:917-924`

**Behavior: Migration 020 (attachment set backfill)**

- Scenarios:
  - Given database with existing parts and attachments, When run migration, Then attachment_sets table created (`tests/test_migrations.py::test_migration_020_creates_attachment_sets`)
  - Given database with existing parts and attachments, When run migration, Then attachments table renamed and FK updated (`tests/test_migrations.py::test_migration_020_renames_attachments`)
  - Given database with existing parts, When run migration, Then each part has attachment_set_id populated (`tests/test_migrations.py::test_migration_020_backfills_parts`)
  - Given database with existing parts, When run migration, Then cover references moved to attachment sets (`tests/test_migrations.py::test_migration_020_migrates_covers`)
  - Given empty database, When run migration, Then schema created correctly (`tests/test_migrations.py::test_migration_020_empty_db`)
  - Given migration completed, When run downgrade, Then schema reverted (`tests/test_migrations.py::test_migration_020_downgrade`)
- Instrumentation: Migration progress logging (line 1056)
- Persistence hooks: Batch operations, constraints added AFTER backfill (line 726)
- Gaps: None—critical coverage for data migration
- Evidence: `plan.md:989-1000`

**Behavior: All new API endpoints**

- Scenarios: Comprehensive scenarios for POST/GET/PUT/DELETE on `/api/attachment-sets/{id}/...` endpoints covering success paths, validation errors, 404s, ownership checks
- Instrumentation: Standard HTTP metrics via prometheus-flask-exporter
- Persistence hooks: Service layer handles all persistence
- Gaps: None
- Evidence: `plan.md:926-987`

---

## 5) Adversarial Sweep

**Checks attempted:**

1. **Circular FK deadlock** — AttachmentSet.cover_attachment_id → Attachment, Attachment.attachment_set_id → AttachmentSet. Could block creation if FKs validated immediately.
   - Evidence: `plan.md:239-246, 1059-1062`
   - Why the plan holds: use_alter=True annotation explicitly documented (line 240), defers FK check until after both rows exist. Pattern proven in existing Part.cover_attachment_id (part.py:53).

2. **Part/Kit deletion orphaning AttachmentSet** — If FK cascade not set correctly, deleting Part could leave orphaned AttachmentSet.
   - Evidence: `plan.md:107-110, 279, 296`
   - Why the plan holds: Plan NOW specifies ON DELETE CASCADE for Part.attachment_set_id and Kit.attachment_set_id (lines 279, 296). AttachmentSet deletion cascades to Attachment (line 256). Full cascade chain: Part DELETE → AttachmentSet DELETE → Attachment DELETE.

3. **Migration backfill with orphaned cover_attachment_id** — Existing Part has cover_attachment_id pointing to deleted PartAttachment.
   - Evidence: `plan.md:1052-1056`
   - Risk documented but mitigation insufficient: Plan states "Add defensive checks for orphaned cover references" but doesn't specify the check logic. Migration could fail or set invalid cover_attachment_id on AttachmentSet.
   - **FINDING (Minor):** Migration should NULL out Part.cover_attachment_id if referenced PartAttachment doesn't exist BEFORE creating AttachmentSet. Add explicit step to backfill logic.

4. **Transaction rollback after S3 upload** — Attachment row flushed, S3 upload succeeds, then later operation fails.
   - Evidence: `plan.md:650-659, 699-703`
   - Why the plan holds: Plan follows flush-before-upload pattern (line 654). If transaction rolls back after S3 upload, CAS object remains in S3 but no DB row references it. Next upload with same content reuses CAS key (deduplication). S3 bloat risk acknowledged in line 1064-1068, accepted for MVP.

5. **AttachmentSetService dependencies missing URL processing** — Plan excludes html_handler, download_cache_service, url_interceptor_registry from AttachmentSetService.
   - Evidence: `plan.md:186-189, 876-884`
   - Why the plan holds: Test scenario at line 880-881 shows "URL processing complexity tested in existing document service tests—focus on set ownership here." AttachmentSetService can delegate URL content download to DocumentService.process_upload_url() (which has all URL dependencies), then attach the result. Pattern is sound.

6. **NOT NULL constraint blocks migration** — Adding attachment_set_id NOT NULL to parts/kits before backfill completes.
   - Evidence: `plan.md:726`
   - Why the plan holds: Plan states "Migration uses batch operations, adds constraints AFTER backfill completes" (line 726). Standard migration pattern: add column nullable, backfill data, alter column NOT NULL.

7. **Cover auto-assignment race condition** — Two concurrent uploads to attachment set with no cover.
   - Evidence: `plan.md:636-643, 658`
   - Why the plan holds: Plan states "Concurrent cover updates last-write-wins (acceptable for single-user app)" (line 658). Product brief confirms single user (product_brief.md:7-9). No locking needed.

8. **Test data FK violation** — parts.json or kits.json references non-existent attachment_set_id.
   - Evidence: `plan.md:729-735, 1046`
   - Why the plan holds: NOT NULL constraint enforces invariant (line 734). Implementation slice 6 requires "Validate test data loads successfully with FK constraints" (line 1046). Failure during load is acceptable—developer must fix JSON.

---

## 6) Derived-Value & Persistence Invariants

**Derived value: Part.cover_url**

- Source dataset: Unfiltered. Joins Part → AttachmentSet → Attachment via attachment_set.cover_attachment_id FK (model property reads relationship).
- Write / cleanup triggered: None. Read-only property for API serialization.
- Guards: Property checks attachment_set.cover_attachment exists and has_preview before building CAS URL (pattern from existing part.py:119-133). Returns None if checks fail.
- Invariant: cover_url is None OR a valid CAS URL pointing to an image attachment in the part's attachment set.
- Evidence: `plan.md:600-607`

**Derived value: Kit.cover_url**

- Source dataset: Unfiltered. Joins Kit → AttachmentSet → Attachment via attachment_set.cover_attachment_id FK.
- Write / cleanup triggered: None. Read-only property for API serialization (new property to be added to Kit model).
- Guards: Property checks attachment_set.cover_attachment exists and has_preview before building CAS URL. Returns None if checks fail.
- Invariant: cover_url is None OR a valid CAS URL pointing to an image attachment in the kit's attachment set.
- Evidence: `plan.md:609-616`

**Derived value: Attachment.attachment_url**

- Source dataset: Unfiltered. Reads s3_key, content_type, filename from Attachment instance columns.
- Write / cleanup triggered: None. Read-only property builds CAS URL from metadata.
- Guards: Returns None if s3_key is None (e.g., for URL-only attachments that don't store content).
- Invariant: attachment_url is None OR a valid CAS URL with content_type and filename query params.
- Evidence: `plan.md:618-625`

**Derived value: Next cover on attachment delete**

- Source dataset: **Filtered query.** Finds first image attachment in set ordered by created_at, **excluding deleted attachment.**
- Write / cleanup triggered: **Sets attachment_set.cover_attachment_id to new value or NULL. Persisted to database via flush.**
- Guards: Query wrapped in delete_attachment transaction. Filter ensures only IMAGE attachments considered. Ordering by created_at is deterministic. **Transaction rollback cleans up if deletion fails.**
- Invariant: After deleting cover attachment, cover_attachment_id points to oldest remaining image OR is NULL if no images remain.
- Evidence: `plan.md:627-634`

**Protection assessment:** Filtered query drives persistent write, BUT query filter is deterministic (created_at ordering, IMAGE type filter) and scoped to single attachment set. Delete operation is transactional—if cover reassignment fails, entire delete rolls back. Guards are sufficient. **Pass.**

**Derived value: Auto-cover on first upload**

- Source dataset: Unfiltered check. Reads attachment_set.cover_attachment_id to check if NULL.
- Write / cleanup triggered: **Sets cover_attachment_id to newly created attachment if set has no cover. Persisted via flush.**
- Guards: Check happens within create_file_attachment transaction. **Only sets if cover is NULL AND new attachment is IMAGE type.** Flush before S3 upload ensures rollback cleans up on failure.
- Invariant: If attachment set has no cover and an image is uploaded, that image becomes the cover.
- Evidence: `plan.md:636-643`

**Protection assessment:** Unfiltered read of attachment_set.cover_attachment_id, conditional write if NULL. Guards prevent setting cover for non-image attachments. Transaction ensures atomicity. **Pass.**

---

## 7) Risks & Mitigations

**Risk: Migration backfill with orphaned cover references**

- Risk: Existing Part.cover_attachment_id points to deleted PartAttachment, migration fails or sets invalid AttachmentSet.cover_attachment_id.
- Mitigation: Add explicit migration step to NULL out Part.cover_attachment_id if referenced PartAttachment.id doesn't exist. Verify on anonymized production data copy.
- Evidence: `plan.md:1052-1056` documents risk but mitigation lacks specifics.

**Risk: Circular FK dependency deadlock**

- Risk: AttachmentSet and Attachment have circular FKs, could block creation.
- Mitigation: use_alter=True on AttachmentSet.cover_attachment_id defers FK check (explicitly documented at line 240). Proven pattern from Part.cover_attachment_id.
- Evidence: `plan.md:1059-1062`

**Risk: Test data updates missed**

- Risk: Developer forgets to create attachment_sets.json or attachments.json, load-test-data fails.
- Mitigation: Implementation slice 6 includes test data file creation and FK constraint validation (line 1046). Failure is acceptable—developer must fix before proceeding.
- Evidence: `plan.md:1070-1074`

---

## 8) Confidence

Confidence: High — All five previously identified issues resolved with explicit plan updates. The plan demonstrates strong codebase fit (evidence citations from 15+ existing files), follows established patterns (S3 consistency, FK cascades, dependency injection), includes comprehensive test coverage (service, API, migration layers with 50+ scenarios), and documents all known risks with mitigations. The one remaining minor issue (migration orphaned cover handling) doesn't block implementation—it's a defensive check to add during migration development. The AttachmentSet aggregate design is sound with real FKs and clear ownership semantics.
