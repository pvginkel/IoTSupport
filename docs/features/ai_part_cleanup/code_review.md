# AI Part Cleanup — Code Review

## 1) Summary & Decision

**Readiness**

The AI part cleanup feature implementation demonstrates solid adherence to project patterns with comprehensive test coverage and proper error handling. The code follows established conventions from AIPartAnalysisTask, implements the planned dual-mode prompt template correctly, and includes thorough unit tests. However, there are several critical issues that must be addressed before shipping: missing metrics integration (plan requirement), incomplete seller/seller_link handling in cleanup_part() that loses existing data, and a gap in test coverage for the service layer cleanup_part() method.

**Decision**

GO-WITH-CONDITIONS — The implementation is fundamentally sound but requires addressing 3 Major findings before deployment: (1) add metrics instrumentation as specified in plan section 9, (2) fix seller field handling to preserve existing seller data, (3) add service-level tests for AIService.cleanup_part().

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- Plan Section 2 (File Map): app/services/prompts/part_search.md → part_analysis.md (RENAME) — Implemented at app/services/prompts/part_analysis.md with mode conditionals (lines 3-57)
- Plan Section 2: app/services/ai_service.py cleanup_part() method — Implemented at app/services/ai_service.py:238-385 with context building and tool exclusion
- Plan Section 2: app/services/ai_part_cleanup_task.py (NEW) — Implemented at app/services/ai_part_cleanup_task.py:1-98 following BaseSessionTask pattern
- Plan Section 2: app/schemas/ai_part_cleanup.py (NEW) — Implemented at app/schemas/ai_part_cleanup.py:1-156 with all planned schemas
- Plan Section 2: app/api/ai_parts.py cleanup endpoints — Implemented at app/api/ai_parts.py:259-407 for POST /cleanup and GET /cleanup/<task_id>/result
- Plan Section 3: CleanedPartDataSchema structure — Matches plan specification at app/schemas/ai_part_cleanup.py:20-118 with all 17 fields
- Plan Section 4: POST /ai-parts/cleanup endpoint — Implemented at app/api/ai_parts.py:259-314 with proper validation and error handling
- Plan Section 5 (Algorithm): Step 5-6 context building — Implemented at app/services/ai_service.py:267-306 with serialize_part() helper
- Plan Section 5: Step 11 tool exclusion — Implemented at app/services/ai_service.py:350-354 passing only url_classifier_function
- Plan Section 13 (Test Plan): Task tests — Comprehensive coverage at tests/test_ai_part_cleanup_task.py with 10 test cases
- Plan Section 13: API tests — Adequate coverage at tests/test_ai_parts_cleanup_api.py with 7 test cases

**Gaps / deviations**

- Plan Section 9 (Observability): No metrics instrumentation found in AIPartCleanupTask or AIService.cleanup_part() — Missing ai_cleanup_requests_total counter, ai_cleanup_duration_seconds histogram, ai_cleanup_part_count gauge, and structured logging (app/services/ai_part_cleanup_task.py:24-97)
- Plan Section 5 (Algorithm Step 15): CleanedPartDataSchema sets seller=None and seller_link=None unconditionally — This loses existing seller data contrary to plan's "do not lose data" requirement (app/services/ai_service.py:379-382)
- Plan Section 13 (Test Plan): Missing service-level tests for AIService.cleanup_part() method — Only task-level tests exist (tests/test_ai_part_cleanup_task.py), no direct service tests (plan:552-561)
- Plan Section 2 (Test Data): No updates to app/data/test_data/parts.json — Plan specified ensuring realistic product_page, seller_link, technical fields for cleanup context testing (plan:202-204)

---

## 3) Correctness — Findings (ranked)

- Title: Major — Seller data loss in cleanup_part() violates "do not lose data" requirement
- Evidence: app/services/ai_service.py:379-382
  ```python
  seller=None,  # AI doesn't return seller directly; frontend handles this
  seller_link=None  # AI doesn't return seller_link directly; frontend handles this
  ```
- Impact: When AI cleans a part, existing seller name and seller_link are always nulled out, even if the part had valid seller data before cleanup. This contradicts the plan's explicit requirement "do not lose existing data" (plan:11) and the prompt's instruction "Do not lose existing data unless it's definitively wrong" (part_analysis.md:11). Users will see seller fields erased when reviewing cleanup diffs.
- Fix: Extract seller fields from target_part_json and populate CleanedPartDataSchema with existing values: `seller=target_part_json.get("seller")`, `seller_link=target_part_json.get("seller_link")`. The AI model's PartAnalysisDetails doesn't include seller fields, so preserve the original values instead of nulling them.
- Confidence: High

