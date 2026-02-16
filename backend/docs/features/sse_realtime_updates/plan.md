# Plan: SSE Real-Time Updates

## 0) Research Log & Findings

**SSE Gateway infrastructure.** The backend already has a fully functional SSE Gateway integration. `SSEConnectionManager` (`app/services/sse_connection_manager.py`) manages bidirectional `request_id <-> token` mappings and supports both targeted send (by `request_id`) and broadcast (pass `None`). The SSE callback endpoint (`app/api/sse.py:45-133`) handles connect/disconnect callbacks. The connect callback already receives the full client request URL and headers (via `SSEGatewayConnectCallback.request`), which makes extracting OIDC tokens from forwarded headers straightforward.

**Observer pattern on SSEConnectionManager.** The manager already supports `register_on_connect` callbacks (line 83-94), used by `FrontendVersionService` to send version events on new connections. There is no `register_on_disconnect` callback yet -- one is needed for cleanup when SSE connections drop.

**LogSinkService.** `LogSinkService` (`app/services/logsink_service.py`) is a singleton that subscribes to the MQTT topic `iotsupport/logsink` (line 42). Its `_on_message` callback receives raw NDJSON payloads and processes each line as a JSON document. Each document contains fields from the device -- critically, a field from which we can match the `device_entity_id`. The service enqueues processed documents for batch writing to Elasticsearch. The SSE forwarding path needs to run in parallel, before or after the enqueue step, using the same parsed data.

**Device model.** `Device.device_entity_id` (`app/models/device.py:59`) stores the entity ID extracted from device config. This is the field incoming MQTT log messages use for identification. The subscribe endpoint needs to resolve `device_id` (the API-facing identifier) to `device_entity_id` for matching.

**Rotation service.** `RotationService` (`app/services/rotation_service.py`) is a Factory service. Key mutation points that should emit nudges: `trigger_fleet_rotation` (line 119), `_rotate_device` (line 335), `_process_timeouts` (line 233), and `rotate_next_queued_device` (line 378, chain rotation). The rotation API (`app/api/rotation.py`) calls these.

**CLI rotation job.** The rotation job (`app/startup.py:162-205`) runs `rotation_service.process_rotation_job()` which internally calls `trigger_fleet_rotation`, `_process_timeouts`, and `_rotate_next_queued_device`. Since this runs in a separate CLI process without SSE connections, it needs to call an internal HTTP endpoint on the web process.

**AppSettings/config.** `INTERNAL_API_URL` is a new environment variable. It belongs in `AppSettings`/`AppEnvironment` (`app/app_config.py`) since it is IoT-deployment-specific, not infrastructure.

**Auth service.** `AuthService.validate_token()` (`app/services/auth_service.py:131`) returns an `AuthContext` with `subject`, `email`, `name`, and `roles`. This is exactly what identity binding needs for the SSE connect callback.

**Conflicts resolved.** The `SSEConnectionManager.on_disconnect` currently has no observer pattern -- only `on_connect` has one. The plan adds `register_on_disconnect` symmetrically. The `LogSinkService` currently has no awareness of SSE; the plan injects a subscription registry dependency without altering its ES write path.

---

## 1) Intent & Scope

**User intent**

Add two real-time SSE features: (1) stream device log messages from `LogSinkService` to subscribed frontend clients, and (2) broadcast lightweight "rotation-updated" nudge events to all connections when rotation state changes, including when the CronJob rotation process triggers changes in a separate process.

**Prompt quotes**

"Stream device log messages in real time to frontend clients viewing a device's log screen."
"When rotation state changes occur in the web process, a lightweight 'rotation-updated' SSE event is broadcast to all connected clients."
"The Kubernetes CronJob (rotation_job) runs in a separate process without SSE connections. To ensure the dashboard updates for CronJob-initiated changes, the CronJob calls an internal HTTP endpoint on the web process to trigger a nudge broadcast."
"A new environment variable (INTERNAL_API_URL) provides the cluster-internal endpoint the CronJob uses for this call."
"The internal notification endpoint lives on `/` (not `/api/`) to separate it from the user-facing API."

**In scope**

- New `DeviceLogStreamService` (singleton) managing per-connection device log subscriptions
- Identity binding: extract and validate OIDC token from SSE connect callback headers, store `request_id -> user_subject`
- REST endpoints for subscribe/unsubscribe to device log streams
- SSE forwarding of matching log messages from `LogSinkService` to subscribed clients
- Rotation nudge broadcast via SSE on state changes
- Internal notification endpoint (on `/`, not `/api/`) for CronJob to trigger rotation nudge
- `INTERNAL_API_URL` environment variable for CronJob configuration
- CronJob calls internal endpoint after rotation processing
- `register_on_disconnect` callback on `SSEConnectionManager` for cleanup
- Comprehensive service and API tests

**Out of scope**

- Frontend implementation
- Changes to existing `GET /devices/{id}/logs` REST endpoint
- Changes to rotation state machine logic
- Per-screen SSE targeting for rotation events (broadcast is sufficient)
- Elasticsearch write path changes

**Assumptions / constraints**

