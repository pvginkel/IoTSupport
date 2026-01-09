# AI Testing Mode for Playwright — Technical Plan

## 0) Research Log & Findings

**Research Areas:**

1. **Current AI endpoint implementation** (`app/api/ai_parts.py`)
   - `/ai-parts/analyze` (POST) accepts multipart form data with text/image
   - `/ai-parts/cleanup` (POST) accepts JSON with `part_key`
   - Both endpoints have result endpoints: `/analyze/<task_id>/result` and `/cleanup/<task_id>/result`
   - Both validate inputs and check part existence before starting tasks
   - Both check `settings.real_ai_allowed` (derived from `DISABLE_REAL_AI_ANALYSIS`) and cache paths
   - When real AI is disabled and no cache exists, they return 400 error with `InvalidOperationException`

2. **Task infrastructure** (`app/services/task_service.py`)
   - Task IDs are generated via `uuid.uuid4()` in `start_task` method at line 137
   - Returns `TaskStartResponse` with `task_id` and `status` fields
   - Tasks are registered in `_tasks` and `_task_instances` dicts

3. **Testing infrastructure** (`app/api/testing.py`)
   - Blueprint exists at `/api/testing` with endpoints only available in testing mode
   - Includes `/sse/task-event` endpoint (lines 334-390) that allows sending fake task events to SSE connections
   - Uses `ConnectionManager` to verify connection exists and send events

4. **Configuration** (`app/config.py`)
   - `DISABLE_REAL_AI_ANALYSIS` exists at line 140-143
   - `real_ai_allowed` property at lines 282-284 returns `not self.DISABLE_REAL_AI_ANALYSIS`
   - When `FLASK_ENV=testing`, `DISABLE_REAL_AI_ANALYSIS` is auto-set to `True` (line 206)

5. **Test setup** (`tests/conftest.py`)
   - All tests set `DISABLE_REAL_AI_ANALYSIS=True` in test settings (line 56)
   - Tests expect 400 error when real AI is disabled and no cache exists

6. **Result endpoints usage**
   - Only one test references result endpoints: `test_ai_parts_cleanup_api.py` line 121
   - These endpoints were created for OpenAPI schema documentation (comments at lines 211-216 in `ai_parts.py`)
   - Frontend Playwright tests don't use them; they rely on SSE events

**Key Findings:**

- The current guard (`real_ai_allowed` check) prevents any task creation in testing mode
- The change brief wants to **bypass all validation** and return a random task ID without task registration
- This allows Playwright to use `/api/testing/sse/task-event` to send controlled events
- Result endpoints serve only documentation purposes and are unused by the frontend
- The environment variable name `DISABLE_REAL_AI_ANALYSIS` is confusing given the new usage pattern

**Conflicts Identified:**

None. The change is a clean extension of the testing infrastructure with removal of unused endpoints.

---

## 1) Intent & Scope

**User intent**

Enable Playwright end-to-end tests to exercise the full SSE flow for AI endpoints without mocking, by allowing AI endpoints to return dummy task IDs in testing mode that can be controlled via the `/api/testing/sse/task-event` endpoint.

**Prompt quotes**

"In testing mode, these endpoints should: Skip all validation (input requirements, part existence checks), Generate a random task ID (UUID), Return a TaskStartResponse with that ID immediately, Do nothing else (no task registration, no execution, no AI calls)"

"Rename DISABLE_REAL_AI_ANALYSIS to something more descriptive for this context (e.g., AI_TESTING_MODE or similar)"

**In scope**

- Remove unused result endpoints: `GET /ai-parts/analyze/<task_id>/result` and `GET /ai-parts/cleanup/<task_id>/result`
- Modify `/ai-parts/analyze` and `/ai-parts/cleanup` to skip validation and return random task IDs when in testing mode
- Rename `DISABLE_REAL_AI_ANALYSIS` environment variable to `AI_TESTING_MODE`
- Add logging when testing mode short-circuits AI endpoints
- Create `frontend_instructions.md` documenting the testing approach for the frontend developer

**Out of scope**

- Changing the SSE event sending mechanism (`/api/testing/sse/task-event` already exists)
- Modifying how tasks are executed or managed
- Changing the AI service implementation or cache behavior
- Updating the OpenAPI documentation generation approach

**Assumptions / constraints**

