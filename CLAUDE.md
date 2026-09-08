# IoTSupport

A homelab IoT device management system: a Flask backend and a React frontend for provisioning
ESP32 devices, distributing firmware, and automatically rotating device OAuth credentials. Single
tenant, one deployment — production. `github.com/pvginkel/IoTSupport` is a **public** repo; the
spec repo is not.

## Repo structure

- **Root** — orchestration tooling (`tools/suite_runner`, `scripts/`), the `Procfile.dev` dev
  stack, `docs/`, and CI (`Jenkinsfile`, `Jenkinsfile.architecture`).
- **`backend/`** — Flask REST API: device/model CRUD, firmware storage, Keycloak M2M auth, MQTT
  rotation notifications, Prometheus metrics. Python/Poetry.
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

The full CI suite is `cexec modern-app poetry run run-suite`; Jenkins runs the same command with
`--output-mode full`. `scripts/dev.py` starts all three dev services (frontend :3100, backend
:3101, SSE gateway :3102) — stop it with `^C`, never `kill`.

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
