# NVS Provisioning - Technical Plan

## 0) Research Log & Findings

### Areas Researched

**Current Provisioning Implementation:**
- `app/api/devices.py:208-243`: The `get_provisioning` endpoint returns a JSON response as a downloadable `.bin` file containing provisioning data (device_key, client_id, client_secret, token_url, base_url, mqtt_url, wifi_ssid, wifi_password).
- `app/services/device_service.py:412-442`: The `get_provisioning_package` method builds a dict with all provisioning fields from the device, Keycloak, and config.
- `app/schemas/device.py:126-137`: `ProvisioningPackageSchema` defines the existing fields but is currently unused (endpoint returns raw JSON).

**Binary Data Patterns:**
- `app/services/firmware_service.py`: Uses `struct` module for ESP32 binary parsing with little-endian format. This establishes the pattern for binary data handling.
- The codebase follows a service-layer pattern where binary generation logic would belong in a dedicated service.

**ESP-IDF NVS Format Research:**
From ESP-IDF documentation, NVS uses a page-based format:
- NVS partition is organized into 4KB pages
- Page header: 32 bytes (state, sequence number, version, CRC)
- Entry header: 32 bytes per entry (namespace, type, span, key, data/pointer)
- String data stored inline or across multiple entries if >32 bytes
- CRC32 used for integrity checking
- Entry format supports primitive types (u8, u16, u32, u64, i8, i16, i32, i64, string, blob)

**Key Length Constraint:**
NVS keys are limited to 15 characters. Since keys are in a dedicated `prov` namespace, no prefix is needed. Keys match the JSON response from `/iot/provisioning`: `device_key` (10), `client_id` (9), `client_secret` (13), `token_url` (9), `base_url` (8), `mqtt_url` (8), `wifi_ssid` (9), `wifi_password` (13). All fit within 15 chars.

**Test Patterns:**
- `tests/api/test_devices.py:272-315`: Existing provisioning tests mock Keycloak and verify JSON content.
- `tests/services/test_device_service.py`: Service tests use container DI and mock external services.

### Resolution of Questions

**Question: What namespace should NVS entries use?**
Resolution: Use `prov` (short for provisioning) as the namespace. NVS namespaces are also limited to 15 chars.

**Question: What is the minimum partition size needed?**
Resolution: One 4KB page is sufficient. With 8 string entries averaging ~50 bytes each, total data is ~500 bytes plus headers (~300 bytes overhead per page), well under 4KB.

**Question: Should we support optional fields being omitted?**
Resolution: Yes. MQTT and WiFi fields are optional in config (`app/config.py:68-79, 184-191`). When `None`, omit the NVS entry entirely rather than storing empty strings.

---

## 1) Intent & Scope

**User intent**

Update the provisioning endpoint to return an ESP-IDF NVS binary blob instead of a JSON file, enabling direct flashing to ESP32 devices via the browser using Web Serial API and esptool-js. The NVS format allows devices to read credentials natively using `nvs_get_str()` without JSON parsing.

**Prompt quotes**

"Update the `/api/devices/{id}/provisioning` endpoint to return JSON with `partition` and `data` fields"
"`data` field contains base64-encoded NVS binary blob"
"Use the same key names as the JSON response (no prefix needed since keys are in `prov` namespace)"
"Implement NVS binary format generation in Python"

**In scope**

- Modify `GET /api/devices/<id>/provisioning` to return JSON `{partition, data}` instead of binary file download
- Create NVS binary generator utility implementing ESP-IDF NVS page format
- Add new response schema `NvsProvisioningResponseSchema`
- Update existing API and service tests
- Document frontend impact

**Out of scope**

- Multiple NVS pages (one 4KB page is sufficient for provisioning data)
- NVS blob type support (only string type needed)
- NVS encryption at rest (frontend handles flashing, device decrypts with flash encryption if enabled)
- Frontend esptool-js integration (separate plan per change brief)

**Assumptions / constraints**

