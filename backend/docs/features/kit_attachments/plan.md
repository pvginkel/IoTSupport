# Kit Attachments — Technical Plan

## 0) Research Log & Findings

### Discovery Work

**Existing attachment infrastructure:**
- Examined `/work/backend/app/models/part_attachment.py` (lines 1-97): Current `PartAttachment` model with `part_id` FK, attachment types (URL, IMAGE, PDF), S3 key storage, CAS URL generation
- Examined `/work/backend/app/models/part.py` (lines 52-111): Part model has `cover_attachment_id` FK pointing to `part_attachments` table
- Examined `/work/backend/app/services/document_service.py` (lines 1-581): Comprehensive service handling file uploads, URL attachments, S3 operations, cover management
- Examined `/work/backend/app/api/documents.py` (lines 1-303): Blueprint at `/api/parts/{part_key}/attachments/...` with full CRUD operations
- Examined `/work/backend/app/schemas/part_attachment.py` (lines 1-184): Request/response schemas for attachments

**Kit infrastructure:**
- Examined `/work/backend/app/models/kit.py` (lines 1-115): Kit model lacks any attachment-related fields
- Examined `/work/backend/app/schemas/kit.py` (lines 1-621): No attachment fields in any kit schemas
- Examined migration `/work/backend/alembic/versions/004_add_document_tables.py`: Original attachment table creation with `part_id` FK

**Service container and wiring:**
- Examined `/work/backend/app/services/container.py` (lines 1-246): `DocumentService` is Factory provider with dependencies on S3, image, HTML handler services
- Examined `/work/backend/app/__init__.py` (lines 130-138): Container wired to `app.api.documents` module
- Examined `/work/backend/app/api/__init__.py` (lines 1-48): `documents_bp` registered under main `api_bp`

**Testing infrastructure:**
- Identified test files: `test_document_api.py`, `test_document_service.py`, `test_document_integration.py`, `test_document_fixtures.py`
- Examined `/work/backend/tests/test_document_api.py` (lines 1-50): Tests use `/api/parts/{part_key}/attachments` endpoints

**Test data:**
- Found test data files in `/work/backend/app/data/test_data/`: parts.json, kits.json, kit_contents.json, etc.
- No existing attachment test data files

### Key Findings

1. **No backwards compatibility needed**: Per change brief and CLAUDE.md, this is a BFF backend—frontend changes accompany backend changes, so we can freely break existing APIs.

2. **Complete removal required**: Change brief explicitly states "Remove existing `/api/parts/{key}/attachments/...` endpoints entirely" and "Remove existing PartAttachmentService and related code - don't try to refactor it".

3. **AttachmentSet as aggregate root**: The design introduces a new first-class entity that owns attachments and cover state, with Parts and Kits holding FKs to their attachment sets.

4. **Real foreign keys only**: No polymorphic associations—`attachment_set_id` is a real FK with cascade delete.

5. **Eager creation invariant**: Every Part and Kit must have an AttachmentSet created at entity creation time. The `attachment_set_id` column is NOT NULL.

6. **New API surface**: `/api/attachment-sets/{id}/...` completely replaces the old part-centric endpoints.

7. **Migration complexity**: Existing parts have attachments that must be migrated to new schema—create attachment sets, move attachments, update FKs, preserve cover references.

### Conflicts Resolved

- **Service naming**: Change brief doesn't mention "PartAttachmentService" by name because it doesn't exist—the service is `DocumentService`. The intent is clear: remove the part-specific attachment logic from DocumentService and replace with attachment-set logic.

- **Backwards compatibility**: CLAUDE.md deprecation policy confirms no backwards compatibility needed, so we remove old endpoints entirely rather than deprecating them.

- **Test data updates**: CLAUDE.md explicitly requires test data in `/work/backend/app/data/test_data/` to be updated with schema changes. We'll need to backfill attachment sets for existing parts in test data.

---

## 1) Intent & Scope

**User intent**

Enable kits to have attachments (PDFs, images, URLs) by introducing a reusable AttachmentSet aggregate that decouples attachment management from specific entity types. Both parts and kits will reference an attachment set, allowing a unified UI component and API surface for managing attachments across entity types.

**Prompt quotes**

"Add attachment support for kits by introducing an `AttachmentSet` aggregate that decouples attachment management from specific entity types."

"AttachmentSet as aggregate — A new entity that owns attachments and cover image state. Parts and kits hold a foreign key to their attachment set."

"Remove existing `/api/parts/{key}/attachments/...` endpoints entirely (no backwards compatibility)"

"Remove existing PartAttachmentService and related code - don't try to refactor it"

"Real foreign keys everywhere — `Attachment.attachment_set_id` → `attachment_sets.id` with cascade delete."

"Eager creation — Every Part and Kit gets an AttachmentSet created at entity creation time. Invariant: `attachment_set_id` is always populated."

**In scope**

- Create `AttachmentSet` model with `cover_attachment_id` FK
- Create `Attachment` model (renamed from `PartAttachment`) with `attachment_set_id` FK
- Add `attachment_set_id` column to `parts` and `kits` tables (NOT NULL)
- Remove `cover_attachment_id` from `parts` table
- Create `AttachmentSetService` with all attachment CRUD operations
- Create new API blueprint `/api/attachment-sets/{id}/...` with full CRUD
- Remove `/api/parts/{part_key}/attachments/...` endpoints from `documents_bp`
- Update Part and Kit response schemas to include `attachment_set_id`
- Update `PartService` and `KitService` to create attachment sets eagerly
- Write migration to backfill attachment sets for existing parts
- Update test data JSON files to include attachment set relationships
- Write comprehensive service tests for `AttachmentSetService`
- Write comprehensive API tests for attachment set endpoints
- Remove old document API tests that use part-specific endpoints

**Out of scope**

- Attachment copying between sets (per change brief exclusions)
- Sharing attachment sets between entities (enforced by application logic)
- Changes to S3/CAS storage layer
- URL preview functionality (remains in document service for AI/upload workflows)
- HTML document handler changes
- Image service changes
- Frontend implementation (documented separately)

**Assumptions / constraints**

- SQLAlchemy cascade behavior handles attachment cleanup when sets are deleted
- CAS storage means S3 keys can be reused (content-addressed, immutable)
- Migration runs on existing production data with parts that have attachments
- Test data loader runs after migration to populate attachment sets
- Service container dependency injection patterns remain unchanged
- SpectTree OpenAPI documentation auto-generates from new endpoints

---

## 2) Affected Areas & File Map

**New files (create):**

- Area: `app/models/attachment_set.py`
- Why: Define AttachmentSet model with cover_attachment_id FK and timestamps
- Evidence: Change brief lines 33-42 specify table schema; no existing file

