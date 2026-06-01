# IoT Device Fleet Architecture - Requirements Verification Report

**Date Generated:** 2026-06-01
**Task:** Verify that the IoT Device Fleet Architecture feature implementation satisfies the User Requirements Checklist from `plan.md` section "1a) User Requirements Checklist"

---

## Verification Summary

| Item | Status | Evidence |
|------|--------|----------|
| 1. Realize logical firmware elements from production database | **PASS** | See below |
| 2. Ensure correct edges are added | **PASS** | See below |
| 3. Expose API(s) for iotsupport-pipeline client | **PASS** | See below |
| 4. Call endpoint(s) from Jenkinsfile.architecture | **PASS** | See below |
| 5. Generate deployed-architecture.yaml artifact | **PASS** | See below |
| 6. Add ARCHITECTURE_PIPELINE_TRIGGER_URL env variable | **PASS** | See below |
| 7. Trigger after device configuration changes | **PASS** | See below |
| 8. device_model changes also trigger pipeline | **PASS** | See below |
| 9. Model new edge from IoT Support to Jenkins | **PASS** | See below |

**Total: 9/9 PASS, 0/9 FAIL**

---

## Detailed Verification

### 1. Realize the logical (firmware) elements based on data in the production database

**Status: PASS**

**Evidence:**

- **File:** `app/services/device_service.py:212-252`
  - Method `get_fleet_projection()` implements the projection endpoint
  - Query at line 228-233: `select(Device).options(selectinload(Device.device_model)).order_by(Device.key)`
  - Returns unfiltered full fleet (no `active` filter per plan §3/§6)
  - Device data includes: key, model_code (from device_model.code), firmware_version, device_name, created_at

- **File:** `tools/gen-architecture.py:350-495`
  - `generate_artifact()` function at line 350 processes the projection and dataset
  - Lines 419-481: Per-device element emission
  - For each device: mints `device:` + `ss:<firmware>-<key>` uuid5 elements (lines 429-430)
  - Builds device/ss element dicts with identity-fenced stats (lines 432-447)
  - Emits Specialization edges to firmware product (line 451)
  - Emits Assignment edges device → ss (line 450)

**Conclusion:** The generator successfully realizes logical firmware elements by projecting the database fleet into the federated model.

---

### 2. Ensure the correct edges are added

**Status: PASS**

**Evidence:**

- **File:** `tools/gen-architecture.py:449-481`
  - Line 450: Assignment edge `device → ss:<firmware>-<key>`
  - Line 451: Specialization edge `ss:<firmware>-<key> → firmware-product (from firmware-products.yaml)`
  - Lines 454-459: Serving edges per logical Association on the firmware
  - Lines 480-481: Aggregation edges from firmware grouping to ss instances

- **File:** `tests/tools/test_gen_architecture.py:123-177`
  - Test `test_per_device_elements_and_edges()` validates all four edge types
  - Asserts Assignment, Specialization, Serving (4 edges for calendar device), and Aggregation edges are present

- **File:** `docs/architecture/architecture.yaml:69-127`
  - Lines 122-126: Hand-authored `app:iotsupport-app → cap:continuous-integration` Association edge modeling the Jenkins trigger

**Conclusion:** All required edges (Assignment, Specialization, Serving, Aggregation) plus the Jenkins trigger edge are correctly implemented.

---

### 3. Expose API(s) accessible by the `iotsupport-pipeline` client to drive this

**Status: PASS**

**Evidence:**

- **File:** `app/api/pipeline.py:123-154`
  - Endpoint: `GET /api/pipeline/fleet-projection` (lines 123-154)
  - Decorator: `@allow_roles("pipeline")` at line 130 (guards with pipeline role)
  - Returns: FleetProjectionResponseSchema (line 145)
  - Call to `device_service.get_fleet_projection()` (line 144)

- **File:** `app/schemas/pipeline.py:77-88`
  - FleetProjectionResponseSchema defined with devices list and fleet config
  - Devices carry: key, model_code, firmware_version, device_name, created_at
  - Fleet carries: mqtt_url, oidc_issuer_url

- **File:** `app/services/container.py:105`
  - Line 105: `additional_roles=["pipeline"]` configures the pipeline role in the auth service

- **File:** `tests/api/test_pipeline.py:268-345`
  - Test `TestPipelineFleetProjection` verifies the endpoint
  - Line 332-344: Tests role-based access (401/403 for missing token/role, 200 for pipeline role)

**Conclusion:** The projection API is fully implemented, role-protected, and accessible by the pipeline client.

---

### 4. Call the endpoint(s) from the `Jenkinsfile.architecture` script

**Status: PASS**

**Evidence:**

