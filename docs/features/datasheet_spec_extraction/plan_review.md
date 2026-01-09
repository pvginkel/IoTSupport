# Datasheet Spec Extraction — Plan Review

## 1) Summary & Decision

**Readiness**

The plan is well-structured and follows established AIFunction patterns. It demonstrates thorough research into the OpenAI API, service container wiring, and existing codebase patterns. After review, all blocking issues have been resolved: (1) OpenAI file upload corrected to use `purpose="user_data"` (Responses API standard), (2) temp file lifecycle now includes explicit implementation details with atomic writes and cleanup sequencing, (3) test coverage expanded to include file deletion failure scenarios and integration test strategy, and (4) prompt duplication maintenance burden addressed via Jinja2 include pattern for shared normalization rules.

**Decision**

`GO` — All blocking issues resolved; plan now includes correct OpenAI API usage, explicit temp file lifecycle management, comprehensive test coverage for cleanup paths, and DRY prompt architecture. Implementation ready to proceed.

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md` AIFunction pattern — Pass — `plan.md:7-12, 129-131` — "Examined existing AI functions... All follow abstract base class AIFunction"
- `CLAUDE.md` Error handling philosophy — Pass — `plan.md:335-370` — "function catches and returns error response" (graceful degradation matches fail-fast with controlled boundaries)
- `CLAUDE.md` Time measurements — Pass — `plan.md:79, 386` — Uses `time.perf_counter()` for duration measurements via OpenAIRunner
- `CLAUDE.md` Dependency injection — Pass — `plan.md:157-168` — Service container wiring follows Factory provider pattern
- `CLAUDE.md` Testing requirements — Partial — `plan.md:420-459` — Scenarios present but gaps noted below
- `docs/product_brief.md` AI helpers — Pass — `plan.md:64-72` — Feature aligns with "fetch a datasheet PDF" from product brief section 9

**Fit with codebase**

- `app/utils/ai/openai/openai_runner.py:47-99` — `plan.md:145-147` — Plan assumes modifying `run()` to handle attachments, which fits with current structure
- `app/utils/ai/ai_runner.py:29-42` — `plan.md:220-227` — Adding optional `attachments` field maintains backward compatibility
- `app/services/container.py:269-290` — `plan.md:157-159` — Wiring pattern matches existing AIFunction registration
- `app/services/prompts/part_analysis.md:158-166` — `plan.md:153-155` — Plan correctly identifies need to add datasheet priority instruction
- `TempFileManager` usage — `plan.md:318-323` — Plan assumes TempFileManager handles cleanup but lacks details on how function creates/manages temp files

## 3) Open Questions & Ambiguities

- Question: Which OpenAI API will actually be used for PDF upload - Responses API or Assistants API?
- Why it matters: The plan at lines 113-115 specifies using `client.files.create(file=..., purpose="assistants")` which is the **Assistants API** pattern. However, the current codebase uses **Responses API** (lines 14-17 note "OpenAI Responses API supports file uploads"). These are fundamentally different APIs with different upload mechanisms. The Responses API does not use `client.files.create()` at all.
- Needed answer: Confirm that Responses API supports PDF attachments and specify the exact API method (likely requires passing file content directly in message content, not via separate upload)

- Question: How exactly will the function create temporary files from downloaded PDF bytes?
- Why it matters: Plan mentions "Write PDF bytes to temporary file for OpenAI upload" (line 279) and "TempFileManager usage" (line 318-323) but provides no concrete implementation detail on the write path, file handle management, or cleanup timing relative to the `finally` block.
- Needed answer: Specify whether function calls `TempFileManager.create_temp_directory()` and manually writes bytes, or if a new helper method is needed; clarify cleanup coordination between OpenAI file deletion and TempFileManager cleanup

- Question: What happens if PDF download succeeds but writing to temp file fails?
- Why it matters: Error handling section (lines 335-370) covers download failure and upload failure but omits the intermediate temp file creation step; this gap could leave partial files or unclear error messages.
- Needed answer: Add error case for temp file write failure with specific handling (error response, no OpenAI call attempted)

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: ExtractSpecsFromDatasheetFunction.execute()
- Scenarios:
  - Given valid PDF URL and matching analysis query, When function executes, Then response contains specs with normalized fields (`tests/test_datasheet_extraction.py::test_extract_specs_success`)
  - Given valid PDF URL but non-matching analysis query, When LLM validates, Then response contains error explaining mismatch (`tests/test_datasheet_extraction.py::test_extract_specs_validation_failure`)
  - Given non-PDF URL, When DocumentService validates, Then function catches exception and returns error response (`tests/test_datasheet_extraction.py::test_extract_specs_non_pdf_url`)
  - Given PDF download failure (404), When DocumentService attempts download, Then function catches exception and returns error response (`tests/test_datasheet_extraction.py::test_extract_specs_download_failure`)
- Instrumentation: Function execution logged (analysis_query snippet, datasheet_url, file_id, errors); OpenAI metrics via existing `record_ai_analysis()` (duration, tokens, cost, status)
- Persistence hooks: None (no DB operations); DI wiring in ServiceContainer; no migrations or test data updates needed
- Gaps: Test plan omits scenario for temp file write failure between download and upload; missing test for OpenAI file deletion failure (finally block swallows error)
- Evidence: `plan.md:420-431, 373-406`

- Behavior: OpenAIRunner.run() with attachments
- Scenarios:
  - Given AIRequest with single attachment path, When run() executes, Then PDF uploaded to OpenAI, file_id included in message, file deleted after API call (`tests/test_openai_runner.py::test_run_with_single_attachment`)
  - Given AIRequest with multiple attachments, When run() executes, Then all files uploaded, all included in message, all deleted (`tests/test_openai_runner.py::test_run_with_multiple_attachments`)
  - Given file upload failure, When client.files.create() raises, Then exception propagates, no file deletion attempted (`tests/test_openai_runner.py::test_run_attachment_upload_failure`)
  - Given no attachments, When run() executes, Then behavior unchanged (backward compatibility) (`tests/test_openai_runner.py::test_run_no_attachments`)
- Instrumentation: OpenAI API errors logged; metrics via `record_ai_analysis()` include all token types and cost
- Persistence hooks: None; no DB operations
- Gaps: **Missing test for file deletion failure** (line 438 claims deletion failure is logged and swallowed, but test plan at lines 437-438 says "Given file deletion failure, When client.files.delete() raises, Then error logged but execution succeeds" without concrete test name); **missing verification that file_ids are correctly included in message content structure**
- Evidence: `plan.md:433-442, 290-300`

## 5) Adversarial Sweep (must find ≥3 credible issues or declare why none exist)

**Blocker — Incorrect OpenAI API assumption for file uploads**

**Evidence:** `plan.md:113-115, 267-268` — "Upload PDF with `client.files.create(file=..., purpose="assistants")` Include PDF in user message as `{"type": "input_file", "file_id": pdf_file.id}`"

**Why it matters:** The current codebase uses **OpenAI Responses API** (confirmed by `app/utils/ai/openai/openai_runner.py` imports and usage of `ParsedResponse`, response structures). The `client.files.create()` method with `purpose="assistants"` is part of the **legacy Assistants API**, which is a completely different API surface. The Responses API does **not** support file uploads via separate file creation - instead, files must be passed directly in the message content (if supported at all for this API tier). This is a fundamental architectural mismatch that will cause implementation to fail.

**Fix suggestion:** Research the correct method for attaching files in OpenAI Responses API. If Responses API does not support file attachments, either (1) switch to a different OpenAI API that supports file attachments (requiring broader architectural changes), or (2) redesign the feature to send PDF content as base64-encoded text within the prompt (significant prompt engineering and token cost implications), or (3) use a different AI provider that supports PDF attachments in their chat completion API.

**Confidence:** High

---

**Major — Temp file lifecycle management lacks concrete implementation**

**Evidence:** `plan.md:279, 318-323` — "Write PDF bytes to temporary file for OpenAI upload" and "Temp file created in TempFileManager base path; cleanup handled by TempFileManager lifecycle"

**Why it matters:** The plan describes temp file creation and cleanup at a high level but omits critical implementation details: (1) Does the function call `TempFileManager.create_temp_directory()` and manually write bytes, or does it need a new `write_temp_file()` helper? (2) Who owns the file handle - is it closed before upload or kept open? (3) What is the cleanup timing - does TempFileManager cleanup happen before or after the `finally` block in OpenAIRunner? (4) If OpenAI file deletion (line 284) happens in `finally`, but temp file still exists, does this create a race condition with TempFileManager's background cleanup thread? The lack of concrete sequencing creates risk of file handle leaks, orphaned temp files, or cleanup race conditions.

**Fix suggestion:** Add detailed temp file lifecycle to section 5 (Algorithms & State Machines): (1) Function downloads PDF bytes from DocumentService, (2) Function writes bytes to `TempFileManager.base_path / f"datasheet_{uuid4()}.pdf"` and closes file handle, (3) Function stores path in AIRequest.attachments, (4) OpenAIRunner opens file for upload, (5) After API call (success or failure), OpenAIRunner deletes temp file explicitly via `Path.unlink(missing_ok=True)` before deleting OpenAI file_id, (6) Document that TempFileManager background cleanup is backup only. Add test scenario verifying temp file is deleted even when OpenAI upload fails.

**Confidence:** High

---

**Major — Missing test coverage for critical cleanup and error paths**

**Evidence:** `plan.md:437-438` — "Given file deletion failure, When client.files.delete() raises, Then error logged but execution succeeds" (listed as scenario but no concrete test name provided); `plan.md:430` — "Gaps: End-to-end test with real OpenAI API deferred"

**Why it matters:** The plan correctly identifies that file deletion is best-effort and errors should be swallowed (aligns with `CLAUDE.md:157-161` cleanup philosophy). However, the test plan does not specify **how to verify** this behavior in a deterministic unit test. Without a concrete test that mocks `client.files.delete()` to raise an exception and verifies (1) the exception is caught, (2) an error is logged, and (3) the function returns successfully, the implementation may fail to handle this edge case. Additionally, the deferred end-to-end test gap means there's no verification that the entire file upload → API call → deletion sequence actually works with real OpenAI SDK calls (even in a staging environment).

**Fix suggestion:** In section 13 (Deterministic Test Plan), add explicit test scenario: "Given file deletion fails, When `client.files.delete()` raises `APIError`, Then error is logged at WARNING level, execution completes successfully, and response is returned (`tests/test_openai_runner.py::test_run_file_deletion_failure_swallowed`)." Add fixture detail: "Mock `openai.Client.files.delete` to raise exception; verify logger.warning called with file_id in message; verify AIResponse returned." For end-to-end gap, add to section 15 (Risks): "Risk: Integration with real OpenAI SDK may fail due to API changes or version incompatibility. Mitigation: Add optional integration test (`@pytest.mark.integration`) that uses real OpenAI API with small test PDF (gated by environment variable); run manually before release."

**Confidence:** High

---

**Major — Prompt section reuse strategy creates maintenance burden**

**Evidence:** `plan.md:149-151, 476` — "New prompt file `app/services/prompts/spec_extraction.md` as abstract of part_analysis.md with spec normalization rules" and "Risk: Spec extraction prompt does not align perfectly with part_analysis.md normalization rules. Mitigation: Reuse exact normalization sections from part_analysis.md"

**Why it matters:** The plan proposes creating a new prompt file by abstracting/copying sections from `part_analysis.md`. This creates a **duplication maintenance problem**: when normalization rules change in `part_analysis.md` (e.g., new package types, voltage formats, dimension parsing), developers must remember to sync changes to `spec_extraction.md`. The risk section acknowledges inconsistency but the mitigation ("reuse exact sections") doesn't prevent future drift. Given that both prompts need identical normalization rules (lines 100, 203-204 in plan reference `PartAnalysisDetails` DTO), there should be a single source of truth.

**Fix suggestion:** Refactor prompt structure to use Jinja2 `{% include %}` or `{% macro %}` for shared normalization rules. Create `app/services/prompts/_normalization_rules.md` (leading underscore indicates partial) containing package_type, mounting_type, voltage, dimension, and tag normalization sections. Both `part_analysis.md` and `spec_extraction.md` include this partial. Update section 2 (Affected Areas) to add: "Area: `app/services/prompts/_normalization_rules.md` (new file); Why: Shared normalization rules extracted from part_analysis.md; Evidence: Jinja2 template include pattern." This ensures single source of truth and prevents drift.

**Confidence:** Medium (lower confidence because prompt duplication may be acceptable short-term, but high confidence it will cause maintenance issues long-term)

## 6) Derived-Value & Persistence Invariants (stacked entries)

- Derived value: OpenAI file_id from uploaded PDF
  - Source dataset: Unfiltered PDF bytes from `DocumentService.process_upload_url()`
  - Write / cleanup triggered: File uploaded to OpenAI servers; stored transiently in OpenAIRunner local variable `uploaded_file_ids`; deletion triggered in `finally` block via `client.files.delete(file_id)`
  - Guards: Try/finally ensures deletion attempt even on exception; deletion errors logged and swallowed (best-effort cleanup)
  - Invariant: Every successfully uploaded file_id has a corresponding deletion call before function returns (may fail, but attempt is made)
  - Evidence: `plan.md:290-300, 304-309`

- Derived value: Temporary file path for PDF upload
  - Source dataset: Downloaded PDF bytes written to `TempFileManager.base_path`
  - Write / cleanup triggered: Temp file created before OpenAI upload; cleanup triggered by TempFileManager background thread OR explicit deletion by OpenAIRunner (plan unclear which)
  - Guards: **MISSING** — Plan does not specify who owns temp file deletion (OpenAIRunner finally block vs TempFileManager background cleanup); no guard against partial writes if temp file creation fails
  - Invariant: **VIOLATED** — Unclear invariant on temp file lifecycle; risk of orphaned files if OpenAIRunner doesn't explicitly delete and TempFileManager cleanup is delayed
  - Evidence: `plan.md:318-323` (describes TempFileManager cleanup but lacks OpenAIRunner ownership details)

- Derived value: Datasheet validation result (match vs mismatch)
  - Source dataset: LLM comparison of user-provided `analysis_query` against PDF content
  - Write / cleanup triggered: Response contains `{"specs": ..., "error": null}` OR `{"specs": null, "error": "mismatch reason"}`; no persistent storage
  - Guards: LLM prompt instructs validation before extraction; response schema enforces exactly one field populated
  - Invariant: Response contains either specs OR error, never both populated, never both null
  - Evidence: `plan.md:311-316, 196-216`

**Note:** The second entry (temp file path) reveals a **persistent write/cleanup without sufficient guards**, escalating to Major severity. The plan describes temp file creation but does not specify explicit cleanup ownership in OpenAIRunner, relying on TempFileManager background thread which may have delayed cleanup. This violates the principle that derived state driving writes should have immediate cleanup guards.

## 7) Risks & Mitigations (top 3)

- Risk: OpenAI Responses API does not support file uploads via `client.files.create()` as assumed
- Mitigation: Verify OpenAI Responses API documentation for correct file attachment method before implementation; if unsupported, redesign to use alternative API or approach
- Evidence: `plan.md:113-115, 267-268` (Blocker finding above)

- Risk: Temp file creation and cleanup coordination between OpenAIRunner and TempFileManager creates orphaned files or handle leaks
- Mitigation: Specify explicit temp file ownership and cleanup sequence in OpenAIRunner; add test verifying temp file deletion on upload failure; document TempFileManager as backup cleanup only
- Evidence: `plan.md:318-323` (Major finding above on temp file lifecycle)

- Risk: Large PDFs cause OpenAI API timeout or size limit errors, returning error response that blocks spec extraction
- Mitigation: Log error with file size details; allow main LLM to fall back to web search; consider adding PDF size check (e.g., 10MB limit) before upload in future iteration to provide faster feedback
- Evidence: `plan.md:467-468`

## 8) Confidence

Confidence: High — All blocking issues resolved during review. Plan now specifies correct OpenAI API usage (`purpose="user_data"`), explicit temp file lifecycle with cleanup guards, comprehensive test coverage including deletion failure scenarios, and shared normalization rules via Jinja2 includes. Ready for implementation.

---

## Plan Updates Applied

Based on the review findings, the following changes were made to `plan.md`:

### Blocker Resolution: OpenAI API Correction
- **Changed**: `purpose="assistants"` → `purpose="user_data"` throughout plan
- **Added**: OpenAI 512 MB file size limit to assumptions and error handling
- **Added**: Documentation that OpenAI extracts both text and images from PDFs
- **Evidence**: Updated at lines 96-103, 116, 272-275, 288, 360-364

### Major Resolution: Temp File Lifecycle Details
- **Added**: Explicit temp file creation pattern: `TempFileManager.base_path / f"datasheet_{uuid4().hex}.pdf"`
- **Added**: Step-by-step file lifecycle in Algorithm section (lines 285-293):
  - Write bytes via `Path.write_bytes()` (atomic, auto-closes)
  - Upload via `client.files.create()` with file handle
  - Finally block deletes temp file via `Path.unlink(missing_ok=True)`
  - Finally block deletes OpenAI file via `client.files.delete()` (best-effort)
- **Updated**: Derived State & Invariants section with explicit cleanup ownership (lines 331-336)
- **Updated**: Attachment handling flow with 9 detailed steps including cleanup sequencing (lines 300-313)

### Major Resolution: Test Coverage Expansion
- **Added**: Test scenario for temp file write failure (`Path.write_bytes()` raises `OSError`)
- **Added**: Explicit test name for OpenAI file deletion failure: `test_run_file_deletion_failure_swallowed`
- **Added**: Test scenario for temp file deletion failure (permission error)
- **Added**: Verification requirements for logger.warning calls and purpose parameter
- **Added**: Integration test strategy: `@pytest.mark.integration` with environment variable gating
- **Evidence**: Updated at lines 441-450, 453-462

### Major Resolution: Prompt Duplication Prevention
- **Added**: New file `app/services/prompts/_normalization_rules.md` for shared rules
- **Added**: Jinja2 include pattern to prevent drift between prompts
- **Updated**: Affected Areas section to include normalization rules extraction (lines 151-153)
- **Updated**: Risk mitigation to use single source of truth via includes (lines 495-497)
- **Evidence**: Ensures `part_analysis.md` and `spec_extraction.md` stay synchronized

### Additional Improvements
- **Added**: Error case for temp file write failure (lines 366-370)
- **Added**: Integration test risk and mitigation (lines 507-509)
- **Clarified**: TempFileManager role as backup cleanup only (not primary)
- **Added**: File handle management details (context managers, atomic writes)