---

- Title: Major — Missing metrics instrumentation for cleanup operations
- Evidence: app/services/ai_part_cleanup_task.py:24-97, app/services/ai_service.py:238-385 — No calls to metrics_service found; plan:459-503 specifies 4 required metrics
- Impact: Operational blind spots for cleanup feature usage, duration, and errors. Plan Section 9 explicitly requires ai_cleanup_requests_total counter with status labels, ai_cleanup_duration_seconds histogram, ai_cleanup_part_count gauge, and structured logging with part_key/task_id. Without these, debugging production issues and monitoring adoption will be difficult.
- Fix: (1) Add metrics_service to AIService constructor (already injected, line 54), (2) In AIPartCleanupTask.execute_session(), call metrics_service.increment_counter("ai_cleanup_requests_total", {"status": "started"}) at line 55, record status on success/error/cancelled, (3) Record duration with metrics_service.record_operation_duration("ai_cleanup", duration, {"status": "success|error"}), (4) Record context part count as gauge after line 269: metrics_service.update_gauge("ai_cleanup_part_count", len(all_parts)), (5) Add structured logging at lines 55, 79.
- Confidence: High

---

- Title: Major — No service-level tests for AIService.cleanup_part()
- Evidence: Plan:552-561 specifies comprehensive service tests; tests/test_ai_part_cleanup_task.py:1-320 only tests task layer with mocked AI service; no tests/services/test_ai_service.py additions for cleanup_part()
- Impact: Core business logic in AIService.cleanup_part() is only tested via task tests with mocks, missing coverage for: (1) prompt building with mode="cleanup", (2) tool list construction (URLClassifier included, DuplicateSearch excluded), (3) response parsing and field mapping, (4) part count limit enforcement (>10000 check at line 272), (5) RecordNotFoundException on missing part. Service logic bugs won't be caught until integration testing.
- Fix: Add test_cleanup_part_* methods to tests/services/test_ai_service.py covering: (a) successful cleanup with minimal/full data, (b) part not found error, (c) part count limit exceeded, (d) prompt mode parameter verification, (e) tool exclusion verification, (f) field mapping from PartAnalysisDetails to CleanedPartDataSchema. Follow existing test_analyze_part() pattern at tests/services/test_ai_service.py.
- Confidence: High

---

- Title: Minor — Part count limit check message includes actual count but context doesn't show how close to limit
- Evidence: app/services/ai_service.py:272-276
  ```python
  if len(all_parts) > 10000:
      raise InvalidOperationException(
          "cleanup part",
          f"Too many parts for cleanup context (limit: 10000, current: {len(all_parts)})"
      )
  ```
- Impact: Error message is clear, but users near the limit won't know they're approaching it. Plan:444-446 mentions this as an edge case that should fail with clear messaging, which is satisfied. However, operational visibility could be improved.
- Fix: Consider logging a warning at 80% threshold (8000 parts): `if len(all_parts) > 8000: logger.warning(f"Cleanup context size approaching limit: {len(all_parts)}/10000 parts")`. This provides early warning without blocking the operation.
- Confidence: Medium

---

## 4) Over-Engineering & Refactoring Opportunities

- Hotspot: serialize_part() helper function duplicated in cleanup_part()
- Evidence: app/services/ai_service.py:250-268 — 20-line nested function defined inside cleanup_part() method
- Suggested refactor: Extract serialize_part() to module-level private function `_serialize_part_to_json(part: Part) -> dict[str, Any]` above the AIService class. This enables reuse if other methods need JSON serialization (e.g., batch cleanup, export features) and improves testability.
- Payoff: Reduces method length from 150 lines to 130, makes serialization logic independently testable, enables reuse without copy-paste. Low risk since it's a pure function with no side effects.

---

- Hotspot: Duplicate progress messages in AIPartCleanupTask
- Evidence: app/services/ai_part_cleanup_task.py:85-87
  ```python
  progress_handle.send_progress("Cleanup complete", 0.95)

  progress_handle.send_progress("Cleanup analysis ready", 1.0)
  ```
