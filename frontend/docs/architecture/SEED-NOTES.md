# Seed notes — `iotsupport-ui` producer

Headless seeding of the first architecture artifact for the IoT Support UI
(React 19 SPA admin interface for the IoT Support backend). Mode:
**hand-authored** (no generator; the YAML is the source of truth).

## Fixed facts applied (not re-derived)

- Producer id: `iotsupport-ui`.
- Product: «SoftwareProduct» ApplicationComponent `app:iotsupport-ui`,
  `sourceRepository: git:pvginkel/IoTSupportUI`, image `registry:5000/iotsupport-ui`.
- `introduced: 2026-01-09` on every element (repo's first commit,
  `git log --reverse --format=%ad --date=short | head -1`).

## Minted ids

| id | kind | notes |
|---|---|---|
| `app:iotsupport-ui,2ab5d9e8-6450-4dd0-b201-29c93b99a24b` | ApplicationComponent «SoftwareProduct» | uuid4 minted once via `python3 -c 'import uuid; print(uuid.uuid4())'` |

No other elements minted (see exclusions below).

## Modeling decisions

### No exposed ApplicationService / ApplicationInterface
The app is a static-asset SPA served by nginx (`nginx.conf`, listen :3100).
It offers **no network API** that another software component consumes by name —
the browser/end-user is the only consumer, and the public ingress host is the
deploying (helm-charts) producer's concern. Per the manual, an interface-per-
served-asset would be an endpoint inventory, not architecture. So the product
realizes no ApplicationService and no capability. `/health` (nginx) is an
operational surface → OUT.

### `environment` / `cluster` unset
Logical, type-level surface spanning all deployed envs; per-env placement is the
helm-charts producer's job.

### Outbound consumption edges (2)

1. `app:iotsupport-ui —Association→ svc:iotsupport-api,b7c5b5ba-36eb-47b8-bf7e-5c50fa1a3656`
   — the SPA's `/api/` calls, proxied by nginx to the backend. The target is the
   IoT Support backend's API service (cross-producer `iotsupport-app`, resolved
   from `../IoTSupport/docs/architecture/architecture.yaml`).
2. `app:iotsupport-ui —Association→ svc:ssegateway,59a7d043-bb0c-4e44-a8b8-3e943338f807`
   — the SPA's `/api/sse/` event stream, proxied by nginx to the SSE gateway
   (`src/components/sse/`). In-house provider service, referenced by its specific
   `svc:` UUID per convention (cross-producer `ssegateway`; same UUID the backend
   artifact references).

### No `boundBy` on either edge — deliberate
The **deployed** artifact is `nginx.conf`, which **hardcodes** the proxy targets
to pod-local loopback (`proxy_pass http://127.0.0.1:3101` for `/api/`,
`http://127.0.0.1:3102` for `/api/sse/`). The backend and SSE gateway are
same-pod sidecars; the wire is not carried by an env var at runtime. The
`BACKEND_URL` / `SSE_GATEWAY_URL` env vars exist **only** for the Vite
dev/preview proxy (`vite.config.ts:78-79`), not the deployed container. Per the
manual ("include `boundBy` only if an env var carries the endpoint; when the base
URL is hardcoded, omit it"), both edges omit `boundBy`. For `svc:` targets
`boundBy` is optional regardless.

## Excluded candidates (inclusion rule → OUT)

- **Monaco editor** (`monaco-editor ^0.55.1`) — a **direct** dependency, bundled
  by Vite (not loaded from a CDN at runtime). No external service. OUT.
- **esptool-js / Web Serial** (`src/lib/esptool/`, `navigator.serial`) — flashes
  ESP32 firmware over a local USB serial port from the browser. Local hardware
  access, not a named network dependency. OUT.
- **OIDC / IdP** — auth is a same-origin redirect to `/api/auth/login`
  (`src/lib/auth-redirect.ts`), proxied to the backend; the SPA never contacts an
  IdP directly. No `cap:iam` edge for the frontend (the backend owns that edge).
- **OpenAPI spec fetch** (`scripts/generate-api.js`) — build-time codegen against
  the backend spec, not a runtime dependency. OUT.
- **`/health`** (nginx) — operational surface, belongs to the deployment lens. OUT.

## Cross-producer references

| Reference | Producer | Status |
|---|---|---|
| `svc:iotsupport-api,b7c5b5ba-…` | `iotsupport-app` | Resolved from the backend repo's local artifact. May dangle until that producer publishes; validator reports, doesn't fail. |
| `svc:ssegateway,59a7d043-…` | `ssegateway` | UUID copied from the backend artifact (same gateway). May dangle until `ssegateway` publishes. |

## Validation

`./scripts/arch-validate.py docs/architecture/*.yaml` → exit 0 (clean).

## Open questions for a human

- **No exposed service for the SPA** — confirm the convention that a static-asset
  frontend models no ApplicationService (the deployer attaches the public host).
  If the rendered UI host should appear as an interface, it would be added by the
  helm-charts producer, not here.
- **`boundBy` omitted** — confirm the deployed nginx genuinely hardcodes loopback
  in all environments (i.e. backend + SSE gateway are always same-pod sidecars).
  If any environment injects the backend host via env at runtime, a `boundBy`
  recipe would be warranted.
- **`svc:ssegateway` ownership** — confirm the `ssegateway` producer will publish
  this UUID so the reference resolves at merge time.
