# Code Review — IoT Device Fleet Architecture (generated producer)

**Revision under review:** uncommitted working tree on `feature/iot-device-fleet-architecture`
(base commit `ae9a016`). Reviewed via `git diff` for modified tracked files plus the
untracked set (`app/services/architecture_pipeline_trigger_service.py`,
`tools/gen-architecture.py`, `docs/architecture/firmware-products.yaml`,
`tests/fixtures/*`, `tests/tools/test_gen_architecture.py`,
`tests/services/test_architecture_pipeline_trigger_service.py`,
`tests/services/test_architecture_trigger_wiring.py`).

## 1) Summary & Decision

**Readiness**
This is a high-quality implementation that closely follows the GO-WITH-CONDITIONS plan and
both conditions from `plan_review.md` are honored. The trigger now fires strictly
post-commit from `teardown_request`'s commit-success branch (`app/__init__.py:254-255`) via a
request-scoped `contextvars.ContextVar` flag, never on rollback, and never on the rotation
path; this is the inversion of the Blocker that plan review #1 raised, and it is correct.
The provider-resolution algorithm now implements all three realizer shapes (a/b/c) called out
in plan review #2, including the `svc:home-assistant-mqtt` direct-prd-instance case and the
`iotsupport-api` workload discriminator (`tools/gen-architecture.py:247-315`). The
unfiltered-fleet read is correct (`device_service.py:225-228`, no `active` filter), the uuid5
determinism / `introduced = date(created_at)` / fail-loud-on-unmapped-code invariants hold, and
the intercom skip+warn is correctly scoped to "concrete `svc:` with zero prd instances" while
the firmware `Specialization` target legitimately dangles-but-emits. Tests are thorough (44
new tests, all passing) and exercise the load-bearing fault lines, including a row-visibility
assertion proving commit-before-fire (`test_architecture_trigger_wiring.py:189-211`). The
config field is threaded through both `AppEnvironment` and `AppSettings.load()`. The known
deviation (generated elements omit `environment`; relations carry deterministic `rel:<uuid5>`
ids) is sound, internally consistent, and test-locked. No new ruff/mypy regressions were
introduced by this change.

**Decision**
`GO` — both plan-review conditions are satisfied, the adversarial sweep found no Blocker/Major,
and tests cover every new/changed behavior. The handful of findings below are Minor and can be
addressed in a follow-up without blocking merge. The one genuine pre-merge caveat (live
validator schema acceptance of the generated artifact) is a CI-time verification the plan
already defers to the first build, not a code defect.

## 2) Conformance to Plan (with evidence)

**Plan alignment**
- `plan.md §7 (post-commit firing)` ↔ `app/__init__.py:238-261` — `committed` flag set only on the
  `else: db_session.commit()` branch (`:245-247`); `fire_if_pending()` guarded by `if committed:`
  (`:254-255`); `clear_pending()` in `finally` (`:260-261`). Matches the condition precisely.
- `plan.md §7 (ContextVar, Flask-free services)` ↔ `architecture_pipeline_trigger_service.py:39-41,69-87`
  — module-level `ContextVar`, `mark_pending`/`is_pending`/`clear_pending`/`fire_if_pending`; no Flask
  import in either service.
- `plan.md §2 (mark_pending wiring)` ↔ `device_service.py:357-358,426-427,463-464`,
  `device_model_service.py:146-147,181-182,213-214,263-264` — all six admin CRUD paths + firmware
  upload mark pending; rotation path untouched.
- `plan.md §5 step 3 (cap resolution, drop SoftwareProduct, env==prd)` ↔
  `gen-architecture.py:163-204` — drops products (`:176`), strict `== "prd"` (`:177`), host tiebreak
  with assert-exactly-one (`:188-204`).
- `plan.md §5 step 4 (svc shapes a/b/c)` ↔ `gen-architecture.py:247-315` — shape (a) direct prd
  instance (`:267-270`), shape (b) descend to prd specializer with workload discriminator
  (`:271-279,298-315`), shape (c) returns None → caller skips + warns (`:287-289,407-411,456-458`).
- `plan.md §3 (identity fence stats: model+firmware only)` ↔ `gen-architecture.py:498-503` — only
  `model` + optional `firmware`; no rotation_state/secret/timestamps/config.
