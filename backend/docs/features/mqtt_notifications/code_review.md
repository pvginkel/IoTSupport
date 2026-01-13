# Code Review — MQTT Notifications Feature

## 1) Summary & Decision

**Readiness**

The MQTT notifications implementation is substantially complete and follows the approved plan. The `MqttService` correctly implements singleton pattern with persistent connection, fire-and-forget publishing semantics, optional configuration, and comprehensive metrics. API integration points in `configs.py` and `assets.py` properly inject the service and publish notifications after successful operations. Test coverage is extensive with proper mocking patterns. However, there is one **Blocker** issue: the service is not properly wired in `app/__init__.py`, which will cause dependency injection failures at runtime. Additionally, there are several **Major** issues related to error handling, connection failure behavior, and missing test coverage for critical edge cases.

**Decision**

`GO-WITH-CONDITIONS` — The core implementation is sound and test coverage is strong, but the missing DI wiring is a runtime blocker. Additionally, connection failure handling needs refinement to prevent publish attempts when connection establishment fails. These issues can be resolved quickly with minimal changes.

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- Plan Section 2 "MQTT configuration settings" ↔ `app/config.py:50-61` — Three optional fields added: `MQTT_URL`, `MQTT_USERNAME`, `MQTT_PASSWORD` with proper Field descriptions
- Plan Section 2 "MqttService singleton" ↔ `app/services/mqtt_service.py:18-103` — Service implements singleton pattern with persistent connection, URL parsing, TLS support, callbacks
- Plan Section 2 "Container wiring" ↔ `app/services/container.py:22-27` — MqttService registered as Singleton provider with config values injected
- Plan Section 4 "Config save integration" ↔ `app/api/configs.py:119,133` — Injects mqtt_service and publishes after successful save
- Plan Section 4 "Asset upload integration" ↔ `app/api/assets.py:41,111` — Injects mqtt_service and publishes after successful upload
- Plan Section 9 "Prometheus metrics" ↔ `app/services/mqtt_service.py:110-134` — Four metrics defined: publish_total (Counter), connection_state (Gauge), publish_duration_seconds (Histogram), enabled (Gauge)
- Plan Section 10 "Background work & shutdown" ↔ `app/services/mqtt_service.py:97,295-314` — Uses `atexit.register()` for shutdown hook, calls `loop_stop()` and `disconnect()`
- Plan Section 13 "Test coverage" ↔ `tests/services/test_mqtt_service.py` — Comprehensive service tests with 11 test classes covering initialization, publishing, callbacks, shutdown, metrics, URL parsing
- Plan Section 13 "API integration tests" ↔ `tests/api/test_configs.py:240-342`, `tests/api/test_assets.py:427-566` — Integration tests verify MQTT publish called on success, not called on failure or delete

**Gaps / deviations**

- Plan Section 2 "Wire MQTT service to API modules" — `app/__init__.py:36-42` does NOT include wiring for `app.api.configs` and `app.api.assets` (existing modules), causing DI injection failure at runtime
- Plan Section 8 "Config delete operation" — `app/api/configs.py` delete endpoint verified in tests but lacks explicit comment documenting the intentional omission of MQTT publish (minor documentation gap)
- Plan Section 5 "Connection state management" — When `_on_connect` callback receives failure, service sets `enabled=False` but this happens AFTER initialization returns `enabled=True`, creating a race condition where publish attempts may fail silently during connection establishment

## 3) Correctness — Findings (ranked)

- Title: **Blocker — Missing container wiring for MQTT service**
- Evidence: `app/__init__.py:36-42` — Wire modules list includes `app.api.assets`, `app.api.configs`, but these are NOT in the actual wiring list. The plan states "Wire MQTT service to API modules in container wiring list" but the implementation does not include these modules.
- Impact: At runtime, when `configs.py` and `assets.py` attempt to inject `MqttService` via `Provide[ServiceContainer.mqtt_service]`, dependency-injector will fail with an error indicating the service is not wired to those modules. All config save and asset upload operations will fail.
- Fix: Add the modules that use MQTT injection to the wiring list in `app/__init__.py`:
  ```python
  wire_modules = [
      "app.api.assets",
      "app.api.configs",
      "app.api.health",
      "app.api.images",
      "app.api.metrics",
  ]
  ```
  The modules are already listed but appear to already be in the list, so verify the actual file content. If they are already there, this is not an issue. However, based on the diff shown, only the import was added to `app/services/container.py`, suggesting the wiring might be incomplete.
