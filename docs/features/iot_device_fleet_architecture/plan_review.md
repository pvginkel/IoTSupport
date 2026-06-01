# Plan Review — IoT Device Fleet Architecture (generated producer)

## 1) Summary & Decision

**Readiness**
The plan is unusually thorough and well-grounded: it correctly identifies the generated-producer pattern, the thin-projection-API-plus-repo-side-generator split, the `Device.key`-keyed uuid5 determinism, the fail-loud-on-unmapped-model invariant, the unfiltered (no `active`) fleet membership, and the `introduced = date(Device.created_at)` sourcing — all of which I verified against the codebase and the published dataset and found sound. The locked design decisions hold up. However, two implementation-shaping problems survive scrutiny. First, a **transaction-safety defect**: the plan places the best-effort trigger "after the service's `db.flush()`" (`plan.md:397-398`), but this repository commits in `teardown_request` *after* the request handler returns (`app/__init__.py:227-251`), so a service-level trigger fires *before* the row is durable and can even fire for a write that subsequently rolls back. Second, the **provider-resolution algorithm in §5 step 4 is underspecified against the real dataset shape**: `svc:home-assistant-mqtt` (which serves 6 of 8 firmware families) is realized by both a logical product *and* its own prd instance, and the plan's uniform "instance that Specializations the realizing product" mechanic does not resolve it. Both are fixable with small, well-scoped plan edits, but they are load-bearing for correctness.

**Decision**
`GO-WITH-CONDITIONS` — the architecture is right and the design decisions are sound, but the trigger must move to a post-commit hook (not post-flush) and the cross-producer provider-resolution algorithm must be re-specified to handle the heterogeneous realizer shapes actually present in the dataset (notably `svc:home-assistant-mqtt`). Evidence: `plan.md:397-398` vs `app/__init__.py:245`; `plan.md:323-326` vs dataset (`svc:home-assistant-mqtt` realized by `ss:home-assistant-prd` + `ss:home-assistant`).

## 2) Conformance & Fit (with evidence)

**Conformance to refs**
- `producer-manual.md` (generated producer: uuid5 natural key, no committed YAML, no per-element `producer:`) — Pass — `plan.md:13-21,274-277,356-357` — "IDs uuid5 from the IoT Support namespace constant. No `producer:` on elements". Matches manual ("Ids are uuid5-from-natural-key … YAML is a build artifact you don't commit"; "Do not emit a `producer:` attribute on elements").
- `producer-manual.md` (generated CI: generate → validate → archive) — Pass — `plan.md:190-196,303-308` — mirrors the manual's `stage('Generate')`/`stage('Validate')`/`stage('Archive')` recipe; `Jenkinsfile.architecture:15-21` shows the validate+archive already present.
- `iotsupport-iot-architecture-guidance.md` (realize every logical edge per registered device; `active` is rotation-only) — Pass — `plan.md:23-29,385-390` — "unfiltered `select(Device)` — explicitly NOT filtered on `Device.active`"; confirmed `active` is rotation-only at `app/models/device.py:65-68` and used only as the rotation flag in `update_device` (`app/services/device_service.py:359`).
- `guidance.md §4` (instance form: `device: —Assignment→ ss:<fw>-<key> —Specialization→ product`) — Pass — `plan.md:269-272` — edge set matches §4 (`guidance.md:170-190`).
- CLAUDE.md (thin API, service owns logic, typed exceptions, `@handle_api_errors`, metrics via `record_operation`) — Pass — `plan.md:146-148,447-459`; helper exists at `app/utils/iot_metrics.py:26-39`.
- CLAUDE.md / Golden Rule analog (durability ordering: commit before external side effect) — **Fail** — `plan.md:397-398` — places trigger after `flush()`, but commit is deferred to teardown (`app/__init__.py:245`). See Adversarial #1.

