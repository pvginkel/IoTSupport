# SSE System Redesign — Technical Plan

## 0) Research Log & Findings

### Discovery Work

Researched the current SSE infrastructure across multiple layers:

**ConnectionManager (`app/services/connection_manager.py:1-335`)**
- Manages bidirectional mappings: identifier <-> token
- Current identifier format: `task:abc123` or `version:xyz789`
- Sends events via HTTP POST to SSE Gateway `/internal/send`
- Extracts service type from identifier prefix for metrics
- Implements connection replacement logic (close old when new connects)

**VersionService (`app/services/version_service.py:1-294`)**
- Maintains local subscriber queues (`_subscribers: dict[str, Queue[VersionEvent]]`)
- Stores pending events (`_pending_events`) for pre-connection delivery
- Tracks activity (`_last_activity`) for idle cleanup
- Runs background cleanup thread (`_cleanup_worker`)
- Dual delivery: SSE Gateway via ConnectionManager + local queues

**TaskService (`app/services/task_service.py:1-611`)**
- Maintains event queues per task (`_event_queues: dict[str, Queue[TaskEvent]]`)
- Implements `on_connect` and `on_disconnect` for SSE Gateway
- TaskProgressHandle broadcasts via ConnectionManager with queue fallback
- Closes connection on task completion (sends `close=True`)
- Integrates with shutdown coordinator (waiter + notification)

**SSE API (`app/api/sse.py:1-196`)**
- Single `/callback` endpoint routes to TaskService or VersionService
- Parses URL to extract `task_id` or `request_id`
- Routes based on path: `/api/sse/tasks` → task, `/api/sse/utils/version` → version
- Authenticates callbacks via shared secret in production

**Testing API (`app/api/testing.py:1-320`)**
- No demo SSE endpoints found (only `trigger_version_deployment` and `start_test_task`)
- Log streaming endpoint uses local queue pattern (`/testing/logs/stream`)

**Metrics (`app/services/metrics_service.py`)**
- `record_sse_gateway_connection(service, action)` with `service_type` dimension
- `record_sse_gateway_event(service, status)` with `service_type` dimension
- `record_sse_gateway_send_duration(service, duration)` with `service_type` dimension

**Integration Tests**
- `test_sse_gateway_version.py`: tests pending events and post-connection delivery
- `test_sse_gateway_tasks.py`: tests task progress events and completion

### Key Findings

1. **Dual delivery complexity**: Both services maintain local queues AND use ConnectionManager
2. **Identifier format coupling**: Service type extracted from `prefix:id` format
3. **Connection close on task completion**: TaskService sends `close=True` after terminal events
4. **No demo endpoints**: Testing API doesn't have local subscriber demo endpoints to remove
5. **Background workers**: VersionService runs cleanup thread for idle subscribers
6. **Metrics labels**: All SSE metrics use `service_type` dimension (task/version)

### Conflicts Resolved

**Observer pattern vs callback registration**: Change brief mentions "observer pattern" for connect notifications. Implemented as callback registration in ConnectionManager to avoid circular dependencies.

**Broadcast vs request_id parameter**: Change brief specifies `send_event(request_id=None)` for broadcast, but current signature uses positional `identifier`. Plan uses optional parameter approach to support both targeted and broadcast.

**Pending version storage**: Change brief says "single pending version (class variable)" but this was shorthand for "service-level state". Plan uses an instance variable (`self._pending_version`) that stores one pending version keyed by request_id, protected by the existing `_lock`.

## 1) Intent & Scope

### User intent

Eliminate HTTP/1.1 connection limit issues by consolidating to a single SSE endpoint that broadcasts all events (version updates, task progress) to all connected clients. Simplify architecture by removing per-task connections, local subscriber queues, pending event tracking, activity monitoring, and cleanup workers. Frontend will filter events client-side by task_id.

### Prompt quotes

"Single SSE Endpoint" — "One endpoint: `/api/sse/stream?request_id=<id>`" — "All events (version updates, task progress) broadcast to all connected clients"

"ConnectionManager Changes" — "Track connections by `request_id` (not `task:X` or `version:Y` format)" — "send_event(request_id, event_data, event_name): request_id=None → broadcast to all connections"

