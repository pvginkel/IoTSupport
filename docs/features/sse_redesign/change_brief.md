# SSE System Redesign - Change Brief

## Overview

Complete reimplementation of the SSE (Server-Sent Events) system to significantly simplify the architecture. The current implementation has complexity stemming from dual delivery mechanisms (local queues and SSE Gateway), per-task connections, and testing infrastructure that exceeds requirements.

## Current Problems

1. **Connection limit issues**: HTTP/1.1 has a 6-connection limit per browser. With persistent version connections and per-task AI analysis connections, this causes practical problems.

2. **Excessive complexity in VersionService**: Local subscriber queues, pending events, activity tracking, and cleanup workers exist primarily to support legacy patterns and testing scenarios that can be simplified.

3. **Per-task SSE connections in TaskService**: Each AI analysis task opens its own SSE connection. Event queuing handles the race between task start and connection establishment.

## New Architecture

### Single SSE Endpoint

- One endpoint: `/api/sse/stream?request_id=<id>`
- Single persistent connection per browser/SharedWorker
- All events (version updates, task progress) broadcast to all connected clients

### ConnectionManager Changes

- Track connections by `request_id` (not `task:X` or `version:Y` format)
- `send_event(request_id, event_data, event_name)`:
  - `request_id=None` → broadcast to all connections
  - `request_id=<value>` → send to specific connection
- Remove `close` parameter from `send_event`
- Add `register_on_connect(callback: Callable[[str], None])` for observer pattern
- On connect: close existing connection for same request_id, register new one, notify observers

### VersionService Changes

- Register callback with ConnectionManager for connect notifications
- On connect callback: get version (pending or fetched) and send to that connection
- `get_frontend_version(request_id)`: returns pending version if matches request_id, else fetches from URL
- `queue_version_event(request_id, version, changelog)`: stores ONE pending version (class variable), also sends immediately via ConnectionManager
- Remove: `_subscribers`, `_pending_events`, `_last_activity`, cleanup worker, `register_subscriber`, `unregister_subscriber`, `on_connect`, `on_disconnect`

### TaskService Changes

- Remove: `_event_queues`, `on_connect`, `on_disconnect`
- Broadcast all task events via `ConnectionManager.send_event(None, event)`
- Task events include `task_id` for frontend routing
- No connection close on task completion
- Keep shutdown waiter (wait for tasks to complete before shutdown)
- Simplify TaskProgressHandle to just broadcast (no queue fallback)

### SSE API Endpoint Changes

- Simplify `/api/sse/callback` to only call ConnectionManager
- Parse `request_id` from URL query params
- Remove routing to TaskService/VersionService

### Testing API Changes

- Remove demo SSE endpoints from `app/api/testing.py` that use local subscriber pattern

### Integration Test Updates

- Update to use new `/api/sse/stream?request_id=X` endpoint
- Test version events and task broadcasts

### Metrics

- Simplify by removing service_type dimension where appropriate

## Key Design Decisions

1. **Broadcast model**: All connected clients receive all messages. Frontend filters by task_id. Simplifies architecture significantly.

2. **No message queueing**: If browser not connected, messages are lost. Acceptable because SPA establishes connection well before user actions.

3. **Single pending version**: Only one pending version stored (for Playwright testing). Keyed by request_id, persists until overwritten.

4. **Observer pattern for connect**: ConnectionManager notifies VersionService via registered callback, avoiding circular dependencies.

5. **No backwards compatibility**: Frontend will be updated immediately after backend changes.

## Frontend Changes Document

Create `docs/features/sse_redesign/frontend_changes.md` documenting:
- New endpoint URL and parameters
- Event format changes
- Removal of per-task SSE connections
- Client-side filtering by task_id