- Area: `app/models/attachment.py`
- Why: Define Attachment model renamed from PartAttachment with attachment_set_id FK
- Evidence: Change brief lines 44-58 specify renamed table and FK change; `/work/backend/app/models/part_attachment.py` exists but will be deleted

- Area: `app/services/attachment_set_service.py`
- Why: Service layer for attachment set CRUD operations, file uploads, S3 integration
- Evidence: Change brief line 130 mentions "Attachment logic is fully isolated in its own service"; no existing AttachmentSetService

- Area: `app/api/attachment_sets.py`
- Why: New blueprint for `/api/attachment-sets/{id}/...` endpoints
- Evidence: Change brief lines 71-83 define new API surface; no existing file

- Area: `app/schemas/attachment_set.py`
- Why: Request/response schemas for attachment set operations
- Evidence: Follows pattern from `/work/backend/app/schemas/part_attachment.py:1-184`; new schemas needed for set-level operations

- Area: `tests/test_attachment_set_service.py`
- Why: Comprehensive service tests for attachment set operations
- Evidence: CLAUDE.md lines 289-318 require service tests; no existing file

- Area: `tests/test_attachment_set_api.py`
- Why: API tests for attachment set endpoints
- Evidence: CLAUDE.md lines 320-331 require API tests; no existing file

- Area: `alembic/versions/020_create_attachment_sets.py`
- Why: Migration to create attachment_sets table, rename part_attachments to attachments, backfill data
- Evidence: Change brief lines 112-116 describe migration requirements; next revision number is 020

- Area: `app/data/test_data/attachment_sets.json`
- Why: Test data for attachment sets with cover references; required for test data loader
- Evidence: CLAUDE.md lines 405-426 require test data for all tables; attachment sets need explicit JSON file

- Area: `app/data/test_data/attachments.json`
- Why: Test data for attachments (images, PDFs, URLs) linked to attachment sets; required for test data loader
- Evidence: CLAUDE.md lines 405-426 require test data for all tables; attachments need explicit JSON file

**Modified files:**

- Area: `app/models/part.py`
- Why: Add attachment_set_id FK (NOT NULL), remove cover_attachment_id, update relationships
- Evidence: `/work/backend/app/models/part.py:52-54` shows cover_attachment_id FK; change brief lines 62-64 specify changes

- Area: `app/models/kit.py`
- Why: Add attachment_set_id FK (NOT NULL)
- Evidence: `/work/backend/app/models/kit.py:1-115` shows no attachment fields; change brief lines 66-67 specify addition

- Area: `app/schemas/part.py`
- Why: Add attachment_set_id field to PartResponseSchema and related schemas
- Evidence: Change brief lines 86-98 show response format change; `/work/backend/app/schemas/part.py` exists

- Area: `app/schemas/kit.py`
- Why: Add attachment_set_id field to KitResponseSchema and related schemas
- Evidence: Change brief lines 86-98 imply kits get same treatment; `/work/backend/app/schemas/kit.py:170-237` shows KitResponseSchema

- Area: `app/services/part_service.py`
- Why: Create AttachmentSet during part creation, wire attachment_set_service dependency
- Evidence: Change brief lines 103-105 describe creation lifecycle; `/work/backend/app/services/part_service.py` exists

- Area: `app/services/kit_service.py`
- Why: Create AttachmentSet during kit creation, wire attachment_set_service dependency
- Evidence: Change brief lines 103-105 apply to both entities; `/work/backend/app/services/kit_service.py` exists

- Area: `app/services/container.py`
- Why: Add attachment_set_service Factory provider with dependencies: db_session, s3_service, image_service, settings (pattern from document_service but excluding html_handler, download_cache_service, url_interceptor_registry which are URL-processing only)
- Evidence: `/work/backend/app/services/container.py:171-180` shows document_service provider pattern

- Area: `app/__init__.py`
- Why: Add 'app.api.attachment_sets' to wire_modules list
- Evidence: `/work/backend/app/__init__.py:130-138` shows wiring pattern

- Area: `app/api/__init__.py`
- Why: Import and register attachment_sets_bp blueprint
- Evidence: `/work/backend/app/api/__init__.py:14-47` shows blueprint registration pattern

- Area: `app/api/documents.py`
- Why: Remove all `/api/parts/{part_key}/attachments/...` endpoints (lines 92-203)
- Evidence: `/work/backend/app/api/documents.py:92-203` shows endpoints to remove; change brief confirms deletion

- Area: `app/data/test_data/parts.json`
- Why: Add attachment_set_id values for each part, remove cover_attachment_id references
- Evidence: CLAUDE.md lines 405-426 require test data updates; `/work/backend/app/data/test_data/parts.json` exists

- Area: `app/data/test_data/kits.json`
- Why: Add attachment_set_id values for each kit
- Evidence: Test data maintenance requirement applies to kits too

- Area: `tests/test_document_api.py`
- Why: Delete tests using old part attachment endpoints
- Evidence: `/work/backend/tests/test_document_api.py:38-44` shows old API usage; new tests go in test_attachment_set_api.py

- Area: `tests/test_document_service.py`
- Why: Remove part-specific attachment tests, keep URL processing tests
- Evidence: Document service will retain URL processing for AI workflows but not part attachment CRUD

**Deleted files:**

- Area: `app/models/part_attachment.py`
- Why: Replaced by app/models/attachment.py with renamed table and FK
- Evidence: `/work/backend/app/models/part_attachment.py:1-97` defines PartAttachment; change brief lines 44-58 show replacement

- Area: `app/schemas/part_attachment.py`
- Why: Replaced by app/schemas/attachment_set.py with set-centric schemas
- Evidence: `/work/backend/app/schemas/part_attachment.py:1-184` shows part-centric schemas; change brief requires entity-agnostic design

---

## 3) Data Model / Contracts

**New table: attachment_sets**

- Entity / contract: attachment_sets table
- Shape:
  ```sql
  attachment_sets (
    id SERIAL PRIMARY KEY,
    cover_attachment_id INTEGER REFERENCES attachments(id) ON DELETE SET NULL,
    -- SQLAlchemy: use_alter=True to defer FK check (circular ref with attachments)
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
  )
  ```
- Refactor strategy: New table, no back-compat needed. Use `use_alter=True` on cover_attachment_id FK in SQLAlchemy model (pattern from `/work/backend/app/models/part.py:52-53`).
- Evidence: Change brief lines 33-42

**Renamed/modified table: attachments (from part_attachments)**

- Entity / contract: attachments table (renamed from part_attachments)
- Shape:
  ```sql
  attachments (
    id SERIAL PRIMARY KEY,
    attachment_set_id INTEGER NOT NULL REFERENCES attachment_sets(id) ON DELETE CASCADE,
    attachment_type ENUM('url', 'image', 'pdf') NOT NULL,
    title VARCHAR(255) NOT NULL,
    s3_key VARCHAR(500),
    url VARCHAR(2000),
    filename VARCHAR(255),
    content_type VARCHAR(100),
    file_size INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
  )
  -- Columns removed: part_id
  -- Columns added: attachment_set_id
  ```
