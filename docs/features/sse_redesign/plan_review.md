# SSE System Redesign — Plan Review

## 1) Summary & Decision

**Readiness**

The updated plan successfully addresses all five previous blockers and major issues. The ConnectionManager callback URL parsing responsibility is now explicit (SSE API extracts, validates, passes plain string). Observer exception handling correctly wraps each callback in try/except with proper logging and continuation semantics. Pending version storage is clarified as an instance variable with thread-safe protection. Metrics approach is coherent (unified connection metrics without service_type, event metrics retain service_type passed by callers). VersionService shutdown cleanup is well-specified (cleanup thread removed, PREPARE_SHUTDOWN registration retained). The plan is comprehensive, implementation-ready, and includes deterministic test coverage for all new behaviors.

**Decision**

GO — All previous blockers resolved; remaining findings are minor clarifications that don't block implementation.

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/commands/plan_feature.md` — Pass — plan:0-635 — Follows all required sections with evidence-backed claims, deterministic test plan, and implementation slices. Each template section filled with concrete details tied to file:line references.

- `CLAUDE.md` (layering architecture) — Pass — plan:114-156 — Affected areas map correctly separates API (request handling), service (business logic), and model (none, in-memory only). SSE API delegates to ConnectionManager; services remain injectable singletons or factories.

- `CLAUDE.md` (dependency injection) — Pass — plan:145-148 — Service container wiring section confirms no changes needed; ConnectionManager, VersionService, TaskService already wired. Observer registration done via method calls, not DI, which is appropriate for runtime registration.

- `CLAUDE.md` (shutdown coordination) — Pass — plan:439-461 — VersionService cleanup thread removal clearly documented; PREPARE_SHUTDOWN registration retained for graceful event rejection. TaskService shutdown waiter unchanged (still blocks on task completion).

- `CLAUDE.md` (metrics) — Pass — plan:401-422 — All three SSE metrics documented with correct type (Counter/Histogram), trigger points, and label strategy (connection metrics unified, event metrics retain service_type).

- `CLAUDE.md` (testing requirements) — Pass — plan:487-569 — Comprehensive test plan covering ConnectionManager lifecycle, broadcast, observer callbacks, VersionService pending version delivery, TaskService execution, API callbacks, and integration tests. Each scenario follows Given/When/Then format.

**Fit with codebase**

- `app/services/connection_manager.py:32-335` — plan:116-119, 159-186 — Current implementation uses `identifier` with prefix format (`task:X`, `version:Y`). Plan refactors to plain `request_id` strings and adds broadcast capability (`request_id=None`). Requires updating all method signatures and removing `_extract_service_type` helper. Observer callback registration is new capability, no conflicts.

- `app/services/version_service.py:42-44, 242-293` — plan:120-123, 439-444 — Current implementation maintains `_subscribers`, `_pending_events`, `_last_activity` dicts and cleanup thread. Plan removes all four data structures and thread, simplifies to single pending version dict and connect callback. Shutdown coordinator registration changes from cleanup thread coordination to event rejection only.

- `app/services/task_service.py:114, 178-278` — plan:124-128 — Current implementation maintains `_event_queues` and drains on connect. Plan removes queues entirely, broadcasts all events, eliminates connection close on completion. Shutdown waiter unchanged (line 123 registration).

- `app/api/sse.py:47-196` — plan:132-136 — Current implementation routes callbacks to TaskService or VersionService based on URL path prefix. Plan simplifies to single endpoint (`/api/sse/stream`), extracts `request_id` from query params, calls ConnectionManager only. Parsing logic moves from `_route_to_service` to simpler query param extraction.

- `app/services/metrics_service.py:156-176` — plan:142-144 — Current `record_sse_gateway_connection` accepts `service` parameter. Plan removes this parameter (unified connection). Event and duration metrics retain `service` parameter but require callers to pass explicitly. Protocol interface must be updated.

- `tests/integration/test_sse_gateway_version.py:1-100` — plan:149-152, 555-562 — Current tests connect to `/api/sse/utils/version?request_id=X`. Plan changes endpoint to `/api/sse/stream?request_id=X` and validates pending version persistence (not cleared on send).

## 3) Open Questions & Ambiguities

No open questions. The plan resolves all previous ambiguities:

- Callback URL parsing responsibility explicitly assigned to SSE API layer (plan:135-136)
- Observer exception handling semantics specified with try/except and continuation (plan:276-279)
- Pending version storage clarified as instance variable with dict structure (plan:199-204, 345-348)
- Metrics label strategy documented for both connection and event metrics (plan:142-144, 401-422)
- Shutdown cleanup behavior specified (plan:439-444)

## 4) Deterministic Backend Coverage (new/changed behavior only)

**Behavior: ConnectionManager connection lifecycle**
- Scenarios:
  - Given no existing connection, When on_connect(request_id, token, url) called, Then connection registered and all observers notified (`plan:490-492`)
  - Given existing connection, When on_connect with same request_id, Then old connection closed, new registered (`plan:492`)
  - Given active connection, When on_disconnect with matching token, Then mappings updated (`plan:493`)
  - Given stale token, When on_disconnect, Then ignored without error (`plan:494`)
- Instrumentation: `sse_gateway_connections_total` counter with `action` label (no `service` label), connection lifecycle logs with request_id/token (plan:401-408, 423-429)
- Persistence hooks: None (in-memory only); DI wiring unchanged (plan:145-148)
- Gaps: None
- Evidence: plan:487-497

**Behavior: ConnectionManager.send_event broadcast**
- Scenarios:
  - Given multiple connections, When send_event(None, data, name, service_type) called, Then all receive event (`plan:500-502`)
  - Given no connections, When broadcast, Then no error, returns early (`plan:502`)
  - Given SSE Gateway 404 for one connection, When broadcasting, Then stale removed, others continue (`plan:503`)
- Instrumentation: `sse_gateway_events_sent_total` and `sse_gateway_send_duration_seconds` with `service` label (plan:409-422), broadcast fanout logs (plan:430-436)
- Persistence hooks: None
- Gaps: None
- Evidence: plan:498-506

**Behavior: ConnectionManager observer callbacks**
- Scenarios:
  - Given observer registered, When on_connect, Then observer called with request_id (`plan:510-511`)
  - Given multiple observers, When on_connect, Then all called serially (`plan:511`)
  - Given first observer raises exception, When on_connect, Then exception logged, connection registered, second observer called (`plan:512`)
  - Given observer raises exception, When on_connect, Then on_connect succeeds without propagation (`plan:513`)
- Instrumentation: Observer exception logged with warning level, includes observer details (plan:277-279)
- Persistence hooks: None (runtime callback registration)
- Gaps: None
- Evidence: plan:507-516

**Behavior: VersionService.on_connect callback**
- Scenarios:
  - Given pending version exists, When callback fired, Then pending sent, NOT cleared (`plan:519-520`)
  - Given no pending version, When callback fired, Then version fetched and sent (`plan:521`)
  - Given send fails, When callback fired, Then error logged, version persists for retry (`plan:522`)
- Instrumentation: Version send via ConnectionManager with service_type="version" (plan:306), logs for fetch/send operations (plan:67-112 evidence)
- Persistence hooks: Pending version stored in `self._pending_version` dict, protected by `_lock` (plan:199-204)
- Gaps: None
- Evidence: plan:517-526

**Behavior: VersionService.queue_version_event**
- Scenarios:
  - Given active connections, When queue_version_event called, Then broadcast AND stored as pending (`plan:528-529`)
  - Given no connections, When queue_version_event called, Then stored as pending only (`plan:530`)
  - Given pending version exists, When queue_version_event called, Then old pending overwritten (`plan:531`)
- Instrumentation: Broadcast via send_event with service_type="version" (plan:327-328)
- Persistence hooks: Pending version persisted until overwritten (plan:345-348)
- Gaps: None
- Evidence: plan:527-535

**Behavior: TaskService.start_task and execution**
- Scenarios:
  - Given task started, When progress updates sent, Then broadcast to all connections (`plan:537-538`)
  - Given task completes, When finishes, Then task_completed broadcast, connection NOT closed (`plan:539`)
  - Given task fails, When exception raised, Then task_failed broadcast, connection NOT closed (`plan:540`)
- Instrumentation: Task events broadcast via send_event with service_type="task" (plan:316-318), shutdown waiter unchanged (plan:447-456)
- Persistence hooks: None (in-memory task state only)
- Gaps: None
- Evidence: plan:536-544

**Behavior: SSE API /api/sse/callback**
- Scenarios:
  - Given valid connect callback with request_id in URL, When received, Then ConnectionManager.on_connect called (`plan:546-547`)
  - Given valid disconnect callback, When received, Then ConnectionManager.on_disconnect called (`plan:548`)
  - Given invalid URL (no request_id), When received, Then 400 returned (`plan:549`)
  - Given auth fails (production), When received, Then 401 returned (`plan:550`)
- Instrumentation: Callback authentication logs, routing errors (plan:47-91 evidence)
- Persistence hooks: None
- Gaps: None
- Evidence: plan:545-554

**Behavior: Integration test for version streaming**
- Scenarios:
  - Given pending version queued, When SSE client connects to /api/sse/stream, Then pending delivered (`plan:556-557`)
  - Given connection established, When version event triggered, Then received immediately (`plan:558`)
- Instrumentation: Integration test logs, SSEClient helper
- Persistence hooks: Pending version persists across reconnects (plan:345-348)
- Gaps: None
- Evidence: plan:555-562

**Behavior: Integration test for task streaming**
- Scenarios:
  - Given task started, When SSE client connects to /api/sse/stream, Then progress events received (`plan:564-565`)
  - Given task completes, When final event sent, Then connection remains open (`plan:566`)
- Instrumentation: Integration test logs, DemoTask fixture
- Persistence hooks: None
- Gaps: None
- Evidence: plan:563-569

## 5) Adversarial Sweep (must find ≥3 credible issues or declare why none exist)

**Minor — Pending version dict structure underspecified for serialization**
**Evidence:** `plan:199-204` — "NEW: self._pending_version: dict[str, dict] # instance variable, request_id -> {version, changelog}"
**Why it matters:** Dict value shape not typed; unclear if `changelog` is optional or what happens if only version provided. Affects queue_version_event implementation and on_connect deserialization.
**Fix suggestion:** Specify dict value as `dict[str, Any]` or `TypedDict` with `version: str, changelog: str | None`. Update plan line 199 to show: `self._pending_version: dict[str, dict[str, Any]] # {version: str, changelog: str | None}`
**Confidence:** High

