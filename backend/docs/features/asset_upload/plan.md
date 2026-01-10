# Asset Upload API - Technical Plan

## 0) Research Log & Findings

### Research Areas

**Legacy PHP Implementation**
Examined `/work/iotsupport/src/html/assetctl/upload.php` to understand current behavior:
- Accepts multipart form uploads with `file`, `timestamp`, and `signature` fields
- Validates filename against path traversal (`..` sequences)
- Validates timestamp within ±5 minutes (±300 seconds)
- Uses RSA private key for signature verification via `openssl_verify` with SHA256
- Returns 400 for validation failures, 500 for filesystem errors, 200/"OK" for success
- Key insight: PHP uses the **private key** to extract the **public key** for verification (lines 25-27)

**Backend Architecture Patterns**
Reviewed existing Flask backend implementation:
- Layered architecture: API → Service → Filesystem (no database for this feature)
- API endpoints in `app/api/*.py` use blueprints, SpectTree validation, `@handle_api_errors`, `@inject`
- Services in `app/services/*.py` implement business logic; ConfigService pattern shows filesystem operations
- Schemas in `app/schemas/*.py` use Pydantic with `Field()` descriptions
- Configuration via `app/config.py` using Pydantic Settings with environment variables
- Dependency injection via `app/services/container.py` (providers.Factory or providers.Singleton)
- Error handling with typed exceptions: `InvalidOperationException`, `RecordNotFoundException`
- Metrics integration via MetricsService for operational visibility
- Test structure: `tests/services/` and `tests/api/` mirror app structure

**Conflicts & Resolutions**
1. **Multipart form-data vs JSON validation**: SpectTree's `@api.validate` decorator typically handles JSON payloads, but this endpoint requires multipart/form-data. Resolution: Access `request.files` and `request.form` directly, perform manual validation in service layer, skip `@api.validate(json=...)` and use `@api.validate(resp=...)` only for response documentation.

2. **Cryptographic library choice**: PHP uses OpenSSL; Python equivalent is `cryptography` library. Resolution: Use `cryptography.hazmat.primitives.serialization` to load RSA keys and `cryptography.hazmat.primitives.asymmetric.padding` with PSS/PKCS1v15 padding for verification. Note: Will verify exact padding scheme PHP uses (likely PKCS1v15).

3. **Timestamp parsing**: PHP uses `DateTime` constructor which is flexible; Python requires explicit format. Resolution: Use `datetime.fromisoformat()` for ISO 8601 strings, with fallback parsing if needed based on device timestamp format.

## 1) Intent & Scope

**User intent**

Migrate the cryptographically-signed asset upload functionality from the legacy PHP endpoint to the Python/Flask backend, preserving exact validation logic (path traversal prevention, timestamp replay attack protection, RSA/SHA256 signature verification) and enabling secure device-initiated uploads of firmware, images, or other asset files to the filesystem.

**Prompt quotes**

"Reference the original PHP implementation at /work/iotsupport/src/html/assetctl/upload.php for exact behavior requirements."

"Validate the timestamp is within a configurable tolerance window (default 5 minutes)"

"Verifies the signature using RSA/SHA256 against a configured signing key"

"Follow existing backend patterns (service layer, Pydantic schemas, dependency injection, error handling)"

**In scope**

- New `/api/assets` POST endpoint accepting multipart/form-data with `file`, `timestamp`, `signature` fields
- Filename validation: reject filenames containing `..` sequences
- Timestamp validation: verify timestamp is within configurable tolerance (default ±300 seconds)
- Cryptographic signature verification: RSA/SHA256 using signing key from file
- Filesystem storage: save uploaded file to configurable assets directory
- Configuration: `ASSETS_DIR` and `SIGNING_KEY_PATH` environment variables
- Service layer: `AssetUploadService` implementing validation and storage logic
- Schemas: Request validation and response schemas
- Error handling: appropriate HTTP status codes (400 for validation failures, 500 for server errors)
- Metrics: track upload attempts, successes, failures, file sizes, durations
- Comprehensive tests: service layer tests (validation scenarios, edge cases) and API tests (multipart uploads, error responses)

