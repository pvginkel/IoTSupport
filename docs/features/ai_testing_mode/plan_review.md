# Plan Review — AI Testing Mode for Playwright

## 1) Summary & Decision

**Readiness**

The plan is well-structured and demonstrates thorough research of the codebase. The intent is clear: enable Playwright tests to exercise SSE flows by having AI endpoints return dummy task IDs in testing mode. The approach is sound—short-circuiting AI endpoints before validation to return random UUIDs allows frontend tests to control task events via the existing `/api/testing/sse/task-event` endpoint. However, there are several critical issues with the configuration property renaming logic and missing coverage for important edge cases. The plan also lacks clarity on how integration tests that currently rely on cache paths will be handled.

**Decision**

`GO-WITH-CONDITIONS` — The core approach is solid and follows existing patterns, but the configuration property refactor introduces semantic confusion that could mislead future developers. Additionally, the test plan has gaps around ensuring production behavior remains unchanged, and there's insufficient guidance on how existing integration tests should adapt.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md` — Pass — `plan.md:148-151` — Plan correctly identifies need for new `frontend_instructions.md` and follows BFF pattern (no backwards compatibility)
- `CLAUDE.md` — Pass — `plan.md:303-340` — Test plan includes service tests and API tests with Given/When/Then scenarios
- `CLAUDE.md` — Partial — `plan.md:168-171` — Property rename inverts semantics (`real_ai_allowed` becomes `ai_testing_mode_enabled`), which violates clarity principle in error handling philosophy
- `docs/product_brief.md` — Pass — Plan does not conflict with product brief; testing infrastructure is implementation detail

**Fit with codebase**

- `app/api/testing.py` — Pass — `plan.md:288, 296-298` — Correctly identifies existing SSE event injection infrastructure and proper `settings.is_testing` guard
- `app/services/container.py:216` — Gap — Plan does not address `AIRunner` provider which uses `cfg.real_ai_allowed` in lambda expression
- `app/services/ai_service.py:72, 81` — Pass — `plan.md:145-148` — Plan identifies usage in AIService constructor
- `tests/conftest.py:56` — Pass — `plan.md:129-132` — Plan correctly identifies test settings update needed
- `tests/test_ai_service.py` — Gap — Plan does not mention test file that uses `DISABLE_REAL_AI_ANALYSIS=True` in settings construction (line 33)

---

## 3) Open Questions & Ambiguities

- Question: How should integration tests that currently rely on cache paths (`AI_ANALYSIS_CACHE_PATH`, `AI_CLEANUP_CACHE_PATH`) be adapted?
- Why it matters: The plan states testing mode short-circuits before cache path checks (plan.md:254-258), but doesn't specify whether integration tests should change environment or if a feature flag is needed
- Needed answer: Decision on whether integration tests should use `FLASK_ENV=development` or if an additional configuration flag should control testing mode behavior

- Question: What is the intended semantics of the new configuration property `ai_testing_mode_enabled`?
- Why it matters: The old property `real_ai_allowed` meant "AI can make real API calls", but new property name suggests "testing mode is active", which has different implications (testing mode affects more than just AI)
- Needed answer: Clarification on whether property should reflect AI capability or testing mode state

- Question: Should testing mode be a mode that can be enabled independently of `FLASK_ENV=testing`?
- Why it matters: The plan ties testing mode to `settings.is_testing` (which checks `FLASK_ENV == "testing"`), but the configuration field rename suggests it could be a separate control
- Needed answer: Confirmation that testing mode short-circuit should always be tied to `FLASK_ENV=testing` and never independently configurable

---

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: `POST /ai-parts/analyze` in testing mode
- Scenarios:
  - Given FLASK_ENV=testing, When POST with valid multipart data, Then receive 201 with random UUID (`tests/test_ai_parts_api.py::test_analyze_testing_mode_returns_task_id`)
  - Given FLASK_ENV=testing, When POST with empty/invalid payload, Then receive 201 (validation skipped) (`tests/test_ai_parts_api.py::test_analyze_testing_mode_skips_validation`)
  - Given FLASK_ENV=production AND real_ai_allowed=False, When POST with text, Then receive 400 error (existing guard behavior) (`tests/test_ai_parts_api.py::test_analyze_production_guard_unchanged`)
