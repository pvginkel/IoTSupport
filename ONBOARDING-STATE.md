# KubeCoder onboarding — state & lessons learned

Onboarding is **green and closed out** (see "Status"). The "Lessons for the
skill" have been folded into `skills/onboard/SKILL.md` and
`references/catalog.md` in KubeCoderConfig and pushed (this session's deltas in
commit `de6f5f6`). This file is deliberately **kept, not deleted**: it is the
handoff to the KubeCoder agent (the `cexec` doc below) and the running record for
`/dev:onboard`.

---

## For the KubeCoder agent

**Document `cexec`'s argument handling in `/etc/claude-code/CLAUDE.md`.** Its
absence cost this session real time. `cexec <toolchain> <command…>` behaves like
`ssh <host> <command…>`: it joins its trailing arguments into one string and runs
that string through a shell in the sidecar, at the working directory the caller
is in (it mirrors the dev-container cwd). So:

- Pass a normal command line: `cexec modern-app poetry run pytest`,
  `cexec frontend pnpm build`.
- **Do not wrap it in `sh -c '…'`.** Exactly like `ssh host sh -c '…'`, the
  wrapper collapses — the args are re-joined and re-parsed, so
  `cexec modern-app sh -c 'ls /unknown'` runs a bare `ls` in the cwd (the `sh -c`
  and `/unknown` get swallowed as the shell's `$0`).
- Quoting is parsed **twice** (caller shell, then sidecar shell); arguments with
  spaces or globs need quoting that survives both passes.
- For another directory or a compound command, pass a single quoted string —
  `cexec modern-app 'cd frontend && pnpm build'` — or change the caller's own cwd
  first, since cexec mirrors it.

Other platform follow-ups this migration surfaced (yours to action in KubeCoder /
KubeCoderConfig):

- Triage [#251](https://trello.com/c/uqcnyDoH) is **shipped** (Wave 2 [100]) —
  close it.
- [#250](https://trello.com/c/NuD8yceK) (cexec exposes pod secrets on the process
  command line) is still open.

---

## Status

Both step-7 blockers from the prior session are cleared by the KubeCoder Wave 2
deploy (headlines in `tmp/release-notes.md`), so former pending items 1–4 (seed
OpenBao, deploy chart, rebuild image, sync) are all done — the environment is on
the target image with real secrets:

- **Rebuilt toolchain image not picked up** → [100] toolchain images with
  floating tags now pull `Always`. The pod runs the rebuilt `modern-app` image:
  `COREPACK_HOME=/home/ubuntu/.corepack`, and `.corepack` is a live ZFS overlay
  with cached pnpm.
- **Restart failed because the secret did not exist** → [099] a missing catalog
  secret now warns instead of failing pod start-up, and the Keycloak admin
  secret is materialised as real env vars in the pod.
- **[#251] "let toolchains declare their own homeOverlays"** shipped as [100].
  The `frontend` and `modern-app` catalog toolchains now declare
  `homeOverlays: [.corepack]` on their own entries (confirmed in the live
  `kubecoder-controller-config`), and the controller merges built-in + repo +
  per-toolchain overlays. Removed the now-redundant repo-level declaration from
  `config.yaml` (commit 8b8ac85).

### Done

1. **Green.** `kc project setup | build | test` all pass on the 5Gi pod — the
   first green under the real ESO-materialised Keycloak secret path. Counts match
   Jenkins #124: **696 backend pytest + 130 Playwright = 826**, `modern-app`
   restarts=0.
2. **modern-app right-sized 3Gi → 5Gi.** The full-stack E2E (backend + SSE +
   frontend per Playwright worker, + chromium) plus backend pytest in one sidecar
   peaked at **~3.3Gi** (3,486,273,536 B) and OOMKilled at 3Gi mid-suite — the
   prior session's "green" was a truncated run. Bumped in HelmCharts
   `charts/kubecoder/values.yaml` (commit `5fbe659`, pushed); operator deployed +
   restarted; re-verified. 5Gi leaves ~1.8Gi headroom.
3. **Skill fold-back pushed** to KubeCoderConfig (commit `de6f5f6`): overlays are
   toolchain-declared (lesson 10), modern-app 5Gi (lesson 11), workspace tasks
   incl. Build All + Procfile.dev-gated Dev Services (lesson 9), slice-099 secret
   softening, catalog snapshot refreshed.

### Remaining

1. `kc project lint` still red on the same 3 pre-existing ruff errors — see
   "Known-red"; **not** onboarding-caused; left for `/dev:onboard`.
2. **`/dev:onboard` (step 9)** not yet run — the full-tier AI-workflow handoff.
   Needs the dev plugin installed. See "Left for /dev:onboard" below.
3. **KubeCoder agent** to document `cexec` (see top) and make any further
   KubeCoder / KubeCoderConfig changes.

### Still open, filed as triage cards

- [#250](https://trello.com/c/NuD8yceK) — cexec exposes every pod secret via the
  process command line. (Still open.)
- [#251](https://trello.com/c/uqcnyDoH) — let toolchains declare their own
  homeOverlays. **Shipped as Wave 2 [100]; close this card.**

---

## Lessons for the skill

Ordered by how much time each would have saved.

> **Folded into KubeCoderConfig and pushed** — lessons 1–8 were already folded
> upstream; this session's 9–11 plus the Wave-2 corrections are in commit
> `de6f5f6`. Kept here as the migration record; nothing here is pending.

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

### 9. One workspace-level Claude task, not per-folder tasks.json

Step 6 says to drop a `kc session` task into each internal sub-project's
`.vscode/tasks.json`. That backfires once this repo is opened as a *sibling*
folder inside another repo's workspace: every per-folder task surfaces, so you
get duplicate "Claude" tasks. Put a single session task in the `.code-workspace`
file's own `tasks:` block instead — workspace-scoped tasks appear only for their
own workspace, so a repo loaded as a sibling contributes none. Shape now live in
`IoTSupport.code-workspace`: one `Claude` task, `kc session --ui --attach`, cwd
`/work`.

Proposed skill change — replace step 6's per-folder `tasks.json` instruction:

> Put one Claude task in the `*.code-workspace` `tasks:` block (cwd `/work`,
> `kc session --ui --attach`), not a per-folder `.vscode/tasks.json`. Per-folder
> tasks duplicate when the repo is opened as a sibling folder in another
> workspace; a workspace-scoped task shows only for its own workspace. This
> trades per-folder session scoping for exactly one Claude task per workspace.

### 10. Do not manage toolchain home-overlays from the skill or config.yaml

As of Wave 2 [100], catalog toolchains declare their own `homeOverlays:` and the
controller merges built-in + repo + per-toolchain lists. The skill must no longer
tell a repo to add a toolchain's cache dir (`.corepack`) to `homeOverlays:`; this
migration's `config.yaml` entry for it is removed (commit 8b8ac85). Assume
toolchains define their own overlays.

Proposed skill change:

> Step 2: delete the "add `.corepack` to `homeOverlays`" known-gap note. A repo's
> `homeOverlays:` is only for paths *its own* work needs to persist — never a
> toolchain's cache. This supersedes the frontend/modern-app overlay edits
> drafted below (corrected inline there).

---

## references/catalog.md — exact edits needed

**The `frontend` entry is now factually wrong.** DockerImages `f91faba` removed
the `corepack prepare pnpm@latest --activate` bake, so "corepack-pinned pnpm" no
longer describes the image. Apply these edits when folding this back.

### Toolchains — replace the `frontend` bullet

Corrected for Wave 2 [100] — the toolchain declares the overlay itself now, the
repo adds nothing:

> - `frontend` — Node.js 24 with corepack (no pnpm version baked in), plus
>   Playwright OS dependencies; neither pnpm nor the browser bundles are baked,
>   both are fetched per project. `COREPACK_HOME=/home/ubuntu/.corepack`, so
>   corepack installs whatever `packageManager` a repo pins. **The toolchain
>   declares `homeOverlays: [.corepack]` on its own catalog entry** (the repo
>   does not add it), and pulls `Always`. 3Gi memory for headless-browser
>   headroom.

### Toolchains — append to the `modern-app` bullet

> Declares `homeOverlays: [.corepack]` itself, same as `frontend`; the selecting
> repo adds nothing.

### Services — replace the `postgres` and `minio` bullets

> - `postgres` — PostgreSQL 18, dev-tuned (small buffers, few connections). Port
>   5432 (tcp). Credentials `postgres`/`postgres`; starts with no application
>   database, so creating it is the repo's `setup:` job.
> - `minio` — MinIO, S3-compatible object store. Ports 9000 (API, http) and 9001
>   (console, http). Root credentials **`minioadmin`/`minioadmin`** — check these
>   against the app's defaults, a mismatch there is a guaranteed first failure.

### Add a new section at the end

> ## Environment facts
>
> Behaviour that is not in the manual and cost time to establish:
>
> - Pod containers **share a network namespace** — a port bound inside a tool
>   sidecar is reachable on `localhost` from the dev container, and vice versa.
> - `cexec` **propagates termination**: killing the local client stops the
>   process in the sidecar, so long-running processes can be supervised through
>   it (verified with a heartbeat file, not assumed).
> - Env vars exported in the dev container **are** mirrored through `cexec` —
>   the denylist is narrower than the help text suggests.
> - The dev container has `python3`, `node`, `bao`, `kubectl` — but **no poetry,
>   no honcho, no gh**. `GH_TOKEN` is set, so reach GitHub via the REST API with
>   curl.
> - Home overlays are separate ZFS datasets mounted over `/home/ubuntu/<dir>`.
>   An overlay **masks** whatever the image baked at that path, so
>   overlay-and-bake do not compose — a toolchain wanting persistent cached
>   content must let the runtime populate it.

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