**Out of scope**

- Authentication/authorization (homelab trusted environment)
- File size limits (defer to Flask/WSGI server configuration)
- Virus scanning or content inspection
- Database persistence of upload metadata (filesystem-only like ConfigService)
- Serving/downloading uploaded assets (different endpoint, out of scope)
- Multi-file uploads (single file per request)
- Progress tracking or resumable uploads

**Assumptions / constraints**

- Devices send ISO 8601 formatted timestamps (consistent with PHP `DateTime` parsing)
- Signing key file is readable at startup and remains available during runtime
- RSA signature padding matches PHP's `openssl_verify` default (likely PKCS1v15)
- Assets directory is writable and has sufficient disk space
- Filename collisions are handled by overwriting (matching PHP `move_uploaded_file` behavior)
- No concurrent upload coordination needed (atomic filesystem writes via temp file + rename)

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Accept multipart/form-data POST requests at `/api/assets` with `file`, `timestamp`, and `signature` fields
- [ ] Validate filename does not contain `..` (path traversal prevention)
- [ ] Validate timestamp is within ±5 minutes of server time (replay attack prevention)
- [ ] Verify signature using RSA/SHA256 against a configured signing key
- [ ] Save valid uploads to a configurable assets directory
- [ ] Return appropriate HTTP error responses (400 for validation failures, 500 for server errors)
- [ ] Add `ASSETS_DIR` configuration setting for the upload destination
- [ ] Add `SIGNING_KEY_PATH` configuration setting for the RSA key location
- [ ] Follow existing backend patterns: service layer, Pydantic schemas, dependency injection, `@handle_api_errors`
- [ ] Include comprehensive tests for the service and API layers

## 2) Affected Areas & File Map

- Area: `app/config.py`
- Why: Add `ASSETS_DIR` and `SIGNING_KEY_PATH` configuration fields
- Evidence: `/work/backend/app/config.py:10-33` — Shows Settings class with Pydantic Field definitions for ESP32_CONFIGS_DIR, pattern to follow for new asset config fields

---

- Area: `app/services/asset_upload_service.py` (new file)
- Why: Implement business logic for file upload validation, signature verification, and filesystem storage
- Evidence: `/work/backend/app/services/config_service.py:40-267` — Shows ConfigService pattern: no BaseService inheritance (no database), constructor takes config paths, methods raise InvalidOperationException, atomic file writes via temp + rename

---

- Area: `app/schemas/asset_upload.py` (new file)
- Why: Define request/response schemas for asset upload endpoint
- Evidence: `/work/backend/app/schemas/config.py:1-53` — Shows Pydantic BaseModel pattern with Field descriptions, ConfigDict(from_attributes=True)

---

- Area: `app/api/assets.py` (new file)
- Why: Create `/api/assets` POST endpoint for multipart uploads
- Evidence: `/work/backend/app/api/configs.py:1-177` — Shows blueprint pattern, SpectreeResponse, @handle_api_errors, @inject, metrics integration, time.perf_counter() for timing

---

- Area: `app/api/__init__.py`
- Why: Register assets blueprint with main API blueprint
- Evidence: `/work/backend/app/api/__init__.py:9-15` — Shows pattern for importing and registering blueprints

---

- Area: `app/services/container.py`
- Why: Wire AssetUploadService with dependency injection
- Evidence: `/work/backend/app/services/container.py:10-23` — Shows providers.Factory pattern for ConfigService, need similar for AssetUploadService with config paths

---

- Area: `app/__init__.py`
- Why: Wire container to new `app.api.assets` module
- Evidence: `/work/backend/app/__init__.py:36-42` — Shows wire_modules list needing "app.api.assets" added

---

- Area: `app/services/metrics_service.py`
- Why: Add metrics for asset upload operations (attempts, successes, failures, file sizes, durations)
- Evidence: `/work/backend/CLAUDE.md:264-295` — Documents MetricsService pattern, use counters for totals and histograms for durations

