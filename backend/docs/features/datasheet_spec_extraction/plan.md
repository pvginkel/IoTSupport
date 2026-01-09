# Datasheet Spec Extraction AIFunction - Technical Plan

## 0) Research Log & Findings

### Areas Researched

**AIFunction Pattern**
- Examined existing AI functions: `DuplicateSearchFunction`, `SearchMouserByPartNumberFunction`, `SearchMouserByKeywordFunction`, `URLClassifierFunction`
- All follow abstract base class `AIFunction` at `app/utils/ai/ai_runner.py:11-26`
- Pattern: implement `get_name()`, `get_description()`, `get_model()`, `execute()`
- Functions are wired into `AIService` via dependency injection in `ServiceContainer`

**OpenAI Runner & PDF Support**
- `OpenAIRunner` at `app/utils/ai/openai/openai_runner.py` handles API calls
- Currently builds input using `_build_responses_api_input()` which constructs developer/user role messages
- No existing PDF attachment support - needs implementation
- OpenAI Responses API supports file uploads via `client.files.create()` and `{"type": "input_file", "file_id": ...}` message format

**AIRequest Model**
- Located at `app/utils/ai/ai_runner.py:29-42`
- Current fields: system_prompt, user_prompt, model, verbosity, reasoning_effort, reasoning_summary, response_model
- No attachment support - needs extension

**Document Service Integration**
- `DocumentService.process_upload_url()` at `app/services/document_service.py:64-100` validates URLs and downloads content
- Returns `UploadDocumentSchema` with content bytes, detected MIME type, attachment type
- Already handles PDF detection via `_mime_type_to_attachment_type()`

**Metrics Integration**
- `MetricsService.record_ai_analysis()` at `app/services/metrics_service.py:151-165` tracks AI operations
- Parameters: status, model, verbosity, reasoning_effort, duration, token counts, cost
- OpenAIRunner already calls this in `_call_openai_api()` at line 156-176 (success) and 182-195 (error)

**Service Container Wiring**
- AI functions registered at `app/services/container.py:269-290`
- Pattern: Factory provider creates function instance with service dependencies
- Functions passed to `AIService` constructor at lines 293-307

**Part Analysis Prompt**
- Located at `app/services/prompts/part_analysis.md`
- Jinja2 template with mode switching (analysis vs cleanup)
- Contains field normalization rules for package_type, mounting_type, voltages, dimensions, tags
- Instructions for URL classification, Mouser integration, duplicate detection

### Special Findings

**Prompt Priority Conflict**
- Current prompt at `part_analysis.md:158-166` instructs LLM to search for URLs actively
- Need to add instruction to prioritize datasheet extraction over web search when datasheet URL is available
- Mouser integration section (lines 129-157) already demonstrates conditional tool usage pattern

**File Cleanup Pattern**
- Python `finally` block required for OpenAI file deletion (per requirements)
- Consistent with error handling philosophy: fail fast, surface errors to user

**ClaudeRunner Exclusion**
- Change brief explicitly excludes ClaudeRunner PDF support
- ClaudeRunner at `app/utils/ai/claude/claude_runner.py` will not be modified

## 1) Intent & Scope

### User intent

Create a new AIFunction that allows the main part analysis LLM to extract technical specifications from PDF datasheets when a datasheet URL is identified. The function validates the datasheet matches the analysis query, downloads and sends the PDF to OpenAI, and returns normalized specs or an error message.

### Prompt quotes

"Add a new AIFunction called `extract_specs_from_datasheet`"
"Request Model: `analysis_query` (string): Free-text description of the part being analyzed. Used to validate that the datasheet matches what we're looking for."
"Send the full PDF bytes to OpenAI API: Upload file with `client.files.create(file=..., purpose="assistants")`"
"Extend `app/services/prompts/part_analysis.md` to: Instruct the LLM to prioritize getting a datasheet for specs over web search"

### In scope

- New AIFunction `ExtractSpecsFromDatasheetFunction` following existing patterns
- Request/response Pydantic models for the function
- AIRequest extension to support file attachments (list of file paths)
- OpenAIRunner extension to upload PDFs and include in messages
- New prompt file `app/services/prompts/spec_extraction.md` with spec normalization rules
- Update to `part_analysis.md` to prioritize datasheet extraction
- Prometheus metrics for spec extraction operations
- Service container wiring for the new function
- Service tests for the function
- Integration tests with OpenAIRunner attachment handling

