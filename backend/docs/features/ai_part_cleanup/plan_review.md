# AI Part Cleanup — Plan Review

## 1) Summary & Decision

**Readiness**

The plan is comprehensive and well-researched, following established patterns from AIPartAnalysisTask. It correctly identifies all affected areas, defines clear contracts, and provides detailed test scenarios. However, several critical issues require resolution: the plan assumes a "Mouser API tool" that doesn't exist in the codebase, lacks clarity on how AI should handle seller field population during cleanup, and doesn't specify URL classifier wiring despite URLClassifierFunction existing. The test data update requirement is mentioned in coverage but not explicitly called out as a blocker. With these gaps addressed, the implementation would be ready.

**Decision**

`GO-WITH-CONDITIONS` — The plan is fundamentally sound and follows project patterns, but requires clarification on tool availability (Mouser API), seller field handling, URL classifier instantiation/wiring, and explicit test data migration requirements before implementation can proceed safely.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/product_brief.md` — Pass — `plan.md:77-95` — Intent correctly scoped to single-part cleanup returning improved JSON; aligns with single-user, no-auth model
- `CLAUDE.md` layering requirements — Pass — `plan.md:162-199` — Correctly separates API (endpoint), Service (AIService.cleanup_part), Task (AIPartCleanupTask), and Schemas
- `CLAUDE.md` error handling — Pass — `plan.md:395-450` — Uses typed exceptions (RecordNotFoundException, InvalidOperationException) and @handle_api_errors decorator pattern
- `CLAUDE.md` dependency injection — Pass — `plan.md:184-186` — Acknowledges no new wiring needed; existing ai_service provider sufficient
- `CLAUDE.md` testing requirements — Pass — `plan.md:528-592` — Comprehensive test scenarios for service, task, API, and prompt template modes
- `docs/commands/plan_feature.md` template — Pass — All 16 sections present with proper evidence citations and templates filled

**Fit with codebase**

- `app/services/ai_service.py` — `plan.md:169-170` — Assumes URLClassifier is injectable but plan doesn't show URLClassifierFunction wiring in container or AIService constructor
- `app/utils/ai/` — `plan.md:656-660` — Open question about Mouser API tool; grep shows no MouserAPI class exists; may be conflating web search with Mouser-specific tool
- `app/services/container.py` — `plan.md:184-186` — Plan states "no wiring changes required" but doesn't address how URLClassifierFunction reaches AIService.cleanup_part()
- `app/data/test_data/` — `plan.md:545-586` — Test coverage section doesn't explicitly require test data JSON updates, though CLAUDE.md mandates test dataset maintenance for schema changes

---

## 3) Open Questions & Ambiguities

- Question: Does the "Mouser API tool" exist as a separate AIFunction implementation?
- Why it matters: Plan lists Mouser API in tools available (plan.md:656-660, change_brief.md:28) but codebase grep finds no MouserAPIFunction or similar; if non-existent, plan overstates AI capabilities and prompt expectations
- Needed answer: Confirm Mouser API integration status; if not implemented, remove from plan and change brief; if web search covers Mouser queries, clarify that distinction

---

- Question: How should AIService.cleanup_part() populate the seller field when Part.seller is null?
- Why it matters: Plan states "seller from manufacturer when product_page domain matches known seller" (plan.md:376-382) but doesn't define matching logic or fallback behavior; ambiguous seller resolution could produce inconsistent cleanup results
- Needed answer: Specify exact logic: (1) if part.seller exists, return seller.name; (2) if null and AI suggests manufacturer, return manufacturer value; (3) frontend performs seller name→id resolution before applying

---

- Question: How is URLClassifierFunction instantiated and passed to AIService.cleanup_part()?
- Why it matters: Plan.md:169-170 mentions URLClassifier inclusion but AIService constructor (app/services/ai_service.py:48-71) only receives duplicate_search_function; cleanup_part() needs url_classifier_function parameter or container access
- Needed answer: Either (a) add url_classifier_function to AIService constructor and container wiring, or (b) instantiate URLClassifierFunction inside cleanup_part() with no dependencies, or (c) reuse self.url_classifier_function if already wired (verify in constructor)

---

- Question: Should test data JSON files be updated to include new cleanup-relevant fields?
- Why it matters: CLAUDE.md mandates test dataset maintenance for schema changes; cleanup expects all parts to have realistic product_page, seller, technical fields for AI context; if test data lacks these, cleanup tests won't exercise realistic scenarios
- Needed answer: Explicit checklist item to update app/data/test_data/parts.json with complete field coverage (package, pin_count, product_page, seller references) before testing cleanup task

---

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: AIPartCleanupTask.execute_session()
- Scenarios:
  - Given part exists with minimal data, When cleanup executes, Then returns CleanedPartDataSchema with all fields populated (`tests/services/test_ai_part_cleanup_task.py::test_cleanup_minimal_part`)
  - Given part exists with complete data, When cleanup executes, Then AI improves data quality without losing existing values (`test_cleanup_preserves_existing_data`)
  - Given part does not exist, When cleanup executes, Then raises RecordNotFoundException before starting task (`test_cleanup_nonexistent_part`)
  - Given cleanup task running, When user cancels, Then returns AIPartCleanupTaskCancelledResultSchema (`test_cleanup_cancellation`)
  - Given OpenAI API fails, When cleanup executes, Then returns error result with user-friendly message (`test_cleanup_ai_failure`)
  - Given 100 other parts in inventory, When cleanup executes, Then context includes all 100 parts serialized correctly (`test_cleanup_builds_full_context`)
  - Given part has type and seller, When cleanup executes, Then context includes type.name and seller.name strings (`test_cleanup_serializes_relationships`)
  - Given part has null seller, When cleanup executes, Then context includes seller: null (`test_cleanup_handles_null_seller`)
  - Given AI suggests type change, When cleanup executes, Then cleaned data includes new type name (`test_cleanup_allows_type_change`)
  - Given AI returns invalid data, When cleanup executes, Then schema validation fails and returns error result (`test_cleanup_invalid_ai_response`)
  - Given >10,000 parts in inventory, When cleanup executes, Then returns error "Too many parts for cleanup context" (`test_cleanup_part_count_limit`)
- Instrumentation: ai_cleanup_requests_total counter (started/success/error/cancelled), ai_cleanup_duration_seconds histogram, ai_cleanup_part_count gauge, structured logs at start/completion
- Persistence hooks: None (read-only task); test data update required for realistic field coverage; no migrations needed
- Gaps: Test data JSON update not explicitly called out as implementation requirement
- Evidence: plan.md:528-544, plan.md:454-497 (telemetry), CLAUDE.md (test data maintenance mandate)

---

- Behavior: AIService.cleanup_part()
- Scenarios:
  - Given part_key and context, When cleanup_part() called, Then builds prompt with mode="cleanup" and all_parts context (`tests/services/test_ai_service.py::test_cleanup_part_builds_context`)
  - Given cleanup mode, When building tools, Then includes URLClassifier but excludes DuplicateSearchFunction (`test_cleanup_excludes_duplicate_search`)
  - Given AI response with analysis_result, When parsing response, Then maps fields to CleanedPartDataSchema correctly (`test_cleanup_maps_response_fields`)
  - Given AI response missing analysis_result, When parsing response, Then raises exception (`test_cleanup_requires_analysis_result`)
  - Given real_ai_allowed=False, When cleanup_part() called, Then raises InvalidOperationException (`test_cleanup_requires_real_ai`)
- Instrumentation: Metrics recorded via AIRunner (inherited from analyze_part pattern)
- Persistence hooks: None (read-only)
- Gaps: URLClassifierFunction wiring not specified
- Evidence: plan.md:547-557, plan.md:320-326

---

- Behavior: POST /api/ai-parts/cleanup
- Scenarios:
  - Given valid part_key, When POST cleanup, Then returns HTTP 201 with TaskStartResponse (`tests/api/test_ai_parts_cleanup.py::test_cleanup_endpoint_success`)
  - Given invalid part_key format, When POST cleanup, Then returns HTTP 400 with validation error (`test_cleanup_invalid_key_format`)
  - Given part_key does not exist, When POST cleanup, Then returns HTTP 400 with "Part not found" error (`test_cleanup_part_not_found`)
  - Given real_ai_allowed=False without dummy response, When POST cleanup, Then returns HTTP 400 with "AI disabled" error (`test_cleanup_ai_disabled`)
  - Given valid request, When task completes, Then SSE stream returns AIPartCleanupTaskResultSchema (`test_cleanup_sse_response`)
- Instrumentation: HTTP request metrics via prometheus-flask-exporter
- Persistence hooks: None
- Gaps: None
- Evidence: plan.md:560-570, plan.md:303-309

---

- Behavior: GET /api/ai-parts/cleanup/<task_id>/result
- Scenarios:
  - Given completed cleanup task, When GET result, Then returns HTTP 200 with AIPartCleanupTaskResultSchema (`tests/api/test_ai_parts_cleanup.py::test_get_cleanup_result_success`)
  - Given task does not exist, When GET result, Then returns HTTP 404 (`test_get_cleanup_result_not_found`)
  - Given task not completed, When GET result, Then returns HTTP 404 with "Task not completed" message (`test_get_cleanup_result_incomplete`)
- Instrumentation: Standard HTTP metrics
- Persistence hooks: None
- Gaps: None
- Evidence: plan.md:572-581, plan.md:312-317

---

- Behavior: Prompt template mode parameter (part_analysis.md)
- Scenarios:
  - Given mode="cleanup", When rendering template, Then includes cleanup instructions and excludes duplicate search guidance (`tests/services/test_ai_service.py::test_prompt_cleanup_mode`)
  - Given mode="analysis", When rendering template, Then includes analysis instructions and duplicate search guidance (`test_prompt_analysis_mode`)
  - Given mode unspecified, When rendering template, Then defaults to analysis mode (`test_prompt_default_mode`)
- Instrumentation: None (template rendering)
- Persistence hooks: Prompt file rename requires atomic deployment
- Gaps: None
- Evidence: plan.md:583-592, plan.md:164-166

---

## 5) Adversarial Sweep (must find ≥3 credible issues or declare why none exist)

**Major — Mouser API Tool Not Implemented**
**Evidence:** `plan.md:134-135, 656-660` — "URLClassifier, web search, and Mouser API tools are already implemented as AIFunction instances (verify and wire)" + Open question about Mouser API; grep of `/work/backend/app/utils/ai/` finds only `url_classification.py` and `duplicate_search.py`, no Mouser-specific tool
**Why it matters:** Plan and change brief promise Mouser API capability to AI, but if tool doesn't exist, AI cannot call it and prompt expectations are wrong; this could degrade cleanup quality for parts with Mouser product pages or mislead users about feature capabilities
**Fix suggestion:** Remove Mouser API from assumptions (plan.md:134-135), open questions (656-660), and change brief (line 28); update prompt template to rely on web search for Mouser queries; if Mouser integration exists elsewhere, provide file path evidence
**Confidence:** High

---

**Major — URLClassifierFunction Wiring Undefined**
**Evidence:** `plan.md:169-170, 184-186` — AIService changes mention URLClassifier but container section says "No wiring changes required"; `app/services/ai_service.py:48-71` constructor only receives `duplicate_search_function`, not `url_classifier_function`; `app/services/container.py:220-242` shows ai_service wired with duplicate_search_function only
**Why it matters:** AIService.cleanup_part() must pass URLClassifierFunction to AIRunner (similar to analyze_part passing both url_classifier and duplicate_search at line 127-132), but plan doesn't specify how cleanup_part gets access to url_classifier instance; without wiring, cleanup_part cannot provide tool to AI
**Fix suggestion:** Add section 2 file map entry for `app/services/container.py` showing url_classifier_function provider creation (Factory with URLClassifierFunction) and injection into ai_service provider; update AIService constructor to accept url_classifier_function parameter; or show URLClassifierFunction has no dependencies and can be instantiated inline
**Confidence:** High

---

**Major — Seller Field Population Logic Ambiguous**
**Evidence:** `plan.md:376-382` — "Seller name in cleaned response... Source: Part.seller relationship (seller.name) or AI's manufacturer field when no seller assigned" + "Seller reference is nullable; return null if part has no seller" contradicts step 15 at `plan.md:346` which says "seller from manufacturer when product_page domain matches known seller"
**Why it matters:** Three different seller resolution strategies mentioned without clear precedence: (1) use Part.seller.name if exists, (2) infer from manufacturer when product_page domain matches, (3) return null if no seller; step-by-step flow (346) and derived value section (376-382) conflict; ambiguous logic will produce inconsistent cleanup results depending on which developer interprets it
**Fix suggestion:** Unify seller logic in section 5 step 15 and section 6 derived value entry: "If Part.seller exists, serialize seller.name; else serialize null; AI may populate seller field in cleaned response based on manufacturer/product_page analysis; frontend resolves seller name→id before applying update"
**Confidence:** High

---

**Minor — Test Data Update Not Explicit Blocker**
**Evidence:** `plan.md:545-586` mentions PartFactory for test fixtures but doesn't call out `app/data/test_data/parts.json` update as explicit requirement; `CLAUDE.md` (Test Data Management section) mandates "When making schema changes: Update the JSON files in app/data/test_data/ to reflect new fields or relationships"
**Why it matters:** Cleanup task relies on realistic part data with product_page, seller, package, pin_count for AI context; if test data lacks these fields (added in extended technical fields feature), cleanup integration tests will exercise incomplete scenarios; CLAUDE.md treats test data drift as blocker-level issue
**Fix suggestion:** Add explicit checklist item in section 1a: "Update app/data/test_data/parts.json to include realistic product_page, seller_link, and technical fields for at least 10 parts to support cleanup context testing"; add to section 4 persistence hooks: "Test data migration: app/data/test_data/parts.json"
**Confidence:** Medium

---

## 6) Derived-Value & Persistence Invariants (stacked entries)

- Derived value: Context parts JSON array
  - Source dataset: Unfiltered query of all Part records excluding target (`SELECT * FROM parts WHERE key != $1`), joined with Type and Seller relationships via selectinload
  - Write / cleanup triggered: None (read-only context serialized and passed to AI as system prompt context)
  - Guards: Part count check before serialization (plan.md:437-442): fail if count > 10,000 to prevent OOM; warn if > 5,000
  - Invariant: Context must include all existing parts except target; if filtered query used (e.g., by type or location), AI's consistency suggestions would be skewed toward visible subset, violating "show AI how parts are currently formatted" requirement
  - Evidence: plan.md:356-363, plan.md:132-136

---

- Derived value: Type name in cleaned response
  - Source dataset: AI's product_category field from PartAnalysisDetails (filtered through existing type names provided in prompt context at plan.md:340)
  - Write / cleanup triggered: None (returned to frontend as string; frontend creates new Type if name doesn't exist, then updates Part.type_id)
  - Guards: Type validation deferred to frontend; backend returns type name string verbatim from AI even if type doesn't exist yet
  - Invariant: Cleaned part data must include type name field even when AI suggests new type; if backend attempted type_id resolution and failed on unknown type, cleanup would fail instead of allowing frontend to offer type creation flow
  - Evidence: plan.md:366-372, change_brief.md:46-47 (type changes allowed during cleanup)

---

- Derived value: Seller name in cleaned response
  - Source dataset: Part.seller relationship (seller.name if seller_id not null), or AI-suggested value when Part.seller is null (ambiguous per section 5 findings)
  - Write / cleanup triggered: None (returned to frontend as string; frontend performs seller name→id resolution or creation before applying update)
  - Guards: Seller field nullable; return null if part.seller is null and AI doesn't suggest seller
  - Invariant: Response seller field is always a name string or null, never seller_id integer; if backend returned seller_id, frontend couldn't distinguish between "seller ID 5" and "seller named '5'"
  - Evidence: plan.md:376-382, plan.md:236 (CleanedPartDataSchema.seller as string)

---

- Derived value: Cleaned part field diffs (implicit)
  - Source dataset: Comparison between original Part fields (serialized at step 7, plan.md:337) and AI's CleanedPartDataSchema response (step 17, plan.md:348)
  - Write / cleanup triggered: None (diff generation is frontend responsibility per plan.md:122, 519-523)
  - Guards: None in backend; frontend must perform field-by-field comparison and user confirmation before PATCH /parts/{key}
  - Invariant: Backend never applies cleaned data to database; if task execution modified Part table, cancellation after AI response wouldn't roll back changes (violates read-only task guarantee at plan.md:387-391)
  - Evidence: plan.md:387-391 (read-only task), plan.md:519-523 (frontend handles diff/apply)

---

## 7) Risks & Mitigations (top 3)

- Risk: URLClassifier and Mouser API tool availability assumptions unverified
- Mitigation: Grep codebase for URLClassifierFunction instantiation pattern in existing analyze_part flow; confirm Mouser API implementation status; update plan to either wire URLClassifier or show no-dependency instantiation; remove Mouser API if non-existent
- Evidence: plan.md:134-135, 169-170, 656-660; finding in section 5

---

- Risk: Seller field population logic conflicts between step-by-step flow and derived value section create implementation ambiguity
- Mitigation: Unify seller handling in section 5 (algorithm) and section 6 (derived value) to single clear rule: serialize Part.seller.name if exists, else null; AI populates seller in cleaned response from manufacturer/product_page analysis; frontend resolves before applying
- Evidence: plan.md:346, 376-382; finding in section 5

---

- Risk: Test data JSON files may lack realistic cleanup-relevant fields (product_page, seller, technical fields), causing cleanup integration tests to miss real-world scenarios
- Mitigation: Add explicit test data update requirement to plan section 1a checklist and section 4 persistence hooks; update app/data/test_data/parts.json with at least 10 parts having complete technical fields before cleanup task testing
- Evidence: plan.md:545-586, CLAUDE.md test data management section; finding in section 5

---

## 8) Confidence

Confidence: Medium — Plan structure and patterns are solid (high confidence in architecture), but tool wiring gaps (URLClassifier, Mouser API) and seller logic ambiguity (medium-high impact) prevent high confidence; once open questions resolved and findings addressed, confidence would rise to High.
