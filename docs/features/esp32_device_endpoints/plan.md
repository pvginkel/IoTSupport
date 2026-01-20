# ESP32 Device Endpoints - Technical Plan

## 0) Research Log & Findings

Researched the existing configuration and asset infrastructure to understand the baseline implementation. Key findings:

1. **Config API** (`app/api/configs.py`): Currently serves configs via `GET /api/configs/<mac>` endpoint with wrapped response (ConfigResponseSchema). Service layer (`ConfigService`) handles file I/O and MAC validation. Files stored directly in filesystem at `ESP32_CONFIGS_DIR`.

2. **Assets API** (`app/api/assets.py`): Currently has `POST /api/assets` for uploads with signature verification. Assets stored in `ASSETS_DIR` from config. No read/serve endpoint exists.

3. **URL routing**: The existing endpoint `GET /api/configs/<mac_address>` returns wrapped JSON with metadata. Need to add `.json` suffix detection to trigger raw mode while preserving existing behavior.

4. **Testing infrastructure**: Comprehensive test coverage in `tests/api/test_configs.py` and `tests/services/test_config_service.py`. Tests use fixtures from `conftest.py` including `make_config_file`, `valid_mac`, `sample_config`.

5. **Metrics integration**: All API endpoints record operations via `MetricsService`. New endpoints should follow the same pattern.

6. **MQTT notifications**: Config saves publish MQTT messages via `MqttService`. Read-only device endpoints should not publish notifications.

7. **No authentication**: Confirmed in product brief - designed for trusted homelab environment with no auth required.

## 1) Intent & Scope

**User intent**

Add raw file-serving endpoints to allow ESP32 devices to fetch configuration and firmware files directly from the backend, replacing NGINX static file serving. This centralizes file access control while maintaining the existing management API for UI operations.

**Prompt quotes**

"Add endpoints to serve raw config and asset files directly to ESP32 devices"
"GET /api/configs/<mac>.json that returns the raw JSON configuration content (not wrapped in a response schema)"
"GET /api/assets/<filename> that serves raw firmware binary files"
"The .json extension triggers raw mode vs. the existing wrapped response"
"Includes Cache-Control: no-cache header"
"Unauthenticated (trusted network)"

**In scope**

- Add `GET /api/configs/<mac>.json` endpoint returning raw JSON config content
- Add `GET /api/assets/<filename>` endpoint serving raw binary files
- Implement `.json` suffix detection in config endpoint routing
- Return HTTP 404 when config or asset file does not exist
- Add `Cache-Control: no-cache` header to device endpoint responses
- Preserve existing `GET /api/configs/<mac>` wrapped response behavior
- Preserve existing `POST /api/assets` upload behavior
- Add comprehensive tests for new endpoints

**Out of scope**

- NGINX rewrite rules (deployment responsibility)
- Authentication/authorization (trusted network assumption)
- Rate limiting for device endpoints
- Content-type validation beyond what exists for uploads
- Caching strategies beyond no-cache header
- Asset directory browsing/listing
- Config file watching or push notifications to devices

**Assumptions / constraints**

- Config files already validated as valid JSON by `ConfigService.save_config`
- Asset files stored with filename preservation (no renaming/hashing)
- MAC addresses normalized to lowercase by `ConfigService`
- Filesystem storage is fast enough for direct serving (CephFS in production)
- No concurrent modification issues (atomic writes via temp files)
- ESP32 devices expect raw content without wrapper objects
- Same `MetricsService` and `ConfigService` instances from DI container
- Flask's `send_file` appropriate for binary asset serving

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Add `GET /api/configs/<mac>.json` endpoint that returns raw JSON config content
- [ ] Add `GET /api/assets/<filename>` endpoint that serves raw firmware binary files
- [ ] Keep existing `GET /api/configs/<mac>` endpoint working with wrapped response
- [ ] Return HTTP 404 when config or asset file doesn't exist
- [ ] Add `Cache-Control: no-cache` header to all device endpoint responses
- [ ] Endpoints must be unauthenticated (no auth checks)

