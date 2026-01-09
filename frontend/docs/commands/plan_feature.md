# Plan a Feature — Frontend Technical Plan Template

**Purpose.** Produce a tight, implementation-ready *technical plan* for a frontend feature slice the user describes. The output is a single Markdown file at:
`docs/features/<FEATURE>/plan.md` (where `<FEATURE>` is **snake_case**, ≤5 words).

**Keep it project-agnostic.** Learn stack details from the repository and canonical docs (e.g., `AGENTS.md`, `docs/contribute/architecture/application_overview.md`, `docs/contribute/testing/playwright_developer_guide.md`) and reference them explicitly in the plan instead of restating guidance here.

**LLM instructions**
Output snippets are marked by XML brackets. The XML brackets are not to be included in the end result.

Assuming the template <output_template>:

```
<output_template>
The answer is <value>
</output_template>
```

The final document will contain the following output only:

```
The answer is 42
```

---

## Inputs you must use

* The user’s prompt or product brief (quote the key phrases verbatim where accuracy matters).
* Repository research: components, hooks, utilities, instrumentation helpers, Playwright specs.
* Canonical contributor docs the user links or that the feature touches (architecture, testing, UI patterns, instrumentation notes).

> If the prompt stays ambiguous **after** code/doc research, ask a **small, blocking set** of clarifying questions; otherwise proceed.

* **User Requirements Checklist** (provided by the orchestrator). The orchestrator extracts explicit requirements from the user's prompt and provides a pre-built checklist. You **must include this checklist verbatim** in the plan output — do not rephrase, reinterpret, or omit any items.

---

## Deliverable format (headings to include in the plan)

### 0) Research Log & Findings

Summarize the discovery work that informed the plan. Mention searched areas, relevant components/hooks, instrumentation helpers, and any conflicts you resolved.

### 1) Intent & Scope (1–3 short paragraphs)

* **User intent** in your own words + **verbatim** snippets from the prompt for critical phrases.
* **In-scope** vs **Out of scope** bullets (tight). Avoid PM language (no timelines, success metrics).
* **Assumptions/constraints** you’ll rely on.

Use the template in `<intent_scope_template>` for each plan:

<intent_scope_template>
**User intent**

<concise restatement>

**Prompt quotes**

"<verbatim phrases you will anchor on>"

**In scope**

- <primary responsibilities the plan will cover>

**Out of scope**

- <explicit exclusions>

**Assumptions / constraints**

<dependencies, data freshness, rollout limits, cross-repo handoffs>
</intent_scope_template>

### 1a) User Requirements Checklist

This section contains the explicit requirements extracted from the user's prompt by the orchestrator. **Include the checklist exactly as provided — do not modify, rephrase, or omit any items.**

This checklist serves as a verification artifact: after implementation, a separate agent will use it to confirm that every requirement has been addressed.

<user_requirements_checklist_template>
**User Requirements Checklist**

<checklist items provided verbatim by the orchestrator>
</user_requirements_checklist_template>

### 2) Affected Areas & File Map (with repository evidence)

List every component, hook, route, style module, and instrumentation helper to create or change. For each, include:

* **Why** it’s touched (one sentence).
* **Evidence:** `path:line-range` quotes showing call sites, props, generated API usage, or existing instrumentation.

> Be exhaustive here; this becomes the implementation checklist.

Use the template in `<file_map_entry_template>` for each entry:

<file_map_entry_template>
- Area: <module / component / hook>
- Why: <reason this area changes>
- Evidence: <path:line-range — short quote proving relevance>
</file_map_entry_template>

### 3) Data Model / Contracts

Document any view model or API contract changes the UI depends on.

* **Data shapes** new/changed (request/response payloads, TanStack Query cache keys, local state models).
* Prefer aligning with generated API hooks; if adjustments are needed upstream, note the dependency and expected response shape.

Use the template in `<data_model_template>`:

<data_model_template>
- Entity / contract: <payload, query key, component state>
- Shape: <concise JSON/table sketch highlighting new or changed fields>
- Mapping: <how snake_case maps to camelCase models or adapter logic>
- Evidence: <path:line-range — schema, model, or hook reference>
</data_model_template>