- Refactor strategy: Rename table, drop part_id column, add attachment_set_id FK with cascade delete. No back-compat—migration handles data transformation.
- Evidence: Change brief lines 44-60; `/work/backend/app/models/part_attachment.py:26-56`

**Modified table: parts**

- Entity / contract: parts table
- Shape:
  ```sql
  parts (
    -- Existing columns unchanged...
    attachment_set_id INTEGER NOT NULL REFERENCES attachment_sets(id) ON DELETE CASCADE,
    -- Removed: cover_attachment_id
  )
  ```
- Refactor strategy: Drop cover_attachment_id FK and column, add attachment_set_id NOT NULL FK with CASCADE delete (Part deletion cascades to delete AttachmentSet). Migration backfills values before adding constraint.
- Evidence: Change brief lines 62-65, 107-110; `/work/backend/app/models/part.py:52-54`

**Modified table: kits**

- Entity / contract: kits table
- Shape:
  ```sql
  kits (
    -- Existing columns unchanged...
    attachment_set_id INTEGER NOT NULL REFERENCES attachment_sets(id) ON DELETE CASCADE
  )
  ```
- Refactor strategy: Add attachment_set_id NOT NULL FK with CASCADE delete (Kit deletion cascades to delete AttachmentSet). Migration creates attachment sets for all kits before adding constraint.
- Evidence: Change brief lines 66-67, 107-110; `/work/backend/app/models/kit.py:1-68`

**API response contract: PartResponseSchema**

- Entity / contract: PartResponseSchema
- Shape:
  ```json
  {
    "id": 1,
    "key": "ABCD",
    "description": "10K Resistor",
    "attachment_set_id": 42,
    "cover_url": "/api/cas/abc123..."
  }
  ```
- Refactor strategy: Add attachment_set_id field, keep cover_url as computed property for backwards-compatible display. Remove cover_attachment_id from schema.
- Evidence: Change brief lines 86-98; `/work/backend/app/schemas/part.py` exists

**API response contract: KitResponseSchema**

- Entity / contract: KitResponseSchema
- Shape:
  ```json
  {
    "id": 17,
    "name": "Synth Voice",
    "attachment_set_id": 43,
    "cover_url": "/api/cas/def456..."
  }
  ```
- Refactor strategy: Add attachment_set_id field, add cover_url computed property. No previous attachment fields exist.
- Evidence: Change brief lines 86-98; `/work/backend/app/schemas/kit.py:170-237`

**API request contract: AttachmentSetCreateFileSchema**

- Entity / contract: Multipart form data for file upload
- Shape:
  ```
  POST /api/attachment-sets/{id}/attachments
  Content-Type: multipart/form-data

  title: "Datasheet"
  file: <binary data>
  ```
- Refactor strategy: New endpoint replacing `/api/parts/{key}/attachments`. Same multipart format.
- Evidence: `/work/backend/app/api/documents.py:93-121` shows existing pattern; change brief lines 77-78

**API request contract: AttachmentSetCreateUrlSchema**

- Entity / contract: JSON payload for URL attachment
- Shape:
  ```json
  {
    "title": "Product Page",
    "url": "https://example.com/part"
  }
  ```
- Refactor strategy: New endpoint, same JSON schema as old part attachment URL creation
- Evidence: `/work/backend/app/schemas/part_attachment.py:22-38` shows existing schema; change brief lines 77-78

---

## 4) API / Integration Surface

**New: GET /api/attachment-sets/{id}**

- Surface: GET /api/attachment-sets/{id}
- Inputs: Path parameter `id` (integer, attachment set ID)
- Outputs: JSON with attachment set ID, list of attachments, cover attachment details. Status 200 on success.
- Errors: 404 if attachment set not found
- Evidence: Change brief line 77; pattern from `/work/backend/app/api/documents.py:76-89`

**New: POST /api/attachment-sets/{id}/attachments**

- Surface: POST /api/attachment-sets/{id}/attachments
- Inputs: Multipart form data (title, file) OR JSON (title, url). Path parameter `id`.
- Outputs: Created attachment details (id, type, title, URLs). Status 201 on success.
- Errors: 400 for validation errors, 404 if set not found, 413 if file too large
- Evidence: Change brief line 78; `/work/backend/app/api/documents.py:93-136`

**New: GET /api/attachment-sets/{id}/attachments**

- Surface: GET /api/attachment-sets/{id}/attachments
- Inputs: Path parameter `id`
- Outputs: JSON array of attachment list schemas. Status 200 on success.
- Errors: 404 if attachment set not found
- Evidence: Change brief line 79; `/work/backend/app/api/documents.py:138-145`

**New: GET /api/attachment-sets/{id}/attachments/{attachment_id}**

- Surface: GET /api/attachment-sets/{id}/attachments/{attachment_id}
- Inputs: Path parameters `id` (set ID), `attachment_id` (attachment ID)
- Outputs: Full attachment response schema. Status 200 on success.
- Errors: 404 if attachment or set not found, 400 if attachment doesn't belong to set
- Evidence: Change brief line 80; `/work/backend/app/api/documents.py:148-155`

**New: PUT /api/attachment-sets/{id}/attachments/{attachment_id}**

- Surface: PUT /api/attachment-sets/{id}/attachments/{attachment_id}
- Inputs: JSON with optional title field. Path parameters `id`, `attachment_id`.
- Outputs: Updated attachment response schema. Status 200 on success.
- Errors: 404 if not found, 400 for validation or ownership errors
- Evidence: Change brief line 81; `/work/backend/app/api/documents.py:158-167`

**New: DELETE /api/attachment-sets/{id}/attachments/{attachment_id}**

- Surface: DELETE /api/attachment-sets/{id}/attachments/{attachment_id}
- Inputs: Path parameters `id`, `attachment_id`
- Outputs: Empty body. Status 204 on success.
- Errors: 404 if not found, 400 if ownership mismatch
- Evidence: Change brief line 82; `/work/backend/app/api/documents.py:170-178`

**New: GET /api/attachment-sets/{id}/cover**

- Surface: GET /api/attachment-sets/{id}/cover
- Inputs: Path parameter `id`
- Outputs: JSON with cover_attachment_id and optional attachment details. Status 200 on success.
- Errors: 404 if attachment set not found
- Evidence: Change brief line 83; `/work/backend/app/api/documents.py:76-89`

**New: PUT /api/attachment-sets/{id}/cover**

- Surface: PUT /api/attachment-sets/{id}/cover
- Inputs: JSON with attachment_id (integer or null). Path parameter `id`.
- Outputs: Updated cover attachment response. Status 200 on success.
- Errors: 404 if set or attachment not found, 400 if attachment doesn't belong to set
- Evidence: Change brief line 84; `/work/backend/app/api/documents.py:41-57`

