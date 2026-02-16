# Frontend Testing Support: SSE Real-Time Updates

## Purpose

Playwright tests run against a real backend but cannot rely on MQTT messages arriving from physical devices. These testing endpoints let the test suite exercise the SSE-driven device logs and rotation dashboard features by injecting events directly into the `DeviceLogStreamService` pipeline.

All endpoints live under `/api/testing/` and are guarded by `reject_if_not_testing()` (available only when `FLASK_ENV=testing`).

---

## 1. Device Log Injection

### `POST /api/testing/devices/logs/inject`

Pushes log entries into the SSE forwarding pipeline, exactly as if they had arrived from MQTT via `LogSinkService`. If no SSE client is currently subscribed to the target device, the logs are silently dropped.

**Request body:**

```json
{
  "device_entity_id": "test_device_abc123",
  "logs": [
    { "message": "Temperature reading: 22.5C" },
    { "message": "Humidity reading: 45%" }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `device_entity_id` | string | yes | The device entity ID to target (matches the subscription key) |
| `logs` | array | yes | 1-N log entries. Each entry must have at least a `message` field. |
| `logs[].message` | string | yes | Log line content |

The backend adds `@timestamp` (current UTC) and `entity_id` (copied from `device_entity_id`) to each entry before forwarding, matching the shape of real MQTT-sourced log events.

**Response `200`:**

```json
{
  "status": "accepted",
  "forwarded": 2
}
```

`forwarded` is the number of log entries passed to `DeviceLogStreamService.forward_logs()`. This does not guarantee delivery (the client may have disconnected between the check and the send).

**Errors:**

| Status | Cause |
|--------|-------|
| 400 | Missing or invalid fields, empty `logs` array |

---

## 2. Subscription Status

### `GET /api/testing/devices/logs/subscriptions`

Returns the current SSE subscription state. Useful for Playwright tests to poll-wait until a subscription is active before injecting logs.

**Query parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `device_entity_id` | string | no | Filter to subscriptions for this device. Omit to return all. |

**Response `200`:**

```json
{
  "subscriptions": [
    {
      "device_entity_id": "test_device_abc123",
      "request_ids": ["req-abc-123"]
    }
  ]
}
```

Returns an empty `subscriptions` array when no active subscriptions exist (or none match the filter).

---

## 3. Rotation Nudge

### `POST /api/testing/rotation/nudge`

Broadcasts a `rotation-updated` SSE event to all connected clients, exactly as the production rotation flow does. No rotation state is changed; this purely tests the SSE-to-dashboard refresh path.

**Request body:** none (or empty `{}`)

**Response `200`:**

```json
{
  "status": "accepted"
}
```

---

## Typical Playwright Test Flows

### Device log streaming

```
1. auth.createSession()
2. devices.create({ deviceEntityId: "test_device_xyz" })
3. Navigate to device logs page
4. Wait for frontend instrumentation event (ListLoading scope="devices.logs" phase="ready")
5. Poll GET /api/testing/devices/logs/subscriptions?device_entity_id=test_device_xyz
   until subscriptions array is non-empty (confirms SSE subscription is active)
6. POST /api/testing/devices/logs/inject  { device_entity_id, logs: [...] }
7. Assert log entries appear in the viewer
```

### Rotation dashboard auto-refresh

```
1. auth.createSession()
2. Set up devices / rotation state via existing factories
3. Navigate to rotation dashboard
4. Wait for dashboard to render (ListLoading scope="rotation.dashboard" phase="ready")
5. Mutate rotation state via existing API (e.g. trigger rotation on a device)
6. POST /api/testing/rotation/nudge
7. Assert dashboard content updates without manual refresh
```

---

## Implementation Notes

- **Blueprint:** Register as a new blueprint (e.g. `testing_devices_bp` and `testing_rotation_bp`) or extend the existing `testing_bp`. Follow the existing `url_prefix="/testing"` convention so endpoints resolve under `/api/testing/`.
- **Guard:** Apply `reject_if_not_testing` via `before_request`, matching the pattern in `testing_sse.py`.
- **Service access:** Inject `DeviceLogStreamService` via `Provide[ServiceContainer.device_log_stream_service]`. The log injection endpoint calls `forward_logs()` with constructed documents. The nudge endpoint calls `broadcast_rotation_nudge()`. The subscriptions endpoint reads from the service's in-memory maps.
- **OpenAPI:** Decorate with `@api.validate()` and Pydantic schemas so the endpoints appear in the generated spec (enabling typed Playwright factory methods on the frontend).
- **No auth:** Mark endpoints `@public` — testing endpoints bypass OIDC.