## 2) Affected Areas & File Map

- Area: `app/api/configs.py` - Config API endpoints module
- Why: Add new route handler for `GET /api/configs/<mac>.json` with raw response
- Evidence: `app/api/configs.py:69-101` - Existing `get_config` endpoint shows pattern for retrieving configs and error handling

- Area: `app/api/assets.py` - Asset API endpoints module
- Why: Add new route handler for `GET /api/assets/<filename>` to serve binary files
- Evidence: `app/api/assets.py:26-156` - Existing `upload_asset` endpoint shows service injection and metrics recording patterns

- Area: `app/services/asset_upload_service.py` - Asset upload service
- Why: May need method to retrieve asset file path for serving (currently only has upload logic)
- Evidence: `app/services/asset_upload_service.py:185-228` - Service has `assets_dir` and `save_file` method showing filesystem access pattern

- Area: `tests/api/test_configs.py` - Config API tests
- Why: Add tests for new `.json` suffix endpoint behavior and Cache-Control header
- Evidence: `tests/api/test_configs.py:44-77` - Existing `TestGetConfig` class shows testing pattern for get operations

- Area: `tests/api/test_assets.py` - Asset API tests
- Why: Add tests for new asset serving endpoint with various file scenarios
- Evidence: File exists and should mirror config test structure

- Area: `app/services/container.py` - Dependency injection container
- Why: Verify asset_upload_service wiring for new asset serving functionality
- Evidence: Referenced in `app/api/assets.py:37-39` via `Provide[ServiceContainer.asset_upload_service]`

- Area: `app/services/metrics_service.py` - Metrics service
- Why: May need new metric methods for device file serving operations
- Evidence: `app/api/configs.py:66` - Existing `record_operation` method used for tracking operations

## 3) Data Model / Contracts

- Entity / contract: Raw config JSON response for `GET /api/configs/<mac>.json`
- Shape: Direct JSON object (no wrapper), identical to stored file content. Example:
  ```json
  {
    "deviceName": "Living Room Sensor",
    "deviceEntityId": "sensor.living_room",
    "enableOTA": true,
    "mqttBroker": "mqtt.local",
    "updateInterval": 60
  }
  ```
- Refactor strategy: No backwards compatibility needed; new endpoint is additive. Existing wrapped endpoint unchanged.
- Evidence: `app/schemas/config.py:47-56` - ConfigResponseSchema shows current wrapped format that must be preserved for `GET /api/configs/<mac>`

- Entity / contract: Raw binary response for `GET /api/assets/<filename>`
- Shape: Binary file data with `application/octet-stream` MIME type and `Cache-Control: no-cache` header
- Refactor strategy: No backwards compatibility needed; new endpoint is additive. No existing GET endpoint for assets.
- Evidence: `app/api/assets.py:26` - Only POST endpoint exists currently

- Entity / contract: HTTP 404 error for missing files
- Shape: Standard error response (same as existing endpoints):
  ```json
  {
    "error": "Config aa-bb-cc-dd-ee-ff was not found",
    "code": "RECORD_NOT_FOUND"
  }
  ```
- Refactor strategy: Reuse existing `@handle_api_errors` decorator and exception types
- Evidence: `app/exceptions.py:17-22` - RecordNotFoundException already exists and is handled

## 4) API / Integration Surface

- Surface: `GET /api/configs/<mac>.json`
- Inputs: `mac` path parameter (MAC address with `.json` suffix), e.g., `aa-bb-cc-dd-ee-ff.json`
- Outputs: Raw JSON config content from file, `Content-Type: application/json`, `Cache-Control: no-cache` header, HTTP 200
- Errors: HTTP 400 for invalid MAC format, HTTP 404 for config not found
- Evidence: `app/api/configs.py:69-101` - Existing get_config shows MAC validation and error handling pattern

