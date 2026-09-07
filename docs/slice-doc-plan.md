# Slice documentation plan

Which documentation surfaces a shipped slice brings up to date, and the rules for each. This is the
doc `.aiworkflowrc` names as `doc_phase.plan`: the run loop's doc phase is "read this and execute
it", working from the whole slice's merged diff.

Work the diff, not a checklist. Each surface below is owed an update only when the slice's changes
actually reached it.

## The surfaces

### 1. The `docs/` that owns the change

Three scopes, and the choice between them is about *what* changed, not which files moved:

| Scope | Owns |
|---|---|
| root `docs/` | cross-cutting and system-level material: how the two components fit together, the dev stack, the pipeline's own procedure docs (this file, `slice-test-plan.md`, `change-discipline.md`) |
| `backend/docs/` | the Flask API — the domain model (`product_brief.md`), designs such as `device_provisioning_design.md`, and the decision records under `decisions/` |
| `frontend/docs/` | the SPA — `product_brief.md`, `features.md`, and the contributor hub under `contribute/` |

A slice that changed the **device-facing or pipeline-facing contract** (`/iot/*`, `/pipeline/*`,
the MQTT rotation notifications) changed a system-level thing whichever component's code moved, and
its design belongs at the root. A slice that only moved one component's internals documents itself
in that component's `docs/`.

`frontend/docs/contribute/` is the live, maintained doc set — `index.md` is its hub and every page
is linked from it. A slice that changed how the suite is written, how instrumentation is emitted,
or how the app is run locally updates the page that owns that topic and leaves the hub's links
intact. The root `docs/` is currently only the three procedure docs; seed a topic there when
**this** slice's design needs a home, not to fill it out.

### 2. The decision records

`backend/docs/decisions/` is a numbered ADR folder. If the slice made or changed a decision worth
outliving the code, add or update a record there and link it from the design doc that carries the
detail. Depth goes in the doc, not the record.

### 3. The reader-facing READMEs

`backend/README.md` and `frontend/README.md` are the human entry points, and both are **known
stale** — they still describe the filesystem-config-file era (no database, ports 3200/3201/5000).
That is a reported finding, not this phase's project. Fix what your slice's diff actually
contradicts; do not open a wholesale rewrite from inside a doc phase.

### 4. `CLAUDE.md` and `AGENTS.md`

The root `CLAUDE.md`, and `backend/AGENTS.md` / `frontend/AGENTS.md` (each with `CLAUDE.md`
symlinked onto it — edit the `AGENTS.md`, never the link). Kept to about one screen and holding
each fact once. A slice rarely touches them; when a new standing rule genuinely belongs there,
something else moves out to a `docs/` topic doc rather than the file growing. Nothing the pipeline
reads by machine goes in them — that is `.aiworkflowrc`.

## What this phase does not touch

- **`backend/docs/features/` and `frontend/docs/features/`** — per-feature plans, plan reviews and
  execution reports from the pre-plugin workflow. They are a frozen audit trail of what was decided
  when, not a description of the system now. Leave them, including their references to commands
  that no longer exist.
- **`docs/architecture/architecture.yaml`** in either component — the federated Architecture-as-Code
  artifact, owned by the operator's `update-architecture` agent and validated by
  `Jenkinsfile.architecture`. Nudge in the close-out when a slice changed something structural; do
  not hand-edit it here.

## What "up to date" means here

**State the design as it is**, as implemented, not as the slice authored it. Where the
implementation diverged from the plan, the doc describes what shipped. No changelog entries, no
"as of slice NNN", no tombstones for superseded conventions — rewrite the doc instead.

**Ground every claim in the shipped source.** A doc sentence that cannot be checked against the
merged tree does not go in. That bites hardest on the two stale READMEs: copy nothing forward from
them without checking it.

## Gates

Documentation changes do not compile, but they do live beside code:

```bash
kc project build       # unchanged and green — the doc phase must not have moved code
```

Run it from the repo root (`kc project` is cwd-bound). Check relative links resolve, including the
cross-scope ones and `frontend/docs/contribute/index.md`'s list. Then commit — this repo and the
spec repo separately, since they are separate git repos.

## When there is little to do

A slice that changed no design, no convention, and no reader-facing surface owes nothing here, and
saying so plainly is the correct outcome. Do not invent doc work to fill the phase; an index entry
for a doc nobody needed is worse than no entry.