**New: DELETE /api/attachment-sets/{id}/cover**

- Surface: DELETE /api/attachment-sets/{id}/cover
- Inputs: Path parameter `id`
- Outputs: JSON with cover_attachment_id=null. Status 200 on success.
- Errors: 404 if attachment set not found
- Evidence: Change brief line 85; `/work/backend/app/api/documents.py:60-73`

**Removed: POST /api/parts/{part_key}/attachments**

- Surface: POST /api/parts/{part_key}/attachments
- Inputs: N/A (endpoint removed)
- Outputs: N/A
- Errors: 404 after removal
- Evidence: `/work/backend/app/api/documents.py:93-136`; change brief confirms removal

**Removed: GET /api/parts/{part_key}/attachments**

- Surface: GET /api/parts/{part_key}/attachments
- Inputs: N/A (endpoint removed)
- Outputs: N/A
- Errors: 404 after removal
- Evidence: `/work/backend/app/api/documents.py:138-145`

**Removed: GET /api/parts/{part_key}/attachments/{attachment_id}**

- Surface: GET /api/parts/{part_key}/attachments/{attachment_id}
- Inputs: N/A (endpoint removed)
- Outputs: N/A
- Errors: 404 after removal
- Evidence: `/work/backend/app/api/documents.py:148-155`

**Removed: PUT /api/parts/{part_key}/attachments/{attachment_id}**

- Surface: PUT /api/parts/{part_key}/attachments/{attachment_id}
- Inputs: N/A (endpoint removed)
- Outputs: N/A
- Errors: 404 after removal
- Evidence: `/work/backend/app/api/documents.py:158-167`

**Removed: DELETE /api/parts/{part_key}/attachments/{attachment_id}**

- Surface: DELETE /api/parts/{part_key}/attachments/{attachment_id}
- Inputs: N/A (endpoint removed)
- Outputs: N/A
- Errors: 404 after removal
- Evidence: `/work/backend/app/api/documents.py:170-178`

**Removed: GET /api/parts/{part_key}/cover**

- Surface: GET /api/parts/{part_key}/cover
- Inputs: N/A (endpoint removed)
- Outputs: N/A
- Errors: 404 after removal
- Evidence: `/work/backend/app/api/documents.py:76-89`

**Removed: PUT /api/parts/{part_key}/cover**

- Surface: PUT /api/parts/{part_key}/cover
- Inputs: N/A (endpoint removed)
- Outputs: N/A
- Errors: 404 after removal
- Evidence: `/work/backend/app/api/documents.py:41-57`

**Removed: DELETE /api/parts/{part_key}/cover**

- Surface: DELETE /api/parts/{part_key}/cover
- Inputs: N/A (endpoint removed)
- Outputs: N/A
- Errors: 404 after removal
- Evidence: `/work/backend/app/api/documents.py:60-73`

---

## 5) Algorithms & State Machines

**AttachmentSetService constructor**

- Flow: AttachmentSetService.__init__(db, s3_service, image_service, settings)
- Steps: Constructor receives injected dependencies for database session, S3 operations, image processing, and configuration settings
- Dependencies:
  - `db: Session` - Database session for ORM operations
  - `s3_service: S3Service` - S3 file upload/exists/delete operations
  - `image_service: ImageService` - Image processing (resizing, thumbnails)
  - `settings: Settings` - Configuration (file size limits, allowed types)
- Evidence: Pattern from `/work/backend/app/services/document_service.py:31-50`

**Flow: Create attachment set**

- Flow: AttachmentSetService.create_attachment_set()
- Steps:
  1. Create new AttachmentSet instance with no cover
  2. Add to session and flush to get ID
  3. Return AttachmentSet instance
- States / transitions: None (stateless creation)
- Hotspots: Called during every Part and Kit creation—must be fast. Expected volume: hundreds per test run, low in production.
- Evidence: Change brief lines 103-105; pattern from `/work/backend/app/services/part_service.py`

**Flow: Create file attachment**

- Flow: AttachmentSetService.create_file_attachment(set_id, title, file_data, filename)
- Steps:
  1. Validate attachment set exists
  2. Read file data, detect MIME type via python-magic
  3. Validate file type against allowed types
  4. Validate file size against limits (image vs. PDF)
  5. Generate CAS key from content hash
  6. Create Attachment instance with attachment_set_id FK
  7. Add to session and flush to get attachment ID
  8. If set has no cover and attachment is image, set as cover
  9. Flush again to persist cover reference
  10. Check if content exists in S3 (CAS deduplication)
  11. If not, upload file data to S3 with content type
  12. Return Attachment instance
- States / transitions: None (linear flow)
- Hotspots: S3 upload is external I/O bottleneck. CAS deduplication reduces uploads. Expected volume: tens of attachments per part/kit.
- Evidence: `/work/backend/app/services/document_service.py:172-324`; change brief lines 102-110

**Flow: Delete attachment**

- Flow: AttachmentSetService.delete_attachment(set_id, attachment_id)
- Steps:
  1. Validate attachment exists and belongs to set
  2. Get parent attachment set
  3. If attachment is current cover, find next image attachment
  4. If found, set new cover_attachment_id; else set to NULL
  5. Delete attachment from session
  6. Flush to persist changes
  7. Do NOT delete S3 object (CAS objects may be shared)
- States / transitions: Cover state transitions (current cover → next image or NULL)
- Hotspots: Cover reassignment query must scan attachments in set. Expected volume: small (< 100 attachments per set).
- Evidence: `/work/backend/app/services/document_service.py:384-414`; change brief confirms S3 cleanup is best-effort

**Flow: Set cover attachment**

- Flow: AttachmentSetService.set_cover_attachment(set_id, attachment_id)
- Steps:
  1. Validate attachment set exists
  2. If attachment_id is not NULL, validate attachment exists and belongs to set
  3. Set attachment_set.cover_attachment_id = attachment_id
  4. Flush to persist
- States / transitions: Cover state (NULL → attachment_id or attachment_id → different_id or attachment_id → NULL)
- Hotspots: None—simple FK update
- Evidence: `/work/backend/app/services/document_service.py:469-495`

**Flow: Part creation with attachment set**

- Flow: PartService.create_part() modification
- Steps:
  1. Validate inputs (description, type, etc.)
  2. Create AttachmentSet via attachment_set_service.create_attachment_set()
  3. Create Part instance with attachment_set_id = attachment_set.id
  4. Add part to session and flush
  5. Return part instance
- States / transitions: None
- Hotspots: Two flushes per part creation. Expected volume: hundreds during test data load.
- Evidence: Change brief lines 103-105; `/work/backend/app/services/part_service.py` exists

