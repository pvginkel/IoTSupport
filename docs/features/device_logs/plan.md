# Device Logs Feature - Technical Plan

## 0) Research Log & Findings

### Areas Researched

1. **Existing API Patterns** (`app/api/devices.py:1-353`)
   - Endpoints follow a consistent pattern: Blueprint registration, SpectTree validation, `@handle_api_errors` decorator, and dependency injection via `@inject`
   - Operations are timed with `time.perf_counter()` and recorded via `metrics_service.record_operation()`
   - Device lookup uses `device_service.get_device(device_id)` which raises `RecordNotFoundException` for 404

2. **Service Layer Architecture** (`app/services/device_service.py:32-626`)
   - Services are factory-instantiated classes injected via the container
   - Services that need the database inherit from `BaseService` or receive `Session` via constructor
   - External HTTP services (like `KeycloakAdminService`) use `httpx.Client` and raise `ExternalServiceException` on failure

3. **Error Handling** (`app/utils/error_handling.py:1-171`)
   - `ExternalServiceException` maps to HTTP 502 Bad Gateway
   - The plan needs a new exception type or mapping for 503 Service Unavailable

4. **Configuration System** (`app/config.py:50-217`, `app/config.py:218-496`)
   - Two-layer config: `Environment` loads from env vars (UPPER_CASE), `Settings` provides lowercase fields
   - New config fields require additions to both classes and the `Settings.load()` method

5. **Container Wiring** (`app/services/container.py:1-121`, `app/__init__.py:63-77`)
   - New services registered as `providers.Singleton` or `providers.Factory`
   - API modules must be added to the `wire_modules` list

6. **Schema Patterns** (`app/schemas/device.py:1-166`)
   - Pydantic schemas with `ConfigDict(from_attributes=True)` for ORM integration
   - Query parameters use separate schema classes (e.g., `NvsProvisioningQuerySchema`)

7. **Test Patterns** (`tests/conftest.py:1-409`, `tests/api/test_devices.py:1-800`)
   - Tests use `app`, `client`, `container` fixtures
   - External services are mocked with `patch.object()`
   - API tests verify status codes and response structure

### Key Findings

- **No 503 mapping exists**: The current `handle_api_errors` only maps `ExternalServiceException` to 502. A new exception type `ServiceUnavailableException` should be added and mapped to 503.
- **HTTP client decision**: The project uses `httpx` for HTTP clients (see `KeycloakAdminService`). We will use `httpx` for Elasticsearch queries as well, for consistency and to avoid adding a new dependency. The Elasticsearch REST API is simple enough that a dedicated DSL library is not needed for this read-only use case.
- **No database persistence needed**: This feature is read-only from Elasticsearch; no new models or migrations required.

### Conflicts Resolved

- The change brief specifies "503 Service Unavailable if Elasticsearch is unreachable" but the codebase only has 502 for external service errors. Resolution: Add a new `ServiceUnavailableException` that maps to 503, distinct from `ExternalServiceException` (502) which is for upstream service failures where we got a bad response. 503 is appropriate when the service is completely unreachable.

---

## 1) Intent & Scope

**User intent**

Add an API endpoint to retrieve device logs from an external Elasticsearch cluster, enabling the frontend to display a scrolling log window per device. The endpoint queries the `logstash-http-*` index pattern, filters by the device's `device_entity_id`, and returns timestamped log entries with pagination support.

**Prompt quotes**

"Add endpoint `GET /api/devices/<id>/logs`"
"Query Elasticsearch index `logstash-http-*` filtering by device's `device_entity_id`"
"Return max 1000 log entries per request"
"Return 503 Service Unavailable if Elasticsearch is unreachable"
"Support `start`, `end`, and `query` parameters"

**In scope**