**Minor — Broadcast loop serial HTTP calls not explicitly acknowledged as blocking**
**Evidence:** `plan:286-297` — "For each token, send event via HTTP POST (best-effort)"; `plan:299` — "Hotspots: Broadcast scales with connection count; serial HTTP POSTs could be slow"
**Why it matters:** Plan acknowledges scaling concern but doesn't specify whether broadcast loop blocks the caller or runs async. If blocking, high connection count (100+) could delay task progress updates by seconds. Affects TaskProgressHandle behavior during builds.
**Fix suggestion:** Add to plan section 5 (Algorithms) step 2d: "Send events serially in calling thread (blocking); broadcast duration = (connection_count × http_timeout)". Add to section 15 (Risks): "Broadcast blocking delays task progress updates proportional to connection count; acceptable for expected load (<10 connections); monitor send_duration_seconds p99."
**Confidence:** Medium

**Minor — Observer callback invocation order unspecified when multiple observers registered**
**Evidence:** `plan:276-279` — "For each observer in `_on_connect_callbacks`: invoke observer in try/except block"
**Why it matters:** If VersionService on_connect callback sends pending version before another observer runs, order matters. Plan doesn't specify list vs set for `_on_connect_callbacks` or whether registration order is preserved.
**Fix suggestion:** Add to plan section 5 (ConnectionManager.on_connect step 9): "Observers invoked in registration order (list, not set); VersionService typically registered first during container initialization."
**Confidence:** Low — implementation detail, unlikely to cause issues in practice