### Out of scope

- ClaudeRunner PDF support (explicitly excluded)
- Page limits or size restrictions on PDFs (may be added later)
- Merging logic for extracted specs (delegated to main LLM)
- API endpoint changes (internal AIFunction only)
- Frontend changes (backend-only feature)

### Assumptions / constraints

- OpenAI Responses API supports PDF file uploads via `client.files.create()` with `purpose="user_data"`
- PDF file IDs can be included in messages as `{"type": "input_file", "file_id": pdf_file.id}`
- Individual PDFs can be up to 512 MB (OpenAI limit)
- DocumentService.process_upload_url() successfully downloads and validates PDF URLs
- Main LLM will call this function after identifying a datasheet URL
- Spec extraction prompt can reuse normalization rules from part_analysis.md
- Metrics tracking follows existing `record_ai_analysis()` pattern
- OpenAI extracts both text and images from PDFs for processing

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Create new AIFunction `extract_specs_from_datasheet` following existing AIFunction patterns
- [ ] Request model has `analysis_query` field with documentation explaining it describes the analysis query and is used to validate the datasheet matches
- [ ] Request model has `datasheet_url` field with documentation explaining it should be a URL to a PDF datasheet
- [ ] Response model has optional `specs` field using `PartAnalysisDetails` DTO
- [ ] Response model has optional `error` field for explaining extraction failures
- [ ] Use `DocumentService.process_upload_url` to validate URL is a PDF and can be downloaded
- [ ] Send full PDF bytes to OpenAI API using file upload
- [ ] Upload PDF with `client.files.create(file=..., purpose="user_data")`
- [ ] Include PDF in user message as `{"type": "input_file", "file_id": pdf_file.id}`
- [ ] Delete uploaded file in a finally block using `client.files.delete()`
- [ ] Extend `AIRequest` with attachment support (list of file paths)
- [ ] Extend `OpenAIRunner` to handle PDF upload and attachment in requests
- [ ] Create prompt at `app/services/prompts/spec_extraction.md` as abstract of part_analysis.md with spec normalization rules
- [ ] Prompt must instruct LLM to validate datasheet matches the analysis query before extracting specs
- [ ] Update `app/services/prompts/part_analysis.md` to prioritize using `extract_specs_from_datasheet` over web search
- [ ] Update main prompt to instruct LLM to prioritize getting a datasheet to get specs
- [ ] Add Prometheus metrics for the function (request count by outcome, duration)
- [ ] Wire the new function in the service container and AIService
- [ ] Do NOT implement ClaudeRunner PDF support

## 2) Affected Areas & File Map

- Area: `app/utils/ai/datasheet_extraction.py` (new file)
- Why: New AIFunction implementation for spec extraction
- Evidence: Pattern from `app/utils/ai/duplicate_search.py:16-72` and `app/utils/ai/mouser_search.py:20-141`

- Area: `app/schemas/datasheet_extraction.py` (new file)
- Why: Request/response Pydantic models for the function
- Evidence: Pattern from `app/schemas/duplicate_search.py` and `app/schemas/mouser.py`

- Area: `app/utils/ai/ai_runner.py:29-42`
- Why: Extend `AIRequest` model with attachments field
- Evidence: Current model has system_prompt, user_prompt, model config fields; needs file path list

- Area: `app/utils/ai/openai/openai_runner.py:310-326`
- Why: Extend `_build_responses_api_input()` to handle file attachments
- Evidence: Current implementation builds developer/user role messages; needs file upload logic

- Area: `app/utils/ai/openai/openai_runner.py:47-99`
- Why: Modify `run()` to upload attachments before API call and delete in finally block
- Evidence: Main execution loop at lines 47-99; needs file lifecycle management

- Area: `app/services/prompts/_normalization_rules.md` (new file)
- Why: Shared normalization rules extracted from part_analysis.md for reuse across prompts
- Evidence: Jinja2 template include pattern; DRY principle to prevent drift

- Area: `app/services/prompts/spec_extraction.md` (new file)
- Why: Prompt template for spec extraction with validation; includes shared normalization rules
- Evidence: Pattern from `app/services/prompts/part_analysis.md:64-250`