- New `GET /api/devices/<id>/logs` endpoint on the devices blueprint
- Elasticsearch service singleton for querying logs
- Configuration for Elasticsearch connection (URL, credentials, index pattern)
- Query parameter support for time range (`start`, `end`) and wildcard search (`query`)
- Pagination via `has_more`, `window_start`, `window_end` response fields
- 503 error response when Elasticsearch is unreachable
- Unit and integration tests for service and API layers

**Out of scope**

- Writing logs to Elasticsearch (handled externally by Logstash)
- Device log retention policies or index lifecycle management
- Aggregations or analytics on log data
- WebSocket/real-time log streaming
- Frontend implementation

**Assumptions / constraints**

- Elasticsearch cluster is already deployed and accessible at the configured URL
- Logs are indexed with fields `@timestamp`, `entity_id`, and `message` by an external Logstash pipeline
- Device `device_entity_id` may be null for some devices (endpoint returns empty logs array)
- Authentication to Elasticsearch uses HTTP Basic Auth if credentials are configured

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Add endpoint `GET /api/devices/<id>/logs`
- [ ] Query Elasticsearch index `logstash-http-*` filtering by device's `device_entity_id`
- [ ] Return array of objects with `timestamp` and `message` fields
- [ ] Support `start` datetime parameter (beginning of time range, defaults to 1 hour ago)
- [ ] Support `end` datetime parameter (end of time range, defaults to now)
- [ ] Support `query` parameter with wildcard search on message field
- [ ] Return max 1000 log entries per request
- [ ] Return `has_more` attribute indicating if more results exist
- [ ] On partial results, return `window_start` and `window_end` datetime values so caller can paginate
- [ ] Return 503 Service Unavailable if Elasticsearch is unreachable
- [ ] Add Elasticsearch configuration to environment variables (URL, username, password, index pattern)

---

## 2) Affected Areas & File Map

- Area: `app/config.py` - `Environment` class
- Why: Add Elasticsearch environment variables (URL, username, password, index pattern)
- Evidence: `app/config.py:50-215` - pattern for adding new environment variables with `Field()` defaults

- Area: `app/config.py` - `Settings` class
- Why: Add lowercase Elasticsearch settings fields and wire them in `Settings.load()`
- Evidence: `app/config.py:218-290` - pattern for adding corresponding settings fields

- Area: `app/exceptions.py`
- Why: Add `ServiceUnavailableException` for 503 responses
- Evidence: `app/exceptions.py:50-57` - `ExternalServiceException` pattern to follow

- Area: `app/utils/error_handling.py`
- Why: Map `ServiceUnavailableException` to HTTP 503
- Evidence: `app/utils/error_handling.py:119-126` - `ExternalServiceException` handling pattern

- Area: `app/services/elasticsearch_service.py` (new file)
- Why: Encapsulate Elasticsearch client and log query logic
- Evidence: `app/services/keycloak_admin_service.py:27-68` - singleton service pattern with config injection

- Area: `app/services/container.py`
- Why: Register `ElasticsearchService` as singleton provider
- Evidence: `app/services/container.py:80-85` - singleton service registration pattern

- Area: `app/schemas/device_logs.py` (new file)
- Why: Define request/response schemas for the logs endpoint
- Evidence: `app/schemas/device.py:126-136` - query parameter schema pattern

- Area: `app/api/devices.py`
- Why: Add `GET /api/devices/<id>/logs` endpoint
- Evidence: `app/api/devices.py:106-134` - existing `GET /api/devices/<id>` endpoint pattern

- Area: `app/__init__.py`
- Why: No changes needed - `app.api.devices` is already wired; `ElasticsearchService` will be injected via `Provide[ServiceContainer.elasticsearch_service]` in the endpoint
- Evidence: `app/__init__.py:68` - devices module already in wire list

- Area: `app/services/metrics_service.py`
- Why: Add Elasticsearch-specific metrics (Counter and Histogram) in `initialize_metrics()`
- Evidence: `app/services/metrics_service.py:29-43` - existing metric definition pattern

