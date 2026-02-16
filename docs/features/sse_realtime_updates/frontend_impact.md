# Frontend Impact: SSE Real-Time Updates

## Overview

The backend now supports two new SSE event types delivered over the existing persistent SSE gateway connection:

1. **`device-logs`** — Real-time device log lines, targeted to subscribed connections
2. **`rotation-updated`** — Nudge event broadcast to all connections when rotation state changes

## 1. Device Log Streaming

### Subscription lifecycle

The frontend manages subscriptions explicitly via REST. The SSE connection must already be established (the backend binds the user's OIDC identity to the `request_id` on connect).

**Subscribe** when navigating to a device log screen:

```
POST /api/device-logs/subscribe
Content-Type: application/json

{
  "request_id": "<sse_request_id>",
  "device_id": 42
}
```

Response `200`:
```json
{
  "status": "subscribed",
  "device_entity_id": "sensor.living_room"
}
```

**Unsubscribe** when leaving the device log screen:

```
POST /api/device-logs/unsubscribe
Content-Type: application/json

{
  "request_id": "<sse_request_id>",
  "device_id": 42
}
```

Response `200`:
```json
{
  "status": "unsubscribed"
}
```

Multiple device subscriptions per connection are supported (e.g., multiple tabs).

Subscriptions are automatically cleaned up when the SSE connection drops, so explicit unsubscribe is a best-effort courtesy.

### Error responses

| Status | Cause |
|--------|-------|
| 400 | Missing or invalid fields |
| 403 | `request_id` not bound to the caller's identity (SSE connect may have failed auth, or another user's `request_id`) |
| 404 | Device not found, or device has no `device_entity_id` configured |

### Recommended flow for initial load + streaming

1. Call `POST /api/device-logs/subscribe` with the SSE `request_id` and `device_id`.
2. Then fetch initial log history via the existing `GET /api/devices/{id}/logs` endpoint.
3. Listen for `device-logs` SSE events for new log lines arriving after the fetch.
4. Deduplicate any overlap between the REST response and early SSE events (match on `timestamp` + `message`).

Subscribing before fetching guarantees no gap between the REST response and the SSE stream.

### SSE event: `device-logs`

Event name: `device-logs`

```json
{
  "device_entity_id": "sensor.living_room",
  "logs": [
    {
      "entity_id": "sensor.living_room",
      "message": "Temperature reading: 22.5C",
      "@timestamp": "2026-02-16T10:30:00.123456+00:00"
    }
  ]
}
```

- `logs` is an array (batched). Expect 1-N entries per event.
- Each log entry contains the raw fields from the device's MQTT payload, plus an `@timestamp` added by the backend.
- The `device_entity_id` top-level field identifies which device the logs belong to (useful when subscribed to multiple devices on one connection).

## 2. Rotation Dashboard Nudge

### SSE event: `rotation-updated`

Event name: `rotation-updated`

```json
{}
```

The payload is empty. On receiving this event, re-fetch the rotation dashboard data:

- `GET /api/rotation/status`
- `GET /api/rotation/dashboard`

No subscription is needed — this event is broadcast to all SSE connections automatically.

### When nudges are emitted

- Manual fleet rotation trigger (`POST /api/rotation/trigger`)
- Device rotation completion (chain rotation)
- CronJob rotation processing (queuing, timeout handling, device rotation)

## No changes to existing endpoints

The existing REST endpoints are unchanged:

- `GET /api/devices/{id}/logs` — same behavior, same response shape
- `GET /api/rotation/status` — same
- `GET /api/rotation/dashboard` — same
