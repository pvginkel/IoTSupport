# Plan: MQTT Log Sink

## 0) Research Log & Findings

### Areas Researched

1. **Existing MQTT Infrastructure** (`app/services/mqtt_service.py:1-290`)
   - Current MqttService is a singleton focused on publishing notifications
   - Uses paho-mqtt v5 with async connection and fire-and-forget publishing
   - Integrates with Prometheus metrics for observability
   - Uses atexit for shutdown handling (no formal ShutdownCoordinator yet)
   - Parses MQTT URLs with mqtt:// and mqtts:// schemes

2. **Elasticsearch Integration** (`app/services/elasticsearch_service.py:1-361`)
   - Existing ElasticsearchService uses httpx for HTTP requests
   - Has authentication support via HTTP Basic Auth
   - Uses `config.elasticsearch_url` and credentials from Settings
   - Writes to index pattern specified in config (default: `logstash-http-*`)

3. **Configuration System** (`app/config.py:1-551`)
   - Pydantic-based Settings with Environment loader
   - Elasticsearch settings exist: `elasticsearch_url`, `elasticsearch_username`, `elasticsearch_password`, `elasticsearch_index_pattern`
   - MQTT settings exist: `mqtt_url`, `mqtt_username`, `mqtt_password`

4. **Service Container** (`app/services/container.py:1-129`)
   - MqttService is a Singleton provider
   - ElasticsearchService is a Singleton provider
   - Services receive dependencies via constructor injection

5. **Metrics Infrastructure** (`app/services/metrics_service.py:1-223`)
   - MetricsService provides Counter, Gauge, Histogram registration
   - Generic `increment_counter` and `record_operation_duration` methods

6. **Graceful Shutdown** (`AGENTS.md:389-442`)
   - Documentation describes ShutdownCoordinator pattern but it is not yet implemented
   - Current MqttService uses simple atexit handler for cleanup

### Key Findings

- The log sink requires a new service since it has a fundamentally different responsibility than the existing MqttService (subscribe vs publish)
- ANSI escape code stripping will need a utility function (regex pattern `\x1b\[[0-9;]*m`)
- Elasticsearch write operations need httpx POST to `/{index}/_doc` endpoint
- The index pattern `logstash-http-YYYY.MM.dd` requires date formatting at write time

### Conflicts Resolved

- **Shutdown Coordination**: Since ShutdownCoordinator is not implemented, the plan includes implementing a `threading.Event`-based shutdown pattern that allows immediate interruption of backoff waits. This improves on MqttService's simple `_shutdown_called` flag by using `Event.wait(timeout)` instead of `time.sleep()`, enabling responsive shutdown during retry backoff.
- **Singleton vs Factory**: LogSinkService should be a Singleton because it maintains a persistent MQTT subscription and background thread
- **Startup Initialization**: Unlike other singletons that are lazy-initialized on first use, LogSinkService must be explicitly initialized at app startup to establish the MQTT subscription. This requires adding explicit startup code to `app/__init__.py`.
- **Enablement Logic**: The service requires BOTH MQTT and Elasticsearch to be configured. If either is missing, the service will be disabled (no partial functionality).

---

## 1) Intent & Scope

**User intent**

Add an MQTT-based log sink service that subscribes to device log messages, processes them (strips ANSI codes, adds timestamp), and writes them to Elasticsearch, replacing the external Logstash HTTP ingestion pipeline.

**Prompt quotes**

- "Subscribe to MQTT topic `iotsupport/logsink`"
- "Strip ANSI escape codes from the `message` field"
- "Use current timestamp as `@timestamp`"
- "Write to Elasticsearch with index pattern `logstash-http-YYYY.MM.dd`"
- "Retry Elasticsearch writes indefinitely with exponential backoff (1s initial, +1s per retry, max 60s)"
- "Use persistent sessions with configurable client ID"
- "Integrate with graceful shutdown coordinator"

