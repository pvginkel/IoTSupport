# Plan — IoT Device Fleet Architecture (generated producer)

## 0) Research Log & Findings

This plan turns IoT Support into a **second, generated** architecture-producer
artifact under the existing producer id `iotsupport-app`. The existing committed
`docs/architecture/architecture.yaml` (`docs/architecture/architecture.yaml:1-2`)
is the hand-authored logical artifact; the new generated artifact realizes the
physical ESP32 fleet from the production database into the federated model.

Areas researched and findings:

- **Producer envelope & generated-producer pattern.** A generated producer fuses
  mechanically-derived structure with a thin committed annotation layer, emits the
  YAML in CI, and does **not** commit it (producer-manual.md:469-509, 636-643). IDs
  must be `uuid5` from a documented natural key under a fixed per-system namespace,
  byte-identical across re-runs (producer-manual.md:159-166, 490-497). The collector
  stamps `producer:` from the envelope; elements must not carry `producer:`
  (producer-manual.md:200-203). Both YAML files share `producer: iotsupport-app`
  and are archived by the existing `docs/architecture/*.yaml` glob
  (`Jenkinsfile.architecture:17-19`).

- **The realization rule.** For each registered device, every logical edge on its
  firmware «SoftwareProduct» is realized unconditionally as
  `provider-instance —Serving→ firmware-instance`
  (`tmp/iotsupport-iot-architecture-guidance.md:89-114`). "Registered device" = every
  row in the `devices` table; `Device.active` governs rotation only and must **not**
  filter the fleet (`tmp/iotsupport-iot-architecture-guidance.md:94-99`,
  `app/models/device.py:65-68`).

- **Dataset verification (from `tmp/published-architecture.json`).** Confirmed via
  scripted inspection:
  - `cap:continuous-integration` is in the capability enum (so the Jenkins edge in
    decision 7 is valid).
  - Firmware products and their logical `Association` edges are present for all eight
    models (`ss:calendar-display`, `ss:doorbell-receiver`, `ss:gesture-device`,
    `ss:infra-statistics-display`, `ss:intercom`, `ss:paper-clock`, `ss:somfy-remote`,
    `ss:underfloor-heating-controller`); the universal set is `svc:iotsupport-api`,
    `cap:pub-sub-broker`, `cap:iam`.
  - `cap:iam` has **three** realizers: `ss:keycloak-prd-keycloak-keycloak`
    (`environment: prd`), `ss:keycloak-dev-keycloak-keycloak` (`environment: dev`), and the
    env-unset **product** `ss:keycloak` (`stereotype: SoftwareProduct`). The candidate rule
    "instances (drop SoftwareProduct) ∧ env==prd" lands the prd instance uniquely. Host
    tiebreaker: `svc:keycloak-prd-keycloak` carries `stats.hosts: auth.ginbov.nl`.
  - `cap:pub-sub-broker` has **two** realizers: the prd instance
    `ss:mosquitto-mosquitto-mosquitto` and the env-unset product `ss:mosquitto`. Same rule
    → the prd instance; host tiebreaker `svc:mosquitto-mosquitto` carries
    `stats.hosts: mosquitto.home`. (The `== prd` filter alone happens to survive the product
    realizers because they are env-unset — but the rule explicitly drops SoftwareProduct so it
    stays correct if a product ever gains an env.)
  - `svc:iotsupport-api` (`b7c5b5ba-…`) has **three** instances specializing
    `app:iotsupport-app`: the main workload `app:iot-iotsupport-iotsupport-app`
    (`stats.workload: iotsupport`, `container: iotsupport-app`), plus
    `…-rotation-cronjob-…` and `…-setup-…` (both `container: iotsupport-setup`). The
    generator must select the main workload and exclude the cronjob/setup jobs — the
    discriminator is `stats.workload == "iotsupport"` / `container == "iotsupport-app"`,
    not environment (all three are prd).
  - Concrete `svc:` realizer shapes differ — the generator must branch (see §5 step 4):
    `svc:home-assistant-mqtt` (`23572189-…`) is realized **directly by the prd instance**
    `ss:home-assistant-prd` *and* by the product `ss:home-assistant` (shape (a); take the prd
    instance — this svc backs 6 of 8 firmware families). `svc:calendar-support` (`e469b02a-…`)
    and `svc:infra-statistics` (`e6a1608a-…`) are product-realized, resolved via the prd instance
    that `Specialization`s the product (`app:calendar-support-…-app`, `app:infra-statistics-…-app`)
    (shape (b)).
  - `svc:intercom` (`5914e568-…`) is realized only by the product `app:intercom-server`, which has
    **no** deployed instance (shape (c)) → its `Serving` edge is **skipped + warned** (cannot source
    a sourceless edge; see §8). **Confirmed expected** (intercom is down); resolves once
    intercom-server deploys and IoT Support re-generates.
  - The dataset already contains **18 `device:` elements** owned by other producers
    (zigbee, ecowitt, pve, …). This makes the ID-collision concern real: the IoT Support
    uuid5 namespace must be its own private constant so device ids never collide with
    those, nor with this repo's hand-authored artifact.

- **Conflict resolved — cap-realizer selection.** The guidance frames host→provider
  matching as the resolution mechanic (`…guidance.md:118-129`), but the host-bearing
  `svc:`/`if:` is linked to the realizing `ss:` instance **only by naming convention**
  (shared `release`/`hosts` stem), not by a relation edge (verified: no edge connects
  `svc:keycloak-prd-keycloak` to `ss:keycloak-prd-keycloak-keycloak`). Resolution
  therefore uses **env=prd-filtered `Realization`→cap** as the relation-grounded primary
  key, and the fleet-URL host as a tiebreaker/verifier for the >1-prd-realizer case.