- ESP-IDF version compatibility: NVS format v2 (version byte = 0xFE) is standard since ESP-IDF 4.x
- Single namespace `prov` for all provisioning keys
- All values stored as NVS string type (type = 0x21)
- Little-endian byte order (ESP32 is little-endian)
- CRC32 uses standard polynomial (IEEE 802.3)

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Update `/api/devices/{id}/provisioning` endpoint to return JSON with `partition` and `data` fields
- [ ] `partition` field contains the string "nvs" (standard NVS partition name)
- [ ] `data` field contains base64-encoded NVS binary blob
- [ ] NVS blob contains the same provisioning data (device_key, client_id, client_secret, token_url, base_url, mqtt_url, wifi_ssid, wifi_password)
- [ ] NVS key names match `/iot/provisioning` JSON keys (no prefix, keys in `prov` namespace)
- [ ] Implement NVS binary format generation in Python (page header, entry headers, data)
- [ ] Add response schema for the new JSON format
- [ ] Update existing tests to validate new response format
- [ ] Document frontend impact in docs/features/nvs_provisioning/frontend_impact.md

---

## 2) Affected Areas & File Map

- Area: `app/utils/nvs_generator.py` (new file)
- Why: New utility module for generating NVS binary format from key-value pairs
- Evidence: Pattern established by `app/services/firmware_service.py:1-30` using `struct` for ESP32 binary work

- Area: `app/services/device_service.py::get_provisioning_package`
- Why: Update return type from dict to include NVS binary generation
- Evidence: `app/services/device_service.py:412-442` — current method returns dict for JSON serialization

- Area: `app/api/devices.py::get_provisioning`
- Why: Change response from binary file download to JSON with base64-encoded NVS blob
- Evidence: `app/api/devices.py:208-243` — currently uses `Response(content, mimetype="application/octet-stream")`

- Area: `app/schemas/device.py`
- Why: Add new `NvsProvisioningResponseSchema` for the JSON response format and remove the now-unused `ProvisioningPackageSchema`
- Evidence: `app/schemas/device.py:126-137` — existing `ProvisioningPackageSchema` will be removed as the response format changes completely

- Area: `tests/api/test_devices.py::TestDevicesProvisioning`
- Why: Update tests to validate new JSON response format with base64 NVS data
- Evidence: `tests/api/test_devices.py:272-315` — current tests parse JSON from binary response

- Area: `tests/services/test_device_service.py`
- Why: Add tests for NVS generation with various field combinations
- Evidence: `tests/services/test_device_service.py:17-95` — pattern for service method tests

- Area: `tests/utils/test_nvs_generator.py` (new file)
- Why: Unit tests for NVS binary format generation
- Evidence: Pattern from other test modules, low-level binary testing is best isolated

- Area: `docs/features/nvs_provisioning/frontend_impact.md` (new file)
- Why: Document the API change for frontend developers
- Evidence: `docs/features/device_provisioning_mdm/frontend_impact.md` — established pattern

---

## 3) Data Model / Contracts

- Entity / contract: NvsProvisioningResponseSchema (new response schema)
- Shape:
```json
{
  "partition": "nvs",
  "data": "<base64-encoded NVS binary blob>"
}
```
- Refactor strategy: Complete replacement of existing response format. No backwards compatibility needed per `CLAUDE.md` BFF pattern rules. The old binary file download is removed entirely.
- Evidence: `app/schemas/device.py:126-137` — `ProvisioningPackageSchema` shows field naming pattern

- Entity / contract: NVS Key Mapping
- Shape:
| NVS Key | Source Field | Type |
|---------|--------------|------|
| `device_key` | device.key | string |
| `client_id` | device.client_id | string |
| `client_secret` | keycloak secret | string |
| `token_url` | config.OIDC_TOKEN_URL | string |
| `base_url` | config.BASEURL | string |
| `mqtt_url` | config.MQTT_URL | string (optional) |
| `wifi_ssid` | config.WIFI_SSID | string (optional) |
| `wifi_password` | config.WIFI_PASSWORD | string (optional) |
- Refactor strategy: Keys match `/iot/provisioning` JSON response; no prefix needed in `prov` namespace.
- Evidence: `docs/features/nvs_provisioning/change_brief.md:21-33` — key mapping table

---

## 4) API / Integration Surface