"VersionService Changes" — "Remove: `_subscribers`, `_pending_events`, `_last_activity`, cleanup worker" — "queue_version_event(request_id, version, changelog): stores ONE pending version (class variable)"

"TaskService Changes" — "Broadcast all task events via `ConnectionManager.send_event(None, event)`" — "No connection close on task completion"

"No backwards compatibility" — "Frontend will be updated immediately after backend changes"

### In scope

- Refactor ConnectionManager to track by request_id and support broadcast
- Add observer callback registration to ConnectionManager
- Simplify VersionService: remove queues/cleanup, add connect callback, single pending version
- Simplify TaskService: remove queues, broadcast events, keep shutdown waiter
- Simplify SSE API: single endpoint, parse request_id from query params
- Update integration tests for new endpoint and broadcast model
- Retain service_type metric dimension by having callers pass it explicitly to send_event
- Document frontend changes in separate file

### Out of scope

- Frontend implementation (documented separately)
- Changes to task execution logic or TaskProgressHandle interface
- Changes to version fetching logic
- Migration strategy (no backwards compatibility)
- Changes to SSE Gateway itself
- Changes to authentication/authorization
- Changes to other testing endpoints

### Assumptions / constraints

- Frontend changes will be deployed atomically with backend
- SSE Gateway remains unchanged (existing `/internal/send` API)
- No active SSE connections during deployment (accept brief disconnect)
- Playwright tests will adapt to new pending version storage (single per request_id)
- Loss of un-received messages is acceptable (browser connects before user actions)
- Shutdown coordinator integration remains unchanged

## 2) Affected Areas & File Map

**Area: ConnectionManager service**
- Why: Core refactoring to support request_id tracking, broadcast, and observer callbacks
- Evidence: `app/services/connection_manager.py:32-335` — current implementation uses identifier-based tracking, `_extract_service_type` relies on prefix format

**Area: VersionService**
- Why: Remove local queues, cleanup thread; add connect callback; simplify pending events
- Evidence: `app/services/version_service.py:42-44` — `_subscribers`, `_pending_events`, `_last_activity` dicts; `app/services/version_service.py:242-276` — cleanup worker thread

**Area: TaskService**
- Why: Remove event queues, simplify to broadcast-only model
- Evidence: `app/services/task_service.py:114` — `_event_queues: dict[str, Queue[TaskEvent]]`; `app/services/task_service.py:178-230` — `on_connect` drains queues; `app/services/task_service.py:245-278` — `_send_event_to_gateway` closes connection on terminal events

**Area: TaskProgressHandle**
- Why: Simplify to broadcast-only (remove queue fallback)
- Evidence: `app/services/task_service.py:58-81` — `_send_progress_event` tries gateway then falls back to queue

**Area: SSE API endpoint**
- Why: Simplify to single endpoint, parse request_id from URL query params in SSE API layer, no service routing
- Evidence: `app/api/sse.py:47-91` — `_route_to_service` parses task/version paths (will be replaced with simple query param extraction); `app/api/sse.py:93-196` — `/callback` endpoint routes to services (will call ConnectionManager only)
- Parsing responsibility: SSE API extracts `request_id` from callback URL query params (`/api/sse/stream?request_id=X`), validates it's non-empty and doesn't contain ':', then calls `ConnectionManager.on_connect(request_id, token, url)` with the plain request_id string (no prefix)

**Area: SSE schemas**
- Why: No changes needed (existing callback schemas remain)
- Evidence: `app/schemas/sse_gateway_schema.py:1-55` — schemas for connect/disconnect callbacks and send requests are unchanged

**Area: MetricsService**
- Why: Update connection metrics to remove service_type (unified connection), retain service_type for event metrics (passed explicitly by callers)
- Evidence: `app/services/metrics_service.py:156-176` — `record_sse_gateway_connection` will drop `service` parameter; `record_sse_gateway_event`, `record_sse_gateway_send_duration` keep `service` parameter

**Area: Service container wiring**
- Why: No changes needed (ConnectionManager, VersionService, TaskService already wired)
- Evidence: `app/services/container.py:110-228` — providers already defined; `app/__init__.py:135` — `app.api.sse` already in wire_modules

