# KubeCoder onboarding — state note

Scratch file. Delete at close-out. Written before the step-7 restart.

## Decisions (from the operator interview)

- **Full tier.** Specs repo is `pvginkel/IoTSupportSpecs` — **created private,
  auto-initialised** (it did not exist; the pod clones it at start-up, so it
  had to exist before the sync). Registered in `config.yaml` with
  `shared: true`.
- **No sibling repos.** The old compose mounted ElectronicsInventory,
  DockerImages/iotsupport and HelmCharts read-only; none carried over.
  SSEGateway is deliberately *not* a sibling — it is a pnpm `github:` devDependency.
- **Ports:** 3100 (frontend) gets `sslOffload`; 3101 (backend) and 3102 (SSE
  gateway) are plain http.
- **Keycloak:** skipped. Every `KEYCLOAK_*` setting defaults to `None` and the
  tests use fake values, so nothing blocks green. Credential rotation against a
  live Keycloak is simply not exercisable in-pod.
- **CI stays on SQLite**; Postgres is added as a service for running the dev app.

## Done (committed)

- `0a9caaf` — `.kubecoder/config.yaml` + `project.yaml`, `backend/scripts/init-dev-database.py`
- `93ca0ce` — deleted both `.llmbox/`, rewrote workspace + three `tasks.json`,
  ported image builds to kaniko, `cexec`-prefixed `Procfile.dev`
- `25100ed` — docs sweep, deleted `tools/ai_workflow/send_message.py`

## Step 7 still owes

After the restart, verify: `IoTSupportSpecs` cloned under `/work`,
`cexec modern-app true`, `cexec kaniko true`, and postgres/minio/opensearch
answering on localhost. Then `kc project setup`, `build`, `test`.

**Baseline to match: Jenkins `IoTSupport/IoTSupport` #124 — 826 passed, 0 failed.**

Known open items, in the order they will probably bite:

1. **MinIO credentials.** `app/config.py` defaults to `admin`/`password`;
   Jenkins uses `minioadmin`/`minioadmin`; the catalog sidecar's actual root
   credentials are unknown until it is up. Tests call
   `ensure_bucket_exists()` themselves, so the bucket is not the problem — the
   credentials are. Prefer fixing the default in code over generating a `.env`.
2. **Postgres.** `init-dev-database.py` assumes the URL's credentials work
   against the maintenance database. Untested — the sidecar did not exist when
   it was written. Also note `.env.example` says database `iot-support` while
   `config.py` says `iotsupport`; reconcile.
3. **`ELASTICSEARCH_URL` defaults to `None`**, so the app skips OpenSearch. For
   dev against the sidecar it wants `http://localhost:9200`. Consider fixing the
   default.
4. **`scripts/dev.py` runs honcho under `unshare --user --pid --fork`.** User
   namespaces may not be permitted in the pod, and its children are now `cexec`
   clients — killing those may not kill the real processes in the sidecar.
   Verify signal handling and log capture, and report the experience back into
   the onboard skill (the skill flags this as lightly-trodden ground).
5. **Python 3.13.** `build-all.py` and `suite_runner/local.py` pin the backend
   venv with `poetry env use python3.13` only when that binary is on PATH.
   Confirm what `modern-app` actually provides.
6. **`run-suite` needs no edits** — run it as
   `cexec modern-app poetry run run-suite`, so its subprocesses land in the
   right container while CI keeps invoking it with no `cexec` inside. Do not
   add `cexec` to `suite_runner/`; Jenkins has neither `cexec` nor `kc`.

## Left for /dev:onboard (step 9)

- `.claude/commands/*`, `.claude/agents/*`, `backend/.claude/agents/*`,
  `frontend/.claude/agents/*` — in-repo copies of the pre-plugin workflow.
- `tools/ai_workflow/claude_session.py`, `codex_exec.py`.
- `scripts/preflight.py` + `scripts/build-all.py` — per-repo preflight, now
  duplicated by `kc project setup`/`build`. **These still call bare
  `poetry`/`pnpm` and will not work in-pod until retired or `cexec`-prefixed.**
- `.claude/commands/{triage,run-slice}.md` reference the deleted
  `send_message.py`.
- The quality tooling (`tools/code_health/`, `.codehealthignore`).
- CLAUDE.md contract lines + diet; specs-repo scaffolding.