- The SSE Gateway forwards browser headers (including OIDC cookies) in the connect callback's `request.headers` field.
- Log messages from MQTT contain a field (e.g., `entity_id` or `client_id`) that maps to `Device.device_entity_id`.
- The internal notification endpoint does not require OIDC auth since it is on `/` (not proxied publicly) and is only accessible within the cluster.
- Scale is small (up to 200 devices, handful of concurrent dashboard users) -- in-memory subscription maps suffice.

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Device log subscription: REST endpoint to subscribe an SSE connection (by request_id) to a device's log stream
- [ ] Device log unsubscription: REST endpoint to unsubscribe from a device's log stream
- [ ] Multiple simultaneous device subscriptions per SSE connection supported
- [ ] Identity binding: on SSE connect callback, extract and validate OIDC token from forwarded headers, store request_id → user_subject mapping
- [ ] Identity verification: subscription endpoints verify the caller's OIDC subject matches the stored subject for the provided request_id
- [ ] Cleanup on SSE disconnect: remove all subscriptions and identity mappings for disconnected request_id
- [ ] Log forwarding: LogSinkService forwards matching log messages via SSE to subscribed clients (parallel to Elasticsearch write)
- [ ] Subscribe endpoint resolves device_id → device_entity_id for MQTT message matching
- [ ] Log events are batched (multiple log lines per SSE event)
- [ ] Rotation nudge: broadcast a lightweight "rotation-updated" SSE event to all connections on rotation state changes
- [ ] Rotation nudge emitted on: fleet trigger, device rotation start, timeout processing, rotation completion (chain rotation)
- [ ] Internal notification endpoint on `/` (not `/api/`) for CronJob to trigger rotation nudge broadcast
- [ ] New environment variable `INTERNAL_API_URL` for the cluster-internal endpoint the CronJob calls
- [ ] CronJob rotation_job calls the internal endpoint after processing to notify the web process
- [ ] All new services and endpoints have comprehensive tests (service tests and API tests)

---

## 2) Affected Areas & File Map

- Area: `app/services/device_log_stream_service.py` (new)
- Why: Core service managing device log subscriptions, identity binding, SSE forwarding, and rotation nudge broadcast.
- Evidence: No equivalent exists; `FrontendVersionService` (`app/services/frontend_version_service.py:1-148`) provides the pattern for SSE-aware singleton services.

- Area: `app/services/sse_connection_manager.py` -- `on_disconnect` / `register_on_disconnect`
- Why: Add `register_on_disconnect` observer pattern so `DeviceLogStreamService` can clean up subscriptions when a connection drops.
- Evidence: `app/services/sse_connection_manager.py:83-94` -- existing `register_on_connect` pattern; `on_disconnect` at line 170 does not notify observers.

- Area: `app/services/logsink_service.py` -- `_on_message` / `_process_line`
- Why: Add a parallel SSE forwarding path that calls into `DeviceLogStreamService` when log messages arrive, preserving the existing Elasticsearch enqueue.
- Evidence: `app/services/logsink_service.py:176-210` -- `_on_message` processes NDJSON lines; the forwarding hook goes here.

- Area: `app/api/device_log_stream.py` (new)
- Why: REST endpoints for subscribe, unsubscribe, and the callback hook into `SSEConnectionManager` connect.
- Evidence: Pattern from `app/api/sse.py:45-133` for SSE callback handling; `app/api/rotation.py:1-120` for REST endpoint patterns.

- Area: `app/api/internal.py` (new)
- Why: Internal notification endpoint on `/` for CronJob rotation nudge trigger.
- Evidence: `app/__init__.py:150-156` -- `health_bp` and `metrics_bp` are registered directly on app (not under `/api`), establishing the pattern for non-API blueprints.

- Area: `app/services/container.py`
- Why: Wire `DeviceLogStreamService` as a singleton with dependencies on `SSEConnectionManager`, `AuthService`, and `LifecycleCoordinator`. Add `DeviceLogStreamService` dependency to `LogSinkService` (Singleton-to-Singleton injection). `RotationService` (Factory) is NOT modified -- rotation nudge calls are placed at the API layer instead.
- Evidence: `app/services/container.py:102-107` -- SSE connection manager singleton; `app/services/container.py:170-177` -- LogSinkService singleton.

- Area: `app/__init__.py`
- Why: Register the new `internal_bp` blueprint on the app (not on `api_bp`).
- Evidence: `app/__init__.py:150-167` -- existing pattern for registering non-API blueprints.

- Area: `app/startup.py` -- `register_blueprints`
- Why: Register `device_log_stream_bp` on `api_bp` (under `/api`).
- Evidence: `app/startup.py:40-57` -- existing blueprint registration.

- Area: `app/app_config.py` -- `AppEnvironment` / `AppSettings`
- Why: Add `INTERNAL_API_URL` environment variable and corresponding settings field.
- Evidence: `app/app_config.py:24-76` -- `AppEnvironment`; `app/app_config.py:79-191` -- `AppSettings`.

- Area: `app/startup.py` -- `rotation_job` CLI command
- Why: After `process_rotation_job`, call the internal endpoint to notify the web process of rotation changes.
- Evidence: `app/startup.py:162-205` -- existing rotation job handler.

- Area: `app/api/rotation.py`
- Why: After `trigger_fleet_rotation` and `rotate_next_queued_device` service calls return, inject `DeviceLogStreamService` and call `broadcast_rotation_nudge()` at the API layer. This keeps `RotationService` (a Factory) free of Singleton dependencies.
- Evidence: `app/api/rotation.py:53-89` -- `trigger_fleet_rotation` endpoint; `app/services/container.py:214-222` -- `RotationService` is a Factory provider.

- Area: `app/api/iot.py` -- `_check_rotation_completion`
- Why: After rotation completion (chain rotation), call `DeviceLogStreamService.broadcast_rotation_nudge()` at the API layer. Inject `DeviceLogStreamService` into the endpoint function signature.
- Evidence: `app/api/iot.py:123-171` -- `_check_rotation_completion` calls `rotation_service.rotate_next_queued_device()`.

- Area: `app/api/sse.py` -- `handle_callback` (connect action)
- Why: After `sse_connection_manager.on_connect()`, extract headers from the connect callback payload and call `device_log_stream_service.bind_identity(request_id, headers)`. This avoids changing the `register_on_connect` callback signature, which only passes `request_id`.
- Evidence: `app/api/sse.py:85-113` -- connect callback handler; `app/schemas/sse_gateway_schema.py:8-14` -- `SSEGatewayRequestInfo` includes `headers`.