- Area: `tests/services/test_elasticsearch_service.py` (new file)
- Why: Unit tests for Elasticsearch service
- Evidence: `tests/services/test_keycloak_admin_service.py` - external service test patterns

- Area: `tests/api/test_devices.py`
- Why: Add API tests for the logs endpoint
- Evidence: `tests/api/test_devices.py:319-506` - existing device endpoint test patterns

- Area: `tests/conftest.py`
- Why: Add Elasticsearch test configuration to `_build_test_settings()`
- Evidence: `tests/conftest.py:60-110` - test settings construction pattern

---

## 3) Data Model / Contracts

- Entity / contract: `Environment` (Elasticsearch configuration)
- Shape:
  ```python
  ELASTICSEARCH_URL: str | None = Field(default=None, description="Elasticsearch base URL")
  ELASTICSEARCH_USERNAME: str | None = Field(default=None, description="Elasticsearch username")
  ELASTICSEARCH_PASSWORD: str | None = Field(default=None, description="Elasticsearch password")
  ELASTICSEARCH_INDEX_PATTERN: str = Field(default="logstash-http-*", description="Index pattern for device logs")
  ```
- Refactor strategy: New fields with None defaults; no back-compat needed
- Evidence: `app/config.py:88-103` - MQTT settings pattern

- Entity / contract: `Settings` (lowercase config fields)
- Shape:
  ```python
  elasticsearch_url: str | None
  elasticsearch_username: str | None
  elasticsearch_password: str | None
  elasticsearch_index_pattern: str
  ```
- Refactor strategy: Direct mapping from Environment in `Settings.load()`
- Evidence: `app/config.py:244-248` - MQTT settings fields pattern

- Entity / contract: `DeviceLogsQuerySchema` (request query parameters)
- Shape:
  ```python
  {
    "start": "2026-02-01T14:00:00Z",  // optional, ISO datetime, defaults to 1 hour ago
    "end": "2026-02-01T14:43:27Z",    // optional, ISO datetime, defaults to now
    "query": "error*"                  // optional, wildcard pattern
  }
  ```
- Refactor strategy: New schema, no existing contract. Default values computed at request time in the API layer.
- Evidence: `app/schemas/device.py:126-136` - `NvsProvisioningQuerySchema` pattern

- Entity / contract: `DeviceLogsResponseSchema` (response body)
- Shape:
  ```json
  {
    "logs": [
      {"timestamp": "2026-02-01T14:43:27.948Z", "message": "Log line content..."}
    ],
    "has_more": true,
    "window_start": "2026-02-01T14:40:00.000Z",
    "window_end": "2026-02-01T14:43:27.948Z"
  }
  ```
- Refactor strategy: New schema, no existing contract
- Evidence: `app/schemas/device.py:109-113` - `DeviceListResponseSchema` pattern

- Entity / contract: `LogEntrySchema` (nested in response)
- Shape:
  ```python
  {
    "timestamp": datetime,
    "message": str
  }
  ```
- Refactor strategy: New schema, no existing contract
- Evidence: `app/schemas/device.py:52-65` - `DeviceSummarySchema` pattern

---

## 4) API / Integration Surface

- Surface: `GET /api/devices/<id>/logs`
- Inputs:
  - Path: `id` (int) - Device ID
  - Query: `start` (ISO datetime, optional) - Beginning of time range, defaults to 1 hour ago
  - Query: `end` (ISO datetime, optional) - End of time range, defaults to now
  - Query: `query` (string, optional) - Wildcard search pattern for message field
- Outputs:
  ```json
  {
    "logs": [{"timestamp": "...", "message": "..."}],
    "has_more": boolean,
    "window_start": "ISO datetime or null",
    "window_end": "ISO datetime or null"
  }
  ```
- Errors:
  - 404 Not Found: Device ID does not exist
  - 503 Service Unavailable: Elasticsearch unreachable or connection timeout
  - 400 Bad Request: Invalid datetime format in query parameters
- Evidence: `app/api/devices.py:106-134` - existing device GET endpoint pattern