- Surface: `GET /api/devices/<int:device_id>/provisioning`
- Inputs: `device_id` path parameter (integer)
- Outputs:
  - 200: JSON `{ "partition": "nvs", "data": "<base64>" }` validated by `NvsProvisioningResponseSchema`
  - 404: Device not found (ErrorResponseSchema)
  - 502: Keycloak secret retrieval failed (ErrorResponseSchema)
- Errors:
  - `RecordNotFoundException` → 404 (device not found)
  - `ExternalServiceException` → 502 (Keycloak unavailable)
- SpectTree integration: Add `@api.validate(resp=SpectreeResponse(HTTP_200=NvsProvisioningResponseSchema, HTTP_404=ErrorResponseSchema, HTTP_502=ErrorResponseSchema))` decorator for OpenAPI documentation
- Evidence: `app/api/devices.py:208-243` — current endpoint lacks `@api.validate`; other endpoints in the file show the pattern

---

## 5) Algorithms & State Machines

- Flow: NVS Binary Generation
- Steps:
  1. Receive dict of key-value pairs (provisioning data)
  2. Filter out keys with `None` values (optional fields)
  3. Initialize 4KB byte buffer (one NVS page)
  4. Write page header (32 bytes): state=0xFFFFFFFE (active), seq=0, version=0xFE, reserved, CRC32
  5. Write namespace entry (32 bytes): type=0x00, span=1, chunk_idx=0xFF, key="prov"
  6. For each key-value pair:
     a. Calculate string length and required spans (each span = 32 bytes)
     b. Write entry header: namespace_idx=0, type=0x21 (string), span count, key (15 bytes max)
     c. Write string data with null terminator, pad to 32-byte boundary
  7. Calculate and write page header CRC32
  8. Calculate and write entry state bitmap CRC32
  9. Return bytes object
- States / transitions: None (stateless transformation)
- Hotspots: CRC32 calculation must match ESP-IDF implementation (standard IEEE polynomial). String encoding must be UTF-8 with null terminator.
- Evidence: `app/services/firmware_service.py:153-200` — binary parsing pattern using struct

- Flow: Provisioning Package with NVS
- Steps:
  1. Get device by ID (raises RecordNotFoundException if not found)
  2. Build client_id from device model code and device key
  3. Fetch client secret from Keycloak (raises ExternalServiceException on failure)
  4. Collect all provisioning values into dict with NVS key names
  5. Generate NVS binary using nvs_generator
  6. Base64-encode the binary
  7. Return dict with partition="nvs" and data=base64_string
- States / transitions: None
- Hotspots: Keycloak secret fetch is the only external call; failure handling already in place.
- Evidence: `app/services/device_service.py:412-442` — current get_provisioning_package method

---

## 6) Derived State & Invariants

- Derived value: NVS binary blob
  - Source: Provisioning dict assembled from Device model, Keycloak secret, and app config (unfiltered except for None optional values)
  - Writes / cleanup: None (ephemeral, generated on each request)
  - Guards: None (no persistent state)
  - Invariant: Binary format must be valid ESP-IDF NVS that can be read by `nvs_get_str()`
  - Evidence: `app/services/device_service.py:427-442` — source data assembly

- Derived value: Base64-encoded data field
  - Source: Raw NVS binary bytes
  - Writes / cleanup: None (ephemeral)
  - Guards: None
  - Invariant: Must be standard base64 encoding (RFC 4648) decodable by browser's `atob()` or equivalent
  - Evidence: N/A — new derivation

- Derived value: Optional field presence
  - Source: Config values for MQTT_URL, WIFI_SSID, WIFI_PASSWORD
  - Writes / cleanup: When None, NVS entry is omitted entirely
  - Guards: Check for None before adding to NVS entries
  - Invariant: Device firmware must handle missing optional keys gracefully
  - Evidence: `app/config.py:68-79, 184-191` — fields are typed as `str | None`

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: Single read-only operation; no transaction needed
- Atomic requirements: None — provisioning generation is stateless read
- Retry / idempotency: Endpoint is naturally idempotent (GET request). Multiple calls return same data (assuming Keycloak secret unchanged).
- Ordering / concurrency controls: None needed. No writes to database.
- Evidence: `app/api/devices.py:208-243` — endpoint does not modify any state