- Area: `app/services/prompts/part_analysis.md:158-166`
- Why: Add instruction to prioritize datasheet extraction when datasheet URL found; update to include _normalization_rules.md
- Evidence: Current URL search section; needs priority guidance; normalization sections at lines 64-250

- Area: `app/services/container.py:269-290`
- Why: Wire new spec extraction function as Factory provider
- Evidence: Existing AIFunction wiring for duplicate_search_function, mouser functions

- Area: `app/services/ai_service.py:59-63`
- Why: Add spec extraction function to constructor dependencies
- Evidence: Existing function dependencies at lines 59-79

- Area: `app/services/ai_service.py:142-153`
- Why: Include spec extraction function in function_tools list for analyze_part()
- Evidence: Current function_tools assembly at lines 142-153

- Area: `app/services/metrics_service.py` (no changes needed)
- Why: Existing `record_ai_analysis()` already supports generic AI operation tracking
- Evidence: Method signature at lines 151-165 with status, duration, token counts

- Area: `tests/test_datasheet_extraction.py` (new file)
- Why: Service tests for spec extraction function
- Evidence: Test pattern from `tests/test_ai_service.py:1-150`

- Area: `tests/test_openai_runner.py` (may exist or be new)
- Why: Integration tests for attachment upload handling
- Evidence: Runner test pattern from `tests/test_claude_runner.py`

## 3) Data Model / Contracts

- Entity / contract: `ExtractSpecsFromDatasheetRequest`
- Shape:
  ```json
  {
    "analysis_query": "0.96 inch OLED display module SSD1306",
    "datasheet_url": "https://cdn-shop.adafruit.com/datasheets/SSD1306.pdf"
  }
  ```
- Refactor strategy: New model, no back-compat concerns
- Evidence: Request pattern from `app/schemas/duplicate_search.py:8-15`

- Entity / contract: `ExtractSpecsFromDatasheetResponse`
- Shape:
  ```json
  {
    "specs": {
      "product_name": "OLED display controller (SSD1306)",
      "package_type": "COG",
      "part_pin_count": 68,
      "voltage_rating": "3.3V",
      "physical_dimensions": "...",
      // ... all PartAnalysisDetails fields
    },
    "error": null
  }
  ```
  or
  ```json
  {
    "specs": null,
    "error": "Datasheet is for SSD1305, not SSD1306 as requested"
  }
  ```
- Refactor strategy: New model, no back-compat concerns; reuses existing `PartAnalysisDetails` DTO
- Evidence: Response pattern from `app/schemas/mouser.py:61-74`; DTO from `app/services/ai_model.py:24-48`

- Entity / contract: `AIRequest.attachments`
- Shape:
  ```python
  class AIRequest(BaseModel):
      # ... existing fields ...
      attachments: list[str] | None = None  # List of file paths to upload
  ```
- Refactor strategy: Add optional field with default None for backward compatibility
- Evidence: AIRequest at `app/utils/ai/ai_runner.py:29-42`

- Entity / contract: OpenAI Responses API input with file attachment
- Shape:
  ```json
  [
    {
      "role": "developer",
      "content": [
        {"type": "input_text", "text": "system prompt"}
      ]
    },
    {
      "role": "user",
      "content": [
        {"type": "input_text", "text": "user prompt"},
        {"type": "input_file", "file_id": "file-abc123"}
      ]
    }
  ]
  ```
- Refactor strategy: Modify `_build_responses_api_input()` to append file content items when attachments present
- Evidence: Current structure at `app/utils/ai/openai/openai_runner.py:310-326`

## 4) API / Integration Surface

- Surface: AIFunction `extract_specs_from_datasheet`
- Inputs: `ExtractSpecsFromDatasheetRequest` with analysis_query (string), datasheet_url (string)
- Outputs: `ExtractSpecsFromDatasheetResponse` with optional specs (PartAnalysisDetails) and optional error (string)
- Errors: Returns error in response field for graceful degradation (PDF download failure, validation failure, API error); function execution never raises
- Evidence: Function pattern from `app/utils/ai/duplicate_search.py:46-72` (execute method returns response, catches exceptions)

- Surface: `OpenAIRunner.run()` with attachments
- Inputs: `AIRequest` with new optional attachments field (list[str] file paths)
- Outputs: `AIResponse` unchanged
- Errors: File upload failure raises exception to caller; file deletion errors logged but swallowed (cleanup is best-effort)
- Evidence: Current run() signature at `app/utils/ai/openai/openai_runner.py:47`; error handling at lines 180-202