---

- Area: `tests/services/test_asset_upload_service.py` (new file)
- Why: Test service validation logic, signature verification, filesystem operations, edge cases
- Evidence: `/work/backend/tests/services/test_config_service.py:1-50` — Shows test structure: pytest classes per method, fixtures for paths, test success and error paths

---

- Area: `tests/api/test_assets.py` (new file)
- Why: Test API endpoint with multipart uploads, validation errors, response formats
- Evidence: `/work/backend/tests/api/test_configs.py:1-50` — Shows API test pattern: FlaskClient fixture, test status codes, JSON responses, error cases

## 3) Data Model / Contracts

- Entity / contract: POST request to `/api/assets` (multipart/form-data)
- Shape:
  ```
  Content-Type: multipart/form-data

  Fields:
    file: (binary file data) - required
    timestamp: string (ISO 8601 format, e.g., "2026-01-09T14:30:00") - required
    signature: string (base64-encoded RSA signature of timestamp) - required
  ```
- Refactor strategy: No backwards compatibility needed (new endpoint); PHP endpoint remains active until frontend switches
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:3-10` — Shows $_FILES['file'], $_POST['timestamp'], base64_decode($_POST['signature'])

---

- Entity / contract: POST response (success)
- Shape:
  ```json
  {
    "filename": "firmware.bin",
    "size": 1048576,
    "uploaded_at": "2026-01-09T14:30:05.123456"
  }
  ```
- Refactor strategy: New schema; no compatibility concerns
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:39` — PHP returns plain "OK" text; Python response adds structured metadata

---

- Entity / contract: POST response (validation error 400)
- Shape:
  ```json
  {
    "error": "Invalid timestamp",
    "details": {
      "message": "Timestamp must be within ±300 seconds of server time"
    },
    "code": "VALIDATION_FAILED"
  }
  ```
- Refactor strategy: Follow existing error_handling.py pattern
- Evidence: `/work/backend/app/utils/error_handling.py:23-43` — Shows _build_error_response structure

---

- Entity / contract: Configuration settings
- Shape:
  ```python
  class Settings(BaseSettings):
      ASSETS_DIR: Path = Field(description="Path to assets upload directory")
      SIGNING_KEY_PATH: Path = Field(description="Path to RSA signing key file")
      TIMESTAMP_TOLERANCE_SECONDS: int = Field(default=300, description="Timestamp validation tolerance")
  ```
- Refactor strategy: Add to existing Settings class
- Evidence: `/work/backend/app/config.py:10-33` — Shows Settings class structure with Field descriptions

## 4) API / Integration Surface

- Surface: POST /api/assets
- Inputs:
  - Multipart form-data with `file` (binary), `timestamp` (string), `signature` (string base64)
  - Filename extracted from uploaded file metadata
  - Request origin (for CORS, already handled globally)
- Outputs:
  - Success (200): JSON with `filename`, `size`, `uploaded_at` fields
  - Validation errors (400): JSON error response with specific validation failure message
  - Server errors (500): JSON error response with generic message
  - Side effects: File written to `ASSETS_DIR` with original filename