- Area: `app/schemas/device_log_stream.py` (new)
- Why: Pydantic schemas for subscribe/unsubscribe request/response validation.
- Evidence: Schema naming convention from `app/schemas/rotation.py`.

- Area: `tests/services/test_device_log_stream_service.py` (new)
- Why: Comprehensive service tests for subscription management, identity binding, forwarding, cleanup.
- Evidence: `tests/services/test_logsink_service.py` -- pattern for testing singleton services.

- Area: `tests/api/test_device_log_stream.py` (new)
- Why: API tests for subscribe/unsubscribe endpoints and identity verification.
- Evidence: `tests/api/test_rotation.py` -- pattern for API tests.

- Area: `tests/api/test_internal.py` (new)
- Why: API tests for internal notification endpoint.
- Evidence: `tests/api/test_rotation.py`.

- Area: `tests/services/test_sse_connection_manager.py` (new or extended)
- Why: Test the new `register_on_disconnect` observer pattern.
- Evidence: No existing test file for SSEConnectionManager; create one.

---

## 3) Data Model / Contracts

- Entity / contract: `DeviceLogSubscription` (in-memory, not persisted)
- Shape:
  ```json
  {
    "_subscriptions_by_request_id": {
      "<request_id>": ["<device_entity_id_1>", "<device_entity_id_2>"]
    },
    "_subscriptions_by_entity_id": {
      "<device_entity_id>": ["<request_id_1>", "<request_id_2>"]
    },
    "_identity_map": {
      "<request_id>": "<user_subject>"
    }
  }
  ```
- Refactor strategy: Pure in-memory, no persistence needed. State is transient and rebuilt on reconnect.
- Evidence: `app/services/frontend_version_service.py:34` -- `_pending_version` dict pattern for in-memory per-connection state.

- Entity / contract: `SubscribeRequest` (Pydantic schema)
- Shape:
  ```json
  {
    "request_id": "abc123",
    "device_id": 42
  }
  ```
- Refactor strategy: New schema, no backwards compatibility needed.
- Evidence: Schema conventions in `app/schemas/rotation.py`.

- Entity / contract: `UnsubscribeRequest` (Pydantic schema)
- Shape:
  ```json
  {
    "request_id": "abc123",
    "device_id": 42
  }
  ```
- Refactor strategy: New schema.
- Evidence: Schema conventions in `app/schemas/rotation.py`.

- Entity / contract: SSE event `device-logs`
- Shape:
  ```json
  {
    "device_entity_id": "sensor.living_room",
    "logs": [
      {"message": "...", "@timestamp": "...", "level": "..."}
    ]
  }
  ```
- Refactor strategy: New event type. Logs are batched matching the NDJSON batch from MQTT.
- Evidence: Change brief specifies "Log events are batched (multiple log lines per SSE event, matching the NDJSON batches from MQTT)."

- Entity / contract: SSE event `rotation-updated`
- Shape:
  ```json
  {}
  ```
- Refactor strategy: New event type. Empty payload -- frontend re-fetches dashboard on receipt.
- Evidence: Change brief specifies "a lightweight 'rotation-updated' SSE event is broadcast to all connected clients (no payload or minimal payload)."

- Entity / contract: `INTERNAL_API_URL` (AppSettings)
- Shape: Added to `AppEnvironment` and `AppSettings`:
  ```
  INTERNAL_API_URL: str | None = None   # e.g., "http://iotsupport-backend:5000"
  internal_api_url: str | None = None
  ```
- Refactor strategy: New field, no migration needed.
- Evidence: `app/app_config.py:24-76` -- `AppEnvironment`; `app/app_config.py:79-191` -- `AppSettings`.

---

## 4) API / Integration Surface

- Surface: `POST /api/device-logs/subscribe`
- Inputs: JSON body `{"request_id": "<id>", "device_id": <int>}`
- Outputs: `200 {"status": "subscribed", "device_entity_id": "<entity_id>"}` on success. Idempotent: subscribing the same (request_id, device_id) pair twice returns 200.
- Errors: `400` missing fields; `403` request_id identity mismatch; `404` device not found or device has no entity_id
- Note: The API layer resolves `device_id -> device_entity_id` using the Factory `DeviceService` (which has a proper request-scoped DB session), then passes the resolved `device_entity_id` to the Singleton `DeviceLogStreamService.subscribe()`. This avoids the Singleton needing direct DB access.
- Evidence: Pattern from `app/api/rotation.py:53-89`; `app/services/device_service.py` for device lookup.

- Surface: `POST /api/device-logs/unsubscribe`
- Inputs: JSON body `{"request_id": "<id>", "device_id": <int>}`
- Outputs: `200 {"status": "unsubscribed"}`
- Errors: `400` missing fields; `403` request_id identity mismatch; `404` subscription not found
- Evidence: Pattern from `app/api/rotation.py:53-89`.

- Surface: `POST /internal/rotation-nudge`
- Inputs: No body required (or empty JSON body).
- Outputs: `200 {"status": "ok"}`
- Errors: `500` if broadcast fails (logged, not retried)
- Evidence: `app/__init__.py:150-156` -- non-API blueprint pattern; `app/api/health.py` for simple internal endpoints.

- Surface: SSE event `device-logs` (targeted to subscribed `request_id`)
- Inputs: Triggered by MQTT message arrival on `iotsupport/logsink`
- Outputs: SSE event with batched log lines matching subscribed `device_entity_id`
- Errors: Send failure logged, connection cleaned up on 404
- Evidence: `app/services/sse_connection_manager.py:232-292` -- `send_event` method.

- Surface: SSE event `rotation-updated` (broadcast to all connections)
- Inputs: Triggered by rotation state changes
- Outputs: SSE event with empty payload
- Errors: Broadcast failures logged, stale connections cleaned up
- Evidence: `app/services/sse_connection_manager.py:251-278` -- broadcast mode.