- **Codebase anchors.** Pipeline blueprint + `pipeline` role pattern
  (`app/api/pipeline.py:25,37,96`); role configured in DI
  (`app/services/container.py:98-103`); auth via `@allow_roles`/`@public`
  (`app/utils/auth.py:93-112,62-72`); Jenkins client-credentials flow
  (`app/templates/upload_firmware.sh.j2:99-117,157-161`); fleet config fields
  `device_mqtt_url`/`oidc_token_url`/`device_baseurl` (`app/app_config.py:99-116,149`);
  httpx singleton pattern (`app/services/keycloak_admin_service.py:42-58`); metrics
  helper `record_operation` (`app/utils/iot_metrics.py:26-39`); device/model CRUD
  surfaces (`app/services/device_service.py:246,328,378`,
  `app/services/device_model_service.py:104,142,175,205`).

## 1) Intent & Scope

**User intent**

Make IoT Support emit a second, **generated** architecture artifact that projects the
physical ESP32 device fleet (from the production DB) into the federated
Architecture-as-Code model: one element set per registered device, the realized
dependency edges, and the firmware→product binding. The backend exposes only a thin raw
projection API; all model resolution lives in a repo-side generator run in CI. Device and
device-model writes trigger the architecture Jenkins job, and the IoT-Support→Jenkins
dependency is modeled in the hand-authored artifact.

**Prompt quotes**

"Realize the logical (firmware) elements based on data in the production database."
"Expose API(s) accessible by the `iotsupport-pipeline` client to drive this."
"Generate a `deployed-architecture.yaml` file exposed as a Jenkins artifact."
"Call that trigger after changes are made to device configuration (add/edit/remove devices)."
"device_model changes also trigger the pipeline." "Model the new edge from IoT Support to Jenkins."

**In scope**

- New thin raw-projection endpoint under `pipeline_bp`, guarded by `@allow_roles("pipeline")`.
- New repo-side generator `tools/gen-architecture.py` emitting `docs/architecture/deployed-architecture.yaml`.
- Committed annotation file `docs/architecture/firmware-products.yaml` (code→firmware-product UUID).
- New `ARCHITECTURE_PIPELINE_TRIGGER_URL` config + best-effort trigger service.
- Trigger wiring into all device + device-model CRUD (incl. firmware upload).
- Hand-authored `app:iotsupport-app —Association→ cap:continuous-integration` edge.
- `Jenkinsfile.architecture` Generate stage; `.gitignore` for the generated YAML.

**Out of scope**

- Conditional/`field:`-bound edges driven by `Device.config` (deliberately deferred —
  `tmp/iotsupport-iot-architecture-guidance.md:141-154`).
- The v0.2 «Artifact» element that would replace the code→product side-channel.
- Any backend dependency on architecture.webathome.org or on the federated model.
- Backfilling/repairing other producers' dangling refs (e.g. intercom).

**Assumptions / constraints**

- The `pipeline` role and `iotsupport-pipeline` client already exist
  (`app/services/container.py:102`); the validator/dataset HTTPS egress already used by the
  architecture job is in place. **New work (not assumed):** the `Generate` stage in
  `Jenkinsfile.architecture` does not exist today (`Jenkinsfile.architecture:15-21` only
  validates+archives), and binding the `IOTSUPPORT_API_URL` / `IOTSUPPORT_CLIENT_ID` /
  `IOTSUPPORT_CLIENT_SECRET` / `IOTSUPPORT_TOKEN_URL` credentials into that job is new pipeline
  configuration the implementer must add (the firmware-upload flow proves the creds exist and the
  pattern works, but they are not bound into the architecture job yet).
- `Device.key` (8-char, immutable) is the stable natural key; `DeviceModel.code` is
  immutable and equals the CMake `project()` name (`app/services/device_model_service.py:28,150`).
- The published dataset is the only source of UUIDs/edges; the generator never hand-copies them.

## 1a) User Requirements Checklist

**User Requirements Checklist**
- [ ] Realize the logical (firmware) elements based on data in the production database.
- [ ] Ensure the correct edges are added.
- [ ] Expose API(s) accessible by the `iotsupport-pipeline` client to drive this.
- [ ] Call the endpoint(s) from the `Jenkinsfile.architecture` script.
- [ ] Generate a `deployed-architecture.yaml` file exposed as a Jenkins artifact (and thus included in the federated architecture).
- [ ] Add a new environment variable holding a URL that triggers the Jenkins job running `Jenkinsfile.architecture`.
- [ ] Call that trigger after changes are made to device configuration (add/edit/remove devices).
- [ ] device_model changes also trigger the pipeline.
- [ ] Model the new edge from IoT Support to Jenkins.

## 2) Affected Areas & File Map

- Area: `app/api/pipeline.py` — new `GET /pipeline/fleet-projection` endpoint
- Why: Exposes the raw fleet projection (devices + fleet config) to the `pipeline` client.
- Evidence: `app/api/pipeline.py:28-37,95-97` (existing `@allow_roles("pipeline")` + `@inject` pattern to mirror).

- Area: `app/schemas/pipeline.py` — new `FleetProjectionResponseSchema`, `FleetProjectionDeviceSchema`, `FleetConfigSchema`
- Why: Pydantic response shapes for the projection endpoint.
- Evidence: `app/schemas/pipeline.py` (home of `FirmwareVersionResponseSchema`, imported at `app/api/pipeline.py:15`).

- Area: `app/services/device_service.py` — new `get_fleet_projection()`; `trigger_service.mark_pending()` in `create_device`/`update_device`/`delete_device`
- Why: Read full fleet (no `active` filter); mark the request fleet-dirty on admin writes (NOT fire — firing is post-commit, see §7).
- Evidence: `app/services/device_service.py:246-309,328-376,378-410`; full-list query at `:192-204`.

- Area: `app/services/device_model_service.py` — `trigger_service.mark_pending()` in `create_device_model`/`update_device_model`/`delete_device_model`/`upload_firmware`
- Why: Model + firmware changes also mark the request fleet-dirty.
- Evidence: `app/services/device_model_service.py:104-140,142-173,175-203,205-251`.

