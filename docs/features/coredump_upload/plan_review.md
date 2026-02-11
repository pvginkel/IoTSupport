# Plan Review: Coredump Upload & Firmware ZIP Support

## 1) Summary & Decision

**Readiness**

The plan is well-structured, research-backed, and closely follows existing codebase patterns. Both features (coredump upload and firmware ZIP support) are additive with no database migrations required. The coredump upload slice is clean and implementation-ready. The firmware ZIP slice initially had a concrete design gap around how `FirmwareService.get_firmware_stream()` resolves the versioned ZIP path without database access. This review identified three conditions (firmware_version threading, container wiring specificity, COREDUMPS_DIR production validation) and a minor improvement (microsecond filename precision). **All conditions have been applied directly to the plan** -- the affected areas, algorithms, error handling, and risk sections have been updated accordingly. The test plan is thorough and scenarios are correctly identified.

**Decision**

`GO` -- All conditions identified during review have been resolved by updating the plan. The firmware download path now explicitly threads `firmware_version` through call sites, the container wiring is specified with a concrete provider declaration, the COREDUMPS_DIR production validation is documented as intentionally omitted, and the filename format uses microsecond precision. The plan is implementation-ready.

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md` (layering: API -> Service -> Model) -- Pass -- `plan.md:55-56,109-111,121-122` -- "New `CoredumpService` for filesystem-based coredump storage", "Add `POST /coredump` endpoint... delegates to `CoredumpService`". Clean API/service separation.
- `CLAUDE.md` (service pattern) -- Pass -- `plan.md:109-111` -- CoredumpService follows singleton pattern matching FirmwareService. No database access needed, so BaseService is correctly not used.
- `CLAUDE.md` (error handling) -- Pass -- `plan.md:353-393` -- Uses `ValidationException` and `InvalidOperationException` from `app.exceptions`, consistent with `app/utils/error_handling.py:156-163` which maps them to 400.
- `CLAUDE.md` (testing requirements) -- Pass -- `plan.md:454-509` -- Service tests and API tests are both planned with Given/When/Then scenarios. Covers success paths, error conditions, and edge cases.
- `CLAUDE.md` (DI container wiring) -- Pass -- `plan.md:117-119` -- CoredumpService registered as singleton matching `app/services/container.py:101-105` FirmwareService pattern.
- `docs/product_brief.md` (device-facing API) -- Pass -- `plan.md:55,229-233` -- New endpoint under `/api/iot/` consistent with existing device-facing endpoints at `app/api/iot.py:38`.
- `CLAUDE.md` (no database enums as native types) -- N/A -- No database changes in this plan.
- `CLAUDE.md` (metrics/observability) -- Pass -- `plan.md:397-418` -- Uses existing `record_operation()` pattern matching `app/api/iot.py:117-119`.

**Fit with codebase**

- `FirmwareService` singleton -- `plan.md:113-115` -- The plan adds `save_firmware_zip()` and modifies `get_firmware_stream()` on a singleton service. Since FirmwareService has no database session, the versioned ZIP download path that needs `firmware_version` from the database (plan Section 5, step 2) cannot be resolved within FirmwareService alone. See Adversarial Sweep finding #1.
- `app/api/iot.py` device auth pattern -- `plan.md:121-123` -- The new coredump endpoint correctly reuses the existing `before_request` device auth hook and `get_device_auth_context()` pattern from `app/utils/device_auth.py:136-142`. Good fit.
- `app/api/pipeline.py` upload detection -- `plan.md:125-127,283-284` -- ZIP magic detection (`PK\x03\x04`) at the API layer is a reasonable approach; the current code at `app/api/pipeline.py:60-64` already distinguishes multipart vs raw body.
- `tests/conftest.py` fixture pattern -- `plan.md:165-167` -- Plan notes `coredumps_dir` addition to test settings. The current `_build_test_settings` at `tests/conftest.py:50-115` does not include a `coredumps_dir` field because the Settings model does not have one yet. The plan correctly identifies both config.py and conftest.py need updates.
- `app/__init__.py` wire_modules -- `plan.md:137-139` -- The plan correctly notes that `app.api.iot` is already in the wire list at `app/__init__.py:70`. However, since `CoredumpService` will be injected into the `iot.py` endpoint via `@inject`, the wiring is already covered.

## 3) Open Questions & Ambiguities

- Question: How does `FirmwareService.get_firmware_stream()` obtain `firmware_version` for the versioned ZIP lookup?
- Why it matters: The current method signature is `get_firmware_stream(self, model_code: str)` (`app/services/firmware_service.py:74`). The plan's algorithm (Section 5, lines 300-308) requires the current `firmware_version` from the database to locate `ASSETS_DIR/{model_code}/firmware-{version}.zip`, but `FirmwareService` is a stateless singleton with no database access. Section 15 acknowledges this risk but proposes only "extend to accept an optional `firmware_version` parameter" without specifying how the IoT endpoint (which calls `firmware_service.get_firmware_stream(model_code)` directly at `app/api/iot.py:203`) would obtain the version.
- Needed answer: Decide whether `get_firmware_stream()` gets `firmware_version` as an explicit parameter (requiring the IoT endpoint to look up the device model first) or whether the service scans the filesystem for the latest ZIP. The former is cleaner; update the IoT endpoint plan to show the device model lookup.

- Question: Should the coredump endpoint path be `/api/iot/coredump` or `/iot/coredump`?
- Why it matters: The requirements checklist (plan line 83) says `POST /iot/coredump`, but the API surface section (plan line 229) says `POST /api/iot/coredump`. Looking at the codebase, `iot_bp` has prefix `/iot` (`app/api/iot.py:38`) and is nested under `api_bp` which has prefix `/api`, so the full path is `/api/iot/coredump`. The change brief line 9 also says `POST /iot/coredump`. This is a minor inconsistency -- the actual URL will be `/api/iot/coredump`.
- Needed answer: Clarify that the requirement refers to the blueprint-relative path and the actual URL is `/api/iot/coredump`. No code impact.

- Question: What happens to legacy flat `.bin` files when the same firmware version is re-uploaded as a ZIP?
- Why it matters: The plan says step 9 of the ZIP upload flow "also writes/overwrites the legacy flat `.bin`" (plan line 291). If a previously uploaded plain `.bin` had a different version than the ZIP, this silently overwrites it. While this is probably desired behavior, it is worth explicitly stating.
- Needed answer: Confirm that overwriting the legacy `.bin` on every ZIP upload is intentional.

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: `CoredumpService.save_coredump()`
- Scenarios:
  - Given valid inputs, When `save_coredump()` is called, Then `.dmp` and `.json` sidecar are created (`tests/services/test_coredump_service.py::test_save_coredump_success`)
  - Given content > 1MB, When `save_coredump()` is called, Then `ValidationException` is raised (`tests/services/test_coredump_service.py::test_save_coredump_exceeds_max_size`)
  - Given empty content, When `save_coredump()` is called, Then `ValidationException` is raised (`tests/services/test_coredump_service.py::test_save_coredump_empty`)
  - Given `coredumps_dir` is None, When `save_coredump()` is called, Then `InvalidOperationException` is raised (`tests/services/test_coredump_service.py::test_save_coredump_not_configured`)
  - Given sidecar read back, Then it contains chip, firmware_version, device_key, model_code, uploaded_at (`tests/services/test_coredump_service.py::test_save_coredump_sidecar_content`)
- Instrumentation: Structured INFO log on save (plan lines 413-418)
- Persistence hooks: `COREDUMPS_DIR` in `app/config.py`, `coredumps_dir` in `tests/conftest.py::_build_test_settings`, `CoredumpService` provider in `app/services/container.py`
- Gaps: None identified.
- Evidence: `plan.md:457-466`

- Behavior: `FirmwareService.save_firmware_zip()` (new method)
- Scenarios:
  - Given a valid ZIP, When `save_firmware_zip()` is called, Then ZIP stored at versioned path and legacy `.bin` updated (`tests/services/test_firmware_service.py::test_save_firmware_zip_valid`)
  - Given ZIP missing `.elf`, When called, Then `ValidationException` (`tests/services/test_firmware_service.py::test_save_firmware_zip_missing_elf`)
  - Given ZIP with extra files, When called, Then `ValidationException` (`tests/services/test_firmware_service.py::test_save_firmware_zip_extra_files`)
  - Given ZIP with invalid `.bin` header, When called, Then `ValidationException` (`tests/services/test_firmware_service.py::test_save_firmware_zip_invalid_bin`)
- Instrumentation: Uses existing `pipeline_upload_firmware` metric path; new `pipeline_upload_firmware_zip` operation metric (plan lines 406-411)
- Persistence hooks: Versioned directory `ASSETS_DIR/{model_code}/` created on disk; no migration needed
- Gaps: None identified.
- Evidence: `plan.md:468-479`

- Behavior: `POST /api/iot/coredump` endpoint
- Scenarios:
  - Given authenticated device + valid params + body, When POST, Then 201 with filename (`tests/api/test_iot.py::test_upload_coredump_success`)
  - Given missing `chip` param, When POST, Then 400 (`tests/api/test_iot.py::test_upload_coredump_missing_chip`)
  - Given missing `firmware_version` param, When POST, Then 400 (`tests/api/test_iot.py::test_upload_coredump_missing_firmware_version`)
  - Given empty body, When POST, Then 400 (`tests/api/test_iot.py::test_upload_coredump_empty_body`)
  - Given body > 1MB, When POST, Then 400 (`tests/api/test_iot.py::test_upload_coredump_exceeds_max_size`)
  - Given no auth, When POST, Then 401 (`tests/api/test_iot.py::test_upload_coredump_unauthorized`)
- Instrumentation: `iot_upload_coredump` counter + histogram via `record_operation()` (plan lines 399-404)
- Persistence hooks: `coredumps_dir` in test Settings, container wiring
- Gaps: None identified.
- Evidence: `plan.md:481-492`

- Behavior: `FirmwareService.get_firmware_stream()` (modified -- ZIP fallback)
- Scenarios:
  - Given versioned ZIP exists, When `get_firmware_stream()` is called, Then `.bin` extracted from ZIP is returned (`tests/services/test_firmware_service.py::test_get_firmware_stream_from_zip`)
  - Given no ZIP but legacy `.bin` exists, When called, Then legacy `.bin` returned (`tests/services/test_firmware_service.py::test_get_firmware_stream_legacy_fallback`)
  - Given neither exists, When called, Then `RecordNotFoundException` (`tests/services/test_firmware_service.py::test_get_firmware_stream_not_found`)
- Instrumentation: Existing firmware download metrics
- Persistence hooks: No new persistence; read-only filesystem access
- Gaps: The plan does not specify how tests will provide `firmware_version` to the modified `get_firmware_stream()` method, which depends on the resolution of Open Question #1.
- Evidence: `plan.md:474-477`

- Behavior: Pipeline firmware upload (ZIP detection path)
- Scenarios:
  - Given valid ZIP via pipeline, When POST, Then 200 with version from `.bin` inside ZIP (`tests/api/test_pipeline.py::test_upload_firmware_zip_success`)
  - Given invalid ZIP structure, When POST, Then 400 (`tests/api/test_pipeline.py::test_upload_firmware_zip_invalid`)
  - Given plain `.bin` upload, When POST, Then 200 as before (`tests/api/test_pipeline.py::test_upload_firmware_bin_backward_compat`)
- Instrumentation: `pipeline_upload_firmware_zip` metric (plan lines 406-411)
- Persistence hooks: No new persistence hooks; uses existing DeviceModelService transaction scope
- Gaps: None identified.
- Evidence: `plan.md:494-501`

## 5) Adversarial Sweep

**Major -- FirmwareService.get_firmware_stream() cannot resolve versioned ZIP path without firmware_version [RESOLVED]**

**Evidence:** `plan.md:299-308` (Algorithm: "Firmware download with ZIP fallback", step 2: "Look up device model to get current `firmware_version`") + `app/services/firmware_service.py:42,74` (FirmwareService is a stateless singleton; `get_firmware_stream(self, model_code: str)` has no DB access)

**Why it matters:** The ZIP fallback algorithm requires knowing the current `firmware_version` to construct the path `ASSETS_DIR/{model_code}/firmware-{version}.zip`. FirmwareService is a singleton without database access. The IoT endpoint at `app/api/iot.py:203` calls `firmware_service.get_firmware_stream(model_code)` without passing a version.

**Resolution applied to plan:** Sections 2, 4, and 5 have been updated to explicitly show: (a) `get_firmware_stream()` gains an optional `firmware_version: str | None = None` parameter; (b) the IoT firmware endpoint is modified to look up the device model's `firmware_version` and pass it through; (c) `DeviceModelService.get_firmware_stream()` already has access to the model and passes `model.firmware_version`. Section 15 risk #3 has been updated with the complete threading strategy.

**Confidence:** High

---

**Major -- CoredumpService not wired into iot.py endpoint via container injection [RESOLVED]**

**Evidence:** `plan.md:117-119` -- "Register `CoredumpService` as a singleton provider." But the endpoint's `@inject` decorator requires the service to be available as `Provide[ServiceContainer.coredump_service]`, which means the CoredumpService provider must be declared in `ServiceContainer` AND the `app.api.iot` module must be in the wire list.

**Why it matters:** If the provider is not explicitly added to `ServiceContainer`, the `Provide[ServiceContainer.coredump_service]` reference in the endpoint will fail at import time with `AttributeError`.

**Resolution applied to plan:** Section 2 has been updated to include the concrete provider declaration: `coredump_service = providers.Singleton(CoredumpService, coredumps_dir=config.provided.coredumps_dir)`.

**Confidence:** Medium -- The original plan mentioned this, the update makes it explicit.

---

**Major -- COREDUMPS_DIR production validation missing [RESOLVED]**

**Evidence:** `plan.md:371-375` -- "Service is created with `None` path; upload attempts raise `InvalidOperationException`." + `app/config.py:334-421` -- `validate_production_config()` validates `ASSETS_DIR` for production (line 363-367) but the plan did not mention whether `COREDUMPS_DIR` should be added to production validation.

**Why it matters:** If a production deployment forgets to set `COREDUMPS_DIR`, coredump uploads will fail with a 400 error at runtime rather than failing fast at startup.

**Resolution applied to plan:** Section 8 has been updated to explicitly document that `COREDUMPS_DIR` is intentionally omitted from `validate_production_config()` because coredump support is optional -- not all deployments need coredump collection. This is a deliberate design difference from `ASSETS_DIR`.

**Confidence:** Medium

---

**Minor -- Sub-second coredump filename collision not addressed with a concrete guard [RESOLVED]**

**Evidence:** `plan.md:539-541` -- Original plan used seconds-only timestamps.

**Why it matters:** While the probability is very low, the fix is trivial.

**Resolution applied to plan:** Sections 5, 6, 7, and 15 have been updated to use microsecond-precision timestamps in the filename format (`YYYYMMDDTHHMMSS_{microseconds}Z`), effectively closing this risk at zero additional complexity.

**Confidence:** Low -- Probability was genuinely very low at this scale even before the fix.

## 6) Derived-Value & Persistence Invariants

- Derived value: Coredump filename timestamp
  - Source dataset: Server-side UTC time at moment of `save_coredump()` call (unfiltered)
  - Write / cleanup triggered: Creates `{device_key}/coredump_{timestamp}.dmp` and `.json` on disk
  - Guards: Timestamp is server-generated, not client-supplied; per-device directory isolation
  - Invariant: Each `.dmp` file has exactly one corresponding `.json` sidecar with the same base name
  - Evidence: `plan.md:314-319`

- Derived value: Versioned firmware ZIP path
  - Source dataset: `firmware_version` extracted from `.bin` inside the uploaded ZIP via `extract_version()` (unfiltered -- uses proven binary parser at `app/services/firmware_service.py:154-202`)
  - Write / cleanup triggered: ZIP written to `ASSETS_DIR/{model_code}/firmware-{version}.zip`; legacy `.bin` also overwritten at `ASSETS_DIR/firmware-{model_code}.bin`
  - Guards: Version extraction validates AppInfo magic number and non-empty version string; upload rejected on failure. Database `DeviceModel.firmware_version` is updated in same transaction.
  - Invariant: The version in the ZIP filename matches the AppInfo version in the `.bin` contained within that ZIP. The `DeviceModel.firmware_version` in the database matches the latest uploaded version.
  - Evidence: `plan.md:321-326`, `app/services/firmware_service.py:154-202`

- Derived value: Firmware stream source selection (ZIP vs legacy)
  - Source dataset: `DeviceModel.firmware_version` from database (filtered by model code) + filesystem existence check for `ASSETS_DIR/{model_code}/firmware-{version}.zip`
  - Write / cleanup triggered: None -- read-only derivation
  - Guards: Falls back to legacy `.bin` if versioned ZIP is absent; raises `RecordNotFoundException` if neither exists
  - Invariant: If a versioned ZIP exists for the current `firmware_version`, the `.bin` served to the device is byte-identical to what was in the uploaded ZIP
  - Evidence: `plan.md:328-333`

- Derived value: Coredump sidecar `model_code` field
  - Source dataset: `DeviceAuthContext.model_code` extracted from JWT `azp` claim via `parse_device_client_id()` at `app/utils/device_auth.py:51-68`
  - Write / cleanup triggered: Written to `.json` sidecar file alongside coredump
  - Guards: Model code is parsed from a validated JWT token using a regex pattern (`DEVICE_CLIENT_ID_PATTERN`); cannot be spoofed by the device
  - Invariant: The `model_code` in the sidecar always matches the device's actual model assignment
  - Evidence: `plan.md:188-194`, `app/utils/device_auth.py:19,51-68`

## 7) Risks & Mitigations (top 3)

- Risk: The firmware download path requires `firmware_version` from the database, but `FirmwareService` is a stateless singleton. If the interface change is not carefully threaded through all call sites (IoT endpoint, admin download, DeviceModelService), firmware downloads could break or silently serve stale legacy `.bin` files.
- Mitigation: Update the plan to explicitly show the `firmware_version` parameter threading through `get_firmware_stream()` and all call sites. Ensure tests cover both ZIP-present and legacy-fallback paths from the actual API endpoints, not just the service layer.
- Evidence: `plan.md:547-549` (acknowledged risk), `app/api/iot.py:203`, `app/services/device_model_service.py:267`

- Risk: Accumulated coredumps and versioned firmware ZIPs consume disk space with no retention or cleanup mechanism.
- Mitigation: The plan explicitly defers this (plan line 67: "Cleanup/retention policy for old coredumps or firmware ZIPs" is out of scope). Acceptable for initial implementation at 200-device scale. Document in operational runbook that manual cleanup may be needed, and consider adding a disk usage metric for `COREDUMPS_DIR`.
- Evidence: `plan.md:543-545`

- Risk: ZIP processing in memory could be a concern if firmware binaries grow beyond expected size, and there is no explicit size limit on firmware ZIP uploads (unlike the 1MB limit on coredumps).
- Mitigation: The plan notes "firmware binaries are typically under 2MB" (plan line 295). Consider adding a configurable max size for firmware uploads (e.g., 10MB) to prevent accidental large uploads from consuming excessive memory.
- Evidence: `plan.md:295`

## 8) Confidence

Confidence: High -- The plan is thorough, well-researched, and follows established patterns. All conditions identified during review have been applied directly to the plan. Both the coredump upload and firmware ZIP slices are now implementation-ready with explicit design decisions, concrete container wiring, and resolved interface questions.