---

## 5) Algorithms & State Machines

- Flow: Log Retrieval Query
- Steps:
  1. Validate device exists via `device_service.get_device(device_id)`
  2. Extract `device_entity_id` from device; if None, return empty logs array
  3. Build Elasticsearch query with:
     - Filter by `entity_id` field matching `device_entity_id`
     - Time range filter on `@timestamp` between `start` and `end`
     - Optional wildcard query on `message` field if `query` param provided
  4. Execute search with `size=1001` (1 extra to detect `has_more`)
  5. Sort results by `@timestamp` ascending (oldest first)
  6. If result count > 1000:
     - Set `has_more = true`
     - Truncate to first 1000 results
     - Set `window_start` = timestamp of first result
     - Set `window_end` = timestamp of last returned result
  7. If result count <= 1000:
     - Set `has_more = false`
     - Set `window_start` = timestamp of first result (or null if empty)
     - Set `window_end` = timestamp of last result (or null if empty)
  8. Map Elasticsearch `_source` fields to `LogEntrySchema`
  9. Return response with logs array and pagination metadata
- States / transitions: None (stateless query)
- Hotspots: Elasticsearch query latency (mitigated by index pattern and time range filters); large result sets (bounded by 1000 limit)
- Evidence: `app/services/keycloak_admin_service.py:129-219` - external service query pattern

---

## 6) Derived State & Invariants

- Derived value: `has_more` flag
  - Source: Elasticsearch hit count compared to limit (1000)
  - Writes / cleanup: None (read-only derivation)
  - Guards: Query size set to 1001 to detect overflow
  - Invariant: `has_more` is true if and only if more than 1000 results matched
  - Evidence: Change brief pagination requirements

- Derived value: `window_start` and `window_end` timestamps
  - Source: First and last timestamps from returned log entries
  - Writes / cleanup: None (read-only derivation)
  - Guards: Only populated when logs array is non-empty
  - Invariant: `window_start <= window_end` when both are set
  - Evidence: Change brief pagination requirements

- Derived value: Empty logs response when `device_entity_id` is null
  - Source: Device model `device_entity_id` field (nullable)
  - Writes / cleanup: None (short-circuits to empty response)
  - Guards: Check for null before querying Elasticsearch
  - Invariant: No Elasticsearch query executed when entity ID is missing
  - Evidence: `app/models/device.py:58` - `device_entity_id` is nullable

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: No database writes; single Elasticsearch read query per request
- Atomic requirements: None (read-only operation)
- Retry / idempotency: GET requests are naturally idempotent; Elasticsearch queries are stateless
- Ordering / concurrency controls: Results ordered by `@timestamp` ascending; no locking needed
- Evidence: `app/api/devices.py:106-134` - read-only endpoint pattern (no transaction commits)

---

## 8) Errors & Edge Cases

- Failure: Elasticsearch cluster unreachable (connection refused, timeout)
- Surface: `GET /api/devices/<id>/logs` API endpoint
- Handling: Return 503 Service Unavailable with error message
- Guardrails: Connection timeout configured (default 10s); new `ServiceUnavailableException` raised
- Evidence: `app/services/keycloak_admin_service.py:113-120` - HTTP error handling pattern

- Failure: Device not found
- Surface: `GET /api/devices/<id>/logs` API endpoint
- Handling: Return 404 Not Found (existing `RecordNotFoundException` behavior)
- Guardrails: Device lookup happens before Elasticsearch query
- Evidence: `app/utils/error_handling.py:101-108` - RecordNotFoundException handling

- Failure: Invalid datetime format in query parameters
- Surface: `GET /api/devices/<id>/logs` API endpoint
- Handling: Return 400 Bad Request via Pydantic validation
- Guardrails: Pydantic schema validates ISO datetime format
- Evidence: `app/utils/error_handling.py:71-81` - ValidationError handling