**Area: Integration tests**
- Why: Update to use new endpoint URL and validate broadcast behavior
- Evidence: `tests/integration/test_sse_gateway_version.py:1-100` — tests connect to `/api/sse/utils/version?request_id=X`; `tests/integration/test_sse_gateway_tasks.py:1-100` — tests connect to `/api/sse/tasks?task_id=X`

**Area: Frontend changes documentation**
- Why: Create new document describing required frontend updates
- Evidence: Change brief line 82-88 — "Create `docs/features/sse_redesign/frontend_changes.md`"

## 3) Data Model / Contracts

**Entity / contract: ConnectionManager connection tracking**
- Shape:
  ```python
  # OLD: _connections: dict[str, dict[str, str]]  # identifier -> {token, url}
  #      identifier format: "task:abc123" or "version:xyz789"

  # NEW: _connections: dict[str, dict[str, str]]  # request_id -> {token, url}
  #      request_id format: plain UUID string, no prefix
  ```
- Refactor strategy: Breaking change, no backwards compatibility. Frontend updated atomically.
- Evidence: `app/services/connection_manager.py:53-56` — current bidirectional mappings

**Entity / contract: ConnectionManager.send_event signature**
- Shape:
  ```python
  # OLD: send_event(identifier: str, event_data: dict, event_name: str, close: bool)
  #      identifier required, always targeted send

  # NEW: send_event(request_id: str | None, event_data: dict, event_name: str, service_type: str)
  #      request_id=None means broadcast to all
  #      close parameter removed (connections stay open)
  #      service_type passed explicitly by callers for metrics ("version" or "task")
  ```
- Refactor strategy: Breaking change. All callers updated in same commit.
- Evidence: `app/services/connection_manager.py:177-193` — current signature

**Entity / contract: ConnectionManager observer callback**
- Shape:
  ```python
  # NEW: Callable[[str], None]  # callback receives request_id on connect
  # Registered via: register_on_connect(callback: Callable[[str], None])
  ```
- Refactor strategy: New capability, no backwards compatibility needed
- Evidence: Not present in current implementation

**Entity / contract: VersionService pending version storage**
- Shape:
  ```python
  # OLD: _pending_events: dict[str, list[VersionEvent]]  # request_id -> list of events

  # NEW: self._pending_version: dict[str, dict]  # instance variable, request_id -> {version, changelog}
  #      Only stores ONE pending version per request_id
  #      Protected by self._lock for thread-safety
  ```
- Refactor strategy: Breaking change. Simplifies to single pending version. Instance variable (not class variable) allows proper unit testing with multiple VersionService instances.
- Evidence: `app/services/version_service.py:43` — current dict of event lists

**Entity / contract: TaskEvent payload**
- Shape:
  ```python
  # UNCHANGED: TaskEvent includes task_id field for client-side filtering
  {
    "event_type": "progress_update" | "task_started" | "task_completed" | "task_failed",
    "task_id": "abc-123",
    "timestamp": "2025-01-15T10:30:00Z",
    "data": { ... }
  }
  ```
- Refactor strategy: No change needed. Already includes task_id.
- Evidence: `app/schemas/task_schema.py` — TaskEvent schema (imported in task_service.py:16-22)

**Entity / contract: SSE endpoint URL**
- Shape:
  ```
  # OLD: /api/sse/tasks?task_id=X
  #      /api/sse/utils/version?request_id=Y

  # NEW: /api/sse/stream?request_id=X
  #      Single endpoint for all event types
  ```
- Refactor strategy: Breaking change. Frontend updated to use new endpoint.
- Evidence: `app/api/sse.py:62-86` — current routing based on path prefix

## 4) API / Integration Surface

**Surface: GET /api/sse/stream**
- Inputs: `request_id` (query parameter, required) — UUID string identifying the client connection
- Outputs: SSE stream delivering all events (version updates, task progress) to this connection. Events include `event` field (event name) and `data` field (JSON payload). Connection remains open until client disconnects or server shutdown.
- Errors:
  - 400 if `request_id` missing or invalid
  - 401 if callback authentication fails (production only, via SSE Gateway)
