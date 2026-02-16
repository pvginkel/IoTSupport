# Plan: SSE Frontend Testing Support

## 0) Research Log & Findings

### Areas researched

**Existing testing blueprint patterns.** The project has multiple testing blueprint modules, each following a consistent pattern: a Flask `Blueprint` with a `before_request` hook calling `reject_if_not_testing()`, endpoints decorated with `@public` (from `app.utils.auth`), and Pydantic schemas for OpenAPI generation via `@api.validate()`. Two registration styles exist:

1. `testing_bp` is registered as a child of `api_bp` in `app/startup.py:register_blueprints()` with `url_prefix="/testing"`, resolving to `/api/testing/...`.
2. `testing_sse_bp`, `testing_auth_bp`, `testing_logs_bp`, and `testing_content_bp` are registered directly on the Flask app in `app/__init__.py` with their own `/api/testing/...` prefix.

The new endpoints can follow either pattern. Since the specification mentions "Register as a new blueprint or extend the existing `testing_bp`", and the existing `testing_bp` already handles device-related testing endpoints (coredumps), the cleanest approach is to create a new blueprint registered directly on the app, consistent with `testing_sse_bp` and `testing_content_bp`.

**DeviceLogStreamService.** This singleton (`app/services/device_log_stream_service.py`) manages in-memory subscription maps: `_subscriptions_by_request_id` (forward: request_id -> set of entity_ids) and `_subscriptions_by_entity_id` (reverse: entity_id -> set of request_ids). It exposes `forward_logs(documents)` for log injection and `subscribe`/`unsubscribe` for managing subscriptions. There is no existing public method to read subscription state; a new `get_subscriptions()` method is needed.

**RotationNudgeService.** This singleton (`app/services/rotation_nudge_service.py`) exposes `broadcast(source="web")` which sends a `rotation-updated` SSE event to all connected clients. The nudge endpoint simply calls this method.

**forward_logs() contract.** The method expects documents with `entity_id` and groups them by that field. The testing inject endpoint must add `@timestamp` (current UTC ISO string) and `entity_id` (copied from `device_entity_id`) to each log entry before calling `forward_logs()`.

**Test infrastructure.** Tests in `tests/api/test_testing.py` use a dedicated `testing_app` / `testing_client` / `testing_container` fixture set that creates a Flask app with `FLASK_ENV=testing`. The `testing_sse_bp` has no existing test file. The new tests should follow the `test_testing.py` patterns and reuse its fixtures.

### Conflicts and resolution

The `testing_sse_bp` already uses the URL prefix `/api/testing` and registers routes like `/tasks/start` and `/deployments/version`. The new endpoints need paths `/devices/logs/inject`, `/devices/logs/subscriptions`, and `/rotation/nudge`. These could be added to `testing_sse_bp`, but that module is focused on SSE Gateway integration testing (tasks, version events), not device log or rotation testing. A separate blueprint keeps concerns isolated and matches the pattern of `testing_content_bp` being separate from `testing_bp`. I will create a new `testing_device_sse_bp` blueprint.

---

## 1) Intent & Scope

**User intent**

Add three testing-only API endpoints under `/api/testing/` that allow Playwright end-to-end tests to exercise SSE-driven device log streaming and rotation dashboard refresh features without requiring real MQTT messages from physical devices.

**Prompt quotes**

"POST /api/testing/devices/logs/inject endpoint that forwards constructed log documents to DeviceLogStreamService.forward_logs()"

"GET /api/testing/devices/logs/subscriptions endpoint that returns current SSE subscription state"

"POST /api/testing/rotation/nudge endpoint that broadcasts rotation-updated SSE event via RotationNudgeService.broadcast()"

"All three endpoints are guarded by reject_if_not_testing() (only available when FLASK_ENV=testing)"

"All endpoints are public (no OIDC auth required)"

"All endpoints have Pydantic schemas and @api.validate() decorators for OpenAPI spec generation"

**In scope**