- Errors:
  - 400 "Missing required field": If `file`, `timestamp`, or `signature` missing from form
  - 400 "Invalid filename": If filename contains `..` sequences
  - 400 "Invalid timestamp format": If timestamp not parseable as ISO 8601
  - 400 "Invalid timestamp": If timestamp outside ±300 second window
  - 400 "Invalid signature": If RSA signature verification fails
  - 500 "Failed to save file": If filesystem write fails
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:3-39` — Shows PHP validation sequence and error responses (400/500 status codes)

## 5) Algorithms & State Machines

- Flow: Asset upload validation and storage
- Steps:
  1. Extract `file`, `timestamp`, `signature` from multipart form-data; validate all required fields present
  2. Extract filename from uploaded file metadata; validate filename does not contain `..` sequences
  3. Parse timestamp string as ISO 8601 datetime
  4. Calculate server time and timestamp difference; validate absolute difference ≤ configured tolerance (default 300 seconds)
  5. Load RSA signing key from configured path (cached at service initialization)
  6. Decode base64 signature string to bytes
  7. Verify signature: RSA/SHA256 verification of timestamp string against decoded signature using public key derived from signing key
  8. If all validations pass, write file to assets directory using atomic temp file + rename pattern
  9. Return success response with filename, file size, and upload timestamp
- States / transitions: None (stateless request-response)
- Hotspots:
  - Signature verification: Cryptographic operation, typically <50ms for RSA-2048
  - Filesystem write: I/O bound, depends on file size and disk speed; expect <100ms for typical firmware files (<1MB)
  - Key loading: One-time cost at service initialization; ~10ms to parse PEM file
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:17-32` — Shows PHP validation sequence: timestamp diff calculation, openssl_verify call

## 6) Derived State & Invariants

- Derived value: Server timestamp for validation window
  - Source: `datetime.now(timezone.utc)` at request time (unfiltered system clock)
  - Writes / cleanup: Used only for comparison; no persistent writes from this value
  - Guards: No guards needed; validation window is symmetric (±tolerance)
  - Invariant: Timestamp validation must be timezone-aware (UTC) to avoid DST/timezone skew
  - Evidence: `/work/iotsupport/src/html/assetctl/upload.php:17-21` — PHP uses (new DateTime())->getTimestamp() for server time

---

- Derived value: Public key extracted from RSA private key
  - Source: Signing key file loaded at service initialization (filtered: only valid PEM keys loaded)
  - Writes / cleanup: Cached in memory for signature verification; no disk writes
  - Guards: Key loading wrapped in try/catch; service initialization fails if key invalid/unreadable
  - Invariant: Public key must match private key format used by devices for signing
  - Evidence: `/work/iotsupport/src/html/assetctl/upload.php:25-26` — PHP: `openssl_pkey_get_details($key)['key']` extracts public key from private key

---

- Derived value: Uploaded file destination path
  - Source: `ASSETS_DIR` (config) + filename (user input, filtered for path traversal)
  - Writes / cleanup: File written to derived path; no cleanup (overwrites allowed)
  - Guards: Filename validation rejects `..` sequences; assets directory validated writable at startup
  - Invariant: Final path must remain within `ASSETS_DIR` boundaries
  - Evidence: `/work/backend/app/services/config_service.py:200-220` — Shows atomic file write pattern with temp file + os.replace

## 7) Consistency, Transactions & Concurrency

- Transaction scope: Single file upload is atomic (temp file write + rename); no database transactions
- Atomic requirements: File must be fully written before being made available at final destination; use temp file in same directory + `os.replace()` for atomic rename
- Retry / idempotency: Uploads are idempotent (same filename overwrites previous); devices may retry with same timestamp + signature within tolerance window; signature verification prevents replay attacks after window expires
- Ordering / concurrency controls: No explicit locking; filesystem rename is atomic; concurrent uploads of different files succeed independently; concurrent uploads of same filename handled by OS (last writer wins)
- Evidence: `/work/backend/app/services/config_service.py:200-220` — Shows atomic write pattern: temp file in same directory, os.replace() for atomic rename, cleanup in finally block

## 8) Errors & Edge Cases

- Failure: Missing `file` field in multipart form
- Surface: POST /api/assets
- Handling: Return 400 "Missing required field 'file'" immediately; no further processing
- Guardrails: Check `'file' in request.files` before accessing; raise ValidationException if missing
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:3-6` — PHP checks isset($_FILES['file']) first

---

- Failure: Filename contains path traversal sequences (`..`)
- Surface: POST /api/assets
- Handling: Return 400 "Invalid filename: path traversal not allowed"; no file written
- Guardrails: Validate `'..' not in filename` before any file operations; raise InvalidOperationException
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:12-15` — PHP: `strpos($file['name'], '..') !== false` returns 400

---