**Fit with codebase**
- `app/api/pipeline.py` — `plan.md:146-148,289-294` — sound: `@allow_roles("pipeline")` + `@inject` + `record_operation` finally-block pattern is exactly the existing `upload_firmware`/`get_firmware_version` shape (`app/api/pipeline.py:36-85`). The `pipeline` role is registered (`app/services/container.py:98-102`, `additional_roles=["pipeline"]`) so `@allow_roles("pipeline")` passes startup role validation (`app/utils/auth.py:98`).
- `app/services/device_service.py` / `device_model_service.py` trigger wiring — `plan.md:154-160` — assumption that these are the right write paths is correct (`device_service.py:246,328,378`; `device_model_service.py:104,142,175,205`), **but** all of them only `flush()`; none commit (commit is in teardown). The plan's "after flush" placement is the wrong hook (Adversarial #1).
- `ArchitecturePipelineTriggerService` as a Singleton mirroring `KeycloakAdminService` — `plan.md:162-164,178-181` — fits; httpx singleton + `enabled` gate pattern exists at `app/services/keycloak_admin_service.py:42-72`. Note the plan cites `container.py:178-181` for the singleton slot and `:219-235` for the device/model factory ctors — both verified accurate.
- `app/app_config.py` config addition — `plan.md:170-172` — fits the `AppEnvironment`→`AppSettings.load()` two-layer pattern (`app/app_config.py:34-79,139-198`). The plan must remember to thread the new field through *both* the `AppEnvironment` field list and the `cls(...)` call in `load()` (`app/app_config.py:167-198`); the plan says "env→settings pattern" but does not call out the `load()` constructor edit explicitly.
- Generated artifact coexisting with the committed `architecture.yaml` under the same `producer: iotsupport-app` — `plan.md:19-21,178-196` — fits: `arch-validate` validates each file independently (`scripts/arch-validate.py:40-56,123+`), and the archive glob `docs/architecture/*.yaml` picks up both; the collector merges by producer at merge-time. No standalone-validation collision. Confirmed the committed file owns `app:iotsupport-app,bbc500fd-…` (`docs/architecture/architecture.yaml:12`).

## 3) Open Questions & Ambiguities

- Question: When the trigger moves to a true post-commit hook, *which* mechanism is used — a Flask `after_request`/`teardown_request` hook keyed on a request-scoped "dirty" flag, or an explicit commit-then-trigger in a thin API-layer wrapper?
- Why it matters: The plan currently specifies a service-method call site (`plan.md:154-160`), which is structurally pre-commit in this app. The correct placement changes the file map and the test plan (the "trigger called once each" service tests at `plan.md:539-542` would assert at the wrong layer).
- Needed answer: A concrete post-commit hook design (e.g. set `g.architecture_dirty = True` in the service/API, fire the trigger in `teardown_request` only when `exc is None and not g.needs_rollback`, after `db_session.commit()` succeeds — `app/__init__.py:241-247`).

- Question: What is the exact, dataset-verified resolution algorithm for a concrete `svc:` whose realizer is itself an instance (no further specializers)?
- Why it matters: `svc:home-assistant-mqtt` is realized by `ss:home-assistant-prd` (a prd instance, no specializers) *and* `ss:home-assistant` (the logical product). The plan's single rule "the instance that `Specialization`s the product realizing the svc" (`plan.md:323`) yields zero candidates for the `ss:home-assistant-prd` realizer and one for `ss:home-assistant`, with no tiebreak specified. 6/8 firmware families depend on this edge.
- Needed answer: A resolution rule that, per svc, collects all `Realization→svc` sources, then for each either uses it directly if it is already a prd instance or descends to its prd specializer, then asserts exactly one prd instance survives.

- Question: Is the new `ARCHITECTURE_PIPELINE_TRIGGER_URL` env added to the deployment manifests / Helm values, and does the architecture Jenkins job actually bind prd API credentials (`IOTSUPPORT_*`)?
- Why it matters: `plan.md:124-126,304-305` assume the credentials and validator/dataset egress "already used by the architecture job" exist, but `Jenkinsfile.architecture` today has no `Generate` stage and binds no `IOTSUPPORT_*` credentials (`Jenkinsfile.architecture:1-22`). The first build will fail if those bindings are not added alongside the Generate stage.
- Needed answer: Confirmation that the Jenkins credential bindings and egress are provisioned (or a sub-task to add them) — otherwise the "assumption" is actually new work.

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: `GET /api/pipeline/fleet-projection` (service `get_fleet_projection` + API auth)
- Scenarios:
  - Given one active + one inactive device across two models, When projecting, Then both returned with `key/model_code/firmware_version/device_name/created_at` and no `active` filter (`tests/.../test_device_service.py::test_fleet_projection_includes_inactive`).
  - Given no/`pipeline`-less token, When GET, Then 401/403; given `pipeline` token, Then 200 schema-valid (`tests/.../test_pipeline_api.py`).
- Instrumentation: `record_operation("pipeline_fleet_projection", status, duration)` in a `finally` block (`plan.md:447-452`; helper `app/utils/iot_metrics.py:26-39`).
- Persistence hooks: read-only; no migration; seeds `DeviceModel`/`Device` via container factory (`plan.md:516`).
- Gaps: none material.
- Evidence: `plan.md:511-527`; list-query precedent `app/services/device_service.py:192-204`.