- `plan.md §6 (unfiltered fleet)` ↔ `device_service.py:223-228` — `select(Device)` with no `active`
  filter, eager-loads `device_model` to avoid N+1.
- `plan.md §1a / requirement "Model the new edge from IoT Support to Jenkins"` ↔
  `docs/architecture/architecture.yaml:119-126` — `app:iotsupport-app —Association→
  cap:continuous-integration`, `boundBy: env:ARCHITECTURE_PIPELINE_TRIGGER_URL`.
- `plan.md §1a / "Call the endpoint(s) from Jenkinsfile.architecture"` ↔ `Jenkinsfile.architecture:18-32`
  — new `Generate` stage with `withCredentials` binding `IOTSUPPORT_*` (the credential-binding work
  plan review #4 flagged as new is now explicitly owned).

**Gaps / deviations**
- `plan.md §3 (emitted element shape) lists `environment: prd`` on `device:`/`ss:` elements
  (`plan.md:275,282`), but the generator deliberately **omits** `environment`
  (`gen-architecture.py:432-447`, test-locked at `test_gen_architecture.py:259-267`). This is the
  documented validator-driven deviation; see §5 / Invariants. Sound and consistent.
- `plan.md §3 (relations)` sketched bare `{type, source, target}` relations; the implementation adds a
  deterministic `rel:<uuid5(type:source:target)>` id (`gen-architecture.py:327-340`). Required by the
  validator schema; deterministic and unique (test `:269-284`). Sound.
- No generated `deployed-architecture.yaml` is committed (correct — `.gitignore:16` ignores it). The
  Jenkins `Generate` stage produces it (`Jenkinsfile.architecture:18-32`).

## 3) Correctness — Findings (ranked)

- Title: `Minor — Jenkins Generate stage installs deps with unpinned pip and no lockfile`
- Evidence: `Jenkinsfile.architecture:28` — `sh 'pip install --quiet requests pyyaml'`.
- Impact: A future incompatible `requests`/`pyyaml` release could break the generated build
  non-deterministically, and the generator's determinism guarantee (byte-identical YAML) is at the
  mercy of whatever `pyyaml` `safe_dump` version CI resolves. Low likelihood, but it undercuts the
  "byte-identical re-runs" invariant across time.
- Fix: pin versions (`pip install requests==X pyyaml==Y`) or add them to the project's CI image /
  a small `tools/requirements.txt`.
- Confidence: Medium.

- Title: `Minor — created_at timezone normalization is fragile for non-UTC offsets`
- Evidence: `gen-architecture.py:343-347` — `_date_of` does `created_at.replace("Z","+00:00")` then
  `datetime.fromisoformat(...).date()`. The projection serializes `created_at` from a naive DB
  `DateTime` column (`app/models/device.py:89-91`, `server_default=func.now()`), and Pydantic's
  `model_dump(mode="json")` (`app/api/pipeline.py:144`) emits it without a `Z`/offset for a naive
  datetime.
- Impact: The `.replace("Z",...)` is a no-op for the naive-timestamp shape that actually flows
  through today, so `introduced` is taken from the naive wall-clock date — correct in practice. But
  the date is computed in whatever the stored value's implicit zone is; if a device were created near
  a midnight boundary the `introduced` date is the server-local date, not UTC. Not a determinism
  problem (the value is fixed once written), only a semantic edge. The fixture uses a trailing `Z`
  (`architecture_projection.json:12`) which `_date_of` handles, but the real API payload will not
  carry a `Z`. No failure, just a latent mismatch between the test fixture shape and the live shape.
- Fix: optionally assert/normalize the projection timestamp shape, or document that `introduced`
  follows the DB-stored zone. Non-blocking.
- Confidence: Medium.

- Title: `Minor — host tiebreak shared-prefix bridge is loose (single leading token)`
- Evidence: `gen-architecture.py:240-244` — `_shared_prefix_tokens` matches when the first
  hyphen-token of two stems is equal (`at[0] == bt[0]`).
- Impact: The tiebreak only runs when a cap has >1 prd instance realizer (today: zero such caps —
  each resolves uniquely at `:179-180` before tiebreak). If that path is ever exercised, a coarse
  first-token match (e.g. two `keycloak-*` services) could bridge to the wrong realizer. Guarded by
  the final assert-exactly-one (`_tiebreak_by_host` returns None unless exactly one candidate matches,
  `:235-237`), so a loose match that hits two candidates fails loud rather than mis-resolving — the
  failure mode is safe. Still, the heuristic is weaker than the plan's "shared release/hint stem"
  language implies.
- Fix: tighten to full-stem or release-field equality if/when a second prd realizer appears; covered
  defensively by the fail-loud assert today.
- Confidence: Low.

No Blocker or Major correctness findings. The two plan-review conditions (post-commit firing,
provider shapes a/b/c) are implemented and test-verified; see §6 and §7.

## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: `resolve_service_provider` re-resolution of provider per `svc:` is fine, but
  `_full_id` (`gen-architecture.py:519-526`) does a linear scan of `dataset.by_id` per call and is
  invoked once per device for the product id (`:399,424`).
- Evidence: `gen-architecture.py:519-526` (O(n) scan), called in the device loop `:419-454`.
- Suggested refactor: build a `uuid -> id` index once in `Dataset.__init__` (alongside `by_id`),
  then `_full_id` is O(1). Trivial.
- Payoff: minor; fleet ≤200 and dataset is small, so this is legibility/efficiency only, not
  correctness.

- Hotspot: the `architecture_pipeline_trigger_service()` provider is resolved twice in teardown
  (once for `fire_if_pending`, once for `clear_pending`) — `app/__init__.py:255,261`.
- Evidence: `app/__init__.py:255,261`.
- Suggested refactor: resolve the singleton once into a local at the top of the `try`. Negligible
  cost (it is a Singleton, so resolution is cheap), purely cosmetic.
- Payoff: marginal.

## 5) Style & Consistency

- Pattern: metrics + best-effort error handling mirror the established `record_operation` +
  log-and-swallow precedent.
- Evidence: `architecture_pipeline_trigger_service.py:108-128` (success/error/skipped statuses,
  host-only logging) matches `app/utils/iot_metrics.py:26-39` and the delete best-effort precedent.
- Impact: consistent with existing services; good.
- Recommendation: none.

- Pattern: API endpoint structure (decorator stack, `try/except/finally` with
  `record_operation`) matches the sibling `upload_firmware`/`get_firmware_version` handlers.
- Evidence: `app/api/pipeline.py:123-155` vs the existing handlers in the same module.
- Impact: thin API layer, delegates to service — conforms to CLAUDE.md layering.
- Recommendation: none.

- Pattern: secret-bearing URL is logged host-only.
- Evidence: `architecture_pipeline_trigger_service.py:62-65,107,116,123` always log
  `urlparse(url).hostname`, never the full URL (which may embed a webhook token).
- Impact: meets the plan's security requirement (§11).
- Recommendation: none.

## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: `DeviceService.get_fleet_projection` (service)
- Scenarios:
  - Given one active + one inactive device across two models, When projecting, Then both returned, no
    `active` filter (`tests/services/test_device_service.py::TestDeviceServiceFleetProjection::test_fleet_projection_includes_inactive`).
  - Given fleet config, Then `mqtt_url == device_mqtt_url`, `oidc_issuer_url == oidc_token_url`,
    `baseurl` absent (`::test_fleet_projection_fleet_config`).
  - Given a model without firmware, Then `firmware_version is None`, device still listed
    (`::test_fleet_projection_null_firmware`).
- Hooks: `container.device_service()`, Keycloak mocked via `_create_device`.
- Gaps: none material.
- Evidence: `tests/services/test_device_service.py:1301-1384`.

- Surface: `GET /api/pipeline/fleet-projection` (API auth/role)
- Scenarios: 401 no token, 403 wrong role, 200 `pipeline` role, 200 empty fleet, 200 schema-valid body
  (`tests/api/test_pipeline.py::TestPipelineFleetProjection`).
- Hooks: `oidc_client`, `generate_test_jwt`.
- Gaps: none.
- Evidence: `tests/api/test_pipeline.py:268-345`.

- Surface: `ArchitecturePipelineTriggerService`
- Scenarios: disabled/enabled gating, not-pending no-op, pending+no-URL skipped, pending+enabled one
  empty-body POST, HTTP error swallowed, `clear_pending` resets, `fire_if_pending` leaves flag for
  teardown (`tests/services/test_architecture_pipeline_trigger_service.py`).
- Hooks: `_reset_pending` autouse fixture, monkeypatched `_http_client.post`.
- Gaps: none.
- Evidence: `tests/services/test_architecture_pipeline_trigger_service.py:27-95`.

- Surface: CRUD `mark_pending` wiring + post-commit firing
- Scenarios: each of create/update/delete device, create/update/delete model, upload_firmware marks
  pending once; rotation does NOT mark; commit fires once after a durable write (with a fresh-session
  row-visibility assertion proving commit-before-fire); rollback does not fire; bulk write coalesces to
  one fire and the flag resets for the next request
  (`tests/services/test_architecture_trigger_wiring.py`).
- Hooks: spy on `mark_pending`, `enabled=True` patch, `fake_post` opening a fresh
  `session_maker()` session.
- **Gaps (Minor):** no test asserts the behavior when `db_session.commit()` *itself* raises (deferred
  constraint surfacing at commit). Stepwise: in `teardown_request`, a raising `commit()` leaves
  `committed = False`, the exception propagates past the `if committed:` guard, the `finally` runs
  `clear_pending()`, and `fire_if_pending` is never reached — so a commit-time failure correctly does
  NOT fire. This is the safe direction and is structurally guaranteed by the `committed` flag, but an
  explicit test would lock it. Non-blocking.
- Evidence: `tests/services/test_architecture_trigger_wiring.py:35-253`; teardown
  `app/__init__.py:238-261`.

- Surface: `tools/gen-architecture.py`
- Scenarios: per-device elements/edges (Assignment/Specialization/4×Serving/Aggregation); intercom
  Serving skipped+warned with other 4 edges intact; `introduced` date + grouping min; null firmware
  omits stat; no per-element `producer`; no `environment` field; valid+unique `rel:<uuid>` ids;
  byte-identical determinism; uuid5 namespacing; unmapped code → `GeneratorError`; cap iam/pub-sub prd
  pick; shape-a home-assistant; shape-b calendar; iotsupport-api workload discriminator; shape-c
  intercom None; synthetic two-prd-realizer disagreeing host → fail loud
  (`tests/tools/test_gen_architecture.py`).
- Hooks: trimmed dataset fixture + sample projection JSON; `importlib` loads the hyphenated module.
- Gaps: end-to-end live-validator acceptance of the emitted YAML is deferred to first CI build (plan
  §13). This is the one genuine pre-merge verification item; it is a CI concern, not a code defect.
- Evidence: `tests/tools/test_gen_architecture.py:60-320`; fixtures
  `tests/fixtures/architecture_dataset.json`, `architecture_projection.json`.

All 44 new tests pass (`poetry run pytest` on the five new/changed test modules). No new ruff or
mypy errors are introduced (pre-existing baseline: 3 ruff errors and 98 mypy errors in unrelated
files; the feature files are clean).

## 7) Adversarial Sweep

- Checks attempted:
  1. **Trigger fires on rollback or pre-commit (the original Blocker).** Traced
     `teardown_request` (`app/__init__.py:238-261`): `fire_if_pending()` is reachable only inside
     `if committed:`, and `committed` is set `True` only on the `else` (commit) branch. A handled
     error sets `g.needs_rollback` → rollback branch → `committed` stays False → no fire. An unhandled
     `exc` → same. A `commit()` that itself raises → exception escapes before `if committed:` → no
     fire, `finally` clears the flag. **Held.** Verified by
     `test_rollback_does_not_fire` and the commit-visibility test.
  2. **Trigger over-fires on rotation.** The rotation service mutates runtime state and commits, but
     never calls `mark_pending()` (grep-confirmed; `test_rotation_does_not_mark_pending`
     `test_architecture_trigger_wiring.py:144-165`). The pending flag stays False → no fire. **Held.**
  3. **Projection accidentally reuses the `active` filter.** `get_fleet_projection`
     (`device_service.py:223-228`) issues a fresh `select(Device)` with no `where(active...)`; the
     inactive-device test asserts membership. **Held.**
  4. **ContextVar leakage across requests on a pooled WSGI thread.** `mark_pending` and
     `fire_if_pending`/`clear_pending` all run in the same request thread (service call → teardown of
     that request). `clear_pending()` runs unconditionally in the teardown `finally`
     (`app/__init__.py:260-261`), resetting the flag before the thread serves another request. The
     bulk-then-GET test (`test_bulk_writes_fire_once_and_reset`) confirms a later request on the same
     client does not re-fire. **Held.**
  5. **DI wiring: trigger service unregistered or not injected.** Singleton registered
     (`container.py:189-191`), injected into both `device_service` (`:247`) and `device_model_service`
     (`:236`) factories, and resolvable from the container in teardown (`app/__init__.py:255,261`).
     **Held** (all wiring tests instantiate via the container).
  6. **Generator emits a sourceless/invented Serving edge for intercom.** Shape (c) returns `None`
     (`gen-architecture.py:287-289`); the caller `continue`s without emitting
     (`:456-458`) and warns once at discovery (`:407-411`). Distinguished from the firmware
     `Specialization` target, which always emits to the known product UUID. **Held**
     (`test_intercom_serving_edge_skipped_with_warning`).
  7. **Provider resolution returns 0 or >1 for the common `svc:home-assistant-mqtt`.** Shape (a)
     takes the single prd non-product realizer directly; de-dup + assert-exactly-one
     (`:281-295`) fails loud on >1. **Held** (`test_svc_home_assistant_mqtt_shape_a`).
  8. **Unmapped model code silently skipped.** `firmware_products.get(code)` raises `GeneratorError`
     naming the code before any element is emitted (`:393-398`); no partial artifact written (the YAML
     is only written after `generate_artifact` returns, `:627,636`). **Held**
     (`test_unmapped_model_code_fails`).
  9. **Determinism: time/random in keys.** All ids are `uuid5` over immutable natural keys
     (`Device.key`, firmware code, and `type:source:target` for relations);
     `yaml.safe_dump(sort_keys=False)` over deterministically-ordered lists (`sorted(devices...)`,
     `sorted(groupings)`, `sorted(svc_targets)`). `introduced` uses the immutable
     date-of-`created_at`. **Held** (`test_determinism_byte_identical`).
  10. **Migrations / schema drift.** No DB schema change in this feature (projection is read-only;
      `device_name`/`created_at`/`active` columns already exist). No Alembic revision required;
      none added — correct.

- Why code held up: the post-commit hook, explicit-mark-at-CRUD-boundary, fail-loud provider
  resolution, and uuid5 determinism each have a direct test, and the dangerous inverse cases
  (rollback, rotation, commit-failure, sourceless edge, ambiguous provider) are either tested or
  structurally precluded by the `committed` flag and assert-exactly-one guards.

## 8) Invariants Checklist

- Invariant: The trigger fires at most once per committed request that touched the fleet, only
  after the write is durable, never on rollback.
  - Where enforced: `app/__init__.py:245-255` (commit→`committed=True`→guarded `fire_if_pending`);
    `architecture_pipeline_trigger_service.py:89-98` (no-op unless `_pending`).
  - Failure mode: firing pre-commit/on-rollback would regenerate the model from stale/aborted state.
  - Protection: `committed` flag gate; `clear_pending` in `finally`.
  - Evidence: `test_architecture_trigger_wiring.py:171-229`.

- Invariant: Fleet membership is the UNFILTERED device set (`active` is rotation-only).
  - Where enforced: `device_service.py:223-228` (no `active` predicate).
  - Failure mode: dropping inactive devices would silently omit real fleet members from the model.
  - Protection: `test_fleet_projection_includes_inactive` flips a device inactive and asserts it
    still projects.
  - Evidence: `tests/services/test_device_service.py:1322-1346`.

- Invariant: Every emitted element id is a stable uuid5 from the private IoT Support namespace,
  byte-identical across re-runs, never colliding with other producers' `device:` ids.
  - Where enforced: `gen-architecture.py:46,322-324,327-340` (namespace constant; uuid5 over natural
    keys including relation `type:source:target`).
  - Failure mode: random/time-based ids would churn the graph or collide with the 18 existing
    `device:` (uuid4) elements.
  - Protection: `test_determinism_byte_identical`, `test_uuid5_ids_stable_and_namespaced`,
    `test_relations_have_valid_ids` (uniqueness).
  - Evidence: `tests/tools/test_gen_architecture.py:269-309`.

- Invariant: A device whose `model_code` is unmapped fails the build (no silent skip, no partial
  artifact).
  - Where enforced: `gen-architecture.py:393-398` (raise before emission); write only after success
    (`:627,636`).
  - Failure mode: a silently-skipped device would under-report the fleet.
  - Protection: `test_unmapped_model_code_fails`.
  - Evidence: `tests/tools/test_gen_architecture.py:311-319`.

- Invariant: A concrete `svc:` with no deployed prd instance (intercom) skips only its own Serving
  edge and warns — it never emits a sourceless or product-targeted Serving edge; the firmware
  `Specialization` target is exempt (it legitimately targets a known product UUID).
  - Where enforced: `gen-architecture.py:454-459` (skip on `None` provider) vs `:451` (Specialization
    always emitted to the product full id).
  - Failure mode: emitting a Serving edge with a product or invented source corrupts the realization
    semantics.
  - Protection: `test_intercom_serving_edge_skipped_with_warning` asserts the other 4 edges survive.
  - Evidence: `tests/tools/test_gen_architecture.py:179-206`.

- Invariant (deviation, validated): generated elements carry no `environment`; relations carry a
  deterministic `rel:<uuid5>` id.
  - Where enforced: `gen-architecture.py:432-447` (no `environment`), `:327-340` (`rel:<uuid5>`).
  - Failure mode: the live validator schema rejects `environment` on these element kinds
    (`additionalProperties: false`) and requires a `rel:` id pattern on relations.
  - Protection: `test_elements_have_no_environment_field`, `test_relations_have_valid_ids`; the
    remote validator is the ultimate check (deferred to first CI build).
  - Evidence: `tests/tools/test_gen_architecture.py:259-284`; deviation rationale matches the existing
    hand-authored relations which already carry `rel:` ids (`docs/architecture/architecture.yaml`).

## 9) Questions / Needs-Info

- Question: Has the emitted `deployed-architecture.yaml` been run through the live
  `architecture.webathome.org/api/validate` schema at least once (the deviation that drops
  `environment` and adds `rel:<uuid5>` ids is asserted in unit tests but the schema is remote)?
- Why it matters: The whole deviation rationale rests on the validator's `additionalProperties:false`
  / required-`rel:`-id behavior. If a generated element kind requires a field the generator omits, the
  first CI build fails at the `Architecture` validate stage.
- Desired answer: confirmation of a successful manual validate run against the real endpoint (or
  acceptance that the first CI build is the verification gate, as plan §13 already states).

- Question: Are the four `iotsupport-*` Jenkins credentials (`iotsupport-api-url`,
  `iotsupport-token-url`, `iotsupport-pipeline-client-id`, `iotsupport-pipeline-client-secret`)
  provisioned in the Jenkins instance, and is `ARCHITECTURE_PIPELINE_TRIGGER_URL` set in the prd
  deployment manifest/Helm values?
- Why it matters: `Jenkinsfile.architecture:22-27` binds them by id; missing creds 401 the projection
  fetch and fail the build. The trigger is a no-op until the env var is set in prd.
- Desired answer: confirmation that the credential ids exist and the env var is wired into the
  deployment (out-of-repo per the sandbox note).

## 10) Risks & Mitigations (top 3)

- Risk: First generated CI build fails on live-validator schema rejection of an emitted element shape.
- Mitigation: run one manual `arch-validate` against a generated artifact before relying on SCM
  builds; the unit tests already lock the known deviations.
- Evidence: §9 Q1; `gen-architecture.py:432-447,327-340`.

- Risk: Unpinned `pip install requests pyyaml` in CI drifts and breaks determinism or imports.
- Mitigation: pin versions or bake into the CI image.
- Evidence: §3 finding 1; `Jenkinsfile.architecture:28`.

- Risk: A future second prd realizer for a capability exercises the loose first-token host bridge.
- Mitigation: the assert-exactly-one guard fails loud (safe) rather than mis-resolving; tighten the
  stem match when that case becomes real.
- Evidence: §3 finding 3; `gen-architecture.py:235-244`.

## 11) Confidence

Confidence: High — both GO-WITH-CONDITIONS conditions are implemented and test-verified, the
adversarial sweep found no Blocker/Major, all 44 new tests pass, no new lint/type regressions, and
the only genuine pre-merge item (live validator acceptance) is a documented CI-time gate, not a code
defect.
