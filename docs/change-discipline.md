# Change discipline

The rules every code change in this repo obeys, in both components. This is the doc `.aiworkflowrc`
names as `design_philosophy`: it is handed to every `code-writer`, `code-reviewer`, `plan-writer`
and `plan-reviewer` the pipeline dispatches, and it is what a reviewer cites when sending work
back. It states the rules; the design they apply to lives in each component's `docs/`.

## Clean breaking changes

Greenfield, single-tenant, and the backend follows the BFF pattern — it serves this frontend and
nothing else. So when an interface between them changes, **fix the callers**: change both sides in
the same slice and do not add a shim, an adapter, a deprecated alias, or an overload that keeps the
old shape alive beside the new one. Delete replaced endpoints and components outright.

**Two boundaries are not free, and they are the ones that leave the repo:**

- **`/iot/*`** — config, firmware, firmware-version, provisioning and coredump upload, consumed by
  ESP32 firmware already running in the field. That firmware is not redeployed in lockstep with
  this repo, so a breaking change there bricks devices until they are reflashed.
- **`/pipeline/*`** and the MQTT rotation notifications — consumed by CI jobs and by the devices'
  MQTT clients, both outside this repo. `/pipeline/upload.sh` and `upload.ps1` are downloaded and
  run by other repos' pipelines.

Inside the BFF boundary, break freely. At those two, keep the old shape working, or plan the
migration explicitly as part of the slice.

## No tombstones

Delete replaced code completely. No "moved to X" comments, no stub functions that forward, no
deprecated aliases, no commented-out blocks, no dead re-exports, and no migration hints in error
messages. The same applies to prose: when a convention is superseded, **rewrite the doc** rather
than appending a note that the old rule no longer holds. Git history is the record of what things
used to be; the working tree is only ever a statement of what is true now.

## No defensive coding

Fail fast and fail loudly. No `try`/`except` that swallows an error, no drop-the-bad-input-and-keep-
going path, no null-guard for a condition the schema or the framework already prevents, no silent
fallback, and no retry, cache or scheduled sweep added without a real observed failure to point at.
On the backend, raise the typed exception from `app.exceptions` and let `@handle_api_errors` turn it
into an HTTP response; on the frontend, use the generated hooks and the centralized error handling
rather than ad hoc `fetch` and bespoke toasts.

**Boundary validation is the exception, and it is deliberate.** Requests arriving at the API,
payloads from devices, and firmware uploads all cross into the system and are validated at the
edge — that is the feature, not defensiveness. Trust what the system has already established.

The one place errors are deliberately swallowed is the second half of the S3 delete rule: the row
is committed first, then the object is deleted best-effort, because an orphaned blob is harmless
and a dangling reference is not. See `backend/CLAUDE.md` for both golden rules.

## Testability is critical

Every change ships with a test. A feature without one is incomplete, and "I verified it by hand" is
not a substitute — the point of the test is that it runs again next time.

| Component | Suite | Runs as |
|---|---|---|
| `backend` | pytest, under `backend/tests/` | `kc project test --project backend` |
| `frontend` | Playwright E2E, under `frontend/tests/` — it boots the real Flask backend per worker | `kc project test --project frontend` |
| `root` | none: orchestration tooling and the dev stack — green by definition | — |

A UI change is not done until its instrumentation ships with it: Playwright specs wait on emitted
`ListLoading`/`Form` events and assert real backend state, never `page.route` mocks. A change that
genuinely cannot be covered by either suite is a change whose testability problem is the first
thing to solve — say so and fix the seam rather than shipping it uncovered.

## Never hand-edit generated artifacts

`frontend/src/lib/api/generated/` is the OpenAPI client, emitted from the backend's spec by
`pnpm generate:api` (repo-wide: `scripts/regenerate-openapi.py`), and `src/routeTree.gen.ts` is
emitted by `tsr generate`. Both are git-ignored and rebuilt as the first steps of `pnpm build`, so
a hand-edit is silently discarded rather than caught. **Change the backend schema and regenerate**
— an API-shape change is a backend change plus a regeneration, in the same slice.

## This is a public repo

`github.com/pvginkel/IoTSupport` is world-readable. `github.com/pvginkel/IoTSupportSpecs`, where
the slices live, is private — do not assume a fact is publishable because a slice stated it. No
secrets, credentials, tokens, internal hostnames or IP addresses, and no non-public names, in code,
tests, fixtures, comments or commit messages. Keycloak coordinates come from the environment
(`backend/scripts/generate-dev-env.sh` and the injected secrets), never from a literal.