- New API blueprint with three testing endpoints (inject, subscriptions, nudge)
- Pydantic request/response schemas for all three endpoints
- New `get_subscriptions()` method on `DeviceLogStreamService`
- Comprehensive API test coverage for all three endpoints
- Blueprint registration in `app/__init__.py`

**Out of scope**

- Changes to production MQTT or SSE pipeline behavior
- Changes to `RotationNudgeService.broadcast()` or `DeviceLogStreamService.forward_logs()` internals
- Frontend changes (separate repository)
- Database schema changes (no migrations needed)

**Assumptions / constraints**

- `DeviceLogStreamService` and `RotationNudgeService` are already wired as singletons in the service container and require no container changes.
- The inject endpoint does not validate that `device_entity_id` corresponds to an actual device; it injects directly into the SSE pipeline (matching how MQTT-sourced logs work).
- The `@timestamp` field uses Python `datetime.now(UTC).isoformat()` to match Elasticsearch/NDJSON conventions.
- Tests do not require a real SSE Gateway or MQTT broker; they exercise the endpoint logic and service method calls.

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] POST /api/testing/devices/logs/inject endpoint that forwards constructed log documents to DeviceLogStreamService.forward_logs()
- [ ] The inject endpoint adds @timestamp (current UTC) and entity_id (from device_entity_id) to each log entry before forwarding
- [ ] The inject endpoint returns { status: "accepted", forwarded: N } with the count of forwarded entries
- [ ] The inject endpoint validates request body (device_entity_id required, logs array required and non-empty, each log must have message field) returning 400 on invalid input
- [ ] GET /api/testing/devices/logs/subscriptions endpoint that returns current SSE subscription state
- [ ] The subscriptions endpoint supports optional device_entity_id query parameter to filter results
- [ ] The subscriptions endpoint returns { subscriptions: [{ device_entity_id, request_ids }] } format
- [ ] POST /api/testing/rotation/nudge endpoint that broadcasts rotation-updated SSE event via RotationNudgeService.broadcast()
- [ ] The nudge endpoint returns { status: "accepted" }
- [ ] All three endpoints are guarded by reject_if_not_testing() (only available when FLASK_ENV=testing)
- [ ] All endpoints are public (no OIDC auth required)
- [ ] All endpoints have Pydantic schemas and @api.validate() decorators for OpenAPI spec generation
- [ ] All endpoints have comprehensive test coverage (API tests)

---

## 2) Affected Areas & File Map

- Area: `app/api/testing_device_sse.py` (new file)
- Why: New blueprint module containing all three testing endpoints (inject, subscriptions, nudge).
- Evidence: Pattern follows `app/api/testing_content.py:13-22` (separate blueprint with `before_request` guard and `/api/testing/` prefix).

- Area: `app/schemas/testing_device_sse.py` (new file)
- Why: Pydantic request and response schemas for all three endpoints.
- Evidence: Pattern follows `app/schemas/testing.py:1-42` and `app/schemas/testing_content.py:1-24`.

- Area: `app/services/device_log_stream_service.py` — new `get_subscriptions()` method
- Why: The subscriptions endpoint needs to read the in-memory subscription state. Currently no public method exposes this data. Method signature: `def get_subscriptions(self, device_entity_id: str | None = None) -> list[dict[str, Any]]`. Each dict contains `device_entity_id: str` and `request_ids: list[str]` (snapshot copy of the set, not a live reference). The method acquires `self._lock` to iterate `_subscriptions_by_entity_id`, applies the optional filter, copies data, and releases the lock.
- Evidence: `app/services/device_log_stream_service.py:56-62` — the `_subscriptions_by_entity_id` dict and `_lock` that must be held during access.

- Area: `app/__init__.py` — blueprint registration
- Why: The new blueprint must be registered on the Flask app, following the pattern for other testing blueprints. DI wiring is automatic via `container.wire(packages=['app.api'])` at `app/__init__.py:80`, so no manual wiring changes are needed.
- Evidence: `app/__init__.py:80` (package-level wiring), `app/__init__.py:161-181` (testing blueprint registration).

