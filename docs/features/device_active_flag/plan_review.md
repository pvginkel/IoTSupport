# Plan Review -- Device Active Flag

## 1) Summary & Decision

**Readiness**

The plan is well-structured, thorough, and closely aligned with the existing codebase patterns. The file map is exhaustive with accurate line references, the test plan is comprehensive, and the data model change is minimal and safe. However, there are several issues that need addressing before implementation: a missing design for the `DevicePatchSchema` handling of the "no fields provided" edge case, an incomplete accounting of all codebase locations that build `device_data` dicts (the dashboard `device_data` dict should include `active` for the frontend to render indicators within the inactive group), and a gap in the rotation status `inactive` count design where the count semantics relative to `counts_by_state` totals need clarification.

**Decision**

`GO-WITH-CONDITIONS` -- The plan is sound and implementable but has three Major-level issues (inactive count double-counting ambiguity, missing `active` field in dashboard device data, and insufficient PATCH validation for all-optional schema) that should be resolved in the plan before implementation begins.

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md` (layering: API thin, service owns logic) -- Pass -- `plan.md:104-106` -- "Add `patch_device()` method... No changes to `trigger_rotation()`". API delegates to service method, consistent with the project's layered architecture.
- `CLAUDE.md` (SQLAlchemy model conventions) -- Pass -- `plan.md:92-94` -- "Add `active: Mapped[bool]` column with default `True`". Uses `Mapped[type]` annotation consistent with `app/models/device.py:45-89`.
- `CLAUDE.md` (no native PostgreSQL ENUMs) -- Pass -- `plan.md:148-154` -- The new column is a plain `BOOLEAN NOT NULL DEFAULT TRUE`, not an enum.
- `CLAUDE.md` (Pydantic schema naming) -- Pass -- `plan.md:101` -- `DevicePatchSchema` follows the `*Schema` naming convention. The `Patch` infix is a reasonable addition to the existing `Create`/`Update` naming pattern.
- `CLAUDE.md` (testing requirements) -- Pass -- `plan.md:390-468` -- Test plan covers service methods, API endpoints, success and error paths, edge cases.
- `CLAUDE.md` (BFF pattern / no backwards compat) -- Pass -- `plan.md:64-65` -- Correctly leverages BFF to add fields to response schemas without versioning.
- `docs/product_brief.md` (rotation state machine) -- Pass -- `plan.md:255` -- "The `active` flag only gates entry into the state machine at the QUEUED transition during fleet rotation." Does not modify the state machine itself.
- `docs/commands/plan_feature.md` (all sections present) -- Pass -- All 16 sections are present and populated.

**Fit with codebase**

- `DeviceService` -- `plan.md:104-106` -- The plan assumes a new `patch_device()` method. `DeviceService` at `app/services/device_service.py:33` is a plain class (not inheriting `BaseService`), and the plan correctly proposes adding a new method following the existing `update_device()` pattern at line 328. Good fit.
- `RotationService.trigger_fleet_rotation()` -- `plan.md:109` -- Current code at `app/services/rotation_service.py:131` queries `Device.rotation_state == RotationState.OK.value`. Adding `Device.active == True` to the WHERE clause is a minimal, clean change. Good fit.
- `RotationService.get_dashboard_status()` -- `plan.md:109-110` -- Current code at `app/services/rotation_service.py:452-478` loops over all devices and categorizes them. Inserting an early `active` check before state categorization is straightforward. Good fit.
- `ServiceContainer` -- `plan.md:117` -- The container at `app/services/container.py:222-229` wires `DeviceService` as a Factory. No DI wiring changes are needed since `patch_device()` is just a new method on the existing service. Good fit.
- `app/api/devices.py` container wiring -- Not explicitly mentioned in plan -- The new PATCH endpoint needs `DeviceService` injection. Since `devices_bp` is already wired (all existing endpoints use `Provide[ServiceContainer.device_service]`), this will work automatically. No gap.

## 3) Open Questions & Ambiguities

- Question: Should the `inactive` count in `RotationStatusSchema` reflect devices that are also counted in `counts_by_state`?
- Why it matters: Currently `counts_by_state` counts ALL devices by their rotation state. If `inactive` is a top-level peer field, an inactive device in OK state would be counted in both `counts_by_state["OK"]` and `inactive`. This double-counting could confuse the frontend. The plan should explicitly state whether `counts_by_state` should exclude inactive devices (breaking change to existing semantics) or whether double-counting is intentional (and the frontend handles it).
- Needed answer: Explicit statement of whether `counts_by_state` filters out inactive devices or counts all devices regardless of active status.

- Question: Should the `DevicePatchSchema` require at least one field to be provided?
- Why it matters: The plan at line 335-339 says an empty body `{}` is valid and results in no changes. While this is harmless, it means the PATCH endpoint becomes a no-op read-and-return. If additional fields are added later, the "all optional, empty is fine" pattern may mask bugs where the frontend sends an empty patch unintentionally. This is a design choice that should be explicit.
- Needed answer: Confirmation that the empty-body-is-valid behavior is intentional, or add a `model_validator` that requires at least one field.

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: `DeviceService.patch_device()` -- new method
- Scenarios:
  - Given an active device, When `patch_device(id, active=False)`, Then device.active is False (`tests/services/test_device_service.py::TestDeviceServicePatch::test_patch_device_deactivate`)
  - Given an inactive device, When `patch_device(id, active=True)`, Then device.active is True (`tests/services/test_device_service.py::TestDeviceServicePatch::test_patch_device_activate`)
  - Given a QUEUED device, When `patch_device(id, active=False)`, Then device.active is False AND rotation_state remains QUEUED (`tests/services/test_device_service.py::TestDeviceServicePatch::test_patch_device_deactivate_queued`)
  - Given nonexistent ID, When `patch_device(id, active=False)`, Then RecordNotFoundException (`tests/services/test_device_service.py::TestDeviceServicePatch::test_patch_device_not_found`)
  - Given empty patch, When `patch_device(id)`, Then device returned unchanged (`tests/services/test_device_service.py::TestDeviceServicePatch::test_patch_device_empty`)
- Instrumentation: `record_operation("patch_device", status, duration)` via existing `iot_metrics.py` utility.
- Persistence hooks: No migration needed beyond the model column. No DI wiring changes.
- Gaps: None.
- Evidence: `plan.md:392-402`

- Behavior: `RotationService.trigger_fleet_rotation()` -- active filtering
- Scenarios:
  - Given 3 active OK + 1 inactive OK, When `trigger_fleet_rotation()`, Then 3 queued (`tests/services/test_rotation_service.py::TestRotationServiceTriggerFleet::test_trigger_fleet_rotation_skips_inactive`)
  - Given all inactive OK, When `trigger_fleet_rotation()`, Then 0 queued (`tests/services/test_rotation_service.py::TestRotationServiceTriggerFleet::test_trigger_fleet_rotation_all_inactive`)
- Instrumentation: Existing rotation job metrics (`iot_rotation_job_runs_total`) cover this path.
- Persistence hooks: No migration beyond model column.
- Gaps: None.
- Evidence: `plan.md:404-411`

- Behavior: `RotationService.get_dashboard_status()` -- inactive group
- Scenarios:
  - Given inactive OK device, When `get_dashboard_status()`, Then device in inactive group, not healthy (`tests/services/test_rotation_service.py::TestRotationServiceDashboard::test_dashboard_inactive_ok`)
  - Given inactive TIMEOUT device, When `get_dashboard_status()`, Then device in inactive group, not warning/critical (`tests/services/test_rotation_service.py::TestRotationServiceDashboard::test_dashboard_inactive_timeout`)
  - Given mix of active/inactive, When `get_dashboard_status()`, Then correct grouping (`tests/services/test_rotation_service.py::TestRotationServiceDashboard::test_dashboard_mixed`)
- Instrumentation: No new metrics needed; dashboard is read-only.
- Persistence hooks: No migration beyond model column.
- Gaps: **Major** -- The plan at `plan.md:259-267` describes adding `active` check before state categorization, but does not specify that the `device_data` dict (built at `app/services/rotation_service.py:459-467`) should include the `active` field. Without `active` in `device_data`, the frontend cannot display active/inactive indicators within the inactive group. This should be added to the plan.
- Evidence: `plan.md:259-267`, `app/services/rotation_service.py:459-467`

- Behavior: `RotationService.get_rotation_status()` -- inactive count
- Scenarios:
  - Given 2 active + 1 inactive, When `get_rotation_status()`, Then `inactive` == 1 (`tests/services/test_rotation_service.py::TestRotationServiceGetStatus::test_status_inactive_count`)
  - Given no inactive, When `get_rotation_status()`, Then `inactive` == 0 (`tests/services/test_rotation_service.py::TestRotationServiceGetStatus::test_status_no_inactive`)
- Instrumentation: No new metrics needed.
- Persistence hooks: No migration beyond model column.
- Gaps: **Major** -- The plan does not clarify whether `counts_by_state` should exclude inactive devices. See Open Questions section.
- Evidence: `plan.md:269-276`

- Behavior: `PATCH /api/devices/{device_id}` -- new endpoint
- Scenarios:
  - Given active device, When PATCH with `{"active": false}`, Then 200 with active=false (`tests/api/test_devices.py::TestDevicesPatch::test_patch_device_deactivate`)
  - Given device, When PATCH with `{"active": "not_a_bool"}`, Then 400/422 (`tests/api/test_devices.py::TestDevicesPatch::test_patch_device_invalid_payload`)
  - Given nonexistent device, When PATCH 99999, Then 404 (`tests/api/test_devices.py::TestDevicesPatch::test_patch_device_not_found`)
  - Given device, When PATCH with `{}`, Then 200 unchanged (`tests/api/test_devices.py::TestDevicesPatch::test_patch_device_empty_body`)
- Instrumentation: `record_operation("patch_device", ...)`.
- Persistence hooks: Container wiring already handles `DeviceService` injection.
- Gaps: None.
- Evidence: `plan.md:432-440`

- Behavior: `GET /api/devices` and `GET /api/devices/{id}` -- `active` field in responses
- Scenarios:
  - Given devices with varying active states, When GET list, Then each summary includes `active` boolean (`tests/api/test_devices.py::TestDevicesList::test_list_devices_includes_active`)
- Instrumentation: No new metrics.
- Persistence hooks: Schema changes only.
- Gaps: None.
- Evidence: `plan.md:442-447`

- Behavior: Test data update
- Scenarios: At least one device in `devices.json` has `"active": false`.
- Instrumentation: N/A.
- Persistence hooks: `app/services/test_data_service.py` must read and apply `active` field from JSON.
- Gaps: None.
- Evidence: `plan.md:120-126`

## 5) Adversarial Sweep

**Major -- Inactive count double-counting in RotationStatusSchema**

**Evidence:** `plan.md:175-178` -- "Add `inactive: int` top-level field to the response." Cross-ref with `app/services/rotation_service.py:86-93` where `counts_by_state` loops over all `RotationState` enum values and counts ALL devices matching each state, regardless of `active` flag.

**Why it matters:** After this change, an inactive device in OK state would be counted in both `counts_by_state["OK"]` (value 1) and `inactive` (value 1). The frontend cannot derive the "active OK devices" count without doing subtraction (`counts_by_state["OK"] - inactive_who_are_in_OK`), and it cannot even do that because `inactive` is a single aggregate across all states. This creates a semantic inconsistency: the sum of `counts_by_state` values equals total devices, but `inactive` is a subset of those same devices. If the frontend displays these side by side, the numbers will not add up to the total in an intuitive way.

**Fix suggestion:** Either (a) filter `counts_by_state` to only count active devices and note the semantic change, or (b) add `inactive_by_state` as a parallel dict, or (c) keep current behavior but explicitly document the double-counting in the plan and the schema description so the frontend developer understands the relationship.

**Confidence:** High

---

**Major -- Dashboard device_data dict missing `active` field**

**Evidence:** `plan.md:259-267` describes the dashboard categorization change. The current `device_data` dict at `app/services/rotation_service.py:459-467` contains `id`, `key`, `device_name`, `device_model_code`, `rotation_state`, `last_rotation_completed_at`, and `days_since_rotation`. The plan does not mention adding `active` to this dict.

**Why it matters:** Devices in the `inactive` group will lack the `active` field in their data. While group membership implicitly conveys active status, the frontend may want to render a consistent toggle/badge for all devices. More importantly, the `DashboardDeviceSchema` at `app/schemas/rotation.py:58-73` validates the dict -- if the frontend expects `active` there, the schema must include it.

**Fix suggestion:** Add `"active": device.active` to the `device_data` dict construction in `get_dashboard_status()`, and add `active: bool` field to `DashboardDeviceSchema`.

**Confidence:** High

---

**Major -- DevicePatchSchema with all-optional fields and SpectTree validation**

**Evidence:** `plan.md:157-163` -- "All fields optional (partial update). Currently only `active`." Cross-ref with the existing pattern at `app/api/devices.py:146-147` which uses `@api.validate(json=DeviceUpdateSchema, ...)`.

**Why it matters:** SpectTree generates OpenAPI docs from the schema. A schema where the only field is optional means the OpenAPI spec will show an empty object as valid input. Additionally, when SpectTree validates the request body against `DevicePatchSchema`, a request with `{}` passes validation and reaches the service layer where it does nothing. While harmless for a single-field schema, the plan should address: (1) how `patch_device()` determines which fields were actually provided vs. defaulted to `None` (Pydantic's `model_fields_set` or `exclude_unset`), and (2) whether SpectTree handles optional-only schemas correctly (some versions generate `required: []` which can cause issues).

**Fix suggestion:** Document in the plan that `patch_device()` should use `data.model_dump(exclude_unset=True)` to distinguish between "field not provided" and "field set to None", and verify SpectTree handles the schema correctly. This becomes critical when additional fields (potentially nullable ones) are added to `DevicePatchSchema` in the future.

**Confidence:** Medium

---

**Minor -- Test data service does not read `active` field**

**Evidence:** `plan.md:124-126` -- "Read and apply `active` field from device test data JSON." Cross-ref with `app/services/test_data_service.py:159-170` where the `Device()` constructor call does not include an `active` kwarg.

**Why it matters:** Without the update to `test_data_service.py`, the `"active": false` entries in `devices.json` will be silently ignored, and all test devices will be created with `active=True` (the column default). This would make the test data useless for verifying inactive device behavior during development.

**Fix suggestion:** The plan already identifies this at line 124-126 but should ensure the implementation slice at line 494-497 includes the `test_data_service.py` change alongside the `devices.json` update. Currently it does. This is noted for completeness.

**Confidence:** High (but already addressed in plan)

## 6) Derived-Value & Persistence Invariants

- Derived value: `inactive` count in rotation status
  - Source dataset: Filtered query `Device.active == False` across all devices (all rotation states).
  - Write / cleanup triggered: None; read-only derived value.
  - Guards: None needed; count is computed fresh on each request.
  - Invariant: `inactive` count must equal `SELECT COUNT(*) FROM devices WHERE active = FALSE`. Since `active` has a NOT NULL constraint with default TRUE, this count is always well-defined.
  - Evidence: `plan.md:282-287`, `app/services/rotation_service.py:86-93`

- Derived value: Dashboard group membership (inactive vs. healthy/warning/critical)
  - Source dataset: Filtered view partitioning all devices into exactly one of four groups based on `active` flag and `rotation_state`.
  - Write / cleanup triggered: None; read-only dashboard rendering.
  - Guards: The inactive check runs first in the loop, ensuring mutual exclusivity. A device with `active=False` always goes to `inactive` regardless of rotation state.
  - Invariant: `len(healthy) + len(warning) + len(critical) + len(inactive) == total_device_count`. No device appears in more than one group.
  - Evidence: `plan.md:289-294`, `app/services/rotation_service.py:452-478`

- Derived value: Fleet rotation candidate set
  - Source dataset: Filtered query `Device.rotation_state == OK AND Device.active == True`.
  - Write / cleanup triggered: Matching devices have `rotation_state` set to QUEUED.
  - Guards: Both conditions applied in a single WHERE clause within the same transaction. No TOCTOU risk because the query and update happen in the same session flush.
  - Invariant: After `trigger_fleet_rotation()`, no device with `active=False` has been moved to QUEUED state by that call. Devices already in QUEUED (from previous calls or single-device trigger) are unaffected.
  - Evidence: `plan.md:296-301`, `app/services/rotation_service.py:131-140`

## 7) Risks & Mitigations (top 3)

- Risk: The `inactive` count semantics relative to `counts_by_state` may confuse the frontend developer, leading to incorrect dashboard rendering where device totals appear inconsistent.
- Mitigation: Resolve the double-counting question explicitly in the plan before implementation. Document the relationship in the schema field descriptions.
- Evidence: `plan.md:175-178`, `app/services/rotation_service.py:86-93`

- Risk: The PATCH endpoint's all-optional schema interacts with SpectTree/OpenAPI generation. If SpectTree does not handle optional-only request bodies gracefully, the generated API docs may be misleading or cause client SDK issues.
- Mitigation: Validate SpectTree behavior with an all-optional schema during implementation of the API slice. Add a manual test to confirm OpenAPI spec correctness.
- Evidence: `plan.md:157-163`, `app/api/devices.py:146-147`

- Risk: Dashboard `device_data` dict missing the `active` field means the frontend cannot distinguish active from inactive devices within or across groups without relying solely on group membership.
- Mitigation: Add `active` to `device_data` dict and `DashboardDeviceSchema` during implementation of the rotation logic slice.
- Evidence: `plan.md:259-267`, `app/services/rotation_service.py:459-467`

## 8) Confidence

Confidence: High -- The plan is thorough and well-researched. The identified issues are all addressable with small, targeted plan amendments. No architectural or design-level concerns exist.
