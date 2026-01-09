# Code Review — Frontend Guidance for LLM (single-pass, adversarial)

**Purpose.** Perform a one-shot, thorough frontend code review that *proves* readiness (or surfaces real risks) without relying on multi-iteration follow-ups. Write the results to:
`docs/features/<FEATURE>/code_review.md`.

**Inputs**
- The feature branch or repo snapshot under review.
- The related plan (`plan.md`) at the same revision (if available).
- The exact code changes (diff or commit range). Refuse to review if this information is missing.

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

**Ignore (out of scope)**
Minor cosmetic nits a competent developer would auto-fix: copy tweaks, import reshuffles, formatting, purely stylistic class name changes.

---

## What to produce (section layout for `code_review.md`)
Use these headings. Inside each, free-form prose is fine, but **quote evidence** with `path:line-range` and a short snippet.

### 1) Summary & Decision
Capture overall readiness and the review verdict. Use `<review_summary_template>` to keep the summary tight and evidence-linked.

<review_summary_template>
**Readiness**
<single paragraph on overall readiness>

**Decision**
`GO` | `GO-WITH-CONDITIONS` | `NO-GO` — <brief reason tied to evidence>
</review_summary_template>

### 2) Conformance to Plan (with evidence)
Explain how the implementation maps to the approved plan, and flag deviations or missing deliverables. Structure the comparison with `<plan_conformance_template>`.

<plan_conformance_template>
**Plan alignment**
- `<plan section>` ↔ `code_path:lines` — <snippet showing implementation>
- ...

**Gaps / deviations**
- `<plan commitment>` — <what's missing or differs> (`code_path:lines`)
- ...
</plan_conformance_template>

### 3) Correctness — Findings (ranked)
List every correctness issue in descending severity using `<finding_template>`. Each entry must include severity with ID/title, the code evidence, the concrete impact, the smallest actionable fix, and your confidence level. For any **Blocker** or **Major**, add either a runnable test sketch or stepwise failure reasoning.

<finding_template>
- Title: `<Severity> — <short summary>`
- Evidence: `file:lines` — <snippet or paraphrase>
- Impact: <user/system consequence>
- Fix: <minimal viable change>
- Confidence: <High / Medium / Low>
</finding_template>

Severity:
- **Blocker** = violates product intent, breaks user-visible flow, drops instrumentation needed for tests, corrupts persistent state, or is untestable → typically `NO-GO`.
- **Major** = correctness risk, API/contract mismatch, caching/state ambiguity affecting scope → often `GO-WITH-CONDITIONS`.
- **Minor** = non-blocking clarity/ergonomics.

### 4) Over-Engineering & Refactoring Opportunities
Highlight hotspots with unnecessary abstraction, duplication, or unclear ownership, and describe the smallest refactor that restores clarity. Capture each observation with `<refactor_opportunity_template>`.

<refactor_opportunity_template>
- Hotspot: <module/component showing over-design>
- Evidence: `file:lines` — <snippet>
- Suggested refactor: <minimal change>
- Payoff: <testability/maintenance benefit>
</refactor_opportunity_template>

### 5) Style & Consistency
Call out substantive consistency issues that threaten maintainability (state patterns, error handling, instrumentation usage) and summarize them with `<style_consistency_template>`.

<style_consistency_template>
- Pattern: <inconsistency observed>
- Evidence: `file:lines` — <snippet>
- Impact: <maintenance/testability consequence>
- Recommendation: <concise alignment step>
</style_consistency_template>

### 6) Tests & Deterministic Coverage (new/changed behavior only)
For each changed behavior, document the exercised Playwright scenarios, supporting instrumentation, and any coverage gaps. Capture the details with `<test_coverage_template>`. Mark missing scenarios or hooks as **Major** and propose the minimum viable tests.

<test_coverage_template>
- Surface: <page/component/workflow>
- Scenarios:
  - Given <context>, When <action>, Then <outcome> (`tests/path.spec.ts`)
- Hooks: <instrumentation events, selectors, backend helpers>
- Gaps: <missing cases or instrumentation>
- Evidence: <code_path:lines or test file references>
</test_coverage_template>