- The `/api/testing/sse/task-event` endpoint already exists and works correctly
- Playwright tests will establish SSE connections before calling AI endpoints
- Testing mode is determined by `settings.is_testing` (which checks `FLASK_ENV == "testing"`)
- The cache path behavior (`AI_ANALYSIS_CACHE_PATH`, `AI_CLEANUP_CACHE_PATH`) remains unchanged for integration tests that need deterministic AI responses

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Remove `GET /ai-parts/analyze/<task_id>/result` endpoint
- [ ] Remove `GET /ai-parts/cleanup/<task_id>/result` endpoint
- [ ] In testing mode, `/ai-parts/analyze` should skip validation and return a random task ID immediately without doing anything else
- [ ] In testing mode, `/ai-parts/cleanup` should skip validation and return a random task ID immediately without doing anything else
- [ ] Rename `DISABLE_REAL_AI_ANALYSIS` environment variable to a more descriptive name
- [ ] Add log messages when testing mode behavior is triggered
- [ ] Create `frontend_instructions.md` in the feature folder with guidance for updating Playwright tests

---

## 2) Affected Areas & File Map

- Area: `app/api/ai_parts.py` - `/ai-parts/analyze` endpoint
- Why: Add testing mode short-circuit that skips validation and returns random task ID
- Evidence: `app/api/ai_parts.py:42-129` — Current implementation validates inputs and starts real tasks

- Area: `app/api/ai_parts.py` - `/ai-parts/cleanup` endpoint
- Why: Add testing mode short-circuit that skips validation and returns random task ID
- Evidence: `app/api/ai_parts.py:261-314` — Current implementation validates part existence and starts real tasks

- Area: `app/api/ai_parts.py` - `/ai-parts/analyze/<task_id>/result` endpoint
- Why: Remove entire endpoint (lines 202-259) as it's unused
- Evidence: `app/api/ai_parts.py:202-259` — Endpoint definition; only used for OpenAPI schema

- Area: `app/api/ai_parts.py` - `/ai-parts/cleanup/<task_id>/result` endpoint
- Why: Remove entire endpoint (lines 317-410) as it's unused
- Evidence: `app/api/ai_parts.py:317-410` — Endpoint definition; only used for OpenAPI schema

- Area: `app/config.py` - Settings class
- Why: Rename `DISABLE_REAL_AI_ANALYSIS` to `AI_TESTING_MODE` and update property
- Evidence: `app/config.py:140-143` — Field definition; `app/config.py:282-284` — Property using the field

- Area: `app/config.py` - Environment-specific defaults
- Why: Update validator to set renamed `AI_TESTING_MODE` field
- Evidence: `app/config.py:206` — Sets `DISABLE_REAL_AI_ANALYSIS = True` when testing

- Area: `tests/conftest.py` - Test settings builder
- Why: Update to use renamed `AI_TESTING_MODE` field
- Evidence: `tests/conftest.py:56` — Sets `DISABLE_REAL_AI_ANALYSIS=True` in test config

- Area: `tests/test_ai_parts_api.py` - Test for disabled AI guard
- Why: Remove test for the old guard behavior since testing mode will return task IDs
- Evidence: `tests/test_ai_parts_api.py:74-87` — Tests the 400 error response

- Area: `tests/test_ai_parts_cleanup_api.py` - Test for disabled AI guard
- Why: Remove test for the old guard behavior since testing mode will return task IDs
- Evidence: `tests/test_ai_parts_cleanup_api.py:87-113` — Tests the 400 error response

- Area: `tests/test_ai_parts_cleanup_api.py` - Test for result endpoint
- Why: Remove test for deleted result endpoint
- Evidence: `tests/test_ai_parts_cleanup_api.py:115-126` — Tests result endpoint not found

- Area: `app/services/ai_service.py` - AIService constructor
- Why: No changes needed — property name `real_ai_allowed` preserved
- Evidence: `app/services/ai_service.py:72` — Uses `config.real_ai_allowed` (unchanged)

- Area: `app/services/container.py` - AIRunner provider
- Why: Verify compatibility — uses `cfg.real_ai_allowed` in lambda expression
- Evidence: `app/services/container.py:216` — `AIRunner(cfg.OPENAI_API_KEY, metrics) if cfg.real_ai_allowed and cfg.OPENAI_API_KEY else None`

- Area: `docs/features/ai_testing_mode/frontend_instructions.md` (new file)
- Why: Document the testing approach for frontend developers
- Evidence: N/A — New file

---

## 3) Data Model / Contracts