**Flow: Kit creation with attachment set**

- Flow: KitService.create_kit() modification
- Steps:
  1. Validate inputs (name, description, build_target)
  2. Create AttachmentSet via attachment_set_service.create_attachment_set()
  3. Create Kit instance with attachment_set_id = attachment_set.id
  4. Add kit to session and flush
  5. Return kit instance
- States / transitions: None
- Hotspots: Two flushes per kit creation. Expected volume: tens during test data load.
- Evidence: Change brief lines 103-105; `/work/backend/app/services/kit_service.py` exists

---

## 6) Derived State & Invariants

**Derived value: Part.cover_url**

- Derived value: Part.cover_url (computed property)
- Source: Unfiltered. Joins Part → AttachmentSet → Attachment via cover_attachment_id FK.
- Writes / cleanup: None. Read-only property for API serialization.
- Guards: Property checks if cover_attachment exists and has_preview before building CAS URL. Returns None if either check fails.
- Invariant: cover_url is None OR a valid CAS URL pointing to an image attachment in the part's attachment set
- Evidence: `/work/backend/app/models/part.py:119-133`; change brief requires moving cover to AttachmentSet

**Derived value: Kit.cover_url**

- Derived value: Kit.cover_url (new computed property)
- Source: Unfiltered. Joins Kit → AttachmentSet → Attachment via cover_attachment_id FK.
- Writes / cleanup: None. Read-only property for API serialization.
- Guards: Property checks if cover_attachment exists and has_preview before building CAS URL. Returns None if either check fails.
- Invariant: cover_url is None OR a valid CAS URL pointing to an image attachment in the kit's attachment set
- Evidence: Pattern from `/work/backend/app/models/part.py:119-133`; kits get equivalent behavior

**Derived value: Attachment.attachment_url**

- Derived value: Attachment.attachment_url (computed property)
- Source: Unfiltered. Reads s3_key, content_type, filename from Attachment instance.
- Writes / cleanup: None. Read-only property builds CAS URL from metadata.
- Guards: Returns None if s3_key is None (e.g., for URL attachments). CAS URL building is safe.
- Invariant: attachment_url is None OR a valid CAS URL with content_type and filename query params
- Evidence: `/work/backend/app/models/part_attachment.py:68-74`; behavior unchanged in new Attachment model

**Derived value: AttachmentSet next cover on delete**

- Derived value: Next cover attachment ID when current cover is deleted
- Source: Filtered query. Finds first image attachment in set ordered by created_at, excluding deleted attachment.
- Writes / cleanup: Sets attachment_set.cover_attachment_id to new value or NULL. Persisted to database via flush.
- Guards: Query wrapped in delete_attachment transaction. Filter ensures only IMAGE attachments considered. Ordering by created_at is deterministic.
- Invariant: After deleting cover attachment, cover_attachment_id points to oldest remaining image OR is NULL if no images remain
- Evidence: `/work/backend/app/services/document_service.py:397-405`; pattern moves to AttachmentSetService

**Derived value: Auto-cover on first upload**

- Derived value: Cover attachment assignment on first image upload
- Source: Unfiltered check. Reads attachment_set.cover_attachment_id to see if NULL.
- Writes / cleanup: Sets cover_attachment_id to newly created attachment if set has no cover. Persisted via flush.
- Guards: Check happens within create_file_attachment transaction. Only sets if cover is NULL and new attachment is IMAGE type.
- Invariant: If attachment set has no cover and an image is uploaded, that image becomes the cover
- Evidence: `/work/backend/app/services/document_service.py:295-297`; pattern moves to AttachmentSetService with set-level check

---

## 7) Consistency, Transactions & Concurrency

**Transaction scope**

- Transaction scope: Each API endpoint runs in its own transaction via Flask request context. Service methods expect an active session and flush changes within the transaction. Commit happens at end of successful request; rollback on exception.
- Atomic requirements:
  - Part/Kit creation + AttachmentSet creation must succeed together or roll back
  - Attachment creation + S3 upload: Attachment row persisted BEFORE S3 upload (flush first) so rollback cleans up orphaned rows if upload fails
  - Attachment deletion + cover reassignment must succeed together
  - Cover update must be atomic (old cover → new cover)
- Retry / idempotency: Attachment creation is idempotent via CAS keys—duplicate uploads reuse same S3 object. No explicit idempotency keys needed.
- Ordering / concurrency controls: No optimistic locking on AttachmentSet or Attachment. Cover reassignment uses FK constraints to prevent dangling references. Concurrent cover updates last-write-wins (acceptable for single-user app).
- Evidence: CLAUDE.md lines 154-168 define transaction patterns; `/work/backend/app/services/document_service.py:292-323` shows flush-before-upload pattern

---

## 8) Errors & Edge Cases

**Failure: Attachment set not found**

- Failure: GET/POST/PUT/DELETE on non-existent attachment set ID
- Surface: All `/api/attachment-sets/{id}/...` endpoints
- Handling: Raise RecordNotFoundException from service, @handle_api_errors converts to 404 JSON response
- Guardrails: Service validates set exists before any mutation. Path parameter type validation (integer) at API layer.
- Evidence: `/work/backend/app/services/document_service.py:245-248` pattern; `/work/backend/app/utils/error_handling.py`

**Failure: Attachment doesn't belong to set**

- Failure: Attempt to update/delete attachment using wrong set ID in path
- Surface: PUT /api/attachment-sets/{id}/attachments/{attachment_id}, DELETE /api/attachment-sets/{id}/attachments/{attachment_id}, PUT /api/attachment-sets/{id}/cover
- Handling: Service checks attachment.attachment_set_id == set_id, raises InvalidOperationException if mismatch, converted to 400
- Guardrails: Explicit ownership validation in service layer before any mutation
- Evidence: Pattern from `/work/backend/app/services/document_service.py:488-489`; change brief line 29 confirms attachment knows parent set

**Failure: File type not allowed**

- Failure: Upload file with disallowed MIME type (e.g., .exe, .zip)
- Surface: POST /api/attachment-sets/{id}/attachments with file
- Handling: Service validates detected MIME type against ALLOWED_IMAGE_TYPES + ALLOWED_FILE_TYPES, raises InvalidOperationException with message, converted to 400
- Guardrails: Python-magic detects actual type from bytes (not just extension/header). Config defines allowed types.
- Evidence: `/work/backend/app/services/document_service.py:123-151`

**Failure: File size exceeds limit**

- Failure: Upload image > MAX_IMAGE_SIZE or PDF > MAX_FILE_SIZE
- Surface: POST /api/attachment-sets/{id}/attachments with file
- Handling: Service validates file size, raises InvalidOperationException with human-readable message (MB), converted to 400
- Guardrails: Config defines limits. Validation happens before S3 upload.
- Evidence: `/work/backend/app/services/document_service.py:153-171`