- Area: `tests/api/test_testing_device_sse.py` (new file)
- Why: Comprehensive API test coverage for all three endpoints.
- Evidence: Test patterns follow `tests/api/test_testing.py:182-639` (testing mode fixtures, guard tests, endpoint tests).

---

## 3) Data Model / Contracts

No database tables or migrations are affected. All data is in-memory (SSE subscriptions) or transient (injected log documents).

- Entity / contract: `LogInjectRequest` (request body for POST /api/testing/devices/logs/inject)
- Shape:
  ```json
  {
    "device_entity_id": "string (required)",
    "logs": [
      { "message": "string (required)" }
    ]
  }
  ```
- Refactor strategy: New schema, no backwards compatibility concern.
- Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:17-27`

- Entity / contract: `LogInjectResponse` (response for POST /api/testing/devices/logs/inject)
- Shape:
  ```json
  {
    "status": "accepted",
    "forwarded": 2
  }
  ```
- Refactor strategy: New schema, no backwards compatibility concern.
- Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:39-44`

- Entity / contract: `SubscriptionsQuery` (query params for GET /api/testing/devices/logs/subscriptions)
- Shape:
  ```json
  {
    "device_entity_id": "string (optional)"
  }
  ```
- Refactor strategy: New schema, no backwards compatibility concern.
- Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:62-66`

- Entity / contract: `SubscriptionsResponse` (response for GET /api/testing/devices/logs/subscriptions)
- Shape:
  ```json
  {
    "subscriptions": [
      {
        "device_entity_id": "string",
        "request_ids": ["string"]
      }
    ]
  }
  ```
- Refactor strategy: New schema, no backwards compatibility concern.
- Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:70-79`

- Entity / contract: `NudgeResponse` (response for POST /api/testing/rotation/nudge)
- Shape:
  ```json
  {
    "status": "accepted"
  }
  ```
- Refactor strategy: New schema, no backwards compatibility concern.
- Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:93-98`

---

## 4) API / Integration Surface

- Surface: `POST /api/testing/devices/logs/inject`
- Inputs: JSON body with `device_entity_id` (string, required) and `logs` (array of objects, each with `message` string, required, non-empty).
- Outputs: `200` with `{ "status": "accepted", "forwarded": N }`. Side effect: calls `DeviceLogStreamService.forward_logs()` with enriched documents (each document gets `@timestamp` and `entity_id` added).
- Errors: `400` for missing/invalid fields or empty `logs` array. `400` (ROUTE_NOT_AVAILABLE) if not in testing mode.
- Evidence: `app/services/device_log_stream_service.py:205-266` — `forward_logs()` method expects documents with `entity_id` field.

- Surface: `GET /api/testing/devices/logs/subscriptions`
- Inputs: Optional query parameter `device_entity_id` (string) to filter results.
- Outputs: `200` with `{ "subscriptions": [{ "device_entity_id": "...", "request_ids": ["..."] }] }`. Empty array when no subscriptions exist.
- Errors: `400` (ROUTE_NOT_AVAILABLE) if not in testing mode.
- Evidence: `app/services/device_log_stream_service.py:56-59` — internal subscription maps to be exposed via new public method.

- Surface: `POST /api/testing/rotation/nudge`
- Inputs: Empty body or `{}`.
- Outputs: `200` with `{ "status": "accepted" }`. Side effect: calls `RotationNudgeService.broadcast()` which sends `rotation-updated` SSE event to all connected clients.
- Errors: `400` (ROUTE_NOT_AVAILABLE) if not in testing mode.
- Evidence: `app/services/rotation_nudge_service.py:39-67` — `broadcast()` method with `source` parameter.

---

## 5) Algorithms & State Machines

- Flow: Log injection pipeline (POST /api/testing/devices/logs/inject)
- Steps:
  1. Validate request body via Pydantic schema (device_entity_id required, logs non-empty, each log has message).
  2. For each log entry in `logs`, construct a document dict: copy the original log entry, add `"@timestamp"` set to `datetime.now(UTC).isoformat()`, add `"entity_id"` set to the value of `device_entity_id`.
  3. Call `device_log_stream_service.forward_logs(documents)` with the full list of enriched documents.
  4. Return `{ "status": "accepted", "forwarded": len(documents) }`.
- States / transitions: None.
- Hotspots: `forward_logs()` acquires a lock briefly to copy subscriber lists, then sends SSE events outside the lock. No performance concern for testing volumes.
- Evidence: `app/services/device_log_stream_service.py:205-266`

- Flow: Subscription state retrieval (GET /api/testing/devices/logs/subscriptions)
- Steps:
  1. Parse optional `device_entity_id` query parameter.
  2. Call `device_log_stream_service.get_subscriptions(device_entity_id=...)` which returns `list[dict[str, Any]]`.
  3. The service method acquires `self._lock`, iterates `_subscriptions_by_entity_id`, optionally filters by entity_id, builds a list of `{ "device_entity_id": str, "request_ids": list[str] }` dicts (copying sets to lists), releases the lock.
  4. Return the subscriptions list in the response envelope.
- States / transitions: None.
- Hotspots: Lock held only during the dict copy; subscription maps are small (test scenarios have 1-2 subscriptions).
- Evidence: `app/services/device_log_stream_service.py:56-59`

- Flow: Rotation nudge broadcast (POST /api/testing/rotation/nudge)
- Steps:
  1. Call `rotation_nudge_service.broadcast(source="testing")`.
  2. Return `{ "status": "accepted" }`.
- States / transitions: None.
- Hotspots: None. The broadcast is a single HTTP call to the SSE Gateway.
- Evidence: `app/services/rotation_nudge_service.py:39-67`

---

## 6) Derived State & Invariants

- Derived value: `forwarded` count in inject response
  - Source: Length of the `logs` array from the request body (unfiltered).
  - Writes / cleanup: No persistent writes; the count is returned in the response and not stored.
  - Guards: Pydantic schema enforces `logs` is non-empty.
  - Invariant: `forwarded` equals the number of documents passed to `forward_logs()`, regardless of whether subscribers exist.
  - Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:46` ("forwarded is the number of log entries passed to DeviceLogStreamService.forward_logs()")

