# Change Brief: Coredump Parsing & Management

## Summary

Add database-backed coredump tracking, automatic parsing via a sidecar container, per-device retention limits, and admin API endpoints. This builds on the recently added coredump upload support (`POST /iot/coredump`) which currently only saves raw `.dmp` files with JSON sidecar metadata to the filesystem.

## What Needs to Change

### Configuration
- Add `PARSE_SIDECAR_XFER_DIR` (Path) — shared volume between main container and parse sidecar for file transfer
- Add `PARSE_SIDECAR_URL` (str) — base URL of the parse sidecar (e.g., `http://localhost:8081`)
- Add `MAX_COREDUMPS` (int, default 20) — per-device retention limit; oldest dumps are deleted when exceeded

### Database Model
- New `coredumps` table linked to `devices` via foreign key
- Fields: id, device_id, filename, chip, firmware_version, size, parse_status (PENDING/PARSED/ERROR), parsed_output (text), uploaded_at, parsed_at, timestamps
- Add `coredumps` relationship to Device model (cascade delete)
- No Alembic migration needed (not yet in production)

### Coredump Service Refactor
- Remove JSON sidecar file writing — metadata moves to DB
- Create DB records on upload with `parse_status=PENDING`
- Enforce `MAX_COREDUMPS` per device — delete oldest records + files when limit exceeded
- Background parsing after upload: extract `.elf` from firmware ZIP in `ASSETS_DIR`, copy `.dmp` and `.elf` to `PARSE_SIDECAR_XFER_DIR`, call sidecar HTTP endpoint, update DB record with parsed output
- Sidecar endpoint: `GET {PARSE_SIDECAR_URL}/parse-coredump?core={dmp_name}&elf={elf_name}&chip={chip}` — returns `{"output": "..."}`
- Retry parsing up to 3 times on failure; after 3 failures write "Unable to parse coredump: {error}" as the parsed output with ERROR status
- Clean up xfer directory files after parsing (best-effort)

### Upload Endpoint Refactor
- `POST /iot/coredump` now creates a DB record and triggers background parsing
- Device lookup needed to get `device_id` for the DB record

### Admin API Endpoints
- Nested under `/api/devices/<device_id>/coredumps`
- `GET /` — list coredumps for device (summaries)
- `GET /<coredump_id>` — detail view including parsed output
- `GET /<coredump_id>/download` — download raw `.dmp` file
- `DELETE /<coredump_id>` — delete single coredump (DB record + file)
- `DELETE /` — delete all coredumps for device
- All endpoints verify the coredump belongs to the specified device

### Testing
- Service tests for all CoredumpService methods (CRUD, MAX enforcement, background parsing with mocked sidecar)
- API tests for all admin endpoints
- Update existing upload test to verify DB record creation