- Suggested refactor: Collapse these into a single final progress update: `progress_handle.send_progress("Cleanup analysis ready", 1.0)`. The intermediate "Cleanup complete" at 95% followed by "ready" at 100% is redundant since no work happens between them.
- Payoff: Simplifies task execution flow, reduces SSE message traffic, matches AIPartAnalysisTask pattern (single completion message at 100%). No functional impact on users.

---

## 5) Style & Consistency

- Pattern: BaseSessionTask.execute() wraps execute_session() with commit/rollback but cleanup task is read-only
- Evidence: app/services/ai_part_cleanup_task.py:24-97 (no writes), app/services/base_task.py:84-96 (commits session at line 88)
- Impact: Unnecessary commit for read-only task. While harmless (no data changes), it misrepresents transaction semantics. AIPartAnalysisTask has same pattern and also doesn't write data, so this is a project-wide consistency issue.
- Recommendation: Document in BaseSessionTask docstring that commit() is called even for read-only tasks (idempotent operation). Alternatively, add a read_only flag to BaseSessionTask constructor that skips commit when True, but this is likely over-engineering for the current scope.

---

- Pattern: Error message format inconsistency for RecordNotFoundException
- Evidence: tests/test_ai_part_cleanup_task.py:123 expects "Part ZZZZ was not found", but RecordNotFoundException generates "Part with key ZZZZ not found" (different phrasing)
- Impact: Test is checking for exception type correctly, but the error message assertion doesn't match actual exception format. This causes test fragility when exception messages change.
- Recommendation: Update test assertion at line 123 to match actual exception message format, or assert only on exception type without message content checks. Prefer loose message matching like `assert "ZZZZ" in result.error_message and "not found" in result.error_message`.

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

- Surface: AIPartCleanupTask.execute_session()
- Scenarios:
  - Given part exists with minimal data, When cleanup executes, Then returns CleanedPartDataSchema with all fields populated (tests/test_ai_part_cleanup_task.py::test_execute_success, lines 53-105)
  - Given part does not exist, When cleanup executes, Then raises RecordNotFoundException before starting task (tests/test_ai_part_cleanup_task.py::test_execute_part_not_found, lines 107-124)
  - Given cleanup task running, When user cancels, Then returns AIPartCleanupTaskCancelledResultSchema (tests/test_ai_part_cleanup_task.py::test_execute_task_cancelled_early, lines 162-178; test_execute_task_cancelled_during_cleanup, lines 180-223)
  - Given OpenAI API fails, When cleanup executes, Then returns error result with user-friendly message (tests/test_ai_part_cleanup_task.py::test_execute_ai_service_error, lines 126-141)
  - Given AI service raises InvalidOperationException, When cleanup executes, Then returns error result (tests/test_ai_part_cleanup_task.py::test_execute_invalid_operation_error, lines 143-160)
  - Given unexpected error during execution, When cleanup executes, Then returns error result (tests/test_ai_part_cleanup_task.py::test_execute_unexpected_error, lines 225-239)
  - Given successful cleanup, When task executes, Then progress reported in correct sequence (tests/test_ai_part_cleanup_task.py::test_execute_progress_reporting_sequence, lines 241-303)
- Hooks: Mock AIService, mock ProgressHandle, mock ServiceContainer with factory returning mocked service
- Gaps: Missing scenario "Given 100 other parts in inventory, When cleanup executes, Then context includes all 100 parts serialized correctly" (plan:540). Missing scenario "Given AI suggests type change, When cleanup executes, Then cleaned data includes new type name" (plan:543). Missing scenario "Given >10,000 parts in inventory, When cleanup executes, Then returns error" (plan:545). Missing service-level tests for AIService.cleanup_part() covering prompt building, tool selection, part count limits (see Finding 3).
- Evidence: tests/test_ai_part_cleanup_task.py:1-320 covers task orchestration; missing tests/services/test_ai_service.py coverage for cleanup_part()

---