**Minor — Connection close on replacement not guaranteed to succeed before new connection sends**
**Evidence:** `plan:268-274` — "If exists, extract old token for later close [...] Release lock [...] Close old connection outside lock"; `plan:394-399` — "Failure: Connection close fails [...] Best-effort; log warning; SSE Gateway will eventually detect stale"
**Why it matters:** New connection can send events before old connection close completes. SSE Gateway might deliver duplicate events if old connection still active. Plan acknowledges this as best-effort but doesn't quantify duplicate event window or frontend resilience.
**Fix suggestion:** Add to section 8 (Errors & Edge Cases): "Failure: Duplicate events during connection replacement — Surface: Frontend SSE client — Handling: Frontend receives same event twice if old connection not yet closed — Guardrails: Event payloads include timestamp; frontend deduplicates by task_id+timestamp or accepts duplicates as harmless. Duplicate window typically <500ms (HTTP timeout)."
**Confidence:** Medium — may surface in testing if SSE Gateway has high latency

**Checks attempted: Transaction safety (none needed, in-memory only), shutdown coordination (correctly specified), metrics label consistency (validated connection vs event split), observer exception isolation (correctly wrapped), pending version overwrite semantics (last-wins documented), broadcast fanout correctness (all connections iterated), stale disconnect handling (token verification present).**

**Why the plan holds:** All previous blockers resolved with explicit specifications. Remaining findings are edge cases (duplicate events during replacement) or clarifications (pending version dict typing, broadcast blocking semantics) that don't prevent implementation. Core invariants protected: connection replacement prevents unbounded growth, observer exceptions don't break connections, pending version persists for retry, broadcast is best-effort with metrics.