**In scope**

- New `LogSinkService` singleton that subscribes to MQTT and writes to Elasticsearch
- ANSI escape code stripping utility
- Elasticsearch document indexing with date-based index names
- Exponential backoff retry logic for ES writes
- Prometheus metrics for observability
- Graceful shutdown integration using shutdown flag pattern
- Configuration for client ID via environment variable

**Out of scope**

- Batching/bulk writes to Elasticsearch
- Exactly-once delivery guarantees
- Changes to existing ElasticsearchService (read-only, for querying)
- Formal ShutdownCoordinator implementation (use simple flag pattern)

**Assumptions / constraints**

- Elasticsearch is reachable from the application at configured URL
- MQTT broker supports persistent sessions and QoS 1
- Device payloads are JSON with at least a `message` field
- At most one message may be lost on crash (QoS 1 semantics)
- The service runs within the Flask application lifecycle

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Subscribe to MQTT topic `iotsupport/logsink`
- [ ] Use persistent sessions with configurable client ID (env var, default: `iotsupport-logsink`)
- [ ] Strip ANSI escape codes from the `message` field
- [ ] Use current timestamp as `@timestamp` (ignore any `relative_time` field in payload)
- [ ] Write to Elasticsearch with index pattern `logstash-http-YYYY.MM.dd`
- [ ] Process messages one at a time (no batching)
- [ ] Use QoS 1 for subscription
- [ ] Retry Elasticsearch writes indefinitely with exponential backoff (1s initial, +1s per retry, max 60s)
- [ ] Integrate with graceful shutdown coordinator
- [ ] Add Prometheus metrics for observability

---

## 2) Affected Areas & File Map

- Area: `app/config.py` - Environment and Settings classes
- Why: Add `LOGSINK_CLIENT_ID` environment variable with default `iotsupport-logsink`
- Evidence: `app/config.py:88-103` - existing MQTT settings pattern

- Area: `app/services/logsink_service.py` (new file)
- Why: New singleton service implementing MQTT subscription, message processing, and ES writes
- Evidence: `app/services/mqtt_service.py:17-28` - similar singleton service pattern

- Area: `app/services/container.py`
- Why: Register LogSinkService as Singleton provider with dependencies
- Evidence: `app/services/container.py:38-44` - MqttService singleton pattern

- Area: `app/services/metrics_service.py`
- Why: Add Prometheus metrics for log sink operations (messages received, ES writes, retries)
- Evidence: `app/services/metrics_service.py:97-108` - Elasticsearch metrics pattern

- Area: `app/__init__.py`
- Why: Initialize LogSinkService singleton on app startup (when enabled). Unlike other singletons that are lazy-initialized, LogSinkService must be explicitly started to establish the MQTT subscription.
- Evidence: `app/__init__.py:57-79` - container initialization pattern
- Implementation note: Add explicit initialization after container wiring:
  ```python
  # Initialize background services (after container.wire())
  if not skip_background_services:
      # Start log sink if both MQTT and ES are configured
      logsink = container.logsink_service()
      if logsink.enabled:
          logger.info("LogSinkService started - subscribed to MQTT log topic")
  ```

- Area: `app/utils/ansi.py` (new file)
- Why: Utility function to strip ANSI escape codes from strings
- Evidence: New utility following `app/utils/` pattern

- Area: `tests/services/test_logsink_service.py` (new file)
- Why: Comprehensive tests for LogSinkService
- Evidence: `tests/services/test_mqtt_service.py:1-463` - similar service test pattern

- Area: `tests/utils/test_ansi.py` (new file)
- Why: Unit tests for ANSI stripping utility
- Evidence: `tests/utils/test_nvs_generator.py` - utility test pattern

---

## 3) Data Model / Contracts