- Area: `app/services/architecture_pipeline_trigger_service.py` (new) — `ArchitecturePipelineTriggerService`
- Why: Holds a `contextvars.ContextVar` pending flag; `mark_pending()` sets it, `fire_if_pending()` does the best-effort empty-body POST and clears it. Keeps services Flask-free.
- Evidence: httpx singleton pattern to mirror `app/services/keycloak_admin_service.py:42-58`.

- Area: `app/__init__.py` — fire the trigger post-commit in `teardown_request`
- Why: Call `trigger_service.fire_if_pending()` only on the commit-success branch (never on rollback), so the trigger reflects a durable write (Blocker fix; §7).
- Evidence: `app/__init__.py:238-251` (teardown commit/rollback branches + `finally` reset).

- Area: `app/services/container.py` — register the trigger service; inject into Device/DeviceModel services; expose to teardown
- Why: DI wiring for the new dependency (and teardown reads it from the container like `db_session`).
- Evidence: `app/services/container.py:178-181` (singleton), `:219-235` (device/model factory ctors to extend).

- Area: `app/app_config.py` — add `ARCHITECTURE_PIPELINE_TRIGGER_URL` env + `architecture_pipeline_trigger_url` setting
- Why: New trigger URL config following the existing env→settings pattern.
- Evidence: `app/app_config.py:34-79` (env), `:82-198` (settings + `load()`).

- Area: `app/utils/iot_metrics.py` (reuse) — record trigger + projection operations
- Why: Observability via the existing helper; no new module needed.
- Evidence: `app/utils/iot_metrics.py:26-39`.

- Area: `docs/architecture/architecture.yaml` (hand-authored, committed) — add Jenkins consumption edge
- Why: Model `app:iotsupport-app —Association→ cap:continuous-integration`, `boundBy: env:ARCHITECTURE_PIPELINE_TRIGGER_URL`.
- Evidence: `docs/architecture/architecture.yaml:69-101` (style of existing `rel:iotsupport-consumes-*`).

- Area: `docs/architecture/firmware-products.yaml` (new, committed annotation) — code→firmware-product UUID map
- Why: Resolves `DeviceModel.code` → firmware «SoftwareProduct» UUID; fail-loud on miss.
- Evidence: `tmp/iotsupport-iot-architecture-guidance.md:206-213`; products confirmed in `tmp/published-architecture.json`.

- Area: `tools/gen-architecture.py` (new) — the generator
- Why: Fetch dataset + projection, resolve providers, emit `deployed-architecture.yaml`.
- Evidence: generated-producer pattern producer-manual.md:469-509,636-643.

- Area: `Jenkinsfile.architecture` — add Generate stage before validate
- Why: Run the generator, then validate + archive all `docs/architecture/*.yaml`.
- Evidence: `Jenkinsfile.architecture:15-21`; manual generate/validate/archive producer-manual.md:636-643.

- Area: `.gitignore` — ignore `docs/architecture/deployed-architecture.yaml`
- Why: Generated artifact is non-committed.
- Evidence: `.gitignore` (no architecture entry today); manual "you don't commit" producer-manual.md:477-479.

- Area: `tests/` — service tests (projection, trigger, CRUD-trigger wiring), API test (auth/role), generator unit tests
- Why: Definition of Done (CLAUDE.md testing requirements).
- Evidence: existing pipeline/device tests under `tests/` mirroring `app/` structure.

## 3) Data Model / Contracts

- Entity / contract: `GET /api/pipeline/fleet-projection` response
- Shape:
  ```json
  {
    "devices": [
      {"key": "ab12cd34", "model_code": "calendar_display",
       "firmware_version": "1.4.2", "device_name": "Hallway clock",
       "created_at": "2026-03-14T09:21:07Z"}
    ],
    "fleet": {"mqtt_url": "mqtt://mosquitto.home:1883",
              "oidc_issuer_url": "https://auth.ginbov.nl/realms/iot/..."}
  }
  ```
- Refactor strategy: New read-only endpoint; no back-compat concerns (BFF; no other consumer).
  `oidc_issuer_url` is sourced from `oidc_token_url` (`app/app_config.py:106,178`); `mqtt_url`
  from `device_mqtt_url` falling back to `MQTT_URL` (`app/app_config.py:149`). `device_name`
  is optional (nullable column `app/models/device.py:61`). `created_at` is the immutable row
  creation timestamp (`app/models/device.py:89-91`); its **date** becomes each generated
  element's `introduced` (see below) — a stable, meaningful, non-render-time source.
  `baseurl` is **not** exposed.
- Evidence: `app/schemas/pipeline.py` (existing schema home); `app/models/device.py:48-61`.

- Entity / contract: `docs/architecture/firmware-products.yaml` (committed annotation)
- Shape:
  ```yaml
  # DeviceModel.code -> firmware «SoftwareProduct» UUID (resolve UUIDs from the dataset)
  products:
    calendar_display:            <uuid-of-ss:calendar-display>
    doorbell_receiver:           <uuid-of-ss:doorbell-receiver>
    gesture_device:              <uuid-of-ss:gesture-device>
    infra_statistics_display:    <uuid-of-ss:infra-statistics-display>
    intercom:                    <uuid-of-ss:intercom>
    paper_clock:                 <uuid-of-ss:paper-clock>
    somfy_remote:                <uuid-of-ss:somfy-remote>
    underfloor_heating_controller: <uuid-of-ss:underfloor-heating-controller>
  # future home for cap -> provider UUID tiebreaker overrides
  ```
- Refactor strategy: Side-channel for the v0.1 missing-Artifact gap; explicit `code`→UUID map
  (snake_case `code` vs kebab `ss:` hint must be stated, not coincidental — `…guidance.md:206-213`).
  A device whose `model_code` is absent **fails** the generator (no silent skip).
- Evidence: `tmp/iotsupport-iot-architecture-guidance.md:206-213`; products in `tmp/published-architecture.json`.