## 6) Derived-Value & Persistence Invariants (stacked entries)

**Derived value: Active connection set per request_id**
- Source dataset: Unfiltered SSE Gateway connect/disconnect callbacks (external system, no filtering)
- Write / cleanup triggered: ConnectionManager updates `_connections` and `_token_to_identifier` bidirectional mappings atomically under `_lock` (plan:335-341)
- Guards: RLock protects updates; disconnect verifies token matches current connection before removal (prevents stale disconnects); connection replacement extracts old token under lock, closes outside lock (best-effort)
- Invariant: At most one connection per request_id; forward and reverse mappings always consistent for active connections; stale tokens rejected on disconnect
- Evidence: plan:335-341, app/services/connection_manager.py:59-163

**Derived value: Pending version for request_id**
- Source dataset: Filtered by request_id match; triggered by testing endpoint (`POST /api/testing/deployments/version`) or deployment automation
- Write / cleanup triggered: VersionService stores single pending version in `self._pending_version[request_id]` (instance variable dict, not class variable); NOT cleared on send, persists until overwritten by new `queue_version_event` call for same request_id
- Guards: Only one pending version per request_id (last-wins if multiple queued); protected by `_lock` for thread-safety; delivered on every connect for that request_id (same version may be delivered multiple times if client reconnects)
- Invariant: Pending version delivered on every connect attempt; version persists across reconnects; if connect happens before queue, no pending version stored (fetch from URL instead); version overwritten (not appended) if multiple queues before connect
- Evidence: plan:343-348, plan:199-204 (instance variable `self._pending_version: dict[str, dict]`)

**Derived value: Task event broadcast recipients**
- Source dataset: Unfiltered active connections (all clients connected to `/api/sse/stream`, regardless of which tasks they care about)
- Write / cleanup triggered: ConnectionManager broadcasts to all active connections on `send_event(None, event_data, event_name, service_type="task")`; no persistence, events lost if no connections or HTTP POST fails
- Guards: No filtering at backend (frontend filters by task_id in event payload); broadcast is best-effort with per-connection error handling (404 removes stale mapping, continues broadcasting to remaining); metrics record success/error per send
- Invariant: Event broadcast is best-effort; no guarantee of delivery if no active connections at broadcast time or if HTTP POST times out; frontend must tolerate missed events or establish connection before triggering actions
- Evidence: plan:350-356, plan:382-387 (acceptable event loss documented)

**Derived value: Metrics service_type label for events**
- Source dataset: Derived from caller context (VersionService passes "version", TaskService passes "task" to ConnectionManager.send_event)
- Write / cleanup triggered: Prometheus counters and histograms incremented per event send; metrics retained in Prometheus TSDB per retention policy (no backend cleanup)
- Guards: Callers must pass service_type explicitly to send_event (plan:179 signature); MetricsService validates label values (implicitly via Prometheus client); connection metrics unified (no service label), event metrics retain service label for observability
- Invariant: Event metrics always tagged with service_type; connection metrics never tagged with service_type (unified tracking); callers responsible for passing correct service_type ("version" or "task")
- Evidence: plan:142-144, plan:401-422

## 7) Risks & Mitigations (top 3)

**Risk:** Broadcast blocking delays task progress updates proportional to connection count
- Mitigation: Monitor `sse_gateway_send_duration_seconds` p99 with `service="task"` label; document expected behavior (serial sends); consider parallelizing broadcast in future iteration if p99 exceeds 1s with >50 connections
- Evidence: plan:299 (Hotspots: "serial HTTP POSTs could be slow"), plan:613-615 (Risk section)

**Risk:** Pending version overwrite loses intermediate versions for Playwright tests
- Mitigation: Change brief explicitly states "ONE pending version" (plan:64, plan:391); accept last-version-wins behavior; update Playwright tests to expect only latest version on connect; document message loss as expected behavior
- Evidence: plan:388-392 (Failure: Multiple pending versions), plan:623-626 (Risk section)

**Risk:** Observer callback exception breaks version delivery on connect
- Mitigation: ConnectionManager wraps each observer in try/except, logs warning with observer details, continues to next observer (plan:277-279); connection remains registered even if VersionService callback fails; version will retry on reconnect (pending version persists)
- Evidence: plan:376-381 (Failure: Observer callback raises exception), plan:616-619 (Risk section)

## 8) Confidence

Confidence: High — All previous blockers resolved with explicit specifications; comprehensive test plan covers new behaviors; implementation is primarily simplification (removing queues, cleanup threads) with well-defined broadcast semantics; minor findings are edge cases that don't block implementation; metrics, shutdown, and observability correctly integrated.