**Failure: S3 upload fails**

- Failure: S3 service raises exception during file upload
- Surface: POST /api/attachment-sets/{id}/attachments with file
- Handling: Attachment row already flushed, so transaction rolls back on exception. Service logs error with attachment ID and key. InvalidOperationException propagates to API, converted to 500.
- Guardrails: Flush before upload ensures rollback cleans orphaned rows. CAS key in DB allows retry—same content generates same key.
- Evidence: `/work/backend/app/services/document_service.py:299-323`; CLAUDE.md lines 93-99 define S3 consistency rules

**Failure: Create attachment for part/kit that doesn't exist**

- Failure: POST to attachment set that was deleted (cascade from part/kit delete)
- Surface: POST /api/attachment-sets/{id}/attachments
- Handling: FK constraint violation on attachment_set_id raises IntegrityError, converted to 404 by error handler
- Guardrails: FK constraint on attachment_sets table. Service validates set exists before creating attachment.
- Evidence: Database FK constraint; `/work/backend/app/utils/flask_error_handlers.py` handles IntegrityError

**Failure: Set cover to non-existent attachment**

- Failure: PUT /api/attachment-sets/{id}/cover with invalid attachment_id
- Surface: PUT /api/attachment-sets/{id}/cover
- Handling: Service validates attachment exists, raises RecordNotFoundException, converted to 404
- Guardrails: Service checks attachment.id and attachment.attachment_set_id before setting FK
- Evidence: Pattern from `/work/backend/app/services/document_service.py:485-489`

**Failure: Migration fails mid-backfill**

- Failure: Migration 020 fails while creating attachment sets for existing parts
- Surface: Alembic migration during upgrade-db
- Handling: Migration wrapped in transaction—partial backfill rolls back. Operator retries upgrade-db.
- Guardrails: Migration uses batch operations, adds constraints AFTER backfill completes. Test on copy of production data first.
- Evidence: Alembic transaction behavior; CLAUDE.md lines 154-168

**Failure: Test data load with missing attachment_set_id**

- Failure: parts.json or kits.json missing attachment_set_id values after schema change
- Surface: CLI load-test-data command
- Handling: FK constraint violation raises IntegrityError, load fails with clear error. Developer updates JSON files.
- Guardrails: NOT NULL constraint enforces invariant. Test data validation during load.
- Evidence: CLAUDE.md lines 405-426 require test data updates; FK constraints enforce correctness

---

## 9) Observability / Telemetry

**Signal: attachment_created_total**

- Signal: attachment_created_total
- Type: Counter
- Trigger: Incremented after successful attachment creation (file or URL) in AttachmentSetService
- Labels / fields: attachment_type (url, image, pdf), entity_type (part, kit)
- Consumer: Metrics dashboard showing attachment creation rates by type and entity
- Evidence: Pattern from `/work/backend/app/services/metrics_service.py`; CLAUDE.md lines 236-256

**Signal: attachment_deleted_total**

- Signal: attachment_deleted_total
- Type: Counter
- Trigger: Incremented after successful attachment deletion in AttachmentSetService
- Labels / fields: attachment_type (url, image, pdf), was_cover (true, false)
- Consumer: Metrics dashboard tracking deletion patterns
- Evidence: Metrics service pattern; useful for monitoring S3 bloat

**Signal: attachment_upload_duration_seconds**

- Signal: attachment_upload_duration_seconds
- Type: Histogram
- Trigger: Measured around S3 upload operation in create_file_attachment
- Labels / fields: attachment_type (image, pdf), size_bucket (small, medium, large)
- Consumer: Performance monitoring for S3 upload latency
- Evidence: Pattern from `/work/backend/app/services/document_service.py:306`; CLAUDE.md lines 154-162 require time.perf_counter() for durations

**Signal: attachment_set_cover_changed**

- Signal: attachment_set_cover_changed
- Type: Counter
- Trigger: Incremented when cover_attachment_id changes (set, cleared, auto-assigned)
- Labels / fields: action (set, cleared, auto_assigned, reassigned_on_delete)
- Consumer: Metrics tracking cover management patterns
- Evidence: Useful for validating auto-cover logic and user behavior

**Log: Attachment creation**

- Signal: Structured log on attachment creation
- Type: Structured log (INFO level)
- Trigger: After successful attachment creation, before S3 upload
- Labels / fields: attachment_id, attachment_set_id, attachment_type, file_size, s3_key
- Consumer: Debugging attachment issues, audit trail
- Evidence: Pattern from `/work/backend/app/services/document_service.py:88`; logging imported in service

**Log: S3 upload skipped (CAS deduplication)**

- Signal: Structured log when content already exists in S3
- Type: Structured log (INFO level)
- Trigger: After CAS key generation, if S3Service.file_exists returns True
- Labels / fields: attachment_id, s3_key, message="Content already exists in CAS"
- Consumer: Verifying CAS deduplication is working
- Evidence: `/work/backend/app/services/document_service.py:301-302`

**Log: Cover reassignment on delete**

- Signal: Structured log when cover is reassigned during attachment deletion
- Type: Structured log (INFO level)
- Trigger: After finding new cover attachment during delete flow
- Labels / fields: attachment_set_id, old_cover_id, new_cover_id (or NULL), action="cover_reassigned"
- Consumer: Debugging cover state transitions
- Evidence: Useful for validating complex delete logic

---

## 10) Background Work & Shutdown

**None**

- Worker / job: None
- Trigger cadence: N/A
- Responsibilities: N/A
- Shutdown handling: N/A
- Evidence: Attachment operations are synchronous HTTP request-response. No background threads, no shutdown coordination needed.

---

## 11) Security & Permissions

**Not applicable**

Single-user application with no authentication or authorization. All API endpoints are publicly accessible. Rate limiting and input validation are the only security controls.

Evidence: CLAUDE.md lines 9-10; product brief lines 7-9

---

## 12) UX / UI Impact

**Frontend impact documentation required**

- Entry point: Part detail page, Kit detail page, shared AttachmentManager component
- Change: Frontend must switch from `/api/parts/{key}/attachments/...` to `/api/attachment-sets/{id}/...` endpoints. Part and Kit response objects now include `attachment_set_id` field for API routing.
- User interaction: No change—users still upload files, add URLs, set cover images, delete attachments. Unified UI component works for both parts and kits.
- Dependencies: Part and Kit API responses include `attachment_set_id`. Frontend reads this value to construct attachment API URLs.
- Evidence: Change brief lines 119-123; frontend dev implements `<AttachmentManager setId={id} />` component that works for any entity type

**Frontend migration path**

