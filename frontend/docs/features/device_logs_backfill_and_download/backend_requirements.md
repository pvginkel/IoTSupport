# Backend Requirements: Device Logs Test Seeding Endpoint

## Context

The device log viewer now supports infinite-scroll backfill (loading older log entries) and a download dialog (fetching up to 10,000 lines). Playwright specs for these features require deterministic setup of historical log data in Elasticsearch.

The existing `POST /api/testing/devices/logs/inject` endpoint only forwards log entries to active SSE subscribers — it does not persist them to the Elasticsearch index. This means tests cannot set up historical log data that the `GET /api/devices/{device_id}/logs` endpoint would return.

## Required Endpoint

### `POST /api/testing/devices/logs/seed`

Write historical log entries directly into Elasticsearch for a given device. This endpoint is **test-only** and should follow the same access patterns as the existing `/api/testing/` endpoints (available only when the test API is enabled).

### Request

```json
{
  "device_entity_id": "string",
  "count": 1500,
  "start_time": "2026-03-04T00:00:00Z",
  "end_time": "2026-03-04T01:00:00Z"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `device_entity_id` | string | Yes | — | The device entity ID to associate log entries with |
| `count` | integer | Yes | — | Number of log entries to create (max 15,000) |
| `start_time` | ISO 8601 datetime | No | 1 hour before `end_time` | Timestamp of the earliest seeded entry |
| `end_time` | ISO 8601 datetime | No | now | Timestamp of the latest seeded entry |

### Behavior

- Generate `count` log entries with timestamps evenly distributed between `start_time` and `end_time`.
- Each entry should have a recognizable message format, e.g. `"Seeded log entry {n}"` or similar, so tests can verify content.
- Entries must be written directly to the same Elasticsearch index that `GET /api/devices/{device_id}/logs` reads from.
- The endpoint must ensure entries are searchable before returning (i.e. call `refresh` on the index or equivalent).
- If the device entity ID does not exist in Elasticsearch yet, the entries should still be written (Elasticsearch creates the document on write).

### Response

```json
{
  "seeded": 1500,
  "window_start": "2026-03-04T00:00:00Z",
  "window_end": "2026-03-04T01:00:00Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `seeded` | integer | Number of entries actually written |
| `window_start` | ISO 8601 datetime | Timestamp of the earliest seeded entry |
| `window_end` | ISO 8601 datetime | Timestamp of the latest seeded entry |

### Errors

| Status | Condition |
|--------|-----------|
| 400 | Missing `device_entity_id` or `count`; `count` < 1 or > 15,000 |
| 503 | Elasticsearch unavailable |

## Test Scenarios This Unblocks

1. **Backfill on scroll to top** — Seed >1,000 entries, navigate to logs tab, scroll to top, verify additional entries are loaded and total count increases.
2. **Backfill exhaustion** — Seed exactly 500 entries, scroll to top after initial load, verify no additional fetch occurs (has_more=false).
3. **Download with specific line count** — Seed 200 entries, request download of 100, verify file contains exactly 100 lines. Seed 50 entries, request 100, verify file contains 50 lines.
4. **Download large volume** — Seed 5,000+ entries, request download of 5,000, verify sequential pagination completes and file is generated.

## Relationship to Existing Endpoints

| Endpoint | Persists to ES | SSE Broadcast | Use Case |
|----------|---------------|---------------|----------|
| `POST /api/testing/devices/logs/inject` | No | Yes | Test SSE streaming behavior |
| `POST /api/testing/devices/logs/seed` (new) | Yes | No | Test historical log retrieval (backfill, download) |
