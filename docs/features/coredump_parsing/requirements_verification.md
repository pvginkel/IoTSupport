# Requirements Verification — Coredump Parsing

**Result: ALL 32 REQUIREMENTS PASS**

## Configuration
- [x] PARSE_SIDECAR_XFER_DIR — `app/config.py:88-91,281`
- [x] PARSE_SIDECAR_URL — `app/config.py:92-95,282`
- [x] MAX_COREDUMPS (default 20) — `app/config.py:96-99,283`

## Data Model
- [x] coredumps table with all fields — `app/models/coredump.py:28-92`
- [x] ParseStatus enum (PENDING, PARSED, ERROR) — `app/models/coredump.py:14-25`
- [x] Device.coredumps relationship with cascade delete — `app/models/device.py:92-97`

## Service Layer
- [x] JSON sidecar removed — `app/services/coredump_service.py` (no JSON writing)
- [x] DB record created with PENDING — `app/services/coredump_service.py:163-175`
- [x] MAX_COREDUMPS enforcement — `app/services/coredump_service.py:193-234`
- [x] Background parsing (extract ELF, copy files, call sidecar) — `app/services/coredump_service.py:236-380`
- [x] Sidecar call format — `app/services/coredump_service.py:347-352`
- [x] 3 retries, ERROR on failure — `app/services/coredump_service.py:323-380`
- [x] Xfer cleanup (best-effort) — `app/services/coredump_service.py:366-374`

## Upload Endpoint
- [x] Creates DB record + triggers background parse — `app/api/iot.py:353-436`

## Admin API
- [x] GET list — `app/api/coredumps.py:30-66`
- [x] GET detail — `app/api/coredumps.py:69-98`
- [x] GET download — `app/api/coredumps.py:101-140`
- [x] DELETE single — `app/api/coredumps.py:143-176`
- [x] DELETE all — `app/api/coredumps.py:179-209`
- [x] Device ownership verification — all endpoints check device_id

## Tests
- [x] Service tests — `tests/services/test_coredump_service.py` (26 tests)
- [x] API tests — `tests/api/test_coredumps.py` (14 tests)
- [x] No Alembic migration (not in production)