- Surface: POST /api/ai-parts/cleanup
- Scenarios:
  - Given valid part_key, When POST cleanup, Then returns HTTP 201 with TaskStartResponse (missing explicit test, but covered implicitly via error case tests)
  - Given invalid part_key format, When POST cleanup, Then returns HTTP 400 with validation error (tests/test_ai_parts_cleanup_api.py::test_cleanup_part_invalid_part_key_format, lines 35-70)
  - Given part_key does not exist, When POST cleanup, Then returns HTTP 400 with "Part not found" error (tests/test_ai_parts_cleanup_api.py::test_cleanup_part_not_found, lines 72-85)
  - Given real_ai_allowed=False without dummy response, When POST cleanup, Then returns HTTP 400 with "AI disabled" error (tests/test_ai_parts_cleanup_api.py::test_cleanup_part_real_ai_disabled_guard, lines 87-113)
  - Given invalid JSON, When POST cleanup, Then returns HTTP 400 (tests/test_ai_parts_cleanup_api.py::test_cleanup_part_invalid_json, lines 13-22)
  - Given missing part_key, When POST cleanup, Then returns HTTP 400 (tests/test_ai_parts_cleanup_api.py::test_cleanup_part_missing_part_key, lines 24-33)
- Hooks: FlaskClient, Session, ServiceContainer for part creation
- Gaps: Missing positive test case "Given valid request with existing part and real_ai_allowed=True with OPENAI_DUMMY_RESPONSE_PATH, When POST cleanup, Then returns HTTP 201 with task_id and stream_url". Current tests only cover error paths, not the happy path.
- Evidence: tests/test_ai_parts_cleanup_api.py:1-135

---

- Surface: GET /api/ai-parts/cleanup/<task_id>/result
- Scenarios:
  - Given task does not exist, When GET result, Then returns HTTP 404 (tests/test_ai_parts_cleanup_api.py::test_get_cleanup_result_task_not_found, lines 115-125)
  - Given task not completed, When GET result, Then returns HTTP 404 with "Task not completed" message (tests/test_ai_parts_cleanup_api.py::test_get_cleanup_result_task_not_completed, lines 127-134, but test body is empty with `pass`)
- Hooks: FlaskClient, pre-completed tasks via TaskService
- Gaps: Missing scenario "Given completed cleanup task, When GET result, Then returns HTTP 200 with AIPartCleanupTaskResultSchema" (plan:580-585). Test at lines 127-134 has no implementation (just `pass` statement).
- Evidence: tests/test_ai_parts_cleanup_api.py:115-135

---

- Surface: Prompt template mode parameter
- Scenarios:
  - Mode conditionals exist in template (app/services/prompts/part_analysis.md:3-57)
  - Mode parameter passed correctly (app/services/ai_service.py:347 passes mode="cleanup")
- Hooks: Template rendering with Jinja2
- Gaps: No explicit tests verifying template rendering with mode="cleanup" vs mode="analysis" produces different content. Existing analyze_part() tests implicitly cover mode="analysis" default, but no test exercises cleanup mode rendering.
- Evidence: Plan:591-597 specifies template mode tests; none found in tests/services/test_ai_service.py

---

## 7) Adversarial Sweep (must attempt ≥3 credible failures or justify none)

**Check 1: Filtered query driving persistent write**
- Attack: Does cleanup_part() query use a filter that could omit parts, leading to incomplete context?
- Evidence: app/services/ai_service.py:267-269
  ```python
  all_parts_stmt = select(Part).where(Part.key != part_key).options(
      selectinload(Part.type),
      selectinload(Part.seller)
  )
  all_parts = self.db.execute(all_parts_stmt).scalars().all()
  ```
- Reasoning: Query correctly excludes only the target part by key. No soft-delete filter, no status filter, no hidden parts logic. All inventory parts are included. Since task is read-only, no persistent writes occur. Risk closed.
- Result: PASS

**Check 2: Session management and transaction boundaries**
- Attack: Could cleanup_part() leave session in dirty state or leak connections?
- Evidence: app/services/ai_part_cleanup_task.py:84-96 (BaseSessionTask.execute() wraps execute_session() with commit/rollback), app/services/ai_service.py:238-385 (cleanup_part() performs only SELECT queries)
- Reasoning: BaseSessionTask.execute() pattern (base_task.py:84-96) commits session at line 88, rolls back on exception at line 91, and resets session in finally block at line 95. AIService.cleanup_part() is read-only (no INSERT/UPDATE/DELETE), so commit is idempotent. Even if cleanup_part() raises exception, rollback and reset happen correctly. No session leakage possible.
- Result: PASS

