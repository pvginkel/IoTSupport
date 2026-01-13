# MQTT Notifications - Technical Plan

## 0) Research Log & Findings

### Discovery Work

**Configuration Management:** Reviewed `app/services/config_service.py` and `app/api/configs.py`. The `save_config` method (lines 158-201) performs atomic writes via temp file + rename and returns `ConfigDetail`. The API endpoint at `/configs/<mac_address>` (PUT, lines 103-149) calls this service method. Delete operations occur at lines 152-182 in the API file.

**Asset Upload Flow:** Examined `app/services/asset_upload_service.py` and `app/api/assets.py`. The `upload_asset` method (lines 229-262) orchestrates validation and file saving. The API endpoint at `/assets` (POST, lines 25-150) processes multipart uploads and returns success/error responses.

**Dependency Injection:** The project uses `dependency-injector` with a centralized container at `app/services/container.py`. Services are registered as Singletons (for stateful services like `MetricsService`, `AssetUploadService`) or Factories (for stateless services like `ConfigService`). API endpoints receive services via the `@inject` decorator with `Provide[ServiceContainer.service_name]`.

**Metrics Integration:** Reviewed `app/services/metrics_service.py`. It's a singleton service that manages Prometheus metrics without background threads. All metrics are updated on-demand during API operations. The service exposes methods like `record_operation()`, `update_config_count()`, and `record_asset_upload()`.

**Testing Patterns:** Examined `tests/services/test_config_service.py` and `tests/conftest.py`. Tests use pytest fixtures for temporary directories, sample data, and service instantiation. The DI container is available via the `container` fixture, and Prometheus registry is cleared between tests to prevent metric registration conflicts.

**Python MQTT Libraries:** The change brief specifies "Mosquitto MQTT 5 server". The standard Python MQTT client is `paho-mqtt`, which supports MQTT v5.0. It provides persistent connections, automatic reconnection, QoS levels, and fire-and-forget publishing.

### Key Findings

1. **No database:** This application stores configs on filesystem, so no transaction scope concerns.
2. **Singleton pattern for MQTT:** The requirement for "persistent connection as singleton service" maps directly to the existing `MetricsService` singleton pattern.
3. **Fire-and-forget semantics:** MQTT failures must NOT block API responses. This requires asynchronous or best-effort publishing with error logging.
4. **Optional MQTT:** If `MQTT_URL` is not configured, the service must silently skip publishing (no errors).
5. **No delete notifications:** The change brief explicitly states config deletions should NOT publish MQTT notifications.
6. **Thread safety:** The MQTT client's network loop runs in a background thread. Connection state must be managed safely.

### Resolved Conflicts

**Singleton vs Request-Scoped:** MQTT service must be a singleton (persistent connection requirement) even though it's called from request handlers. This follows the `MetricsService` pattern already in use.

**Async Publishing:** MQTT publishing must not block API responses. The `paho-mqtt` library supports both synchronous and asynchronous publishing via `publish()` which returns immediately when QoS > 0. The library's background thread handles actual transmission.

**Graceful Shutdown:** MQTT connections should disconnect cleanly during application shutdown to avoid leaving stale sessions on the broker. The service will register a `shutdown()` method with Python's `atexit` module to ensure cleanup on process termination.

## 1) Intent & Scope

### User intent

Implement MQTT publish notifications when configuration files are saved or firmware assets are uploaded, enabling IoT devices to receive immediate update notifications via MQTT subscriptions and pull updated files via HTTP. Devices avoid polling by subscribing to topics.

### Prompt quotes

"publish a notification to `iotsupport/updates/configs` with payload `{"filename": "<mac-address>.json"}`"

"publish a notification to `iotsupport/updates/assets` with payload `{"filename": "<asset-filename>"}`"

"Config deletions should NOT publish MQTT notifications"

"Persistent connection as singleton service, reconnects on disconnect"

"If MQTT is not configured (no `MQTT_URL`), skip publishing silently"

"Fire-and-forget - if MQTT publish fails, log the error but let the API operation succeed"