- Entity / contract: `TaskStartResponse` (response body for AI endpoints in testing mode)
- Shape: Unchanged — `{"task_id": "uuid-string", "status": "pending"}`
- Refactor strategy: No changes to schema; only behavior differs in testing mode
- Evidence: `app/schemas/task_schema.py:54-58` — Schema definition

- Entity / contract: Environment variable `DISABLE_REAL_AI_ANALYSIS` → `AI_TESTING_MODE`
- Shape: Boolean environment variable
- Refactor strategy: Direct rename; no backwards compatibility needed per BFF pattern
- Evidence: `app/config.py:140-143` — Field definition

- Entity / contract: Configuration property `real_ai_allowed` (unchanged name)
- Shape: Boolean property computed from environment variable
- Refactor strategy: Keep property name, derive from new field: `return not self.AI_TESTING_MODE` (preserves semantic meaning "can make real AI calls")
- Evidence: `app/config.py:282-284` — Property definition

---

## 4) API / Integration Surface

- Surface: DELETE `GET /ai-parts/analyze/<task_id>/result`
- Inputs: N/A (endpoint removed)
- Outputs: N/A (endpoint removed)
- Errors: N/A (endpoint removed)
- Evidence: `app/api/ai_parts.py:202-259` — Endpoint being removed

- Surface: DELETE `GET /ai-parts/cleanup/<task_id>/result`
- Inputs: N/A (endpoint removed)
- Outputs: N/A (endpoint removed)
- Errors: N/A (endpoint removed)
- Evidence: `app/api/ai_parts.py:317-410` — Endpoint being removed

- Surface: MODIFIED `POST /ai-parts/analyze`
- Inputs: Multipart form-data with optional `text` and `image` (unchanged in signature, but not validated in testing mode)
- Outputs: In testing mode: `{"task_id": "<random-uuid>", "status": "pending"}` with HTTP 201. In production: unchanged behavior (starts real task)
- Errors: In testing mode: none (validation skipped). In production: unchanged (400 for invalid content type, missing input, unsupported image, disabled AI without cache)
- Evidence: `app/api/ai_parts.py:42-129` — Current endpoint implementation

- Surface: MODIFIED `POST /ai-parts/cleanup`
- Inputs: JSON with `part_key` (unchanged in signature, but not validated in testing mode)
- Outputs: In testing mode: `{"task_id": "<random-uuid>", "status": "pending"}` with HTTP 201. In production: unchanged behavior (starts real task)
- Errors: In testing mode: none (validation skipped). In production: unchanged (400 for invalid JSON, missing part_key, part not found, disabled AI without cache)
- Evidence: `app/api/ai_parts.py:261-314` — Current endpoint implementation

---

## 5) Algorithms & State Machines

- Flow: `/ai-parts/analyze` request handling
- Steps:
  1. Check if `settings.is_testing` is true
  2. If testing mode: generate random UUID, log testing mode activation, return `TaskStartResponse` immediately
  3. If production mode: execute existing validation and task start logic (unchanged)
- States / transitions: None (stateless request handling)
- Hotspots: No complexity added; early return in testing mode is fast path
- Evidence: `app/api/ai_parts.py:42-129` — Endpoint logic to be modified

- Flow: `/ai-parts/cleanup` request handling
- Steps:
  1. Check if `settings.is_testing` is true
  2. If testing mode: generate random UUID, log testing mode activation, return `TaskStartResponse` immediately
  3. If production mode: execute existing validation and task start logic (unchanged)
- States / transitions: None (stateless request handling)
- Hotspots: No complexity added; early return in testing mode is fast path
- Evidence: `app/api/ai_parts.py:261-314` — Endpoint logic to be modified

---

## 6) Derived State & Invariants

None. This change does not introduce derived state that drives persistent writes or cleanup. The testing mode short-circuit returns ephemeral task IDs that are never registered in `TaskService` and have no lifecycle beyond the HTTP response.

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: N/A — Testing mode endpoints return immediately without database access
- Atomic requirements: None — No database writes or task registration in testing mode
- Retry / idempotency: Not applicable — Endpoints are stateless and generate fresh UUIDs on each call
- Ordering / concurrency controls: None — No shared state modified in testing mode
- Evidence: `app/api/ai_parts.py:42-129, 261-314` — Endpoints that will short-circuit before any database interaction

---

## 8) Errors & Edge Cases