- Entity / contract: Emitted `deployed-architecture.yaml` element shapes (per registered device)
- Shape:
  ```yaml
  schemaVersion: "0.1"
  producer: iotsupport-app
  devices:
    - id: device:<label-hint>,<uuid5(ns, "device:"+key)>
      label: <device_name or key>
      summary: ...
      introduced: <date(Device.created_at)>   # immutable DB timestamp, date portion
      lifecycle: active
      environment: prd
      stats: {model: <code>, firmware: <firmware_version>}
  systemSoftware:
    - id: ss:<firmware>-<key>,<uuid5(ns, "ss:"+key)>
      label: <firmware> @ <key>
      summary: ...
      introduced: <date(Device.created_at)>   # same source as the device it runs on
      lifecycle: active
      environment: prd
  groupings:
    - id: grp:<firmware>,<uuid5(ns, "grp:"+code)>   # one per firmware/model (legibility)
  relations:
    - {type: Specialization, source: ss:<firmware>-<key>, target: ss:<firmware>,<product-uuid>}
    - {type: Assignment,     source: device:…,            target: ss:<firmware>-<key>}
    - {type: Serving,        source: <provider-instance>, target: ss:<firmware>-<key>}  # per realized edge
    - {type: Aggregation,    source: grp:<firmware>,      target: ss:<firmware>-<key>}
  ```
- Refactor strategy: Instance form per guidance §4 (`…guidance.md:170-190`). Identity fence:
  `stats` carries only `model`/`firmware`; exclude rotation_state, cached_secret, timestamps,
  coredumps, raw config (`…guidance.md:172-176`, producer-manual.md:482-488). No `producer:` on
  elements (producer-manual.md:200-203). IDs uuid5 from the IoT Support namespace constant.
  **`introduced` sourcing:** the `device:` and its `ss:<firmware>-<key>` instance both take the
  **date portion of `Device.created_at`** (returned by the projection). The per-firmware
  `grp:<firmware>` Grouping takes `min(created_at)` across its member devices — deterministic
  from the projection, no extra field needed. `created_at` is set once by the DB server default
  and never mutated (`app/models/device.py:89-91`), so `introduced` is stable across re-renders
  without a hand-picked constant. (A device with no member yet cannot exist; an empty model
  emits no instance, so no grouping is produced for it.)
- Evidence: `tmp/iotsupport-iot-architecture-guidance.md:158-190`; element kinds producer-manual.md:100,209-245,276-288.

## 4) API / Integration Surface

- Surface: `GET /api/pipeline/fleet-projection`
- Inputs: none (auth: bearer JWT with `pipeline` role / `iotsupport-pipeline` client).
- Outputs: `FleetProjectionResponseSchema` (devices + fleet config); read-only, no side effects.
- Errors: 401 unauthenticated; 403 missing `pipeline` role (`@allow_roles` → AuthorizationException,
  `app/utils/auth.py:199-216`); 500 on unexpected. No 404 (always returns, possibly empty list).
- Evidence: `app/api/pipeline.py:28-86` (mirror upload_firmware decorator stack + metrics block).

- Surface: Architecture pipeline trigger (outbound, fire-and-forget)
- Inputs: empty-body `POST` to `ARCHITECTURE_PIPELINE_TRIGGER_URL` (opaque Jenkins generic-webhook URL).
- Outputs: none consumed; best-effort. On unset URL → no-op. On HTTP/network failure → log + swallow.
- Errors: never propagates to the originating device/model write (decision 6). Short httpx timeout.
- Evidence: httpx pattern `app/services/keycloak_admin_service.py:58`; best-effort delete precedent
  `app/services/device_service.py:399-408`.

- Surface: `Jenkinsfile.architecture` Generate stage (CI)
- Inputs: env-bound creds `IOTSUPPORT_API_URL`, `IOTSUPPORT_CLIENT_ID`, `IOTSUPPORT_CLIENT_SECRET`,
  `IOTSUPPORT_TOKEN_URL` (Jenkins credentials); outbound HTTPS to architecture.webathome.org + prd API.
- Outputs: writes `docs/architecture/deployed-architecture.yaml`, then validate + archive glob.
- Errors: generator non-zero exit (unmapped model, fetch failure) fails the build before validate.
- Evidence: `Jenkinsfile.architecture:15-21`; client-credentials flow `app/templates/upload_firmware.sh.j2:99-117`.

## 5) Algorithms & State Machines