---

## 8) Errors & Edge Cases

- Failure: Device not found
- Surface: API endpoint
- Handling: 404 response with error message
- Guardrails: Standard RecordNotFoundException handling via `@handle_api_errors`
- Evidence: `app/api/devices.py:209` — `@handle_api_errors` decorator

- Failure: Keycloak unavailable / secret retrieval fails
- Surface: API endpoint (via service)
- Handling: 502 response indicating external service error
- Guardrails: ExternalServiceException propagates to error handler
- Evidence: `app/services/device_service.py:431` — keycloak_admin_service.get_client_secret call

- Failure: String value exceeds NVS storage limit
- Surface: NVS generator
- Handling: Raise ValidationException with descriptive message
- Guardrails: Check string length before encoding; NVS max string = 4000 bytes
- Evidence: N/A — new validation logic

- Failure: Key name exceeds 15 character limit
- Surface: NVS generator
- Handling: Raise ValidationException
- Guardrails: Validate key length at entry point
- Evidence: ESP-IDF NVS documentation — 15-char key limit

- Failure: Required field is None or empty
- Surface: NVS generator
- Handling: Raise ValidationException with descriptive message indicating which required field is missing
- Guardrails: Validate that required fields (p_dev_key, p_client_id, p_secret, p_token_url, p_base_url) are present and non-empty before generating blob
- Evidence: N/A — new validation logic to prevent device runtime failures

- Failure: Total entries exceed single page capacity
- Surface: NVS generator
- Handling: Raise ValidationException (for this use case, should not occur)
- Guardrails: Check entry count and total size; log warning if approaching limits
- Evidence: ESP-IDF spec — 126 entries max per page

---

## 9) Observability / Telemetry

- Signal: `get_provisioning` operation metric (existing)
- Type: histogram (duration) + counter (status)
- Trigger: On endpoint completion via existing metrics_service.record_operation
- Labels / fields: operation="get_provisioning", status=success/error
- Consumer: Prometheus metrics endpoint, existing dashboards
- Evidence: `app/api/devices.py:241-243` — metrics_service.record_operation call

No new telemetry signals needed. The existing operation metric captures provisioning requests. NVS generation is a pure CPU operation with negligible latency compared to Keycloak round-trip.

---

## 10) Background Work & Shutdown

No background workers introduced by this change. NVS generation is synchronous and completes within the request lifecycle.

---

## 11) Security & Permissions

- Concern: Sensitive data exposure (client_secret, wifi_password)
- Touchpoints: Provisioning endpoint response
- Mitigation: Endpoint requires authentication (admin API). Secret is already exposed in current JSON format; no change in security posture. Base64 is encoding, not encryption.
- Residual risk: Same as current implementation — provisioning package contains secrets. Acceptable because endpoint is admin-only and intended for device flashing.
- Evidence: `app/api/devices.py:1-28` — endpoint is under `/api/devices` which requires auth

---

## 12) UX / UI Impact

- Entry point: Device management page, "Download Provisioning" button
- Change: Button now fetches JSON and invokes esptool-js flash flow instead of downloading a file
- User interaction: User clicks button → modal opens with device connection prompt → Web Serial connects → NVS partition is flashed
- Dependencies: Frontend needs esptool-js integration (separate plan). Backend provides base64 NVS data.
- Evidence: `docs/features/nvs_provisioning/change_brief.md:36-44` — frontend flow description

---

## 13) Deterministic Test Plan

- Surface: NVS Generator utility (`app/utils/nvs_generator.py`)
- Scenarios:
  - Given a dict with all required keys, When generate_nvs_blob is called, Then returns valid 4096-byte NVS binary
  - Given a dict with optional keys set to None, When generate_nvs_blob is called, Then omits those entries from NVS
  - Given a key longer than 15 characters, When generate_nvs_blob is called, Then raises ValidationException
  - Given a string value longer than 4000 bytes, When generate_nvs_blob is called, Then raises ValidationException
  - Given a required key with None value, When generate_nvs_blob is called, Then raises ValidationException
  - Given a required key with empty string value, When generate_nvs_blob is called, Then raises ValidationException
  - Given valid NVS binary, When parsed manually, Then page header CRC matches computed CRC
  - Given valid NVS binary, When CRC compared to nvs_partition_gen.py output for same data, Then CRCs match
  - Given valid NVS binary, When parsed manually, Then namespace entry is correctly formatted
  - Given valid NVS binary with 8 entries, When parsed manually, Then all entry headers and data are correctly aligned
  - Given a string with non-ASCII UTF-8 characters, When generate_nvs_blob is called, Then string is correctly encoded with null terminator