- Failure: Timestamp not parseable as ISO 8601
- Surface: POST /api/assets
- Handling: Return 400 "Invalid timestamp format: expected ISO 8601"; example included in message
- Guardrails: Wrap `datetime.fromisoformat()` in try/except; raise ValidationException on parse failure
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:17` — PHP: `new DateTime($timestamp)` may throw exception

---

- Failure: Timestamp outside tolerance window (±300 seconds default)
- Surface: POST /api/assets
- Handling: Return 400 "Invalid timestamp: must be within ±300 seconds of server time"; include server time and timestamp in details
- Guardrails: Calculate `abs(server_time - upload_time).total_seconds()`; compare against configured tolerance; raise ValidationException if exceeded
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:18-21` — PHP: timestamp_diff < -300 or > 300 returns 400

---

- Failure: Base64 signature decode fails
- Surface: POST /api/assets
- Handling: Return 400 "Invalid signature format: expected base64-encoded string"
- Guardrails: Wrap `base64.b64decode()` in try/except; catch binascii.Error; raise ValidationException
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:10` — PHP: base64_decode($_POST['signature']) may fail silently or return false

---

- Failure: RSA signature verification fails (wrong signature, wrong key, tampered timestamp)
- Surface: POST /api/assets
- Handling: Return 400 "Invalid signature: cryptographic verification failed"
- Guardrails: Catch cryptography.exceptions.InvalidSignature; raise ValidationException; never leak key material in error messages
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:29-32` — PHP: verification !== 1 returns 400 "Invalid signature"

---

- Failure: Signing key file not readable at service initialization
- Surface: Application startup (service container initialization)
- Handling: Fail fast: raise exception during container.config_service() provider initialization; prevent app startup
- Guardrails: Load and validate key in AssetUploadService.__init__; catch FileNotFoundError and cryptography exceptions
- Evidence: `/work/backend/app/services/config_service.py:43-49` — ConfigService takes paths in __init__, validates config_dir accessibility

---

- Failure: Assets directory not writable (permissions, disk full, read-only filesystem)
- Surface: POST /api/assets (during file write)
- Handling: Return 500 "Failed to save file: [error details]"; log full exception with traceback
- Guardrails: Wrap file write in try/except; catch OSError; raise generic server error (avoid leaking filesystem paths to clients)
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:34-37` — PHP: move_uploaded_file failure returns 500 "Failed to move file"

---

- Failure: Empty filename (filename='')
- Surface: POST /api/assets
- Handling: Return 400 "Invalid filename: filename cannot be empty"
- Guardrails: Check `filename and filename.strip()` before validation; raise ValidationException if empty
- Evidence: Implicit in PHP file handling; explicit check prevents edge case

---

- Failure: Signature field missing or empty
- Surface: POST /api/assets
- Handling: Return 400 "Missing required field 'signature'"
- Guardrails: Check `'signature' in request.form and request.form['signature']` before processing
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:10` — PHP accesses $_POST['signature'] directly (would error if missing)

## 9) Observability / Telemetry

- Signal: `asset_upload_requests_total`
- Type: Counter
- Trigger: Incremented on every POST /api/assets request, labeled by status (success, validation_error, server_error)
- Labels / fields: `status={success|validation_error|server_error}`, `error_type={filename|timestamp|signature|filesystem}` (for failures)
- Consumer: Prometheus; dashboard showing upload success rate and error breakdown
- Evidence: `/work/backend/app/api/configs.py:35-65` — Shows metrics_service integration pattern in API endpoints

---

- Signal: `asset_upload_duration_seconds`
- Type: Histogram
- Trigger: Recorded for every upload attempt (success or failure); measured via time.perf_counter() around service call
- Labels / fields: `status={success|failure}`
- Consumer: Prometheus; P50/P95/P99 latency monitoring for upload operations
- Evidence: `/work/backend/app/api/configs.py:35-65` — Shows time.perf_counter() pattern for operation timing

---