- Surface: `GET /api/configs/<mac>` (existing, must preserve)
- Inputs: `mac` path parameter (MAC address without `.json` suffix), e.g., `aa-bb-cc-dd-ee-ff`
- Outputs: Wrapped JSON response via ConfigResponseSchema, HTTP 200
- Errors: HTTP 400 for invalid MAC, HTTP 404 for not found (unchanged behavior)
- Evidence: `app/api/configs.py:69-101` - Current implementation must continue working

- Surface: `GET /api/assets/<filename>`
- Inputs: `filename` path parameter (asset filename), e.g., `firmware-v1.2.3.bin`
- Outputs: Raw binary file content, `Content-Type: application/octet-stream`, `Cache-Control: no-cache` header, HTTP 200
- Errors: HTTP 400 for invalid filename (path traversal), HTTP 404 for asset not found
- Evidence: `app/services/asset_upload_service.py:80-103` - Filename validation shows security pattern

## 5) Algorithms & State Machines

- Flow: Raw config serving (`GET /api/configs/<mac>.json`)
- Steps:
  1. Extract MAC address from path, detect `.json` suffix
  2. Strip `.json` suffix to get bare MAC address
  3. Delegate to `ConfigService.get_config(mac)` (existing method)
  4. Extract raw `content` dict from ConfigDetail
  5. Set `Cache-Control: no-cache` header on response
  6. Return raw JSON content (Flask auto-serializes dict to JSON)
  7. Record operation metrics via MetricsService
- States / transitions: None (stateless request/response)
- Hotspots: File I/O is synchronous; acceptable for ~200 devices at low request rates
- Evidence: `app/api/configs.py:69-101` - Existing pattern uses service, then returns schema

- Flow: Asset file serving (`GET /api/assets/<filename>`)
- Steps:
  1. Extract filename from path parameter
  2. Validate filename for path traversal (delegate to AssetUploadService or inline)
  3. Construct file path: `assets_dir / filename`
  4. Check file existence; raise RecordNotFoundException if missing
  5. Use Flask's `send_file(path, mimetype='application/octet-stream')` to serve
  6. Set `Cache-Control: no-cache` header on response
  7. Record operation metrics via MetricsService
- States / transitions: None (stateless request/response)
- Hotspots: Binary file serving via Flask send_file; acceptable for firmware files under ~10MB
- Evidence: `app/services/asset_upload_service.py:80-103` - Filename validation pattern

- Flow: Wrapped config serving (`GET /api/configs/<mac>`) - existing, unchanged
- Steps: Same as current implementation, returns ConfigResponseSchema
- States / transitions: None
- Hotspots: None (no change)
- Evidence: `app/api/configs.py:69-101` - Current implementation

## 6) Derived State & Invariants

None. These endpoints are stateless read operations with no derived state, persistence writes, or cleanup actions.

Justification: Both endpoints serve files directly from filesystem without transformations, filtering, or state mutations. No derived values drive writes or cleanup. MAC address normalization happens in ConfigService (already tested), and filename validation prevents path traversal but doesn't derive state.

## 7) Consistency, Transactions & Concurrency

- Transaction scope: No transactions; read-only file serving
- Atomic requirements: None; no writes or multi-step operations
- Retry / idempotency: Naturally idempotent (GET requests); safe to retry
- Ordering / concurrency controls: None needed; read operations are safe to interleave
- Evidence: `app/api/configs.py:69-101` - Existing read endpoint has no transaction scope

## 8) Errors & Edge Cases

- Failure: Config file does not exist for requested MAC
- Surface: `GET /api/configs/<mac>.json`
- Handling: ConfigService raises RecordNotFoundException, `@handle_api_errors` converts to HTTP 404 with error JSON
- Guardrails: Existing exception handling infrastructure
- Evidence: `app/api/configs.py:73-101` and `app/exceptions.py:17-22`

- Failure: Invalid MAC address format (e.g., uppercase, wrong separators)
- Surface: `GET /api/configs/<mac>.json`
- Handling: ConfigService raises InvalidOperationException, converted to HTTP 400
- Guardrails: Existing MAC validation in ConfigService.get_config
- Evidence: `app/services/config_service.py:119-122` - MAC validation before file access

