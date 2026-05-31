# SEED-NOTES — iotsupport-app architecture artifact

First-version seeding of the `iotsupport-app` producer. Hand-authored mode
(the YAML is the source of truth). Run headless — decisions taken without
operator triage and logged here. `introduced` on every element is this repo's
first-commit date, **2026-01-09** (`git log --reverse --format=%ad --date=short | head -1`).

## Mode

Hand-authored. No generator / annotation convention present. uuid4 minted once
per element (below); never re-minted.

## Minted ids

| id | label | uuid |
|---|---|---|
| `app:iotsupport-app` | IoT Support (SoftwareProduct) | `bbc500fd-ef66-4d82-846c-cd0357cb03f7` |
| `svc:iotsupport-api` | IoT Support API | `b7c5b5ba-36eb-47b8-bf7e-5c50fa1a3656` |
| `if:iotsupport-admin-api` | IoT Support admin API | `5cd24be3-4067-4044-9acc-d5b4f59016f3` |
| `if:iotsupport-device-api` | IoT Support device API | `01a9b280-38c5-4713-8da2-6930243b6d02` |

`app:iotsupport-app` carries `stereotype: SoftwareProduct`,
`sourceRepository: git:pvginkel/IoTSupport`, and `stats.image: registry:5000/iotsupport-app`
(per fixed-facts brief). `environment`/`cluster` left unset on every element —
these are logical type-level surfaces spanning all deployed envs; per-env
placement belongs to the helm-charts producer.

## Exposed surface

One `ApplicationService` (`svc:iotsupport-api`) realized by the product
(`app —Realization→ svc`). Two `ApplicationInterface`s, one per **distinct
consumer class** (grouped by consumer, never per route):

- **admin UI** → `if:iotsupport-admin-api` — the `/api/*` management surface
  (device-models, devices, rotation), user-OIDC authenticated. Consumer is the
  separate frontend producer; its consumption edge is authored on that
  producer's side, not here.
- **device fleet** → `if:iotsupport-device-api` — the `/api/iot` surface
  (config, firmware, provisioning, coredump), Keycloak M2M JWT authenticated.

Both `if —Assignment→ svc`. The two classes are distinct by auth mechanism
(user OIDC vs device M2M), origin (browser/SPA vs ESP32), and intent
(management vs device lifecycle).

Evidence: `app/api/__init__.py:6` (`/api` prefix), `app/api/iot.py:41,44-64`
(device-auth `/iot`), `app/api/auth.py:34` (OIDC BFF).

## Outbound consumption edges (modeled)

| Target | Kind | boundBy | Evidence |
|---|---|---|---|
| `cap:relational-database` | substitutable infra (PostgreSQL) | `env:DATABASE_URL` | `app/config.py:86` |
| `cap:iam` | substitutable infra (Keycloak/OIDC) | `env:OIDC_ISSUER_URL` | `app/config.py:133` |
| `cap:pub-sub-broker` | substitutable infra (MQTT) | `env:MQTT_URL` | `app/app_config.py:46,173` |
| `cap:object-storage` | substitutable infra (S3 / Ceph RGW) | `env:S3_ENDPOINT_URL` | `app/config.py:180` |
| `cap:logging` | substitutable infra (Elasticsearch) | `env:ELASTICSEARCH_URL` | `app/app_config.py:73,192` |
| `svc:ssegateway,59a7d043-bb0c-4e44-a8b8-3e943338f807` | in-house provider service | `env:SSE_GATEWAY_URL` | `app/config.py:215`, `app/services/sse_connection_manager.py:79` |

All are `app —Association→ target`. The SSE gateway UUID was hand-provided by
the seeding brief (not yet in the published dataset); the edge will resolve
once that producer is published — dangling-but-reported is acceptable per the
manual. The app POSTs to `{SSE_GATEWAY_URL}/send`; the webhook the app exposes
for the gateway is an implementation detail of *consuming* the gateway, so it
is modeled as this one edge, not a second interface on the app.

## Decisions & exclusions (default-out on borderline)

- **Keycloak appears as IAM via two wires** — browser OIDC (`OIDC_ISSUER_URL`)
  and the Keycloak admin API for device-client provisioning
  (`KEYCLOAK_BASE_URL`, `app/app_config.py:54`). Both terminate at the same IAM
  provider, so modeled as **one** `cap:iam` edge. Chose `OIDC_ISSUER_URL` as the
  `boundBy` (the canonical IAM issuer binding). *Open question:* is the admin
  API a sufficiently distinct dependency to warrant its own edge? Default: no.
- **Elasticsearch → `cap:logging`.** The app bulk-indexes device logs into ES
  (`/_bulk`) and searches them. `cap:logging` ("log shipping / aggregation /
  search") fits the domain better than `cap:full-text-search`. *Open question:*
  confirm `cap:logging` vs `cap:full-text-search`.
- **Parse sidecar (`PARSE_SIDECAR_URL`, `app/app_config.py:36`) — OUT.** A
  coredump-parsing sidecar deployed alongside this app; no matching capability
  in the enum, no published `svc:` UUID to reference, and (as a sidecar) likely
  same-pod. Treated as a deployment implementation detail. *Open question:* is
  the parse sidecar a separate producer that should own a `svc:` element this
  app then references?
- **`INTERNAL_API_URL` (`app/app_config.py:79`) — OUT.** Self-call: the rotation
  CronJob nudges this same app's web process (`/internal/rotation-nudge`). Not a
  distinct dependency.
- **`FRONTEND_VERSION_URL` (`app/config.py:207`) — OUT.** Trivial
  backend→frontend version-check ping; the manual explicitly excludes these.
- **`BASEURL`/`DEVICE_BASEURL` (`app/app_config.py:61,165`) — OUT.** The app's
  own advertised base URL baked into provisioning packages, not an outbound
  dependency.
- **Operational surfaces OUT:** `/metrics` (Prometheus, `app/api/metrics.py:8`),
  `/health` probes (`app/api/health.py:14`), `/internal` — these belong to the
  deployment (helm-charts) lens, not the app.
- **No capability realized.** This is a business backend; it realizes no
  platform capability, so no `app —Realization→ cap:` edge.

## Cross-producer references

- `svc:ssegateway,59a7d043-bb0c-4e44-a8b8-3e943338f807` — hand-provided UUID;
  not in the published dataset yet, so the reference dangles until that producer
  builds. Reported by the validator, not failing.

## Validation

`./scripts/arch-validate.py docs/architecture/*.yaml` → exit 0 (clean).

## Open questions for a human

1. `cap:logging` vs `cap:full-text-search` for the Elasticsearch device-log
   store?
2. Should the Keycloak admin API (`KEYCLOAK_BASE_URL`) be a second `cap:iam`
   edge, or is one IAM edge sufficient?
3. Is the parse sidecar (`PARSE_SIDECAR_URL`) its own producer/service worth a
   modeled edge, or a same-pod implementation detail (current assumption)?