- Evidence: New endpoint replacing `app/api/sse.py:62-86` routing logic

**Surface: POST /api/sse/callback**
- Inputs: SSE Gateway callback payload (connect or disconnect), `secret` query parameter (production only)
- Outputs:
  - 200 on success (empty JSON body)
  - 401 if authentication fails
  - 400 if payload invalid
- Errors: Same as current, but simplified routing (no service-type extraction)
- Evidence: `app/api/sse.py:93-196` — current callback handler

**Surface: POST /api/testing/deployments/version** (unchanged)
- Inputs: `{request_id, version, changelog?}`
- Outputs: 202 with `{requestId, delivered, status}`
- Errors: None (testing endpoint)
- Evidence: `app/api/testing.py:253-276` — current implementation unchanged

**Surface: POST /api/testing/tasks/start** (unchanged)
- Inputs: `{task_type, params}`
- Outputs: 200 with `{task_id, stream_url, status}` (stream_url will reference new endpoint)
- Errors: 400 if unknown task_type
- Evidence: `app/api/testing.py:279-320` — current implementation, only stream_url changes

## 5) Algorithms & State Machines

**Flow: ConnectionManager.on_connect**
- Steps:
  1. Acquire lock
  2. Check for existing connection with same request_id
  3. If exists, extract old token for later close
  4. Remove old token from reverse mapping
  5. Register new connection in both forward and reverse mappings
  6. Record connection metric
  7. Release lock
  8. Close old connection outside lock (best-effort HTTP POST)
  9. Notify all registered observers with request_id:
     a. For each observer in `_on_connect_callbacks`:
     b. Invoke observer in try/except block
     c. If exception raised, log warning with observer details, continue to next observer
     d. Connection remains registered regardless of observer failures
- States / transitions: None (stateless connection registration)
- Hotspots: Lock contention if many simultaneous connects; HTTP call to close old connection blocks
- Evidence: `app/services/connection_manager.py:61-113` — current on_connect, adds observer notification with exception handling

**Flow: ConnectionManager.send_event (broadcast)**
- Steps:
  1. If request_id is None (broadcast):
     a. Acquire lock
     b. Copy all connection tokens to local list
     c. Release lock
     d. For each token, send event via HTTP POST (best-effort)
     e. Record metrics for each send
  2. If request_id is not None (targeted):
     a. Acquire lock
     b. Look up token for request_id
     c. Release lock
     d. Send event via HTTP POST
     e. Record metrics
- States / transitions: None (stateless send)
- Hotspots: Broadcast scales with connection count; serial HTTP POSTs could be slow
- Evidence: `app/services/connection_manager.py:177-281` — current send_event, enhanced for broadcast

**Flow: VersionService.on_connect (new observer callback)**
- Steps:
  1. Check if pending version exists for this request_id (under lock)
  2. If yes, retrieve pending version from instance variable and send via ConnectionManager with service_type="version"
  3. If no, fetch version from URL and send via ConnectionManager with service_type="version"
  4. Do NOT clear pending version (per change brief: "Persist it until overwritten")
- States / transitions: None (stateless callback)
- Hotspots: HTTP fetch of version if no pending version
- Evidence: `app/services/version_service.py:67-112` — current on_connect SSE Gateway callback, simplified to remove queue draining

**Flow: TaskService task execution**
- Steps:
  1. Mark task as RUNNING
  2. Broadcast task_started event (request_id=None)
  3. Execute task with TaskProgressHandle for progress updates
  4. On completion: broadcast task_completed event (request_id=None)
  5. On failure: broadcast task_failed event (request_id=None)
  6. NO connection close (connection remains open)
- States / transitions: PENDING → RUNNING → COMPLETED/FAILED/CANCELLED
- Hotspots: Broadcast for every progress update; event loss if client not connected
- Evidence: `app/services/task_service.py:373-478` — current _execute_task, modified to broadcast and not close

**Flow: VersionService.queue_version_event**
- Steps:
  1. Check if shutting down (if yes, return False)
  2. Broadcast version event via ConnectionManager.send_event(None, payload)
  3. Store version as pending for this request_id (single pending version, class variable)
  4. Return True (event sent)