- Surface: CLI `rotation-job` (modified)
- Inputs: Unchanged
- Outputs: Unchanged, plus HTTP POST to `INTERNAL_API_URL/internal/rotation-nudge` after processing
- Errors: HTTP call failure logged but does not fail the job (best-effort notification)
- Evidence: `app/startup.py:162-205` -- existing rotation job.

---

## 5) Algorithms & State Machines

- Flow: SSE connect with identity binding
- Steps:
  1. SSE Gateway calls `/api/sse/callback` with `action=connect`, forwarding browser headers in the callback payload.
  2. Callback handler (`app/api/sse.py`) extracts `request_id` from URL query params (existing logic).
  3. Callback handler registers connection with `SSEConnectionManager.on_connect()` (existing logic; notifies observers like `FrontendVersionService`).
  4. **New:** After `on_connect()` returns, the callback handler extracts headers from `connect_callback.request.headers` and calls `device_log_stream_service.bind_identity(request_id, headers)`.
  5. `bind_identity` extracts the OIDC access token from the forwarded headers (e.g., `Authorization` header or `Cookie` header containing the access token).
  6. If OIDC is enabled, validates token via `AuthService.validate_token()`, stores `request_id -> subject` in `_identity_map`.
  7. If OIDC is disabled (dev/test), stores a sentinel subject (e.g., `"local-user"`).
  8. If token validation fails, logs warning. Identity map is NOT populated; subsequent subscribe calls for this `request_id` will fail with 403. The SSE connection remains active for unauthenticated events (e.g., rotation nudges).
- States / transitions: None (stateless handshake).
- Hotspots: Token validation is cached by `PyJWKClient` (5-min TTL), so overhead is minimal. The `bind_identity` call runs synchronously inside the SSE callback handler.
- Evidence: `app/api/sse.py:85-113` -- connect callback; `app/schemas/sse_gateway_schema.py:8-14` -- `SSEGatewayRequestInfo` includes `headers`.
- Design rationale: Identity binding is done in the SSE callback handler (`app/api/sse.py`) rather than via the `register_on_connect` observer pattern because the observer callback only receives `request_id`, not the full callback payload with headers. This avoids changing the existing observer signature used by `FrontendVersionService`.

- Flow: Device log subscription
- Steps:
  1. Frontend POSTs to `/api/device-logs/subscribe` with `request_id` and `device_id`.
  2. Endpoint extracts caller's OIDC subject from `g.auth_context` (set by `before_request` hook).
  3. **API layer** resolves `device_id` -> `Device.device_entity_id` using the Factory `DeviceService` (which has a request-scoped DB session). Returns 404 if device not found or `device_entity_id` is null.
  4. Endpoint calls `DeviceLogStreamService.subscribe(request_id, device_entity_id, caller_subject)`.
  5. Service verifies `_identity_map[request_id] == caller_subject` (identity verification). Raises `InvalidOperationException` on mismatch (API returns 403).
  6. Service adds `device_entity_id` to `_subscriptions_by_request_id[request_id]` and `request_id` to `_subscriptions_by_entity_id[device_entity_id]`. Idempotent: if already subscribed, returns success.
  7. Returns success with `device_entity_id`.
- States / transitions: None.
- Hotspots: DB lookup is per-subscribe call (not per-message). At most ~200 devices, negligible.
- Design rationale: The device lookup is done at the API layer (not inside the Singleton `DeviceLogStreamService`) because `DeviceLogStreamService` is a Singleton and per `CLAUDE.md` guidelines, Singletons should not directly use request-scoped DB sessions. The Factory `DeviceService` handles session lifecycle properly.
- Evidence: `app/models/device.py:59` -- `device_entity_id` field; `app/services/device_service.py:1-50`; `CLAUDE.md` -- Singleton DB access pattern.

- Flow: Log message forwarding via SSE
- Steps:
  1. MQTT message arrives on `iotsupport/logsink`.
  2. `LogSinkService._on_message(payload)` is called (existing).
  3. After parsing the NDJSON batch, for each line, the existing flow enqueues to ES.
  4. New: Before enqueuing, collect all parsed log documents from the batch. After processing all lines, call `DeviceLogStreamService.forward_logs(batch_documents)`.
  5. `forward_logs` groups documents by `device_entity_id` (or equivalent MQTT field).
  6. For each `device_entity_id` with active subscriptions, sends a single SSE event containing all matching log lines to each subscribed `request_id`.
  7. SSE event name: `device-logs`. Payload: `{"device_entity_id": "...", "logs": [...]}`.
- States / transitions: None.
- Hotspots: Forwarding runs in the MQTT callback thread. SSE send is HTTP POST to gateway (2s timeout). If no subscribers, the check is O(1) dict lookup. With subscribers, serial send per subscriber per entity_id. At small scale (handful of viewers), this is fine.
- Evidence: `app/services/logsink_service.py:176-243` -- message processing; `app/services/sse_connection_manager.py:232-292` -- send_event.

- Flow: Rotation nudge broadcast (web process)
- Steps:
  1. Rotation state change occurs via API call (fleet trigger in `app/api/rotation.py`, chain rotation in `app/api/iot.py`).
  2. After the `RotationService` method returns, the **API endpoint** calls `DeviceLogStreamService.broadcast_rotation_nudge()`. The `DeviceLogStreamService` is injected into the endpoint via `Provide[ServiceContainer.device_log_stream_service]`.
  3. Service calls `sse_connection_manager.send_event(None, {}, "rotation-updated", "rotation")`.
  4. SSE Gateway delivers event to all connected clients.
- States / transitions: None.
- Hotspots: Broadcast is serial over connections. At small scale, sub-second.
- Design rationale: Nudge calls are placed at the API layer rather than inside `RotationService` because `RotationService` is a Factory service and `DeviceLogStreamService` is a Singleton. Injecting a Singleton into a Factory is technically possible in dependency-injector but muddies the ownership boundary. The API-layer approach is consistent with the existing pattern where API endpoints orchestrate service calls.
- Evidence: `app/services/sse_connection_manager.py:251-278` -- broadcast mode; `app/services/container.py:214-222` -- `RotationService` is Factory.