- **File:** `Jenkinsfile.architecture:17-34`
  - Stage "Generate" at lines 17-34
  - Lines 22-26: withCredentials binding IOTSUPPORT_API_URL, _TOKEN_URL, _CLIENT_ID, _CLIENT_SECRET
  - Line 33: Executes `./tools/gen-architecture.py`

- **File:** `tools/gen-architecture.py:615-624`
  - Lines 615-624: `main()` function's projection-fetch logic
  - Line 618: requires `IOTSUPPORT_API_URL` from environment (line 618)
  - Lines 619-623: fetch_token() client-credentials flow
  - Line 624: fetch_projection() calls `GET /api/pipeline/fleet-projection` with Bearer token

**Conclusion:** The Jenkinsfile correctly binds credentials and invokes the generator, which fetches from the projection endpoint.

---

### 5. Generate a `deployed-architecture.yaml` file exposed as a Jenkins artifact

**Status: PASS**

**Evidence:**

- **File:** `tools/gen-architecture.py:576-642`
  - Lines 636: `Path(args.output).write_text(dump_yaml(artifact), encoding="utf-8")`
  - Default output path: `docs/architecture/deployed-architecture.yaml` (line 580)

- **File:** `Jenkinsfile.architecture:35-42`
  - Stage "Architecture" at lines 35-42
  - Line 41: archiveArtifacts includes `docs/architecture/deployed-architecture.yaml`
  - archiveArtifacts makes the file available as a Jenkins artifact (fingerprinted)

- **File:** `tests/tools/test_gen_architecture.py:286-295`
  - Test `test_determinism_byte_identical()` confirms output is deterministic
  - Multiple artifact generations produce byte-identical YAML

**Conclusion:** The deployed-architecture.yaml artifact is generated and archived by Jenkins as required.

---

### 6. Add a new environment variable holding a URL that triggers the Jenkins job

**Status: PASS**

**Evidence:**

- **File:** `app/app_config.py:84`
  - AppEnvironment field: `ARCHITECTURE_PIPELINE_TRIGGER_URL: str | None = Field(default=None)`

- **File:** `app/app_config.py:142`
  - AppSettings field: `architecture_pipeline_trigger_url: str | None = None`

- **File:** `app/app_config.py:205`
  - Loaded via: `architecture_pipeline_trigger_url=env.ARCHITECTURE_PIPELINE_TRIGGER_URL`

- **File:** `app/services/container.py:189-192`
  - ArchitecturePipelineTriggerService registered as singleton with config dependency
  - Config passed at line 191: `config=app_config`

**Conclusion:** The ARCHITECTURE_PIPELINE_TRIGGER_URL environment variable is properly defined and configured.

---

### 7. Call that trigger after changes are made to device configuration (add/edit/remove devices)

**Status: PASS**

**Evidence:**

- **File:** `app/services/device_service.py:358`
  - create_device(): `self.trigger_service.mark_pending()` at line 358

- **File:** `app/services/device_service.py:427`
  - update_device(): `self.trigger_service.mark_pending()` at line 427

- **File:** `app/services/device_service.py:450-459`
  - delete_device() method (lines 430-459)
  - Line 451: `self.db.delete(device)` and flush
  - Line 454-456: Keycloak delete (best-effort)
  - Line 457: `self.trigger_service.mark_pending()`

- **File:** `app/__init__.py:251-255`
  - teardown_request at line 227
  - Line 254-255: Post-commit firing: `container.architecture_pipeline_trigger_service().fire_if_pending()`
  - Fires ONLY when committed (line 246: `db_session.commit()` succeeds), never on rollback (line 244)

- **File:** `tests/services/test_architecture_trigger_wiring.py:35-165`
  - TestCrudMarkPendingWiring: Tests all CRUD paths call mark_pending()
  - test_create_device_marks_pending() (line 38)
  - test_update_device_marks_pending() (line 53)
  - test_delete_device_marks_pending() (line 75)

- **File:** `tests/services/test_architecture_trigger_wiring.py:171-212`
  - TestPostCommitFiring: Tests teardown fires trigger post-commit
  - test_commit_fires_once_after_durable_write() (line 171) proves commit-before-fire ordering

**Conclusion:** Device CRUD operations correctly mark pending, and the trigger fires post-commit via teardown_request.

---

### 8. device_model changes also trigger the pipeline

**Status: PASS**

**Evidence:**

- **File:** `app/services/device_model_service.py:147`
  - create_device_model(): `self.trigger_service.mark_pending()` at line 147

- **File:** `app/services/device_model_service.py:182`
  - update_device_model(): `self.trigger_service.mark_pending()` at line 182

- **File:** `app/services/device_model_service.py:215`
  - delete_device_model(): `self.trigger_service.mark_pending()` at line 215

