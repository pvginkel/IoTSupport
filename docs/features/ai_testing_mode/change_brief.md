# Change Brief: AI Testing Mode for Playwright

## Summary

Modify the AI endpoints (`/ai-parts/analyze` and `/ai-parts/cleanup`) to support Playwright end-to-end testing without mocking. In testing mode, these endpoints should return a task ID immediately without performing any actual work, allowing the Playwright test suite to send fake SSE events via the existing `/api/testing/sse/task-event` endpoint.

## Changes Required

### 1. Remove Unused Result Endpoints

Remove the following endpoints as they are no longer used:
- `GET /ai-parts/analyze/<task_id>/result`
- `GET /ai-parts/cleanup/<task_id>/result`

### 2. Testing Mode Behavior for AI Endpoints

When in testing mode, the `/ai-parts/analyze` and `/ai-parts/cleanup` endpoints should:
- Skip all validation (input requirements, part existence checks)
- Generate a random task ID (UUID)
- Return a `TaskStartResponse` with that ID immediately
- Do nothing else (no task registration, no execution, no AI calls)

This allows Playwright tests to:
1. Connect to SSE stream (obtaining a `request_id`)
2. Call the AI endpoint to get a `task_id`
3. Use `/api/testing/sse/task-event` to send controlled events to their connection
4. Test the full SSE flow without mocking

### 3. Rename Environment Variable

Rename `DISABLE_REAL_AI_ANALYSIS` to something more descriptive for this context (e.g., `AI_TESTING_MODE` or similar).

### 4. Add Logging

Add log messages when testing mode is active to provide visibility into this behavior.

### 5. Frontend Instructions

Document the new testing approach for the frontend developer so they can update Playwright tests to use real backend calls instead of mocks.

## Rationale

The previous approach of mocking AI responses in Playwright tests caused problems because mocks did not accurately represent real backend behavior. Using the real backend with controlled SSE events provides more realistic testing while maintaining determinism.