- Surface: OpenAI Files API `client.files.create()` and `client.files.delete()`
- Inputs: create() accepts file-like object and purpose="user_data" (Responses API standard); delete() accepts file_id
- Outputs: create() returns file object with .id; delete() returns deletion confirmation
- Errors: API errors propagate as exceptions; individual file size limit 512 MB
- Evidence: OpenAI SDK usage; OpenAI docs specify `purpose="user_data"` for model inputs

## 5) Algorithms & State Machines

- Flow: Spec extraction from PDF datasheet
- Steps:
  1. Main LLM identifies datasheet URL during part analysis
  2. Main LLM calls `extract_specs_from_datasheet` with analysis_query and datasheet_url
  3. Function uses `DocumentService.process_upload_url()` to download and validate PDF
  4. If validation fails (not a PDF, download error), return error response
  5. Function generates unique filename: `temp_path = TempFileManager.base_path / f"datasheet_{uuid4().hex}.pdf"`
  6. Write PDF bytes to temp file using `temp_path.write_bytes(pdf_content)` (atomic write, auto-closes)
  7. Create `AIRequest` with spec extraction prompt, analysis query in user prompt, and `attachments=[str(temp_path)]`
  8. OpenAIRunner uploads PDF via `client.files.create(file=open(temp_path, 'rb'), purpose="user_data")`
  9. OpenAIRunner stores file_id in local list for cleanup tracking
  10. OpenAIRunner includes file_id in user message content as `{"type": "input_file", "file_id": file_id}`
  11. OpenAI API processes PDF (extracts text + images) and returns structured specs or validation error
  12. In finally block: (a) delete temp file via `Path(attachment).unlink(missing_ok=True)` for each attachment, (b) delete OpenAI file via `client.files.delete(file_id)` (log errors, swallow exceptions for best-effort cleanup)
  13. Return response with specs (if successful) or error (if validation failed)
- States / transitions: Stateless function; no persistent state machine
- Hotspots: PDF download latency (external URL fetch); OpenAI API latency (large file upload + processing, up to 512 MB); temp file cleanup on exceptions; file handle management
- Evidence: Function execution pattern from `app/utils/ai/duplicate_search.py:46-72`; OpenAI runner flow from `app/utils/ai/openai/openai_runner.py:47-99`; OpenAI docs specify `purpose="user_data"` for Responses API

- Flow: Attachment handling in OpenAIRunner
- Steps:
  1. Runner receives AIRequest with attachments list (file paths)
  2. Initialize `uploaded_file_ids: list[str] = []` for tracking
  3. Before API call loop, iterate attachments and upload each: `file_obj = client.files.create(file=open(path, 'rb'), purpose="user_data")`
  4. Store `file_obj.id` in `uploaded_file_ids` list
  5. Close file handles (handled by context manager if using `with open()`)
  6. Build user message content: extend existing content with `{"type": "input_file", "file_id": fid}` for each file_id
  7. Execute OpenAI API call loop as usual (may have multiple turns with function calls)
  8. In finally block (after API call completes or fails):
     a. For each attachment path: `Path(path).unlink(missing_ok=True)` (delete temp file, swallow FileNotFoundError)
     b. For each file_id in uploaded_file_ids: `client.files.delete(file_id)` wrapped in try/except (log APIError, swallow for best-effort)
  9. Metrics and response assembly unchanged
- States / transitions: Transient upload state during API call; no persistence; file_ids list cleared after cleanup
- Hotspots: Multiple file uploads increase latency linearly; partial upload failure leaves uploaded files (cleaned in finally); large files (up to 512 MB) may hit network timeouts
- Evidence: OpenAI runner structure at `app/utils/ai/openai/openai_runner.py:47-99`; OpenAI docs for file upload API

## 6) Derived State & Invariants

- Derived value: OpenAI file upload success
  - Source: Unfiltered PDF bytes from DocumentService.process_upload_url()
  - Writes / cleanup: File ID stored transiently; file deletion in finally block
  - Guards: Try/finally ensures deletion even on exception; deletion errors logged but swallowed
  - Invariant: Uploaded files are deleted before function returns (best-effort; failures logged)
  - Evidence: File lifecycle pattern from OpenAI SDK docs; cleanup philosophy from `CLAUDE.md:157-161`