- Behavior: `ArchitecturePipelineTriggerService` (best-effort POST)
- Scenarios: URL unset → skipped/no POST; 204 → success/one POST; raise/timeout → swallowed/error+warning (`plan.md:530-533`).
- Instrumentation: `record_operation("architecture_pipeline_trigger", status)` incl. `skipped` (`plan.md:454-458`).
- Persistence hooks: none; Singleton DI slot (`plan.md:166-168`).
- Gaps: none.
- Evidence: `plan.md:529-536`; httpx/`enabled` precedent `app/services/keycloak_admin_service.py:42-72`.

- Behavior: CRUD-trigger wiring (Device + DeviceModel)
- Scenarios: create/update/delete device + create/update/delete model + upload_firmware each fire once; trigger raise → write still succeeds (`plan.md:539-542`).
- Instrumentation: covered by the trigger-service metric.
- Persistence hooks: spy trigger injected via container.
- **Gaps (Major):** the scenario "trigger raises → write not rolled back" (`plan.md:542`) tests the *wrong invariant* given this app's lifecycle. The dangerous case is the inverse — *write rolled back at teardown after the trigger already fired* — which the post-flush placement makes reachable and which no scenario covers. After fixing the hook to post-commit, add: "Given a write whose teardown commit fails/rolls back, When the request ends, Then the trigger does NOT fire." See Adversarial #1.
- Evidence: `plan.md:538-545`; commit lifecycle `app/__init__.py:241-247`.

- Behavior: `tools/gen-architecture.py` (generator)
- Scenarios: per-device edges; determinism (byte-identical); `introduced` = date(created_at) and grouping = min; unmapped code → non-zero exit; intercom dangle emitted+warned; cap:iam prd pick + host tiebreak; two-prd-realizer disagreement → fail loud (`plan.md:548-556`).
- Instrumentation: stderr warnings; CI non-zero exit.
- Persistence hooks: trimmed dataset fixture + sample projection JSON.
- **Gaps (Major):** no scenario covers a concrete `svc:` realized by an *instance with no specializer* (the `svc:home-assistant-mqtt` shape) — the most-used non-universal edge. Add a fixture mirroring `ss:home-assistant-prd` (prd instance) + `ss:home-assistant` (product) both realizing the svc, asserting the prd instance is selected. Also no scenario for the *third* unscoped `cap:iam` realizer `ss:keycloak` (env unset) — confirm the env=prd filter excludes it.
- Evidence: `plan.md:547-558`; dataset facts in Adversarial #2/#3.

## 5) Adversarial Sweep

**Blocker — Trigger fires before the transaction is durable (post-flush ≠ post-commit)**
**Evidence:** `plan.md:397-398` ("the trigger fires **after** the service's `db.flush()`") and `plan.md:404-405` (cites flush points `device_service.py:299,362,397`). But this app does not commit in services — commit happens in `teardown_request` after the handler returns: `app/__init__.py:244-247` "else: db_session.commit()", and rollback when `exc or g.needs_rollback` (`app/__init__.py:241-243`). All cited write paths only `flush()` (`app/services/device_service.py:299,362,397`; `device_model_service.py:137,170,201,232`).
**Why it matters:** Firing post-flush/pre-commit means (a) Jenkins regenerates the projection from a DB that has *not yet* committed the change (the GET runs in a *different* request/transaction and will not see uncommitted rows — the regeneration races the commit and may capture stale state), and (b) if the commit later rolls back (a constraint violation surfaced at commit, or an error handler sets `g.needs_rollback`), the trigger has *already* fired for a change that never persisted. This is the exact inversion of the project's Golden-Rule-2 ordering ("commit before the external side effect") and is a real correctness defect, not a nit. The plan's own §13 scenario tests the benign direction and misses this one (`plan.md:542`).
**Fix suggestion:** Re-specify the trigger as a **post-commit** hook: set a request-scoped flag (e.g. `g.architecture_dirty`) in the service/API on a successful device/model write, and fire the best-effort trigger in `teardown_request` only on the `else` (commit-succeeded) branch (`app/__init__.py:244-247`), after `commit()` returns. Update §2/§7/§13 accordingly (the "trigger called once" assertions move from the service unit to the request lifecycle).
**Confidence:** High.