- States / transitions: None (stateless event queue)
- Hotspots: None (simplified from multi-event queue)
- Evidence: `app/services/version_service.py:165-218` — current queue_version_event, simplified to broadcast + single pending

## 6) Derived State & Invariants

**Derived value: Active connection set per request_id**
- Source: Unfiltered SSE Gateway connect/disconnect callbacks
- Writes / cleanup: ConnectionManager updates `_connections` and `_token_to_identifier` mappings atomically under lock
- Guards: RLock protects bidirectional mappings; disconnect callbacks verify token matches current connection before removal
- Invariant: At most one connection per request_id; reverse mapping always matches forward mapping for active connections
- Evidence: `app/services/connection_manager.py:59-163` — connection lifecycle management

**Derived value: Pending version for request_id**
- Source: Filtered by request_id match; triggered by testing endpoint or deployment automation
- Writes / cleanup: VersionService stores single pending version in instance-level dict (`self._pending_version`); NOT cleared on send, persists until overwritten by new queue_version_event call
- Guards: Only one pending version per request_id; overwritten if multiple versions queued; protected by `_lock` for thread-safety
- Invariant: Pending version delivered on every connect for that request_id (same version may be delivered multiple times if client reconnects); if connect happens before queue, no pending version stored
- Evidence: Change brief — "Persist it until overwritten"

**Derived value: Task event broadcast recipients**
- Source: Unfiltered active connections (all clients connected to `/api/sse/stream`)
- Writes / cleanup: ConnectionManager broadcasts to all active connections on send_event(None, ...); no persistence, events lost if no connections
- Guards: No filtering; frontend filters by task_id in event payload
- Invariant: Event broadcast is best-effort; no guarantee of delivery if no active connections or HTTP POST fails
- Evidence: Change brief lines 42-45 — "Broadcast all task events" with "frontend filters by task_id"

## 7) Consistency, Transactions & Concurrency

**Transaction scope: No database transactions**
- Atomic requirements: None (in-memory state only)
- Retry / idempotency: ConnectionManager tolerates duplicate connect/disconnect callbacks (token verification prevents stale disconnects)
- Ordering / concurrency controls:
  - RLock protects ConnectionManager mappings (allows nested locking)
  - Observer callbacks invoked serially after releasing lock (no lock held during HTTP calls)
  - Broadcast sends events serially to each connection (no parallelization)
- Evidence: `app/services/connection_manager.py:59` — `_lock = threading.RLock()`; `app/services/connection_manager.py:111-113` — close and notify outside lock

## 8) Errors & Edge Cases

**Failure: Client disconnects during event broadcast**
- Surface: ConnectionManager.send_event (broadcast)
- Handling: SSE Gateway returns 404; ConnectionManager logs warning, removes stale mapping, continues broadcasting to remaining connections
- Guardrails: Best-effort delivery; no retries; metrics record error per connection
- Evidence: `app/services/connection_manager.py:231-241` — 404 handling removes stale mapping

**Failure: Observer callback raises exception**
- Surface: ConnectionManager.on_connect
- Handling: Exception is caught and logged with warning; connection remains registered; remaining observers are still notified (iteration continues)
- Guardrails: Each observer invocation wrapped in try/except; exceptions don't block other observers or break connection establishment
- Evidence: ConnectionManager.on_connect algorithm step 9c — "If exception raised, log warning with observer details, continue to next observer"

**Failure: Broadcast with no active connections**
- Surface: TaskService, VersionService broadcasting events
- Handling: ConnectionManager.send_event returns early (no connections found); no error raised; event lost
- Guardrails: Acceptable per change brief ("messages lost if browser not connected")
- Evidence: Change brief lines 70-71 — "No message queueing"

**Failure: Multiple pending versions queued before connect**
- Surface: VersionService.queue_version_event called multiple times before connect
- Handling: Latest version overwrites previous pending version; only latest delivered on connect
- Guardrails: Single pending version per request_id (class variable)
- Evidence: Change brief lines 72-73 — "Single pending version"