- Flow: Rotation nudge from CronJob (separate process)
- Steps:
  1. CronJob runs `rotation_job` CLI command.
  2. After `process_rotation_job()` completes and commits, the job POSTs to `INTERNAL_API_URL/internal/rotation-nudge`.
  3. Web process receives POST, calls `DeviceLogStreamService.broadcast_rotation_nudge()`.
  4. If HTTP call fails, log warning and continue (best-effort).
- States / transitions: None.
- Hotspots: Single HTTP call, 5s timeout. Failure is non-fatal.
- Evidence: `app/startup.py:162-205` -- rotation job.

- Flow: SSE disconnect cleanup
- Steps:
  1. SSE Gateway calls `/api/sse/callback` with `action=disconnect`.
  2. `SSEConnectionManager.on_disconnect(token)` removes connection mappings.
  3. New: After removing mappings, `SSEConnectionManager` notifies `register_on_disconnect` callbacks with `request_id`.
  4. `DeviceLogStreamService._on_disconnect_callback(request_id)` removes all subscriptions for that `request_id` from both maps and removes the identity mapping.
- States / transitions: None.
- Hotspots: None. Cleanup is O(number of subscriptions for that request_id).
- Evidence: `app/services/sse_connection_manager.py:170-218` -- `on_disconnect`.

---

## 6) Derived State & Invariants

- Derived value: `_subscriptions_by_entity_id` (reverse index)
  - Source: Built from `_subscriptions_by_request_id` entries (unfiltered). Updated atomically with forward map.
  - Writes / cleanup: Written on subscribe, removed on unsubscribe and disconnect cleanup.
  - Guards: Both maps updated under the same lock. Subscribe verifies identity before modifying. Disconnect cleanup iterates forward map entries.
  - Invariant: `_subscriptions_by_entity_id[eid]` contains `rid` if and only if `_subscriptions_by_request_id[rid]` contains `eid`.
  - Evidence: N/A (new code); pattern from `app/services/sse_connection_manager.py:72-76` -- bidirectional mappings.

- Derived value: `_identity_map` (request_id -> user_subject)
  - Source: Populated from OIDC token validation during SSE connect callback. Unfiltered (one entry per active connection).
  - Writes / cleanup: Written on connect, removed on disconnect.
  - Guards: Protected by lock. Only the connect callback writes; only disconnect callback removes.
  - Invariant: Every `request_id` in `_subscriptions_by_request_id` MUST have a corresponding entry in `_identity_map`. Disconnect cleanup removes identity map entry only after removing all subscriptions.
  - Evidence: N/A (new code).

- Derived value: Resolved `device_entity_id` (from `device_id` on subscribe)
  - Source: DB lookup of `Device.device_entity_id` where `Device.id == device_id`.
  - Writes / cleanup: No persistent write. The resolved value is stored only in-memory in subscription maps.
  - Guards: If device is deleted after subscription, the subscription becomes a no-op (no matching MQTT messages). Disconnect cleanup removes stale subscriptions.
  - Invariant: The `device_entity_id` stored in subscriptions was valid at subscribe time. Stale subscriptions are harmless (no matches) and cleaned up on disconnect.
  - Evidence: `app/models/device.py:59` -- `device_entity_id`.

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: The subscribe endpoint uses a DB session (Factory `DeviceService` at the API layer) to resolve `device_id` -> `device_entity_id`. The session is committed/rolled back by Flask's `teardown_request`. The subscription maps in `DeviceLogStreamService` (Singleton) are in-memory and do not participate in DB transactions.
- Atomic requirements: Both forward and reverse subscription maps must be updated atomically under the same lock. Identity map must be consistent with subscription maps (identity entry exists for every subscribed request_id).
- Retry / idempotency: Subscribe is idempotent -- subscribing the same (request_id, device_entity_id) pair twice returns 200 (no-op). Unsubscribe for a non-existent subscription returns 404. The CronJob's internal nudge HTTP call is fire-and-forget; retrying is unnecessary since the next CronJob tick will trigger another nudge anyway.
- Ordering / concurrency controls: `DeviceLogStreamService` uses `threading.RLock` (following `SSEConnectionManager` pattern at line 81). MQTT callback thread and Flask request threads may access subscription maps concurrently. The lock serializes all mutations and reads of the maps. SSE `send_event` calls happen outside the lock to avoid blocking.
- Evidence: `app/services/sse_connection_manager.py:81` -- `threading.RLock()`; `app/services/frontend_version_service.py:33` -- `threading.RLock()`.

---

## 8) Errors & Edge Cases

- Failure: Subscribe with invalid/missing `request_id` (no active SSE connection)
- Surface: `POST /api/device-logs/subscribe`
- Handling: 403 -- the identity map has no entry for this request_id, meaning no SSE connect was processed.
- Guardrails: Identity verification is the first check in subscribe flow.
- Evidence: New code; pattern from `app/api/rotation.py` error handling.

- Failure: Subscribe with mismatched OIDC subject (cross-user hijacking attempt)
- Surface: `POST /api/device-logs/subscribe`
- Handling: 403 -- caller's subject (from `g.auth_context`) does not match stored subject for `request_id`.
- Guardrails: Identity verification check runs on every subscribe/unsubscribe call.
- Evidence: Change brief: "Subscription endpoints verify the caller's identity matches the stored subject for the provided request_id."

- Failure: Subscribe to device with no `device_entity_id`
- Surface: `POST /api/device-logs/subscribe`
- Handling: 404 -- device found but entity_id is null, meaning log matching is impossible.
- Guardrails: Null check on `device.device_entity_id` after DB lookup.
- Evidence: `app/models/device.py:59` -- nullable field.