**Check 3: Type field handling and creation responsibility**
- Attack: AI suggests type "Proposed: NewType" but CleanedPartDataSchema expects type name only. Will frontend handle "Proposed:" prefix?
- Evidence: app/services/ai_service.py:371 maps `type=analysis_details.product_category`, app/services/prompts/part_analysis.md:92-94 instructs "If none fits: 'Proposed: <name>'"
- Reasoning: PartAnalysisDetails.product_category can contain "Proposed: <name>" format. This is passed through verbatim to CleanedPartDataSchema.type field (line 371). Plan Section 3 (line 245) states "frontend maps type name→id before applying". The prompt correctly instructs AI to use "Proposed:" prefix for new types (part_analysis.md:94). However, frontend must handle two cases: (1) exact match to existing type.name, (2) "Proposed: X" format requiring type creation. This is a frontend requirement, not a backend bug.
- Result: PASS (backend correctly returns AI's suggestion; frontend responsible for parsing)

**Check 4: Part count limit enforcement timing**
- Attack: What if part count check passes but another request adds parts before serialization starts?
- Evidence: app/services/ai_service.py:272-276 checks `len(all_parts) > 10000` after executing query at line 269
- Reasoning: There's a TOCTOU (time-of-check-to-time-of-use) window between the count check and serialization loop, but: (1) task is read-only so concurrent writes don't corrupt cleanup operation, (2) if part count increases between check and serialization, we'll serialize more parts than the limit but not crash (Python list comprehension handles dynamic size), (3) worst case is slightly exceeding limit, which may cause AI context overflow but won't corrupt data. The risk is operational (AI performance degradation) rather than correctness (no data loss). Adding SELECT COUNT(*) before query would close window but adds extra query cost. Current approach is acceptable for 10k limit.
- Result: PASS (acceptable operational risk, no correctness issue)

**Check 5: Seller field preservation across cleanup**
- Attack: Does cleanup correctly preserve existing seller data when AI can't determine seller?
- Evidence: app/services/ai_service.py:379-382 hardcodes `seller=None, seller_link=None`
- Reasoning: This is Finding 1 (Major severity). target_part has seller and seller_link populated from database (serialized at line 306), but CleanedPartDataSchema unconditionally nulls these fields. Users will see seller data erased in cleanup diff. The comment "frontend handles this" is misleading—frontend can't restore data that backend discarded. This is a data loss bug.
- Result: FAIL (escalated as Major finding above)

**Check 6: Progress handle exceptions during SSE streaming**
- Attack: What if progress_handle.send_progress() raises exception (network disconnect)?
- Evidence: app/services/ai_part_cleanup_task.py:49, 58, 76, 85, 87 call send_progress() without try/except; outer try/except at line 93 catches all exceptions
- Reasoning: If send_progress() raises (e.g., SSE client disconnects), exception propagates to outer try/except at line 93, which returns AIPartCleanupTaskResultSchema(success=False, error_message="Unexpected error: ..."). Task service will handle the error result. However, the task will appear failed even though cleanup logic succeeded—it just couldn't report progress. This matches AIPartAnalysisTask pattern (ai_part_analysis_task.py:52-129 has same structure). Acceptable trade-off: if client disconnects, task result is marked failed, user must retry.
- Result: PASS (matches established pattern, acceptable behavior)

---

## 8) Invariants Checklist (stacked entries)

- Invariant: All parts except target must be included in cleanup context
  - Where enforced: app/services/ai_service.py:267-269 `select(Part).where(Part.key != part_key)`
  - Failure mode: If query adds filters (e.g., `where(Part.deleted == False)`), context would be incomplete
  - Protection: Query is explicit and unfiltered (only excludes target); no soft-delete or status filters exist in Part model (app/models/part.py:31-133 has no deleted flag)
  - Evidence: app/models/part.py:31-133 shows Part has no is_deleted or status column

---

- Invariant: Cleanup task must be read-only (no database writes)
  - Where enforced: app/services/ai_part_cleanup_task.py:24-97 calls only AIService.cleanup_part() which performs SELECT queries (app/services/ai_service.py:238-385)
  - Failure mode: If cleanup_part() adds INSERT/UPDATE/DELETE, task would mutate data and violate cancellation semantics
  - Protection: Code review confirms no db.add(), db.delete(), or model attribute assignments in cleanup_part(); only SELECT with options(selectinload())
  - Evidence: app/services/ai_service.py:260-306 only queries, no writes

---

- Invariant: CleanedPartDataSchema must include all fields even if unchanged
  - Where enforced: app/schemas/ai_part_cleanup.py:20-118 defines 17 fields with Optional types and defaults; app/services/ai_service.py:367-383 populates all fields
  - Failure mode: If cleanup_part() returns partial schema, frontend diff would treat missing fields as deletions
  - Protection: Pydantic schema validation enforces field presence; all fields explicitly assigned in cleanup_part() mapping (lines 367-383)
  - Evidence: app/schemas/ai_part_cleanup.py:28-116 shows all fields have defaults (None or [])

---

- Invariant: Task cancellation must be detected at phase boundaries
  - Where enforced: app/services/ai_part_cleanup_task.py:51-52, 72-73, 81-82 check `self.is_cancelled`
  - Failure mode: If cancellation check is missed, long-running AI call could complete despite user cancellation
  - Protection: Three cancellation checks: before AI call (line 51), after AI call (line 72), after processing (line 81); matches AIPartAnalysisTask pattern (ai_part_analysis_task.py:54-98)
  - Evidence: tests/test_ai_part_cleanup_task.py:162-223 verify cancellation handling at different points

---

## 9) Questions / Needs-Info

- Question: Should metrics_service be injected into AIPartCleanupTask or accessed via container?
- Why it matters: Plan Section 9 requires metrics instrumentation. AIPartAnalysisTask doesn't emit metrics directly (only AIService does via metrics_service injection). Need to clarify if cleanup task should record metrics at task level or only service level.
- Desired answer: Review MetricsService usage in AIPartAnalysisTask (app/services/ai_part_analysis_task.py) vs AIService (app/services/ai_service.py:54,69-71). If task-level metrics are needed, add metrics_service to container.ai_part_cleanup_task provider.

---

- Question: What is the expected frontend behavior for "Proposed: <type>" format?
- Why it matters: CleanedPartDataSchema.type can contain "Proposed: NewType" (plan:94). Need to confirm frontend parsing logic to ensure backend contract matches frontend expectations.
- Desired answer: Verify with frontend developer that type field is parsed for "Proposed:" prefix, extracted type name is checked against existing types, and new type creation flow is triggered when needed. Alternatively, backend could split "Proposed: X" into `type: "X", type_exists: false` fields for clearer contract.

---

- Question: Should test data (app/data/test_data/parts.json) be updated as part of this change?
- Why it matters: Plan Section 2 (line 202-204) specifies "Update test data JSON files to include realistic product_page, seller_link, and technical fields for at least 10 parts to support cleanup context testing." No changes to test data files found in diff.
- Desired answer: Confirm whether test data updates are required in this PR or deferred to separate commit. If required, update parts.json with 10+ parts having populated product_page, seller_link, package, pin_count, voltage_rating fields.

---

## 10) Risks & Mitigations (top 3)

- Risk: Seller data loss in production cleanups will require manual restoration
- Mitigation: Fix seller field handling (Finding 1) before merge. Add test case verifying existing seller name/link are preserved when AI doesn't populate those fields. Consider adding "fields_changed" list to result schema showing which fields actually changed vs preserved.
- Evidence: app/services/ai_service.py:379-382 hardcodes None values

---

- Risk: Missing metrics will prevent monitoring cleanup feature adoption and errors
- Mitigation: Implement metrics as specified in plan Section 9 (Finding 2). Add metrics_service calls at task start/end and record part count gauge. Verify metrics appear in /metrics endpoint before merge.
- Evidence: Plan:459-503 specifies 4 metrics; none found in implementation

---

- Risk: Incomplete service-level test coverage could miss bugs in production
- Mitigation: Add service tests for AIService.cleanup_part() covering prompt building, tool exclusion, part count limits, and field mapping (Finding 3). Follow test pattern from test_analyze_part() in tests/services/test_ai_service.py.
- Evidence: Plan:552-561 specifies service tests; only task tests exist

---

## 11) Confidence

Confidence: Medium — The implementation follows established patterns correctly and has good task-level test coverage, but three Major findings (seller data loss, missing metrics, no service tests) reduce confidence. Addressing these findings will raise confidence to High. The architectural approach is sound; issues are localized fixes rather than fundamental design problems.
