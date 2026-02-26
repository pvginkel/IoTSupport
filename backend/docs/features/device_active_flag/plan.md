# Device Active Flag - Technical Plan

## 0) Research Log & Findings

**Areas researched:**

- **Device model** (`app/models/device.py:34-122`): The `Device` SQLAlchemy model has columns for key, config, rotation state, cached secret, and timestamps. No `active` field exists yet. The model uses `Mapped[type]` annotations and `mapped_column()`.
- **Device service** (`app/services/device_service.py:33-631`): Handles CRUD, Keycloak lifecycle, and provisioning. The `update_device()` method (line 328) currently only accepts `config` as a parameter. The `trigger_rotation()` method (line 464) queues a single device regardless of any active state.
- **Rotation service** (`app/services/rotation_service.py:50-489`): Contains `trigger_fleet_rotation()` (line 123) which selects all devices in OK state and sets them to QUEUED. `process_rotation_job()` (line 142) checks CRON schedule and calls `trigger_fleet_rotation()`. The `get_dashboard_status()` (line 427) groups devices into healthy/warning/critical. `get_rotation_status()` (line 80) counts devices by rotation state.
- **Device schemas** (`app/schemas/device.py:1-158`): `DeviceUpdateSchema` only has `config`. `DeviceSummarySchema` and `DeviceResponseSchema` do not include `active`. The update endpoint is `PUT`, not `PATCH`.
- **Rotation schemas** (`app/schemas/rotation.py:1-96`): `RotationStatusSchema` has `counts_by_state` dict. `DashboardResponseSchema` has healthy/warning/critical lists and counts dict. Neither has an `inactive` category.
- **API layer** (`app/api/devices.py:145-178`): The update endpoint is `PUT /devices/<int:device_id>` and only updates config. There is no `PATCH` endpoint. (`app/api/rotation.py:1-124`): Dashboard and status endpoints delegate to rotation service.
- **Test data** (`app/data/test_data/devices.json:1-74`): Six devices, all without an `active` field.
- **Test data service** (`app/services/test_data_service.py:103-178`): Reads devices.json and creates Device objects. Does not set an `active` field.
- **Migrations** (`alembic/versions/`): Seven migrations exist. The next should be `008`.
- **IoT endpoints** (`app/api/iot.py:1-442`): Device-facing endpoints for config, firmware, and provisioning. These look up devices by key and serve data regardless of any active flag -- they must remain unaffected.
- **Container** (`app/services/container.py:232-239`): RotationService is a Factory provider receiving db, config, device_service, keycloak_admin_service, and mqtt_service.

**Key design decisions:**

1. **PATCH vs PUT**: The change brief specifies `PATCH /devices/{id}` for updating `active`. The existing `PUT /devices/<id>` replaces config entirely. Adding a new `PATCH` endpoint that accepts partial updates (currently only `active`, but extensible) is the cleanest approach and avoids overloading the PUT endpoint with unrelated concerns.
2. **Dashboard inactive group**: The dashboard currently builds three lists in a single loop over all devices. Adding a fourth `inactive` list means inserting an early check on `device.active` before the existing state-based categorization.
3. **Rotation status inactive count**: The status endpoint currently counts by rotation state enum values. Adding an `inactive` count means adding a separate query that counts inactive devices, independent of their rotation state.
4. **Fleet rotation filtering**: Both CRON-triggered and manual fleet triggers call `trigger_fleet_rotation()`. The filter should be applied there: only queue active devices in OK state.

---

## 1) Intent & Scope

**User intent**

Add a boolean `active` flag to the Device model so that administrators can exclude devices from automatic credential rotation without removing them from the system. Inactive devices remain fully functional (authentication, firmware, config, provisioning all unaffected) but are excluded from CRON-based and fleet-wide manual rotation queuing and are displayed separately on the rotation dashboard.

**Prompt quotes**

- "Add an `active` boolean field to the Device model (default `True`) that controls whether a device participates in automatic credential rotation"
- "Inactive devices are skipped when queuing devices for rotation"
- "Single-device manual rotation (`POST /devices/<id>/rotate`): Still works for inactive devices"
- "Deactivating a device mid-rotation (QUEUED/PENDING) does not cancel the in-flight rotation"
- "Inactive devices are shown in a new fourth group called 'inactive'"