- Failure: Testing mode endpoint called in production
- Surface: N/A — `settings.is_testing` is false in production, so testing mode code path never executes
- Handling: Production behavior unchanged; no risk of testing mode activation outside test environment
- Guardrails: `settings.is_testing` derived from `FLASK_ENV == "testing"`
- Evidence: `app/config.py:277-279` — Property definition

- Failure: Playwright test calls AI endpoint before establishing SSE connection
- Surface: Test code responsibility (out of scope for backend)
- Handling: Backend returns task ID successfully; test must handle missing connection
- Guardrails: Frontend instructions will document proper sequence
- Evidence: `docs/features/ai_testing_mode/frontend_instructions.md` — Will document this

- Failure: Integration tests that rely on cache paths stop working
- Surface: Integration tests using `AI_ANALYSIS_CACHE_PATH` or `AI_CLEANUP_CACHE_PATH`
- Handling: Testing mode short-circuit happens first (checks `settings.is_testing`), before cache path checks; integration tests must use `FLASK_ENV=development` or another non-testing value
- Guardrails: The `is_testing` check uses `FLASK_ENV == "testing"`, not the `AI_TESTING_MODE` field. This separates:
  - **Playwright tests**: `FLASK_ENV=testing` → testing mode short-circuit (return dummy task IDs)
  - **Integration tests with cache replay**: `FLASK_ENV=development` + cache paths → real flow with cached AI responses
- Evidence: `app/api/ai_parts.py:106-117, 296-307` — Cache path checks that require non-testing environment

---

## 9) Observability / Telemetry

- Signal: Log message when testing mode skips AI endpoint validation
- Type: Structured log (INFO level)
- Trigger: When `settings.is_testing` is true and AI endpoint is called
- Labels / fields: endpoint name (`/ai-parts/analyze` or `/ai-parts/cleanup`), generated task_id
- Consumer: Test logs, debugging
- Evidence: `app/api/ai_parts.py:35` — Logger instance

- Signal: Existing AI metrics remain unchanged
- Type: N/A
- Trigger: Testing mode does not execute AI service, so no metrics emitted
- Labels / fields: N/A
- Consumer: Production monitoring only
- Evidence: `app/services/ai_service.py` — AI service not invoked in testing mode

---

## 10) Background Work & Shutdown

None. Testing mode does not register tasks with `TaskService`, so no background work is initiated and no shutdown coordination is required.

---

## 11) Security & Permissions

Not applicable. Testing endpoints are already protected by `before_request` check requiring `FLASK_ENV=testing` (see `app/api/testing.py:40-56`). The AI endpoints' testing mode uses the same mechanism via `settings.is_testing`.

---

## 12) UX / UI Impact

- Entry point: Playwright test suite (frontend repository)
- Change: Tests can now call real backend AI endpoints instead of mocking responses
- User interaction: Playwright tests establish SSE connection, call AI endpoint to get task_id, then use `/api/testing/sse/task-event` to send controlled events
- Dependencies: Existing `/api/testing/sse/task-event` endpoint; SSE connection infrastructure
- Evidence: `app/api/testing.py:334-390` — Endpoint for sending test events

---

## 13) Deterministic Test Plan

- Surface: `POST /ai-parts/analyze` in testing mode
- Scenarios:
  - Given FLASK_ENV=testing, When POST to /ai-parts/analyze with any payload, Then receive 201 with random task_id
  - Given FLASK_ENV=testing, When POST to /ai-parts/analyze with empty payload, Then receive 201 (no validation)
  - Given FLASK_ENV=testing, When POST to /ai-parts/analyze with invalid content type, Then receive 201 (no validation)
- Fixtures / hooks: Use existing `app` fixture with `test_settings` (already sets FLASK_ENV=testing)
- Gaps: None
- Evidence: `tests/test_ai_parts_api.py` — Existing test file; `tests/conftest.py:49-70` — Test settings fixture

- Surface: `POST /ai-parts/cleanup` in testing mode
- Scenarios:
  - Given FLASK_ENV=testing, When POST to /ai-parts/cleanup with any part_key, Then receive 201 with random task_id
  - Given FLASK_ENV=testing, When POST to /ai-parts/cleanup with non-existent part, Then receive 201 (no validation)
  - Given FLASK_ENV=testing, When POST to /ai-parts/cleanup with invalid JSON, Then receive 201 (no validation)
- Fixtures / hooks: Use existing `app` fixture with `test_settings`
- Gaps: None
- Evidence: `tests/test_ai_parts_cleanup_api.py` — Existing test file