Create `docs/features/kit_attachments/frontend_impact.md` with:
- Breaking change: Old `/api/parts/{key}/attachments` endpoints removed
- New endpoints: `/api/attachment-sets/{id}/attachments` with same request/response shapes
- Schema changes: Part and Kit responses include `attachment_set_id` field
- Migration steps: Update API client, update component props, test part and kit attachment flows

Evidence: CLAUDE.md lines 15-19 require frontend impact documentation when breaking changes occur

---

## 13) Deterministic Test Plan

**Surface: AttachmentSetService.create_attachment_set()**

- Scenarios:
  - Given service instance, When create_attachment_set called, Then returns AttachmentSet with ID and no cover
  - Given service instance, When create multiple sets, Then each has unique ID
- Fixtures / hooks: Flask app context, database session, ServiceContainer with attachment_set_service
- Gaps: None
- Evidence: Pattern from `/work/backend/tests/test_document_service.py`; CLAUDE.md lines 289-318

**Surface: AttachmentSetService.create_file_attachment()**

- Scenarios:
  - Given attachment set exists, When create image attachment with valid file, Then attachment created with IMAGE type and S3 key
  - Given attachment set exists, When create PDF attachment with valid file, Then attachment created with PDF type and S3 key
  - Given attachment set with no cover, When create image attachment, Then attachment auto-set as cover
  - Given attachment set with existing cover, When create image attachment, Then cover unchanged
  - Given attachment set ID, When create attachment with invalid file type, Then raises InvalidOperationException
  - Given attachment set ID, When create attachment with file exceeding size limit, Then raises InvalidOperationException
  - Given non-existent set ID, When create attachment, Then raises RecordNotFoundException
  - Given duplicate file content (same hash), When create attachment, Then S3 upload skipped (CAS deduplication)
- Fixtures / hooks: Flask app, session, container, mock S3Service (file_exists, upload_file, generate_cas_key), mock python-magic, sample image and PDF files
- Gaps: None
- Evidence: `/work/backend/tests/test_document_service.py` pattern; CLAUDE.md lines 289-318

**Surface: AttachmentSetService.create_url_attachment()**

- Scenarios:
  - Given attachment set exists, When create URL attachment with valid URL, Then attachment created with URL type and no S3 key
  - Given attachment set exists, When create URL attachment for image URL, Then attachment created with IMAGE type and S3 key (content downloaded)
  - Given non-existent set ID, When create URL attachment, Then raises RecordNotFoundException
- Fixtures / hooks: Flask app, session, container, mock download_cache_service, mock URL interceptor registry
- Gaps: URL processing complexity tested in existing document service tests—focus on set ownership here
- Evidence: `/work/backend/app/services/document_service.py:203-237`

**Surface: AttachmentSetService.delete_attachment()**

- Scenarios:
  - Given attachment in set, When delete attachment, Then attachment removed from database
  - Given attachment is cover, When delete attachment, Then cover reassigned to next oldest image or NULL
  - Given attachment in set A, When delete using set B ID, Then raises InvalidOperationException (ownership check)
  - Given non-existent attachment ID, When delete, Then raises RecordNotFoundException
- Fixtures / hooks: Flask app, session, container, pre-created attachment sets with multiple attachments
- Gaps: None
- Evidence: `/work/backend/app/services/document_service.py:384-414`

**Surface: AttachmentSetService.set_cover_attachment()**

- Scenarios:
  - Given attachment set and attachment in set, When set cover to attachment ID, Then cover_attachment_id updated
  - Given attachment set with cover, When set cover to NULL, Then cover cleared
  - Given attachment in different set, When set as cover, Then raises InvalidOperationException
  - Given non-existent attachment ID, When set as cover, Then raises RecordNotFoundException
- Fixtures / hooks: Flask app, session, container, pre-created attachment sets with attachments
- Gaps: None
- Evidence: `/work/backend/app/services/document_service.py:469-495`

**Surface: PartService.create_part() with attachment set**

- Scenarios:
  - Given valid part data, When create part, Then part created with attachment_set_id populated and AttachmentSet exists (`tests/test_part_service.py::test_create_part_with_attachment_set`)
  - Given part creation fails after attachment set created, When transaction rolls back, Then both part and attachment set rolled back (`tests/test_part_service.py::test_part_creation_rollback_attachment_set`)
- Fixtures / hooks: Flask app, session, container with part_service and attachment_set_service wired
- Gaps: None
- Evidence: Change brief lines 103-105; CLAUDE.md service testing requirements

**Surface: KitService.create_kit() with attachment set**

- Scenarios:
  - Given valid kit data, When create kit, Then kit created with attachment_set_id populated and AttachmentSet exists (`tests/test_kit_service.py::test_create_kit_with_attachment_set`)
  - Given kit creation fails after attachment set created, When transaction rolls back, Then both kit and attachment set rolled back (`tests/test_kit_service.py::test_kit_creation_rollback_attachment_set`)
- Fixtures / hooks: Flask app, session, container with kit_service and attachment_set_service wired
- Gaps: None
- Evidence: Change brief lines 103-105; CLAUDE.md service testing requirements

**Surface: POST /api/attachment-sets/{id}/attachments (file upload)**

- Scenarios:
  - Given attachment set ID, When POST valid image file, Then 201 response with attachment details
  - Given attachment set ID, When POST valid PDF file, Then 201 response with attachment details
  - Given attachment set ID, When POST invalid file type, Then 400 response with error
  - Given non-existent set ID, When POST file, Then 404 response
  - Given attachment set ID, When POST file exceeding size limit, Then 400 response
- Fixtures / hooks: Flask test client, database session, container, sample image/PDF files
- Gaps: None
- Evidence: `/work/backend/tests/test_document_api.py:23-50` pattern

**Surface: POST /api/attachment-sets/{id}/attachments (URL)**

- Scenarios:
  - Given attachment set ID, When POST valid URL JSON, Then 201 response with attachment details
  - Given attachment set ID, When POST invalid JSON (missing title), Then 400 response
  - Given non-existent set ID, When POST URL, Then 404 response
- Fixtures / hooks: Flask test client, database session, container, mock URL processing
- Gaps: None
- Evidence: API testing pattern; CLAUDE.md lines 320-331

**Surface: GET /api/attachment-sets/{id}/attachments**

- Scenarios:
  - Given attachment set with multiple attachments, When GET list, Then 200 response with all attachments
  - Given attachment set with no attachments, When GET list, Then 200 response with empty array
  - Given non-existent set ID, When GET list, Then 404 response
- Fixtures / hooks: Flask test client, database session, pre-created attachment sets
- Gaps: None
- Evidence: API testing pattern

**Surface: DELETE /api/attachment-sets/{id}/attachments/{attachment_id}**

- Scenarios:
  - Given attachment in set, When DELETE attachment, Then 204 response and attachment removed
  - Given attachment is cover, When DELETE attachment, Then 204 response and cover reassigned
  - Given attachment in different set, When DELETE using wrong set ID, Then 400 response
  - Given non-existent attachment ID, When DELETE, Then 404 response
