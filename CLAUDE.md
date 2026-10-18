# IoTSupport

A homelab IoT device management system: a Flask backend and a React frontend for provisioning
ESP32 devices, distributing firmware, and automatically rotating device OAuth credentials. Single
tenant, one deployment — production. `github.com/pvginkel/IoTSupport` is a **public** repo; the
spec repo is not.

## Repo structure

- **Root** — orchestration tooling (`tools/suite_runner`, `scripts/`), the `Procfile.dev` dev stack,
  `docs/`, and CI (`Jenkinsfile`, `Jenkinsfile.architecture`, which publishes the architecture
  model).
- **`backend/`** — Flask REST API: device/model CRUD, firmware storage, Keycloak M2M auth, MQTT
  rotation notifications, Prometheus metrics. Python/uv.
- **`frontend/`** — React 19 + TanStack Router/Query SPA with a generated OpenAPI client.
  pnpm + Vite + Playwright.
- **`../IoTSupportSpecs`** — the slice/planning repo, a **separate git repo**. Commit there as you
  go, staged by name: it is a shared working tree and parallel sessions live in it.

Those three names are the components `kc project` drives; `kc project list` is the source of truth
for them.

## Building and testing

`kc project setup|build|test|lint [component]` runs the curated automation declared in
`.kubecoder/project.yaml`. **Run every verb from the repo root** — `kc project` is cwd-bound.
Everything executes in the `modern-app` tool container, one sidecar for both toolsets because the
Playwright harness boots the Flask backend per worker.

The full CI suite is `cexec modern-app uv run run-suite`; Jenkins runs the same command with
`--output-mode full`. `scripts/dev.py` starts all three dev services (frontend :3100, backend :3101,
SSE gateway :3102) — stop it with `^C`, never `kill`; `scripts/dev.py stop` stops it from another
shell. The root and `backend/` are two uv projects, each with its own committed `uv.lock`, because
CI and the image sync `--locked`. After a backend API change,
`scripts/regenerate-openapi.py --frontend` refreshes the frontend's OpenAPI cache and client; a
backend test fails while the committed cache is stale.
`cexec modern-app python3 scripts/check_updates.py` reports the dependencies with a newer release,
major, minor and patch, in every component it finds.

`kc project lint` is green at HEAD. It stops at the first failing statement, so a red lint hides
the state of every statement behind it — run them individually to read it.

## Design philosophy

Clean breaking changes inside the BFF boundary — fix the callers, no shims. No tombstones: delete
replaced code rather than deprecating it. No defensive coding; fail fast. Every change ships with
a test. Never hand-edit the generated OpenAPI client. The two contracts that leave the repo —
`/iot/*` for deployed firmware and `/pipeline/*` for other repos' CI — are the exception and are
not broken freely. `docs/change-discipline.md` is the full rule set and the reviewers' citation.

## Key documentation

- `docs/` — the cross-cutting docs, including the pipeline's own procedure docs.
- `backend/CLAUDE.md` — backend architecture, layering, DI, testing, and S3/storage conventions.
- `backend/docs/product_brief.md` — the domain model: devices, models, credential rotation.
- `backend/docs/decisions/` — the ADRs.
- `frontend/CLAUDE.md` — frontend launchpad; the detailed conventions live under
  `frontend/docs/contribute/`, hub at `index.md`.
- `frontend/docs/product_brief.md` — frontend product context and workflows.

`*/docs/features/` in both components is a frozen audit trail from the pre-plugin workflow, not a
description of the system as it is now.

## Architecture model

IoTSupport is a producer in the estate's federated architecture model. Its models are hand-authored:
the backend's in `backend/docs/architecture/architecture.yaml` and the frontend's in
`frontend/docs/architecture/*.yaml`; `firmware-products.yaml` beside the backend's is the
generator's input, not a model. `Jenkinsfile.architecture`, the job `AaC/IoTSupport`, generates a
deployed-architecture model from the production device fleet on every build (never committed),
validates it and the hand-authored models against the architecture service, and archives them for
AaC/Architecture to collect. `kc project lint` validates the hand-authored models too
(`arch-validate`, in the `aac-tools` sidecar).

The model is kept current centrally, not from here: the central architecture update in
`pvginkel/Architecture` (`tooling/fleet.py update`) reads the commits since the model last changed
and commits what they change in it. Nothing needs to run here after a change.

`Jenkinsfile.architecture` is the app's own, and `copier update` leaves it alone.