### 4) API / Integration Surface

Enumerate backend endpoints, TanStack Query hooks, and event emitters the UI calls or listens to.

* Method/path, generated hook name, variables passed, expected responses, error surfaces.
* State how mutations invalidate or update caches.

Use `<integration_surface_template>`:

<integration_surface_template>
- Surface: <HTTP method + path / generated hook>
- Inputs: <variables or payload the UI sends>
- Outputs: <response data, cache updates, post-mutation state>
- Errors: <error boundaries, toast/notification routing, retry semantics>
- Evidence: <path:line-range — existing hook or service usage>
</integration_surface_template>

### 5) Algorithms & UI Flows (step-by-step)

Describe core UI logic in numbered steps or pseudo-flow chart form.

* Component render flow, form submission lifecycle, pagination/filter interactions, optimistic updates.
* Note concurrency details (parallel queries, dependent mutations, streaming updates).

Use `<algorithm_template>`:

<algorithm_template>
- Flow: <name or trigger of the UI flow>
- Steps:
  1. <step one>
  2. <step two>
  3. <continue as needed>
- States / transitions: <React state machine, query statuses, navigation transitions>
- Hotspots: <re-render pressure, latency blockers, dependency coupling>
- Evidence: <path:line-range — logic reference>
</algorithm_template>

### 6) Derived State & Invariants (stacked bullets)

List derived values that drive UI visibility, cached data, or cross-page state. Provide ≥3 entries or justify “none”. For each derived value, use `<derived_value_template>`:

<derived_value_template>
- Derived value: <name>
  - Source: <filtered/unfiltered inputs and where they come from>
  - Writes / cleanup: <what follows from the derived value (e.g., cache updates, navigation, form resets)>
  - Guards: <conditions, feature flags, optimistic update rollbacks>
  - Invariant: <what must stay true to prevent UI drift or data loss>
  - Evidence: <file:line>
</derived_value_template>

> If a **filtered** view drives a **persistent** write or cache mutation, call it out explicitly and propose protections.

### 7) State Consistency & Async Coordination

Explain how the UI keeps TanStack Query caches, React state, and instrumentation in sync.

* Query invalidation strategy, stale data windows, aborting in-flight requests on navigation or prop changes.
* Coordination with `useListLoadingInstrumentation`, `trackForm*`, or other telemetry hooks.

Use `<consistency_template>`:

<consistency_template>
- Source of truth: <query cache, local state, context provider>
- Coordination: <how derived state stays aligned across components>
- Async safeguards: <abort controllers, stale response protection, suspense boundaries>
- Instrumentation: <events emitted and when; ensure tests can rely on them>
- Evidence: <path:line-range — hook/component reference>
</consistency_template>

### 8) Errors & Edge Cases

Enumerate user-visible failures and validation rules.

* Error presentation (global handler, inline messages), fallback UI, empty states.
* Validation bounds, disabled states, retry prompts.

Log each case using `<error_case_template>`:

<error_case_template>
- Failure: <what goes wrong>
- Surface: <component/route that observes it>
- Handling: <error UI, retry, navigation>
- Guardrails: <validation, disabled states, analytics alerts>
- Evidence: <path:line-range — existing behavior or TODO>
</error_case_template>

### 9) Observability / Instrumentation

Define how the feature stays measurable and testable.

* Events emitted through instrumentation hooks, data attributes (`data-testid`) added, analytics or logging forwarders.
* Any alerts or metrics proving the UI flow works in production.

Detail instrumentation with `<telemetry_template>`:

<telemetry_template>
- Signal: <event/test hook/metric name>
- Type: <instrumentation event, console log, analytics ping>
- Trigger: <when you emit it and from where>
- Labels / fields: <dimensions that differentiate outcomes>
- Consumer: <Playwright wait helper, analytics view, alert>
- Evidence: <path:line-range — existing instrumentation helper>
</telemetry_template>

### 10) Lifecycle & Background Work

Capture lifecycle hooks that need coordination.

