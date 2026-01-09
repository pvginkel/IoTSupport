# Kit Attachments - Change Brief

## Summary

Add attachment support for kits by introducing an `AttachmentSet` aggregate that decouples attachment management from specific entity types. Both parts and kits will reference an attachment set, and all attachment operations will be performed against the attachment set directly.

## Architecture

```
┌───────┐     ┌─────────────────┐     ┌─────────────┐
│ Part  │────▶│ AttachmentSet   │◀────│ Attachment  │
└───────┘     │                 │     └─────────────┘
              │ - cover_id FK ──┼──────────┘
┌───────┐     │                 │
│ Kit   │────▶│                 │
└───────┘     └─────────────────┘
```

**Key design decisions:**

1. **AttachmentSet as aggregate** - A new entity that owns attachments and cover image state. Parts and kits hold a foreign key to their attachment set.

2. **Real foreign keys everywhere** - `Attachment.attachment_set_id` → `attachment_sets.id` with cascade delete. No soft/polymorphic references.

3. **Eager creation** - Every Part and Kit gets an AttachmentSet created at entity creation time. Invariant: `attachment_set_id` is always populated.

4. **Separate API surface** - New blueprint at `/api/attachment-sets/{id}/...` handles all attachment operations. Entity APIs (parts, kits) just expose `attachment_set_id` in responses.

5. **Entity-agnostic attachments** - The `Attachment` model has no knowledge of parts or kits. It only knows about its parent attachment set.

## Schema Changes

### New table: `attachment_sets`
```sql
attachment_sets (
  id INTEGER PRIMARY KEY,
  cover_attachment_id INTEGER FK → attachments.id (nullable),
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```

### Modified table: `attachments` (renamed from `part_attachments`)
```sql
attachments (
  id INTEGER PRIMARY KEY,
  attachment_set_id INTEGER FK → attachment_sets.id NOT NULL ON DELETE CASCADE,
  attachment_type ENUM('url', 'image', 'pdf'),
  title VARCHAR(255),
  s3_key VARCHAR(500),
  url VARCHAR(2000),
  filename VARCHAR(255),
  content_type VARCHAR(100),
  file_size INTEGER,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```

Note: `part_id` column removed, replaced with `attachment_set_id`.

### Modified table: `parts`
- Add `attachment_set_id INTEGER FK → attachment_sets.id NOT NULL`
- Remove `cover_attachment_id` (moved to attachment_set)

### Modified table: `kits`
- Add `attachment_set_id INTEGER FK → attachment_sets.id NOT NULL`

## API Design

### New endpoints: `/api/attachment-sets/{id}/...`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/attachment-sets/{id}` | Get attachment set with attachments list and cover |
| POST | `/attachment-sets/{id}/attachments` | Create attachment (file upload or URL) |
| GET | `/attachment-sets/{id}/attachments` | List attachments |
| GET | `/attachment-sets/{id}/attachments/{attachment_id}` | Get single attachment |
| PUT | `/attachment-sets/{id}/attachments/{attachment_id}` | Update attachment metadata |
| DELETE | `/attachment-sets/{id}/attachments/{attachment_id}` | Delete attachment |
| GET | `/attachment-sets/{id}/cover` | Get cover attachment |
| PUT | `/attachment-sets/{id}/cover` | Set cover attachment |
| DELETE | `/attachment-sets/{id}/cover` | Clear cover attachment |

### Modified responses: Parts and Kits

Part and Kit API responses will include `attachment_set_id` so the UI can interact directly with the attachment set endpoints:

```json
{
  "id": 1,
  "key": "ABCD",
  "description": "10K Resistor",
  "attachment_set_id": 42,
  "cover_url": "/api/cas/abc123..."
}
```

The `cover_url` convenience property remains on Part/Kit for display purposes, derived from the attachment set's cover.

## Lifecycle Management

### Creation
- When creating a Part or Kit, the service layer creates an AttachmentSet first, then assigns its ID to the entity.
- Single transaction ensures atomicity.

### Deletion
- Part/Kit deletion must cascade to delete the AttachmentSet.
- AttachmentSet deletion cascades to delete all Attachments.
- Use SQLAlchemy `cascade="all, delete-orphan"` with `single_parent=True`.

### Migration
- Existing parts need AttachmentSets created and backfilled.
- Existing `part_attachments` rows need `attachment_set_id` populated based on their `part_id`.
- Cover attachment references need to move from Part to AttachmentSet.

## Benefits

1. **Reusable UI component** - Frontend can implement a single `<AttachmentManager setId={id} />` component that works for any entity type.

2. **Real referential integrity** - All foreign keys are real constraints with proper cascade behavior.

3. **Easy to extend** - Adding attachments to a new entity type (e.g., Project, Supplier) just requires adding an `attachment_set_id` column.

4. **Separation of concerns** - Attachment logic is fully isolated in its own service and blueprint.

5. **No polymorphism** - No `entity_type`/`entity_id` soft references, no type checking at runtime.

## Exclusions

- No attachment copying between sets
- No sharing of attachment sets between entities (enforced by application logic)
- No changes to S3/CAS storage layer