- Flow: `tools/gen-architecture.py` resolution
- Steps:
  1. Fetch published dataset (HTTPS) and call `GET /api/pipeline/fleet-projection` (client-credentials token).
  2. Load `docs/architecture/firmware-products.yaml`; build `code → product-UUID` map.
  3. Resolve once-per-build cap providers from `fleet`. **Candidate rule (both caps):** elements
     with `Realization→cap`, **excluding `stereotype: SoftwareProduct` entries** (the product-level
     realizers — see note), then filtered `environment == prd`:
     - `cap:iam` has **three** realizers in the dataset — `ss:keycloak-prd-…` (prd instance),
       `ss:keycloak-dev-…` (dev instance), and the env-unset product `ss:keycloak`. The
       product+dev are dropped by "instances ∧ env==prd" → `ss:keycloak-prd-keycloak-keycloak`.
       If >1 prd instance ever realizes it, tiebreak by fleet `oidc_issuer_url` host → matching
       host-bearing `svc:`/`if:` (`stats.hosts`/`url`) → bridge to the realizer by shared
       `release`/hint stem; assert agreement with the env pick.
     - `cap:pub-sub-broker` has **two** realizers — `ss:mosquitto-…-mosquitto` (prd instance) and
       the env-unset product `ss:mosquitto`. Same rule → `ss:mosquitto-mosquitto-mosquitto`;
       tiebreak via fleet `mqtt_url` host (`mosquitto.home`). Assert exactly one survivor or fail loud.
  4. Resolve once-per-build concrete `svc:` providers (by UUID from §6) to a running **instance**.
     The dataset has **three realizer shapes**, so branch:
     - **(a) svc realized directly by a prd instance** — e.g. `svc:home-assistant-mqtt` is realized
       by `ss:home-assistant-prd` (a prd `ss:` instance, producer `architecture`) *and* by the
       product `ss:home-assistant`. Take the non-product realizer with `environment == prd`
       directly as the provider. (This svc backs 6 of 8 firmware families, so this branch drives
       most non-universal `Serving` edges — it is the common case, not an exception.)
     - **(b) svc realized by a product only** — e.g. `svc:calendar-support`, `svc:infra-statistics`,
       `svc:iotsupport-api`. Find the prd instance(s) that `Specialization→` that product. For
       `svc:iotsupport-api` three prd instances specialize `app:iotsupport-app`, so pick the one
       with `stats.workload == "iotsupport"` / `container == "iotsupport-app"` (exclude the
       rotation-cronjob and setup-job instances); calendar/infra resolve to a single prd instance.
     - **(c) product realizer with no prd instance** — `svc:intercom` (`app:intercom-server` has
       zero specializers). No provider instance exists, so **skip that one `Serving` edge** and
       emit a warning (a `Serving` edge needs a real source — do not emit a sourceless/product-
       targeted edge). The device's other edges are unaffected. Expected/transient until
       intercom-server deploys (user-confirmed).
  5. For each device: resolve firmware product UUID from `code`; read that product's logical
     `Association` edges from the dataset; mint `device:` + `ss:<firmware>-<key>` (uuid5);
     emit `Specialization`, `Assignment`, one `Serving` per logical edge (provider-instance → ss),
     and `Aggregation` from the firmware grouping.
  6. Emit YAML envelope (`producer: iotsupport-app`, no per-element `producer:`).
- States / transitions: none (pure projection).
- Hotspots: dataset traversal is small (≤ low hundreds of elements); fleet ≤ 200 devices →
  trivial. Cap resolution computed once, not per device.
- Evidence: realization rule `…guidance.md:89-133`; instances confirmed in `tmp/published-architecture.json`.

- Flow: cap-provider host verify (tiebreaker)
- Steps:
  1. Parse host from fleet URL (`urlparse(...).hostname`).
  2. Find `svc:`/`if:` whose `stats.hosts`/`stats.url` contains that host.
  3. Bridge host-bearing element → realizing instance by shared `release`/hint stem (NOT by edge —
     no relation links them; verified).
  4. Assert the bridged instance equals the env=prd `Realization` pick; mismatch → fail loud.
- States / transitions: none.
- Hotspots: only exercised when >1 prd *instance* realizer for a cap; today each cap has exactly one prd instance realizer (after dropping product/dev realizers).
- Evidence: `svc:keycloak-prd-keycloak hosts auth.ginbov.nl`, `svc:mosquitto-mosquitto hosts mosquitto.home`
  (verified in `tmp/published-architecture.json`); structural note `…guidance.md:118-132`.

## 6) Derived State & Invariants

- Derived value: per-device element ids `device:…` and `ss:<firmware>-<key>`
  - Source: `uuid5(IOTSUPPORT_NS, "<prefix>:" + Device.key)` — `Device.key` is immutable
    (`app/models/device.py:48-50`; never mutated in `update_device`).
  - Writes / cleanup: emitted into `deployed-architecture.yaml`; not persisted in the DB.
  - Guards: namespace constant owned by the generator; no `Date.now()`/random in keys.
  - Invariant: regenerating twice yields byte-identical output (producer-manual.md:490-497).
  - Evidence: `tmp/iotsupport-iot-architecture-guidance.md:160-168,219-221`.

- Derived value: `introduced` date on every generated element
  - Source: **date portion of `Device.created_at`** from the projection; the `grp:<firmware>`
    Grouping uses `min(created_at)` over its members.
  - Writes / cleanup: the `introduced` field of each emitted `device:`/`ss:`/`grp:` element.
  - Guards: `created_at` is DB-server-set once and never mutated (`app/models/device.py:89-91`);
    use only the **date** (drop time/tz) so a single render second can't perturb output.
  - Invariant: deterministic and non-render-time — re-rendering an unchanged fleet keeps every
    `introduced` byte-identical; no hand-picked constant required.
  - Evidence: `app/models/device.py:89-91` (created_at server_default, no onupdate).

- Derived value: device→firmware-product binding
  - Source: filtered map `firmware-products.yaml[DeviceModel.code]`.
  - Writes / cleanup: the `Specialization` edge target (product UUID).
  - Guards: **fail-loud on unmapped `code`** — generator exits non-zero, build fails (no silent skip).
  - Invariant: every emitted device has exactly one resolvable firmware product.
  - Evidence: `…guidance.md:103-111,206-213`; immutable `code` `app/services/device_model_service.py:28,150`.

- Derived value: cap provider instance (iam, pub-sub-broker)
  - Source: `Realization→cap` set, **dropping `stereotype: SoftwareProduct` realizers**, then `environment == prd` (relation-grounded); fleet URL host is tiebreaker. (cap:iam has 3 realizers, cap:pub-sub-broker has 2 — see §0.)
  - Writes / cleanup: `Serving` edge source for every device of every firmware.
  - Guards: filtered (env=prd) view drives **emitted edges** for the whole fleet; if the env filter
    yields 0 or >1 unverified candidates → fail loud (assert exactly one after tiebreak).
  - Invariant: resolved provider must `Realize` the cap (matches the `boundBy`-resolver invariant,
    producer-manual.md:329-331); env pick and host tiebreak must agree.
  - Evidence: keycloak realizers prd/dev/product + mosquitto realizers prd/product (verified).