- Instrumentation: INFO log when testing mode activates (plan.md:263-269)
- Persistence hooks: None (testing mode is stateless)
- Gaps: No test verifies that production behavior is unchanged when `FLASK_ENV != "testing"`
- Evidence: `plan.md:304-312`

- Behavior: `POST /ai-parts/cleanup` in testing mode
- Scenarios:
  - Given FLASK_ENV=testing, When POST with any part_key, Then receive 201 with random UUID (`tests/test_ai_parts_cleanup_api.py::test_cleanup_testing_mode_returns_task_id`)
  - Given FLASK_ENV=testing, When POST with non-existent part, Then receive 201 (validation skipped) (`tests/test_ai_parts_cleanup_api.py::test_cleanup_testing_mode_skips_validation`)
  - Given FLASK_ENV=production AND real_ai_allowed=False, When POST with part_key, Then receive 400 error (existing guard behavior) (missing test)
- Instrumentation: INFO log when testing mode activates
- Persistence hooks: None
- Gaps: Missing explicit test that production guard still works after changes
- Evidence: `plan.md:314-322`

- Behavior: Configuration field rename (`DISABLE_REAL_AI_ANALYSIS` → `AI_TESTING_MODE`)
- Scenarios:
  - Given AI_TESTING_MODE=True, When Settings created, Then ai_testing_mode_enabled is True (`tests/test_config.py::test_ai_testing_mode_enabled`)
  - Given FLASK_ENV=testing, When Settings created, Then AI_TESTING_MODE auto-set to True (`tests/test_config.py::test_testing_env_sets_ai_testing_mode`)
- Instrumentation: None needed
- Persistence hooks: None
- Gaps: No test verifies that AIService initialization respects new property name; no test for AIRunner provider in container
- Evidence: `plan.md:332-339`

- Behavior: Deleted result endpoints
- Scenarios:
  - Given any environment, When GET /ai-parts/analyze/{task_id}/result, Then receive 404 (`tests/test_ai_parts_api.py::test_analyze_result_endpoint_removed`)
  - Given any environment, When GET /ai-parts/cleanup/{task_id}/result, Then receive 404 (`tests/test_ai_parts_cleanup_api.py::test_cleanup_result_endpoint_removed`)
- Instrumentation: None
- Persistence hooks: None
- Gaps: None
- Evidence: `plan.md:324-330`

---

## 5) Adversarial Sweep (must find ≥3 credible issues or declare why none exist)

**Major — Configuration property semantic inversion introduces confusion**
**Evidence:** `plan.md:168-171` — "Property: Old property `real_ai_allowed` returned `not DISABLE_REAL_AI_ANALYSIS`; new property `ai_testing_mode_enabled` returns `AI_TESTING_MODE` directly"
**Why it matters:** The old property `real_ai_allowed` had clear semantics: "can the system make real AI API calls?" The new property `ai_testing_mode_enabled` inverts this to "is testing mode active?" This creates confusion because:
1. Testing mode affects more than just AI (it also enables `/api/testing` endpoints)
2. The property is used in `AIService` constructor (ai_service.py:72) where the semantic should be "AI capability", not "testing state"
3. The `AIRunner` provider in container.py:216 uses `cfg.real_ai_allowed` to decide whether to instantiate the runner—this should reflect AI capability, not testing mode
**Fix suggestion:** Keep property name as `real_ai_allowed` and derive it from the new field: `@property def real_ai_allowed(self) -> bool: return not self.AI_TESTING_MODE`. This maintains semantic clarity while enabling the rename.
**Confidence:** High

**Major — Missing AIRunner provider update in affected areas**
**Evidence:** `app/services/container.py:216` — `lambda cfg, metrics: AIRunner(cfg.OPENAI_API_KEY, metrics) if cfg.real_ai_allowed and cfg.OPENAI_API_KEY else None`
**Why it matters:** The plan lists affected areas (plan.md:102-151) but omits the AIRunner provider definition in container.py. This provider uses `cfg.real_ai_allowed` in a lambda expression and must be verified to work correctly with the renamed configuration. If the property is renamed to `ai_testing_mode_enabled` without inverting the logic, this provider will break.
**Fix suggestion:** Add `app/services/container.py` to affected areas (section 2) with evidence at line 216. Verify that property semantics remain compatible or update the lambda expression.
**Confidence:** High