"QoS 1 (at least once delivery)"

"Do not retain messages"

### In scope

- New `MqttService` singleton with persistent MQTT v5 connection
- Environment variables: `MQTT_URL`, `MQTT_USERNAME`, `MQTT_PASSWORD`
- Publish to `iotsupport/updates/configs` on config save (create or update)
- Publish to `iotsupport/updates/assets` on asset upload success
- No publishing on config delete operations
- QoS 1, no retain flag, topics without leading slash
- Fire-and-forget publishing with error logging
- Silent skip when MQTT not configured
- Prometheus metrics for MQTT operations (publish attempts, failures, connection state)
- Comprehensive service tests (mocking MQTT client)
- API integration tests (verifying publish calls occur at correct times)

### Out of scope

- MQTT subscriptions (devices handle subscriptions separately)
- Message retention or persistence beyond QoS 1
- Custom reconnection logic (rely on `paho-mqtt` automatic reconnection)
- Authentication methods beyond username/password
- TLS/SSL configuration (assume broker URL handles this via `mqtts://` scheme)
- Message delivery confirmation or retry logic beyond library defaults

### Assumptions / constraints

- `paho-mqtt` library will be added as a dependency
- MQTT broker (Mosquitto v5) is externally managed and available at `MQTT_URL`
- Configuration and asset operations remain synchronous (MQTT publish doesn't block)
- Existing API endpoints (`save_config`, `upload_asset`) succeed/fail independently of MQTT
- The application runs single-process (no multi-process concerns for singleton)
- MQTT client thread safety is handled by `paho-mqtt` library
- Environment variables are read at application startup and not changed dynamically

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Publish config save notifications to `iotsupport/updates/configs` topic with payload `{"filename": "<mac-address>.json"}`
- [ ] Publish asset upload notifications to `iotsupport/updates/assets` topic with payload `{"filename": "<asset-filename>"}`
- [ ] Do NOT publish notifications on config delete operations
- [ ] Read MQTT settings from environment variables: MQTT_URL, MQTT_USERNAME, MQTT_PASSWORD
- [ ] Support Mosquitto MQTT 5 server
- [ ] Use persistent connection as singleton service with automatic reconnection
- [ ] Make MQTT optional - skip publishing silently if MQTT_URL is not configured
- [ ] Use QoS 1 (at least once delivery)
- [ ] Do not use retain flag on published messages
- [ ] Use topic format without leading slash (iotsupport/updates/configs, iotsupport/updates/assets)
- [ ] Fire-and-forget on publish failure - log error but let API operation succeed
- [ ] Add comprehensive tests for the MQTT service

## 2) Affected Areas & File Map (with repository evidence)

- Area: `app/config.py`
- Why: Add MQTT configuration fields (URL, username, password)
- Evidence: `app/config.py:13-48` — `Settings` class with environment variable loading via `pydantic_settings`

---

- Area: `app/services/mqtt_service.py` (new file)
- Why: Create singleton service managing MQTT connection and publishing
- Evidence: `app/services/metrics_service.py:10-20` — Singleton service pattern with `__init__` and instance variables

---

- Area: `app/services/container.py`
- Why: Register `MqttService` as singleton provider and wire dependencies
- Evidence: `app/services/container.py:12-39` — `ServiceContainer` class with singleton and factory providers

---

- Area: `app/api/configs.py`
- Why: Inject `MqttService` and publish notification after successful `save_config`
- Evidence: `app/api/configs.py:103-149` — `save_config` endpoint with service injection pattern

---

- Area: `app/api/assets.py`
- Why: Inject `MqttService` and publish notification after successful asset upload
- Evidence: `app/api/assets.py:25-150` — `upload_asset` endpoint with service injection pattern

---

- Area: `app/services/mqtt_service.py` (metrics section)
- Why: Define MQTT-specific Prometheus metrics (publish attempts, failures, connection state) directly in MqttService using prometheus_client, following the pattern where each service owns its domain metrics
- Evidence: `app/services/metrics_service.py:29-43` — Pattern for Counter/Gauge/Histogram definitions; metrics are defined where they are used

---

- Area: `app/__init__.py`
- Why: Wire MQTT service to API modules in container wiring list
- Evidence: `app/__init__.py:36-44` — Container wiring with API module list

---

- Area: `pyproject.toml`
- Why: Add `paho-mqtt` dependency
- Evidence: `pyproject.toml:12-26` — Poetry dependencies section

---

- Area: `tests/services/test_mqtt_service.py` (new file)
- Why: Create comprehensive unit tests for MQTT service (connection, publish, error handling)
- Evidence: `tests/services/test_config_service.py:1-14` — Test structure pattern with pytest and service instantiation

---

- Area: `tests/api/test_configs.py` (modify existing or create)
- Why: Add integration tests verifying MQTT publish is called on config save
- Evidence: `tests/conftest.py:79-95` — Test fixtures for app and container

---

- Area: `tests/api/test_assets.py` (modify existing or create)
- Why: Add integration tests verifying MQTT publish is called on asset upload
- Evidence: `tests/conftest.py:79-95` — Test fixtures for app and container

---

- Area: `tests/conftest.py`
- Why: Add MQTT test fixtures (mock client, optional MQTT URL settings)
- Evidence: `tests/conftest.py:52-76` — `test_settings` fixture with Settings instantiation

## 3) Data Model / Contracts

- Entity / contract: MQTT configuration settings
- Shape:
  ```python
  MQTT_URL: str | None = Field(default=None, description="MQTT broker URL (e.g., mqtt://localhost:1883, mqtts://broker:8883)")
  MQTT_USERNAME: str | None = Field(default=None, description="MQTT broker username")
  MQTT_PASSWORD: str | None = Field(default=None, description="MQTT broker password")
  ```
- Refactor strategy: These are new optional fields with `None` defaults, so no backwards compatibility concerns. Existing deployments without MQTT simply leave these unset.
- Evidence: `app/config.py:14-48` — Settings class structure

---

- Entity / contract: MQTT notification message payload
- Shape:
  ```json
  {
    "filename": "aa-bb-cc-dd-ee-ff.json"
  }
  ```
  or
  ```json
  {
    "filename": "firmware-v1.2.3.bin"
  }
  ```
- Refactor strategy: New message format with single `filename` field. Devices subscribe and parse this simple structure.
- Evidence: Change brief lines 9, 12 — Payload specification

---

- Entity / contract: MQTT topics
- Shape:
  - Config saves: `iotsupport/updates/configs`
  - Asset uploads: `iotsupport/updates/assets`
- Refactor strategy: Topics are hardcoded constants in `MqttService`. No versioning or backwards compatibility needed (new feature).
- Evidence: Change brief lines 9, 12 — Topic specification

## 4) API / Integration Surface

- Surface: MQTT publish to `iotsupport/updates/configs`
- Inputs: Filename (MAC address + `.json` extension)
- Outputs: MQTT message published with QoS 1, no retain. No return value (fire-and-forget).
- Errors: Publish failures logged but do not propagate to caller. Connection failures trigger reconnection via `paho-mqtt` auto-reconnect.
- Evidence: `app/api/configs.py:103-149` — `save_config` endpoint is the trigger point

---

- Surface: MQTT publish to `iotsupport/updates/assets`
- Inputs: Filename (asset filename from upload)
- Outputs: MQTT message published with QoS 1, no retain. No return value (fire-and-forget).
- Errors: Publish failures logged but do not propagate to caller. Connection failures trigger reconnection via `paho-mqtt` auto-reconnect.
- Evidence: `app/api/assets.py:25-150` — `upload_asset` endpoint is the trigger point

---

- Surface: No MQTT publish on config delete
- Inputs: N/A
- Outputs: N/A
- Errors: N/A
- Evidence: Change brief line 13 — "Config deletions should NOT publish MQTT notifications"

## 5) Algorithms & State Machines (step-by-step)

- Flow: MQTT Service Initialization
- Steps:
  1. Read `MQTT_URL`, `MQTT_USERNAME`, `MQTT_PASSWORD` from Settings
  2. If `MQTT_URL` is None or empty, set `enabled=False` and return (no connection attempted)
  3. Create `paho.mqtt.client.Client` instance with MQTT v5 protocol
  4. Set `username_pw_set()` if username/password provided
  5. Register `on_connect`, `on_disconnect`, `on_publish` callbacks for logging and metrics
  6. Initialize Prometheus metrics (Counter, Gauge, Histogram)
  7. Call `connect_async()` to initiate connection in background
  8. Call `loop_start()` to start background network thread
  9. Register `shutdown()` method with `atexit` for graceful cleanup
  10. Mark `enabled=True` to allow publishing
- States / transitions: Connection state managed by `paho-mqtt` library (disconnected → connecting → connected). Service tracks `enabled` boolean only.
- Hotspots: Connection establishment is asynchronous; initial publishes may fail if connection not yet established (QoS 1 ensures delivery once connected)
- Evidence: `app/services/metrics_service.py:18-20` — Singleton `__init__` pattern

---

- Flow: Publish Notification
- Steps:
  1. Check if MQTT service is enabled (`self.enabled`)
  2. If disabled, return immediately (silent skip)
  3. Construct JSON payload: `{"filename": "<filename>"}`
  4. Call `self.client.publish(topic, payload, qos=1, retain=False)`
  5. Capture `MQTTMessageInfo` result from publish
  6. If result indicates error, log warning and increment failure metric
  7. Otherwise increment success metric
  8. Return (do not wait for publish confirmation)
- States / transitions: None (stateless publish operation)
- Hotspots: `publish()` is non-blocking; actual transmission handled by background thread
- Evidence: Change brief lines 24-25 — Fire-and-forget with error logging

---

- Flow: Config Save with MQTT Notification
- Steps:
  1. API receives PUT request to `/configs/<mac_address>`
  2. Validate request schema
  3. Call `config_service.save_config()`
  4. If save succeeds, construct filename: `{mac_address}.json`
  5. Call `mqtt_service.publish_config_update(filename)`
  6. Update metrics (existing pattern)
  7. Return success response
- States / transitions: None (synchronous API flow with async MQTT publish)
- Hotspots: MQTT publish must not throw exceptions that abort API response
- Evidence: `app/api/configs.py:114-149` — Existing save_config flow

---

- Flow: Asset Upload with MQTT Notification
- Steps:
  1. API receives POST request to `/assets`
  2. Validate multipart form data
  3. Call `asset_upload_service.upload_asset()`
  4. If upload succeeds, extract filename from result
  5. Call `mqtt_service.publish_asset_update(filename)`
  6. Record metrics (existing pattern)
  7. Return success response
- States / transitions: None (synchronous API flow with async MQTT publish)
- Hotspots: MQTT publish must not throw exceptions that abort API response
- Evidence: `app/api/assets.py:88-122` — Existing upload flow

## 6) Derived State & Invariants (stacked bullets)

- Derived value: MQTT enabled state
  - Source: Unfiltered input from `Settings.MQTT_URL` (environment variable)
  - Writes / cleanup: No persistent writes; only affects in-memory `enabled` flag and whether connection is established
  - Guards: If `MQTT_URL` is None or empty string, `enabled` remains False and no connection is attempted
  - Invariant: When `enabled=False`, all publish calls must return immediately without attempting MQTT operations
  - Evidence: Change brief line 20 — "If MQTT is not configured, skip publishing silently"

---

- Derived value: MQTT connection state
  - Source: Unfiltered MQTT broker availability (external service)
  - Writes / cleanup: `paho-mqtt` library manages connection state and automatic reconnection. No application-level writes or cleanup triggered by connection state changes.
  - Guards: Publish operations use QoS 1, which queues messages during disconnect and sends when reconnected. Fire-and-forget semantics mean failures are logged but do not retry.
  - Invariant: Connection state changes (disconnect/reconnect) must not cause exceptions in publish callers
  - Evidence: Change brief line 19 — "reconnects on disconnect"

---

- Derived value: MQTT publish success/failure metrics
  - Source: Filtered view of publish results (success vs various failure modes)
  - Writes / cleanup: Increments Prometheus counters for `mqtt_publish_total` with labels `{topic, status}`. No cleanup; counters are monotonic.
  - Guards: Publish method catches all exceptions from `client.publish()` and increments failure counter. No exceptions propagate to API layer.
  - Invariant: Every call to `publish_config_update()` or `publish_asset_update()` must increment exactly one metric (success or failure)
  - Evidence: `app/services/metrics_service.py:91-111` — Pattern for recording operations

## 7) Consistency, Transactions & Concurrency

- Transaction scope: N/A — No database transactions involved. File writes in `ConfigService` and `AssetUploadService` use atomic rename (temp file + `os.replace`).
- Atomic requirements: MQTT publish is decoupled from file write. File write succeeds or fails independently. MQTT publish is best-effort after successful write.
- Retry / idempotency: QoS 1 provides at-least-once delivery within MQTT protocol (library handles retries). No application-level retry. Devices receiving duplicate notifications should be idempotent (re-fetching config is safe).
- Ordering / concurrency controls: No ordering guarantees across topics. Within a topic, messages are published in API call order, but network conditions may reorder delivery. No locks needed; `paho-mqtt` client is thread-safe for publish calls.
- Evidence: `app/services/config_service.py:228-248` — Atomic file write pattern; Change brief line 22 — QoS 1

## 8) Errors & Edge Cases

- Failure: MQTT broker unreachable during service initialization
- Surface: `MqttService.__init__` at application startup
- Handling: Connection attempt is asynchronous (`connect_async()`). Service initialization succeeds, but publishes fail until connection established. Metrics increment failure counts. API operations succeed.
- Guardrails: Monitor `mqtt_connection_state` gauge (0=disconnected, 1=connected) to detect prolonged outages.
- Evidence: Change brief line 24 — "Fire-and-forget - log error but let API operation succeed"

---

- Failure: MQTT credentials invalid
- Surface: `MqttService` connection callbacks
- Handling: `on_connect` callback receives connection failure reason code. Log error, increment connection failure metric, set `enabled=False` to prevent publish attempts.
- Guardrails: Monitor connection failure metrics. Document that invalid credentials disable MQTT without affecting API functionality.
- Evidence: `paho-mqtt` documentation — Connection result codes

---

- Failure: `client.publish()` raises exception (e.g., message too large, client not connected)
- Surface: `MqttService.publish_config_update()` or `publish_asset_update()`
- Handling: Wrap `publish()` in try/except. Log exception with full context (topic, filename). Increment failure metric. Return normally (do not re-raise).
- Guardrails: Alert on high failure rates. Document max message size (MQTT broker config, typically 256MB default).
- Evidence: Change brief line 24 — "log error but let API operation succeed"

---

- Failure: MQTT_URL is malformed (e.g., `http://` instead of `mqtt://`)
- Surface: `MqttService.__init__` when parsing URL
- Handling: `paho-mqtt` client expects URL parsing to extract host/port. If parsing fails, connection fails. Service logs error and sets `enabled=False`.
- Guardrails: Validate MQTT_URL format in Settings (pydantic validator). Fail fast at startup if invalid.
- Evidence: `app/config.py:6-20` — Pydantic settings validation

---

- Failure: Config save succeeds but MQTT publish fails (partial success)
- Surface: `app/api/configs.py` `save_config` endpoint
- Handling: File is written successfully. MQTT publish fails and logs error. API returns 200 success (file write is source of truth). Device may miss notification but can poll or receive notification on next config change.
- Guardrails: Document that notifications are best-effort. Devices should implement polling fallback or retry logic.
- Evidence: Change brief line 24 — "let API operation succeed"

---

- Failure: MQTT_URL is None (optional MQTT not configured)
- Surface: `MqttService.__init__`
- Handling: Set `enabled=False`. All publish calls return immediately without logging errors (silent skip).
- Guardrails: Document that MQTT is optional. Monitor `mqtt_enabled` gauge to detect if MQTT is active.
- Evidence: Change brief line 20 — "If MQTT is not configured, skip publishing silently"

## 9) Observability / Telemetry

- Signal: `mqtt_publish_total`
- Type: Counter
- Trigger: Incremented on every publish attempt (success or failure) from `MqttService.publish_config_update()` or `publish_asset_update()`
- Labels / fields: `{topic: "iotsupport/updates/configs" | "iotsupport/updates/assets", status: "success" | "failure"}`
- Consumer: Prometheus dashboard to track publish rates and failure rates per topic
- Evidence: `app/services/metrics_service.py:29-43` — Counter definition pattern

---

- Signal: `mqtt_connection_state`
- Type: Gauge
- Trigger: Updated on connection state changes via `on_connect` and `on_disconnect` callbacks
- Labels / fields: None (single gauge, 0=disconnected, 1=connected)
- Consumer: Alert if disconnected for >5 minutes
- Evidence: `app/services/metrics_service.py:35-37` — Gauge definition pattern

---

- Signal: `mqtt_publish_duration_seconds`
- Type: Histogram
- Trigger: Observed for every publish call (measures time from `publish()` call to return, not end-to-end delivery)
- Labels / fields: `{topic}`
- Consumer: Dashboard to monitor publish latency (should be <10ms for local call)
- Evidence: `app/services/metrics_service.py:39-43` — Histogram definition pattern

---

- Signal: `mqtt_enabled`
- Type: Gauge
- Trigger: Set once during service initialization
- Labels / fields: None (0=disabled, 1=enabled)
- Consumer: Dashboard to verify MQTT is configured and active
- Evidence: New metric, follows existing gauge pattern

---

- Signal: Structured log messages
- Type: Structured log
- Trigger: On connection events (`on_connect`, `on_disconnect`), publish failures, and initialization
- Labels / fields: `{level: INFO/WARNING/ERROR, message, topic, filename, error}`
- Consumer: Log aggregation for debugging MQTT issues
- Evidence: `app/services/config_service.py:17` — Logger usage pattern

## 10) Background Work & Shutdown

- Worker / job: MQTT client network loop thread
- Trigger cadence: Started at service initialization via `client.loop_start()`, runs continuously
- Responsibilities: Handle incoming messages (none expected), process outgoing publish queue, maintain connection, trigger reconnection
- Shutdown handling: MqttService provides a `shutdown()` method that calls `client.loop_stop()` and `client.disconnect()` for graceful cleanup. This method is registered with Python's `atexit` module during initialization to ensure cleanup on process termination. The shutdown sequence: (1) stop accepting new publishes, (2) stop network loop thread, (3) disconnect from broker.
- Evidence: `paho-mqtt` documentation — `loop_start()` and `loop_stop()` methods; Python `atexit` module for cleanup hooks

## 11) Security & Permissions (if applicable)

- Concern: MQTT credentials exposure
- Touchpoints: `Settings` class reads `MQTT_USERNAME` and `MQTT_PASSWORD` from environment variables
- Mitigation: Environment variables are not logged. Credentials are passed directly to `client.username_pw_set()` without intermediate storage. Prometheus metrics do not expose credentials.
- Residual risk: Environment variables visible in process listings (`ps aux`). Acceptable for trusted homelab environment. Document that credentials should be managed securely (e.g., Kubernetes secrets).
- Evidence: `app/config.py:13-48` — Settings with environment variable loading

---

- Concern: MQTT message injection
- Touchpoints: `MqttService` constructs JSON payloads from filenames
- Mitigation: Filenames are already validated by `ConfigService` (MAC address regex) and `AssetUploadService` (path traversal checks). JSON payload construction uses safe `json.dumps()` without user-controlled keys.
- Residual risk: None. Filenames are controlled inputs, not arbitrary user strings.
- Evidence: `app/services/config_service.py:19-20` — MAC address validation; `app/services/asset_upload_service.py:80-103` — Filename validation

## 12) UX / UI Impact (if applicable)

Not applicable. This is a backend-only feature. Devices (ESP32 IoT devices) subscribe to MQTT topics and receive notifications, but no frontend UI changes are required.

## 13) Deterministic Test Plan (new/changed behavior only)

- Surface: `MqttService` initialization
- Scenarios:
  - Given MQTT_URL is set, When service initializes, Then connection is attempted and enabled=True
  - Given MQTT_URL is None, When service initializes, Then no connection attempted and enabled=False
  - Given MQTT_URL is empty string, When service initializes, Then no connection attempted and enabled=False
  - Given MQTT credentials are provided, When service initializes, Then credentials are set on client
  - Given MQTT enabled, When service initializes, Then shutdown handler registered with atexit
- Fixtures / hooks: Mock `paho.mqtt.client.Client` to verify `connect_async()`, `loop_start()`, `username_pw_set()` calls. Mock `atexit.register` to verify shutdown registration. Use pytest `monkeypatch` for environment variables.
- Gaps: None
- Evidence: `tests/services/test_config_service.py:17-24` — Service initialization test pattern

---

- Surface: `MqttService.shutdown()`
- Scenarios:
  - Given MQTT enabled and client connected, When shutdown called, Then loop_stop() and disconnect() called in order
  - Given MQTT disabled, When shutdown called, Then no client methods called (no-op)
  - Given shutdown already called, When shutdown called again, Then no exception raised (idempotent)
- Fixtures / hooks: Mock MQTT client, spy on `loop_stop()` and `disconnect()` calls
- Gaps: None
- Evidence: New test file `tests/services/test_mqtt_service.py`

---

- Surface: `MqttService.publish_config_update()`
- Scenarios:
  - Given MQTT enabled and client connected, When publish_config_update called, Then client.publish() called with correct topic, payload, qos=1, retain=False
  - Given MQTT disabled, When publish_config_update called, Then client.publish() NOT called (silent skip)
  - Given client.publish() succeeds, When publish_config_update called, Then success metric incremented
  - Given client.publish() raises exception, When publish_config_update called, Then exception logged, failure metric incremented, no exception propagated
  - Given payload contains special characters, When publish_config_update called, Then JSON payload is correctly escaped
- Fixtures / hooks: Mock MQTT client, spy on `publish()` calls, assert call arguments
- Gaps: None
- Evidence: New test file `tests/services/test_mqtt_service.py`

---

- Surface: `MqttService.publish_asset_update()`
- Scenarios:
  - Given MQTT enabled, When publish_asset_update called, Then client.publish() called with iotsupport/updates/assets topic
  - Given MQTT disabled, When publish_asset_update called, Then client.publish() NOT called
  - Given filename with spaces, When publish_asset_update called, Then payload is valid JSON
- Fixtures / hooks: Same as publish_config_update tests
- Gaps: None
- Evidence: New test file `tests/services/test_mqtt_service.py`

---

- Surface: API endpoint `/configs/<mac_address>` (PUT) with MQTT
- Scenarios:
  - Given MQTT enabled, When config saved successfully, Then mqtt_service.publish_config_update called with "{mac}.json"
  - Given MQTT disabled, When config saved successfully, Then no MQTT publish attempted
  - Given MQTT publish fails, When config saved, Then API returns 200 (success) and error logged
  - Given config save fails, When endpoint called, Then no MQTT publish attempted
- Fixtures / hooks: Use `container` fixture to inject mock `MqttService`, spy on publish calls
- Gaps: None
- Evidence: `tests/conftest.py:93-95` — Container fixture for DI testing

---

- Surface: API endpoint `/assets` (POST) with MQTT
- Scenarios:
  - Given MQTT enabled, When asset uploaded successfully, Then mqtt_service.publish_asset_update called with filename
  - Given MQTT disabled, When asset uploaded, Then no MQTT publish attempted
  - Given MQTT publish fails, When asset uploaded, Then API returns 200 and error logged
  - Given upload validation fails, When endpoint called, Then no MQTT publish attempted
- Fixtures / hooks: Use `container` fixture, mock MQTT service
- Gaps: None
- Evidence: New or modified `tests/api/test_assets.py`

---

- Surface: MQTT metrics (Prometheus)
- Scenarios:
  - Given multiple publishes, When metrics scraped, Then publish_total counter incremented correctly per topic
  - Given connection state changes, When metrics scraped, Then connection_state gauge reflects current state
  - Given MQTT disabled, When metrics scraped, Then mqtt_enabled gauge = 0
- Fixtures / hooks: Access `metrics_service` from container, call `get_metrics_text()`, parse output
- Gaps: None
- Evidence: `app/services/metrics_service.py:206-212` — `get_metrics_text()` method

---

- Surface: Config delete operation (negative test)
- Scenarios:
  - Given MQTT enabled, When config deleted, Then mqtt_service.publish_config_update NOT called
- Fixtures / hooks: Spy on MqttService to verify no publish calls
- Gaps: None
- Evidence: Change brief line 13 — Explicit requirement to NOT publish on delete

## 14) Implementation Slices (only if large)

This feature is small enough to implement in a single slice. The following order is recommended for incremental development:

- Slice: MQTT service foundation
- Goal: Add dependency, create service skeleton, wire into container
- Touches: `pyproject.toml`, `app/services/mqtt_service.py`, `app/services/container.py`, `app/config.py`
- Dependencies: None

---

- Slice: MQTT metrics and observability
- Goal: Add Prometheus metrics for MQTT operations (defined within MqttService)
- Touches: `app/services/mqtt_service.py` (metrics defined inline)
- Dependencies: MQTT service skeleton exists

---

- Slice: Config save integration
- Goal: Publish notifications on config save
- Touches: `app/api/configs.py`, `tests/services/test_mqtt_service.py`, `tests/api/test_configs.py`
- Dependencies: MQTT service and metrics complete

---

- Slice: Asset upload integration
- Goal: Publish notifications on asset upload
- Touches: `app/api/assets.py`, `tests/api/test_assets.py`
- Dependencies: Config save integration complete (same pattern)

## 15) Risks & Open Questions

- Risk: MQTT client thread interferes with application shutdown
- Impact: Unclean disconnect, orphaned connections on broker
- Mitigation: MqttService registers its `shutdown()` method with Python's `atexit` module. This ensures `loop_stop()` and `disconnect()` are called during normal process termination, providing graceful cleanup.

---

- Risk: QoS 1 message queue grows unbounded during prolonged disconnect
- Impact: Memory exhaustion if thousands of messages queued
- Mitigation: `paho-mqtt` library has internal queue limits (default 1000 messages). Document that prolonged outages may drop messages. Monitor connection state.

---

- Risk: Flaky tests due to MQTT client background thread
- Impact: Test suite instability, difficult to debug
- Mitigation: Mock `paho.mqtt.client.Client` completely in tests. Never instantiate real client in test suite.

---

- Risk: MQTT broker performance bottleneck
- Impact: Slow publish operations delay API responses
- Mitigation: Publish is non-blocking. `paho-mqtt` background thread handles transmission. Monitor `mqtt_publish_duration_seconds` metric to detect anomalies.

---

- Risk: Device receives duplicate notifications (QoS 1 at-least-once)
- Impact: Devices fetch config multiple times unnecessarily
- Mitigation: Document that devices must implement idempotent handling (re-fetching config is safe operation).

## 16) Confidence (one line)

Confidence: High — This is a straightforward integration using a mature MQTT library with well-defined fire-and-forget semantics, simple payloads, and no complex state management. The singleton pattern matches existing `MetricsService`, and the testing approach (mocking MQTT client) is proven.
