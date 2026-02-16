# Change Brief: SSE Real-Time Updates

## Summary

Add two real-time SSE features to the backend: device log streaming and rotation dashboard nudge events.

## Feature 1: Device Log Streaming via SSE

Stream device log messages in real time to frontend clients viewing a device's log screen.

**Architecture:**
- The app uses a persistent per-tab SSE connection via an external SSE Gateway. The gateway forwards browser headers (including OIDC cookies) in its connect callback. The backend already manages connections via `SSEConnectionManager`.
- Frontend explicitly subscribes and unsubscribes to device log streams via REST endpoints, providing its `request_id` and the target `device_id`.
- Multiple device subscriptions per SSE connection are supported (e.g., multiple tabs showing different device logs).
- Identity binding: on SSE connect, the backend extracts the OIDC access token from forwarded headers, validates it, and stores `request_id -> user_subject`. Subscription endpoints verify the caller's identity matches the stored subject for the provided `request_id`, preventing cross-user hijacking.
- `LogSinkService` already receives all device logs via MQTT. A parallel path is added: when a message arrives, check if any SSE clients are subscribed to that device's `entity_id`, and forward matching logs via SSE (in addition to writing to Elasticsearch).
- The subscribe endpoint resolves `device_id` -> `device_entity_id` for matching incoming MQTT log messages.
- Cleanup occurs on both explicit unsubscribe and SSE disconnect callback.

**Frontend flow:**
1. Frontend subscribes to device X's logs via REST (providing its `request_id`).
2. Frontend then fetches initial log history via the existing `GET /devices/{id}/logs` endpoint.
3. Any logs arriving via SSE that overlap with the initial fetch are deduplicated by the frontend.
4. Log events are batched (multiple log lines per SSE event, matching the NDJSON batches from MQTT).

## Feature 2: Rotation Dashboard Real-Time Updates via SSE

Provide real-time updates to the rotation dashboard using a nudge pattern.

**Architecture:**
- When rotation state changes occur in the web process, a lightweight "rotation-updated" SSE event is broadcast to all connected clients (no payload or minimal payload).
- The frontend, upon receiving the nudge, re-fetches the dashboard endpoint to get fresh data.
- Nudges are emitted on: fleet trigger, individual device rotation start, timeout processing, and device rotation completion (chain rotation).
- The Kubernetes CronJob (`rotation_job`) runs in a separate process without SSE connections. To ensure the dashboard updates for CronJob-initiated changes, the CronJob calls an internal HTTP endpoint on the web process to trigger a nudge broadcast.
- A new environment variable (`INTERNAL_API_URL`) provides the cluster-internal endpoint the CronJob uses for this call.
- The internal notification endpoint lives on `/` (not `/api/`) to separate it from the user-facing API.

## Non-Goals

- No frontend implementation (backend only).
- No changes to the existing `GET /devices/{id}/logs` REST endpoint behavior.
- No changes to the rotation state machine logic itself.
- No per-screen SSE targeting for rotation events (broadcast to all is sufficient given low event volume).
