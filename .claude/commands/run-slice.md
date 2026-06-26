# Run Slice

Run the implementation workflow for a slice. Argument: the slice number (e.g., `001`).

## What this skill does

You are the orchestrator. You drive per-subproject dev agents through the slice workflow by invoking `claude` via the session manager script. The session manager handles environment setup, session tracking, and state persistence automatically.

**Session manager:** All `claude` invocations go through `python3 tools/ai_workflow/claude_session.py`. No need to manually `unset CLAUDECODE` or `cd` into project directories. The session manager takes a `--project` parameter with the following supported arguments: `root`, `backend`, and `frontend`.

**Prompt delivery:** Prompts are delivered via file or stdin — never as inline shell arguments (to avoid shell escaping issues with backticks, quotes, and special characters).

```bash
# Preferred for long/complex prompts: write a file, pass it with --prompt-file
python3 tools/ai_workflow/claude_session.py start --project backend --timeout 7200 --prompt-file /tmp/prompt.txt --response-file /tmp/response.txt

# Fine for short prompts: heredoc via stdin
python3 tools/ai_workflow/claude_session.py start --project backend --timeout 7200 <<'EOF'
Please read the brief and come back with informed questions.
EOF
```

**Response handling:** The session manager streams progress to stderr and writes the agent's final response to stdout (or to a file via `--response-file`). Use `--response-file` when running in the background so you can read the response after completion.

**Push notifications:** Use `python3 tools/ai_workflow/send_message.py --title "Slice <NUMBER>" "<message>"` to notify the user. Send a notification when:
- The slice completes successfully.
- The slice is blocked and needs user attention (agent failure, test failures requiring user input, missing work reported by a downstream agent, significant API contract gaps).

Do **not** notify for routine progress. Only notify when the user needs to act or when the workflow has reached its end.

## Slice file formats

Slices are authored by the `/write-slice` skill. The layout:

```
slices/<SLICE_DIR>/
  overview.md, acceptance_criteria.json, api_contract.json,
  grounding_check.md, ux_design.md, verification.json  ← orchestrator-owned
  backend/brief.md, frontend/brief.md                  ← dev-agent-owned folders
  (one folder per subproject that has work in this slice)
```

The files the runner reads:

- **`acceptance_criteria.json`** — testable conditions with `id` (prefixed by subproject — e.g., `BE-`/`FE-`), `area`, and `description`. The criteria definition is immutable here; verdicts live exclusively in `verification.json` (Step 0c onward) so AC state is tracked in one place.
- **`api_contract.json`** — structured API spec with `endpoints` (id, method, path, status_codes, key fields, `verified` flag), `schema_changes`, and `removals`.
- **`backend/brief.md` / `frontend/brief.md`** — scoped task descriptions for each dev agent. Determine which agents need to run based on which of these files exist.
- **`overview.md`** — what the slice delivers, dependencies, scope.
- **`ux_design.md`** (optional) — UX guidance for slices with non-trivial UI work.
- **`grounding_check.md`** — per-brief record of verified `file:line` citations and "current state" claims produced by `/write-slice`'s grounding pass.

When sending briefs to agents, reference the relevant acceptance criteria and API contract IDs so the agent knows exactly which conditions and endpoints its work must satisfy.

## Procedure

### Step 0: Identify the slice and verify build/test infrastructure

Resolve the argument to the slice directory under `../IoTSupportSpecs/slices/`. For example, argument `001` resolves to `../IoTSupportSpecs/slices/001_<name>/`.

Read all documents in the slice directory. Determine which agents need to run based on which `<subproject>/brief.md` files exist.

**Pre-flight: verify build and test infrastructure.** Before starting any agent, confirm the environment is in a clean buildable state AND that tests can actually run. Code that hasn't been tested is not done, and agents inherit whatever broken environment you hand them — so catch environment drift before they start, not after.

Run `python3 /home/pvginkel/source/IoTSupport/scripts/preflight.py` from the repo root before dispatching any dev agent. It bundles the checks that must pass before any agent starts:

- **Full repo build** (`scripts/build-all.py`) — root `poetry install`, `backend` `poetry install`, `frontend` `pnpm install` (frozen lockfile, standalone — the frontend is not a pnpm workspace member), and `frontend` `pnpm build`. Catches dependency drift and broken builds across both subprojects.
- **Backend test collection** (`poetry run pytest --co`) — confirms the backend test harness can collect tests without import or environment errors (the IoTSupport backend bootstraps its test DB from fixtures, so there is no separate `cli prepare` step).

The script is silent on success; on failure it dumps the buffered output of every check plus the failing step's details.

```bash
python3 /home/pvginkel/source/IoTSupport/scripts/preflight.py
```

**If any pre-flight check fails:** do **not** try to work around it — fix the root cause. Notify the user (include the pre-flight output so they can act) and **stop immediately**. Do not start any dev agent. Unverified code is worse than no code.

### Step 0b: Pre-flight review with user

After reading all slice documents and passing infrastructure checks, present a pre-flight summary to the user before starting any agent work.

1. **Work rundown.** Summarize which agents will run based on which briefs exist, with a brief description of what each will deliver (1–3 sentences per agent). Include any issue-tracker items in the Planned list tagged for this slice.
2. **High-impact decisions.** Flag decisions with significant architectural, data-model, or cross-slice implications (new DB tables, new API patterns, cross-subproject changes, irreversible migrations). Skip this section if the slice is primarily low-impact CRUD/UI work.
3. **Clarifications.** If anything is ambiguous, contradictory, or could go multiple ways, ask the user now — before any agent starts.
4. **Notify and wait.** Send a push notification and wait for the user to respond before proceeding. Do not start Step 0c until the user confirms (e.g., "go", "looks good", "proceed").

### Step 0c: Seed the verification log

Once the user confirms the pre-flight, create `../IoTSupportSpecs/slices/<SLICE_DIR>/verification.json` and seed it from `acceptance_criteria.json`. The verification log is the single source of truth for what the slice's independent verifier checks at Step 8c — items only get verified if they're in the log.

Schema (one entry per item):

```json
{
  "items": [
    {
      "id": "V01",
      "source": "ac",
      "area": "backend",
      "description": "BE-1: <verbatim AC description>",
      "verdict": null,
      "rationale": "",
      "evidence": []
    }
  ]
}
```