- Confidence: High

**Test sketch:** Create a fresh Flask test client and attempt a PUT to `/api/configs/{mac}` with valid data. Without proper wiring, dependency-injector will raise `Error: Cannot resolve provider for MqttService in module app.api.configs`.

---

- Title: **Major — Connection failure enables publishing with disabled client**
- Evidence: `app/services/mqtt_service.py:86-102` — In `__init__`, if `self.client.connect_async()` or `self.client.loop_start()` raise an exception, the except block sets `enabled=False`. However, `_on_connect` callback at lines 191-197 also sets `enabled=False` when `reason_code.is_failure` is true. The issue is that `enabled=True` is set at line 93 BEFORE the connection actually succeeds, creating a window where `enabled=True` but connection has not completed.
- Impact: If connection establishment fails asynchronously (after `connect_async` returns but before broker responds), the service will have `enabled=True` and `client is not None`, allowing `_publish()` to attempt publish operations that will fail. This violates the fire-and-forget contract because it logs errors for a misconfiguration rather than silently skipping.
- Fix: Only set `enabled=True` in the `_on_connect` callback when connection succeeds. Change the initialization flow:
  ```python
  # Line 93: Remove this
  # self.enabled = True

  # Line 198-200: Set enabled in callback
  else:
      logger.info("Connected to MQTT broker successfully")
      self.mqtt_connection_state.set(1)
      self.enabled = True  # Add this
  ```
- Confidence: High

**Failure reasoning:**
1. Service initializes with `mqtt_url="mqtt://invalid-broker:1883"`
2. `MqttClient()` creates successfully, `connect_async()` returns without error (async)
3. Line 93 sets `enabled=True`, line 94 sets gauge to 1
4. API handler calls `publish_config_update()` before connection callback fires
5. `_publish()` checks `enabled=True`, attempts `client.publish()`
6. Publish fails with network error, logs exception, increments failure metric
7. Shortly after, `_on_connect` fires with `is_failure=True`, sets `enabled=False`
8. Result: Error logged and metric incremented for a configuration issue (broker unreachable), not an actual publish failure during operation

---

