# Backend Request: Coredump Testing Endpoint

## Context

The frontend now has UI support for core dumps (table on device editor, detail page with Monaco viewer, "Last Core Dump" column on device list). Playwright tests need to seed coredump data for a device, but the real upload endpoint (`POST /api/iot/coredump`) requires device authentication headers and a valid ESP32 coredump binary — neither of which is practical from the test harness.

Following the pattern established by `POST /api/testing/auth/session` (which bypasses OIDC for test isolation), we need a testing endpoint that bypasses the real upload/parse flow and directly seeds a coredump database record.

## Endpoint Specification

### `POST /api/testing/coredumps`

Creates a coredump record for a device with controllable metadata. No real `.dmp` binary or sidecar parsing is involved — this only seeds the database row (and optionally writes a dummy file if the download endpoint requires one on disk).

**Request body:**

| Field              | Type             | Required | Default                | Notes                                                        |
|--------------------|------------------|----------|------------------------|--------------------------------------------------------------|
| `device_id`        | `integer`        | Yes      | —                      | Must reference an existing device.                           |
| `chip`             | `string`         | No       | `"esp32s3"`            | Chip type string.                                            |
| `firmware_version` | `string`         | No       | `"0.0.0-test"`         | Firmware version at time of crash.                           |
| `size`             | `integer`        | No       | Some reasonable value   | Reported file size in bytes. Does not need to match any real file. |
| `parse_status`     | `string`         | No       | `"PARSED"`             | One of `PENDING`, `PARSED`, `ERROR`. Lets tests cover all three status display states. |
| `parsed_output`    | `string \| null` | No       | Placeholder text when `PARSED`, `null` otherwise | The textual crash analysis shown in the Monaco viewer.       |

**Response:** `201 Created` with the full `CoredumpDetailSchema` body (same shape as `GET /api/devices/{device_id}/coredumps/{coredump_id}`).

**Example request:**

```json
{
  "device_id": 42,
  "chip": "esp32s3",
  "firmware_version": "1.2.3",
  "size": 262144,
  "parse_status": "PARSED",
  "parsed_output": "Core dump from task watchdog...\nBacktrace: 0x40081234\n..."
}
```

**Example response:**

```json
{
  "id": 7,
  "device_id": 42,
  "filename": "test_coredump_7.dmp",
  "chip": "esp32s3",
  "firmware_version": "1.2.3",
  "size": 262144,
  "parse_status": "PARSED",
  "parsed_output": "Core dump from task watchdog...\nBacktrace: 0x40081234\n...",
  "parsed_at": "2026-02-12T10:30:00Z",
  "uploaded_at": "2026-02-12T10:30:00Z",
  "created_at": "2026-02-12T10:30:00Z",
  "updated_at": "2026-02-12T10:30:00Z"
}
```

## What Does NOT Need to Work

- **No real `.dmp` file on disk is required.** The tests verify the download link's `href` attribute but do not actually download and inspect binary content. If the download endpoint would 404 without a file, writing a small dummy file is fine.
- **No sidecar parsing should be triggered.** This is purely a database seed.
- **No device authentication.** This endpoint runs under the test session (same cookie as `POST /api/testing/auth/session`).

## Cleanup

No dedicated cleanup endpoint is needed. The tests will use the existing `DELETE /api/devices/{device_id}/coredumps/{coredump_id}` to remove individual coredumps, and device deletion in test teardown should cascade to associated coredumps.

## How the Frontend Tests Will Use This

The `DevicesFactory` in `tests/api/factories/devices.ts` will get a new `createCoredump(options)` method that calls this endpoint. A typical test flow:

```typescript
const device = await devices.create({ ... })
const coredump = await devices.createCoredump({
  deviceId: device.id,
  parseStatus: 'PARSED',
  parsedOutput: 'Backtrace: 0x40081234...'
})

// Navigate to device editor, assert coredump table shows the row
// Click row, assert detail page shows parsed output in Monaco editor
// Delete coredump, assert table updates
```