**Failure: Connection close fails (old connection close in on_connect)**
- Surface: ConnectionManager.on_connect closing old connection
- Handling: Best-effort; log warning; continue with new connection registration; old connection may remain stale in gateway
- Guardrails: SSE Gateway will eventually detect stale connection; no blocking; new connection always registered
- Evidence: `app/services/connection_manager.py:283-321` — `_close_connection_internal` logs exceptions, doesn't raise

## 9) Observability / Telemetry

**Signal: sse_gateway_connections_total**
- Type: Counter
- Trigger: ConnectionManager.on_connect and on_disconnect
- Labels / fields: `action` (connect/disconnect) — remove `service` label (connection is now unified, not per-service)
- Consumer: Prometheus metrics endpoint, grafana dashboards
- Evidence: `app/services/metrics_service.py:483-488` — current counter with `service` and `action` labels

**Signal: sse_gateway_events_sent_total**
- Type: Counter
- Trigger: ConnectionManager.send_event after each HTTP POST
- Labels / fields: `service` (version/task), `status` (success/error) — retain `service` label (passed explicitly by callers)
- Consumer: Prometheus metrics endpoint, grafana dashboards
- Evidence: `app/services/metrics_service.py:489-494` — current counter with `service` and `status` labels

**Signal: sse_gateway_send_duration_seconds**
- Type: Histogram
- Trigger: ConnectionManager.send_event around HTTP POST
- Labels / fields: `service` (version/task) — retain `service` label (passed explicitly by callers)
- Consumer: Prometheus metrics endpoint, latency monitoring
- Evidence: `app/services/metrics_service.py:495-500` — current histogram with `service` label

**Signal: Log entries for connection lifecycle**
- Type: Structured log
- Trigger: ConnectionManager.on_connect, on_disconnect, send_event (errors)
- Labels / fields: `request_id`, `token`, `url`, `event_name`
- Consumer: Log aggregation, debugging
- Evidence: `app/services/connection_manager.py:102-109` — connection registered log

**Signal: Log entries for broadcast events**
- Type: Structured log (debug level)
- Trigger: ConnectionManager.send_event when broadcasting
- Labels / fields: `request_id` (or "broadcast"), `event_name`, `recipient_count`
- Consumer: Debugging, monitoring broadcast fanout
- Evidence: New logging for broadcast operations

## 10) Background Work & Shutdown

**Worker / job: VersionService cleanup thread (REMOVED)**
- Trigger cadence: Previously periodic (every `_cleanup_interval` seconds)
- Responsibilities: Previously cleaned up idle subscribers, restored pending events
- Shutdown handling: Cleanup thread and its shutdown coordinator registration will be removed entirely. VersionService will still register for PREPARE_SHUTDOWN to stop accepting new events gracefully.
- Evidence: `app/services/version_service.py:242-293` — cleanup worker and thread management; `app/services/version_service.py:53` — shutdown coordinator registration

**Worker / job: TaskService cleanup thread (UNCHANGED)**
- Trigger cadence: Periodic (every `cleanup_interval` seconds, default 600)
- Responsibilities: Remove completed tasks older than cleanup_interval
- Shutdown handling: Stops on `_shutdown_event.wait()`, joins with timeout
- Evidence: `app/services/task_service.py:480-516` — cleanup worker remains unchanged

**Worker / job: TaskService executor threads (UNCHANGED)**
- Trigger cadence: Event-driven (task submission)
- Responsibilities: Execute background tasks, send progress events
- Shutdown handling: Shutdown coordinator waiter blocks until tasks complete or timeout
- Evidence: `app/services/task_service.py:563-591` — `_wait_for_tasks_completion` remains unchanged

**Worker / job: None for ConnectionManager**
- Trigger cadence: N/A (no background threads)
- Responsibilities: Synchronous connection management
- Shutdown handling: No lifecycle integration needed
- Evidence: `app/services/connection_manager.py` — no threads created

## 11) Security & Permissions

Not applicable. SSE callback authentication remains unchanged (shared secret in production), and new endpoint uses same SSE Gateway integration with same security model.

## 12) UX / UI Impact

**Entry point: SSE connection establishment**
- Change: Frontend connects to new `/api/sse/stream?request_id=X` endpoint instead of separate task/version endpoints
- User interaction: No visible change; connection established on app load
- Dependencies: Frontend SSE client, SharedWorker for connection pooling
- Evidence: Change brief lines 82-88 — "frontend_changes.md" documents new endpoint