- Derived value: Datasheet validation result
  - Source: LLM comparison of analysis_query against PDF content
  - Writes / cleanup: Error message returned in response; no persistent state
  - Guards: LLM instructed to validate before extraction; returns error if mismatch
  - Invariant: Response contains either specs OR error, never both populated
  - Evidence: Prompt requirement "validate datasheet matches the analysis query before extracting specs"

- Derived value: Temporary file path for PDF
  - Source: Downloaded PDF bytes written to `TempFileManager.base_path / f"datasheet_{uuid4().hex}.pdf"`
  - Writes / cleanup: Temp file created via `Path.write_bytes()` (atomic write); OpenAIRunner explicitly deletes in finally block via `Path.unlink(missing_ok=True)`; TempFileManager background cleanup is backup only
  - Guards: OpenAIRunner finally block ensures deletion even on upload failure or API error; `missing_ok=True` prevents FileNotFoundError if already deleted; file handle auto-closed by write_bytes()
  - Invariant: Every temp file created for upload is deleted by OpenAIRunner before function returns (best-effort; failures logged); TempFileManager cleanup catches any missed files after age threshold
  - Evidence: TempFileManager usage from `app/services/ai_service.py:53`; cleanup pattern from S3 best-effort deletion `CLAUDE.md:157-161`

## 7) Consistency, Transactions & Concurrency

- Transaction scope: No database operations; purely external API calls
- Atomic requirements: None (no DB writes)
- Retry / idempotency: OpenAI file upload failures propagate to caller; main LLM can retry function call; file deletion is best-effort in finally block
- Ordering / concurrency controls: None; function is stateless and thread-safe (no shared mutable state)
- Evidence: AIFunction execution from `app/utils/ai/duplicate_search.py:46-72`; no DB session usage

## 8) Errors & Edge Cases

- Failure: URL is not a PDF
- Surface: `extract_specs_from_datasheet` function
- Handling: `DocumentService.process_upload_url()` raises `InvalidOperationException`; function catches and returns error response: `{"error": "URL is not a valid PDF datasheet"}`
- Guardrails: DocumentService validates MIME type; function logs error and returns graceful degradation response
- Evidence: DocumentService validation at `app/services/document_service.py:64-100`; error handling pattern from `app/utils/ai/duplicate_search.py:62-72`

- Failure: PDF download fails (network error, 404, timeout)
- Surface: `extract_specs_from_datasheet` function
- Handling: `DocumentService.process_upload_url()` raises exception; function catches and returns error response: `{"error": "Failed to download datasheet: <details>"}`
- Guardrails: Download cache service has timeout; function logs error
- Evidence: DownloadCacheService timeout from `app/services/container.py:144-149`

- Failure: OpenAI file upload fails (API error, size limit exceeds 512 MB)
- Surface: `OpenAIRunner.run()` with attachments
- Handling: `client.files.create()` raises `APIError`; propagates to caller; uploaded file_ids cleaned in finally block; temp files deleted in finally block
- Guardrails: Exception propagates to main LLM; logged by OpenAIRunner error handling at lines 180-202; finally block ensures partial cleanup
- Evidence: OpenAI runner error handling at `app/utils/ai/openai/openai_runner.py:180-202`; 512 MB limit from OpenAI docs

- Failure: Temp file write fails (disk full, permission error)
- Surface: `extract_specs_from_datasheet` function
- Handling: `Path.write_bytes()` raises `OSError`; function catches and returns error response: `{"error": "Failed to write temporary file: <details>"}`
- Guardrails: Function logs error; no OpenAI API call attempted; no cleanup needed (file not created)
- Evidence: Error handling pattern from `app/utils/ai/duplicate_search.py:62-72`

- Failure: OpenAI file deletion fails (API error, file already deleted)
- Surface: `OpenAIRunner.run()` finally block
- Handling: Log error but swallow exception (cleanup is best-effort); function execution succeeds
- Guardrails: Try/except around `client.files.delete()`; error logged at warning level
- Evidence: Cleanup philosophy from `CLAUDE.md:157-161` (fail fast, but cleanup errors are best-effort)