- Failure: SSE Gateway send returns 404 (connection gone)
- Surface: `DeviceLogStreamService.forward_logs()` via `SSEConnectionManager.send_event()`
- Handling: Connection cleaned up by `SSEConnectionManager._send_event_to_token` (existing logic at line 337-349). Subscription maps cleaned up by subsequent disconnect callback.
- Guardrails: Existing SSE connection manager cleanup.
- Evidence: `app/services/sse_connection_manager.py:337-349`.

- Failure: OIDC token validation fails during SSE connect callback
- Surface: `DeviceLogStreamService._on_connect_callback()`
- Handling: Log warning. Do not store identity mapping. Subsequent subscribe calls for this request_id will fail with 403. The SSE connection itself remains active (it may be used for non-authenticated events like rotation nudges).
- Guardrails: Try/catch around token validation in connect callback.
- Evidence: `app/services/auth_service.py:131-243` -- validate_token raises AuthenticationException.

- Failure: Internal rotation nudge HTTP call fails (from CronJob)
- Surface: CLI rotation job
- Handling: Log warning, continue. The nudge is best-effort; the frontend will see stale data until the next manual refresh or nudge.
- Guardrails: HTTP call wrapped in try/except with 5s timeout.
- Evidence: Change brief: "CronJob calls an internal HTTP endpoint on the web process."

- Failure: MQTT message has no identifiable entity_id field
- Surface: `DeviceLogStreamService.forward_logs()`
- Handling: Skip forwarding for that log line. Log at debug level (high volume).
- Guardrails: Defensive check for entity_id field presence.
- Evidence: `app/services/logsink_service.py:222-243` -- `_process_line` parsing.

---

## 9) Observability / Telemetry

- Signal: `sse_device_log_subscriptions_active`
- Type: Gauge
- Trigger: Updated on subscribe/unsubscribe/disconnect cleanup in `DeviceLogStreamService`.
- Labels / fields: None (total active subscriptions across all connections).
- Consumer: Prometheus dashboard.
- Evidence: `app/services/sse_connection_manager.py:46-49` -- `SSE_GATEWAY_ACTIVE_CONNECTIONS` gauge pattern.

- Signal: `sse_device_log_events_sent_total`
- Type: Counter
- Trigger: Incremented each time a `device-logs` SSE event is sent (per request_id per batch).
- Labels / fields: `status` (success/error).
- Consumer: Prometheus dashboard.
- Evidence: `app/services/sse_connection_manager.py:31-39` -- `SSE_GATEWAY_EVENTS_SENT_TOTAL` counter pattern.

- Signal: `sse_rotation_nudge_broadcast_total`
- Type: Counter
- Trigger: Incremented each time a `rotation-updated` broadcast is attempted.
- Labels / fields: `source` (web/cronjob).
- Consumer: Prometheus dashboard.
- Evidence: Pattern from existing metrics.

- Signal: `sse_identity_binding_total`
- Type: Counter
- Trigger: Incremented on SSE connect when identity binding is attempted.
- Labels / fields: `status` (success/failed/skipped).
- Consumer: Prometheus dashboard for monitoring auth failures.
- Evidence: `app/services/auth_service.py:17-25` -- auth metrics pattern.

---

## 10) Background Work & Shutdown

- Worker / job: `DeviceLogStreamService` (singleton, no background thread)
- Trigger cadence: Event-driven (callbacks from SSE connect/disconnect, subscribe/unsubscribe API calls, MQTT message forwarding).
- Responsibilities: Manages in-memory subscription state. Sends SSE events via `SSEConnectionManager`.
- Shutdown handling: Register for `LifecycleEvent.PREPARE_SHUTDOWN` via lifecycle coordinator. On prepare shutdown, clear all subscription maps and identity maps. This prevents forwarding during shutdown. No waiter needed since there are no background threads.
- Evidence: `app/services/frontend_version_service.py:138-148` -- lifecycle notification pattern.

- Worker / job: CronJob internal nudge HTTP call (in rotation_job CLI)
- Trigger cadence: Once per rotation job invocation, after processing.
- Responsibilities: Single HTTP POST to web process internal endpoint.
- Shutdown handling: Not applicable (CLI process exits after job completes).
- Evidence: `app/startup.py:162-205`.

---

## 11) Security & Permissions

- Concern: Identity binding -- preventing cross-user SSE hijacking
- Touchpoints: `app/api/sse.py` callback handler calls `DeviceLogStreamService.bind_identity()` (token extraction), subscribe/unsubscribe endpoints (identity verification).
- Mitigation: OIDC token validated on SSE connect via `bind_identity(request_id, headers)`. Subject stored per request_id. Every subscribe/unsubscribe call verifies caller's `g.auth_context.subject` matches stored subject. When OIDC is disabled (dev/test), a fixed sentinel subject is used, and `/api` before_request hook does not set `g.auth_context`, so the service accepts any caller.
- Residual risk: If the SSE Gateway callback does not forward the OIDC cookie headers, identity binding fails silently (connect callback logs warning, subscribe returns 403). This is a deployment configuration issue.
- Evidence: `app/schemas/sse_gateway_schema.py:8-14` -- headers forwarded; `app/services/auth_service.py:131` -- `validate_token`.

- Concern: Internal endpoint access control
- Touchpoints: `POST /internal/rotation-nudge`
- Mitigation: Endpoint is on `/` (not `/api/`), so it is not proxied through the public ingress. Only accessible within the Kubernetes cluster network. No OIDC auth required.
- Residual risk: Any pod in the cluster can call this endpoint. Acceptable given the trusted network environment and the endpoint's side-effect is benign (triggers UI refresh).
- Evidence: `app/__init__.py:150-156` -- health/metrics endpoints follow same pattern; `docs/product_brief.md` -- "Users in trusted network environments."