**In scope**

- Add `active` boolean column to Device model with default `True`
- Alembic migration for the new column
- PATCH endpoint for updating the `active` field
- Filter inactive devices from fleet rotation (CRON and manual trigger)
- Rotation dashboard: new "inactive" group, excluded from healthy/warning/critical
- Rotation status: new `inactive` count
- Surface `active` in device list and detail responses
- Update test data to include inactive device(s)
- Comprehensive service and API tests

**Out of scope**

- Filter/query parameters on the device list endpoint
- Changes to IoT device-facing endpoints (/iot/*)
- Changes to device creation (new devices always start active)
- Any notification or MQTT behavior change for active flag

**Assumptions / constraints**

- The existing fleet of up to 200 devices means migration is instant and non-disruptive.
- The BFF pattern means we can add the `active` field to all response schemas without backwards compatibility concerns.
- Default `True` means all existing devices remain active after migration with no manual intervention.

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Add `active` boolean field to Device model, default `True`
- [ ] Create Alembic migration for the new field
- [ ] Automatic CRON-based rotation skips inactive devices (they are not queued)
- [ ] Fleet-wide manual trigger (`POST /rotation/trigger`) skips inactive devices
- [ ] Single-device manual rotation (`POST /devices/<id>/rotate`) still works for inactive devices
- [ ] Deactivating a device mid-rotation (QUEUED/PENDING) does not cancel in-flight rotation
- [ ] Reactivation requires no special handling; device rejoins next rotation naturally
- [ ] Rotation dashboard shows inactive devices in a separate "inactive" group (4th group)
- [ ] Rotation dashboard excludes inactive devices from healthy/warning/critical groups
- [ ] Rotation status endpoint includes an `inactive` count
- [ ] `active` field is updatable via `PATCH /devices/{id}`
- [ ] `active` field is visible in GET device list and GET device detail responses
- [ ] No filter parameters added to device list endpoint
- [ ] Authentication, firmware, config, provisioning endpoints are unaffected by active flag

---

## 2) Affected Areas & File Map

- Area: `app/models/device.py` -- Device model
- Why: Add `active: Mapped[bool]` column with default `True`.
- Evidence: `app/models/device.py:34-89` -- existing column definitions using `Mapped[type]` and `mapped_column()`.

- Area: `alembic/versions/008_add_device_active_flag.py` -- New migration
- Why: Add `active` boolean column with server default `True` to the `devices` table.
- Evidence: `alembic/versions/007_drop_coredumps_filename.py:19` -- `revision = "007"`, so next is `008`.

- Area: `app/schemas/device.py` -- Device schemas
- Why: Add `active` field to `DeviceSummarySchema`, `DeviceResponseSchema`, and create `DevicePatchSchema` for the new PATCH endpoint.
- Evidence: `app/schemas/device.py:51-98` -- `DeviceSummarySchema` and `DeviceResponseSchema` define the fields visible in responses. `DeviceUpdateSchema` (line 32) only has `config`.

- Area: `app/services/device_service.py` -- DeviceService
- Why: Add `patch_device()` method that accepts partial updates via keyword arguments (initially just `active`). The method should accept `**kwargs` from `model_dump(exclude_unset=True)` so only explicitly provided fields are updated. No changes to `trigger_rotation()` -- single-device rotation remains unaffected by active flag.
- Evidence: `app/services/device_service.py:328-374` -- existing `update_device()` method pattern. `app/services/device_service.py:464-489` -- `trigger_rotation()` which must NOT check active flag.

- Area: `app/services/rotation_service.py` -- RotationService
- Why: (1) Filter `trigger_fleet_rotation()` to skip inactive devices. (2) Add `inactive` count to `get_rotation_status()`. (3) Add `inactive` group to `get_dashboard_status()`.
- Evidence: `app/services/rotation_service.py:123-140` -- `trigger_fleet_rotation()` queries `Device.rotation_state == OK`. `app/services/rotation_service.py:80-121` -- `get_rotation_status()` counts by state. `app/services/rotation_service.py:427-489` -- `get_dashboard_status()` categorizes devices.

- Area: `app/api/devices.py` -- Devices API
- Why: Add `PATCH /devices/<int:device_id>` endpoint using `DevicePatchSchema`.
- Evidence: `app/api/devices.py:145-178` -- existing PUT endpoint pattern to follow.

- Area: `app/schemas/rotation.py` -- Rotation schemas
- Why: Add `inactive` top-level field to `RotationStatusSchema`, add `inactive` list and count to `DashboardResponseSchema`, and add `active: bool` field to `DashboardDeviceSchema` so the frontend can render active/inactive indicators for all dashboard devices.
- Evidence: `app/schemas/rotation.py:8-28` -- `RotationStatusSchema`. `app/schemas/rotation.py:58-73` -- `DashboardDeviceSchema`. `app/schemas/rotation.py:76-96` -- `DashboardResponseSchema`.

- Area: `app/data/test_data/devices.json` -- Test data
- Why: Add at least one device with `"active": false` to exercise the inactive path in development and verify dashboard grouping.
- Evidence: `app/data/test_data/devices.json:1-74` -- existing device fixtures.

- Area: `app/services/test_data_service.py` -- TestDataService
- Why: Read and apply `active` field from device test data JSON.
- Evidence: `app/services/test_data_service.py:128-176` -- device loading loop that maps JSON fields to Device columns.

- Area: `tests/services/test_device_service.py` -- DeviceService tests
- Why: Add tests for `patch_device()` method.
- Evidence: `tests/services/test_device_service.py:1-80` -- existing test structure.

- Area: `tests/services/test_rotation_service.py` -- RotationService tests
- Why: Add tests for inactive device exclusion in fleet rotation, dashboard grouping, and status count.
- Evidence: `tests/services/test_rotation_service.py:68-130` -- fleet rotation tests. `tests/services/test_rotation_service.py:490-683` -- dashboard tests.

- Area: `tests/api/test_devices.py` -- Device API tests
- Why: Add tests for PATCH endpoint and verify `active` field in GET responses.
- Evidence: `tests/api/test_devices.py:1-80` -- existing test patterns.

- Area: `tests/api/test_rotation.py` -- Rotation API tests
- Why: Add tests for inactive count in status and inactive group in dashboard.
- Evidence: `tests/api/test_rotation.py:1-138` -- existing rotation API tests.

---

## 3) Data Model / Contracts

- Entity / contract: `devices` table -- new `active` column
- Shape:
  ```
  active BOOLEAN NOT NULL DEFAULT TRUE
  ```
- Refactor strategy: Simple column addition with server default. No back-compat needed; all existing rows become `active=True` via default.
- Evidence: `app/models/device.py:34-89` -- existing column pattern.

- Entity / contract: `DevicePatchSchema` -- new request schema
- Shape:
  ```json
  { "active": true }
  ```
  All fields optional (partial update). Currently only `active`. The service method must use `data.model_dump(exclude_unset=True)` to distinguish "field not provided" from "field explicitly set", which is critical for future-proofing when nullable fields are added.
- Refactor strategy: New schema; no existing schema replaced. An empty body `{}` is valid and results in no changes (the device is returned as-is). This is intentional PATCH semantics.
- Evidence: `app/schemas/device.py:32-48` -- existing `DeviceUpdateSchema` for reference.

- Entity / contract: `DeviceSummarySchema` -- response schema for list
- Shape: Add `"active": true` boolean field.
- Refactor strategy: Add field directly; BFF pattern means frontend updates simultaneously.
- Evidence: `app/schemas/device.py:51-65` -- current fields.

- Entity / contract: `DeviceResponseSchema` -- response schema for detail
- Shape: Add `"active": true` boolean field.
- Refactor strategy: Same as above.
- Evidence: `app/schemas/device.py:78-98` -- current fields.

- Entity / contract: `RotationStatusSchema` -- add `inactive` count
- Shape: Add `"inactive": <int>` top-level field to the response. This field counts devices where `active == False`. Note: `counts_by_state` continues to count ALL devices (active and inactive) by rotation state. The `inactive` count is an orthogonal dimension; an inactive device in OK state will appear in both `counts_by_state["OK"]` and `inactive`. The frontend should use `inactive` as a separate indicator rather than subtracting from `counts_by_state` totals.
- Refactor strategy: Add field directly to schema and service return dict. Update schema description to document the relationship.
- Evidence: `app/schemas/rotation.py:8-28` -- current schema. `app/services/rotation_service.py:86-93` -- existing `counts_by_state` loop counts all devices.

- Entity / contract: `DashboardResponseSchema` -- add `inactive` group
- Shape:
  ```json
  {
    "healthy": [...],
    "warning": [...],
    "critical": [...],
    "inactive": [...],
    "counts": { "healthy": 10, "warning": 2, "critical": 1, "inactive": 3 }
  }
  ```
  Each device entry in all four lists includes the existing fields plus `"active": <bool>` (via updated `DashboardDeviceSchema`).
- Refactor strategy: Add `inactive` list and update `counts` dict. Add `active: bool` to `DashboardDeviceSchema`.
- Evidence: `app/schemas/rotation.py:58-73` -- `DashboardDeviceSchema`. `app/schemas/rotation.py:76-96` -- current `DashboardResponseSchema` with three groups.

---

## 4) API / Integration Surface

- Surface: `PATCH /api/devices/{device_id}`
- Inputs: JSON body `{ "active": <bool> }` -- all fields optional (partial update).
- Outputs: `DeviceResponseSchema` (200) with updated device data.
- Errors: 404 if device not found, 400 if payload invalid.
- Evidence: `app/api/devices.py:145-178` -- existing PUT endpoint pattern.

- Surface: `GET /api/devices` (existing, response changes)
- Inputs: Unchanged (optional `model_id` and `rotation_state` query params).
- Outputs: `DeviceListResponseSchema` -- each `DeviceSummarySchema` now includes `active: bool`.
- Errors: Unchanged.
- Evidence: `app/api/devices.py:39-74` -- list endpoint.

- Surface: `GET /api/devices/{device_id}` (existing, response changes)
- Inputs: Unchanged.
- Outputs: `DeviceResponseSchema` now includes `active: bool`.
- Errors: Unchanged.
- Evidence: `app/api/devices.py:114-142` -- get endpoint.

- Surface: `POST /api/rotation/trigger` (existing, behavior change)
- Inputs: Unchanged (no body).
- Outputs: Unchanged (`RotationTriggerResponseSchema`). `queued_count` will now exclude inactive devices.
- Errors: Unchanged.
- Evidence: `app/api/rotation.py:53-93` -- fleet trigger endpoint.

- Surface: `GET /api/rotation/status` (existing, response changes)
- Inputs: Unchanged.
- Outputs: `RotationStatusSchema` gains `inactive: int` field.
- Errors: Unchanged.
- Evidence: `app/api/rotation.py:26-50` -- status endpoint.

- Surface: `GET /api/rotation/dashboard` (existing, response changes)
- Inputs: Unchanged.
- Outputs: `DashboardResponseSchema` gains `inactive` list and `counts.inactive` integer.
- Errors: Unchanged.
- Evidence: `app/api/rotation.py:96-124` -- dashboard endpoint.

- Surface: `POST /api/devices/{device_id}/rotate` (existing, no behavior change)
- Inputs: Unchanged.
- Outputs: Unchanged. Still works for inactive devices.
- Errors: Unchanged.
- Evidence: `app/api/devices.py:255-294` -- single-device rotation trigger.

- Surface: CLI `rotation-job` (existing, behavior change)
- Inputs: Unchanged.
- Outputs: Unchanged. The underlying `process_rotation_job()` calls `trigger_fleet_rotation()` which will now skip inactive devices.
- Errors: Unchanged.
- Evidence: `app/startup.py:199-249` -- rotation-job command.

---

## 5) Algorithms & State Machines

- Flow: Fleet rotation queueing (modified)
- Steps:
  1. Query all devices where `rotation_state == OK` AND `active == True`.
  2. Set each matching device's `rotation_state` to `QUEUED`.
  3. Flush and return count.
- States / transitions: No change to the rotation state machine itself. The `active` flag only gates entry into the state machine at the QUEUED transition during fleet rotation.
- Hotspots: None; up to 200 devices, single query.
- Evidence: `app/services/rotation_service.py:123-140` -- current `trigger_fleet_rotation()`.

- Flow: Dashboard categorization (modified)
- Steps:
  1. Fetch all devices with model info.
  2. Build `device_data` dict for each device (existing fields plus `"active": device.active`).
  3. For each device: if `device.active is False`, add to `inactive` group and skip further categorization.
  4. Otherwise, categorize by rotation state as before (healthy/warning/critical).
  5. Return all four groups with counts.
- States / transitions: None.
- Hotspots: None; up to 200 devices, single pass.
- Evidence: `app/services/rotation_service.py:427-489` -- current `get_dashboard_status()`. The `device_data` dict at line 459-467 must be extended with `active`.

- Flow: Rotation status counting (modified)
- Steps:
  1. Count devices by rotation state (existing logic, unchanged).
  2. Add separate count of devices where `active == False`.
  3. Return combined result.
- States / transitions: None.
- Hotspots: None; single additional count query.
- Evidence: `app/services/rotation_service.py:80-121` -- current `get_rotation_status()`.

---

## 6) Derived State & Invariants

- Derived value: `inactive` count in rotation status
  - Source: Filtered query on `Device.active == False` (all devices regardless of rotation state).
  - Writes / cleanup: Read-only; no writes triggered.
  - Guards: None needed; purely derived from current device state.
  - Invariant: `inactive` count must equal the total number of devices with `active == False`.
  - Evidence: `app/services/rotation_service.py:80-121`

- Derived value: Dashboard `inactive` group membership
  - Source: Filtered view of all devices where `active == False`.
  - Writes / cleanup: Read-only; no writes triggered.
  - Guards: Inactive check runs before state-based categorization, ensuring no device appears in both `inactive` and `healthy`/`warning`/`critical`.
  - Invariant: A device appears in exactly one dashboard group. Inactive devices never appear in healthy/warning/critical.
  - Evidence: `app/services/rotation_service.py:427-489`

- Derived value: Fleet rotation candidate set
  - Source: Filtered query on `Device.rotation_state == OK` AND `Device.active == True`.
  - Writes / cleanup: Matching devices have `rotation_state` set to `QUEUED`.
  - Guards: The `active` filter is applied at query time (WHERE clause), not post-fetch. This prevents any race where a device is deactivated between query and state update in the same transaction.
  - Invariant: Only active devices in OK state are queued during fleet rotation. Inactive devices are never auto-queued.
  - Evidence: `app/services/rotation_service.py:123-140`

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: All changes operate within the standard per-request Flask session. The `PATCH` endpoint, fleet rotation trigger, and rotation job each commit via the `teardown_request` handler (`app/__init__.py:214-238`). The CLI rotation-job explicitly commits (`app/startup.py:234`).
- Atomic requirements: The `patch_device()` method updates a single field and flushes. No multi-table writes. Fleet rotation updates multiple device rows in a single flush, which is already the existing pattern.
- Retry / idempotency: `PATCH` with `active=True` on an already-active device is a no-op at the data level (same value written). Fleet rotation is also idempotent: re-queuing already-queued devices is harmless because the query only selects OK devices.
- Ordering / concurrency controls: No new locking needed. The active flag is a simple boolean toggle. Deactivating a device mid-rotation is safe because the rotation state machine continues independently -- the `active` flag is only checked at the point of fleet queuing, not during PENDING/TIMEOUT processing.
- Evidence: `app/__init__.py:214-238` -- session teardown. `app/services/rotation_service.py:123-140` -- fleet rotation.

---

## 8) Errors & Edge Cases

- Failure: PATCH with invalid payload (e.g., `active` is not a boolean)
- Surface: `PATCH /api/devices/{device_id}`
- Handling: Pydantic validation returns 400 with validation error details.
- Guardrails: `DevicePatchSchema` enforces `active: bool` type.
- Evidence: `app/schemas/device.py:32-48` -- existing validation pattern.

- Failure: PATCH on non-existent device
- Surface: `PATCH /api/devices/{device_id}`
- Handling: `RecordNotFoundException` raised by `get_device()`, converted to 404 by `handle_api_errors`.
- Guardrails: Standard error handling chain.
- Evidence: `app/services/device_service.py:206-224` -- `get_device()` raises on missing.

- Failure: Deactivating a device that is currently QUEUED or PENDING
- Surface: `PATCH /api/devices/{device_id}` with `active=false`
- Handling: The patch succeeds. The in-flight rotation continues to completion or timeout. The `active` flag does not interfere with the rotation state machine.
- Guardrails: By design, `active` is only checked during fleet queuing, not during rotation processing.
- Evidence: `app/services/rotation_service.py:231-289` -- timeout processing does not check `active`. `app/services/rotation_service.py:302-331` -- device selection does not check `active`.

- Failure: PATCH with empty body `{}`
- Surface: `PATCH /api/devices/{device_id}`
- Handling: All fields in `DevicePatchSchema` are optional. An empty body is valid and results in no changes. The API layer uses `model_dump(exclude_unset=True)` which produces an empty dict, and `patch_device()` applies no changes. The device is returned as-is.
- Guardrails: Pydantic schema with all-optional fields handles this gracefully. The `exclude_unset` pattern ensures future nullable fields are not accidentally set to `None`.
- Evidence: New schema design decision.

---

## 9) Observability / Telemetry

- Signal: `record_operation("patch_device", status, duration)`
- Type: Counter + histogram (via existing `record_operation` utility)
- Trigger: On every `PATCH /api/devices/{device_id}` request.
- Labels / fields: `operation="patch_device"`, `status="success"|"error"`
- Consumer: Prometheus `/metrics` endpoint, existing dashboards.
- Evidence: `app/utils/iot_metrics.py` -- `record_operation` used by all device endpoints at `app/api/devices.py:73,111,142,177`.

No additional metrics are needed. The `active` flag is a simple boolean stored in the database; its effect on rotation is observable through the existing rotation status and dashboard endpoints, and the `inactive` count provides direct visibility.

---

## 10) Background Work & Shutdown

- Worker / job: CLI `rotation-job` (existing, behavior change only)
- Trigger cadence: Kubernetes CronJob schedule.
- Responsibilities: Calls `process_rotation_job()` which calls `trigger_fleet_rotation()`. After this change, `trigger_fleet_rotation()` filters by `active == True`.
- Shutdown handling: Unchanged. The rotation job is a short-lived CLI process.
- Evidence: `app/startup.py:199-249` -- rotation-job command.

No new background workers or shutdown hooks are introduced by this feature.

---

## 11) Security & Permissions

Not applicable. The `active` flag is an administrative field on the Device model. It does not affect authentication or authorization. The `/iot` endpoints remain completely unaffected -- inactive devices can still authenticate and access all device-facing endpoints. The admin API has no per-endpoint authorization beyond the existing auth middleware.

---

## 12) UX / UI Impact

- Entry point: Device detail page / device list page
- Change: The `active` boolean field appears in device list and detail responses. Frontend should display the active state (e.g., toggle switch or badge) and provide a way to toggle it via `PATCH`.
- User interaction: Admin can toggle a device's active state. Inactive devices appear grayed out or with an "inactive" indicator.
- Dependencies: Frontend consumes `active` field from `DeviceSummarySchema` and `DeviceResponseSchema`. Frontend sends `PATCH /api/devices/{id}` with `{ "active": false/true }`.
- Evidence: `app/schemas/device.py:51-98` -- schemas that frontend consumes.

- Entry point: Rotation dashboard page
- Change: A fourth group "inactive" appears with inactive devices separated from healthy/warning/critical. The counts section includes `inactive`.
- User interaction: Admin sees inactive devices in their own section, making it clear which devices are excluded from rotation.
- Dependencies: Frontend consumes `DashboardResponseSchema` with new `inactive` list and `counts.inactive`.
- Evidence: `app/schemas/rotation.py:76-96` -- dashboard schema.

---

## 13) Deterministic Test Plan

- Surface: `DeviceService.patch_device()`
- Scenarios:
  - Given an active device, When `patch_device(device_id, active=False)`, Then the device `active` field is `False` and the device is returned.
  - Given an inactive device, When `patch_device(device_id, active=True)`, Then the device `active` field is `True`.
  - Given a device in QUEUED state, When `patch_device(device_id, active=False)`, Then the device `active` is `False` but `rotation_state` remains `QUEUED` (no cancellation).
  - Given a device in PENDING state, When `patch_device(device_id, active=False)`, Then `active` is `False` but `rotation_state` remains `PENDING`.
  - Given a non-existent device_id, When `patch_device(device_id, active=False)`, Then `RecordNotFoundException` is raised.
  - Given an empty patch (no fields), When `patch_device(device_id)`, Then the device is returned unchanged.
- Fixtures / hooks: Existing `make_device` and `make_device_model` fixtures from `tests/conftest.py:150-181`.
- Gaps: None.
- Evidence: `tests/services/test_device_service.py:1-80` -- existing test patterns.

- Surface: `RotationService.trigger_fleet_rotation()` -- active filtering
- Scenarios:
  - Given 3 active OK devices and 1 inactive OK device, When `trigger_fleet_rotation()`, Then only 3 devices are queued.
  - Given all devices inactive with OK state, When `trigger_fleet_rotation()`, Then 0 devices are queued.
  - Given 2 active OK devices and 1 inactive QUEUED device, When `trigger_fleet_rotation()`, Then 2 devices are queued and the inactive device remains QUEUED.
- Fixtures / hooks: Existing device creation pattern with Keycloak mocking from `tests/services/test_rotation_service.py:72-103`.
- Gaps: None.
- Evidence: `tests/services/test_rotation_service.py:68-130` -- existing fleet rotation tests.

- Surface: `RotationService.get_rotation_status()` -- inactive count
- Scenarios:
  - Given 2 active devices and 1 inactive device, When `get_rotation_status()`, Then `inactive` count is 1.
  - Given no inactive devices, When `get_rotation_status()`, Then `inactive` count is 0.
  - Given all devices inactive, When `get_rotation_status()`, Then `inactive` count equals total device count.
- Fixtures / hooks: Same as above.
- Gaps: None.
- Evidence: `tests/services/test_rotation_service.py:12-66` -- existing status tests.

- Surface: `RotationService.get_dashboard_status()` -- inactive group
- Scenarios:
  - Given an inactive device in OK state, When `get_dashboard_status()`, Then device appears in `inactive` group, not in `healthy`.
  - Given an inactive device in TIMEOUT state, When `get_dashboard_status()`, Then device appears in `inactive` group, not in `warning` or `critical`.
  - Given a mix of active and inactive devices, When `get_dashboard_status()`, Then active devices appear in healthy/warning/critical as before, inactive devices appear only in `inactive`.
  - Given no inactive devices, When `get_dashboard_status()`, Then `inactive` list is empty and `counts.inactive` is 0.
- Fixtures / hooks: Same as above.
- Gaps: None.
- Evidence: `tests/services/test_rotation_service.py:490-683` -- existing dashboard tests.

- Surface: `PATCH /api/devices/{device_id}` -- API endpoint
- Scenarios:
  - Given an active device, When `PATCH /api/devices/{id}` with `{"active": false}`, Then 200 with `active=false` in response.
  - Given a device, When `PATCH /api/devices/{id}` with `{"active": "not_a_bool"}`, Then 400/422 validation error.
  - Given a non-existent device, When `PATCH /api/devices/99999`, Then 404.
  - Given a device, When `PATCH /api/devices/{id}` with `{}`, Then 200 with device unchanged.
- Fixtures / hooks: Existing `client` fixture and device creation pattern from `tests/api/test_devices.py:26-51`.
- Gaps: None.
- Evidence: `tests/api/test_devices.py:1-80` -- existing API test patterns.

- Surface: `GET /api/devices` -- active field in response
- Scenarios:
  - Given devices with varying `active` states, When `GET /api/devices`, Then each device summary includes `active` boolean.
- Fixtures / hooks: Existing fixtures.
- Gaps: None.
- Evidence: `tests/api/test_devices.py:15-51` -- existing list tests.

- Surface: `GET /api/rotation/status` -- inactive count
- Scenarios:
  - Given inactive devices exist, When `GET /api/rotation/status`, Then response includes `inactive` integer field.
- Fixtures / hooks: Existing fixtures.
- Gaps: None.
- Evidence: `tests/api/test_rotation.py:12-57` -- existing status API tests.

- Surface: `GET /api/rotation/dashboard` -- inactive group
- Scenarios:
  - Given inactive devices exist, When `GET /api/rotation/dashboard`, Then response includes `inactive` list and `counts.inactive`.
- Fixtures / hooks: Existing fixtures.
- Gaps: None.
- Evidence: `tests/api/test_rotation.py` -- no dashboard API tests exist yet, but pattern follows status tests.

- Surface: Single-device rotation for inactive device
- Scenarios:
  - Given an inactive device in OK state, When `POST /api/devices/{id}/rotate`, Then device is queued (200, status="queued"). Active flag does not block single-device rotation.
- Fixtures / hooks: Existing fixtures.
- Gaps: None.
- Evidence: `app/api/devices.py:255-294` -- single rotation trigger endpoint.

---

## 14) Implementation Slices

- Slice: Model + Migration
- Goal: Add `active` field to Device model and create Alembic migration.
- Touches: `app/models/device.py`, `alembic/versions/008_add_device_active_flag.py`
- Dependencies: None. Must be first.

- Slice: Schemas + Service
- Goal: Add `DevicePatchSchema`, update response schemas, add `patch_device()` to DeviceService.
- Touches: `app/schemas/device.py`, `app/services/device_service.py`
- Dependencies: Model slice must be complete.

- Slice: API endpoint
- Goal: Add `PATCH /api/devices/{device_id}` endpoint.
- Touches: `app/api/devices.py`
- Dependencies: Schema + service slice.

- Slice: Rotation logic
- Goal: Filter inactive devices from fleet rotation, add inactive count to status, add inactive group to dashboard.
- Touches: `app/services/rotation_service.py`, `app/schemas/rotation.py`
- Dependencies: Model slice.

- Slice: Test data
- Goal: Add inactive device(s) to test fixtures, update TestDataService to read `active` field.
- Touches: `app/data/test_data/devices.json`, `app/services/test_data_service.py`
- Dependencies: Model slice.

- Slice: Tests
- Goal: Comprehensive service and API tests for all new/changed behavior.
- Touches: `tests/services/test_device_service.py`, `tests/services/test_rotation_service.py`, `tests/api/test_devices.py`, `tests/api/test_rotation.py`
- Dependencies: All implementation slices.

---

## 15) Risks & Open Questions

- Risk: Migration applied before code deployment in a rolling update could expose `active` field not yet handled by old code.
- Impact: Minimal -- column has a server default of `True`, so old code ignores it and all devices behave as before.
- Mitigation: Default `True` ensures backward-safe migration. Deploy migration before or with code.

- Risk: PATCH endpoint with all-optional fields could be confusing if extended with more fields later that have complex interdependencies.
- Impact: Low for now; only one field.
- Mitigation: Keep the schema simple. If future fields have validation dependencies, add cross-field validators at that time.

- Risk: Inactive device in TIMEOUT state could be confusing on the dashboard -- it appears in "inactive" group even though it has a rotation problem.
- Impact: Low -- the admin deliberately deactivated it, so showing it as inactive is correct behavior per requirements.
- Mitigation: The dashboard device data includes `rotation_state`, so the frontend can still display TIMEOUT indicators within the inactive group if desired.

No open questions remain. All requirements are clear from the change brief and have been resolved through code analysis.

---

## 16) Confidence

Confidence: High -- This is a straightforward boolean flag addition with well-defined filtering behavior. All affected code paths have been identified, the existing patterns are clear, and the requirements leave no ambiguity.