- Entity / contract: MQTT Log Message (input)
- Shape:
  ```json
  {
    "message": "string (may contain ANSI escape codes)",
    "entity_id": "string (device identifier)",
    "relative_time": "ignored",
    "...": "other fields passed through"
  }
  ```
- Refactor strategy: No back-compat needed; new service consumes existing device payload format
- Evidence: `docs/features/mqtt_logsink/change_brief.md:13-17` - payload format

- Entity / contract: Elasticsearch Document (output)
- Shape:
  ```json
  {
    "@timestamp": "2026-02-02T10:30:00.123456Z",
    "message": "string (ANSI codes stripped)",
    "entity_id": "string",
    "...": "other fields from payload"
  }
  ```
- Refactor strategy: Matches existing Logstash output format; no changes to downstream consumers
- Evidence: `docs/features/mqtt_logsink/change_brief.md:17` - index pattern `logstash-http-YYYY.MM.dd`

- Entity / contract: Configuration (Settings)
- Shape:
  ```python
  logsink_client_id: str  # default: "iotsupport-logsink"
  # Note: Service is enabled only when BOTH mqtt_url AND elasticsearch_url are configured
  # No explicit logsink_enabled setting; enablement is derived from dependency availability
  ```
- Refactor strategy: New fields with sensible defaults; existing deployments work unchanged
- Evidence: `app/config.py:263-266` - mqtt_url pattern for optional services

---

## 4) API / Integration Surface

- Surface: MQTT Subscription `iotsupport/logsink`
- Inputs: JSON payloads from devices (message, entity_id, optional fields)
- Outputs: None (fire-and-forget from publisher perspective)
- Errors: Invalid JSON logged and skipped; processing errors logged
- Evidence: `docs/features/mqtt_logsink/change_brief.md:13` - topic specification

- Surface: Elasticsearch Index `POST /{index}/_doc`
- Inputs: Processed log document with @timestamp and cleaned message
- Outputs: Document ID on success
- Errors: Connection errors trigger exponential backoff retry; never gives up
- Evidence: `app/services/elasticsearch_service.py:202-244` - ES HTTP client pattern

---

## 5) Algorithms & State Machines

- Flow: Log Message Processing Pipeline
- Steps:
  1. Receive MQTT message from `iotsupport/logsink` topic
  2. Parse JSON payload; skip if invalid JSON (log warning)
  3. Extract `message` field; strip ANSI escape codes
  4. Generate current UTC timestamp as `@timestamp`
  5. Remove `relative_time` field if present
  6. Compute target index name: `logstash-http-{YYYY.MM.dd}` using current date
  7. Attempt Elasticsearch POST to `/{index}/_doc`
  8. If ES write fails, enter retry loop with exponential backoff
  9. Acknowledge MQTT message only after successful ES write
- States / transitions: None (stateless pipeline per message)
- Hotspots: ES write latency under backoff could cause message buildup; QoS 1 provides broker-side buffering
- Evidence: `docs/features/mqtt_logsink/change_brief.md:23-24` - retry specification

- Flow: Exponential Backoff Retry
- Steps:
  1. Set delay = 1 second
  2. Wait for delay duration using `threading.Event.wait(timeout=delay)` for interruptible sleep
  3. If shutdown event was set during wait, exit loop immediately (message may be lost)
  4. Retry ES write
  5. If success, exit loop and reset delay gauge to 0
  6. If failure and not shutting down, increment delay by 1 second (max 60s)
  7. Go to step 2
- States / transitions: retry_delay: 1s -> 2s -> 3s -> ... -> 60s (capped)
- Hotspots: Long retry loops during ES outage; `threading.Event` allows immediate wakeup on shutdown signal
- Implementation note: Use `threading.Event` instead of `time.sleep()` to allow immediate interruption on shutdown
- Evidence: `docs/features/mqtt_logsink/change_brief.md:24` - "1s initial delay, +1s per retry, max 60s"

---

## 6) Derived State & Invariants