* Effects that attach listeners, timers, or subscriptions and how they clean up.
* Idle/background revalidation or polling initiated by the UI.

Use `<lifecycle_template>`:

<lifecycle_template>
- Hook / effect: <name>
- Trigger cadence: <on mount, on interval, on visibility change>
- Responsibilities: <work performed and dependencies>
- Cleanup: <how it disposes on unmount or navigation>
- Evidence: <path:line-range — hook/component reference>
</lifecycle_template>

### 11) Security & Permissions (if applicable)

* Gated features, role-based visibility, redaction of sensitive data in the UI.

Capture changes with `<security_template>` (omit if truly not applicable):

<security_template>
- Concern: <authentication, authorization, data exposure>
- Touchpoints: <components enforcing the rule>
- Mitigation: <how you enforce / log / alert>
- Residual risk: <what remains and why it’s acceptable>
- Evidence: <path:line-range — guard or policy usage>
</security_template>

### 12) UX / UI Impact (if applicable)

* Entry points, screens/forms affected, validation interactions, accessibility updates.
* Reference canonical UI guidelines for patterns you extend.

Outline UI changes with `<ux_impact_template>` (omit if no UX impact):

<ux_impact_template>
- Entry point: <route, modal, tab>
- Change: <copy, layout, validation, navigation adjustment>
- User interaction: <what the user experiences differently>
- Dependencies: <frontend components or backend contracts relied on>
- Evidence: <path:line-range — component reference>
</ux_impact_template>

### 13) Deterministic Test Plan (new/changed behavior only)

For each UI behavior or API interaction:

* **Scenarios** (Given/When/Then) tied to Playwright specs.
* **Instrumentation** (`data-testid`, test events) and backend coordination requirements.
* **Gaps** intentionally left for later (justify).

Use `<test_plan_template>`:

<test_plan_template>
- Surface: <page/component/workflow>
- Scenarios:
  - Given <context>, When <action>, Then <outcome>
  - <add more scenarios as needed>
- Instrumentation / hooks: <selectors, events, backend helpers>
- Gaps: <anything deferred + justification>
- Evidence: <path:line-range — existing spec or helper>
</test_plan_template>

### 14) Implementation Slices (only if large)

Order slices that ship value incrementally (e.g., instrumentation → API wiring → UI polish → tests).

Use `<implementation_slice_template>`:

<implementation_slice_template>
- Slice: <name or milestone>
- Goal: <value the slice ships>
- Touches: <primary files/modules to update>
- Dependencies: <what must happen before/after; feature flags if any>
</implementation_slice_template>

### 15) Risks & Open Questions

* Top 3–5 **risks** with short mitigations.
* **Open questions** that could change the design (why they matter + who answers).

Use `<risk_template>` and `<open_question_template>`:

<risk_template>
- Risk: <what could go wrong>
- Impact: <user or system consequence>
- Mitigation: <quick action to reduce likelihood or impact>
</risk_template>

<open_question_template>
- Question: <missing info that affects the design>
- Why it matters: <decision or dependency blocked>
- Owner / follow-up: <who can answer or where to research>
</open_question_template>

### 16) Confidence (one line)

* High/Medium/Low with a short reason.

Use `<confidence_template>`:

<confidence_template>Confidence: <High / Medium / Low> — <one-sentence rationale></confidence_template>

---

## Method (how to work while writing the plan)

1. **Research-first.** Scan the repo and canonical docs (`docs/contribute/*`, instrumentation guides, component conventions) before asking questions; quote file/line evidence for every claim.
2. **Be minimal.** Prefer the smallest viable UI and API changes that satisfy intent; reuse existing hooks and patterns.
3. **No code.** Use pseudocode or structured bullets only; keep the plan implementable by a competent frontend developer.
4. **Name the feature folder well.** Use `<FEATURE>` that’s short, descriptive, and snake_case.
5. **Stop condition.** The plan is done when all sections above contain enough precision that another developer can implement without guessing and Playwright scenarios are deterministic.

## Final check
All XML template demarcation tags have been removed and all XML tags inside template output has been replaced with an actual value.