- Signal: `asset_upload_file_size_bytes`
- Type: Histogram
- Trigger: Recorded on successful uploads; value = uploaded file size in bytes
- Labels / fields: None
- Consumer: Prometheus; track file size distribution, detect anomalies (unusually large files)
- Evidence: `/work/backend/CLAUDE.md:278-281` — Documents histogram for duration measurements; adapt for size tracking

---

- Signal: `asset_upload_signature_verification_duration_seconds`
- Type: Histogram
- Trigger: Recorded during signature verification operation (regardless of success/failure)
- Labels / fields: `result={valid|invalid}`
- Consumer: Prometheus; monitor cryptographic operation performance, detect key issues
- Evidence: New metric specific to security operation; follows duration histogram pattern

---

- Signal: Structured log entry on upload success
- Type: Structured log (INFO level)
- Trigger: After successful file write
- Labels / fields: `filename`, `size_bytes`, `timestamp`, `duration_ms`
- Consumer: Log aggregation (Loki/CloudWatch); audit trail for uploaded assets
- Evidence: `/work/backend/app/services/config_service.py:4` — Shows logging import pattern

---

- Signal: Structured log entry on validation failure
- Type: Structured log (WARNING level)
- Trigger: On validation errors (filename, timestamp, signature)
- Labels / fields: `error_type`, `filename`, `timestamp`, `remote_addr` (if available)
- Consumer: Log aggregation; security monitoring for potential attack patterns
- Evidence: `/work/backend/app/services/config_service.py:70-73` — Shows logger.warning pattern for validation issues

## 10) Background Work & Shutdown

None. This feature has no background workers, threads, or long-running operations. All processing is synchronous within HTTP request-response cycle.

## 11) Security & Permissions