**Major — Test plan missing verification that production behavior unchanged**
**Evidence:** `plan.md:304-322` — Test scenarios for testing mode behavior but no explicit test for production guard preservation
**Why it matters:** The plan removes tests for the old guard behavior (plan.md:133-143) but doesn't add tests confirming that production mode still returns 400 errors when `real_ai_allowed=False` and no cache exists. This creates a coverage gap where production behavior could regress without detection.
**Fix suggestion:** Add test scenarios: "Given FLASK_ENV=production AND DISABLE_REAL_AI_ANALYSIS=True (or AI_TESTING_MODE=True), When POST to AI endpoints, Then receive 400 error (not testing mode short-circuit)". This ensures `settings.is_testing` check prevents testing mode from activating in production even if the configuration field is set.
**Confidence:** High

**Minor — Integration test guidance incomplete**
**Evidence:** `plan.md:254-258` — "Integration tests should use development or dedicated environment"
**Why it matters:** The plan mentions that integration tests using cache paths will be affected but doesn't provide concrete migration guidance. Integration tests might currently set `FLASK_ENV=testing` with cache paths to get deterministic responses. If testing mode now short-circuits before cache checks, these tests will break.
**Fix suggestion:** Add explicit guidance in section 8 (Errors & Edge Cases) on how to adapt integration tests: either use `FLASK_ENV=development` or add a recommendation to separate "cache replay testing" from "Playwright SSE testing" into different test suites with different environment configurations.
**Confidence:** Medium

---

## 6) Derived-Value & Persistence Invariants (stacked entries)

None; proof: The testing mode change is stateless and introduces no derived values that trigger persistence operations. The returned task IDs are ephemeral and never registered in TaskService (plan.md:282), so they have no lifecycle that could affect database state or storage. The existing AI endpoints' production behavior with cache paths (lines 106-117, 296-307 in ai_parts.py) remains unchanged and was previously reviewed.

---

## 7) Risks & Mitigations (top 3)

- Risk: Configuration property semantic confusion leads to incorrect usage in future features
- Impact: Developers might set `ai_testing_mode_enabled=True` expecting to disable AI, but the property name suggests "enable testing mode" which affects more than just AI capability
- Mitigation: Keep property name as `real_ai_allowed` and derive from `AI_TESTING_MODE` field, or rename to `ai_capability_disabled` to match the field semantics more closely
- Evidence: `plan.md:168-171, app/services/ai_service.py:72`

- Risk: Integration tests using cache paths break when testing mode short-circuits
- Impact: Tests that currently set `FLASK_ENV=testing` with `AI_ANALYSIS_CACHE_PATH` to replay cached responses will fail because testing mode bypasses cache checks
- Mitigation: Document in frontend_instructions.md that cache-based tests should use `FLASK_ENV=development` instead, or add test suite configuration guidance to separate Playwright tests from integration tests
- Evidence: `plan.md:254-258, app/api/ai_parts.py:106-117`

- Risk: Removing old guard tests without adding production behavior verification creates regression risk
- Impact: If the `settings.is_testing` check is accidentally removed or misconfigured, production could start returning random task IDs instead of proper error messages
- Mitigation: Add explicit tests that verify production mode still returns 400 errors when AI is disabled without cache, ensuring testing mode doesn't activate in production environments
- Evidence: `plan.md:133-143 (tests being removed), plan.md:304-322 (test plan)`

---

## 8) Confidence

Confidence: Medium — The core technical approach is sound and leverages existing infrastructure correctly (testing blueprint guard, SSE event injection). However, the configuration refactor introduces semantic confusion that could mislead future developers and impact maintainability. The test plan has gaps around production behavior verification and integration test migration guidance. These issues are fixable with the suggested changes, but they represent important architectural decisions that should be clarified before implementation.
