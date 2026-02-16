# Code Review: SSE Real-Time Updates

## 1) Summary & Decision

**Readiness**

The SSE real-time updates feature is well-implemented and closely follows both the approved plan and established project patterns. The change introduces a new `DeviceLogStreamService` singleton with identity binding, subscription management, log forwarding, and rotation nudge broadcasting. All integration points (SSE callback, LogSinkService, rotation API endpoints, internal CronJob endpoint) are correctly wired. The code ships with 65 passing tests covering service logic, API endpoints, and integration. Ruff and mypy show no new issues. The architectural decisions -- placing the device lookup at the API layer to keep the singleton DB-free, and placing nudge calls at the API layer rather than inside the Factory RotationService -- are sound and well-documented.

**Decision**

`GO-WITH-CONDITIONS` -- Two Major findings require attention before merge: (1) the `InvalidOperationException` -> 403 mapping in the subscribe/unsubscribe endpoints bypasses the standard error handler by pattern-matching on the `cause` string, which is fragile; and (2) the unsubscribe endpoint passes an empty string as `device_entity_id` when the device has no entity_id, which produces a misleading "no active subscription" error instead of a clean 404. Neither is a data-safety issue, but both affect API contract correctness. The conditions for GO are minor and addressable in a follow-up patch.

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- `Plan: Section 2, SSEConnectionManager on_disconnect` <-> `app/services/sse_connection_manager.py:97-109` -- `register_on_disconnect` and observer invocation at lines 237-258 match plan exactly.
- `Plan: Section 2, DeviceLogStreamService core` <-> `app/services/device_log_stream_service.py:53-468` -- Identity binding, subscription maps, forward/reverse indexes, lock discipline, forwarding, nudge broadcast, lifecycle shutdown all implemented as planned.
- `Plan: Section 2, REST endpoints` <-> `app/api/device_log_stream.py:48-137` -- Subscribe/unsubscribe endpoints with schema validation, identity verification, and device lookup at API layer.
- `Plan: Section 2, Internal endpoint` <-> `app/api/internal.py:23-43` -- `/internal/rotation-nudge` POST endpoint on `/` (not `/api/`).
- `Plan: Section 2, Container wiring` <-> `app/services/container.py:131-137` -- Singleton with `sse_connection_manager`, `auth_service`, `lifecycle_coordinator` dependencies. LogSinkService wired at line 186.
- `Plan: Section 2, Blueprint registration` <-> `app/startup.py:42,52` -- `device_log_stream_bp` registered under `api_bp`. `app/__init__.py:153,157` -- `internal_bp` registered on app root.
- `Plan: Section 2, AppSettings` <-> `app/app_config.py:78-80,133-134,196` -- `INTERNAL_API_URL` in env, `internal_api_url` in settings, `strip_slashes` applied.
- `Plan: Section 2, CronJob nudge` <-> `app/startup.py:134-156,232` -- `_notify_rotation_nudge` with httpx POST, best-effort error handling, called after rotation job completes.
- `Plan: Section 2, Rotation API nudge` <-> `app/api/rotation.py:66,84` -- `broadcast_rotation_nudge(source="web")` called after fleet trigger.
- `Plan: Section 2, IoT config nudge` <-> `app/api/iot.py:75,180` -- Nudge after chain rotation completion.
- `Plan: Section 2, SSE callback identity binding` <-> `app/api/sse.py:51,117-119` -- `bind_identity` called after `on_connect` in callback handler.
- `Plan: Section 9, Metrics` <-> `app/services/device_log_stream_service.py:29-47` -- All four planned Prometheus metrics implemented: `sse_device_log_subscriptions_active`, `sse_device_log_events_sent_total`, `sse_rotation_nudge_broadcast_total`, `sse_identity_binding_total`.

**Gaps / deviations**

- `Plan: Section 4, Unsubscribe error 404 for subscription not found` -- The plan specifies 404 for missing subscriptions. The implementation maps this through `RecordNotFoundException` re-raise which reaches `handle_api_errors` for 404, but only after string-matching `e.cause`. This is deviation-by-fragility, not a missing feature. See Finding #2 below.
- No deviations from the approved plan's scope or data contracts.