- Failure: Device has no `device_entity_id` configured
- Surface: `GET /api/devices/<id>/logs` service method
- Handling: Return empty logs array with `has_more=false`, null window timestamps
- Guardrails: Check for null before querying Elasticsearch
- Evidence: `app/models/device.py:58` - `device_entity_id` is nullable

- Failure: Elasticsearch returns error response (4xx/5xx)
- Surface: `ElasticsearchService.query_logs()` method
- Handling: Raise `ExternalServiceException` (maps to 502 Bad Gateway)
- Guardrails: HTTP response status check; meaningful error message extraction
- Evidence: `app/services/keycloak_admin_service.py:212-219` - HTTP error handling

- Failure: Query parameter `query` contains invalid Elasticsearch syntax
- Surface: Elasticsearch query execution
- Handling: Raise `ExternalServiceException` (maps to 502); let Elasticsearch return the parse error
- Guardrails: Document that `query` uses Elasticsearch wildcard syntax
- Evidence: Change brief specifies "wildcard search on message field"

---

## 9) Observability / Telemetry

- Signal: `elasticsearch_operations_total` (attribute on `MetricsService`)
- Type: Counter
- Trigger: Each Elasticsearch query (success or error)
- Labels / fields: `operation` (query_logs), `status` (success, error)
- Consumer: Prometheus metrics endpoint, operational dashboard
- Implementation: Add to `MetricsService.initialize_metrics()` following the `config_operations_total` pattern
- Evidence: `app/services/metrics_service.py:29-33` - Counter definition pattern

- Signal: `elasticsearch_query_duration_seconds` (attribute on `MetricsService`)
- Type: Histogram
- Trigger: After each Elasticsearch query completes
- Labels / fields: `operation` (query_logs)
- Consumer: Prometheus metrics endpoint, latency monitoring
- Implementation: Add to `MetricsService.initialize_metrics()` following the `config_operation_duration_seconds` pattern
- Evidence: `app/services/metrics_service.py:39-43` - Histogram definition pattern

- Signal: Structured log on query execution
- Type: Structured log (INFO level)
- Trigger: Query execution with device_entity_id, result count, duration
- Labels / fields: device_id, entity_id, result_count, duration_ms, has_more
- Consumer: Application logs (stdout/file)
- Evidence: `app/services/keycloak_admin_service.py:161` - operation logging pattern

- Signal: Structured log on Elasticsearch error
- Type: Structured log (ERROR level)
- Trigger: Connection failure or query error
- Labels / fields: device_id, error_type, error_message
- Consumer: Application logs, alerting
- Evidence: `app/services/keycloak_admin_service.py:214` - error logging pattern

---

## 10) Background Work & Shutdown

No background workers or scheduled jobs are required for this feature. The Elasticsearch service is a singleton HTTP client that can be instantiated lazily and does not require shutdown coordination.

- Worker / job: None
- Trigger cadence: N/A
- Responsibilities: N/A
- Shutdown handling: N/A
- Evidence: `app/services/keycloak_admin_service.py:53` - httpx.Client is stateless; no cleanup needed

---

## 11) Security & Permissions

- Concern: Elasticsearch credential exposure
- Touchpoints: `Settings` class, `ElasticsearchService` constructor
- Mitigation: Credentials stored in environment variables only; not logged or included in responses
- Residual risk: Credentials visible in memory; acceptable for server-side service
- Evidence: `app/config.py:172-179` - Keycloak secrets handling pattern

- Concern: Log data access control
- Touchpoints: `GET /api/devices/<id>/logs` endpoint
- Mitigation: Endpoint inherits existing admin authentication (OIDC when enabled); logs are filtered by device entity ID
- Residual risk: Admin users can view logs for any device; acceptable for admin-only API
- Evidence: `app/api/devices.py` - no per-device authorization (admin-only API)

---

## 12) UX / UI Impact

This is a backend-only feature. Frontend impact should be documented separately in `docs/features/device_logs/frontend_impact.md` if needed.