### 7) **Adversarial Sweep (must attempt ≥3 credible failures or justify none)**
Attack likely frontend fault lines:
- Derived state ↔ persistence: filtered lists driving writes or cache mutations without guards.
- Concurrency/async: race windows between navigation and responses, missing effect cleanup, stale closures in callbacks.
- Query/cache usage: forgetting invalidation, mixing server data with local state, optimistic updates that never roll back.
- Instrumentation & selectors: missing events/tests, unstable `data-testid` usage.
- Performance traps: accidental O(n²) loops, unnecessary re-renders, large memo dependencies.

Report adversarial findings using `<finding_template>`. If the sweep turns up no credible failures, document the attempted attacks and rationale with `<adversarial_proof_template>`.

<adversarial_proof_template>
- Checks attempted: <list of fault lines probed>
- Evidence: <code_path:lines or test output references>
- Why code held up: <reasoning that closes the risk>
</adversarial_proof_template>

### 8) Invariants Checklist (table)
Document critical invariants the code must maintain, providing at least three entries or a justified “none; proof.” Fill out `<invariant_template>` for each invariant.

<invariant_template>
- Invariant: <statement the system must uphold>
  - Where enforced: <component/hook/test proving it (`file:lines`)>
  - Failure mode: <how the invariant could break>
  - Protection: <existing guard, effect cleanup, cache invalidation>
  - Evidence: <additional path:lines as needed>
</invariant_template>

> If an entry shows filtered/derived state driving a persistent write/cleanup without a guard, escalate to at least **Major**.

### 9) Questions / Needs-Info
List unresolved questions that block confidence in the change, explaining why each matters and what clarification is required. Record them with `<question_template>`.

<question_template>
- Question: <what you need to know>
- Why it matters: <decision blocked or risk introduced>
- Desired answer: <specific clarification or artifact>
</question_template>

### 10) Risks & Mitigations (top 3)
Call out the top execution risks revealed by the review and the mitigation you expect before shipping. Summarize each using `<risk_template>`.

<risk_template>
- Risk: <concise statement tied to evidence>
- Mitigation: <action or follow-up to reduce impact>
- Evidence: <reference to finding/question `path:lines`>
</risk_template>

### 11) Confidence
State your confidence level and rationale, using `<confidence_template>` to keep the statement concise.

<confidence_template>Confidence: <High / Medium / Low> — <one-sentence rationale></confidence_template>

---

## Method (how to think)
1. **Assume wrong until proven**: stress React lifecycle, query cache usage, instrumentation hooks, and navigation flows before endorsing the change.
2. **Quote evidence**: every claim includes `file:lines` (and plan refs when applicable).
3. **Be diff-aware**: focus on changed code first, but validate touchpoints (components, hooks, API calls, tests, instrumentation).
4. **Prefer minimal fixes**: propose the smallest change that closes the risk (e.g., add abort controller, tighten dependency array, extend instrumentation).
5. **Don’t self-certify**: never claim “fixed”; suggest patches or tests.

---

## Frontend specifics to keep in mind
- Generated API hooks: prefer `useXQuery`/`useXMutation` wrappers; avoid ad hoc `fetch` and wire cache invalidation.
- React 19 features: respect concurrent rendering, use `useEffectEvent`/`useTransition` where documented, clean up subscriptions.
- State management: avoid deriving persistent decisions from filtered views; keep source of truth in TanStack Query or central contexts.
- Instrumentation: keep `useListLoadingInstrumentation`, `trackForm*`, and `isTestMode()` flows aligned with Playwright expectations; selectors must stay stable.
- Accessibility & semantics: reuse shared components and adhere to UI guidelines before shipping.

---

## Stop condition
If **Blocker/Major** is empty and tests/coverage are adequate, recommend **GO**; otherwise `GO-WITH-CONDITIONS` or `NO-GO` with the minimal changes needed for `GO`.

## Final check
All XML template demarcation tags have been removed and all XML tags inside template output has been replaced with an actual value.