- Derived value: Target Index Name
  - Source: Current UTC date at message processing time
  - Writes / cleanup: Determines which ES index receives the document
  - Guards: None; date computed fresh for each message
  - Invariant: Index name always matches `logstash-http-YYYY.MM.dd` format
  - Evidence: `docs/features/mqtt_logsink/change_brief.md:17`

- Derived value: Cleaned Message
  - Source: Raw message field from MQTT payload
  - Writes / cleanup: Stored in ES document; original message discarded
  - Guards: ANSI regex only removes escape codes; other content preserved
  - Invariant: Output message contains no ANSI escape sequences
  - Evidence: `docs/features/mqtt_logsink/change_brief.md:15`

- Derived value: Document Timestamp
  - Source: `datetime.now(UTC)` at processing time
  - Writes / cleanup: Stored as `@timestamp` in ES document
  - Guards: Any `relative_time` field in payload is ignored/removed
  - Invariant: Timestamp reflects when message was processed, not device time
  - Evidence: `docs/features/mqtt_logsink/change_brief.md:16`

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: Single message processing is atomic from MQTT ack perspective
- Atomic requirements: ES write must succeed before MQTT ack; partial failure results in message redelivery (QoS 1)
- Retry / idempotency: ES documents have auto-generated IDs; duplicate writes on retry create duplicate documents (acceptable for logs)
- Ordering / concurrency controls: Single-threaded message processing (paho callback); no concurrent writes to ES from this service
- Evidence: `docs/features/mqtt_logsink/change_brief.md:23` - "at most one message is lost on crash"

---

## 8) Errors & Edge Cases

