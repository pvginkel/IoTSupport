# Plan Review — Frontend Guidance for LLM (single-pass, adversarial)

**Purpose.** Perform a one-shot, thorough review of a frontend feature plan that surfaces real risks without relying on follow-up prompts. Write the results to:
`docs/features/<FEATURE>/plan_review.md`.

**References (normative).**

* `@docs/commands/plan_feature.md`
* `@docs/product_brief.md`
* `@AGENTS.md`
* `@docs/contribute/architecture/application_overview.md`
* `@docs/contribute/testing/playwright_developer_guide.md`
* (optional) other docs the user links

**Ignore**: minor implementation nits (naming, copy polish, CSS minutiae). Assume a competent developer will handle those during implementation.

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

## What to produce (write to `plan_review.md`)

Use these headings (free-form prose inside each, but **quote evidence** with file + line ranges from the plan and supporting docs).

### 1) Summary & Decision
Provide an overall readiness assessment and verdict, using `<plan_review_summary_template>` to anchor the evidence and decision.

<plan_review_summary_template>
**Readiness**
<single paragraph assessing plan readiness>

**Decision**
`GO` | `GO-WITH-CONDITIONS` | `NO-GO` — <brief reason tied to evidence>
</plan_review_summary_template>

### 2) Conformance & Fit (with evidence)
Evaluate how the plan honors the governing references and meshes with the existing frontend architecture. Summarize the results with `<plan_conformance_fit_template>`.

<plan_conformance_fit_template>
**Conformance to refs**
- `<reference>` — Pass/Fail — `plan_path:lines` — <quote>
- ...

**Fit with codebase**
- `<component/hook>` — `plan_path:lines` — <alignment issue or confirmation>
- ...
</plan_conformance_fit_template>

### 3) Open Questions & Ambiguities
List unanswered questions, emphasizing the impact of each and the decision that hinges on it. Capture them with `<open_question_template>`.

<open_question_template>
- Question: <uncertainty to resolve>
- Why it matters: <impact on implementation or scope>
- Needed answer: <what information unlocks progress>
</open_question_template>

If questions can be answered by performing research, perform the research and provide the answer yourself.

### 4) Deterministic Playwright Coverage (new/changed behavior only)
For each new or changed user-visible behavior, document the scenarios, instrumentation, and backend hooks that validate it. Employ `<plan_coverage_template>` to note any gaps; missing elements should be escalated as **Major**.

<plan_coverage_template>
- Behavior: <page/component/workflow>
- Scenarios:
  - Given <context>, When <action>, Then <outcome> (`tests/path.spec.ts`) 
- Instrumentation: <events, `data-testid`, or helpers the tests rely on>
- Backend hooks: <API factories/helpers required for deterministic runs>
- Gaps: <missing element if any>
- Evidence: <plan_path:lines or reference doc>
</plan_coverage_template>

### 5) **Adversarial Sweep (must find ≥3 credible issues or declare why none exist)**
Stress-test the plan by targeting failure modes that would surface in implementation. Focus on instrumentation gaps, stale cache risks, React concurrency gotchas, and generated API usage.

Record each issue with `<finding_template>`, or—if no credible issues remain—log the attempted checks and justification via `<adversarial_proof_template>`.

<finding_template>
**Severity — Title**
**Evidence:** `plan_path:lines` (+ refs) — <quote>
**Why it matters:** <impact>
**Fix suggestion:** <minimal plan change>
**Confidence:** <High / Medium / Low>
</finding_template>

<adversarial_proof_template>
- Checks attempted: <targeted invariants or fault lines>
- Evidence: <plan_path:lines or referenced sections>
- Why the plan holds: <reason the risk is closed>
</adversarial_proof_template>

If you can improve the fix suggestion by performing research, do the research and include the results of the research in the fix suggestion.

### 6) **Derived-Value & State Invariants (table)**
Document derived UI values that affect cache writes, cleanup, or cross-route state, providing at least three entries or a justified “none; proof.” Populate `<derived_value_template>` for each.

<derived_value_template>
- Derived value: <name>
  - Source dataset: <filtered/unfiltered inputs>
  - Write / cleanup triggered: <cache update, navigation, storage mutation>
  - Guards: <conditions or feature flags>
  - Invariant: <statement that must hold>
  - Evidence: <plan_path:lines or reference doc>
</derived_value_template>

> If an entry uses a **filtered** view to drive a **persistent** write/cleanup without guards, flag **Major** unless fully justified.

### 7) Risks & Mitigations (top 3)
Summarize the top plan-level risks and expected mitigations, grounding each in cited evidence. Use `<risk_template>` for consistency.

<risk_template>
- Risk: <description tied to plan evidence>
- Mitigation: <action or clarification needed>
- Evidence: <plan_path:lines or referenced ref>
</risk_template>

### 8) Confidence
State your confidence in the plan and the reasoning behind it, using `<confidence_template>` to keep the statement concise.

<confidence_template>Confidence: <High / Medium / Low> — <one-sentence rationale></confidence_template>

---

## Severity (keep it simple)

* **Blocker:** Misalignment with product brief, missing instrumentation for required coverage, or untestable/undefined core behavior → tends to `NO-GO`.
* **Major:** Fit-with-codebase risks, missing deterministic Playwright coverage, cache/state ambiguity affecting scope → often `GO-WITH-CONDITIONS`.
* **Minor:** Clarifications that don’t block implementation.

---

## Review method (how to think)

1. **Assume wrong until proven**: hunt for violations of documented UI patterns, stale data flows, or instrumentation omissions.
2. **Quote evidence**: every claim or closure needs plan `file:line` quotes (and supporting doc references when relevant).
3. **Focus on invariants**: filtering, sorting, pagination, optimistic updates, and derived counts must not orphan cache entries or mislead instrumentation.
4. **Coverage is explicit**: if behavior is new/changed, require scenarios + selectors + backend coordination; reject “we’ll test later.”

## Final check
All XML template demarcation tags have been removed and all XML tags inside template output has been replaced with an actual value.