- Surface: Production behavior verification (non-testing mode)
- Scenarios:
  - Given FLASK_ENV=development AND AI_TESTING_MODE=True AND no cache, When POST to /ai-parts/analyze with text, Then receive 400 error (not testing mode short-circuit)
  - Given FLASK_ENV=development AND AI_TESTING_MODE=True AND no cache, When POST to /ai-parts/cleanup with part_key, Then receive 400 error (not testing mode short-circuit)
- Fixtures / hooks: Create dedicated `production_like_settings` fixture with `is_testing=False` and `real_ai_allowed=False`
- Gaps: None
- Evidence: Ensures testing mode only activates when `FLASK_ENV=testing`, not just when `AI_TESTING_MODE=True`

- Surface: Deleted result endpoints
- Scenarios:
  - Given any environment, When GET /ai-parts/analyze/<task_id>/result, Then receive 404 (endpoint removed)
  - Given any environment, When GET /ai-parts/cleanup/<task_id>/result, Then receive 404 (endpoint removed)
- Fixtures / hooks: Standard client fixture
- Gaps: None
- Evidence: `app/api/ai_parts.py:202-259, 317-410` — Endpoints being removed

- Surface: Configuration rename (`DISABLE_REAL_AI_ANALYSIS` → `AI_TESTING_MODE`)
- Scenarios:
  - Given AI_TESTING_MODE=True, When creating Settings, Then settings.real_ai_allowed is False (inverted logic preserved)
  - Given AI_TESTING_MODE=False, When creating Settings, Then settings.real_ai_allowed is True
  - Given FLASK_ENV=testing, When creating Settings, Then AI_TESTING_MODE auto-set to True (and real_ai_allowed is False)
- Fixtures / hooks: Direct Settings instantiation
- Gaps: None
- Evidence: `app/config.py:140-143, 200-207` — Field and validator

---

## 14) Implementation Slices

This change is small enough to implement as a single slice, but can be broken down for clarity:

- Slice: Configuration field rename
- Goal: Rename environment variable `DISABLE_REAL_AI_ANALYSIS` to `AI_TESTING_MODE`, keep `real_ai_allowed` property with inverted logic
- Touches: `app/config.py`, `tests/conftest.py`
- Dependencies: Must complete first to avoid name conflicts

- Slice: Remove unused result endpoints
- Goal: Clean up endpoints that frontend doesn't use
- Touches: `app/api/ai_parts.py` (delete two functions), `tests/test_ai_parts_cleanup_api.py` (delete one test)
- Dependencies: Configuration rename complete

- Slice: Add testing mode short-circuit to AI endpoints
- Goal: Enable Playwright testing without mocks
- Touches: `app/api/ai_parts.py` (add testing mode checks to analyze and cleanup endpoints), `tests/test_ai_parts_api.py` (remove/update tests), `tests/test_ai_parts_cleanup_api.py` (remove/update tests)
- Dependencies: Result endpoints removed

- Slice: Frontend instructions
- Goal: Document testing approach for frontend developers
- Touches: `docs/features/ai_testing_mode/frontend_instructions.md`
- Dependencies: Backend changes complete

---

## 15) Risks & Open Questions

**Risks:**

- Risk: Integration tests using cache paths might break
- Impact: Tests that rely on `AI_ANALYSIS_CACHE_PATH` or `AI_CLEANUP_CACHE_PATH` for deterministic responses
- Mitigation: Integration tests should run with `FLASK_ENV=development` instead of `testing`, or explicitly check environment and adjust expectations

- Risk: Existing Playwright tests might fail temporarily
- Impact: Frontend tests currently mocking AI responses will need updates
- Mitigation: Create clear frontend instructions; coordinate deployment with frontend developer

- Risk: Configuration property semantics could confuse future developers
- Impact: Field is now `AI_TESTING_MODE` (positive) but property remains `real_ai_allowed` (negative)
- Mitigation: Keep property name `real_ai_allowed` with `return not self.AI_TESTING_MODE` to preserve existing semantic meaning across codebase

**Open Questions:**

None. The change is well-scoped and straightforward.

---

## 16) Confidence

Confidence: High — The change is small, well-understood, and follows existing patterns. Testing mode infrastructure already exists (`/api/testing` blueprint, SSE event injection). The endpoints are simple HTTP handlers with clear control flow. Risk is minimal because testing mode is isolated by `FLASK_ENV` check.