- Failure: Invalid JSON payload
- Surface: LogSinkService MQTT callback
- Handling: Log warning with payload preview, skip message, ack to prevent redelivery
- Guardrails: Counter metric for parse failures; no retry (bad data won't improve)
- Evidence: Standard JSON parsing error handling

- Failure: Missing `message` field in payload
- Surface: LogSinkService message processing
- Handling: Use empty string for message; continue processing
- Guardrails: Log debug message; metric for malformed payloads
- Evidence: `app/services/elasticsearch_service.py:341` - empty string default pattern

- Failure: Elasticsearch connection refused / timeout
- Surface: LogSinkService ES write
- Handling: Exponential backoff retry (1s, 2s, 3s... up to 60s); never give up
- Guardrails: Histogram metric for retry delays; gauge for current retry count
- Evidence: `docs/features/mqtt_logsink/change_brief.md:24`

- Failure: Elasticsearch HTTP error (4xx/5xx)
- Surface: LogSinkService ES write
- Handling: Retry with backoff (transient errors may recover); log error details
- Guardrails: Counter for ES write errors by status code
- Evidence: `app/services/elasticsearch_service.py:228-237` - HTTP error handling pattern

- Failure: Shutdown during retry loop
- Surface: LogSinkService backoff wait
- Handling: Check shutdown flag each second; exit loop gracefully if shutting down
- Guardrails: Message may be lost if shutdown during retry; acceptable per requirements
- Evidence: `docs/features/mqtt_logsink/change_brief.md:24` - "at most one message lost on crash"

---

## 9) Observability / Telemetry

**Implementation pattern:** LogSinkService will define its own Prometheus metrics directly (following MqttService pattern at `app/services/mqtt_service.py:104-134`), not via MetricsService. This avoids coupling and matches how other services with dedicated metrics operate.

- Signal: `iot_logsink_messages_received_total`
- Type: Counter
- Trigger: Each MQTT message received on logsink topic
- Labels / fields: `status` (success, parse_error, processing_error)
- Consumer: Dashboard for ingestion rate; alert on elevated error rate
- Evidence: `app/services/metrics_service.py:97-102` - counter pattern

- Signal: `iot_logsink_es_writes_total`
- Type: Counter
- Trigger: Each Elasticsearch write attempt (success or failure)
- Labels / fields: `status` (success, error), `error_type` (connection, timeout, http_error)
- Consumer: Dashboard for write success rate; alert on prolonged failures
- Evidence: `app/services/metrics_service.py:97-102` - counter pattern

- Signal: `iot_logsink_es_write_duration_seconds`
- Type: Histogram
- Trigger: Each successful ES write
- Labels / fields: None
- Consumer: Dashboard for latency percentiles
- Evidence: `app/services/metrics_service.py:104-108` - histogram pattern

- Signal: `iot_logsink_retry_delay_seconds`
- Type: Gauge
- Trigger: When entering retry backoff; reset to 0 on success
- Labels / fields: None
- Consumer: Dashboard for current backoff state; alert on sustained high values
- Evidence: Real-time visibility into retry behavior

- Signal: `iot_logsink_connection_state`
- Type: Gauge
- Trigger: MQTT connect/disconnect callbacks
- Labels / fields: None (0=disconnected, 1=connected)
- Consumer: Dashboard for service health
- Evidence: `app/services/mqtt_service.py:116-119` - connection state pattern

---

## 10) Background Work & Shutdown

- Worker / job: LogSinkService MQTT subscription loop
- Trigger cadence: Event-driven (paho-mqtt callback on message arrival)
- Responsibilities: Receive messages, process, write to ES, handle retries
- Shutdown handling:
  1. Set `_shutdown_event` (threading.Event) to interrupt any active backoff wait
  2. Call `loop_stop()` to stop paho-mqtt network thread
  3. Call `disconnect()` to cleanly close MQTT connection
  4. Register shutdown via `atexit.register(self.shutdown)` for cleanup
- Evidence: `app/services/mqtt_service.py:270-289` - shutdown pattern

- Worker / job: paho-mqtt network loop
- Trigger cadence: Continuous background thread managed by paho
- Responsibilities: Maintain MQTT connection, receive messages, trigger callbacks
- Shutdown handling: Call `loop_stop()` then `disconnect()`
- Evidence: `app/services/mqtt_service.py:89` - `loop_start()` pattern

---

## 11) Security & Permissions

- Concern: MQTT authentication
- Touchpoints: LogSinkService MQTT connection
- Mitigation: Use existing MQTT credentials from config (`mqtt_username`, `mqtt_password`)
- Residual risk: Credentials in environment variables; acceptable for internal service
- Evidence: `app/services/mqtt_service.py:74-76` - credential handling

- Concern: Elasticsearch authentication
- Touchpoints: LogSinkService ES writes
- Mitigation: Use existing ES credentials from config (`elasticsearch_username`, `elasticsearch_password`)
- Residual risk: Same as MQTT; internal network only
- Evidence: `app/services/elasticsearch_service.py:76-84` - auth handling

---

## 12) UX / UI Impact

Not applicable. This is a backend-only feature with no user-facing changes.

---

## 13) Deterministic Test Plan

- Surface: LogSinkService initialization
- Scenarios:
  - Given MQTT and ES both configured, When service initializes, Then MQTT client connects with persistent session and subscribes to `iotsupport/logsink`
  - Given MQTT configured but ES not configured, When service initializes, Then service.enabled is False and no MQTT connection is made
  - Given ES configured but MQTT not configured, When service initializes, Then service.enabled is False and no MQTT connection is made
  - Given neither MQTT nor ES configured, When service initializes, Then service.enabled is False without error
  - Given custom client ID env var, When service initializes, Then MQTT client ID matches configured value
- Fixtures / hooks: Mock MqttClient, mock httpx.Client, test Settings with various combinations
- Gaps: None
- Evidence: `tests/services/test_mqtt_service.py:10-139` - initialization test pattern

- Surface: LogSinkService message processing
- Scenarios:
  - Given valid JSON with message, When message received, Then ANSI codes stripped and ES write attempted
  - Given invalid JSON, When message received, Then warning logged and message acked
  - Given JSON without message field, When message received, Then empty message written to ES
  - Given message with ANSI codes, When processed, Then output contains no escape sequences
- Fixtures / hooks: Mock MQTT message, mock ES client
- Gaps: None
- Evidence: `tests/services/test_elasticsearch_service.py:14-108` - processing test pattern

- Surface: LogSinkService ES write with retry
- Scenarios:
  - Given ES available, When write attempted, Then document created and success metric incremented
  - Given ES unavailable, When write attempted, Then retry with 1s delay
  - Given ES unavailable then available, When retrying, Then success after recovery
  - Given ES unavailable for 5 attempts, When retrying, Then delays are 1s, 2s, 3s, 4s, 5s
  - Given delay at 60s, When next retry fails, Then delay stays at 60s (max cap)
  - Given shutdown during retry, When flag set, Then loop exits gracefully
- Fixtures / hooks: Mock httpx with configurable failures, mock `threading.Event` for interruptible sleep testing
- Gaps: None
- Evidence: Retry logic is critical path; thorough testing required

- Surface: LogSinkService shutdown
- Scenarios:
  - Given service running, When shutdown called, Then MQTT disconnects cleanly
  - Given retry in progress, When shutdown called, Then retry loop exits
  - Given service disabled, When shutdown called, Then no error
- Fixtures / hooks: Mock MQTT client
- Gaps: None
- Evidence: `tests/services/test_mqtt_service.py:327-381` - shutdown test pattern

- Surface: ANSI stripping utility
- Scenarios:
  - Given string with color codes, When stripped, Then plain text remains
  - Given string with cursor codes, When stripped, Then plain text remains
  - Given string without ANSI, When stripped, Then string unchanged
  - Given empty string, When stripped, Then empty string returned
- Fixtures / hooks: None (pure function)
- Gaps: None
- Evidence: Regex-based utility; straightforward unit tests

---

## 14) Implementation Slices

- Slice: ANSI Utility
- Goal: Reusable function for stripping escape codes
- Touches: `app/utils/ansi.py`, `tests/utils/test_ansi.py`
- Dependencies: None; can be implemented first

- Slice: Configuration
- Goal: Add logsink_client_id to Settings
- Touches: `app/config.py`
- Dependencies: None

- Slice: Metrics Registration
- Goal: Add log sink metrics to MetricsService
- Touches: `app/services/metrics_service.py`
- Dependencies: None

- Slice: LogSinkService Core
- Goal: MQTT subscription, message parsing, ANSI stripping, ES writes
- Touches: `app/services/logsink_service.py`, `tests/services/test_logsink_service.py`
- Dependencies: ANSI utility, configuration, metrics

- Slice: Container Integration
- Goal: Register LogSinkService in DI container
- Touches: `app/services/container.py`
- Dependencies: LogSinkService

- Slice: App Startup
- Goal: Initialize LogSinkService singleton when app starts
- Touches: `app/__init__.py`
- Dependencies: Container integration

---

## 15) Risks & Open Questions

- Risk: Elasticsearch outage causes unbounded message accumulation in MQTT broker
- Impact: Broker memory exhaustion if outage is prolonged and devices send high volume
- Mitigation: Configure broker-side queue limits; monitor retry gauge metric for alerts

- Risk: MQTT persistent session expiry loses queued messages
- Impact: Messages sent during extended app downtime may be lost
- Mitigation: Configure broker session expiry appropriately; document operational requirement

- Risk: Duplicate documents in ES on crash during retry
- Impact: Log queries may return duplicate entries
- Mitigation: Acceptable for log data; downstream consumers can dedupe if needed

No open questions remain; all requirements are clear and implementation path is defined.

---

## 16) Confidence

Confidence: High — Requirements are clear, existing patterns in the codebase provide solid templates for MQTT subscription and ES writes, and the scope is well-bounded to a single new service.