- Fixtures / hooks: None needed; pure function testing
- Gaps: None
- Evidence: `tests/services/test_device_service.py` — pattern for isolated unit tests

- Surface: DeviceService.get_provisioning_package
- Scenarios:
  - Given a valid device with mocked Keycloak secret, When get_provisioning_package is called, Then returns dict with partition="nvs" and base64 data field
  - Given a device with optional config fields None, When get_provisioning_package is called, Then NVS blob omits optional entries
  - Given a valid provisioning response, When base64 data is decoded, Then result is 4096 bytes
- Fixtures / hooks: Mock keycloak_admin_service.get_client_secret; use container DI
- Gaps: None
- Evidence: `tests/services/test_device_service.py:471-552` — secret caching tests show mocking pattern

- Surface: GET /api/devices/<id>/provisioning endpoint
- Scenarios:
  - Given a valid device ID with mocked Keycloak, When GET provisioning is called, Then returns 200 with JSON content-type
  - Given a valid device ID with mocked Keycloak, When GET provisioning is called, Then response has "partition" and "data" keys
  - Given a valid device ID with mocked Keycloak, When base64 data is decoded, Then length is 4096 bytes
  - Given a nonexistent device ID, When GET provisioning is called, Then returns 404
  - Given Keycloak failure, When GET provisioning is called, Then returns 502
- Fixtures / hooks: Flask test client; mock keycloak_admin_service
- Gaps: None
- Evidence: `tests/api/test_devices.py:272-315` — existing provisioning endpoint tests

---

## 14) Implementation Slices

- Slice: NVS Generator Utility
- Goal: Implement core binary generation logic with full test coverage
- Touches: `app/utils/nvs_generator.py`, `tests/utils/test_nvs_generator.py`
- Dependencies: None; self-contained utility

- Slice: Service Layer Update
- Goal: Integrate NVS generator into provisioning package method
- Touches: `app/services/device_service.py`, `tests/services/test_device_service.py`
- Dependencies: NVS generator must be complete

- Slice: API Layer Update
- Goal: Change endpoint response format, add SpectTree validation, add new schema, and remove unused `ProvisioningPackageSchema`
- Touches: `app/api/devices.py`, `app/schemas/device.py`, `tests/api/test_devices.py`
- Dependencies: Service layer changes must be complete

- Slice: Documentation
- Goal: Document frontend impact for esptool-js integration
- Touches: `docs/features/nvs_provisioning/frontend_impact.md`
- Dependencies: API changes finalized

---

## 15) Risks & Open Questions

- Risk: NVS format implementation may have subtle incompatibilities with ESP-IDF
- Impact: Devices fail to read provisioning data after flash
- Mitigation: Test with actual ESP32 device during development; compare binary output with nvs_partition_gen.py tool output

- Risk: CRC32 calculation might use wrong polynomial or byte order
- Impact: NVS page rejected as corrupt by ESP-IDF
- Mitigation: Use Python's `binascii.crc32` with default parameters (initial value 0, matches IEEE 802.3 polynomial with XOR-out); add test case that verifies CRC against a known ESP-IDF NVS test vector from `nvs_partition_gen.py` output

- Risk: String encoding issues (UTF-8 vs ASCII, null terminator handling)
- Impact: Corrupted values read by device
- Mitigation: Strict UTF-8 encoding with explicit null terminator; length includes null byte

No blocking open questions remain. All NVS format details are documented in ESP-IDF source code and can be verified during implementation.

---

## 16) Confidence

Confidence: High — The change is well-scoped with clear requirements, established patterns in the codebase for binary handling, and comprehensive test coverage planned. The NVS format is stable and well-documented.