- Fixtures / hooks: Flask test client, database session, pre-created attachments
- Gaps: None
- Evidence: API testing pattern

**Surface: PUT /api/attachment-sets/{id}/cover**

- Scenarios:
  - Given attachment set and attachment, When PUT cover with attachment_id, Then 200 response and cover set
  - Given attachment set with cover, When PUT cover with null, Then 200 response and cover cleared
  - Given attachment in different set, When PUT cover, Then 400 response (ownership check)
- Fixtures / hooks: Flask test client, database session, pre-created attachments
- Gaps: None
- Evidence: API testing pattern

**Surface: Part and Kit API responses include attachment_set_id**

- Scenarios:
  - Given part with attachment set, When GET part, Then response includes attachment_set_id field
  - Given kit with attachment set, When GET kit, Then response includes attachment_set_id field
  - Given part with cover attachment, When GET part, Then response includes cover_url field
- Fixtures / hooks: Flask test client, database session, pre-created parts/kits with attachment sets
- Gaps: None
- Evidence: Schema validation in API tests

**Surface: Alembic migration 020**

- Scenarios:
  - Given database with existing parts and attachments, When run migration, Then attachment_sets table created
  - Given database with existing parts and attachments, When run migration, Then attachments table renamed and FK updated
  - Given database with existing parts, When run migration, Then each part has attachment_set_id populated
  - Given database with existing parts, When run migration, Then cover references moved to attachment sets
  - Given empty database, When run migration, Then schema created correctly
  - Given migration completed, When run downgrade, Then schema reverted
- Fixtures / hooks: Flask app, test database, Alembic migrations, pre-seeded parts with attachments
- Gaps: None—critical to test migration thoroughly
- Evidence: CLAUDE.md migration testing pattern; change brief lines 112-116

---

## 14) Implementation Slices

**Slice 1: Models and migration**

- Slice: Create AttachmentSet and Attachment models, write migration
- Goal: Database schema in place, migration tested on copy of production data
- Touches: app/models/attachment_set.py, app/models/attachment.py, alembic/versions/020_create_attachment_sets.py, app/models/part.py, app/models/kit.py
- Dependencies: None—starts the feature. Test migration before proceeding.

**Slice 2: Service layer**

- Slice: Create AttachmentSetService with full CRUD operations
- Goal: Business logic isolated, thoroughly tested at service layer
- Touches: app/services/attachment_set_service.py, app/services/container.py, tests/test_attachment_set_service.py
- Dependencies: Slice 1 complete. Wire service into container.

**Slice 3: Part and Kit service integration**

- Slice: Update PartService and KitService to create attachment sets during entity creation
- Goal: Invariant enforced—all parts and kits have attachment sets
- Touches: app/services/part_service.py, app/services/kit_service.py, tests for part and kit creation
- Dependencies: Slice 2 complete. Inject attachment_set_service into part/kit services.

**Slice 4: API layer**

- Slice: Create attachment_sets_bp blueprint, remove old endpoints from documents_bp
- Goal: New API surface fully functional, old endpoints gone
- Touches: app/api/attachment_sets.py, app/api/documents.py, app/api/__init__.py, app/__init__.py, tests/test_attachment_set_api.py
- Dependencies: Slice 3 complete. Wire blueprint into app.

**Slice 5: Schemas and response updates**

- Slice: Update Part and Kit schemas to include attachment_set_id, add cover_url property to Kit model
- Goal: API responses include attachment_set_id for frontend routing
- Touches: app/schemas/part.py, app/schemas/kit.py, app/models/kit.py, tests for part and kit API responses
- Dependencies: Slice 4 complete. Add computed property to Kit model.

**Slice 6: Test data updates and cleanup**

- Slice: Create new test data JSON files, update existing files, remove old tests, delete obsolete files
- Goal: Test data loader works with new schema, old code removed, repo clean
- Touches: app/data/test_data/attachment_sets.json (create), app/data/test_data/attachments.json (create), app/data/test_data/parts.json (add attachment_set_id), app/data/test_data/kits.json (add attachment_set_id), tests/test_document_api.py (delete old tests), app/models/part_attachment.py (delete), app/schemas/part_attachment.py (delete)
- Dependencies: Slices 1-5 complete. Create attachment_sets.json and attachments.json with realistic electronics documentation examples (datasheets, product images). Validate test data loads successfully with FK constraints.

---

## 15) Risks & Open Questions

**Risk: Migration fails on production data**

- Risk: Backfill logic doesn't handle edge cases in production (e.g., parts with cover_attachment_id pointing to deleted attachment)
- Impact: Migration fails, database left in inconsistent state, requires manual intervention
- Mitigation: Test migration on anonymized copy of production data. Add defensive checks for orphaned cover references. Use batch processing with progress logging.

**Risk: Circular FK dependency between attachment_sets and attachments**

- Risk: AttachmentSet has cover_attachment_id FK to attachments, Attachment has attachment_set_id FK to attachment_sets—potential deadlock during creation/deletion
- Impact: Cannot create first attachment for new set if cover FK validation runs before attachment exists
- Mitigation: Use `use_alter=True` on cover_attachment_id FK in AttachmentSet model (pattern from Part.cover_attachment_id). SQLAlchemy defers FK check until after both rows exist.

**Risk: S3 bloat from abandoned CAS objects**

- Risk: CAS objects never deleted when attachments removed—S3 bucket grows unbounded
- Impact: Storage costs increase, no automated cleanup
- Mitigation: Accept for MVP (change brief excludes cleanup). Document S3 lifecycle policy for manual cleanup. Future: implement background job to scan CAS keys and delete unreferenced objects.

**Risk: Test data updates missed during migration**

- Risk: Developer forgets to update test data JSON files, load-test-data fails
- Impact: Development and CI environments broken until test data fixed
- Mitigation: Update test data JSON files in same commit as migration. Add validation in CLI load-test-data to check FK constraints before commit.

**Risk: Frontend breaks due to missing attachment_set_id**

- Risk: Part or Kit created without attachment set (programming error bypassing invariant)
- Impact: Frontend cannot construct attachment API URLs, attachments inaccessible
- Mitigation: NOT NULL constraint on attachment_set_id enforces invariant. Database rejects rows without valid FK. Service layer unit tests verify AttachmentSet created during Part/Kit creation.

---

## 16) Confidence

Confidence: High — The design is well-scoped with clear evidence from existing code patterns, the change brief provides explicit architecture decisions, and the removal of backwards compatibility eliminates migration complexity. The AttachmentSet aggregate cleanly decouples attachments from entity types with real FKs, avoiding polymorphic association pitfalls. Migration risk is manageable via copy-of-production testing, and the existing DocumentService provides a proven template for S3/CAS operations.