- **File:** `app/services/device_model_service.py:264`
  - upload_firmware(): `self.trigger_service.mark_pending()` at line 264

- **File:** `tests/services/test_architecture_trigger_wiring.py:92-142`
  - test_create_model_marks_pending() (line 92)
  - test_update_model_marks_pending() (line 103)
  - test_delete_model_marks_pending() (line 117)
  - test_upload_firmware_marks_pending() (line 129)

**Conclusion:** All device model CRUD operations and firmware uploads trigger the pipeline.

---

### 9. Model the new edge from IoT Support to Jenkins

**Status: PASS**

**Evidence:**

- **File:** `docs/architecture/architecture.yaml:119-126`
  - Relation ID: `rel:iotsupport-consumes-continuous-integration` (line 122)
  - Source: `app:iotsupport-app` (line 123)
  - Target: `cap:continuous-integration` (line 124)
  - Type: `Association` (line 125)
  - BoundBy: `env:ARCHITECTURE_PIPELINE_TRIGGER_URL` (line 126)
  - Comment (lines 119-121): Explains the edge models best-effort POST to Jenkins webhook

**Conclusion:** The Jenkins edge is properly modeled in the hand-authored architecture.yaml with the correct capability binding.

---

## Additional Verification: Supporting Implementation Details

### Trigger Service Implementation

**File:** `app/services/architecture_pipeline_trigger_service.py:44-129`

- Constructor: enables service when URL is truthy (line 58)
- mark_pending(): sets ContextVar flag (line 75)
- fire_if_pending(): fires empty-body POST only when pending and enabled (lines 89-128)
- Best-effort: catches exceptions, logs warnings, never propagates errors (lines 120-128)
- Short timeout: 5 seconds (line 55) to prevent request blocking

**Tests:** `tests/services/test_architecture_pipeline_trigger_service.py:27-95`
- Behavioral tests for enable/disable, fire/skip, error handling, flag clearing

### Projection Endpoint Schema

**File:** `app/schemas/pipeline.py:23-88`

- FleetProjectionDeviceSchema: key, model_code, firmware_version, device_name, created_at (no secrets/rotation state)
- FleetConfigSchema: mqtt_url, oidc_issuer_url (for host tiebreaking)
- FleetProjectionResponseSchema: devices list + fleet config

### Generator Features

**File:** `tools/gen-architecture.py`

- Provider resolution (lines 163-315): caps, concrete svcs, host tiebreaking
- Artifact generation (lines 350-495): per-device elements, all edge types
- Determinism (line 573): yaml.safe_dump with sort_keys=False, default_flow_style=False
- UUID5 namespace: IOTSUPPORT_NS constant (line 46) ensures stable, namespaced ids
- Error handling: GeneratorError on unmapped code, missing provider instance (shape c), etc.

**File:** `.gitignore:18`
- `docs/architecture/deployed-architecture.yaml` is ignored (not committed)

### Container DI Wiring

**File:** `app/services/container.py:189-192, 231-237, 240-248`

- ArchitecturePipelineTriggerService registered as singleton
- Injected into DeviceModelService and DeviceService factories
- Accessed in teardown via `container.architecture_pipeline_trigger_service()`

### Annotation File

**File:** `docs/architecture/firmware-products.yaml:16-24`

- Maps device model codes (snake_case) to firmware product UUIDs
- 8 products: calendar_display, doorbell_receiver, gesture_device, infra_statistics_display, intercom, paper_clock, somfy_remote, underfloor_heating_controller
- Comments explain the mapping is explicit (not derived from string munging)

### Rotation Path Exclusion

**File:** `tests/services/test_architecture_trigger_wiring.py:144-165`

- test_rotation_does_not_mark_pending(): Confirms rotation mutations do NOT trigger
- Rotation path (app/startup.py:199-262) mutates runtime state only; no mark_pending() call
- Prevents wasted Jenkins builds on every rotation step

---

## Conclusion

All 9 checklist items have been successfully implemented with concrete evidence in the codebase:

1. ✅ Logical firmware elements realized from database fleet
2. ✅ Correct edges added (Assignment, Specialization, Serving, Aggregation)
3. ✅ Pipeline API endpoint (GET /api/pipeline/fleet-projection) with role-based access
4. ✅ Jenkinsfile invokes generator with client credentials
5. ✅ deployed-architecture.yaml generated and archived
6. ✅ ARCHITECTURE_PIPELINE_TRIGGER_URL env var configured
7. ✅ Device CRUD triggers post-commit firing
8. ✅ Device model CRUD and firmware upload trigger
9. ✅ Jenkins edge modeled in hand-authored architecture.yaml

**Implementation Status: COMPLETE**