- Derived value: Subscription list in subscriptions response
  - Source: In-memory `_subscriptions_by_entity_id` dict in `DeviceLogStreamService`, optionally filtered by `device_entity_id` query parameter.
  - Writes / cleanup: Read-only; no writes or cleanup triggered.
  - Guards: Lock acquisition ensures consistent snapshot. Optional filter is applied within the lock.
  - Invariant: Returned subscriptions reflect the exact state at the moment the lock is held; stale reads are acceptable since this is a polling endpoint.
  - Evidence: `app/services/device_log_stream_service.py:56-62`

- Derived value: `@timestamp` enrichment on injected documents
  - Source: `datetime.now(UTC)` called at inject time.
  - Writes / cleanup: Written into the transient document dicts passed to `forward_logs()`. No persistent storage.
  - Guards: Always added; no conditional logic.
  - Invariant: Every document forwarded to `forward_logs()` must contain `@timestamp` and `entity_id` fields.
  - Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:35`

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: No database transactions involved. All three endpoints operate on in-memory state only.
- Atomic requirements: None. The inject endpoint calls `forward_logs()` with the full batch; `forward_logs()` handles its own lock internally. The subscriptions endpoint reads a consistent snapshot under lock.
- Retry / idempotency: All three endpoints are safe to retry. Inject is not idempotent (duplicate calls forward duplicate logs), but this is expected for testing use. Subscriptions is a pure read. Nudge broadcasts are idempotent (same empty event each time).
- Ordering / concurrency controls: `DeviceLogStreamService` uses `threading.RLock` for subscription map access (`device_log_stream_service.py:62`). No additional concurrency controls needed in the API layer.
- Evidence: `app/services/device_log_stream_service.py:62` (lock), `app/services/rotation_nudge_service.py:39-67` (stateless broadcast)

---

## 8) Errors & Edge Cases

- Failure: Missing `device_entity_id` in inject request body
- Surface: POST /api/testing/devices/logs/inject
- Handling: Pydantic validation returns 400 with field-level error details.
- Guardrails: `device_entity_id: str` marked as required in schema with `min_length=1`.
- Evidence: Pattern from `app/schemas/testing.py:13-18` (required string field with min_length).

- Failure: Empty `logs` array in inject request body
- Surface: POST /api/testing/devices/logs/inject
- Handling: Pydantic validation returns 400 (`min_length=1` on the logs list field).
- Guardrails: Schema enforces `logs: list[LogEntrySchema]` with `min_length=1`.
- Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:32` ("1-N log entries").

