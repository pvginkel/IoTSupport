# Change Brief: Core Dump Support in Frontend

## Summary

Surface the new backend core dump support in the frontend. The API already has endpoints for listing, viewing, downloading, and deleting core dumps per device, as well as a `last_coredump_at` field on the device list endpoint.

## Changes Required

### 1. Device Detail Page — Core Dumps Table

Add a core dumps table below the device log monitor on the device editor page. This table should:

- Always be visible (show an empty state when no core dumps exist).
- Display columns: **Uploaded At | Firmware | Size | Status | Actions**.
- Actions column contains a **Download** button (plain `<a href="...">` link to the download endpoint, letting the browser handle the binary download) and a **Delete** button per row.
- Rows are clickable and navigate to a **new dedicated page** for viewing the core dump detail.
- Delete should have a confirmation dialog and use the single-coredump delete endpoint.

### 2. Core Dump Detail Page

A new route/page for viewing a single core dump's detail:

- Show the parsed output (`parsed_output` field from the detail endpoint) in a **read-only Monaco editor** with no syntax highlighting (plain text mode).
- Show the core dump metadata (filename, chip, firmware version, size, parse status, uploaded at, parsed at).
- Provide a download link (same `<a href>` pattern).
- Show the parse status as-is without any custom UI treatment (no special styling for PENDING/PARSED/ERROR states — these are temporary).

### 3. Device List — Last Core Dump Column

- Add a new **sortable** column `Last Core Dump` to the devices list table.
- Display the `last_coredump_at` field as an **absolute** datetime using `toLocaleString()`.
- No visual highlighting — plain text, show "—" when null.

## API Endpoints Used

- `GET /api/devices/{device_id}/coredumps` — list core dumps (summary schema)
- `GET /api/devices/{device_id}/coredumps/{coredump_id}` — get detail with parsed output
- `GET /api/devices/{device_id}/coredumps/{coredump_id}/download` — download raw .dmp binary
- `DELETE /api/devices/{device_id}/coredumps/{coredump_id}` — delete single core dump
- `GET /api/devices` — already returns `last_coredump_at` on each device summary