- Derived value: full fleet membership (the `devices` projection)
  - Source: **unfiltered** `select(Device)` — explicitly NOT filtered on `Device.active`.
  - Writes / cleanup: drives the entire set of emitted device elements/edges.
  - Guards: must not reuse the rotation/active filter; `active` is rotation-only.
  - Invariant: one emitted device per `devices` row (`…guidance.md:94-99`, `app/models/device.py:65-68`).
  - Evidence: list query `app/services/device_service.py:192-204`.

> A **filtered** (env=prd) view drives **emitted** cross-producer `Serving` edges; protected by
> asserting exactly one resolved provider and verifying against the fleet-URL host (Guards above).

## 7) Consistency, Transactions & Concurrency

- Transaction scope: this app does **not** commit in the service/handler — the request transaction
  is committed (or rolled back) centrally in `teardown_request` *after* the handler returns
  (`app/__init__.py:241-247`: `db_session.commit()` only on the `not (exc or g.needs_rollback)`
  branch). Every device/model write method only `flush()`es (`device_service.py:299,362,397`;
  `device_model_service.py:137,170,201,232`). **So the trigger must NOT fire inside the service**
  (it would fire before the row is committed/visible to the regenerating GET, and would fire even
  for a write that later rolls back — the inverse of Golden Rule 2).
- **Trigger firing = post-commit, request-scoped flag.** Two-step:
  1. The admin CRUD service methods (device create/update/delete; model create/delete; `upload_firmware`)
     call `self.trigger_service.mark_pending()` — which sets a `contextvars.ContextVar`, **not**
     Flask `g` (services stay Flask-free per CLAUDE.md "no Flask imports in services").
  2. `teardown_request`, in its **commit-success branch only** (after `db_session.commit()` returns,
     never on the rollback branch), calls `trigger_service.fire_if_pending()` — the best-effort POST.
     The ContextVar is cleared in the teardown `finally`.
  This fires exactly once per committed request that touched the fleet, after the row is durable —
  matching the project's "commit before external side effect" ordering.
- **Must not over-fire on rotation.** The rotation job mutates `Device` (rotation_state,
  cached_secret, timestamps) and commits, but those fields are runtime state excluded from the
  artifact (identity fence) — a regeneration would be byte-identical. Because firing is driven by
  explicit `mark_pending()` at the admin CRUD boundary (and the rotation path does **not** call it),
  rotation commits fire no trigger. This is why dirty-tracking every `Device` commit (a SQLAlchemy
  `after_commit` listener) is rejected: it would fire wasted Jenkins builds on every rotation step.
- Atomic requirements: the DB write commits independently of the trigger; a trigger failure is
  swallowed and never rolls back the write (it runs after the commit has already returned).
- Retry / idempotency: none needed — the trigger asks Jenkins to regenerate; the generator is
  idempotent (uuid5 keys). Duplicate/overlapping triggers are harmless (Jenkins coalesces builds).
- Latency note: `fire_if_pending()` runs synchronously in teardown with a short httpx timeout
  (≤5s); device/model writes are low-frequency admin ops (≤200 devices) so added latency is
  acceptable, and a failed/slow POST never blocks the committed write.
- Ordering / concurrency controls: none; the projection endpoint is a read; generator runs single-threaded in CI.
- Evidence: teardown commit `app/__init__.py:238-251`; flush points cited above; httpx singleton
  precedent `app/services/keycloak_admin_service.py:42-58`.

## 8) Errors & Edge Cases

- Failure: device's `model_code` absent from `firmware-products.yaml`
- Surface: generator (CI).
- Handling: exit non-zero with the offending code; build fails. No partial YAML.
- Guardrails: keep the mapping in sync when adding a model; covered by a generator unit test.
- Evidence: `…guidance.md:103-111,206-213`.

- Failure: a concrete `svc:` target has no resolvable provider instance (today: `svc:intercom`)
- Surface: generator.
- Handling: **skip that one `Serving` edge and log a warning** (not fatal). A `Serving` edge needs a
  real source UUID, and the future `intercom-server` instance UUID is unknowable here (helm-charts
  mints it on deploy), so a valid forward-reference cannot be emitted — emitting a product-targeted
  or invented-UUID edge would be wrong. The intercom device's other 4 edges still resolve; the
  svc:intercom edge appears automatically once intercom-server deploys and IoT Support re-generates.
- Guardrails: this skip is scoped to *concrete `svc:` with zero prd instances* (NOT the firmware
  `Specialization` target, which is a known published UUID and would legitimately dangle-but-emit).
  Distinguish the two in code. User-confirmed that the intercom gap is expected/transient.
- Evidence: `app:intercom-server` has zero Specialization instances (verified); `…guidance.md:237,240-242`.

- Failure: `ARCHITECTURE_PIPELINE_TRIGGER_URL` unset (dev/test)
- Surface: trigger service.
- Handling: no-op (skip POST), debug log. Never errors.
- Guardrails: gate on truthy config (mirrors `KeycloakAdminService.enabled` `app/services/keycloak_admin_service.py:61-72`).
- Evidence: optional config pattern `app/app_config.py:34-79`.

- Failure: trigger POST times out / 5xx
- Surface: trigger service.
- Handling: catch, `logger.warning`, swallow; the device/model write still succeeds.
- Guardrails: short httpx timeout; metric records `error` status.
- Evidence: best-effort precedent `app/services/device_service.py:399-408`.

