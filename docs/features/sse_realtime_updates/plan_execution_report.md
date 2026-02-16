# Plan Execution Report: SSE Real-Time Updates

## Status

**DONE** — The plan was implemented successfully with all requirements verified and code review issues resolved.

## Summary

Two SSE features were added to the backend:

1. **Device Log Streaming via SSE** — A new `DeviceLogStreamService` singleton manages per-connection device log subscriptions with OIDC identity binding. REST endpoints allow frontends to subscribe/unsubscribe to device log streams. `LogSinkService` forwards matching MQTT log messages to subscribed SSE clients in parallel with its Elasticsearch write path.

2. **Rotation Dashboard Nudge Events** — Lightweight `rotation-updated` SSE events are broadcast to all connected clients when rotation state changes occur. An internal HTTP endpoint (`POST /internal/rotation-nudge`) allows the Kubernetes CronJob to trigger nudge broadcasts from its separate process.

All 15 user requirements from the checklist were verified as implemented with concrete code evidence.

## Code Review Summary

- **Decision:** GO-WITH-CONDITIONS (upgraded to GO after fixes)
- **Blockers:** 0
- **Majors:** 2 (both resolved)
  - Fragile string matching for error-to-status-code mapping → Fixed by using distinct exception types (`AuthorizationException`, `RecordNotFoundException`) in the service layer
  - Unsubscribe with null `device_entity_id` passes empty string → Fixed by adding the same null check as the subscribe endpoint
- **Minors:** 0

## Verification Results

**Ruff:** `All checks passed!`

**Mypy:** 98 errors in 8 files — all pre-existing in unrelated files (`health_service.py`, `cas_image_service.py`, `startup.py`, `testing_sse.py`, `oidc_hooks.py`, `__init__.py`). No new errors in any modified or created files.

**Pytest:** `559 passed, 215 warnings in 48.61s` — 0 failures. New tests account for ~60 of the total.

## Files Created

| File | Purpose |
|------|---------|
| `app/services/device_log_stream_service.py` | Singleton service: subscriptions, identity binding, log forwarding, rotation nudge |
| `app/schemas/device_log_stream.py` | Pydantic schemas for subscribe/unsubscribe |
| `app/api/device_log_stream.py` | REST endpoints: `POST /api/device-logs/subscribe`, `POST /api/device-logs/unsubscribe` |
| `app/api/internal.py` | Internal endpoint: `POST /internal/rotation-nudge` |
| `tests/services/test_device_log_stream_service.py` | 33 service tests |
| `tests/services/test_sse_connection_manager.py` | 7 tests for disconnect observer |
| `tests/api/test_device_log_stream.py` | 11 API tests |
| `tests/api/test_internal.py` | 2 API tests |
| `tests/test_startup.py` | 4 CLI helper tests |

## Files Modified

| File | Change |
|------|--------|
| `app/services/sse_connection_manager.py` | Added `register_on_disconnect` observer pattern |
| `app/services/logsink_service.py` | Added SSE forwarding path in `_on_message` |
| `app/services/container.py` | Wired `DeviceLogStreamService` singleton |
| `app/api/sse.py` | Added identity binding in SSE connect callback |
| `app/api/rotation.py` | Added rotation nudge after fleet trigger |
| `app/api/iot.py` | Added rotation nudge after chain rotation |
| `app/app_config.py` | Added `INTERNAL_API_URL` env var |
| `app/startup.py` | Added `_notify_rotation_nudge` helper, CronJob notification |
| `app/__init__.py` | Registered `internal_bp` blueprint |
| `tests/api/test_rotation.py` | Updated trigger tests to verify nudge calls |
| `tests/api/test_iot.py` | Added chain rotation nudge test |
| `tests/services/test_logsink_service.py` | Added SSE forwarding integration tests |

## Outstanding Work & Suggested Improvements

- **MQTT entity_id field name**: The `forward_logs` method assumes the MQTT log payload has an `entity_id` top-level field. This should be verified against actual MQTT message samples from ESP32 devices. If the field name differs, update the field name in `DeviceLogStreamService.forward_logs()`.
- **SSE Gateway header forwarding**: Verify in integration testing that the SSE Gateway forwards the `Cookie` header in connect callbacks. If not, identity binding will silently fail (subscribe returns 403).
- **Frontend impact**: The frontend needs to be updated to use the new subscribe/unsubscribe endpoints and listen for `device-logs` and `rotation-updated` SSE events. See `docs/features/sse_realtime_updates/change_brief.md` for the expected frontend flow.