- `id` — sequential `V01`, `V02`, … in entry order.
- `source` — `ac` (seeded from acceptance criteria) or `qa_correction` (added in Step 1+ when you override an agent's stated direction).
- `area` — the subproject a failure routes back to. For AC entries, copy the AC's `area`.
- `description` — what must be true in the implementation. For AC entries, prefix with the AC id (e.g., `BE-1: …`) so Step 10 can map verdicts back. State the *what*, not the *why* — no opinions.
- `verdict`, `rationale`, `evidence` — left empty; the verifier fills these in.

Seed one item per AC, in order. Commit `verification.json` to the specs repo before starting Step 1.

### Step 1: Run the "leading" subproject

IoTSupport follows the BFF (backend-for-frontend) pattern: the **backend** owns the API contract and always leads. Dispatch the backend dev agent first — it defines or changes the API, then the frontend regenerates its generated OpenAPI client (Step 2) and follows. So for every slice that touches both, run `backend` before `frontend`.

Start a new session in the leading subproject:

```bash
python3 tools/ai_workflow/claude_session.py start --project backend --timeout 7200 --response-file /tmp/backend_response.txt <<'EOF'
I'm the orchestrator coordinating slice <SLICE_NUMBER>. You are the backend dev agent — your job is to implement the backend part of this slice per the brief. I'll handle everything outside the backend subproject: cross-project test suite, acceptance criteria, issue tracker, and moving the slice to completed.

Please read ../IoTSupportSpecs/slices/<SLICE_DIR>/backend/brief.md and come back with informed questions.
EOF
```

Check the exit code:
- `0` — success, read the response from `/tmp/backend_response.txt`.
- `1` — error, notify the user and stop.
- `2` — timeout, check `.claude/sessions/backend.json`. If the last invocation has `duration_ms > 0`, the agent was working — resume with a nudge. If `duration_ms == 0` or state is stale, restart.

Answer all informed questions yourself based on your knowledge of the project documentation. Be thorough and precise — you know this project deeply.

**Do not prescribe implementation details.** Your answers describe **what** needs to happen and **why**, not **how**. Do not include code snippets, pseudocode, or specific implementation patterns. The agent reads the codebase, writes the plan, and designs the implementation — that's the whole point of the workflow.

**Pick one value when the agent surfaces a tunable.** When a question asks about a numeric threshold, timer, retry count, cadence, or other tunable, give a single value in your answer — not a range, not "either is acceptable." If the agent disagrees with the value, they must argue back; "either is fine" is abdication, not delegation. Picking one value is not implementation guidance — it is a numeric requirement. If the agent had proposed a different value and you overrode it, log that as a `qa_correction` (the description names the required value); if the agent simply asked, your answer is binding and no log entry is needed.

**Ground every claim about the codebase in a verified `file:line` citation.** When an answer depends on how the code behaves today — a call graph, a dispatcher wiring, an endpoint's side effects, a hook's behavior — read the file or grep before committing the answer, and cite `file_path:line_number` in the answer itself. Do not assert code behavior from your short-term mental model. If a claim would slow the answer down to verify, say "I believe X but have not verified" rather than stating X as fact.

**Trace agent-narrated behavior boundaries against the brief, not the agent's framing.** When the agent's plan or answer narrates a behavior boundary — "metric A is exception-only," "this flag toggles only on path X," "log L is unaffected by Z," "the recovery path doesn't need to know about Y" — do not accept the framing on its own merits. For every relevant acceptance criterion, walk what the operator / user / test observes on the new code path *under the agent's stated boundary*, and compare that to what the brief requires. The failure mode this catches: an agent's narrative ("counter semantic stays exception-driven") sounds defensible in isolation but, when traced through the new path, produces an outcome the brief forbids — zero metric increments on a watchdog-driven reconnect even though the metric exists for that exact observability reason; a recovery log gated on a flag that the new clean-return path never sets; a transition pair the brief mandates that never gets emitted because each half lives behind a different gate. Plausible framing is not requirement satisfaction. Apply this on first-round answers, on revised plans, and especially when the agent's prose does the reasoning instead of the code path. If the agent's stated boundary leaves any relevant AC dangling, that is a `qa_correction`.

**Log the Q&A exchange** to `../IoTSupportSpecs/slices/<SLICE_DIR>/qa_log.md`:

```markdown
## Backend — Round N

Q: <agent's question>
A: <your answer>

Q: <agent's question>
A: <your answer>
```

Pair each question with its answer directly. Do the same for the frontend (using `## Frontend — Round N` headings). Create the file on the first write.

**Log corrections to the verification log.** When your answer overrides the agent's stated direction — the agent proposed approach A and you said no, do B because… — also append an entry to `verification.json` with `source: qa_correction`. The `description` should state what must be true in the implementation (not the discussion that led there). Use the next sequential `V##` id and the area of the agent being answered.

The bar is *direction change*. Clarifications, style preferences, picking a tunable value the agent simply asked about, and "yes that's right" confirmations do **not** go in the log — only cases where the agent was about to do something different and you turned them.

**Log deferred items.** If any Q&A exchange surfaces work out of scope for the current slice but needing future attention (a missing feature, a known limitation, a future improvement), create an entry on the issue log immediately — don't rely on the QA log alone.

**Decide whether to allow follow-up questions.** Use your judgment:
- If the questions show the agent has a good understanding and your answers are clarifications or minor tweaks, skip the follow-up round and go straight to execution.
- If the questions reveal significant gaps, confusion, or unclear scope, allow a follow-up round by ending your answer with: *"Please come back with followup questions. Do not start the implementation if you don't have any."*

**If allowing followups**, write answers to a prompt file and resume:

```bash
python3 tools/ai_workflow/claude_session.py resume --project backend --timeout 7200 --prompt-file /tmp/backend_answers.txt
```

**When ready to execute** (after answering initial questions directly, or after follow-up rounds), write the final answers plus execution instruction to a prompt file:

```bash
python3 tools/ai_workflow/claude_session.py resume --project backend --timeout 7200 --prompt-file /tmp/backend_execute.txt
```

**Keep the execute prompt tight: answers + novel caveats + closing boilerplate.** If it's in the brief, don't repeat it — no scope restatement, no constraint re-listing, no gate reminders. Novel caveats attach to your answers (e.g., "approve the contract, but audit for any deep-link callsites bypassing the cache check").

**Pick the workflow for this agent** based on the brief plus what you learned from Q&A:

- **`/minor-change`** — pattern-following work with existing precedent, no new architectural decisions, narrow diff (≤ ~200 lines / ≤ ~5 files), executable without a written plan. Examples: a verbatim mirror of a sibling change, a bug fix with a clear reproduction, a cosmetic/config tweak, adding a field that follows an established pattern.
- **`/major-change`** — anything that introduces new patterns, crosses module boundaries, or involves design decisions worth capturing in a written plan. Default to major when in doubt.

Asymmetry across agents is expected — e.g., backend major, frontend minor when the frontend mirrors a backend change.

The prompt file should end with: *"Run `/<chosen_workflow> ../IoTSupportSpecs/slices/<SLICE_DIR>/<project>/brief.md` (e.g. `/minor-change …/brief.md` or `/major-change …/brief.md`) to implement the brief. Store feature artifacts (change brief, plan files, code reviews, feature docs, and other supporting artifacts) under ../IoTSupportSpecs/slices/<SLICE_DIR>/<project>/ — that subfolder is yours. **Do not create, edit, or delete files at the slice root (../IoTSupportSpecs/slices/<SLICE_DIR>/\*.md, \*.json, or any sibling subproject folder) — those belong to the orchestrator and the other dev agents.** Commit ALL your work when done, including the feature artifacts. Run 'git status' before your final commit to make sure nothing is left uncommitted."*

Wait for the agent to complete. Do not poll for progress — the session manager streams progress to stderr. If a long time has passed (30+ minutes) and you suspect the agent may be stuck, run `git status` as a diagnostic — new or modified files in the subproject indicate the agent is actively working. On timeout (exit 2), read `.claude/sessions/<project>.json` and decide whether to resume or restart. On error (exit 1), report the failure and stop.

**On success**, finish the session:

```bash
python3 tools/ai_workflow/claude_session.py finish --project backend
```

### Step 2: Regenerate derived artifacts (if applicable)

If the slice has a `frontend/brief.md`, regenerate the frontend's generated OpenAPI client so the frontend dev agent works against the updated contract. Run it in the foreground — `scripts/regenerate-openapi.py` runs the backend's `cli prepare`, picks a free port, starts the backend, waits until `/api/docs/openapi.json` is reachable, runs `pnpm generate:api` in the frontend, and stops the backend cleanly on exit:

```bash
scripts/regenerate-openapi.py --frontend
```

**Commit the regenerated client** so the frontend agent picks up the updated spec — stage only the regenerated cache:

```bash
cd /home/pvginkel/source/IoTSupport && git add frontend/openapi-cache/ && git commit -m "Regenerate API client (slice <NUMBER>)"
```

### Step 3: Review the API contract (if applicable)

Read the generated OpenAPI spec and compare it against `api_contract.json`. For each endpoint entry:

1. Verify the endpoint exists in the spec (method + path).
2. Check that `key_request_fields` and `key_response_fields` appear in the schemas.
3. Confirm the `status_codes` are documented.
4. Update the `verified` field to `true` or `false`.

For each `schema_changes` entry, verify the change is reflected. For each `removals` entry:
- `schema_field` removals: grep the OpenAPI spec for the field name and confirm it does not appear in the named schema.
- `endpoint` removals: confirm the method + path combination does not exist in the spec.

Write the updated `api_contract.json` back to the slice directory.

If any endpoint has `verified: false`, assess whether it's a significant gap (missing endpoint, wrong schema) or a minor difference (field ordering, naming convention). Significant gaps → notify the user and stop. Minor differences are fine.

**Log any issues** (gaps, deferred items, workarounds) to the issue log.

### Step 4+: Run the consumer subprojects

For each remaining subproject with a brief file, run `claude` using the same pattern as Step 1 (ask questions, log Q&A, append `qa_correction` entries to `verification.json` per the Step 1 rule, pick workflow, execute, finish). The sequence is the same; only the project name changes.

**UX design:** If `ux_design.md` exists, include it in the initial prompt: ask the agent to read it alongside the brief.

**Check for testing infrastructure gaps.** If the agent's questions reveal that it needs testing infrastructure from the leading subproject (e.g., a seeding endpoint for end-to-end tests), **stop the agent immediately**. Send the leading subproject's agent to implement the missing infrastructure first, then resume. Testing infrastructure gaps are blocking.

### Step 6: Release notes (not applicable)

IoTSupport does not maintain a user-facing release-notes file, so there is no release-notes step for this project. Proceed directly to the full test suite.

### Step 7: Run the full test suite

After all agents have completed, run the full test suite to verify everything is green:

```bash
poetry run run-suite
```

Run this in the background (`run_in_background: true`). The background task mechanism notifies you automatically when it completes — do **not** poll with sleep+check commands.

**If all tests pass:** proceed to Step 8c.

**If any tests fail:**

1. Read the suite-result artifact for the detailed failure output.
2. For each failure, identify which agent owns it based on where the failing test lives.
3. **Diagnose before fixing.** Understand *why* the test fails. In particular:
   - **When a consumer subproject's tests fail after a leading-subproject-only change**, the cause is almost always test infrastructure that references the old behavior (a startup command, an endpoint path, an env var). Look at how **passing** tests start their services and follow the same pattern for the failing service. Do not add special cases or workarounds — if a fix requires a lot of special-casing, the approach is wrong.
   - **When a fix seems to need changes to the app factory or core test infrastructure**, stop and reconsider. That infrastructure is battle-tested; the problem is more likely in the new code.
4. Write the failure output to a prompt file and send the owning agent back to fix it. Tell the agent explicitly: *"The test suite was green before your changes. These failures are regressions caused by your code changes (all unpushed commits). Find and fix the root cause."* Include the full failure output and your diagnosis.
5. After the agent finishes, re-run the suite to verify the fix.
6. **If a failure is clearly caused by a leading-subproject gap** that a consumer agent cannot fix alone, notify the user and stop.
7. **Repeat until green or blocked.**
8. **Maximum 3 fix rounds per agent.** If an agent cannot get its tests green after 3 attempts, notify the user and stop.

### Step 8c: Independent verification

Verification runs in fresh context via the `slice-verifier` sub-agent walking the verification log.

1. **Determine the slice's commit range** — typically the unpushed commits on the current branch, or the commits added since this slice started. Capture as a hash range or list.

2. **Dispatch the `slice-verifier` sub-agent** with paths only:

   ```
   Slice directory: ../IoTSupportSpecs/slices/<SLICE_DIR>/
   Commit range: <hash>..HEAD  (or specific hashes)
   ```

   **Do not** include framing — no opinions about quality, no hints about which entries you expect to pass. The agent definition contains everything the verifier needs.

3. **Read the updated `verification.json`.** The verifier has filled in `verdict`, `rationale`, and `evidence` per entry.

4. **Route the result:**
   - Any entry with verdict `failed` or `uncertain` → slice goes back to the owning agent (use the entry's `area`) with the verifier's evidence and the gap. Do not re-derive the verdict yourself.
   - A rationale that reads like a rubber-stamp (matches without surprises, no falsification statement) → send back to the verifier with the entry id and ask for sharper reading.
   - All passed → proceed to Step 9.

Trust the verifier's flags. If you genuinely disagree, escalate to the user — do not add an override block to `verification.json`. `verification.json` is committed with the rest of the slice artifacts at the end of the run.

### Step 9: Review QA log for issue log items

Review `../IoTSupportSpecs/slices/<SLICE_DIR>/qa_log.md` end-to-end. Look for:

- **Deferred work** — features or improvements explicitly deferred to a later slice.
- **Known limitations** — architectural shortcuts that will need revisiting.
- **Contract/spec drift** — cases where implementation diverged from the original brief.
- **Design decisions with future implications.**

For each item found, create a card on the issue log. Don't duplicate items already logged inline during Q&A.

### Step 10: Report results

Summarize what happened:
- Which agents ran and whether they succeeded.
- Any issues encountered.
- The API contract review result (from `api_contract.json` — how many endpoints verified/failed).
- Test suite results (pass/fail per project, number of fix rounds if any).
- Acceptance criteria results — count `source: ac` entries in `verification.json` by `verdict`. At this point all should be `passed` (failed/uncertain were routed back in Step 8c); if any remain unresolved, Step 8c was skipped and you must go back.
- Any failures blocked on identified gaps (link to issue log entries).

Move the slice from the **Pending** section to the **Completed** section in `../IoTSupportSpecs/README.md`.

Notify the user that the slice is complete (or partially complete if there are outstanding items).

## Important notes

- **The test suite is green before every slice.** This is a hard assumption. If tests fail after a slice run, the slice's changes caused the regression. Do NOT dismiss failures as "pre-existing" or "flaky" — this has been wrong every time. Always send the owning agent back with the explicit instruction that the suite was green and their changes caused the failure.
- **No backwards compatibility.** When answering agent questions, never suggest backwards-compatible workarounds (optional fields to preserve old callers, fallback branches, silent defaults for missing data). Always prefer clean breaking changes.
- **Answer questions yourself.** You have full access to all project documentation. Do not ask the user to answer the dev agent's questions.
- **Do not put code in briefs or answers.** Describe *what* and *why*, not *how*.
- **Stop on failure.** If any agent fails, report to the user and stop.
- **Do not run agents in parallel.** Subprojects may have dependencies — the leading subproject must complete before consumers can start.
- **Run subprojects sequentially**, not in parallel. Resource constraints during test suites make parallel runs unreliable.
- **Timeouts.** Dev agents may take a long time, especially running end-to-end tests. Default timeout is 2 hours per invocation. On timeout, check the session state file at `.claude/sessions/<project>.json` before deciding to resume or restart.
- **Session state files** live at `.claude/sessions/<project>.json`. You can read them at any time to check invocation history and session IDs.
- **Agents must always use one of the change workflows.** If an agent can't make progress using the workflow, the slice is too large — report to the user to discuss splitting it.

## Issue log

Whenever you encounter something that needs future attention — a gap in the API, a deferred feature, a workaround, a missing field, a known limitation — log it to the issue tracker. See root `CLAUDE.md` for the card conventions.

**Card lifecycle during a slice run:**
- When a slice **starts**, check the Planned list for cards with the slice's label. These are issues the slice is expected to address.
- When an issue is **implemented** by a dev agent (code committed), move its card from Planned → Implemented.
- When new issues are **discovered** during the slice (QA log, spec review, test failures), create them in the New list. If the issue is scoped into the current or a follow-up slice, also move it to Planned.
- At the **end of the slice** (Step 10), review all cards with the slice's label and ensure they are in the correct list:
  - Delivered items → **Implemented**
  - Items scoped for a follow-up slice → **Planned** (with the follow-up slice's label)
  - Unplanned items still in New → leave in **New** for triage