- Failure: dataset fetch / projection API unreachable in CI
- Surface: generator.
- Handling: exit non-zero; build fails (don't emit a partial/empty artifact). Validation not skipped.
- Guardrails: explicit fetch error handling; no silent fallback.
- Evidence: producer-manual.md:633-649; `arch-validate` transport handling `scripts/arch-validate.py:142-147`.

- Failure: cap resolves to 0 or >1 unverified prd realizers
- Surface: generator.
- Handling: fail loud (assert exactly one after env filter + host tiebreak).
- Guardrails: covered by generator unit test with a synthetic two-prd-realizer dataset.
- Evidence: producer-manual.md:329-331; resolution flow §5.

## 9) Observability / Telemetry

- Signal: `iot_config_operations_total{operation="pipeline_fleet_projection",status}`
- Type: counter (+ duration histogram via the same helper).
- Trigger: emitted in the projection endpoint's `finally` block.
- Labels / fields: `operation`, `status` (success/error).
- Consumer: existing Prometheus `/metrics`.
- Evidence: `app/utils/iot_metrics.py:26-39`; pattern `app/api/pipeline.py:51-85`.

- Signal: `iot_config_operations_total{operation="architecture_pipeline_trigger",status}`
- Type: counter.
- Trigger: emitted by the trigger service per POST attempt (incl. skipped/error).
- Labels / fields: `operation`, `status` (success/error/skipped).
- Consumer: `/metrics`.
- Evidence: `app/utils/iot_metrics.py:26-39`.

- Signal: structured log on trigger skip/failure and on generator warnings (dangling intercom)
- Type: structured log.
- Trigger: trigger service warning paths; generator stderr.
- Labels / fields: target URL host (not secret payload), device count, unmapped code.
- Consumer: log aggregation; CI console.
- Evidence: logging precedent `app/services/device_service.py:402-408`.

## 10) Background Work & Shutdown

- Worker / job: architecture pipeline trigger (synchronous, in `teardown_request` post-commit)
- Trigger cadence: event-driven — once per committed request whose admin CRUD path called
  `mark_pending()` (device create/update/delete; model create/delete; firmware upload). Fires from
  the teardown commit-success branch, after the write is durable; never on rollback; never on the
  rotation path (which does not mark pending).
- Responsibilities: one short best-effort outbound POST; no threads, no queue.
- Shutdown handling: none required — synchronous and best-effort; if the process is shutting down a
  failed/aborted POST is swallowed like any other failure. No `LifecycleCoordinator` registration needed.
- Evidence: synchronous nature per decision 6; coordinator usage is for background threads
  (`app/services/container.py:155-160` MqttService is the threaded counter-example).

- Worker / job: `tools/gen-architecture.py`
- Trigger cadence: CI only (Generate stage), invoked by the trigger and by SCM builds.
- Responsibilities: project → resolve → emit YAML. Stateless, single-shot.
- Shutdown handling: n/a (CI process).
- Evidence: `Jenkinsfile.architecture`; producer-manual.md:636-643.

## 11) Security & Permissions

- Concern: authorization of the projection endpoint
- Touchpoints: `GET /api/pipeline/fleet-projection`.
- Mitigation: `@allow_roles("pipeline")` (same gate as firmware upload); validated at startup
  (`app/utils/auth.py:401-424`). M2M JWT via `iotsupport-pipeline` client.
- Residual risk: projection exposes device keys + model codes + firmware versions to the pipeline
  client only; no secrets (no Keycloak secrets, no NVS, no raw config). Acceptable.
- Evidence: `app/api/pipeline.py:37,96`; role config `app/services/container.py:98-103`.

- Concern: opaque trigger URL handling
- Touchpoints: `ARCHITECTURE_PIPELINE_TRIGGER_URL` (may embed a Jenkins generic-webhook token).
- Mitigation: treat as a secret-bearing config; never log the full URL (log host only); not returned by any API.
- Residual risk: low; URL lives only in server env.
- Evidence: config pattern `app/app_config.py:34-79`; logging discipline §9.

## 12) UX / UI Impact

- Entry point: none (admin UI).
- Change: none — the trigger is a server-side side effect of existing device/model writes; the
  projection endpoint is pipeline-only. No new admin screens or contracts.
- User interaction: unchanged.
- Dependencies: none. A `frontend_impact.md` is **not** warranted for this feature.
- Evidence: BFF/no-frontend-change note (CLAUDE.md deprecation section); endpoints are pipeline-scoped.

## 13) Deterministic Test Plan

- Surface: `GET /api/pipeline/fleet-projection` (service: `DeviceService.get_fleet_projection`)
- Scenarios:
  - Given two devices (one `active`, one inactive) across two models, When projecting, Then both appear (no `active` filter) with `key`, `model_code`, `firmware_version`, `device_name`, `created_at`.
  - Given fleet config set, When projecting, Then `fleet.mqtt_url` = `device_mqtt_url` and `oidc_issuer_url` = `oidc_token_url`; `baseurl` absent.
  - Given a model without firmware (`firmware_version is None`), When projecting, Then `firmware_version` is null and the device is still listed.
- Fixtures / hooks: `container.device_service()`, seeded `DeviceModel`/`Device`, `AppSettings` with fleet URLs.
- Gaps: none.
- Evidence: `app/services/device_service.py:192-204`; container test pattern (CLAUDE.md).

- Surface: `GET /api/pipeline/fleet-projection` (API auth/role)
- Scenarios:
  - Given no token, When GET, Then 401.
  - Given a token without `pipeline`, When GET, Then 403.
  - Given a `pipeline` token, When GET, Then 200 + schema-valid body.
- Fixtures / hooks: testing-auth helpers used by existing pipeline API tests.
- Gaps: none.
- Evidence: `app/utils/auth.py:199-216`; `app/api/pipeline.py:37`.

- Surface: `ArchitecturePipelineTriggerService`
- Scenarios:
  - Given URL unset, When trigger(), Then no POST, status `skipped`, no exception.
  - Given URL set + stubbed httpx 204, When trigger(), Then one empty-body POST, status `success`.
  - Given httpx raises/timeouts, When trigger(), Then exception swallowed, status `error`, warning logged.
- Fixtures / hooks: monkeypatch httpx client; `AppSettings` with/without the URL.
- Gaps: none.
- Evidence: httpx singleton `app/services/keycloak_admin_service.py:42-58`.

- Surface: CRUD `mark_pending()` wiring (Device + DeviceModel services)
- Scenarios:
  - Given a spy trigger, When create/update/delete device, Then `mark_pending()` called once each.
  - Given a spy trigger, When create/update/delete model and upload_firmware, Then `mark_pending()` called once each.
  - Given a spy trigger, When the rotation job mutates a device's rotation_state and commits, Then `mark_pending()` is NOT called (no wasted trigger).
- Fixtures / hooks: inject a spy trigger via the container; assert `mark_pending` call counts.
- Gaps: none.
- Evidence: service ctors `app/services/container.py:219-235`; rotation path `app/startup.py:199-262`; write paths cited in §2.

- Surface: post-commit firing (API-level, exercises `teardown_request`)
- Scenarios:
  - Given URL set, When a POST creates a device (request commits), Then exactly one trigger POST fires AFTER commit (assert ordering: row visible to a follow-up GET before the POST is observed).
  - Given a request that sets `g.needs_rollback` / raises after `mark_pending()`, When it tears down, Then NO trigger fires (rolled-back write must not trigger).
  - Given two devices created in one request (bulk), When it commits, Then the trigger fires once (pending flag is per-request, not per-row), and the ContextVar is reset in teardown `finally`.
- Fixtures / hooks: Flask test client; stub httpx; assert fire happens on commit-success branch only.
- Gaps: none.
- Evidence: teardown `app/__init__.py:238-251`; ContextVar reset mirrors `db_session.reset()` discipline.

- Surface: `tools/gen-architecture.py` (generator unit tests against a fixture dataset)
- Scenarios:
  - Given a fixture dataset + projection, When generating, Then per-device `device:`/`ss:` + Specialization/Assignment/Serving/Aggregation edges match expected.
  - Given identical inputs twice, When generating, Then byte-identical YAML (determinism).
  - Given a projection with a known `created_at`, When generating, Then each element's `introduced` = its date portion, and the per-firmware Grouping's `introduced` = `min(created_at)` of its members.
  - Given a device whose `model_code` is unmapped, When generating, Then non-zero exit + clear error.
  - Given `svc:intercom` with no prd instance, When generating, Then that one `Serving` edge is SKIPPED + a warning logged (not fatal), and the device's other edges are still emitted.
  - Given `svc:home-assistant-mqtt` realized by both a prd `ss:` instance and a product, When resolving, Then the prd instance is chosen (shape (a), not via Specialization).
  - Given keycloak prd+dev realizers, When resolving `cap:iam`, Then prd instance chosen; host tiebreak agrees.
  - Given a synthetic two-prd-realizer cap with disagreeing host, When resolving, Then fail loud.
- Fixtures / hooks: a trimmed `tmp/published-architecture.json`-shaped fixture + a sample projection JSON.
- Gaps: end-to-end CI run against live prd deferred to manual first-build verification.
- Evidence: verified resolution facts in `tmp/published-architecture.json`; determinism producer-manual.md:490-497.

## 14) Implementation Slices

- Slice: Projection endpoint
- Goal: Pipeline client can fetch the raw fleet projection.
- Touches: `app/schemas/pipeline.py`, `app/services/device_service.py`, `app/api/pipeline.py`, tests.
- Dependencies: none.

- Slice: Trigger config + service + mark_pending wiring + post-commit firing
- Goal: Committed device/model writes best-effort trigger the architecture job, post-commit, never on rollback or rotation.
- Touches: `app/app_config.py`, `app/services/architecture_pipeline_trigger_service.py` (ContextVar +
  `mark_pending`/`fire_if_pending`), `app/services/container.py`, `device_service.py`,
  `device_model_service.py` (`mark_pending` calls), `app/__init__.py` (teardown post-commit fire), tests.
- Dependencies: config first.

- Slice: Annotation file + hand-authored Jenkins edge
- Goal: code→product map committed; IoT-Support→Jenkins edge modeled.
- Touches: `docs/architecture/firmware-products.yaml`, `docs/architecture/architecture.yaml`.
- Dependencies: UUIDs resolved from the dataset.

- Slice: Generator + CI + gitignore
- Goal: `deployed-architecture.yaml` generated, validated, archived in CI.
- Touches: `tools/gen-architecture.py`, `Jenkinsfile.architecture`, `.gitignore`, generator tests.
- Dependencies: projection endpoint + annotation file.

## 15) Risks & Open Questions

- Risk: ID collision with the 18 existing `device:` elements or this repo's hand-authored YAML.
- Impact: corrupted/merged graph.
- Mitigation: private IoT Support uuid5 namespace constant; prefix-scoped keys; verify no overlap on first build.

- Risk: cap-realizer ambiguity if a second prd realizer appears.
- Impact: wrong `Serving` source for the whole fleet.
- Mitigation: env=prd filter + host tiebreak + assert-exactly-one; unit-tested.

- Risk: trigger failure silently masks stale architecture.
- Impact: model lags reality until next SCM build.
- Mitigation: best-effort by design + metric/warning; SCM builds also regenerate.

- Risk: annotation file drifts when a new model is added.
- Impact: generator fails the build (fail-loud) — acceptable, but blocks CI until updated.
- Mitigation: documented in the file; covered by a test.

- Question: Is the Jenkins trigger URL a Generic Webhook Trigger (token in query) or a Jenkins remote-build URL?
- Why it matters: affects whether the empty-body POST needs auth headers vs an embedded token.
- Owner / follow-up: Pieter / Jenkins config — the service treats it as fully opaque, so either works.

- RESOLVED: `introduced` for generated elements = date portion of `Device.created_at` (the
  Grouping uses `min(created_at)` of its members). `created_at` is the immutable, DB-set row
  timestamp, so `introduced` is stable, meaningful (when the device actually entered the fleet),
  and non-render-time — no hand-picked constant. The projection returns `created_at` per device.
  See §3 (contract) and §6 (`introduced` derived value).

## 16) Confidence

Confidence: High — every resolution path (firmware edges, cap realizers, concrete svc instances, the
intercom dangle, the iotsupport main-workload disambiguation) was verified against the published
dataset, and all touchpoints map cleanly onto existing pipeline/auth/DI/CI patterns.