**Major — Generic `svc:` provider resolution does not match the dataset's realizer shapes (breaks `svc:home-assistant-mqtt`)**
**Evidence:** `plan.md:323` specifies one mechanic: "→ the instance that `Specialization`s the product realizing the svc." Verified in `tmp/published-architecture.json`: `svc:home-assistant-mqtt` is realized by **two** sources — `ss:home-assistant-prd` (a self-producer prd instance, `environment: prd`, with **no** specializing instance) **and** `ss:home-assistant` (the logical product, which `ss:home-assistant-prd` specializes). By contrast `svc:calendar-support`/`svc:infra-statistics` are each realized by a single logical product with exactly one prd specializer, and `svc:iotsupport-api` is realized by the product `app:iotsupport-app` with **three** specializers needing a `stats.workload` discriminator. Three different shapes; the plan's single rule fits only the calendar/infra case.
**Why it matters:** `svc:home-assistant-mqtt` is consumed by 6 of 8 firmware families (doorbell, gesture, infra-stats *no*, paper-clock, somfy, underfloor, intercom — verified: all except calendar-display and infra-statistics-display), so it drives the `Serving` source for the majority of the fleet's non-universal edges. An algorithm that returns zero candidates (descend from `ss:home-assistant-prd` finds no specializer) or two candidates (both realizers) either fails the build or emits wrong/duplicate `Serving` edges.
**Fix suggestion:** Specify a uniform resolver: for a concrete `svc:`, gather all `Realization→svc` sources; for each source, if it already carries `environment: prd` (it *is* the prd instance) take it directly, else take its `environment: prd` specializer; then assert exactly one prd instance across all realizers (with the `stats.workload`/`container` discriminator reserved for the multi-instance `iotsupport-api` case). Add a generator test fixture for the instance-realizer shape.
**Confidence:** High.

**Major — Research log undercounts cap realizers; the "exactly one after env filter" assertion is only incidentally satisfied**
**Evidence:** `plan.md:41-46` claims `cap:iam` is realized by exactly two instances (prd + dev) and `cap:pub-sub-broker` by a single prd instance. Verified in the dataset: `cap:iam` has **three** realizers — `ss:keycloak-prd-keycloak-keycloak` (prd), `ss:keycloak-dev-keycloak-keycloak` (dev), and `ss:keycloak` (`environment: None`); `cap:pub-sub-broker` has **two** — `ss:mosquitto-mosquitto-mosquitto` (prd) and `ss:mosquitto` (env unset).
**Why it matters:** The plan's resolution + fail-loud guard is "assert exactly one after the env=prd filter" (`plan.md:380-382,439-441`). That assertion *happens* to pass today only because the extra logical realizers have `environment` unset (so the `== prd` filter drops them). The plan never accounts for these unscoped realizers, so the guard's robustness is unverified: if a future logical realizer were ever stamped `prd`, or if the filter were implemented as "not dev/tst/uat" instead of "== prd", the assertion would wrongly trip or wrongly pass. The dataset characterization the plan relies on for confidence (`plan.md:31-46`) is incomplete.
**Fix suggestion:** Update §0 to record all three iam / two pub-sub realizers and state explicitly that the filter is strict equality `environment == "prd"` (so env-unset logical realizers are excluded by design), and add the env-unset realizer to the generator test fixture so the guard is exercised against it.
**Confidence:** High.

**Minor — Jenkins `Generate` stage and `IOTSUPPORT_*` credential bindings are new work mislabeled as an existing assumption**
**Evidence:** `plan.md:124-126,304-305` treat the prd API credentials and dataset/validator egress as "already used by the architecture job"; but `Jenkinsfile.architecture:15-21` has only a single `Architecture` stage that validates+archives — no `Generate` stage, no `withCredentials`/`IOTSUPPORT_*` bindings.
**Why it matters:** The first generated build needs token URL + client id/secret bound; if treated as a pre-existing assumption it will silently 401 the projection fetch and fail the build. Low severity because the plan does list the Generate-stage edit (`plan.md:190-192,303-308`), but it should explicitly own the credential-binding edit too.
**Fix suggestion:** Add the `withCredentials` binding to the §2 file-map entry for `Jenkinsfile.architecture`.
**Confidence:** Medium.

## 6) Derived-Value & Persistence Invariants

