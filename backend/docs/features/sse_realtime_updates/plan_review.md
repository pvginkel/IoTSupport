# Plan Review: SSE Real-Time Updates

## 1) Summary & Decision

**Readiness**

The revised plan is well-structured, thoroughly researched, and addresses all previously identified architectural concerns. The three Major issues from the initial review (Singleton DB access, rotation nudge placement contradiction, and identity binding header plumbing gap) have been resolved cleanly. Device lookup is now correctly placed at the API layer using the Factory `DeviceService`, rotation nudge calls are consistently at the API layer rather than inside the Factory `RotationService`, and identity binding is done via a dedicated `bind_identity()` call in the SSE callback handler rather than through the observer pattern. The plan correctly follows all project guidelines around layering, DI patterns, lifecycle management, and testing.

**Decision**

`GO` -- All architectural concerns resolved. The plan is implementation-ready with only minor remaining deployment risks (MQTT field name, SSE Gateway header forwarding) that are appropriately flagged with mitigations.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md` (layering: API thin, services own logic) -- Pass -- `plan.md:105-107,133-143` -- API endpoints delegate to services; nudge calls and device lookups are correctly placed at the API layer as orchestration, not business logic.
- `CLAUDE.md` (DI container: Singleton vs Factory) -- Pass -- `plan.md:113-115` -- `DeviceLogStreamService` (Singleton) injected into `LogSinkService` (Singleton) is valid. `RotationService` (Factory) is explicitly NOT modified. Nudge calls placed at API layer.
- `CLAUDE.md` (Singleton DB access pattern) -- Pass -- `plan.md:303-310` -- Device lookup moved to API layer using Factory `DeviceService`. Singleton `DeviceLogStreamService` receives resolved `device_entity_id` directly, avoiding the need for DB access.
- `CLAUDE.md` (error handling: fail fast) -- Pass -- `plan.md:394-436` -- Error cases enumerated with clear status codes, no silent swallowing.
- `CLAUDE.md` (testing requirements) -- Pass -- `plan.md:520-598` -- Comprehensive test scenarios covering service tests, API tests, integration tests, and edge cases.
- `CLAUDE.md` (graceful shutdown) -- Pass -- `plan.md:472-484` -- Lifecycle integration follows the `FrontendVersionService` pattern with `PREPARE_SHUTDOWN` notification.
- `docs/product_brief.md` (scope alignment) -- Pass -- `plan.md:25-66` -- Features serve the admin dashboard (rotation nudge) and device log viewer (log streaming), consistent with the product's purpose.
- `docs/commands/plan_feature.md` (all sections present) -- Pass -- All 16 required sections are present and well-populated.

**Fit with codebase**

- `SSEConnectionManager` -- `plan.md:97-99` -- Correctly identifies the missing `register_on_disconnect` pattern and proposes adding it symmetrically to the existing `register_on_connect` at `sse_connection_manager.py:83-94`.
- `LogSinkService._on_message` -- `plan.md:101-103,313-324` -- Plan correctly notes that `_on_message` processes lines sequentially and proposes collecting parsed documents before forwarding. This requires restructuring `_on_message` to accumulate parsed docs, which is acknowledged.
- `SSE callback handler` -- `plan.md:141-143,284-297` -- Identity binding via `bind_identity()` call in `app/api/sse.py` after `on_connect()` cleanly avoids changing the existing observer signature. The `SSEGatewayRequestInfo.headers` field (`sse_gateway_schema.py:12`) confirms headers are available.
- `Container wiring` -- `plan.md:113-115` -- Singleton-to-Singleton injection (`DeviceLogStreamService` into `LogSinkService`) is valid. No Factory services are modified.
- `Rotation API endpoints` -- `plan.md:133-139` -- Nudge calls at the API layer in `rotation.py` and `iot.py` follow existing patterns where API endpoints orchestrate multiple service calls (e.g., `trigger_fleet_rotation` followed by `rotate_next_queued_device`).

---

## 3) Open Questions & Ambiguities

- Question: What is the exact MQTT message field name that maps to `device_entity_id`?
- Why it matters: If the field name is wrong, all log forwarding silently fails. This is a deployment risk, not a plan risk.
- Needed answer: Inspect actual MQTT log message samples from a running device. The plan's mitigation (warning-level logging on extraction failure) is appropriate.

- Question: Does the SSE Gateway actually forward OIDC cookies/headers in the connect callback payload?
- Why it matters: Identity binding depends on this. If headers are not forwarded, subscribe always returns 403.
- Needed answer: Verify SSE Gateway configuration in staging. The schema (`sse_gateway_schema.py:12`) supports headers, but the gateway must be configured to include them.

---

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: `DeviceLogStreamService.subscribe()` / `unsubscribe()`
- Scenarios:
  - Given identity binding and valid device_entity_id, When subscribe, Then stored in both maps (`tests/services/test_device_log_stream_service.py`)
  - Given mismatched subject, When subscribe, Then `InvalidOperationException` (`tests/services/test_device_log_stream_service.py`)
  - Given already subscribed pair, When subscribe again, Then idempotent success (`tests/services/test_device_log_stream_service.py`)
  - Given active subscription, When unsubscribe, Then removed from both maps (`tests/services/test_device_log_stream_service.py`)
  - Given disconnect, When cleanup fires, Then all subscriptions and identity removed (`tests/services/test_device_log_stream_service.py`)
- Instrumentation: `sse_device_log_subscriptions_active` gauge
- Persistence hooks: DI wiring in `container.py`; no migrations
- Gaps: None
- Evidence: `plan.md:522-540`

- Behavior: `DeviceLogStreamService.forward_logs()`
- Scenarios:
  - Given subscriptions for entity_id, When forward_logs with matching logs, Then SSE event sent (`tests/services/test_device_log_stream_service.py`)
  - Given no subscriptions, When forward_logs, Then no SSE event (`tests/services/test_device_log_stream_service.py`)
- Instrumentation: `sse_device_log_events_sent_total` counter
- Persistence hooks: `LogSinkService` DI wiring updated
- Gaps: None
- Evidence: `plan.md:531-533`

- Behavior: `DeviceLogStreamService.bind_identity()`
- Scenarios:
  - Given OIDC enabled with valid token, When bind_identity, Then identity stored (`tests/services/test_device_log_stream_service.py`)
  - Given OIDC disabled, When bind_identity, Then sentinel stored (`tests/services/test_device_log_stream_service.py`)
  - Given invalid token, When bind_identity, Then warning logged, no identity stored (`tests/services/test_device_log_stream_service.py`)
- Instrumentation: `sse_identity_binding_total` counter
- Persistence hooks: None
- Gaps: None
- Evidence: `plan.md:535-536`

- Behavior: `POST /internal/rotation-nudge`
- Scenarios:
  - Given active connections, When POST, Then 200 and broadcast called (`tests/api/test_internal.py`)
  - Given no connections, When POST, Then 200 (`tests/api/test_internal.py`)
- Instrumentation: `sse_rotation_nudge_broadcast_total` counter
- Persistence hooks: Blueprint registration in `app/__init__.py`
- Gaps: None
- Evidence: `plan.md:574-580`

- Behavior: `SSEConnectionManager.register_on_disconnect`
- Scenarios:
  - Given registered callback, When valid disconnect, Then callback invoked (`tests/services/test_sse_connection_manager.py`)
  - Given stale token, When disconnect, Then callback NOT invoked (`tests/services/test_sse_connection_manager.py`)
  - Given callback that raises, When disconnect, Then other callbacks still execute (`tests/services/test_sse_connection_manager.py`)
- Instrumentation: Existing disconnect counter
- Persistence hooks: None
- Gaps: None
- Evidence: `plan.md:542-550`

- Behavior: Rotation nudge from CronJob
- Scenarios:
  - Given INTERNAL_API_URL set, When rotation_job completes, Then HTTP POST attempted (`tests integration`)
  - Given INTERNAL_API_URL not set, When rotation_job completes, Then no HTTP call (`tests integration`)
  - Given HTTP call fails, When rotation_job runs, Then warning logged, job succeeds (`tests integration`)
- Instrumentation: `sse_rotation_nudge_broadcast_total` with `source=cronjob`
- Persistence hooks: `INTERNAL_API_URL` in `AppEnvironment` and `AppSettings`
- Gaps: None
- Evidence: `plan.md:590-598`

---

## 5) Adversarial Sweep (must find >=3 credible issues or declare why none exist)

- Checks attempted: Singleton DB access, Factory-Singleton injection boundary, observer callback signature mismatch, subscription map consistency under concurrent access, MQTT thread blocking, transaction lifecycle for subscribe endpoint, idempotency semantics consistency, identity map cleanup ordering
- Evidence: `plan.md:303-311` (Singleton DB access resolved), `plan.md:326-335` (API-layer nudge), `plan.md:284-297` (identity binding via bind_identity), `plan.md:384-390` (concurrency controls), `plan.md:386-390` (transaction scope)
- Why the plan holds: The three previously identified Major issues (Singleton DB access, nudge placement, header plumbing) have all been resolved with clean, well-documented design rationales. The concurrency model (RLock with send outside lock) follows the established `SSEConnectionManager` pattern. The identity map cleanup ordering (subscriptions first, then identity) is explicitly documented in the invariants. The subscribe idempotency is now consistently specified as 200 (no-op) throughout.

**Minor -- `_on_message` restructuring not fully specified**

**Evidence:** `plan.md:313-318` -- "After parsing the NDJSON batch, for each line, the existing flow enqueues to ES. New: Before enqueuing, collect all parsed log documents from the batch."

**Why it matters:** The current `_on_message` (`logsink_service.py:176-210`) calls `_process_line` per line, which parses and immediately enqueues. The plan says to collect parsed documents first, then forward. This requires restructuring `_on_message` to accumulate documents, which is not explicitly described. An implementer might try to hook into `_process_line` instead, which would send per-line rather than per-batch.

**Fix suggestion:** Add a note that `_on_message` should be modified to: (1) parse all lines into a list of dicts, (2) call `DeviceLogStreamService.forward_logs(docs)` with the full batch, (3) then enqueue each doc to ES. Alternatively, `forward_logs` could be called after all lines are processed, passing the accumulated docs.

**Confidence:** Medium

---

## 6) Derived-Value & Persistence Invariants (stacked entries)

- Derived value: `_subscriptions_by_entity_id` (reverse index)
  - Source dataset: Unfiltered -- mirrors `_subscriptions_by_request_id` entries.
  - Write / cleanup triggered: Written on subscribe, removed on unsubscribe and disconnect.
  - Guards: Both maps updated atomically under `threading.RLock`. Identity verified before mutation.
  - Invariant: `_subscriptions_by_entity_id[eid]` contains `rid` iff `_subscriptions_by_request_id[rid]` contains `eid`.
  - Evidence: `plan.md:361-366`

- Derived value: `_identity_map` (request_id -> user_subject)
  - Source dataset: Populated from OIDC token validation via `bind_identity()`. One entry per active connection.
  - Write / cleanup triggered: Written on connect (bind_identity), removed on disconnect (after subscription cleanup).
  - Guards: Protected by lock. Only `bind_identity` writes; only disconnect callback removes.
  - Invariant: Every `request_id` in `_subscriptions_by_request_id` has a corresponding entry in `_identity_map`. Cleanup order: subscriptions first, then identity.
  - Evidence: `plan.md:368-373`

- Derived value: Resolved `device_entity_id`
  - Source dataset: DB lookup at API layer (unfiltered, point-in-time).
  - Write / cleanup triggered: Stored in-memory in subscription maps only. No persistent write.
  - Guards: Stale subscriptions are harmless (MQTT messages for deleted devices stop arriving). Cleaned up on disconnect.
  - Invariant: A stale `device_entity_id` never causes incorrect delivery.
  - Evidence: `plan.md:375-380`

---

## 7) Risks & Mitigations (top 3)

- Risk: MQTT log message field name for device identification may not match `device_entity_id`, causing silent forwarding failure.
- Mitigation: Inspect actual MQTT samples before implementation. Add warning-level logging on first N extraction failures to catch mismatches early.
- Evidence: `plan.md:638-640`

- Risk: SSE Gateway may not forward OIDC cookies in connect callback headers, breaking identity binding for all connections.
- Mitigation: Verify SSE Gateway configuration in staging. Schema supports headers (`sse_gateway_schema.py:12`). Integration test with real gateway.
- Evidence: `plan.md:642-644`

- Risk: `LogSinkService._on_message` restructuring could introduce subtle changes to the existing ES write path if not carefully implemented.
- Mitigation: The plan specifies that the ES write path is unchanged ("preserving the existing Elasticsearch enqueue"). Service tests already cover the ES path (`tests/services/test_logsink_service.py`). The forwarding hook should be added after the ES enqueue, not instead of it.
- Evidence: `plan.md:101-103,582-588`

---

## 8) Confidence

Confidence: High -- All architectural issues from the initial review have been cleanly resolved. The plan follows established codebase patterns, correctly handles Singleton/Factory boundaries, and has comprehensive test coverage. The only remaining risks are deployment-configuration concerns (MQTT field names, SSE Gateway headers) that are appropriately flagged with mitigations.
