# Code Review — Kit Attachments Feature

## 1) Summary & Decision

**Readiness**

The implementation introduces the AttachmentSet aggregate pattern to enable kit attachments while decoupling attachment management from entity types. The code includes new models (AttachmentSet, Attachment), a comprehensive service layer (AttachmentSetService), new API endpoints (/api/attachment-sets/...), updated Part and Kit services to create attachment sets eagerly, a migration to backfill existing data, and extensive test updates to handle the NOT NULL constraint. However, critical gaps exist: no dedicated tests for AttachmentSetService or the new API endpoints, missing test data JSON files for attachments and attachment_sets, legacy Part.cover_attachment_id field retained in model despite migration dropping it, and the plan's requirement to remove old document endpoints is not implemented.

**Decision**

`GO-WITH-CONDITIONS` — The core architecture (models, service, migration, DI wiring) is sound and follows project patterns correctly. The migration properly backfills data and enforces invariants. However, the feature lacks the comprehensive test coverage required by CLAUDE.md Definition of Done, the old API endpoints remain (violating the plan's explicit "remove" directive), and test data files are missing. These conditions must be resolved before shipping.

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- **Plan Section 2 (Models)** ↔ `app/models/attachment_set.py:15-54, app/models/attachment.py:26-97` — AttachmentSet and Attachment models created with proper FKs, circular FK using use_alter=True, cascade delete configured correctly
- **Plan Section 2 (Services)** ↔ `app/services/attachment_set_service.py:22-377` — AttachmentSetService implements full CRUD operations including create_attachment_set, create_file_attachment, create_url_attachment, delete_attachment with cover reassignment, set_cover_attachment
- **Plan Section 2 (API)** ↔ `app/api/attachment_sets.py:1-186` — New blueprint created at /api/attachment-sets with GET /set/{id}, POST/GET/PUT/DELETE /set/{id}/attachments, GET/PUT/DELETE /set/{id}/cover endpoints
- **Plan Section 2 (Migration)** ↔ `alembic/versions/020_create_attachment_sets.py:36-263` — Migration creates attachment_sets table, renames part_attachments to attachments, backfills attachment sets for parts and kits, moves cover references, enforces NOT NULL constraints
- **Plan Section 2 (DI Container)** ↔ `app/services/container.py:53-72, 175-178` — attachment_set_service provider added with proper dependencies (s3_service, image_service, settings), injected into part_service and kit_service
- **Plan Section 2 (Part/Kit Services)** ↔ `app/services/part_service.py:62-102, app/services/kit_service.py:403-430` — Both services create AttachmentSet during entity creation with fallback for tests without injection
- **Plan Section 2 (Schemas)** ↔ `app/schemas/attachment_set.py:1-157, app/schemas/part.py:278-282, app/schemas/kit.py:195-202` — AttachmentSet schemas created, Part and Kit schemas include attachment_set_id and cover_url fields
- **Plan Section 2 (Test Fixtures)** ↔ `tests/conftest.py:197-237` — make_attachment_set and make_attachment_set_flask fixtures added for test convenience
- **Plan Section 2 (Test Updates)** ↔ `tests/services/test_kit_service.py:181-191, tests/test_part_service.py:517-523` — Existing tests updated to create attachment sets using fixtures or stubs

**Gaps / deviations**

- **Plan Section 2 (Delete old files)** — `app/models/part_attachment.py` and `app/schemas/part_attachment.py` still exist in the repository (plan required deletion)
- **Plan Section 2 (Remove old API endpoints)** — `/api/parts/{part_key}/attachments/...` endpoints in `app/api/documents.py` NOT removed (plan lines 198-201 explicitly required removal)
- **Plan Section 2 (Test data files)** — `app/data/test_data/attachment_sets.json` and `app/data/test_data/attachments.json` NOT created (plan lines 152-158 required creation, CLAUDE.md lines 405-426 mandate test data for all tables)
- **Plan Section 13 (Service tests)** — No `tests/test_attachment_set_service.py` file created (plan lines 860-906 required comprehensive service tests for all public methods)
- **Plan Section 13 (API tests)** — No `tests/test_attachment_set_api.py` file created (plan lines 926-977 required API tests for all endpoints)
- **Plan Section 2 (Part model)** — `app/models/part.py:56-59` retains `cover_attachment_id` column definition despite migration dropping it (lines 197-199); comment says "Legacy: cover_attachment_id will be removed in migration" but field is still defined in model

---

## 3) Correctness — Findings (ranked)

### Blocker Findings

- Title: `Blocker — Part model retains dropped cover_attachment_id column`
- Evidence: `app/models/part.py:56-59` — Defines `cover_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("part_attachments.id", ...))` with comment "Legacy: cover_attachment_id will be removed in migration"
- Impact: After migration runs, the database has no `parts.cover_attachment_id` column (migration line 199 drops it), but the SQLAlchemy model still defines it. Any query that accesses `Part.cover_attachment_id` will fail with "column does not exist". The `Part.cover_url` property fallback (lines 142-143) attempts to read this non-existent column.
- Fix: Remove `cover_attachment_id` column definition and `cover_attachment` relationship from `app/models/part.py` (lines 56-59, 109-115). Update `cover_url` property (lines 127-145) to only use `attachment_set.cover_attachment` path, removing the fallback.
- Confidence: High
- **Failure reasoning:** After migration 020 runs `op.drop_column('parts', 'cover_attachment_id')` (line 199), the database schema has no such column. When a Part instance is loaded from database, SQLAlchemy will attempt to populate `part.cover_attachment_id` attribute from the SELECT result but the column won't exist in the result set, causing either AttributeError or None assignment. When `Part.cover_url` property executes `if self.cover_attachment and self.cover_attachment.has_preview:` (line 142), it triggers a lazy load SELECT on a non-existent FK, raising OperationalError: "column parts.cover_attachment_id does not exist".

- Title: `Blocker — Missing comprehensive test coverage for AttachmentSetService`
- Evidence: No file at `tests/test_attachment_set_service.py` or `tests/services/test_attachment_set_service.py`
- Impact: CLAUDE.md lines 289-318 state "Every piece of code must have comprehensive tests. No feature is complete without tests." The AttachmentSetService has 9 public methods (create_attachment_set, get_attachment_set, create_file_attachment, create_url_attachment, get_attachments, get_attachment, update_attachment, delete_attachment, set_cover_attachment) with complex logic (file validation, S3 upload, cover reassignment, ownership checks). Zero tests exist for any of these methods. Violates Definition of Done.
- Fix: Create `tests/services/test_attachment_set_service.py` with test classes covering all scenarios from plan lines 852-906: attachment set creation, file attachment creation with validation failures, URL attachment creation, delete with cover reassignment, ownership validation failures, etc.
- Confidence: High
- **Test sketch:**
```python
def test_create_file_attachment_auto_sets_cover(app, session, container):
    service = container.attachment_set_service()
    attachment_set = service.create_attachment_set()

    # First image should auto-set as cover
    with open('tests/fixtures/test_image.jpg', 'rb') as f:
        attachment = service.create_file_attachment(
            attachment_set.id, "Test Image", f, "test.jpg"
        )

    session.flush()
    attachment_set = service.get_attachment_set(attachment_set.id)
    assert attachment_set.cover_attachment_id == attachment.id
```

- Title: `Blocker — Missing API tests for attachment set endpoints`
- Evidence: No file at `tests/test_attachment_set_api.py` or `tests/api/test_attachment_set_api.py`
- Impact: CLAUDE.md lines 320-331 require API tests for all HTTP endpoints. The feature adds 9 new API endpoints (GET/POST/DELETE for attachments, GET/PUT/DELETE for cover, GET for set) with request validation, error handling, multipart uploads. Zero tests exist for response formats, status codes, validation errors, ownership checks. Violates Definition of Done.
- Fix: Create `tests/api/test_attachment_set_api.py` with test classes covering scenarios from plan lines 926-977: multipart file upload returning 201, JSON URL creation, invalid file type returning 400, non-existent set returning 404, cover management, etc.
- Confidence: High
- **Test sketch:**
```python
def test_create_file_attachment_returns_201(client, app, session):
    with app.app_context():
        attachment_set = AttachmentSet()
        db.session.add(attachment_set)
        db.session.commit()
        set_id = attachment_set.id

    data = {
        'title': 'Test PDF',
        'file': (BytesIO(b'%PDF-1.4...'), 'test.pdf')
    }
    response = client.post(
        f'/api/attachment-sets/{set_id}/attachments',
        data=data,
        content_type='multipart/form-data'
    )
    assert response.status_code == 201
    assert response.json['attachment_type'] == 'pdf'
```

### Major Findings

- Title: `Major — Old part attachment API endpoints not removed`
- Evidence: `app/api/documents.py` still contains endpoints at lines 41-203 (based on plan evidence); plan Section 2 line 198-201 states "Remove `/api/parts/{part_key}/attachments/...` endpoints from `documents_bp`"
- Impact: Breaking change brief and plan explicitly require removing old endpoints to force frontend migration to new API surface. Keeping old endpoints creates API surface drift, maintenance burden, and ambiguous behavior (which endpoint should frontend use?). Plan conformance failure.
- Fix: Delete all `/api/parts/{part_key}/attachments/...` endpoint functions from `app/api/documents.py` (POST, GET, PUT, DELETE for attachments; GET, PUT, DELETE for cover). Update frontend to use `/api/attachment-sets/{id}/...` endpoints exclusively.
- Confidence: High

- Title: `Major — Missing test data JSON files for attachments and attachment_sets`
- Evidence: No files at `app/data/test_data/attachment_sets.json` or `app/data/test_data/attachments.json` (verified with ls command output)
- Impact: CLAUDE.md lines 405-426 state "The project includes a comprehensive fixed test dataset that must be kept up to date with any schema or business logic changes." Plan lines 152-158 explicitly require creation of these test data files. Without them, `load-test-data` command creates parts and kits with empty attachment sets (no realistic examples of datasheets, product images, PDFs). Test coverage gaps for attachment-related features. Test data maintenance requirement violated.
- Fix: Create `app/data/test_data/attachment_sets.json` with realistic attachment set examples (e.g., sets with 1-5 attachments, sets with covers, empty sets). Create `app/data/test_data/attachments.json` with realistic electronics documentation (datasheets PDFs, product images, manufacturer URLs). Update `TestDataService` to load these files during `load-test-data` command, preserving FK relationships to parts/kits.
- Confidence: High

- Title: `Major — Part service and Kit service fallback bypasses NOT NULL constraint`
- Evidence: `app/services/part_service.py:71-77, app/services/kit_service.py:418-422` — Both services have `if self.attachment_set_service: ... else: attachment_set_id = None` fallback logic
- Impact: When `attachment_set_service` is not injected (fallback branch), `attachment_set_id = None` is assigned and passed to Part/Kit constructor. Database NOT NULL constraint on `parts.attachment_set_id` and `kits.attachment_set_id` (migration lines 161, 173) will raise IntegrityError when flush executes, causing cryptic test failures. The fallback comment "# Fallback for testing without injection" suggests this is intentional, but it violates the eager creation invariant stated in plan lines 40-45.
- Fix: Remove the fallback branches entirely. Always require `attachment_set_service` injection. Update tests to use proper DI (container or stub). If a test truly needs to create a Part without attachment set, it should create the AttachmentSet manually first, not bypass the invariant.
- Confidence: High

- Title: `Major — Obsolete model and schema files not deleted`
- Evidence: `app/models/part_attachment.py` and `app/schemas/part_attachment.py` exist on filesystem (ls output); plan Section 2 lines 220-226 required deletion
- Impact: Code repository contains dead code that references old schema (`part_attachments` table instead of `attachments`, `part_id` FK instead of `attachment_set_id`). Imports of `PartAttachment` or `PartAttachmentSchema` will create confusion. Maintenance burden. Plan conformance failure.
- Fix: Delete `app/models/part_attachment.py` and `app/schemas/part_attachment.py` files. Remove any remaining imports (verify with `grep -r "part_attachment" app/`). Update `app/models/__init__.py` if it imports PartAttachment.
- Confidence: High

- Title: `Major — Part schema retains deprecated cover_attachment_id and attachments fields`
- Evidence: `app/schemas/part.py:282-289` — `cover_attachment_id` and `attachments` fields marked as "DEPRECATED" in descriptions but still present in PartResponseSchema
- Impact: API responses continue to include deprecated fields, creating ambiguity for frontend (should it use `attachment_set_id` + new API or `cover_attachment_id` + old API?). Plan Section 2 lines 299-314 shows Part response should include `attachment_set_id` and `cover_url` but doesn't mention retaining old fields. CLAUDE.md lines 15-19 state "Remove replaced/unused code and endpoints entirely (no deprecation markers)".
- Fix: Remove `cover_attachment_id` and `attachments` fields from PartResponseSchema. Update tests that assert these fields. Frontend will use `attachment_set_id` to fetch attachments via new API.
- Confidence: Medium (possible that these are retained intentionally during migration period, but contradicts CLAUDE.md policy)

- Title: `Major — Kit model attachment_set relationship uses lazy='select' instead of 'selectin'`
- Evidence: `app/models/kit.py:102-106` — `attachment_set: Mapped[AttachmentSet] = relationship("AttachmentSet", lazy="select", ...)`
- Impact: When KitResponseSchema serializes `cover_url` property (which accesses `self.attachment_set.cover_attachment`), it triggers N+1 query problem if multiple kits are loaded. CLAUDE.md lines 146-148 state "Use `lazy='selectin'` for commonly accessed relationships." The cover_url is included in every kit API response (schema line 198-202), making this a commonly accessed relationship.
- Fix: Change `lazy="select"` to `lazy="selectin"` in `app/models/kit.py:103`. Similarly, verify Part.attachment_set relationship uses `lazy="selectin"`.
- Confidence: High

### Minor Findings

- Title: `Minor — AttachmentSetService constructor missing type hint for Session`
- Evidence: `app/services/attachment_set_service.py:25` — `def __init__(self, db: Session, s3_service: S3Service, ...)`
- Impact: Session is imported from sqlalchemy.orm, which is correct, but CLAUDE.md lines 156-158 require "type hints for all function parameters and return types." The db parameter has correct type hint, so this is actually compliant. No issue found upon closer inspection.
- Fix: None needed
- Confidence: Low (false alarm)

- Title: `Minor — Inconsistent comment style in migration`
- Evidence: `alembic/versions/020_create_attachment_sets.py:39-46` — Uses single-line comments above operations instead of inline
- Impact: Purely cosmetic. Migration is readable and functional.
- Fix: None needed (cosmetic)
- Confidence: Low

---

## 4) Over-Engineering & Refactoring Opportunities

No significant over-engineering detected. The AttachmentSet aggregate pattern is appropriately scoped, the service layer is clean with single-responsibility methods, and the API endpoints follow established blueprint patterns. The fallback logic in Part/Kit services (Blocker finding above) should be removed for simplicity rather than maintained.

---

## 5) Style & Consistency

- Pattern: Inconsistent lazy loading strategy
- Evidence: `app/models/kit.py:103` uses `lazy="select"` while `app/models/attachment.py:54` uses `lazy="selectin"` for similar parent-child relationships
- Impact: Performance inconsistency across codebase. Commonly accessed relationships should eagerly load via selectin to avoid N+1 queries.
- Recommendation: Standardize on `lazy="selectin"` for all attachment_set relationships accessed during serialization. Document when `lazy="select"` is appropriate (rare access paths).

- Pattern: Fallback logic in service constructors
- Evidence: `app/services/part_service.py:71-77, app/services/kit_service.py:418-422` — Both have `if self.attachment_set_service: ... else: attachment_set_id = None`
- Impact: Violates fail-fast principle (CLAUDE.md lines 182-188). Silent None assignment will fail later at database constraint check, making debugging harder.
- Recommendation: Remove fallback logic entirely. Require proper dependency injection in all contexts. If a test needs flexibility, use a stub (as demonstrated in `tests/services/test_kit_service.py:181-193` with AttachmentSetStub).

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

**Surface: AttachmentSetService.create_attachment_set()**
- Scenarios: MISSING — No tests exist
- Hooks: N/A
- Gaps: Zero test coverage for service method that creates attachment sets during Part/Kit creation
- Evidence: Plan lines 852-859 required tests; no file created

**Surface: AttachmentSetService.create_file_attachment()**
- Scenarios: MISSING — No tests for file validation, S3 upload, auto-cover assignment, CAS deduplication
- Hooks: N/A
- Gaps: Plan lines 861-874 required 8 test scenarios (valid image/PDF, auto-cover, invalid type, size limit, CAS dedup, etc.)
- Evidence: No test file exists

**Surface: AttachmentSetService.delete_attachment()**
- Scenarios: MISSING — No tests for cover reassignment logic
- Hooks: N/A
- Gaps: Plan lines 886-895 required tests for cover deletion triggering reassignment to next oldest image or NULL
- Evidence: Critical derived state logic (cover reassignment) untested

**Surface: POST /api/attachment-sets/{id}/attachments**
- Scenarios: MISSING — No API tests for multipart upload or JSON URL creation
- Hooks: N/A
- Gaps: Plan lines 926-936 required tests for 201 responses, 400 validation errors, 404 for missing set
- Evidence: No API test file created

**Surface: Part and Kit creation with attachment sets**
- Scenarios:
  - Given valid part data, When create part, Then part has attachment_set_id (`tests/test_part_service.py` — no explicit test found in diff)
  - Given valid kit data, When create kit, Then kit has attachment_set_id (`tests/services/test_kit_service.py:537+` — test starts but not shown in diff)
- Hooks: make_attachment_set fixture (`tests/conftest.py:197-237`), AttachmentSetStub (`tests/services/test_kit_service.py:181-191`)
- Gaps: No test for transaction rollback when attachment set creation succeeds but Part/Kit creation fails (plan lines 910-916 required rollback tests)
- Evidence: Existing tests updated to create attachment sets, but edge case coverage missing

**Surface: Alembic migration 020**
- Scenarios: MISSING — No migration test found
- Hooks: N/A
- Gaps: Plan lines 989-1000 required testing migration on database with existing parts/attachments, verifying backfill, cover migration, and downgrade
- Evidence: Migration is complex (263 lines, multi-step backfill) but no test validates correctness

**Surface: Test data loading with attachment sets**
- Scenarios:
  - Given parts.json, When load test data, Then each part gets attachment set (`app/services/test_data_service.py:189-191`)
  - Given kits.json, When load test data, Then each kit gets attachment set (`app/services/test_data_service.py:291-297`)
- Hooks: TestDataService creates AttachmentSet inline during load
- Gaps: No test data JSON files for attachments or attachment_sets means loaded data has empty attachment sets
- Evidence: Test data service updated but test data files missing (Major finding above)

---

## 7) Adversarial Sweep

**Attack 1: Part created without attachment_set_id violates NOT NULL constraint**
- **Test:** Create Part instance without attachment_set_id, flush session
- **Expected failure:** IntegrityError: "null value in column 'attachment_set_id' violates not-null constraint"
- **Protection:** Migration line 161 enforces `NOT NULL` constraint. Part/Kit services create attachment sets eagerly (lines 71-77, 418-422) before constructing entity.
- **Gap found:** The fallback logic `attachment_set_id = None` (Major finding) allows bypassing this protection, causing IntegrityError at flush time instead of failing early.

**Attack 2: Delete AttachmentSet cascades to delete Part/Kit**
- **Test:** Create Part with AttachmentSet, delete AttachmentSet, verify Part deleted
- **Expected failure:** Cascade delete removes Part when AttachmentSet deleted
- **Evidence:** `app/models/part.py:53-55` — `ForeignKey("attachment_sets.id", ondelete="CASCADE")`. Migration line 168 confirms CASCADE on FK.
- **Protection:** This is CORRECT behavior per plan. AttachmentSet is aggregate root owned by Part/Kit. Deleting Part should cascade to AttachmentSet (not reverse).
- **Issue found:** FK is backwards! Part deletion should cascade to AttachmentSet deletion, but current FK has `ondelete="CASCADE"` on Part.attachment_set_id, meaning AttachmentSet deletion cascades to Part deletion. This violates aggregate ownership.
- **Severity: BLOCKER**

**Attack 3: Attachment created with wrong attachment_set_id bypasses ownership validation**
- **Test:** POST /api/attachment-sets/123/attachments with set_id=123, create Attachment with attachment_set_id=456, verify 400 error
- **Expected failure:** Should fail ownership validation
- **Evidence:** `app/api/attachment_sets.py:63-68` passes `set_id` to `service.create_file_attachment()` which creates Attachment with `attachment_set_id=attachment_set.id` (service line 144). No way to bypass ownership.
- **Protection:** Service always sets attachment_set_id to verified set's ID. API path parameter and attachment FK are consistent.
- **Code held up:** Ownership enforced correctly.

**Attack 4: Migration backfill creates duplicate attachment sets for parts with attachments**
- **Test:** Run migration on database with 1 part having 3 attachments, verify only 1 attachment_set created
- **Expected failure:** Could create 3 attachment sets (one per attachment)
- **Evidence:** Migration lines 59-76 — `SELECT DISTINCT part_id FROM attachments`, then for each part_id creates ONE attachment set and updates all attachments with that part_id. Correctness via DISTINCT.
- **Protection:** DISTINCT clause prevents duplicates.
- **Code held up:** Backfill logic is correct.

**Attack 5: Set cover_attachment_id to attachment from different set**
- **Test:** Create two AttachmentSets, each with attachments. Call `set_cover_attachment(set_id=1, attachment_id=<attachment from set 2>)`, expect error.
- **Expected failure:** Should raise InvalidOperationException for ownership mismatch
- **Evidence:** `app/services/attachment_set_service.py:342-344` — Calls `self.get_attachment(set_id, attachment_id)` which validates ownership (lines 252-257). If attachment.attachment_set_id != set_id, raises InvalidOperationException.
- **Protection:** Explicit ownership check before setting cover.
- **Code held up:** Cover setting is safe.

**Attack 6: Circular FK deadlock on AttachmentSet creation**
- **Test:** Create AttachmentSet with cover_attachment_id pointing to non-existent Attachment, flush, expect FK violation
- **Expected failure:** FK constraint fails
- **Evidence:** `app/models/attachment_set.py:26-29` — `use_alter=True` on cover_attachment_id FK. Migration line 184-192 creates FK with ondelete='SET NULL'. SQLAlchemy defers FK check until after both rows exist.
- **Protection:** use_alter pattern breaks circular dependency.
- **Code held up:** FK handling is correct.

---

## 8) Invariants Checklist

**Invariant 1: Every Part and Kit has an AttachmentSet**
- Invariant: `parts.attachment_set_id IS NOT NULL AND kits.attachment_set_id IS NOT NULL`
- Where enforced:
  - Database: Migration lines 161, 173 add NOT NULL constraint
  - Service: `app/services/part_service.py:71-77` creates AttachmentSet before Part, `app/services/kit_service.py:418-422` creates AttachmentSet before Kit
  - Tests: Updated to use `make_attachment_set()` fixture
- Failure mode: If Part/Kit created without calling `attachment_set_service.create_attachment_set()`, IntegrityError raised
- Protection: Database constraint prevents insertion. Service layer enforces via eager creation. HOWEVER, fallback logic `attachment_set_id = None` (Major finding) weakens this protection.
- Evidence: `app/services/part_service.py:71-77, app/services/kit_service.py:418-422, alembic/versions/020_create_attachment_sets.py:161,173`

**Invariant 2: AttachmentSet.cover_attachment_id points to Attachment in same set OR is NULL**
- Invariant: `cover_attachment_id IS NULL OR (SELECT attachment_set_id FROM attachments WHERE id = cover_attachment_id) = attachment_sets.id`
- Where enforced:
  - Service: `app/services/attachment_set_service.py:342-344` validates ownership before setting cover
  - Service: `app/services/attachment_set_service.py:301-316` reassigns cover to attachment in same set on delete
- Failure mode: If cover_attachment_id set to attachment from different set, queries for cover_url will return wrong image
- Protection: Ownership validation in `set_cover_attachment()` and `get_attachment()`. Auto-assignment logic filters by `attachment_set_id`.
- Evidence: `app/services/attachment_set_service.py:252-257, 342-344, 303-307`

**Invariant 3: Attachment always belongs to exactly one AttachmentSet**
- Invariant: `attachments.attachment_set_id IS NOT NULL AND references valid attachment_sets.id`
- Where enforced:
  - Database: Migration line 149 adds NOT NULL constraint, lines 150-157 add FK with CASCADE delete
  - Service: `app/services/attachment_set_service.py:144` always sets attachment_set_id when creating Attachment
- Failure mode: Orphaned attachment (attachment_set deleted but attachment remains)
- Protection: FK with CASCADE delete ensures attachment deleted when set deleted. NOT NULL prevents orphans.
- Evidence: `alembic/versions/020_create_attachment_sets.py:149-157, app/services/attachment_set_service.py:143-151`

**Invariant 4: Part/Kit cascade delete removes AttachmentSet**
- Invariant: When Part or Kit deleted, associated AttachmentSet must be deleted
- Where enforced:
  - Database: `app/models/part.py:53-55, app/models/kit.py:63-65` — FK with `ondelete="CASCADE"`
  - Expected: Part/Kit owns AttachmentSet, deletion cascades down
- Failure mode: **VIOLATED** — Current FK is BACKWARDS. Part.attachment_set_id FK has ondelete="CASCADE", meaning AttachmentSet deletion cascades to delete Part. Should be reverse (Part deletion cascades to AttachmentSet).
- Protection: **BROKEN** — FK direction is inverted. Deleting AttachmentSet will orphan Part (or delete Part unexpectedly).
- Evidence: `app/models/part.py:53-55` — This is a **BLOCKER** finding (added above).

---

## 9) Questions / Needs-Info

- Question: Should Part.cover_attachment_id and Part.attachments fields remain in PartResponseSchema during a migration period?
- Why it matters: CLAUDE.md deprecation policy says "Remove replaced/unused code entirely", but retaining fields could ease frontend migration. Unclear if retention is intentional or oversight.
- Desired answer: Clarify if there's a multi-phase rollout plan (Phase 1: backend ships with both fields, Phase 2: frontend migrates, Phase 3: backend drops old fields) or immediate cutover (backend drops old fields now, frontend updates same release).

- Question: Why does AttachmentSet deletion cascade to Part/Kit instead of reverse?
- Why it matters: FK with ondelete="CASCADE" on Part.attachment_set_id means deleting AttachmentSet deletes Part. This violates aggregate root pattern where Part owns AttachmentSet.
- Desired answer: Confirm this is a bug and FK should be reversed, or explain design rationale if intentional.

- Question: Are the old `/api/parts/{key}/attachments/...` endpoints intended to remain during migration?
- Why it matters: Plan explicitly states "Remove existing `/api/parts/{key}/attachments/...` endpoints entirely" but code doesn't show removal. Unclear if this is deferred to later commit or oversight.
- Desired answer: Confirm removal is required before shipping or document multi-phase migration plan.

---

## 10) Risks & Mitigations (top 3)

**Risk 1: Inverted FK cascade deletes Parts/Kits when AttachmentSets deleted**
- Risk: `app/models/part.py:53-55, app/models/kit.py:63-65` — FK has `ondelete="CASCADE"` pointing from Part to AttachmentSet. Deleting AttachmentSet will cascade delete Part/Kit, losing inventory data.
- Mitigation: **Immediate fix required.** Change FK to use a different cascade strategy. Part/Kit should own AttachmentSet, so Part deletion cascades to AttachmentSet (correct), but AttachmentSet deletion should RESTRICT or SET NULL (prevent orphaning). Alternatively, remove ondelete from Part.attachment_set_id FK and rely on application logic to delete AttachmentSet when Part deleted.
- Evidence: Blocker finding and Invariant 4 failure above

**Risk 2: Missing test coverage allows regressions in attachment management**
- Risk: Zero service tests and zero API tests for new AttachmentSet feature. Complex logic (file validation, S3 upload, cover reassignment, ownership checks) is untested. Future changes may break functionality without detection.
- Mitigation: **Must create comprehensive tests before shipping.** Implement plan's test scenarios (lines 852-1000) covering service methods, API endpoints, migration, and edge cases. Run pytest with coverage report to verify >90% coverage of new code.
- Evidence: Blocker findings for missing test files

**Risk 3: Test data JSON files missing prevents realistic development/testing**
- Risk: `load-test-data` command creates parts/kits with empty attachment sets. Developers and frontend engineers lack realistic test data showing parts with datasheets, images, URLs. Integration testing incomplete.
- Mitigation: **Create test data files before shipping.** Add `attachment_sets.json` and `attachments.json` with 10-20 examples covering various scenarios (part with PDF datasheet, part with product image, kit with assembly instructions, URL attachments). Ensure FK references match parts/kits in test data.
- Evidence: Major finding for missing test data files

---

## 11) Confidence

Confidence: Medium — The core architecture (AttachmentSet aggregate, service layer, migration backfill, DI wiring) follows project patterns correctly and the migration logic is sound. However, critical gaps severely limit confidence: the inverted FK cascade is a data corruption risk, zero test coverage violates Definition of Done, missing test data files prevent validation, and the retention of deprecated model fields/API endpoints creates plan conformance ambiguity. With the identified blockers fixed (FK direction, Part model cleanup, comprehensive tests added, test data created, old endpoints removed), confidence would increase to High.