**Entry point: Task progress updates**
- Change: Frontend filters received events by `task_id` instead of relying on per-task connection
- User interaction: No visible change; progress updates appear same way
- Dependencies: Frontend event filtering logic
- Evidence: Change brief line 87 — "Client-side filtering by task_id"

**Entry point: Version update notifications**
- Change: Version events arrive on same connection as task events
- User interaction: No visible change; banner appears same way
- Dependencies: Frontend deployment banner component
- Evidence: Change brief lines 82-88 — documented in frontend_changes.md

## 13) Deterministic Test Plan

**Surface: ConnectionManager connection lifecycle**
- Scenarios:
  - Given no existing connection, When on_connect called with request_id, Then connection registered and observers notified
  - Given existing connection for request_id, When on_connect called with same request_id, Then old connection closed and new connection registered
  - Given active connection, When on_disconnect called with matching token, Then connection removed from mappings
  - Given stale disconnect (token doesn't match), When on_disconnect called, Then disconnect ignored, no error
- Fixtures / hooks: Mock ConnectionManager, mock SSE Gateway HTTP endpoint, test observer callbacks
- Gaps: None
- Evidence: `app/services/connection_manager.py:61-163` — connection lifecycle methods

**Surface: ConnectionManager.send_event broadcast**
- Scenarios:
  - Given multiple active connections, When send_event(None, data) called, Then all connections receive event
  - Given no active connections, When send_event(None, data) called, Then no error raised, returns early
  - Given SSE Gateway returns 404 for one connection, When broadcasting, Then stale connection removed, other connections still receive event
- Fixtures / hooks: Multiple mock connections in ConnectionManager, mock SSE Gateway responses
- Gaps: None
- Evidence: New broadcast behavior in send_event

**Surface: ConnectionManager observer callbacks**
- Scenarios:
  - Given observer registered, When connection established, Then observer called with request_id
  - Given multiple observers, When connection established, Then all observers called serially
  - Given first observer raises exception, When connection established, Then exception logged, connection still registered, second observer still called
  - Given observer raises exception, When connection established, Then on_connect returns successfully (no exception propagated to caller)
- Fixtures / hooks: Mock observer callbacks, exception-raising observers
- Gaps: None
- Evidence: ConnectionManager.on_connect algorithm step 9 with try/except

**Surface: VersionService.on_connect callback**
- Scenarios:
  - Given pending version exists for request_id, When connect callback fired, Then pending version sent (NOT cleared, persists until overwritten)
  - Given no pending version, When connect callback fired, Then version fetched from URL and sent
  - Given pending version send fails, When connect callback fired, Then error logged, version still pending (for retry on reconnect)
- Fixtures / hooks: Mock ConnectionManager, mock version URL, pending version storage
- Gaps: None
- Evidence: `app/services/version_service.py:67-112` — refactored on_connect

**Surface: VersionService.queue_version_event**
- Scenarios:
  - Given active connections, When queue_version_event called, Then version broadcast to all connections AND stored as pending
  - Given no connections, When queue_version_event called, Then version stored as pending only
  - Given pending version already exists, When queue_version_event called, Then old pending version overwritten
- Fixtures / hooks: Mock ConnectionManager, pending version storage
- Gaps: None
- Evidence: `app/services/version_service.py:165-218` — refactored queue method

**Surface: TaskService.start_task and execution**
- Scenarios:
  - Given task started, When task sends progress updates, Then updates broadcast to all connections
  - Given task completes successfully, When task finishes, Then task_completed event broadcast, connection NOT closed
  - Given task fails, When exception raised, Then task_failed event broadcast, connection NOT closed
- Fixtures / hooks: DemoTask fixture, mock ConnectionManager broadcast, event assertions
- Gaps: None
- Evidence: `app/services/task_service.py:373-478` — task execution flow

**Surface: SSE API /api/sse/callback**
- Scenarios:
  - Given valid connect callback, When callback received with request_id in URL, Then ConnectionManager.on_connect called
  - Given valid disconnect callback, When callback received, Then ConnectionManager.on_disconnect called
  - Given invalid URL (no request_id), When callback received, Then 400 error returned
  - Given authentication fails (production), When callback received, Then 401 error returned
- Fixtures / hooks: Mock SSE Gateway callback payloads, mock ConnectionManager, settings with FLASK_ENV=production
- Gaps: None
- Evidence: `app/api/sse.py:93-196` — callback handler refactored

**Surface: Integration test for version streaming**
- Scenarios:
  - Given pending version queued, When SSE client connects to /api/sse/stream, Then pending version delivered
  - Given connection established, When version event triggered, Then event received immediately
- Fixtures / hooks: SSE Gateway subprocess, SSEClient helper, testing endpoint
- Gaps: None
- Evidence: `tests/integration/test_sse_gateway_version.py:1-100` — updated for new endpoint

**Surface: Integration test for task streaming**
- Scenarios:
  - Given task started, When SSE client connects to /api/sse/stream, Then progress events received
  - Given task completes, When final event sent, Then connection remains open (no close)
- Fixtures / hooks: SSE Gateway subprocess, SSEClient helper, DemoTask
- Gaps: None
- Evidence: `tests/integration/test_sse_gateway_tasks.py:1-100` — updated for new behavior

## 14) Implementation Slices

**Slice: ConnectionManager refactoring**
- Goal: Support request_id tracking, broadcast, and observer callbacks
- Touches: `app/services/connection_manager.py`, unit tests
- Dependencies: None (foundational change)

**Slice: VersionService simplification**
- Goal: Remove queues and cleanup, add connect callback, simplify pending version
- Touches: `app/services/version_service.py`, unit tests
- Dependencies: ConnectionManager refactoring (observer registration)

**Slice: TaskService simplification**
- Goal: Remove event queues, broadcast events, no connection close
- Touches: `app/services/task_service.py`, TaskProgressHandle, unit tests
- Dependencies: ConnectionManager refactoring (broadcast capability)

**Slice: SSE API simplification**
- Goal: Single endpoint, request_id parsing, no service routing
- Touches: `app/api/sse.py`, unit tests
- Dependencies: ConnectionManager, VersionService, TaskService refactoring

**Slice: Metrics update**
- Goal: Remove service_type from connection metrics (unified connection), retain service_type for event metrics (passed by callers)
- Touches: `app/services/metrics_service.py`, MetricsServiceProtocol
- Dependencies: ConnectionManager refactoring (callers pass service_type to send_event)

**Slice: Integration tests update**
- Goal: Validate new endpoint and broadcast behavior
- Touches: `tests/integration/test_sse_gateway_version.py`, `tests/integration/test_sse_gateway_tasks.py`
- Dependencies: All backend slices complete

**Slice: Frontend changes documentation**
- Goal: Document required frontend updates
- Touches: `docs/features/sse_redesign/frontend_changes.md`
- Dependencies: Backend implementation complete (to document accurate API)

## 15) Risks & Open Questions

**Risks**

- Risk: Broadcast scale degrades with many connections (serial HTTP POSTs to SSE Gateway)
- Impact: High latency for events when 100+ connections active
- Mitigation: Monitor send_duration metrics (with service_type label); consider parallelizing broadcast in future iteration if needed

- Risk: Observer callback exceptions break version delivery
- Impact: Version events not delivered on connect if VersionService callback crashes
- Mitigation: ConnectionManager wraps each observer in try/except, logs warning, and continues to next observer. Connection remains registered even if observer fails.

- Risk: Event loss acceptable assumption violated in production
- Impact: Users miss task progress or version updates if browser not connected when event fires
- Mitigation: Frontend establishes connection early (before user actions); document message loss as expected behavior

- Risk: Pending version overwrite loses intermediate versions
- Impact: Playwright tests or deployment automation may expect all queued versions
- Mitigation: Change brief explicitly states "ONE pending version"; accept last-version-wins behavior

**Open Questions**

None. Change brief provides complete requirements, and codebase research confirms all dependencies and integration points.

## 16) Confidence

Confidence: High — Change brief is comprehensive and explicit; codebase research confirms all affected components; refactoring is primarily simplification (removing code) with clear backward-incompatible changes documented for frontend team.