- Concern: Path traversal prevention
- Touchpoints: AssetUploadService.validate_filename() method; called before any filesystem operations
- Mitigation: Reject filenames containing `..` sequences; validate filename does not contain directory separators (`/`, `\`); log rejected attempts
- Residual risk: Complex filename edge cases (Unicode normalization attacks, NTFS alternate data streams); acceptable for homelab environment; consider additional path sanitization if deployed to untrusted environments
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:12-15` — PHP path traversal check

---

- Concern: Replay attack prevention
- Touchpoints: AssetUploadService.validate_timestamp() method; verifies timestamp freshness
- Mitigation: Enforce configurable time window (default ±300 seconds); signature includes timestamp, so replayed signatures fail after window expires
- Residual risk: Uploads within tolerance window can be replayed; acceptable trade-off for clock skew tolerance; tighten window to ±60 seconds if stricter protection needed
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:17-21` — PHP timestamp window validation

---

- Concern: Cryptographic signature verification
- Touchpoints: AssetUploadService.verify_signature() method using `cryptography` library
- Mitigation: RSA/SHA256 signature verification using public key derived from signing key; timestamp included in signed data prevents tampering; use constant-time comparison if signature comparison exposed to timing attacks (library handles this)
- Residual risk: Key compromise allows forged uploads; key rotation not implemented; acceptable for homelab; implement key rotation if key exposure suspected
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:25-32` — PHP RSA signature verification

---

- Concern: Signing key exposure
- Touchpoints: AssetUploadService.__init__ loads key from filesystem; key cached in memory
- Mitigation: Key file path configurable via environment variable; file permissions should restrict read access (0600); never log key material; verify key file permissions at startup
- Residual risk: Memory dumps could expose key; process memory access requires root; acceptable for homelab deployment
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:25` — PHP loads key from filesystem

---

- Concern: Denial of service via large file uploads
- Touchpoints: Flask/WSGI server request size limits; filesystem storage limits
- Mitigation: Rely on Flask's `MAX_CONTENT_LENGTH` configuration (set by ops/deployment); monitor disk usage via metrics; consider implementing file size limit in service layer if needed
- Residual risk: Large uploads consume disk space; no cleanup/quota enforcement; acceptable for trusted device uploads; implement quota if disk exhaustion risk increases
- Evidence: Out of scope per assumptions, but standard Flask configuration

## 12) UX / UI Impact

This feature has no direct UI impact (backend-only API for device-initiated uploads). Frontend changes out of scope for this plan.

Note: If frontend needs to trigger uploads on behalf of devices, a separate authenticated endpoint would be required (devices use signature-based auth; frontend would use session/token-based auth).

## 13) Deterministic Test Plan

- Surface: AssetUploadService.validate_filename()
- Scenarios:
  - Given valid filename "firmware.bin", When validate_filename called, Then no exception raised
  - Given filename with path traversal "../etc/passwd", When validate_filename called, Then InvalidOperationException raised
  - Given filename with forward slash "subdir/firmware.bin", When validate_filename called, Then InvalidOperationException raised
  - Given empty filename "", When validate_filename called, Then InvalidOperationException raised
  - Given filename with only spaces "   ", When validate_filename called, Then InvalidOperationException raised
- Fixtures / hooks: None needed (pure validation logic)
- Gaps: None
- Evidence: `/work/backend/tests/services/test_config_service.py:13-50` — Shows service test pattern

---

- Surface: AssetUploadService.validate_timestamp()
- Scenarios:
  - Given timestamp equal to server time, When validate_timestamp called, Then no exception raised
  - Given timestamp 299 seconds in past (within tolerance), When validate_timestamp called, Then no exception raised
  - Given timestamp 301 seconds in past (outside tolerance), When validate_timestamp called, Then ValidationException raised
  - Given timestamp 299 seconds in future (within tolerance), When validate_timestamp called, Then no exception raised
  - Given timestamp 301 seconds in future (outside tolerance), When validate_timestamp called, Then ValidationException raised
  - Given non-ISO8601 timestamp "not-a-date", When validate_timestamp called, Then ValidationException raised
- Fixtures / hooks: Mock `datetime.now(timezone.utc)` to control server time for deterministic tests
- Gaps: None
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:17-21` — Shows ±300 second tolerance logic

---

- Surface: AssetUploadService.verify_signature()
- Scenarios:
  - Given valid timestamp and correct signature, When verify_signature called, Then no exception raised
  - Given valid timestamp and incorrect signature, When verify_signature called, Then ValidationException raised
  - Given tampered timestamp (different from signed), When verify_signature called, Then ValidationException raised
  - Given non-base64 signature string, When verify_signature called, Then ValidationException raised
  - Given empty signature, When verify_signature called, Then ValidationException raised
- Fixtures / hooks: Generate test RSA keypair in conftest.py; provide fixture for signing timestamps; inject test key path into service
- Gaps: None
- Evidence: `/work/iotsupport/src/html/assetctl/upload.php:25-32` — Shows RSA verification behavior

---

- Surface: AssetUploadService.save_file()
- Scenarios:
  - Given valid file upload, When save_file called, Then file written to assets directory with correct content
  - Given upload to writable directory, When save_file called, Then file written atomically (temp + rename)
  - Given upload with existing filename, When save_file called, Then existing file overwritten
  - Given upload to non-existent directory, When save_file called, Then OSError raised (directory should exist at startup)
  - Given upload to read-only directory, When save_file called, Then OSError raised
- Fixtures / hooks: Temporary assets directory via pytest tmp_path; mock file object with read() method
- Gaps: None
- Evidence: `/work/backend/app/services/config_service.py:200-220` — Shows atomic write pattern to test

---

- Surface: POST /api/assets (API endpoint)
- Scenarios:
  - Given valid multipart upload (file, timestamp, signature), When POST /api/assets, Then 200 response with filename/size/timestamp
  - Given missing 'file' field, When POST /api/assets, Then 400 "Missing required field 'file'"
  - Given missing 'timestamp' field, When POST /api/assets, Then 400 "Missing required field 'timestamp'"
  - Given missing 'signature' field, When POST /api/assets, Then 400 "Missing required field 'signature'"
  - Given filename with path traversal, When POST /api/assets, Then 400 "Invalid filename"
  - Given timestamp outside tolerance, When POST /api/assets, Then 400 "Invalid timestamp"
  - Given invalid signature, When POST /api/assets, Then 400 "Invalid signature"
  - Given all validations pass, When POST /api/assets, Then metrics recorded (request count, duration, file size)
- Fixtures / hooks: FlaskClient fixture; helper function to create valid multipart requests with signatures; test RSA keypair fixture
- Gaps: None
- Evidence: `/work/backend/tests/api/test_configs.py:1-50` — Shows API test pattern with FlaskClient

---

- Surface: MetricsService asset upload metrics
- Scenarios:
  - Given successful upload, When metrics queried, Then asset_upload_requests_total{status=success} incremented
  - Given validation failure, When metrics queried, Then asset_upload_requests_total{status=validation_error} incremented
  - Given successful upload, When metrics queried, Then asset_upload_duration_seconds histogram recorded
  - Given successful upload, When metrics queried, Then asset_upload_file_size_bytes histogram recorded
- Fixtures / hooks: MetricsService singleton; parse Prometheus text format from /metrics endpoint
- Gaps: None
- Evidence: `/work/backend/app/api/configs.py:35-65` — Shows metrics integration to verify

## 14) Implementation Slices

Small feature, implement in single slice:

- Slice: Complete asset upload feature
- Goal: Ship working `/api/assets` endpoint with validation, signature verification, filesystem storage, tests
- Touches:
  - `app/config.py` (configuration)
  - `app/services/asset_upload_service.py` (business logic)
  - `app/schemas/asset_upload.py` (validation schemas)
  - `app/api/assets.py` (HTTP endpoint)
  - `app/api/__init__.py` (blueprint registration)
  - `app/services/container.py` (DI wiring)
  - `app/__init__.py` (module wiring)
  - `app/services/metrics_service.py` (metrics)
  - `tests/services/test_asset_upload_service.py` (service tests)
  - `tests/api/test_assets.py` (API tests)
- Dependencies: Install `cryptography` library (add to pyproject.toml); none others

## 15) Risks & Open Questions

**Risks**

- Risk: RSA signature padding mismatch between PHP OpenSSL and Python cryptography library
- Impact: Signature verification always fails; uploads rejected despite valid signatures from devices
- Mitigation: Test with actual device-generated signatures during implementation; PHP likely uses PKCS1v15 (default for openssl_verify); confirm with cryptography.hazmat.primitives.asymmetric.padding.PKCS1v15()

---

- Risk: ISO 8601 timestamp format variations (timezone designators, milliseconds)
- Impact: Timestamp parsing fails for valid device timestamps
- Mitigation: Test with sample timestamps from devices; implement flexible parsing with fallback formats if needed; consider `dateutil.parser.isoparse()` for more lenient parsing

---

- Risk: Signing key file format incompatibility (PEM vs DER, public vs private key)
- Impact: Service initialization fails; app won't start
- Mitigation: Document required key format (PEM-encoded RSA private key); provide test key generation instructions; validate key format in unit tests

---

- Risk: Concurrent uploads of same filename may corrupt file during write
- Impact: Partially written files if OS rename not atomic or temp file collision
- Mitigation: Use same-directory temp files with unique names (temp file + timestamp suffix); rely on os.replace() atomicity; acceptable risk for low-concurrency homelab environment

---

- Risk: Large file uploads block Waitress WSGI worker threads
- Impact: Worker exhaustion if many simultaneous large uploads
- Mitigation: Document recommended file size limits; consider async file writes if issue observed; monitor worker thread usage metrics; acceptable for expected upload patterns (firmware files <1MB)

**Open Questions**

None. All ambiguities resolved via PHP implementation analysis and existing backend pattern review.

## 16) Confidence

Confidence: High — PHP implementation provides clear specification for validation logic; existing ConfigService demonstrates filesystem patterns; cryptography library is mature and well-documented; test plan covers all validation scenarios; metrics integration follows established pattern; no database complexity or distributed system coordination.