- Entry point: N/A (API only)
- Change: N/A
- User interaction: N/A
- Dependencies: Frontend will consume `GET /api/devices/<id>/logs` endpoint
- Evidence: N/A

---

## 13) Deterministic Test Plan

- Surface: `ElasticsearchService.query_logs()`
- Scenarios:
  - Given Elasticsearch is reachable, When querying with valid entity_id and time range, Then returns log entries sorted by timestamp ascending
  - Given Elasticsearch is reachable, When querying with wildcard query pattern, Then returns only matching log entries
  - Given Elasticsearch returns > 1000 results, When querying, Then returns first 1000 with has_more=true
  - Given Elasticsearch returns <= 1000 results, When querying, Then returns all with has_more=false
  - Given Elasticsearch is unreachable, When querying, Then raises ServiceUnavailableException
  - Given Elasticsearch returns HTTP error, When querying, Then raises ExternalServiceException
  - Given entity_id is None, When querying, Then returns empty logs array without hitting Elasticsearch
- Fixtures / hooks: Mock `httpx.Client` or use `responses` library; mock Elasticsearch JSON responses
- Gaps: No integration test against real Elasticsearch (requires separate test infrastructure)
- Evidence: `tests/services/test_keycloak_admin_service.py` - external service mocking patterns

- Surface: `GET /api/devices/<id>/logs` API endpoint
- Scenarios:
  - Given device exists and has logs, When GET with no params, Then returns 200 with logs array
  - Given device exists, When GET with start and end params, Then returns 200 with filtered logs
  - Given device exists, When GET with query param, Then returns 200 with filtered logs
  - Given device exists with no entity_id, When GET, Then returns 200 with empty logs array
  - Given device does not exist, When GET, Then returns 404
  - Given Elasticsearch is unreachable, When GET, Then returns 503
  - Given invalid datetime in query params, When GET, Then returns 400
- Fixtures / hooks: `make_device` fixture; mock `ElasticsearchService.query_logs()`
- Gaps: None
- Evidence: `tests/api/test_devices.py:319-506` - provisioning endpoint test patterns

---

## 14) Implementation Slices

- Slice: Configuration and Exception Foundation
- Goal: Add Elasticsearch config fields and 503 exception mapping
- Touches: `app/config.py`, `app/exceptions.py`, `app/utils/error_handling.py`, `tests/conftest.py`
- Dependencies: None; enables subsequent slices

- Slice: Elasticsearch Service
- Goal: Implement log query logic with error handling and metrics
- Touches: `app/services/elasticsearch_service.py` (new), `app/services/container.py`, `app/services/metrics_service.py`, `tests/services/test_elasticsearch_service.py` (new)
- Dependencies: Slice 1 (config and exceptions)

- Slice: API Endpoint and Schemas
- Goal: Wire up the endpoint with request/response validation
- Touches: `app/schemas/device_logs.py` (new), `app/api/devices.py`, `tests/api/test_devices.py`
- Dependencies: Slice 2 (Elasticsearch service)

---

## 15) Risks & Open Questions

- Risk: Elasticsearch query performance on large index
- Impact: Slow API responses under high log volume
- Mitigation: Time range filtering is required by design; Elasticsearch index should have proper time-based retention

- Risk: Elasticsearch schema mismatch (field names differ from expected)
- Impact: Empty or incorrect results
- Mitigation: Document expected field names (`@timestamp`, `entity_id`, `message`); add debug logging for query and response

- Risk: Connection pool exhaustion under load
- Impact: 503 errors on concurrent requests
- Mitigation: Use httpx connection pooling with sensible limits; singleton service reuses client

---

## 16) Confidence

Confidence: High - The feature is straightforward (read-only query proxy), follows established patterns in the codebase, and has clear requirements. The `start` parameter defaults to 1 hour ago (not "now") to ensure meaningful default behavior. The main risk is Elasticsearch field name assumptions which can be validated during testing.