- Failure: Datasheet does not match analysis query
- Surface: Spec extraction LLM response
- Handling: LLM returns error in response: `{"error": "Datasheet is for <wrong_part>, not <expected_part>"}`; function returns this to main LLM
- Guardrails: Prompt instructs LLM to validate before extraction; main LLM can retry with different URL or fall back to web search
- Evidence: Requirement "Prompt must instruct LLM to validate datasheet matches the analysis query"

- Failure: PDF is unreadable or corrupted
- Surface: OpenAI API response
- Handling: OpenAI returns error or LLM cannot extract; response contains error field; main LLM informed
- Guardrails: Function returns graceful error response; main LLM can fall back
- Evidence: Error field in response model

## 9) Observability / Telemetry

- Signal: `ai_analysis_requests_total`
- Type: Counter
- Trigger: OpenAIRunner records via `metrics_service.record_ai_analysis()` on each API call completion
- Labels / fields: status (success/error), model, verbosity, reasoning_effort
- Consumer: Prometheus dashboard for AI usage tracking
- Evidence: OpenAIRunner metrics at `app/utils/ai/openai/openai_runner.py:164-176` (success) and `182-195` (error)

- Signal: `ai_analysis_duration_seconds`
- Type: Histogram
- Trigger: OpenAIRunner records duration in `record_ai_analysis()` call
- Labels / fields: model, verbosity, reasoning_effort
- Consumer: Latency percentiles for AI operations
- Evidence: Duration calculation at `app/utils/ai/openai/openai_runner.py:79`

- Signal: `ai_analysis_tokens_total`
- Type: Counter (multiple series)
- Trigger: OpenAIRunner records input/output/reasoning/cached tokens in `record_ai_analysis()`
- Labels / fields: token_type (input/output/reasoning/cached_input), model
- Consumer: Token usage tracking and cost attribution
- Evidence: Token tracking at `app/utils/ai/openai/openai_runner.py:69-74`

- Signal: `ai_analysis_cost_dollars_total`
- Type: Counter
- Trigger: OpenAIRunner records calculated cost in `record_ai_analysis()`
- Labels / fields: model
- Consumer: Cost monitoring and budgeting
- Evidence: Cost calculation at `app/utils/ai/openai/openai_runner.py:81`

- Signal: Function execution logs
- Type: Structured log (INFO/WARNING/ERROR)
- Trigger: Log at function entry (analysis_query), PDF download, file upload, API call, deletion, errors
- Labels / fields: analysis_query snippet, datasheet_url, file_id, error details
- Consumer: Debugging spec extraction failures
- Evidence: Logging pattern from `app/utils/ai/duplicate_search.py:64-71`

## 10) Background Work & Shutdown

No background work or shutdown hooks required. Function is request-scoped and stateless.

## 11) Security & Permissions

Not applicable. No authentication, authorization, or sensitive data handling beyond existing AIService patterns. PDF URLs are user-provided and validated by DocumentService.

## 12) UX / UI Impact

Not applicable. This is a backend-only internal AIFunction with no direct UI exposure.

## 13) Deterministic Test Plan

- Surface: `ExtractSpecsFromDatasheetFunction`
- Scenarios:
  - Given valid PDF URL and matching analysis query, When function executes, Then response contains specs with normalized fields
  - Given valid PDF URL but non-matching analysis query, When LLM validates, Then response contains error explaining mismatch
  - Given non-PDF URL, When DocumentService validates, Then function catches exception and returns error response
  - Given PDF download failure (404), When DocumentService attempts download, Then function catches exception and returns error response
  - Given temp file write failure, When Path.write_bytes() raises OSError, Then function catches exception and returns error response
  - Given OpenAI API error during spec extraction, When runner calls API, Then function catches exception and returns error response
- Fixtures / hooks: Mock DocumentService.process_upload_url(); mock OpenAIRunner.run(); mock Path.write_bytes(); stub MetricsService; temp UUID generation
- Gaps: End-to-end integration test with real OpenAI API deferred (add optional `@pytest.mark.integration` test gated by environment variable; run manually before release to verify SDK compatibility and 512 MB limit behavior)
- Evidence: Test pattern from `tests/test_ai_service.py:93-127`