- Failure: Asset file does not exist for requested filename
- Surface: `GET /api/assets/<filename>`
- Handling: Raise RecordNotFoundException, converted to HTTP 404
- Guardrails: Explicit file existence check before send_file
- Evidence: `app/exceptions.py:17-22` - RecordNotFoundException pattern

- Failure: Path traversal attempt in asset filename (e.g., `../../etc/passwd`)
- Surface: `GET /api/assets/<filename>`
- Handling: Validate filename (no `..`, `/`, `\`), raise ValidationException, converted to HTTP 400
- Guardrails: Reuse AssetUploadService.validate_filename or inline validation
- Evidence: `app/services/asset_upload_service.py:80-103` - Existing filename validation

- Failure: Empty or malformed filename in asset request
- Surface: `GET /api/assets/<filename>`
- Handling: Validation raises ValidationException, converted to HTTP 400
- Guardrails: Filename validation before file access
- Evidence: `app/services/asset_upload_service.py:89-91` - Empty filename check

- Failure: Requesting `.json` suffix with invalid MAC
- Surface: `GET /api/configs/<mac>.json`
- Handling: After stripping `.json`, invalid MAC format raises InvalidOperationException (HTTP 400)
- Guardrails: Same validation as non-.json endpoint
- Evidence: `app/services/config_service.py:119-122`

- Failure: JSON decode error when reading config file (corrupted file)
- Surface: `GET /api/configs/<mac>.json`
- Handling: ConfigService.get_config raises InvalidOperationException, converted to HTTP 400
- Guardrails: Existing error handling in ConfigService
- Evidence: `app/services/config_service.py:132-135` - JSON decode exception handling

## 9) Observability / Telemetry

- Signal: `device_config_get_total` (or reuse existing config operation metric)
- Type: Counter with labels `{status: "success"|"error"}`
- Trigger: On GET /api/configs/<mac>.json completion (success or failure)
- Labels / fields: operation="get_raw", status, duration
- Consumer: Prometheus, existing dashboards for config operations
- Evidence: `app/api/configs.py:65-66` - Existing metrics_service.record_operation pattern

- Signal: `device_asset_get_total` (or extend existing asset metrics)
- Type: Counter with labels `{status: "success"|"error", filename}`
- Trigger: On GET /api/assets/<filename> completion
- Labels / fields: operation="serve", status, duration, optional filename
- Consumer: Prometheus, asset serving dashboards
- Evidence: `app/api/assets.py:148-155` - Existing metrics_service.record_asset_upload pattern

- Signal: Application logs
- Type: Structured log entries
- Trigger: On file not found, validation errors, successful serves
- Labels / fields: logger name, level, MAC/filename, error details
- Consumer: Log aggregation, debugging
- Evidence: `app/services/config_service.py:17` - Logger usage pattern

## 10) Background Work & Shutdown

None. These are synchronous HTTP request handlers with no background threads, workers, or long-running operations.

## 11) Security & Permissions

- Concern: Path traversal in asset filename
- Touchpoints: `GET /api/assets/<filename>` endpoint
- Mitigation: Validate filename contains no `..`, `/`, `\` characters before accessing filesystem
- Residual risk: Acceptable; filesystem permissions provide second layer of defense
- Evidence: `app/services/asset_upload_service.py:93-103` - Existing path traversal prevention

- Concern: Unauthenticated access to config and firmware files
- Touchpoints: Both new endpoints
- Mitigation: None; explicit design decision for trusted homelab network
- Residual risk: Acceptable per product brief; network-level security assumed
- Evidence: `docs/product_brief.md:12` - "No authentication - Designed for trusted homelab environments"

- Concern: Information disclosure via config file contents
- Touchpoints: `GET /api/configs/<mac>.json`
- Mitigation: None; configs contain device settings meant for ESP32 consumption
- Residual risk: Acceptable; same data already accessible via wrapped endpoint
- Evidence: `app/api/configs.py:69-101` - Existing endpoint serves same content

## 12) UX / UI Impact

Not applicable. These endpoints are for ESP32 device consumption, not UI. No frontend changes required.

## 13) Deterministic Test Plan

- Surface: `GET /api/configs/<mac>.json` endpoint
- Scenarios:
  - Given valid MAC with .json suffix, When requesting raw config, Then return HTTP 200 with raw JSON content and Cache-Control header
  - Given valid MAC without .json suffix, When requesting config, Then return HTTP 200 with wrapped response (existing behavior preserved)
  - Given MAC with .json suffix for non-existent config, When requesting, Then return HTTP 404 with error JSON
  - Given invalid MAC format with .json suffix, When requesting, Then return HTTP 400 with error JSON
  - Given valid MAC with .json suffix for corrupted JSON file, When requesting, Then return HTTP 400 with error JSON
  - Given uppercase MAC with .json suffix, When requesting, Then normalize and return HTTP 200 with raw JSON
- Fixtures / hooks: `make_config_file`, `valid_mac`, `sample_config`, `client` from conftest.py
- Gaps: None
- Evidence: `tests/api/test_configs.py:44-77` - Existing test patterns for config endpoint

- Surface: `GET /api/assets/<filename>` endpoint
- Scenarios:
  - Given valid filename for existing asset, When requesting, Then return HTTP 200 with binary content and Cache-Control header
  - Given filename for non-existent asset, When requesting, Then return HTTP 404
  - Given filename with path traversal (../, ..\), When requesting, Then return HTTP 400
  - Given filename with directory separators (/, \), When requesting, Then return HTTP 400
  - Given empty filename, When requesting, Then return HTTP 400
  - Given valid filename with different file sizes, When requesting, Then serve complete binary content
- Fixtures / hooks: New `make_asset_file` fixture (similar to `make_config_file`), `assets_dir` fixture from test_settings
- Gaps: None
- Evidence: `tests/api/test_assets.py` - Existing test file for asset operations

- Surface: MetricsService integration for new endpoints
- Scenarios:
  - Given successful raw config get, When operation completes, Then metrics record success status and duration
  - Given failed raw config get (404), When operation fails, Then metrics record error status
  - Given successful asset serve, When operation completes, Then metrics record success status and duration
  - Given failed asset serve (404, 400), When operation fails, Then metrics record error status
- Fixtures / hooks: `container` fixture to access MetricsService, mock or spy on metric methods
- Gaps: None
- Evidence: `tests/api/test_configs.py:242-343` - Existing metrics testing patterns

## 14) Implementation Slices

Not applicable. Feature is small enough to implement in a single slice.

Single slice: Add raw device endpoints (all files touched together)
- Goal: ESP32 devices can fetch configs and assets directly from backend
- Touches: `app/api/configs.py`, `app/api/assets.py`, `tests/api/test_configs.py`, `tests/api/test_assets.py`, `tests/conftest.py` (if asset fixture needed)
- Dependencies: None; no feature flags; deploy when tests pass

## 15) Risks & Open Questions

- Risk: Flask `send_file` performance with larger firmware files (>10MB)
- Impact: Slow device downloads, potential request timeouts
- Mitigation: Test with realistic firmware sizes; consider nginx offload if needed in future

- Risk: File I/O errors (permission denied, disk full) during read operations
- Impact: HTTP 500 errors for devices
- Mitigation: OSError handling converts to HTTP 500; existing `@handle_api_errors` infrastructure

- Risk: Concurrent config updates while device is downloading
- Impact: Device may receive partially updated config (mid-write)
- Mitigation: Existing atomic writes via temp files ensure devices never read partial content

- Risk: Missing Cache-Control header breaks device caching assumptions
- Impact: Devices cache stale configs
- Mitigation: Explicit test case verifies header presence; fail fast if missing

- Risk: Metrics recording failures shouldn't break device requests
- Impact: Lost observability but device still functions
- Mitigation: Metrics wrapped in try/finally; exceptions logged but not raised

## 16) Confidence

Confidence: High — Feature is a straightforward addition with well-established patterns (existing config/asset endpoints), clear requirements, minimal new logic, and strong test foundation.