---

## 12) UX / UI Impact

- Entry point: Device log viewer page (frontend)
- Change: Frontend subscribes to device log stream via REST on page open, receives logs via SSE `device-logs` event. Deduplicates with initial REST fetch.
- User interaction: Real-time log streaming without polling.
- Dependencies: New `POST /api/device-logs/subscribe` and `POST /api/device-logs/unsubscribe` endpoints. SSE event `device-logs`.
- Evidence: Change brief frontend flow description.

- Entry point: Rotation dashboard page (frontend)
- Change: Frontend listens for `rotation-updated` SSE event and re-fetches dashboard data.
- User interaction: Dashboard auto-refreshes on rotation state changes without manual refresh.
- Dependencies: SSE event `rotation-updated`. No new REST endpoints (uses existing dashboard endpoint).
- Evidence: Change brief: "The frontend, upon receiving the nudge, re-fetches the dashboard endpoint."

---

## 13) Deterministic Test Plan

- Surface: `DeviceLogStreamService` (service tests)
- Scenarios:
  - Given an active SSE connection with identity binding, When subscribe is called with matching subject and valid device_entity_id, Then subscription is stored in both forward and reverse maps.
  - Given an active SSE connection, When subscribe is called with mismatched subject, Then `InvalidOperationException` is raised.
  - Given an active SSE connection, When subscribe is called with unknown request_id (no identity), Then `InvalidOperationException` is raised.
  - Given no active connection for request_id, When subscribe is called, Then `InvalidOperationException` is raised.
  - Given an already-subscribed (request_id, device_entity_id) pair, When subscribe is called again, Then returns success (idempotent, no duplicate entries in maps).
  - Given an active subscription, When unsubscribe is called with matching subject, Then subscription is removed from both maps.
  - Given an active subscription, When disconnect callback fires, Then all subscriptions and identity mapping for that request_id are removed.
  - Given subscriptions for device_entity_id "sensor.a", When forward_logs is called with matching logs, Then SSE send_event is called with correct payload for each subscribed request_id.
  - Given subscriptions for device_entity_id "sensor.a", When forward_logs is called with non-matching entity_id, Then no SSE event is sent.
  - Given no subscriptions, When forward_logs is called, Then no SSE event is sent (fast path).
  - Given active connections, When broadcast_rotation_nudge is called, Then SSE broadcast with event name "rotation-updated" and empty payload is sent.
  - Given OIDC disabled, When bind_identity is called, Then identity map stores sentinel subject.
  - Given OIDC enabled with invalid token in headers, When bind_identity is called, Then identity map is NOT populated and warning is logged.
  - Given active subscriptions, When PREPARE_SHUTDOWN lifecycle event fires, Then all maps are cleared.
- Fixtures / hooks: Mock `SSEConnectionManager`, mock `AuthService`. `StubLifecycleCoordinator` for shutdown tests. Note: `DeviceService` is NOT mocked at the service level because device lookup is done at the API layer; the service receives `device_entity_id` directly.
- Gaps: None.
- Evidence: `tests/services/test_logsink_service.py` -- pattern for singleton service tests with mocks.

- Surface: `SSEConnectionManager.register_on_disconnect` (service tests)
- Scenarios:
  - Given a registered on_disconnect callback, When on_disconnect is called with valid token, Then callback is invoked with the request_id.
  - Given a registered on_disconnect callback, When on_disconnect is called with stale token, Then callback is NOT invoked.
  - Given multiple on_disconnect callbacks, When disconnect occurs, Then all callbacks are invoked.
  - Given a callback that raises an exception, When disconnect occurs, Then other callbacks still execute.
- Fixtures / hooks: Direct instantiation of `SSEConnectionManager` with test gateway URL.
- Gaps: None.
- Evidence: `app/services/sse_connection_manager.py:83-94` -- on_connect callback pattern to mirror.

- Surface: `POST /api/device-logs/subscribe` (API tests)
- Scenarios:
  - Given valid request_id with identity binding and valid device_id, When POST subscribe, Then 200 with device_entity_id.
  - Given valid request_id but device not found, When POST subscribe, Then 404.
  - Given valid request_id but device has no entity_id, When POST subscribe, Then 404.
  - Given request_id with no identity binding, When POST subscribe, Then 403.
  - Given request_id with mismatched subject, When POST subscribe, Then 403.
  - Given missing request_id in body, When POST subscribe, Then 400.
  - Given missing device_id in body, When POST subscribe, Then 400.
- Fixtures / hooks: Mock `DeviceLogStreamService` and mock `DeviceService` (for device_entity_id lookup) in container. Test client with request context.
- Gaps: None.
- Evidence: `tests/api/test_rotation.py` -- API test patterns.

- Surface: `POST /api/device-logs/unsubscribe` (API tests)
- Scenarios:
  - Given active subscription, When POST unsubscribe with matching subject, Then 200.
  - Given no active subscription, When POST unsubscribe, Then 404.
  - Given request_id with mismatched subject, When POST unsubscribe, Then 403.
- Fixtures / hooks: Mock `DeviceLogStreamService` in container.
- Gaps: None.
- Evidence: `tests/api/test_rotation.py`.

- Surface: `POST /internal/rotation-nudge` (API tests)
- Scenarios:
  - Given active connections, When POST nudge, Then 200 and broadcast is called.
  - Given no active connections, When POST nudge, Then 200 (broadcast returns False, still OK).
- Fixtures / hooks: Mock `DeviceLogStreamService` in container.
- Gaps: None.
- Evidence: `tests/api/test_rotation.py`.

- Surface: `LogSinkService` with SSE forwarding (integration)
- Scenarios:
  - Given `DeviceLogStreamService` injected into `LogSinkService`, When MQTT message arrives, Then `forward_logs` is called with parsed documents in addition to ES enqueue.
  - Given `DeviceLogStreamService` is None (disabled), When MQTT message arrives, Then ES enqueue proceeds normally without error.