- Surface: `OpenAIRunner` with attachments
- Scenarios:
  - Given AIRequest with single attachment path, When run() executes, Then PDF uploaded to OpenAI with `purpose="user_data"`, file_id included in message, temp file deleted, OpenAI file deleted after API call
  - Given AIRequest with multiple attachments, When run() executes, Then all files uploaded, all included in message, all temp files deleted, all OpenAI files deleted
  - Given file upload failure, When client.files.create() raises, Then exception propagates, uploaded file_ids cleaned in finally, temp files deleted in finally
  - Given OpenAI file deletion failure, When client.files.delete() raises `APIError`, Then error logged at WARNING level, execution succeeds, response returned (`tests/test_openai_runner.py::test_run_file_deletion_failure_swallowed`)
  - Given temp file deletion failure, When Path.unlink() raises (e.g., permission error despite missing_ok=True), Then error logged, execution continues, OpenAI file still deleted
  - Given no attachments, When run() executes, Then behavior unchanged (backward compatibility)
- Fixtures / hooks: Mock OpenAI client; mock Path.unlink and Path.write_bytes; verify upload/delete call counts, arguments, and purpose parameter; verify logger.warning called with file_id on deletion failure
- Gaps: None (deletion failure test explicitly added)
- Evidence: Runner test pattern from `tests/test_claude_runner.py`; cleanup verification pattern

- Surface: Spec extraction prompt
- Scenarios:
  - Given prompt rendered with analysis query, When LLM processes, Then instructions include validation requirement
  - Given prompt contains normalization rules, When LLM extracts specs, Then output follows package_type, voltage, dimension formats
- Fixtures / hooks: Render prompt template; verify key instructions present
- Gaps: LLM behavior verification deferred to integration test
- Evidence: Prompt testing pattern from existing codebase

- Surface: `AIService.analyze_part()` with spec extraction function
- Scenarios:
  - Given function wired in container, When analyze_part() builds function_tools, Then spec extraction function included in list
  - Given Mouser enabled, When function_tools assembled, Then spec extraction alongside Mouser functions
- Fixtures / hooks: Service container wiring test; verify function_tools list contents
- Gaps: None
- Evidence: Service test pattern from `tests/test_ai_service.py:93-127`

## 14) Implementation Slices

Not applicable (feature is small enough to implement in a single iteration).

## 15) Risks & Open Questions

- Risk: Large PDFs cause OpenAI API timeout or size limit errors
- Impact: Function returns error; main LLM cannot extract specs from that datasheet
- Mitigation: Log error with details; allow main LLM to fall back to web search; consider adding PDF size check in future iteration

- Risk: OpenAI file deletion fails repeatedly, leaving orphaned files in OpenAI account
- Impact: Account storage fills up; potential cost impact
- Mitigation: Log deletion failures prominently; monitor OpenAI dashboard for orphaned files; manual cleanup if needed

- Risk: Spec extraction prompt diverges from part_analysis.md normalization rules over time (duplication maintenance burden)
- Impact: Main LLM receives inconsistent spec formats, merging logic fails; developers must remember to sync changes across both prompts
- Mitigation: Extract shared normalization rules to `app/services/prompts/_normalization_rules.md` (Jinja2 partial with leading underscore); both prompts include this partial via `{% include "_normalization_rules.md" %}`; ensures single source of truth

- Risk: TempFileManager cleanup timing causes temp files to persist longer than expected
- Impact: Disk usage increases temporarily
- Mitigation: TempFileManager has background cleanup thread; temp files cleaned after age threshold or on shutdown

- Risk: Main LLM calls spec extraction function with non-datasheet URLs (product pages, images)
- Impact: Function returns error; LLM learns to validate URL type first
- Mitigation: Function description emphasizes PDF datasheets; URL validation via DocumentService catches non-PDFs

- Risk: Integration with real OpenAI SDK may fail due to API changes, version incompatibility, or 512 MB limit edge cases
- Impact: Implementation works in unit tests but fails with real OpenAI API calls
- Mitigation: Add optional integration test (`@pytest.mark.integration`) that uses real OpenAI API with small test PDF (gated by environment variable `OPENAI_INTEGRATION_TEST=1`); run manually before release; verify file upload, processing, and deletion lifecycle

## 16) Confidence

Confidence: High — Implementation follows well-established AIFunction pattern, reuses existing DocumentService and OpenAIRunner infrastructure, and extends proven metrics/DI wiring. Prompt engineering is the primary unknown, mitigated by reusing normalization rules from part_analysis.md.