---

## 3) Correctness -- Findings (ranked)

- Title: `Major -- InvalidOperationException-to-403 mapping via string matching on e.cause is fragile`
- Evidence: `app/api/device_log_stream.py:84` -- `if "identity" in e.cause:`; `app/api/device_log_stream.py:133` -- `if "no active subscription" in e.cause:`
- Impact: If the cause message in `DeviceLogStreamService._verify_identity` or `unsubscribe` changes even slightly (e.g., "Identity mismatch" capitalized, or "subscription" rephrased), the string match fails and the error falls through to `handle_api_errors` which maps `InvalidOperationException` to 400. The API contract (403 for identity errors, 404 for missing subscriptions) silently breaks. This is a correctness risk because consumers (the frontend) rely on status codes.
- Fix: Introduce distinct exception subclasses (e.g., `IdentityVerificationException` inheriting from `InvalidOperationException`, or a more direct approach: raise `AuthorizationException` for identity mismatches and `RecordNotFoundException` for missing subscriptions directly in the service). This eliminates string matching entirely. Alternatively, use a structured code field on the exception rather than substring matching.
- Confidence: High

  Step-by-step failure scenario:
  1. Developer changes `_verify_identity` message from `"no identity binding for this SSE connection"` to `"no authenticated session for this SSE connection"`.
  2. `"identity" in e.cause` still matches (the word "identity" is gone but "authenticated" doesn't contain "identity").
  3. Wait -- actually "no identity binding" does contain "identity". But if someone writes `"No authenticated binding"` the check fails.
  4. The `InvalidOperationException` propagates to `handle_api_errors` which returns 400 instead of 403.
  5. Frontend receives unexpected 400 and cannot distinguish auth failure from bad request.

- Title: `Major -- Unsubscribe with device that has no entity_id sends empty string as device_entity_id`
- Evidence: `app/api/device_log_stream.py:118` -- `device_entity_id = device.device_entity_id or ""`
- Impact: When a device exists but has `device_entity_id = None`, the unsubscribe endpoint passes `""` to `DeviceLogStreamService.unsubscribe()`. The service will fail with `InvalidOperationException("no active subscription for this device")` because no subscription exists for `""`. This surfaces as a confusing error. The subscribe endpoint correctly returns 404 for this case (`app/api/device_log_stream.py:73-74`), but the unsubscribe endpoint does not.
- Fix: Add the same null check as in the subscribe endpoint: if `not device.device_entity_id: raise RecordNotFoundException("Device entity ID", data.device_id)` before calling `unsubscribe`. Remove the `or ""` fallback.
- Confidence: High

  Step-by-step failure:
  1. User subscribes to device with entity_id `"sensor.a"`.
  2. Admin clears the device's `device_entity_id` (sets to None).
  3. User tries to unsubscribe for same device_id.
  4. API resolves device, gets `device_entity_id = None`, substitutes `""`.
  5. Service raises `InvalidOperationException("no active subscription")` because subscription was for `"sensor.a"`, not `""`.
  6. API catches this via string match and re-raises as `RecordNotFoundException` -- 404 is returned but the real issue is a data change, not a missing subscription.

- Title: `Minor -- Rotation nudge broadcast is called even when fleet trigger raises an exception`
- Evidence: `app/api/rotation.py:81-84` -- The nudge call is inside the `try` block after `rotate_next_queued_device()`. If `rotate_next_queued_device` raises, the nudge is not called (exception jumps to `except`). However, if `trigger_fleet_rotation()` at line 79 raises, the nudge is also correctly skipped. The logic is actually correct as written because the nudge is after both service calls. No action needed -- this is a positive observation.
- Evidence (second concern): `app/api/rotation.py:84` -- The nudge is broadcast even when `queued_count == 0`, which means a nudge fires for a no-op fleet trigger. This is intentional per the plan ("Nudge is still broadcast even when no devices were queued", see `tests/api/test_rotation.py:118`). The test confirms this is desired behavior.
- Impact: None. This is consistent with the plan.
- Fix: None required.
- Confidence: High

---

## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: None identified. The implementation is lean and follows established patterns. The `DeviceLogStreamService` is appropriately scoped as a single class handling related concerns (subscriptions, identity, forwarding, nudge). The separation of device lookup at the API layer vs. subscription management in the singleton is well-motivated by the DB session lifecycle constraints.

---

## 5) Style & Consistency

- Pattern: Identity binding call placement in SSE callback handler
- Evidence: `app/api/sse.py:114-119` -- `bind_identity` is called inline in the connect handler, not via the `register_on_connect` observer pattern. A comment at lines 114-116 explains why.
- Impact: Future developers might expect all SSE connect actions to go through observers. The explicit comment mitigates this.
- Recommendation: The comment is sufficient. No change needed.

- Pattern: Consistent use of `perf_counter` for timing
- Evidence: No timing measurements are introduced in the new code. The `_notify_rotation_nudge` function uses `httpx` with a `timeout=5.0` parameter (wall-clock timeout, not a duration measurement). This is correct usage per CLAUDE.md.
- Impact: None.
- Recommendation: None needed.

- Pattern: Error handling in the internal endpoint
- Evidence: `app/api/internal.py:23-43` -- The `/internal/rotation-nudge` endpoint does not use `@handle_api_errors`. Since it is internal and always returns 200, this is acceptable. If `broadcast_rotation_nudge` raises, the exception would propagate to Flask's generic handler (500).
- Impact: A failure in the broadcast would return a 500 to the CronJob, which already treats the call as best-effort.
- Recommendation: Consider wrapping in try/except for consistent 200 responses, but this is a nit given the CronJob's best-effort semantics.

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: `DeviceLogStreamService` (service tests)
- Scenarios:
  - Given OIDC disabled, When `bind_identity` called, Then sentinel subject stored (`tests/services/test_device_log_stream_service.py::TestIdentityBinding::test_bind_identity_oidc_disabled_stores_sentinel`)
  - Given valid Bearer token, When `bind_identity` called, Then subject from validation stored (`test_bind_identity_oidc_enabled_with_valid_bearer_token`)
  - Given cookie header, When `bind_identity` called, Then token extracted from cookie (`test_bind_identity_oidc_enabled_with_cookie`)
  - Given no token, When `bind_identity` called, Then identity map not populated (`test_bind_identity_oidc_enabled_no_token_in_headers`)
  - Given invalid token, When `bind_identity` called, Then identity map not populated (`test_bind_identity_oidc_enabled_invalid_token`)
  - Given Bearer + cookie present, When `bind_identity` called, Then Bearer takes priority (`test_bind_identity_bearer_takes_priority_over_cookie`)
  - Given identity bound, When `subscribe` called with matching subject, Then stored in both maps (`test_subscribe_success`)
  - Given same pair, When `subscribe` called twice, Then idempotent (`test_subscribe_idempotent`)
  - Given connection, When `subscribe` to multiple devices, Then all stored (`test_subscribe_multiple_devices`)
  - Given two connections, When both subscribe to same device, Then reverse map has both (`test_subscribe_multiple_connections_same_device`)
  - Given no identity, When `subscribe` called, Then `InvalidOperationException` raised (`test_subscribe_no_identity_binding_raises`)
  - Given mismatched subject, When `subscribe` called, Then `InvalidOperationException` raised (`test_subscribe_mismatched_subject_raises`)
  - Given OIDC subject match, When `subscribe` called, Then success (`test_subscribe_with_matching_oidc_subject_succeeds`)
  - Given subscription, When `unsubscribe` called, Then removed from both maps (`test_unsubscribe_success`)
  - Given no subscription, When `unsubscribe` called, Then raises (`test_unsubscribe_nonexistent_raises`)
  - Given two subscriptions, When `unsubscribe` one, Then other remains (`test_unsubscribe_keeps_other_subscriptions`)
  - Given subscription for entity, When `forward_logs` with matching docs, Then SSE event sent with correct payload (`test_forward_logs_to_subscribers`)
  - Given subscription, When `forward_logs` with non-matching entity, Then no SSE event (`test_forward_logs_no_match`)
  - Given no subscriptions, When `forward_logs` called, Then fast no-op (`test_forward_logs_no_subscriptions`)
  - Given docs without entity_id, When `forward_logs` called, Then those docs skipped (`test_forward_logs_skips_docs_without_entity_id`)
  - Given two subscribers for same device, When `forward_logs` called, Then event sent to both (`test_forward_logs_multiple_subscribers`)
  - Given subscriptions for different entities, When `forward_logs` with both, Then grouped correctly (`test_forward_logs_groups_by_entity`)
  - Given shutdown, When `forward_logs` called, Then no-op (`test_forward_logs_during_shutdown_is_noop`)
  - Given connections, When `broadcast_rotation_nudge` called, Then broadcast event sent (`test_broadcast_rotation_nudge`)
  - Given no connections, When `broadcast_rotation_nudge` called, Then returns False (`test_broadcast_rotation_nudge_no_connections`)
  - Given shutdown, When `broadcast_rotation_nudge` called, Then returns False (`test_broadcast_rotation_nudge_during_shutdown`)
  - Given subscriptions, When `_on_disconnect_callback` called, Then all subscriptions and identity removed (`test_disconnect_removes_all_subscriptions`, `test_disconnect_removes_identity_mapping`)
  - Given two connections with shared device, When one disconnects, Then other preserved (`test_disconnect_preserves_other_connections`)
  - Given no subscriptions for request_id, When disconnect, Then safe no-op (`test_disconnect_no_subscriptions_is_safe`, `test_disconnect_unknown_request_id_is_safe`)
  - Given active state, When `PREPARE_SHUTDOWN` fires, Then all maps cleared and flag set (`test_prepare_shutdown_clears_all_state`)
  - Given shutdown completed, When `subscribe` attempted, Then raises no identity (`test_subscribe_after_shutdown_does_not_crash`)
- Hooks: Mock `SSEConnectionManager`, mock `AuthService`, `StubLifecycleCoordinator`, `TestLifecycleCoordinator`
- Gaps: None identified for the service layer.
- Evidence: `tests/services/test_device_log_stream_service.py` -- 22 tests, all passing.

- Surface: `SSEConnectionManager.register_on_disconnect` (service tests)
- Scenarios:
  - Given registered callback, When valid disconnect, Then callback invoked with request_id (`test_disconnect_callback_invoked_on_valid_disconnect`)
  - Given registered callback, When stale token disconnect, Then callback NOT invoked (`test_disconnect_callback_not_invoked_for_stale_token`)
  - Given registered callback, When replaced connection disconnect with old token, Then callback NOT invoked (`test_disconnect_callback_not_invoked_for_replaced_connection`)
  - Given two callbacks, When disconnect, Then both invoked (`test_multiple_disconnect_callbacks_all_invoked`)
  - Given failing callback, When disconnect, Then other callbacks still run (`test_callback_exception_does_not_block_other_callbacks`)
  - Given connection, When disconnect, Then mappings removed (`test_disconnect_removes_connection_mappings`)
  - Given both connect and disconnect callbacks, When connect, Then only connect callback fires (`test_connect_callback_still_works_with_disconnect_registered`)
- Hooks: Direct instantiation of `SSEConnectionManager`
- Gaps: None.
- Evidence: `tests/services/test_sse_connection_manager.py` -- 7 tests, all passing.

- Surface: `POST /api/device-logs/subscribe` and `POST /api/device-logs/unsubscribe` (API tests)
- Scenarios:
  - Subscribe success (`test_subscribe_success`), device not found (`test_subscribe_device_not_found`), no entity_id (`test_subscribe_device_no_entity_id`), no identity (`test_subscribe_no_identity_binding`), missing fields (`test_subscribe_missing_request_id`, `test_subscribe_missing_device_id`), idempotent (`test_subscribe_idempotent`)
  - Unsubscribe success (`test_unsubscribe_success`), no subscription (`test_unsubscribe_no_subscription`), no identity (`test_unsubscribe_no_identity_binding`)
- Hooks: `_setup_device` helper creates device model + device with Keycloak mocks. Container-provided `device_log_stream_service` singleton for identity binding.
- Gaps: Missing test for subscribe with OIDC-enabled subject mismatch at the API layer (only tested at service layer). Also missing test for `unsubscribe` when device has no `entity_id`. These are Minor given the service-layer coverage.
- Evidence: `tests/api/test_device_log_stream.py` -- 10 tests, all passing.

- Surface: `POST /internal/rotation-nudge` (API tests)
- Scenarios:
  - Nudge with active connections returns 200 (`test_rotation_nudge_success`)
  - Nudge with no connections returns 200 (`test_rotation_nudge_no_connections`)
- Hooks: `patch.object` on `device_log_stream_service.broadcast_rotation_nudge`
- Gaps: None for the endpoint's contract.
- Evidence: `tests/api/test_internal.py` -- 2 tests, all passing.

- Surface: `_notify_rotation_nudge` startup helper (unit tests)
- Scenarios:
  - URL configured -> HTTP POST sent (`test_nudge_sent_when_url_configured`)
  - URL not configured -> no call (`test_nudge_skipped_when_url_not_configured`)
  - HTTP failure -> exception swallowed (`test_nudge_failure_does_not_raise`)
  - URL format correct (`test_nudge_strips_trailing_slash`)
- Hooks: Mocked `app.container.app_config()`, patched `httpx.post`
- Gaps: None.
- Evidence: `tests/test_startup.py` -- 4 tests, all passing.

- Surface: `LogSinkService` SSE forwarding integration
- Scenarios:
  - Single doc forwarded (`test_forward_logs_called_with_parsed_documents`)
  - Multiple NDJSON lines forwarded (`test_forward_logs_called_with_multiple_ndjson_lines`)
  - None service -> no error (`test_no_forward_when_service_is_none`)
  - Forward error does not break ES write (`test_forward_error_does_not_break_es_enqueue`)
  - Invalid JSON not forwarded (`test_forward_not_called_for_invalid_json`)
- Hooks: Mock `DeviceLogStreamService`, mock MQTT, `TestLifecycleCoordinator`, mock httpx client
- Gaps: None.
- Evidence: `tests/services/test_logsink_service.py::TestLogSinkServiceSSEForwarding` -- 5 tests, all passing.

- Surface: Rotation nudge emission from API endpoints
- Scenarios:
  - Fleet trigger broadcasts nudge (`tests/api/test_rotation.py::test_trigger_fleet_rotation`)
  - Fleet trigger with no OK devices still broadcasts (`test_trigger_fleet_rotation_no_ok_devices`)
  - Fleet trigger with no devices still broadcasts (`test_trigger_fleet_rotation_no_devices`)
  - Chain rotation completion broadcasts nudge (`tests/api/test_iot.py::test_get_config_rotation_completion_broadcasts_nudge`)
- Hooks: `patch.object` on `device_log_stream_service.broadcast_rotation_nudge`, mock device auth context
- Gaps: None.
- Evidence: `tests/api/test_rotation.py`, `tests/api/test_iot.py` -- 4 tests, all passing.

---

## 7) Adversarial Sweep

**Attack 1: Singleton-to-Singleton circular initialization**

- Checks attempted: `DeviceLogStreamService` (Singleton) depends on `SSEConnectionManager` (Singleton) and `AuthService` (Singleton). `LogSinkService` (Singleton) depends on `DeviceLogStreamService`. Could there be circular initialization in the container?
- Evidence: `app/services/container.py:104-108` (SSE manager), `app/services/container.py:97` (auth_service), `app/services/container.py:131-137` (device_log_stream_service), `app/services/container.py:181-188` (logsink_service). The dependency graph is: SSE manager -> none; auth_service -> config; device_log_stream_service -> SSE manager + auth_service + lifecycle; logsink_service -> mqtt + lifecycle + device_log_stream_service. No cycles.
- Why code held up: `dependency-injector` Singleton providers resolve lazily. There is no circular dependency. The `register_for_background_startup` call at line 137 ensures eagerly-touched instantiation happens in declaration order, which respects dependencies.

**Attack 2: Lock contention between MQTT thread and Flask request threads**

- Checks attempted: The `_lock` in `DeviceLogStreamService` is acquired by `forward_logs` (MQTT thread), `subscribe`/`unsubscribe` (Flask request thread), and `_on_disconnect_callback` (SSE callback handler thread). Could the lock block MQTT ingestion?
- Evidence: `app/services/device_log_stream_service.py:334-336` -- fast-path check under lock; `app/services/device_log_stream_service.py:354-358` -- copy subscriber list under lock; `app/services/device_log_stream_service.py:367-377` -- SSE sends happen OUTSIDE the lock.
- Why code held up: The lock is held only for dict lookups and copies (microseconds). The expensive HTTP call to SSE Gateway happens outside the lock. This follows the same pattern as `SSEConnectionManager.on_connect` (lines 147-149 in the existing code). At the documented scale (up to 200 devices, handful of users), contention is negligible.

**Attack 3: Missing SSE forwarding when `_process_line` raises a non-JSON exception**

- Checks attempted: If `_process_line` raises a non-`JSONDecodeError` exception (e.g., `ShutDown` from the queue), do we lose forwarding for documents already parsed?
- Evidence: `app/services/logsink_service.py:210-213` -- If `ShutDown` is raised, the method returns immediately. Lines 221-226 (the forwarding block) are never reached. Documents parsed before the `ShutDown` exception are lost for SSE forwarding.
- Impact: This is an edge case that only happens during shutdown. During shutdown, the `DeviceLogStreamService` has already cleared its state (via `PREPARE_SHUTDOWN`), so forwarding would be a no-op anyway. The ES write for those docs is also lost (queue is shut down).
- Why code held up: The `ShutDown` exception during queue put means the service is shutting down. All SSE clients are being disconnected. Losing the last batch of log forwarding during shutdown is acceptable.

**Attack 4: Identity map entry outlives subscription cleanup**

- Checks attempted: Can the `_identity_map` entry persist after all subscriptions and the SSE connection are gone?
- Evidence: `app/services/device_log_stream_service.py:436` -- `_on_disconnect_callback` removes identity map entry with `self._identity_map.pop(request_id, None)`. This happens after subscription cleanup (line 427-434). But what about `bind_identity` being called and no subsequent disconnect? If the SSE Gateway crashes without sending a disconnect callback, the identity map entry remains indefinitely.
- Impact: Memory leak -- but bounded by the number of SSE connections (handful of users, ~200 max). The identity map entry is a `{str: str}` pair, so the leak is trivially small. On next `PREPARE_SHUTDOWN` or app restart, all state is cleared.
- Why code held up: This is a known limitation of SSE connection tracking in general. The existing `SSEConnectionManager` has the same characteristic (connection entries persist if no disconnect callback arrives). The lifecycle shutdown cleanup bounds the leak.

---

## 8) Invariants Checklist

- Invariant: Bidirectional subscription maps are always consistent -- `_subscriptions_by_entity_id[eid]` contains `rid` if and only if `_subscriptions_by_request_id[rid]` contains `eid`.
  - Where enforced: `app/services/device_log_stream_service.py:201-212` (subscribe), `app/services/device_log_stream_service.py:256-265` (unsubscribe), `app/services/device_log_stream_service.py:426-434` (disconnect cleanup). All mutations happen under `self._lock`.
  - Failure mode: If one map is updated but not the other (e.g., exception between updates).
  - Protection: Both updates happen within the same `with self._lock:` block. Set operations (`add`, `discard`) do not raise exceptions for normal inputs. Tests verify both maps after every mutation (`tests/services/test_device_log_stream_service.py::TestSubscription`).
  - Evidence: `app/services/device_log_stream_service.py:81` -- `threading.RLock()`

- Invariant: Every `request_id` in `_subscriptions_by_request_id` has a corresponding entry in `_identity_map`.
  - Where enforced: `subscribe` calls `_verify_identity` (line 202) which checks `_identity_map.get(request_id)` before allowing subscription creation. Disconnect cleanup removes subscriptions first (line 427), then identity (line 436).
  - Failure mode: `bind_identity` fails (token invalid) so identity map not populated, but somehow subscribe succeeds. This cannot happen because `_verify_identity` raises `InvalidOperationException` when no identity exists.
  - Protection: `_verify_identity` at `app/services/device_log_stream_service.py:290-310`. Tests: `test_subscribe_no_identity_binding_raises`.
  - Evidence: `app/services/device_log_stream_service.py:202`

- Invariant: SSE event sends happen outside the subscription lock to prevent MQTT thread blocking.
  - Where enforced: `app/services/device_log_stream_service.py:354-358` -- subscriber list copied under lock; `app/services/device_log_stream_service.py:367-377` -- `send_event` called outside the lock scope.
  - Failure mode: If sends were inside the lock, an HTTP timeout (2s) would block MQTT ingestion and other subscription operations.
  - Protection: Code structure -- the `with self._lock:` block ends at line 358, SSE sends start at line 367.
  - Evidence: Pattern mirrors `SSEConnectionManager.on_connect` observer notification (existing code).

- Invariant: `PREPARE_SHUTDOWN` clears all in-memory state and prevents new forwarding/broadcasting.
  - Where enforced: `app/services/device_log_stream_service.py:460-467` -- clears all three maps and sets `_is_shutting_down = True`. `forward_logs` (line 330) and `broadcast_rotation_nudge` (line 395) check `_is_shutting_down` first.
  - Failure mode: Shutdown event not delivered, or maps not cleared atomically.
  - Protection: `_on_lifecycle_event` is registered in constructor (line 87). Clear operations happen under lock. Test: `test_prepare_shutdown_clears_all_state`.
  - Evidence: `app/services/device_log_stream_service.py:87`

---

## 9) Questions / Needs-Info

- Question: What is the exact field name in MQTT log messages that maps to `Device.device_entity_id`?
- Why it matters: `DeviceLogStreamService.forward_logs` uses `doc.get("entity_id")` at `app/services/device_log_stream_service.py:341`. If the MQTT payload uses a different field name (e.g., `client_id`, `deviceEntityId`, or a nested path), log forwarding silently drops all messages.
- Desired answer: A sample MQTT log message payload from `iotsupport/logsink` showing the field name, or confirmation that `entity_id` is correct. If it differs, either rename the lookup or make it configurable.

---

## 10) Risks & Mitigations (top 3)

- Risk: String-based exception mapping in API endpoints is fragile and could silently break the 403/404 contract.
- Mitigation: Replace string matching with distinct exception types or structured error codes. This is a small refactor confined to `app/api/device_log_stream.py` and `app/services/device_log_stream_service.py`.
- Evidence: Finding #1, `app/api/device_log_stream.py:84,133`

- Risk: MQTT `entity_id` field name assumption may not match reality.
- Mitigation: Verify against actual MQTT payload samples. Add a warning log that fires when the first N documents lack `entity_id` (already partially addressed by the skip logic in `forward_logs`, but no proactive warning is emitted).
- Evidence: `app/services/device_log_stream_service.py:341`, Question #1 above.

- Risk: SSE Gateway may not forward OIDC cookies in connect callback headers, causing all identity bindings to fail.
- Mitigation: Integration test with real SSE Gateway to verify header forwarding. The plan acknowledges this risk. The failure mode is graceful (bind fails with logged warning, subscribe returns 403).
- Evidence: `app/services/device_log_stream_service.py:121-125`, plan Section 15 Risk #2.

---

## 11) Confidence

Confidence: High -- The implementation closely follows the approved plan, all 65 new/modified tests pass, code quality checks are clean, and the two Major findings are isolated to API-layer error mapping rather than core data safety. The architectural decisions (singleton without DB, API-layer nudge placement, lock discipline) are sound and well-documented.