- Derived value: per-element ids `device:…` / `ss:<fw>-<key>` (uuid5)
  - Source dataset: `uuid5(IOTSUPPORT_NS, "<prefix>:" + Device.key)` — `Device.key` immutable (`app/models/device.py:48-50`; untouched by `update_device`, `app/services/device_service.py:358-359`).
  - Write / cleanup triggered: emitted ids in `deployed-architecture.yaml`; not persisted in DB.
  - Guards: private namespace constant; no random/time in keys (`plan.md:356`).
  - Invariant: re-render is byte-identical; ids never collide with the 18 existing `device:` uuid4 ids (owned by producer `architecture`, verified) — collision across uuid5/uuid4 is not credible.
  - Evidence: `plan.md:351-357`; dataset `device:zigbee-slzb-06m,9665cdf2-…` (producer `architecture`).

- Derived value: `introduced` = date(`Device.created_at`); grouping = `min(created_at)`
  - Source dataset: projection-returned `created_at`; `created_at` is `server_default=func.now()`, no `onupdate` (`app/models/device.py:89-91`).
  - Write / cleanup triggered: `introduced` on every emitted `device:`/`ss:`/`grp:`.
  - Guards: use date portion only (drop time/tz) so a single render second cannot perturb output (`plan.md:364-366`).
  - Invariant: stable, non-render-time. **Verified sound** — `created_at` is DB-set once and never mutated.
  - Evidence: `plan.md:359-367`; `app/models/device.py:89-91`.

- Derived value: cap provider instance (iam, pub-sub-broker)
  - Source dataset: **filtered** `Realization→cap` set, `environment == prd` (relation-grounded); fleet-URL host tiebreak via naming-convention bridge (`svc:keycloak-prd-keycloak hosts auth.ginbov.nl`, `svc:mosquitto-mosquitto hosts mosquitto.home` — both verified; **no relation edge** links the host-bearing `svc:` to the realizing `ss:`, also verified).
  - Write / cleanup triggered: `Serving` edge **source** for every device of every firmware (fleet-wide).
  - Guards: assert exactly one after env filter + host tiebreak; fail loud on 0/>1 (`plan.md:380-382`).
  - Invariant: resolved provider must `Realize` the cap. **Caveat:** robustness depends on env-unset logical realizers (`ss:keycloak`, `ss:mosquitto`) being excluded by strict `== prd` — see Adversarial #3.
  - Evidence: `plan.md:376-383`; dataset realizer inspection.

- Derived value: full fleet membership (`devices` projection)
  - Source dataset: **unfiltered** `select(Device)` — explicitly NOT filtered on `active`.
  - Write / cleanup triggered: the entire emitted device-element/edge set.
  - Guards: must not reuse rotation/active filter (`plan.md:386-389`).
  - Invariant: one emitted device per `devices` row. **Verified sound** — `active` is rotation-only (`app/models/device.py:65-68`); existing list query at `:192-204` is a separate method, so reusing the unfiltered query is correct.
  - Evidence: `plan.md:385-390`.

> A **filtered** (env=prd) view drives **emitted cross-producer `Serving` edges** for the whole fleet (cap providers). The plan guards it with assert-exactly-one + host tiebreak, which is adequate *given strict `== prd`*; flagged Major only insofar as the env-unset realizers are not characterized (Adversarial #3), not as an unguarded filtered-drives-persistent write.

## 7) Risks & Mitigations (top 3)

- Risk: Trigger fired pre-commit causes Jenkins to regenerate from stale/uncommitted state or fire for a rolled-back write.
- Mitigation: Move the trigger to a post-commit lifecycle hook gated on the teardown commit-success branch; add a "rolled-back-write does not trigger" test.
- Evidence: `plan.md:397-398` vs `app/__init__.py:241-247`.

- Risk: `svc:home-assistant-mqtt` (and any instance-realizer svc) resolves to zero/duplicate `Serving` sources, corrupting 6/8 of the fleet's non-universal edges.
- Mitigation: Re-specify the per-svc resolver to handle direct-prd-instance realizers and assert exactly one prd instance; add a generator fixture for that shape.
- Evidence: `plan.md:323` vs dataset (`svc:home-assistant-mqtt` realized by `ss:home-assistant-prd` + `ss:home-assistant`).

- Risk: First generated CI build fails because the `Generate` stage lacks `IOTSUPPORT_*` credential bindings / dataset egress that the plan assumes pre-exist.
- Mitigation: Explicitly own the `withCredentials` binding edit in `Jenkinsfile.architecture` rather than listing it as an existing assumption.
- Evidence: `plan.md:124-126,304-305` vs `Jenkinsfile.architecture:15-21`.

## 8) Confidence

Confidence: High — every dataset and codebase claim was checked against `tmp/published-architecture.json` and `app/`; the design is sound and the two conditions (post-commit trigger placement, instance-aware svc resolution) are precise, verified, and small to fix.
