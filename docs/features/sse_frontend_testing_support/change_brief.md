# Change Brief: SSE Frontend Testing Support

Add testing-only API endpoints that allow Playwright tests to exercise the SSE-driven device log streaming and rotation dashboard features without requiring real MQTT messages from physical devices.

Three endpoints are needed, all under `/api/testing/` and guarded by the existing `reject_if_not_testing()` mechanism:

1. **POST /api/testing/devices/logs/inject** - Injects log entries directly into the `DeviceLogStreamService.forward_logs()` pipeline, simulating logs that would normally arrive via MQTT through `LogSinkService`. The backend adds `@timestamp` and `entity_id` to each entry before forwarding. Returns the count of forwarded entries.

2. **GET /api/testing/devices/logs/subscriptions** - Returns current SSE subscription state so Playwright tests can poll-wait until a subscription is active before injecting logs. Supports an optional `device_entity_id` query parameter to filter results.

3. **POST /api/testing/rotation/nudge** - Broadcasts a `rotation-updated` SSE event to all connected clients via `RotationNudgeService.broadcast()`, without changing any rotation state. Tests the SSE-to-dashboard refresh path.

All endpoints are public (no OIDC auth), validated with Pydantic schemas for OpenAPI generation, and follow the existing testing blueprint patterns established in `app/api/testing.py` and `app/api/testing_sse.py`.

The full specification is in `docs/features/sse_realtime_updates/frontend_testing_support.md`.