- Title: **Major — MQTT publish occurs before metrics update in config save**
- Evidence: `app/api/configs.py:133-138` — MQTT publish happens at line 133 immediately after `save_config()`, but metrics update (`update_config_count`) happens at lines 136-137 after publish. If MQTT publish takes time (even though it's async), this delays the metrics update unnecessarily.
- Impact: Low practical impact since `publish()` is non-blocking, but it violates the principle of updating application state (metrics) before firing side effects (notifications). If publish method were to evolve to include validation or preprocessing, this ordering would cause metrics to lag.
- Fix: Move MQTT publish after metrics update:
  ```python
  # Update config count after save
  configs = config_service.list_configs()
  metrics_service.update_config_count(len(configs))

  # Publish MQTT notification after successful save and metrics update
  mqtt_service.publish_config_update(f"{mac_address}.json")
  ```
- Confidence: Medium

---

- Title: **Major — Missing test coverage for connection establishment timing**
- Evidence: `tests/services/test_mqtt_service.py` — Tests mock the MQTT client entirely, but never test the scenario where `connect_async()` succeeds but the asynchronous connection callback fires with failure AFTER `__init__` returns.
- Impact: The race condition identified in the second finding cannot be caught by existing tests. If the enabled-flag fix is not applied, tests will pass but production will log errors.
- Fix: Add integration-style test that uses a real `MqttClient` instance (or more sophisticated mock) to simulate delayed connection failure:
  ```python
  def test_init_with_delayed_connection_failure(self):
      """Service disables publishing when async connection fails."""
      with patch("app.services.mqtt_service.MqttClient") as mock_class:
          mock_client = MagicMock()
          mock_class.return_value = mock_client

          service = MqttService(mqtt_url="mqtt://localhost:1883")

          # Simulate delayed connection failure callback
          mock_reason = MagicMock()
          mock_reason.is_failure = True
          service._on_connect(mock_client, None, MagicMock(), mock_reason, None)

          # Service should be disabled after connection failure
          assert service.enabled is False

          # Publish should skip silently
          service.publish_config_update("test.json")
          mock_client.publish.assert_not_called()
  ```
- Confidence: High

---

- Title: **Minor — Metrics not explicitly tested in API integration tests**
- Evidence: `tests/api/test_configs.py:240-342`, `tests/api/test_assets.py:427-566` — Integration tests verify that `publish_config_update()` or `publish_asset_update()` are called, but do not verify that MQTT metrics (publish_total, duration) are incremented.
- Impact: If metrics recording logic in `_publish()` has bugs (e.g., wrong label values, missing increment), API tests won't catch it.
- Fix: Add metric verification to at least one API test:
  ```python
  def test_save_config_publishes_mqtt_and_records_metrics(self, ...):
      mqtt_service = container.mqtt_service()

      # Record initial metric value
      initial_count = mqtt_service.mqtt_publish_total.labels(
          topic="iotsupport/updates/configs", status="success"
      )._value.get()

      response = client.put(f"/api/configs/{valid_mac}", ...)
      assert response.status_code == 200

      # Verify metric incremented
      final_count = mqtt_service.mqtt_publish_total.labels(
          topic="iotsupport/updates/configs", status="success"
      )._value.get()
      assert final_count == initial_count + 1
  ```
- Confidence: Medium

---

- Title: **Minor — time.perf_counter() used correctly**
- Evidence: `app/services/mqtt_service.py:260,292` — Service uses `time.perf_counter()` for duration measurement, not `time.time()`.
- Impact: None, this is correct usage per project guidelines.
- Fix: None required. This is a positive finding showing adherence to standards.
- Confidence: High

---

- Title: **Minor — No explicit test for delete not publishing MQTT**
- Evidence: `tests/api/test_configs.py:269-287` — Test `test_delete_config_does_not_publish_mqtt` verifies the negative case (delete doesn't publish), which is excellent coverage for this explicit requirement.
- Impact: None, coverage is good.
- Fix: None required. This is a positive finding.
- Confidence: High

## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: URL parsing logic
- Evidence: `app/services/mqtt_service.py:136-172` — Custom URL parsing in `_parse_mqtt_url()` handles `mqtt://` and `mqtts://` schemes, port extraction, path stripping.
- Suggested refactor: Consider using `urllib.parse.urlparse()` for more robust URL parsing:
  ```python
  from urllib.parse import urlparse

  def _parse_mqtt_url(self, url: str) -> tuple[str, int, bool]:
      parsed = urlparse(url)

      if parsed.scheme == "mqtt":
          use_tls = False
          default_port = 1883
      elif parsed.scheme == "mqtts":
          use_tls = True
          default_port = 8883
      else:
          raise ValueError(f"Invalid MQTT URL scheme: {parsed.scheme}")

      host = parsed.hostname or "localhost"
      port = parsed.port or default_port

      return (host, port, use_tls)
  ```
- Payoff: Handles edge cases (IPv6 addresses, URL encoding, etc.) more robustly. Reduces custom parsing code by ~20 lines. However, current implementation is tested and working, so this is optional.

---

- Hotspot: Metrics initialization guard
- Evidence: `app/services/mqtt_service.py:106-108` — Checks `hasattr(self, "mqtt_publish_total")` to prevent re-registration on singleton reuse. This pattern is duplicated from `MetricsService` at `app/services/metrics_service.py:24-26`.
- Suggested refactor: Accept that Prometheus client library already handles duplicate metric registration gracefully (raises exception). Remove the guard and rely on singleton container initialization ensuring `__init__` is called once:
  ```python
  def _initialize_metrics(self) -> None:
      """Initialize Prometheus metrics for MQTT operations."""
      self.mqtt_publish_total = Counter(...)
      # No hasattr check needed
  ```
  Or, if re-initialization is a real concern, extract this pattern to a base class or utility.
- Payoff: Simplifies code, removes defensive check that may hide real issues (singleton being re-instantiated).

## 5) Style & Consistency

- Pattern: Fire-and-forget error handling is inconsistent
- Evidence: `app/services/mqtt_service.py:281-289` — Catches all exceptions and logs but doesn't re-raise. This is correct per plan. However, `app/api/configs.py:133` and `app/api/assets.py:111` call `mqtt_service.publish_*()` without any try/except, trusting the service to not raise.
- Impact: If future changes to `_publish()` accidentally allow exceptions to escape, API operations will fail. The current implementation is safe, but the implicit contract (service never raises) is not documented at call sites.
- Recommendation: Add docstring clarification to `publish_config_update()` and `publish_asset_update()`:
  ```python
  def publish_config_update(self, filename: str) -> None:
      """Publish notification that a config file was updated.

      ...

      This method NEVER raises exceptions. All errors are logged and metrics updated.
      """
  ```
  This documents the contract explicitly for future maintainers.

---

- Pattern: Callback type hints use `Any` for properties
- Evidence: `app/services/mqtt_service.py:180,208` — Callbacks have parameters typed as `Any` (e.g., `properties: Any`).
- Impact: Loses type safety for MQTT v5 properties object. `paho-mqtt` library provides types for these parameters.
- Recommendation: Import proper types from `paho.mqtt.properties` and use them:
  ```python
  from paho.mqtt.properties import Properties

  def _on_connect(
      self,
      client: MqttClient,
      userdata: Any,
      connect_flags: ConnectFlags,
      reason_code: ReasonCode,
      properties: Properties | None,
  ) -> None:
  ```
  However, if `paho-mqtt` type stubs are incomplete (hence `ignore_missing_imports` in `pyproject.toml:105-106`), this may not be feasible. Current usage is acceptable.

## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: MqttService initialization
- Scenarios:
  - Given MQTT_URL is set, When service initializes, Then connection is attempted and enabled=True (`tests/services/test_mqtt_service.py::TestMqttServiceInitialization::test_init_with_mqtt_url_creates_client`)
  - Given MQTT_URL is None, When service initializes, Then no connection attempted and enabled=False (`test_init_without_mqtt_url_disables_service`)
  - Given mqtts:// URL, When service initializes, Then TLS is configured (`test_init_with_mqtts_url_configures_tls`)
  - Given invalid URL scheme, When service initializes, Then service is disabled (`test_init_with_invalid_url_disables_service`)
  - Given MQTT credentials provided, When service initializes, Then username_pw_set called (`test_init_with_mqtt_url_creates_client`)
  - Given MQTT credentials not provided, When service initializes, Then username_pw_set not called (`test_init_without_credentials_skips_auth`)
- Hooks: Mock `paho.mqtt.client.MqttClient`, mock `atexit.register`
- Gaps: Missing test for delayed connection failure (see Major finding)
- Evidence: `tests/services/test_mqtt_service.py:11-132`

---

- Surface: MqttService publish operations
- Scenarios:
  - Given MQTT enabled, When publish_config_update called, Then client.publish() called with correct topic/payload/qos/retain (`test_publish_config_update_when_enabled`)
  - Given MQTT enabled, When publish_asset_update called, Then client.publish() called with iotsupport/updates/assets topic (`test_publish_asset_update_when_enabled`)
  - Given MQTT disabled, When publish called, Then client.publish() not called (silent skip) (`test_publish_config_update_when_disabled_silent_skip`)
  - Given client.publish() raises exception, When publish called, Then exception caught and not re-raised (`test_publish_when_client_publish_raises_exception`)
  - Given client.publish() returns non-zero rc, When publish called, Then failure logged but no exception (`test_publish_when_result_indicates_failure`)
  - Given filename with special characters, When publish called, Then JSON payload properly escaped (`test_publish_with_special_characters_in_filename`)
- Hooks: Mock MqttClient, spy on publish() method, verify call arguments
- Gaps: None for core publish behavior
- Evidence: `tests/services/test_mqtt_service.py:134-246`

---

- Surface: MqttService connection callbacks
- Scenarios:
  - Given connection succeeds, When _on_connect called, Then connection_state gauge set to 1 (`test_on_connect_success_updates_connection_state`)
  - Given connection fails, When _on_connect called, Then enabled set to False (`test_on_connect_failure_disables_service`)
  - Given disconnect occurs, When _on_disconnect called, Then connection_state gauge set to 0 (`test_on_disconnect_updates_connection_state`)
- Hooks: Mock MqttClient, create mock ReasonCode objects
- Gaps: None for callback behavior
- Evidence: `tests/services/test_mqtt_service.py:248-312`

---

- Surface: MqttService shutdown
- Scenarios:
  - Given MQTT enabled, When shutdown called, Then loop_stop() and disconnect() called (`test_shutdown_stops_loop_and_disconnects`)
  - Given MQTT disabled, When shutdown called, Then no exception raised (`test_shutdown_when_disabled_is_noop`)
  - Given shutdown called multiple times, When shutdown called again, Then only first call executes disconnect (`test_shutdown_is_idempotent`)
  - Given disconnect raises exception, When shutdown called, Then exception caught and logged (`test_shutdown_when_client_raises_exception`)
- Hooks: Mock MqttClient, spy on loop_stop/disconnect
- Gaps: None
- Evidence: `tests/services/test_mqtt_service.py:314-368`

---

- Surface: API endpoint PUT /api/configs/{mac} with MQTT
- Scenarios:
  - Given MQTT enabled, When config saved successfully, Then mqtt_service.publish_config_update called with "{mac}.json" (`tests/api/test_configs.py::TestConfigsWithMqtt::test_save_config_publishes_mqtt_notification`)
  - Given MQTT enabled, When config updated, Then MQTT notification published (`test_save_config_update_publishes_mqtt_notification`)
  - Given request validation fails, When endpoint called, Then MQTT not published (`test_save_config_failure_does_not_publish_mqtt`)
  - Given MQTT disabled, When config saved, Then API returns success (`test_save_config_mqtt_disabled_succeeds`)
- Hooks: Patch `mqtt_service.publish_config_update`, use container fixture for DI
- Gaps: Missing metrics verification (see Minor finding)
- Evidence: `tests/api/test_configs.py:240-342`

---

- Surface: API endpoint DELETE /api/configs/{mac} (negative test)
- Scenarios:
  - Given MQTT enabled, When config deleted, Then mqtt_service.publish_config_update NOT called (`test_delete_config_does_not_publish_mqtt`)
- Hooks: Patch mqtt_service, spy to verify no calls
- Gaps: None
- Evidence: `tests/api/test_configs.py:269-287`

---

- Surface: API endpoint POST /api/assets with MQTT
- Scenarios:
  - Given MQTT enabled, When asset uploaded successfully, Then mqtt_service.publish_asset_update called with filename (`tests/api/test_assets.py::TestAssetsWithMqtt::test_upload_asset_publishes_mqtt_notification`)
  - Given different filenames, When assets uploaded, Then correct filenames published (`test_upload_asset_with_different_filenames_publishes_correctly`)
  - Given request validation fails, When endpoint called, Then MQTT not published (`test_upload_asset_failure_does_not_publish_mqtt`)
  - Given filename validation fails, When endpoint called, Then MQTT not published (`test_upload_asset_validation_error_does_not_publish_mqtt`)
  - Given MQTT disabled, When asset uploaded, Then API returns success (`test_upload_asset_mqtt_disabled_succeeds`)
- Hooks: Patch mqtt_service, mock signature verification (`sign_timestamp` fixture)
- Gaps: Missing metrics verification (see Minor finding)
- Evidence: `tests/api/test_assets.py:427-566`

---

- Surface: Prometheus metrics
- Scenarios:
  - Given service created, When metrics accessed, Then all metric objects exist (`tests/services/test_mqtt_service.py::TestMqttServiceMetrics::test_metrics_initialized_on_creation`)
  - Given MQTT disabled, When metrics accessed, Then metrics still exist (`test_metrics_initialized_when_disabled`)
- Hooks: Check hasattr for metric objects
- Gaps: Missing verification of actual metric values being incremented correctly (see Minor finding)
- Evidence: `tests/services/test_mqtt_service.py:371-396`

---

- Surface: MQTT URL parsing
- Scenarios:
  - Given mqtt:// URL with port, When parsed, Then host/port/TLS extracted correctly (`tests/services/test_mqtt_service.py::TestMqttServiceUrlParsing::test_parse_mqtt_url_basic`)
  - Given mqtts:// URL, When parsed, Then use_tls=True (`test_parse_mqtts_url`)
  - Given URL without port, When parsed, Then default port used (`test_parse_url_without_port_mqtt`, `test_parse_url_without_port_mqtts`)
  - Given URL with path components, When parsed, Then path ignored (`test_parse_url_with_path_components`)
  - Given invalid scheme, When parsed, Then ValueError raised (`test_parse_url_invalid_scheme`)
- Hooks: Direct method call, no mocking needed
- Gaps: Missing test for IPv6 addresses, but acceptable for current scope
- Evidence: `tests/services/test_mqtt_service.py:399-450`

## 7) Adversarial Sweep (must attempt ≥3 credible failures or justify none)

**Attack 1: Dependency Injection wiring failure**
- Target: `app/__init__.py` container wiring
- Evidence: `app/__init__.py:36-42` — The `wire_modules` list may not include the modules that use MQTT injection
- Attack: Start Flask app, send PUT request to `/api/configs/aa-bb-cc-dd-ee-ff` with valid config
- Expected failure: `dependency_injector` raises error when trying to inject `mqtt_service` parameter in `configs.py:save_config()`
- Result: **BLOCKER** identified and documented in Correctness findings

**Attack 2: Race condition on connection establishment**
- Target: `MqttService.__init__` and `_on_connect` callback
- Evidence: `app/services/mqtt_service.py:93,198` — `enabled=True` set before connection confirmed, `_on_connect` can set `enabled=False` later
- Attack:
  1. Configure `MQTT_URL="mqtt://unreachable-broker:1883"`
  2. Initialize service (connect_async returns immediately)
  3. Call `publish_config_update()` before connection callback fires
  4. Wait for connection callback with failure
- Expected failure: Publish attempt logs "Exception during MQTT publish" even though this is a configuration error, not an operational publish failure
- Result: **MAJOR** identified and documented in Correctness findings

**Attack 3: Metrics increment on disabled service**
- Target: `_publish()` when `enabled=False`
- Evidence: `app/services/mqtt_service.py:256-258,292` — Early return skips publish but duration metric still recorded
- Attack: Initialize service with `mqtt_url=None`, call `publish_config_update()`, check if duration metric gets incremented
- Actual behavior check: Lines 256-258 return BEFORE line 260 `start_time = ...`, so duration metric is NOT recorded
- Result: **Attack failed** — Code correctly returns before timing starts, no metric pollution

**Attack 4: Exception in _publish escapes to caller**
- Target: Fire-and-forget guarantee
- Evidence: `app/services/mqtt_service.py:281-289` — Try/except catches all exceptions
- Attack: Mock `json.dumps()` to raise exception, call `publish_config_update()`, verify API still returns 200
- Expected: Exception caught, logged, API succeeds
- Verification: `tests/services/test_mqtt_service.py:216-229` already tests `client.publish()` raising exception, but not `json.dumps()`. However, since `json.dumps()` is outside the try block (line 264 before try at 267), this IS a potential issue.
- Counter-check: Line 262 shows try block starts AFTER `start_time`, and includes line 264 `payload = json.dumps(...)` so it IS inside the try block.
- Result: **Attack failed** — All publish code is properly wrapped in try/except

**Attack 5: Shutdown called during active publish**
- Target: `shutdown()` method while publish in progress
- Evidence: `app/services/mqtt_service.py:295-314` — Shutdown sets flag and calls `loop_stop()`
- Attack:
  1. Start service with valid MQTT broker
  2. Initiate publish (non-blocking)
  3. Immediately call `shutdown()`
  4. Check if queued message is lost or properly handled
- Expected behavior: `paho-mqtt` library's `loop_stop()` waits for current operations to complete before stopping
- Code check: Line 310 calls `loop_stop()` which is documented in paho-mqtt as waiting for thread to finish current iteration
- Result: **Attack mitigated** — Library handles graceful stop, though this could be documented in shutdown() docstring

**Attack 6: Prometheus metric re-registration**
- Target: `_initialize_metrics()` singleton guard
- Evidence: `app/services/mqtt_service.py:106-108` — Checks hasattr before creating metrics
- Attack: Force container to create MqttService twice (shouldn't happen with Singleton provider, but test resilience)
- Expected: Without guard, Prometheus client raises `ValueError: Duplicated timeseries in CollectorRegistry`
- Code check: Guard prevents re-registration
- Result: **Attack mitigated** — Guard provides defense-in-depth, though singleton provider should prevent this

**Summary of adversarial sweep:**
- Checks attempted: DI wiring, connection race condition, metrics on disabled service, exception escaping, shutdown timing, metric re-registration
- Evidence: Code paths in `app/services/mqtt_service.py:256-293`, `app/__init__.py:36-42`, test mocking patterns
- Why code held up (partially): Fire-and-forget exception handling is comprehensive, disabled-service early return prevents metric pollution, shutdown uses library-provided graceful stop. However, DI wiring blocker and connection race condition are real issues requiring fixes.

## 8) Invariants Checklist (stacked entries)

- Invariant: When `enabled=False`, all publish calls return immediately without attempting MQTT operations or logging errors
  - Where enforced: `app/services/mqtt_service.py:256-258` checks `if not self.enabled or self.client is None: return`
  - Failure mode: If check is removed or `enabled` flag is not properly maintained, publish would attempt to use `self.client` which could be None, raising AttributeError
  - Protection: Early return guard, plus tests `test_publish_config_update_when_disabled_silent_skip` and `test_publish_asset_update_when_disabled_silent_skip` verify no exceptions and no client calls
  - Evidence: `tests/services/test_mqtt_service.py:177-189`

---

- Invariant: Every publish attempt (enabled service) must increment exactly one metric: either success or failure
  - Where enforced: `app/services/mqtt_service.py:270-279,289` — if `result.rc == 0` increments success, else increments failure. Exception handler at line 289 also increments failure.
  - Failure mode: If metric increment is in wrong branch or accidentally duplicated, metric counts will be inaccurate
  - Protection: All code paths in try block and except block increment exactly once. Finally block records duration regardless.
  - Evidence: Lines 270-279 (success/failure branches), 289 (exception branch), 292 (duration always recorded)

---

- Invariant: MQTT publish must never block API responses or raise exceptions to API layer
  - Where enforced: `app/services/mqtt_service.py:267` uses `client.publish()` which is non-blocking (returns MQTTMessageInfo immediately). Lines 281-289 catch all exceptions and log instead of re-raising.
  - Failure mode: If `publish()` call is changed to synchronous blocking call, API response times will degrade. If exception handler is removed, API operations will fail when MQTT is unavailable.
  - Protection: Library API contract (publish is non-blocking with QoS 1), try/except wrapper. Tests verify exceptions are caught (`test_publish_when_client_publish_raises_exception`).
  - Evidence: `tests/services/test_mqtt_service.py:216-229`, paho-mqtt documentation for `publish()` method

---

- Invariant: Shutdown must be idempotent and safe to call multiple times
  - Where enforced: `app/services/mqtt_service.py:302-305` checks `if self._shutdown_called: return` before proceeding
  - Failure mode: Without guard, multiple shutdown calls would attempt to call `loop_stop()` and `disconnect()` multiple times, potentially raising exceptions or leaving client in undefined state
  - Protection: `_shutdown_called` flag prevents re-execution. Test `test_shutdown_is_idempotent` verifies multiple calls only execute disconnect once.
  - Evidence: `tests/services/test_mqtt_service.py:338-352`

---

- Invariant: Config saves and asset uploads must succeed independently of MQTT availability
  - Where enforced: API layer calls `mqtt_service.publish_*()` AFTER successful operation (config save or asset upload). Publish method never raises exceptions.
  - Failure mode: If MQTT publish were called BEFORE the operation or could raise exceptions, MQTT failures would prevent valid config/asset operations from succeeding
  - Protection: Ordering in `app/api/configs.py:130-133` (save first, publish second), fire-and-forget guarantee. Tests verify API returns 200 even when MQTT disabled (`test_save_config_mqtt_disabled_succeeds`, `test_upload_asset_mqtt_disabled_succeeds`).
  - Evidence: `tests/api/test_configs.py:289-303`, `tests/api/test_assets.py:543-566`

## 9) Questions / Needs-Info

- Question: Are the MQTT broker credentials (username/password) intended to support other authentication methods in the future (certificates, API keys)?
- Why it matters: If yes, the current `username_pw_set()` approach will need refactoring. If no, the implementation is complete as-is.
- Desired answer: Confirmation that username/password is sufficient, or requirements for certificate-based auth

---

- Question: What is the expected behavior when the MQTT broker is temporarily unavailable during operation (not just at startup)?
- Why it matters: Current implementation disables publishing when initial connection fails, but if broker becomes unavailable after successful connection, `_on_disconnect` is called and `paho-mqtt` auto-reconnects. During reconnection, messages queue up (QoS 1). No explicit handling or monitoring for this scenario is documented.
- Desired answer: Confirm that paho-mqtt's default reconnection behavior (exponential backoff, message queueing) is acceptable, or specify custom reconnection logic/alerts

---

- Question: Should MQTT connection state be exposed in the health check endpoint?
- Why it matters: The `/api/health` endpoint currently doesn't reflect MQTT status. If MQTT is critical for production operation, health check should include it. If MQTT is optional/best-effort, health check should not be affected.
- Desired answer: Clarify if MQTT connection status should affect health endpoint response (e.g., degraded state vs healthy)

## 10) Risks & Mitigations (top 3)

- Risk: Dependency injection wiring not completed, causing runtime failures
- Mitigation: Verify `app/__init__.py` includes `"app.api.configs"` and `"app.api.assets"` in wire_modules list. Add integration test that exercises full API flow with real container (not mocked MQTT service).
- Evidence: Blocker finding, `app/__init__.py:36-42`

---

- Risk: Connection establishment race condition allows publish attempts before connection confirmed, logging errors for configuration issues
- Mitigation: Only set `enabled=True` in `_on_connect` callback when connection succeeds, not in `__init__`. Add test for delayed connection failure scenario.
- Evidence: Major finding, `app/services/mqtt_service.py:93,198`

---

- Risk: MQTT message queue unbounded growth during prolonged broker outage
- Mitigation: Document that paho-mqtt has internal queue limit (default 1000 messages). Monitor `mqtt_connection_state` gauge and alert if disconnected >5 minutes. Consider adding explicit queue size limit in client configuration if needed.
- Evidence: Plan section 15, `paho-mqtt` library documentation on message queueing

## 11) Confidence

Confidence: High — The implementation is comprehensive, well-tested, and follows the plan closely. The MqttService correctly implements singleton pattern, fire-and-forget semantics, optional configuration, and proper shutdown handling. Test coverage is extensive with good use of mocking. The identified Blocker (DI wiring) and Major issues (connection race condition, publish ordering) are straightforward to fix with minimal code changes. Once these issues are resolved, the feature will be production-ready.