- Fixtures / hooks: Mock `DeviceLogStreamService`, mock MQTT, `TestLifecycleCoordinator`.
- Gaps: None.
- Evidence: `tests/services/test_logsink_service.py`.

- Surface: Rotation nudge emission points (integration)
- Scenarios:
  - Given `DeviceLogStreamService` injected, When `trigger_fleet_rotation` is called via API, Then `broadcast_rotation_nudge` is called.
  - Given `DeviceLogStreamService` injected, When rotation completes (chain rotation in `/iot/config`), Then `broadcast_rotation_nudge` is called.
  - Given `DeviceLogStreamService` injected, When rotation job CLI runs and INTERNAL_API_URL is set, Then HTTP POST to internal endpoint is attempted.
  - Given INTERNAL_API_URL is not set, When rotation job CLI runs, Then no HTTP call is made (logged as debug).
- Fixtures / hooks: Mock HTTP client for CLI test. Mock `DeviceLogStreamService` for API tests.
- Gaps: None.
- Evidence: `tests/api/test_rotation.py`; `tests/api/test_iot.py`.

---

## 14) Implementation Slices

- Slice: 1 -- SSEConnectionManager disconnect observer
- Goal: Add `register_on_disconnect` to `SSEConnectionManager` with tests.
- Touches: `app/services/sse_connection_manager.py`, `tests/services/test_sse_connection_manager.py` (new).
- Dependencies: None. Foundation for slice 2.

- Slice: 2 -- DeviceLogStreamService core
- Goal: Implement subscription management, identity binding, forwarding logic, and rotation nudge broadcast. Full service tests.
- Touches: `app/services/device_log_stream_service.py` (new), `app/services/container.py`, `tests/services/test_device_log_stream_service.py` (new).
- Dependencies: Slice 1.

- Slice: 3 -- REST endpoints for subscribe/unsubscribe + schemas
- Goal: Expose subscribe/unsubscribe as REST endpoints with identity verification. API tests.
- Touches: `app/api/device_log_stream.py` (new), `app/schemas/device_log_stream.py` (new), `app/startup.py`, `tests/api/test_device_log_stream.py` (new).
- Dependencies: Slice 2.

- Slice: 4 -- LogSinkService SSE forwarding integration
- Goal: Wire `DeviceLogStreamService` into `LogSinkService` so MQTT log messages are forwarded to subscribed SSE clients.
- Touches: `app/services/logsink_service.py`, `app/services/container.py`, `tests/services/test_logsink_service.py`.
- Dependencies: Slice 2.

- Slice: 5 -- Rotation nudge (web process)
- Goal: Emit rotation-updated SSE broadcast from rotation API endpoints and IoT config endpoint (chain rotation).
- Touches: `app/api/rotation.py`, `app/api/iot.py`, `app/services/container.py`, `tests/api/test_rotation.py`, `tests/api/test_iot.py`.
- Dependencies: Slice 2.

- Slice: 6 -- Internal endpoint + CronJob nudge
- Goal: Add internal notification endpoint, `INTERNAL_API_URL` config, and CronJob HTTP call.
- Touches: `app/api/internal.py` (new), `app/__init__.py`, `app/app_config.py`, `app/startup.py`, `tests/api/test_internal.py` (new).
- Dependencies: Slice 2.

---

## 15) Risks & Open Questions

- Risk: MQTT log messages may not contain `device_entity_id` as a top-level field -- the field name might differ (e.g., `entity_id`, `client_id`, or nested).
- Impact: Log forwarding will silently miss all messages if the field name is wrong.
- Mitigation: Inspect actual MQTT log message samples to confirm field name. Add a configurable field-name mapping if needed. Log at warning level when entity_id extraction fails for the first N messages.

- Risk: SSE Gateway connect callback may not forward OIDC cookies in `request.headers`.
- Impact: Identity binding fails for all connections; subscribe always returns 403.
- Mitigation: Verify SSE Gateway configuration forwards `Cookie` header. The `SSEGatewayRequestInfo.headers` field already exists (`app/schemas/sse_gateway_schema.py:12`). Integration test with real gateway to confirm.

- Risk: (RESOLVED) The `_on_connect_callback` needs access to the forwarded headers, but `SSEConnectionManager.on_connect` only passes `request_id` to callbacks, not the full callback payload.
- Impact: Cannot extract OIDC token from headers in the callback.
- Mitigation: Identity binding is done in the SSE callback handler (`app/api/sse.py`) by calling `DeviceLogStreamService.bind_identity(request_id, headers)` directly after `on_connect()`, rather than via the observer pattern. This avoids changing the existing `register_on_connect` callback signature. See Section 5, "SSE connect with identity binding" flow and File Map entry for `app/api/sse.py`.

- Risk: Holding the subscription lock during SSE send (HTTP call) could block MQTT callback thread.
- Impact: Log ingestion to Elasticsearch could be delayed.
- Mitigation: Copy subscriber list under lock, then send events outside lock (following existing `SSEConnectionManager` pattern at line 147-149).

- Risk: Large log batches could cause SSE events that are too large for the gateway.
- Impact: SSE Gateway may reject oversized events.
- Mitigation: Cap SSE event payload size. If batch exceeds limit, split into multiple SSE events. For initial implementation, rely on MQTT batch sizes being reasonable (they are already bounded by `QUEUE_MAXSIZE=100`).

---

## 16) Confidence

Confidence: High -- The codebase has well-established patterns for SSE event delivery, singleton services with lifecycle management, and observer callbacks. The feature is entirely in-memory with no schema migrations, and all integration points are well-understood from the existing `FrontendVersionService` and `TaskService` implementations. Architectural concerns around Singleton DB access, nudge placement, and identity binding header plumbing have been resolved in this revision.
