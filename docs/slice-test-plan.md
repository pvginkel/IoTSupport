# Slice testing strategy

How a slice is proven once its phases are merged. This is the doc `.aiworkflowrc` names as
`test_phase.strategy`: the run loop's test phase is "read this and execute it", and nothing else
names it. Read it top to bottom and do what it says.

## What this phase proves, and what it does not

**Verification here is local.** This repo has exactly one deployment — production, on the `prd`
cluster — and no dev instance to roll. So the test phase deploys nothing and verifies nothing
against a deployed instance. It runs the suites tree-wide and boots this repo's own dev stack in
this environment, from the merged working tree.

**The push deploys to production.** `Jenkinsfile` runs a validation Job, then builds both images
with `helmCharts.kaniko` (`backend/Dockerfile` → `iot-support`, `frontend/Dockerfile` →
`iot-support-frontend`), then `cicd.helmDeploy()`. There is no DTAP: a green build on `main` *is*
the release. That is the repo's standing behaviour, not something this phase controls, and it is
the whole reason for the ordering below — **everything is verified before the push, because after
the push it is live.**

There is no `devlock`: with no dev instance, nothing contends.

## 0. Preconditions

The driver has ff-merged every code phase into the base branch. Confirm the tree is clean
(`git status --short`) before starting — a dirty tree here means an earlier phase left something
behind, and that is a finding, not something to tidy away.

`kc project` is cwd-bound: run every verb below from the repo root.

## 1. The suites, tree-wide

```bash
kc project build      # frontend: pnpm build (generate:api, routes, check, vite build, verify)
kc project test       # backend: pytest. frontend: Playwright, which boots the Flask backend per worker
kc project lint       # backend: ruff, mypy, vulture. frontend: pnpm check
```

`root` declares no `build:` and no `test:` — it is the orchestration tooling and the dev stack, and
that is a decision, not a gap. `backend` declares no `build:` either: its artifact is
`backend/Dockerfile`, which CI builds.

Build and test must be green. `kc project build` is also what preflight demands, so a red build
here means the slice never should have reached this phase.

No gate in this repo is known red, and the suite has no known flake: a failure in `kc project
build`, `test` or `lint` is this slice's, and reporting it as pre-existing needs evidence from
HEAD, not an assumption. One mechanical caveat: **`kc project lint` stops at the first failing
statement**, so a red lint tells you nothing about the statements behind it — read it by running
the statements individually (`cexec modern-app poetry run ruff check .`, `... mypy .`, `...
vulture app/ vulture_whitelist.py --min-confidence 80` from `backend/`, `... pnpm check` from
`frontend/`).

## 2. The live check: boot the dev stack

`scripts/dev.py` runs honcho over `Procfile.dev` inside the `modern-app` sidecar and starts all
three services on the ports `.kubecoder/config.yaml` publishes: **frontend :3100**, **backend
:3101**, **SSE gateway :3102**.

Do this whenever the slice touched `backend/` or `frontend/`. A docs-only or tooling-only slice
skips to step 3 and says so.

`scripts/dev.py` ignores SIGINT and SIGTERM by design and expects a terminal to deliver `^C`
through its pty. `kill` on it orphans the whole process tree and leaves 3100-3102 held. The
deterministic headless form is a fifo held open on a spare fd:

```bash
rm -f /tmp/devfifo; mkfifo /tmp/devfifo
exec 9<>/tmp/devfifo
scripts/dev.py < /tmp/devfifo > /tmp/dev-run.log 2>&1 &
DEVPID=$!                                    # the only handle you need — never match on a pattern

for i in $(seq 1 75); do sleep 4
  curl -sf -o /dev/null --max-time 5 http://localhost:3100/ \
    && curl -sf -o /dev/null --max-time 5 http://localhost:3101/health/healthz && break
done
```

Then probe both surfaces, and whatever else the slice touched:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3100/                 # SPA shell
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3100/api/devices      # through the dev proxy
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3101/health/healthz
curl -s               http://localhost:3101/health/readyz                       # read the body
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3101/metrics
```

All answer `200`; `readyz` reports `"ready": true` with `database.connected` and
`sse_gateway.reachable` both true — which is what confirms postgres and the gateway on :3102, since
neither suite exercises them. The proxied `/api/devices` is the one probe that proves the frontend
and backend are talking, so it is not optional.

Stop it by sending `^C` down the fifo and waiting on the pid you captured:

```bash
printf '\003' >&9
wait $DEVPID            # exits 130; never `kill $DEVPID`, never `pkill -f dev.py`
exec 9>&-; rm -f /tmp/devfifo
```

Then confirm 3100-3102 are closed and `git status --short` is clean — `logs/` is git-ignored but
the tree must go back to how it started.

## 3. Check off `verification.json`

Mark each acceptance criterion with the evidence that settled it — the command run and what it
returned, or the surface loaded and what was seen. A criterion nothing in steps 1-2 exercised is
not "passed by inspection"; it is either an untested criterion (a finding) or one whose check
belongs in this doc and is missing from it.

## 4. Push, then follow the build it triggers

Pushing is this phase's job — the driver ff-merges locally and never pushes a code phase, then
checks before the doc phase that every repo in `state.json`'s `bases` reached `origin`. Push each
one, honouring any repo named in `plan.md`'s `## Push holds`.

The push triggers Jenkins job **`IoTSupport/IoTSupport`**. Follow it in the foreground:

```
mcp__jenkins__getJob   jobFullName="IoTSupport/IoTSupport"
                       tree="lastBuild[number,result,building,url],inQueue"
mcp__jenkins__getBuild jobFullName="IoTSupport/IoTSupport" buildNumber=<n>
                       tree="number,result,building,duration"
```

Poll `getBuild` until `building` is false, then read `result`. The Jenkins **MCP tools are the way
that works here**: the anonymous REST API (`.../lastBuild/api/json`) answers **403**, and this
environment holds no Jenkins token. A session without the MCP tools reports the build number and
its URL and leaves the verdict to the operator rather than guessing at it.

Unlike a repo with a dev tier, this is **not only** a did-I-break-CI check: this build is the
release. A red build is a blocking finding, and note *where* it went red — the pipeline fails the
build on a non-zero validation exit and never enters the image or deploy stages, so a validation
failure means nothing was redeployed and production is still on the last green build's images.

## Findings

Blocking findings come back as appended phases. Sub-bar findings go in the close-out report for the
operator to triage. A live check that cannot be run at all — a service down, the sidecar
unavailable — is reported as *not verified*, never as passed; the phase is allowed to end with a
criterion unproven and said so, and is not allowed to end with one assumed.

## The operator gate

The operator's gate is the close-out report, after the run. Production has by then already taken
the change, which is what makes steps 1-2 the real gate and why they precede the push.
