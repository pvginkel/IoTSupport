# Plan Review: Device Provisioning MDM

## 1) Summary & Decision

**Readiness**

The plan is comprehensive and well-researched. It demonstrates strong understanding of the existing codebase patterns (service container, API blueprints, SQLAlchemy models, testing fixtures) and proposes a coherent architecture for transforming the application from a simple config manager to a full MDM system. The research log shows thorough investigation of existing services. However, several significant gaps need addressing: the product brief states "no authentication required" and "no database" which directly contradicts the plan's assumptions; the plan introduces APScheduler without addressing multi-worker deployment concerns adequately; and the rotation secret caching introduces security considerations that need explicit handling.

**Decision**

`GO-WITH-CONDITIONS` - The plan is implementable but requires resolution of product brief alignment, clarification on scheduler deployment strategy, and explicit secret lifecycle management before proceeding.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/product_brief.md` - **Fail** - `plan.md:39-42` - "Transform the IoT Support backend from a simple config file manager into a full MDM application" - The product brief at lines 36-39 explicitly states "No authentication - Designed for trusted homelab environments" and "No database - Configurations stored as JSON files on the filesystem". The plan fundamentally changes both of these design decisions without updating the product brief.

- `CLAUDE.md` - **Pass** - `plan.md:333` - "Store as string column (CLAUDE.md prohibits native ENUM)" correctly references the guideline against PostgreSQL native ENUMs.

- `CLAUDE.md` - **Pass** - `plan.md:619-638` - Transaction patterns follow guidance on flush-before-external-call and rollback-on-failure for Keycloak integration.

- `docs/commands/plan_feature.md` - **Pass** - Plan structure follows all required sections with evidence and templates.

**Fit with codebase**

- `app/services/container.py` - `plan.md:229-230` - Plan correctly identifies need to register new services. The existing container pattern at `container.py:18-83` supports both Factory and Singleton providers as planned.

- `app/services/mqtt_service.py` - `plan.md:249-252` - Plan references MQTT service for rotation notifications. However, MqttService at `mqtt_service.py:227-251` only has `publish_config_update` and `publish_asset_update` methods; a new method for rotation topics will need to be added.

- `app/api/__init__.py` - `plan.md:237-239` - Plan correctly identifies blueprint registration pattern. However, the plan proposes a separate `/iot` blueprint outside the `/api` prefix, which requires additional wiring in `app/__init__.py` rather than just in `app/api/__init__.py`.

- `app/config.py` - `plan.md:225-227` - Settings class at `config.py:14-166` will need significant extension for Keycloak admin credentials and rotation settings.

---

## 3) Open Questions & Ambiguities

- Question: How does the plan align with the product brief's "no authentication" and "no database" statements?
- Why it matters: The plan fundamentally changes these architectural decisions. Either the product brief needs updating or the plan needs to justify this divergence.
- Needed answer: Confirmation that the product brief should be updated to reflect the new MDM architecture, or clarification on backwards compatibility requirements.

- Question: What is the deployment strategy for the rotation scheduler in multi-worker environments?
- Why it matters: `plan.md:993-994` mentions "single-worker deployment for scheduler" but this contradicts typical Kubernetes deployments with multiple replicas for availability.
- Needed answer: Explicit decision on whether to use leader election, database job store, or single-replica deployment with documented trade-offs.

- Question: Should the device key be recoverable after initial provisioning?
- Why it matters: `plan.md:1008-1010` flags this as an open question. The answer affects whether the admin API should allow viewing/regenerating device keys.
- Needed answer: Product decision on whether device key is displayed in admin UI or considered a secret.

- Question: How should firmware version changes trigger device awareness?
- Why it matters: `plan.md:1016-1018` explicitly defers OTA push capability, but devices need some mechanism to know when to check for firmware updates.
- Needed answer: Clarification on whether MQTT should notify devices of firmware updates (similar to config updates).

---

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: DeviceModelService CRUD operations
- Scenarios:
  - Given no models, When create_model, Then model created with timestamps (`tests/services/test_device_model_service.py::test_create_model_minimal`)
  - Given model exists, When create_model with same code, Then RecordExistsException (`tests/services/test_device_model_service.py::test_create_model_duplicate_code`)
  - Given model with devices, When delete_model, Then InvalidOperationException (`tests/services/test_device_model_service.py::test_delete_model_with_devices`)
- Instrumentation: `iot_device_count` gauge with model_code label
- Persistence hooks: Migration 002 creates device_models table
- Gaps: None identified
- Evidence: `plan.md:843-852`

- Behavior: Device creation with Keycloak integration
- Scenarios:
  - Given model exists, When create_device, Then device created with key, Keycloak client created (`tests/services/test_device_service.py::test_create_device_success`)
  - Given Keycloak unavailable, When create_device, Then ExternalServiceException, no device created (`tests/services/test_device_service.py::test_create_device_keycloak_failure`)
- Instrumentation: `iot_keycloak_operations_total` counter
- Persistence hooks: Migration 002 creates devices table; Keycloak client created as external side effect
- Gaps: **Major** - Plan at `plan.md:623-624` states "Create Keycloak client first, then DB insert" but does not specify rollback mechanism if DB insert fails after Keycloak client creation. Need explicit cleanup strategy.
- Evidence: `plan.md:856-864`

- Behavior: Rotation state machine transitions
- Scenarios:
  - Given device in OK, When CRON triggers, Then state becomes QUEUED (`tests/services/test_rotation_service.py::test_cron_trigger_queues_devices`)
  - Given device in PENDING past timeout, When job runs, Then secret restored, state becomes TIMEOUT (`tests/services/test_rotation_service.py::test_pending_timeout_restores_secret`)
- Instrumentation: `iot_rotation_state_count` gauge, `iot_rotation_duration_seconds` histogram
- Persistence hooks: Device.rotation_state, cached_secret columns updated
- Gaps: **Major** - Plan does not specify test scenario for concurrent rotation attempts (two job instances selecting same device). `plan.md:636` mentions `FOR UPDATE` but no test coverage specified.
- Evidence: `plan.md:877-886`

- Behavior: IoT device authentication via JWT
- Scenarios:
  - Given valid device JWT, When GET /iot/config, Then config returned (`tests/api/test_iot.py::test_get_config_valid_token`)
  - Given expired JWT, When GET /iot/config, Then 401 (`tests/api/test_iot.py::test_get_config_expired_token`)
  - Given device in PENDING, When GET /iot/config with new JWT, Then rotation completed (`tests/api/test_iot.py::test_rotation_completion_on_config_fetch`)
- Instrumentation: Existing `iot_auth_validation_total` counter reused
- Persistence hooks: Device JWT fixture needed for tests
- Gaps: **Minor** - Plan at `plan.md:467-469` extracts device key from `azp` claim but does not specify test for malformed client ID in token.
- Evidence: `plan.md:919-928`

- Behavior: Firmware version extraction from ESP32 binary
- Scenarios:
  - Given valid ESP32 binary, When extract_version, Then version string returned (`tests/services/test_firmware_service.py::test_extract_version_valid`)
  - Given binary with wrong magic, When extract_version, Then ValidationException (`tests/services/test_firmware_service.py::test_extract_version_invalid_magic`)
- Instrumentation: None specified (acceptable for synchronous operation)
- Persistence hooks: DeviceModel.firmware_version column updated
- Gaps: **Minor** - Plan does not specify sample firmware binary fixture format for tests.
- Evidence: `plan.md:888-897`

---

## 5) Adversarial Sweep

**Major - Keycloak Client Orphan Risk on DB Failure**

**Evidence:** `plan.md:623-624` - "Create Keycloak client first, then DB insert, rollback Keycloak on DB failure"

**Why it matters:** If the Keycloak client is created successfully but the subsequent DB insert fails (constraint violation, connection drop), the plan states to "rollback Keycloak" but Keycloak does not support transactional rollback. The client will remain as an orphan in Keycloak, potentially blocking future device creation with the same key.

**Fix suggestion:** Add explicit error handling that attempts to delete the Keycloak client if DB insert fails. Document this as best-effort cleanup with potential for orphaned clients. Consider adding a startup reconciliation check that removes Keycloak clients without matching database records.

**Confidence:** High

---

**Major - Cached Secret Column Security Exposure**

**Evidence:** `plan.md:1004-1006` - "Cached secret column creates security liability... Clear cached_secret immediately after use, consider encryption at rest"

**Why it matters:** The `cached_secret` column stores the previous Keycloak client secret in plaintext to enable timeout recovery. An attacker with database read access gains previous credentials for all rotating devices. The plan acknowledges this risk but defers mitigation to "consider encryption".

**Fix suggestion:** Specify concrete mitigation: either (1) encrypt cached_secret using application-level encryption with a key from environment, or (2) store only a hash sufficient to verify the old secret was correctly restored to Keycloak, or (3) accept the risk with documented rationale that the secret is short-lived (5 min timeout) and database compromise already implies full system compromise.

**Confidence:** High

---

**Major - APScheduler Multi-Worker Race Condition**

**Evidence:** `plan.md:992-994` - "APScheduler job doesn't run in multi-worker deployment... Mitigation: Use APScheduler persistent job store (database), or single-worker deployment for scheduler"

**Why it matters:** Kubernetes deployments typically run multiple replicas. If multiple workers run APScheduler with in-memory job store, each will execute the rotation job independently, causing race conditions in device selection and potential double-rotations despite the `FOR UPDATE` lock (which only prevents concurrent transactions, not concurrent job executions selecting different devices).

**Fix suggestion:** Specify one of: (1) Use APScheduler's SQLAlchemy job store with `misfire_grace_time` to coalesce jobs, (2) Separate scheduler into a single-replica deployment/sidecar, or (3) Use Kubernetes CronJob to trigger rotation via HTTP endpoint instead of in-process scheduler. Document the chosen approach in the plan.

**Confidence:** High

---

**Minor - CRON Schedule Parsing Ambiguity**

**Evidence:** `plan.md:537` - "Check if CRON schedule matches (compare last_scheduled_at with current time)"

**Why it matters:** The plan mentions CRON syntax but does not specify the library for parsing or how "matching" is determined. Different CRON libraries have different behaviors for edge cases (DST transitions, missed schedules).

**Fix suggestion:** Specify use of `croniter` library (commonly paired with APScheduler) and document behavior for missed schedules (e.g., after deployment downtime).

**Confidence:** Medium

---

## 6) Derived-Value & Persistence Invariants

- Derived value: `keycloak_client_id`
  - Source dataset: Computed from `device_model.code` (immutable) + `device.key` (immutable)
  - Write / cleanup triggered: Keycloak client create on device create; Keycloak client delete on device delete
  - Guards: Model code and device key immutability enforced at service layer (no update endpoints for these fields)
  - Invariant: `client_id == f"iotdevice-{device.device_model.code}-{device.key}"` must hold for all Keycloak operations
  - Evidence: `plan.md:588-593`

- Derived value: `rotation_state` (state machine)
  - Source dataset: Combination of timeout checks, job execution, and device API calls
  - Write / cleanup triggered: State transitions update Device record; MQTT published on QUEUED->PENDING; cached_secret written on QUEUED->PENDING, cleared on completion/timeout
  - Guards: State transitions validated (e.g., only PENDING->OK allowed on rotation completion); `FOR UPDATE` lock prevents concurrent selection
  - Invariant: At most one device can be in PENDING state at any time (single rotation at a time)
  - Evidence: `plan.md:519-533`

- Derived value: `firmware_path`
  - Source dataset: Derived from `ASSETS_DIR` env var + `device_model.code` (immutable)
  - Write / cleanup triggered: File written on firmware upload; file deleted on model deletion
  - Guards: Model code immutability prevents path drift after firmware upload
  - Invariant: `path == ASSETS_DIR / f"firmware-{model.code}.bin"` - firmware file path matches model code
  - Evidence: `plan.md:603-607`

- Derived value: `secret_age` (for UI display)
  - Source dataset: `device.secret_created_at` compared to current time
  - Write / cleanup triggered: UI display only, no persistence
  - Guards: Read-only computation
  - Invariant: Calculation uses server time, not client time
  - Evidence: `plan.md:595-600`

---

## 7) Risks & Mitigations (top 3)

- Risk: Product brief misalignment may cause stakeholder confusion about application scope
- Mitigation: Update `docs/product_brief.md` before implementation to reflect MDM architecture, authentication requirements, and database usage
- Evidence: `plan.md:39-42` vs `docs/product_brief.md:36-39`

- Risk: Multi-worker scheduler execution causes rotation race conditions
- Mitigation: Document and implement one of the approaches in Finding #3 (SQLAlchemy job store, separate scheduler deployment, or Kubernetes CronJob)
- Evidence: `plan.md:992-994`

- Risk: Keycloak API changes break rotation flow silently
- Mitigation: Pin Keycloak version in deployment; add integration test against real Keycloak in CI; implement version check at startup as stated in `plan.md:990`
- Evidence: `plan.md:989-991`

---

## 8) Confidence

Confidence: Medium - The plan is thorough and well-aligned with codebase patterns, but the product brief contradiction, scheduler deployment ambiguity, and secret caching security concern need resolution before implementation can proceed with high confidence.