- Failure: Log entry missing `message` field
- Surface: POST /api/testing/devices/logs/inject
- Handling: Pydantic validation returns 400 with nested field error.
- Guardrails: `LogEntrySchema` has `message: str` as required field.
- Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:33` ("Each entry must have at least a message field").

- Failure: No active SSE subscriptions when injecting logs
- Surface: POST /api/testing/devices/logs/inject
- Handling: `forward_logs()` silently drops undeliverable documents; endpoint still returns 200 with `forwarded: N`. This is documented and expected.
- Guardrails: None needed; the spec explicitly states "If no SSE client is currently subscribed to the target device, the logs are silently dropped."
- Evidence: `docs/features/sse_realtime_updates/frontend_testing_support.md:15`, `app/services/device_log_stream_service.py:223-225`.

- Failure: Endpoints called when FLASK_ENV is not "testing"
- Surface: All three endpoints
- Handling: `reject_if_not_testing()` returns 400 with `ROUTE_NOT_AVAILABLE` error code.
- Guardrails: `before_request` hook on the blueprint.
- Evidence: `app/api/testing_guard.py:10-31`.

---

## 9) Observability / Telemetry

No new Prometheus metrics are needed. The existing metrics in `DeviceLogStreamService` and `RotationNudgeService` already cover the relevant operations:

- Signal: `sse_device_log_events_sent_total`
- Type: Counter
- Trigger: When `forward_logs()` sends SSE events to subscribed clients (incremented inside `DeviceLogStreamService.forward_logs()`).
- Labels / fields: `status` ("success" or "error")
- Consumer: Existing Prometheus dashboard
- Evidence: `app/services/device_log_stream_service.py:31-35`

- Signal: `sse_rotation_nudge_broadcast_total`
- Type: Counter
- Trigger: When `broadcast()` is called. The nudge endpoint will pass `source="testing"` to differentiate from production broadcasts.
- Labels / fields: `source` ("web", "cronjob", or "testing")
- Consumer: Existing Prometheus dashboard
- Evidence: `app/services/rotation_nudge_service.py:17-21`

- Signal: `sse_device_log_subscriptions_active`
- Type: Gauge
- Trigger: Updated on subscribe/unsubscribe/disconnect within `DeviceLogStreamService`.
- Labels / fields: None
- Consumer: Existing Prometheus dashboard
- Evidence: `app/services/device_log_stream_service.py:27-30`

---

## 10) Background Work & Shutdown

No new background workers or threads are introduced. All three endpoints are synchronous request handlers. The services they call (`DeviceLogStreamService`, `RotationNudgeService`) already have shutdown integration via `LifecycleCoordinator`:

- Worker / job: `DeviceLogStreamService` (existing singleton)
- Trigger cadence: Event-driven (on inject call or MQTT callback)
- Responsibilities: Forwards logs to SSE subscribers; manages subscription maps.
- Shutdown handling: `PREPARE_SHUTDOWN` lifecycle event sets `_is_shutting_down=True` and clears all maps. `forward_logs()` returns early when shutting down.
- Evidence: `app/services/device_log_stream_service.py:310-319`

- Worker / job: `RotationNudgeService` (existing singleton)
- Trigger cadence: Event-driven (on nudge call)
- Responsibilities: Broadcasts rotation-updated SSE events.
- Shutdown handling: `PREPARE_SHUTDOWN` lifecycle event sets `_is_shutting_down=True`; `broadcast()` returns `False` when shutting down.
- Evidence: `app/services/rotation_nudge_service.py:69-74`

---

## 11) Security & Permissions

- Concern: Testing endpoints must not be accessible in production.
- Touchpoints: `reject_if_not_testing()` before_request hook on the new blueprint.
- Mitigation: The guard checks `settings.is_testing` (derived from `FLASK_ENV=testing`). Production deployments use `FLASK_ENV=production`. The guard returns a `400 ROUTE_NOT_AVAILABLE` response when not in testing mode.
- Residual risk: If someone deploys with `FLASK_ENV=testing` in production, the endpoints would be accessible. This is acceptable as it requires explicit misconfiguration and the endpoints only affect in-memory SSE state.
- Evidence: `app/api/testing_guard.py:10-31`, `app/api/testing_content.py:16-21` (same pattern).

- Concern: Endpoints are public (no OIDC authentication).
- Touchpoints: The blueprint is registered directly on the Flask app (not as a child of `api_bp`), which bypasses the OIDC `before_request` hook entirely. No `@public` decorator is needed -- this matches the pattern used by `testing_content_bp`, `testing_sse_bp`, `testing_auth_bp`, and `testing_logs_bp`.
- Mitigation: Testing blueprints registered directly on the app bypass OIDC by design. Additionally, the endpoints are only active when `FLASK_ENV=testing`.
- Residual risk: None beyond the FLASK_ENV misconfiguration scenario above.
- Evidence: `app/__init__.py:160-181` (testing blueprints registered on app, not api_bp), `app/api/testing_content.py` and `app/api/testing_sse.py` (no `@public` decorator used).

---

## 12) UX / UI Impact

No direct UI changes in this plan. The endpoints are consumed by Playwright test code in the frontend repository. The frontend testing support document (`docs/features/sse_realtime_updates/frontend_testing_support.md:103-128`) describes the expected Playwright flows but those are out of scope for this backend plan.

---

## 13) Deterministic Test Plan

- Surface: POST /api/testing/devices/logs/inject
- Scenarios:
  - Given FLASK_ENV=testing, When POST with valid device_entity_id and logs array, Then return 200 with `{ "status": "accepted", "forwarded": N }` where N equals the length of the logs array.
  - Given FLASK_ENV=testing, When POST with valid payload, Then each document passed to `forward_logs()` contains `@timestamp` (UTC ISO string) and `entity_id` (matching `device_entity_id`).
  - Given FLASK_ENV=testing, When POST with missing `device_entity_id`, Then return 400.
  - Given FLASK_ENV=testing, When POST with empty `logs` array, Then return 400.
  - Given FLASK_ENV=testing, When POST with log entry missing `message` field, Then return 400.
  - Given FLASK_ENV=testing, When POST with missing body, Then return 400.
  - Given FLASK_ENV=development (not testing), When POST to inject endpoint, Then return 400 with `ROUTE_NOT_AVAILABLE`.
- Fixtures / hooks: Reuse `testing_app`/`testing_client`/`testing_container` fixtures from `tests/api/test_testing.py`. Mock or access `DeviceLogStreamService` from container to verify `forward_logs()` calls. Use `unittest.mock.patch.object` on `device_log_stream_service.forward_logs` to capture call arguments.
- Gaps: No integration test with a real SSE client (would require concurrent SSE connection); the API test verifies the endpoint calls the service correctly.
- Evidence: `tests/api/test_testing.py:104-166` (fixture patterns), `tests/api/test_testing.py:511-639` (endpoint test patterns).

- Surface: GET /api/testing/devices/logs/subscriptions
- Scenarios:
  - Given FLASK_ENV=testing and no active subscriptions, When GET /api/testing/devices/logs/subscriptions, Then return 200 with `{ "subscriptions": [] }`.
  - Given FLASK_ENV=testing and subscriptions exist for entity "device_a" and "device_b", When GET without filter, Then return both subscriptions with their request_ids.
  - Given FLASK_ENV=testing and subscriptions exist, When GET with `device_entity_id=device_a`, Then return only the subscription for "device_a".
  - Given FLASK_ENV=testing and subscriptions exist, When GET with `device_entity_id=nonexistent`, Then return 200 with `{ "subscriptions": [] }`.
  - Given FLASK_ENV=development, When GET subscriptions endpoint, Then return 400 with `ROUTE_NOT_AVAILABLE`.
- Fixtures / hooks: Reuse `testing_app`/`testing_client`/`testing_container`. Directly populate `DeviceLogStreamService._subscriptions_by_entity_id` and `_subscriptions_by_request_id` maps via the singleton instance from the container to set up subscription state without needing real SSE connections. Note: this couples tests to internal data structures, but is an acceptable trade-off since establishing real SSE connections in pytest would be disproportionately complex. If the internal maps are refactored, only the test fixture setup needs updating.
- Gaps: None.
- Evidence: `tests/api/test_testing.py:104-166` (fixture patterns).

- Surface: POST /api/testing/rotation/nudge
- Scenarios:
  - Given FLASK_ENV=testing, When POST /api/testing/rotation/nudge (empty body), Then return 200 with `{ "status": "accepted" }`.
  - Given FLASK_ENV=testing, When POST /api/testing/rotation/nudge with empty JSON `{}`, Then return 200 with `{ "status": "accepted" }`.
  - Given FLASK_ENV=testing, When POST nudge, Then `RotationNudgeService.broadcast()` is called with `source="testing"`.
  - Given FLASK_ENV=development, When POST nudge endpoint, Then return 400 with `ROUTE_NOT_AVAILABLE`.
- Fixtures / hooks: Reuse `testing_app`/`testing_client`/`testing_container`. Mock `RotationNudgeService.broadcast` to verify it is called and capture the `source` argument.
- Gaps: None.
- Evidence: `tests/api/test_testing.py:104-166` (fixture patterns).

---

## 14) Implementation Slices

- Slice: 1 - Schemas
- Goal: Define all Pydantic request/response schemas so the API contracts are established.
- Touches: `app/schemas/testing_device_sse.py` (new file).
- Dependencies: None.

- Slice: 2 - Service method
- Goal: Add `get_subscriptions()` method to `DeviceLogStreamService` to expose subscription state.
- Touches: `app/services/device_log_stream_service.py`.
- Dependencies: None.

- Slice: 3 - API blueprint
- Goal: Implement all three endpoints in a new blueprint, wire to services, register in app factory.
- Touches: `app/api/testing_device_sse.py` (new file), `app/__init__.py`.
- Dependencies: Slices 1 and 2.

- Slice: 4 - Tests
- Goal: Comprehensive API test coverage for all three endpoints.
- Touches: `tests/api/test_testing_device_sse.py` (new file).
- Dependencies: Slice 3.

---

## 15) Risks & Open Questions

- Risk: `DeviceLogStreamService` is a singleton; accessing its internal subscription maps in the `get_subscriptions()` method requires holding the lock. Under high concurrency this could briefly block the MQTT callback thread.
- Impact: Negligible; testing scenarios have minimal concurrency and the lock is held only for a dict snapshot.
- Mitigation: Keep the lock scope minimal (copy data under lock, format outside lock), consistent with existing patterns in `forward_logs()`.

- Risk: The `forward_logs()` call count (`forwarded`) always equals the input array length, regardless of whether any SSE client received the events. Playwright tests that depend on `forwarded > 0` as proof of delivery may have false confidence.
- Impact: Low; the spec explicitly documents this behavior and the Playwright test flow uses subscription polling before injection.
- Mitigation: Document in endpoint response schema description that `forwarded` does not guarantee delivery.

- Risk: If the new blueprint name or import collides with existing `testing_sse_bp`, it could cause registration errors.
- Impact: App fails to start.
- Mitigation: Use a distinct blueprint name (`testing_device_sse`) and module name (`testing_device_sse.py`); verify no naming collision.

---

## 16) Confidence

Confidence: High -- All three endpoints are thin API wrappers around existing service methods with well-understood contracts, following established testing blueprint patterns. No database, migration, or production logic changes are required.
