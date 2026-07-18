# KubeCoder onboarding — state & lessons learned

Scratch file. Delete at close-out, **after** folding the "Lessons for the skill"
section into `skills/onboard/SKILL.md` and `references/catalog.md` in
KubeCoderConfig (the skill's standing requirement).

---

## Status

`kc project setup | build | test` all pass. Totals match the last green Jenkins
build (`IoTSupport/IoTSupport` #124, 826 passed): **696 backend pytest + 130
Playwright = 826.**

`kc project lint` is red on 3 pre-existing ruff errors — see "Known-red" below.

### Pending, in order — do not reorder

1. **Seed OpenBao**, copying IoTSupport's Keycloak admin client from the Jenkins
   entry into the catalog. Script:
   `scratchpad/add-keycloak-catalog-secret.sh` (uses `kv patch`, so the catalog's
   existing properties survive; prints no secret values).
2. **Deploy the kubecoder chart** so ESO materialises the two new catalog keys
   (`configs/prd/kubecoder/prd/values.yaml` already committed).
3. **Rebuild the frontend toolchain image** (DockerImages `f91faba`) so
   `COREPACK_HOME` moves under the home overlay. modern-app rebuilds with it.
4. **Sync the IoTSupport environment.** Only now — `config.yaml` already
   references the two catalog keys, and a `secrets:` entry pointing at a key that
   does not exist yet may break pod start-up.

Until step 3 lands, every pnpm command needs `COREPACK_HOME=$HOME/.corepack`
prefixed. **Nothing in the repo works around this**, deliberately.

### Filed as triage cards

- [#250](https://trello.com/c/NuD8yceK) — cexec exposes every pod secret via the
  process command line.
- [#251](https://trello.com/c/uqcnyDoH) — let toolchains declare their own
  homeOverlays.

---

## Lessons for the skill

Ordered by how much time each would have saved.

### 1. "Do the tests need service X?" cannot be answered from the test code alone

The skill's inventory step led to checking pytest fixtures and grepping the E2E
tests for the service name. Both said Keycloak was optional — every setting
defaulted to `None`, backend conftest used fake `auth.example.com` values, and
the frontend tests had zero `KEYCLOAK` hits. On that basis the operator was
advised to skip it. **Wrong**: the Playwright suite drives the *real* backend,
and creating a device creates a Keycloak client. 70 of 130 E2E tests failed.

The reliable signal was in the Jenkinsfile all along: **every env var the CI job
injects is load-bearing for some suite.** A greenfield homelab CI job does not
carry a Vault lookup for decoration.

Proposed skill change — in step 2 (Derive the target configuration), add:

> Treat the CI job's injected environment as the authoritative dependency list.
> For each variable, find the suite that needs it before concluding it is
> optional. An E2E suite that boots the real application depends on everything
> the application depends on, regardless of what the unit-test fixtures stub out.
> Grepping the E2E tests for the service name proves nothing — they exercise it
> through the app.

### 2. Deleting "docker cruft" needs a consumer check first

`backend/scripts/args.sh` looked like pure Docker chain (it defined `NAME` and
`ARGS` for `docker run`, and was sourced by `stop.sh`). It was also sourced by
`testing-server.sh`, which Playwright launches per worker. Deleting it made all
130 E2E tests fail at 1ms with `process exited before ready (code=1)` — under
`set -euo pipefail` a missing `source` is fatal.

Proposed skill change — in step 6 / the kaniko porting recipe:

> Before deleting any script in the docker chain, grep the whole repo for its
> filename. These files are often `source`d by test and dev-server scripts for a
> port number or project name, far from anything docker-related. Delete the
> docker-specific *content*, keep whatever else is consumed — inline it at the
> remaining call site rather than resurrecting the file.

### 3. `.dockerignore` is per-context, and CI hides the difference

The repo-root `.dockerignore` excluded `node_modules`, but each component is its
own kaniko context and neither had one. Invisible in CI (fresh clone, nothing to
ignore); in a dev pod the frontend's `COPY . .` would have overwritten the
image's freshly installed dependencies with 185M of host `node_modules`.

Proposed skill change — in the kaniko recipe:

> `.dockerignore` is read from the build context root, not the repo root. When
> the context is a subdirectory, check that subdirectory has its own — and note
> that CI builds from a clean clone, so a missing one is invisible there and only
> bites in the dev environment, where build outputs and dependencies exist.

### 4. Local image-build scripts must not default to the deployed tag

The ported `build-image.sh` defaulted to `:latest` — the same tag Jenkins
publishes and the deployment tracks. A developer verifying a local build would
have silently overwritten the deployed image.

Proposed skill change — in the kaniko recipe:

> Default local build scripts to a non-deployed tag (`:dev`). Jenkins owns
> `:latest` and the numbered tags; a local build must never be able to clobber
> them by accident.

### 5. Dev-runner porting: check the wrapper's own toolchain, and poetry nesting

The skill says "prefix each Procfile line with its toolchain's `cexec`; the
honcho/dev.py wrapper itself runs in the dev container." That assumption does not
hold: **the dev container has `python3` and `node` but no poetry and no honcho.**
Since all three services needed the same toolchain, the working shape was the
inverse — run honcho *inside* the toolchain via cexec, and leave the Procfile
lines bare.

That then exposed a second, repo-level bug: honcho runs from the root project's
poetry venv, children inherit `VIRTUAL_ENV`, so the backend's `poetry run` reused
the root venv and crashed with `ModuleNotFoundError: paste`. Fixed with
`env -u VIRTUAL_ENV -u POETRY_ACTIVE` on that Procfile line.

Proposed skill change — replace the Procfile guidance with:

> Check what the wrapper itself needs before deciding where it runs — the dev
> container has no language toolchains. If every service uses one toolchain, run
> the process manager inside it via cexec and leave the Procfile lines bare; only
> split per-line when services genuinely need different toolchains. In a
> multi-project poetry repo, also clear `VIRTUAL_ENV`/`POETRY_ACTIVE` per line, or
> nested `poetry run` silently reuses the parent's venv.

### 6. A repo pinning `packageManager` breaks the frontend toolchain

`corepack` honours `packageManager`, and the toolchain baked one pnpm version
into a root-owned `COREPACK_HOME`. Any repo pinning a different version fails
setup with "Failed to create cache directory". Fixed in the image
(DockerImages `f91faba`) rather than worked around in the repo.

Proposed skill change — add to step 2 as a known toolchain gap:

> Check `packageManager` in package.json against the pnpm the frontend toolchain
> bakes. A mismatch is a toolchain-image fix, never a repo workaround.

### 7. Verify the whole chain, not just the suites

`kc project setup/build/test` going green did not mean onboarding was done. The
kaniko builds, the dev runner, and `kc project lint` were each still broken, and
each surfaced a distinct real defect.

Proposed skill change — in step 7, make the exit checklist explicit:

> Green means all of: `kc project setup`, `build`, `test`, **`lint`**, each
> ported image build actually executed once, and the dev runner booted with every
> service answering. Anything not executed is not verified.

### 8. Reference-repo commits are not a licence to fix reference-repo code

`kc project lint` was red on 3 pre-existing ruff errors. Tempting to `ruff --fix`
while in there — but CLAUDE.md makes the orchestrator not edit application code
ad hoc. Onboarding's remit is the environment, plus repairing regressions
onboarding itself caused.

Proposed skill change — in the close-out:

> Distinguish "broken by onboarding" (fix it, say so) from "already broken"
> (report it, leave it). A red `lint` gate that predates the migration is a
> finding for the operator or `/dev:onboard`, not a licence to edit product code.

---

## Environment facts (candidates for references/catalog.md)

- Pod containers share a network namespace — a port bound in a tool sidecar is
  reachable on `localhost` from the dev container.
- `cexec` propagates termination: killing the local client stops the sidecar
  process (measured with a heartbeat file). Long-running processes can be managed
  through it.
- Env vars exported in the dev container **are** mirrored through cexec
  (`COREPACK_HOME` verified); the denylist is narrower than it sounds.
- The dev container has `python3`, `node`, `bao`, `kubectl` — but **no poetry,
  no honcho, no gh** (`GH_TOKEN` is set, so use the REST API via curl).
- `minio` sidecar credentials are `minioadmin`/`minioadmin`. Worth adding to the
  catalog file — the code defaults in this repo (`admin`/`password`) did not
  match, and that is a guaranteed first failure.
- `postgres` accepts `postgres`/`postgres`; database creation is the repo's job
  (the sidecar starts empty).
- `opensearch` answers on 9200 and reports green with no setup.
- Home overlays are separate ZFS datasets mounted over `/home/ubuntu/<dir>`; an
  overlay **masks** anything the image baked at that path, so overlay-and-bake do
  not compose.

---

## Known-red, pre-existing, not caused by onboarding

`kc project lint` fails on 3 ruff errors, last touched by the
architecture-producer commits and untouched by any onboarding commit:

- `app/__init__.py:3` I001 import block unsorted
- `app/__init__.py:10` F811 `ProxyFix` imported twice — a literal duplicate line
- `scripts/arch-validate.py:55` UP015 unnecessary `"r"` mode argument

All ruff-autofixable. CI never caught them: `run-suite` runs pytest + Playwright
only, so ruff was never a gate before `kc project lint` existed. Needs a slice,
or `/dev:onboard` negotiating the `lint:` verb.

## Not verified

Real terminal Ctrl-C against `scripts/dev.py`. It ignores SIGINT by design and
relies on the terminal delivering it to honcho through the PTY; a scripted signal
is not equivalent, so this needs a human at a terminal. Services start, log
correctly, and cexec termination propagation is proven — but the Ctrl-C path
itself is untested.

## Left for /dev:onboard (step 9)

- `.claude/commands/*`, `.claude/agents/*`, `backend/.claude/agents/*`,
  `frontend/.claude/agents/*` — in-repo copies of the pre-plugin workflow.
- `tools/ai_workflow/claude_session.py`, `codex_exec.py`.
- `scripts/preflight.py` + `scripts/build-all.py` — per-repo preflight, now
  duplicated by `kc project setup`/`build`. **Still call bare `poetry`/`pnpm`, so
  they do not work in-pod until retired or cexec-prefixed.**
- `.claude/commands/{triage,run-slice}.md` reference the deleted
  `send_message.py`.
- The quality tooling (`tools/code_health/`, `.codehealthignore`).
- CLAUDE.md contract lines + diet; spec-repo scaffolding (repo exists, empty).
