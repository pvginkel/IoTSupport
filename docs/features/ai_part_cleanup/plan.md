# AI Part Cleanup — Technical Plan

## 0) Research Log & Findings

### Areas Researched

**Existing AI Analysis Infrastructure**
- Examined `AIPartAnalysisTask` (app/services/ai_part_analysis_task.py:18-131) — Long-running task pattern with progress reporting, cancellation support, and session management via `BaseSessionTask`
- Reviewed `AIService.analyze_part()` (app/services/ai_service.py:72-229) — Builds prompt from template, calls AI runner with tools, processes response
- Analyzed prompt template `part_search.md` (app/services/prompts/part_search.md) — Uses Jinja2 for category injection, comprehensive field normalization rules
- Studied AI runner and function protocol (app/utils/ai/ai_runner.py) — Function-based tool system with URLClassifier and DuplicateSearch implementations

**Part Data Model & Service**
- Part model (app/models/part.py:31-133) — All technical fields present: manufacturer_code, type_id, manufacturer, product_page, seller_id, seller_link, package, pin_count, pin_pitch, voltage_rating, input_voltage, output_voltage, mounting_type, series, dimensions, tags
- PartService (app/services/part_service.py:17-100) — Lightweight service with create_part() accepting all extended fields
- AttachmentSet relationship (app/models/part.py:99-105) — Every part has attachment_set_id; cover image determined via attachment_set.cover_attachment

**Task & Schema Infrastructure**
- BaseSessionTask (app/services/base_task.py:60-115) — Provides session management, cancellation, and commit/rollback pattern
- Task result schemas (app/schemas/ai_part_analysis.py:194-228) — Success/error wrapper with optional analysis field
- API endpoint pattern (app/api/ai_parts.py:37-124) — Multipart validation, task creation, SSE stream response

**Duplicate Search Integration**
- DuplicateSearchFunction (app/utils/ai/duplicate_search.py:16-72) — AI function that performs duplicate search via second LLM chain
- Used in analysis mode to detect existing parts before full analysis
- Returns matches with confidence levels (high/medium) and reasoning

**Dependency Injection Setup**
- ServiceContainer (app/services/container.py:43-262) — Wiring for ai_service, duplicate_search_function, part_service, type_service
- Factory providers for stateless services, Singleton for stateful (metrics, shutdown coordinator)

### Key Findings

**Template Sharing Opportunity**
The existing `part_search.md` prompt already uses Jinja2 for dynamic category injection (line 31-33). Adding mode-based conditionals is straightforward and maintains single source of truth for field normalization rules.

**Complete Part Context Required**
For cleanup mode, the AI needs visibility into all existing parts (except target) to understand current inventory patterns and ensure consistency. This differs from analysis mode which only needs type categories.

**Type Changes During Cleanup**
The change brief explicitly allows type changes during cleanup. The Part model's type_id is nullable and mutable (app/models/part.py:39-41), supporting this requirement. Response schema must include type field alongside other part data.

**Tool Exclusion Pattern**
The AI runner accepts a list of AIFunction implementations. For cleanup mode, we pass only URLClassifierFunction and exclude DuplicateSearchFunction to prevent redundant duplicate checking of an already-existing part.

**Seller Field Handling**
Part model has seller_id (FK) and seller_link (string). Cleanup should return seller NAME (string) matching the input format, not seller_id. The frontend will handle seller resolution/creation before applying updates.

**No Database Writes**
Cleanup task only reads the target part and returns improved JSON over SSE. All database writes happen later when user accepts changes, keeping the task side-effect free and cancellable.

**Existing Patterns to Follow**
- Progress reporting phases (0-5% init, 5-80% AI, 80-95% processing, 95-100% finalization)
- Cancellation checks at phase boundaries
- Error wrapping in task result schema with success=False
- Settings.real_ai_allowed gating with OPENAI_DUMMY_RESPONSE_PATH fallback

### Conflicts & Resolutions

**Conflict: Template file naming**
Change brief suggests renaming `part_search.md` to `part_analysis.md` for generality. However, this breaks existing references in AIService._build_prompt() (line 240-242) and potentially other locations.

**Resolution:** Rename to `part_analysis.md` and update all references atomically. Grep confirms only AIService._build_prompt() references the filename directly.

**Conflict: Attachment handling during cleanup**
Change brief states "no new images or datasheets expected" but URLClassifier and web search tools are included. Should AI be allowed to suggest new documents?

**Resolution:** Include tools for URL validation and metadata enrichment of EXISTING product_page/seller_link fields, but instruct prompt that cleanup focuses on improving existing data, not adding attachments. If AI finds better documentation URLs, they populate product_page field rather than documents array.

**Conflict: Return format for seller**
Input JSON includes seller (name), but Part model uses seller_id (FK). Output must match input structure.

**Resolution:** Service layer fetches seller.name from relationship and includes in JSON context. Response includes seller name string. Frontend maps name→id before applying update.

---

## 1) Intent & Scope

**User intent**

Add a long-running background task that applies current AI analysis rules and tools to existing inventory parts, improving data quality for parts created before certain features were available. The task accepts a part key, provides the target part and all other parts as JSON context to the AI, and returns the complete improved part data over SSE for frontend diff/apply workflows.

**Prompt quotes**

"Add a new long-running task that uses AI to clean up and improve existing parts in the inventory."

"Provide the AI with all existing parts (except the target) as JSON context showing the AI how parts are currently formatted, ensuring consistency."

"Allow AI to suggest type changes during cleanup."

"Return the complete improved part data (same structure as input) as the task result over SSE."

"Prioritize rules in the prompt over patterns in existing data when there are conflicts."

**User Requirements Checklist**

- [ ] Create a long-running task (similar to AIPartAnalysisTask) that accepts a part key as input
- [ ] Rename `part_search.md` to a more general name and use Jinja2 conditionals to support both analysis and cleanup modes
- [ ] For cleanup mode, provide the AI with all existing parts (except the target) as JSON context showing: key, manufacturer_code, type, description, manufacturer, tags, package, pin_count, pin_pitch, voltage_rating, input_voltage, output_voltage, mounting_type, series, dimensions, product_page, seller (name), seller_link
- [ ] Provide the target part using the same JSON structure as the context parts
- [ ] Include URLClassifierFunction in cleanup mode (web search is inherent to the AI model, not a separate tool)
- [ ] Exclude duplicate search function from cleanup mode
- [ ] Allow AI to suggest type changes during cleanup
- [ ] Return the complete improved part data (same structure as input) as the task result over SSE
- [ ] The prompt must instruct the AI that its job is to improve data quality by applying current rules to potentially old data without losing data
- [ ] Create API endpoint `POST /ai-parts/cleanup` to start the cleanup task
- [ ] Prioritize rules in the prompt over patterns in existing data when there are conflicts

**In scope**

- New AIPartCleanupTask class inheriting from BaseSessionTask
- Renaming prompt template from part_search.md to part_analysis.md with mode parameter
- Adding cleanup-specific prompt sections via Jinja2 conditionals
- AIService.cleanup_part() method that builds part context JSON and excludes duplicate search
- POST /ai-parts/cleanup endpoint accepting part_key in request body
- Response schema for cleanup task results (CleanedPartDataSchema, AIPartCleanupTaskResultSchema)
- Service layer logic to fetch all parts with relationships (type, seller) and serialize to JSON
- Progress reporting and cancellation support matching existing task patterns

**Out of scope**

- Applying cleaned data to the database (frontend responsibility)
- Diff generation or change visualization (frontend responsibility)
- Batch cleanup of multiple parts (single part per task)
- Automatic cleanup triggers or scheduling
- Cleanup history or audit logging
- Rollback or undo mechanisms
- Image upload or attachment creation during cleanup
- Changes to created_at, updated_at, part_locations, quantity_history, kit_contents, or attachment_set

**Assumptions / constraints**

- OpenAI API key and real_ai_allowed configuration are already functional (reuse existing AIService setup)
- URLClassifierFunction is already instantiated inline in AIService.__init__ (line 60) and can be reused for cleanup mode
- Web search is performed by the AI model itself (not a separate tool); Mouser queries are handled via general web search capabilities
- Part model's type_id is mutable and supports null values
- Seller name resolution happens in frontend before applying updates
- SSE infrastructure and TaskService support long-running tasks with progress reporting
- Database session management via BaseSessionTask handles commit/rollback correctly
- Cleanup tasks are infrequent enough that loading all parts into memory is acceptable
- Part counts remain under ~10,000 (reasonable JSON payload size for AI context)

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Create a long-running task (similar to AIPartAnalysisTask) that accepts a part key as input
- [ ] Rename `part_search.md` to a more general name and use Jinja2 conditionals to support both analysis and cleanup modes
- [ ] For cleanup mode, provide the AI with all existing parts (except the target) as JSON context showing: key, manufacturer_code, type, description, manufacturer, tags, package, pin_count, pin_pitch, voltage_rating, input_voltage, output_voltage, mounting_type, series, dimensions, product_page, seller (name), seller_link
- [ ] Provide the target part using the same JSON structure as the context parts
- [ ] Include URLClassifierFunction in cleanup mode (web search is inherent to the AI model, not a separate tool)
- [ ] Exclude duplicate search function from cleanup mode
- [ ] Allow AI to suggest type changes during cleanup
- [ ] Return the complete improved part data (same structure as input) as the task result over SSE
- [ ] The prompt must instruct the AI that its job is to improve data quality by applying current rules to potentially old data without losing data
- [ ] Create API endpoint `POST /ai-parts/cleanup` to start the cleanup task
- [ ] Prioritize rules in the prompt over patterns in existing data when there are conflicts

---

## 2) Affected Areas & File Map (with repository evidence)

- Area: app/services/prompts/part_search.md → part_analysis.md (RENAME)
- Why: Generalize filename and add Jinja2 mode conditionals for cleanup vs analysis behavior
- Evidence: app/services/ai_service.py:240-242 — Only reference to hardcoded filename "part_search.md"

- Area: app/services/ai_service.py
- Why: Update prompt path reference, add cleanup_part() method, add _build_prompt() mode parameter
- Evidence: app/services/ai_service.py:235-249 — _build_prompt() builds system prompt from template with categories; app/services/ai_service.py:72-229 — analyze_part() orchestrates AI analysis with tools

- Area: app/services/ai_part_cleanup_task.py (NEW)
- Why: Implement long-running cleanup task with progress reporting and session management
- Evidence: app/services/ai_part_analysis_task.py:18-131 — Pattern for BaseSessionTask with phases, cancellation, result wrapping

- Area: app/schemas/ai_part_cleanup.py (NEW)
- Why: Define request/response schemas for cleanup task (CleanupPartRequestSchema, CleanedPartDataSchema, AIPartCleanupTaskResultSchema, AIPartCleanupTaskCancelledResultSchema)
- Evidence: app/schemas/ai_part_analysis.py:194-228 — Task result schema pattern with success/error/cancelled variants

- Area: app/api/ai_parts.py
- Why: Add POST /ai-parts/cleanup endpoint to start cleanup task
- Evidence: app/api/ai_parts.py:37-124 — analyze_part() endpoint pattern with task creation and SSE response

- Area: app/services/container.py
- Why: No wiring changes required; URLClassifierFunction is instantiated inline in AIService.__init__ (not injected via container)
- Evidence: app/services/ai_service.py:60 — URLClassifierFunctionImpl instantiated with download_cache_service and document_service

- Area: app/models/part.py
- Why: No changes (all required fields already present, type_id mutable)
- Evidence: app/models/part.py:36-66 — All technical fields defined with correct types and nullability

- Area: tests/services/test_ai_part_cleanup_task.py (NEW)
- Why: Comprehensive service tests for cleanup task execution, error handling, cancellation
- Evidence: tests/services/test_ai_part_analysis_task.py — Existing pattern for task testing with fixtures

- Area: tests/api/test_ai_parts_cleanup.py (NEW)
- Why: API tests for cleanup endpoint validation, task creation, response format
- Evidence: tests/api/test_ai_parts.py — Existing pattern for AI endpoint testing

- Area: app/data/test_data/parts.json (UPDATE)
- Why: Ensure test data includes realistic product_page, seller_link, and technical fields for at least 10 parts to support cleanup context testing
- Evidence: CLAUDE.md (Test Data Management section) — Mandates test dataset maintenance for schema/feature changes

---

## 3) Data Model / Contracts

- Entity / contract: CleanupPartRequestSchema (request body for POST /ai-parts/cleanup)
- Shape:
  ```json
  {
    "part_key": "ABCD"  // 4-character part identifier (required, CHAR(4), existing part must exist)
  }
  ```
- Refactor strategy: New schema, no back-compat needed (BFF pattern)
- Evidence: app/schemas/ai_part_analysis.py:231-339 — AIPartCreateSchema pattern for request validation

---

- Entity / contract: CleanedPartDataSchema (cleaned part data returned by AI)
- Shape:
  ```json
  {
    "key": "ABCD",
    "manufacturer_code": "STM32F103C8T6",
    "type": "Microcontroller",  // Type name (string), AI can suggest changes
    "description": "32-bit ARM Cortex-M3 microcontroller",
    "manufacturer": "STMicroelectronics",
    "tags": ["arm", "cortex-m3", "32-bit", "microcontroller"],
    "package": "LQFP-48",
    "pin_count": 48,
    "pin_pitch": "0.5mm",
    "voltage_rating": "3.3V",
    "input_voltage": "2.0-3.6V",
    "output_voltage": null,
    "mounting_type": "Surface-Mount",
    "series": "STM32F1",
    "dimensions": "7x7mm",
    "product_page": "https://www.st.com/en/microcontrollers-microprocessors/stm32f103.html",
    "seller": "DigiKey",  // Seller name (string), not ID
    "seller_link": "https://www.digikey.com/..."
  }
  ```
- Refactor strategy: New schema mirroring input structure; frontend maps type name→id and seller name→id before applying
- Evidence: app/models/part.py:36-66 — Part model field definitions; app/schemas/ai_part_analysis.py:33-133 — PartAnalysisDetailsSchema pattern

---

- Entity / contract: AIPartCleanupTaskResultSchema (task result wrapper)
- Shape:
  ```json
  {
    "success": true,
    "cleaned_part": { /* CleanedPartDataSchema */ },
    "error_message": null  // Populated on failure
  }
  ```
- Refactor strategy: New schema following AIPartAnalysisTaskResultSchema pattern
- Evidence: app/schemas/ai_part_analysis.py:194-211 — Task result schema with success/error/data fields

---

- Entity / contract: AIPartCleanupTaskCancelledResultSchema (cancellation result)
- Shape:
  ```json
  {
    "cancelled": true,
    "message": "Cleanup cancelled by user"
  }
  ```
- Refactor strategy: New schema matching existing cancellation pattern
- Evidence: app/schemas/ai_part_analysis.py:214-228 — Cancellation schema pattern

---

- Entity / contract: PartAnalysisSuggestion (LLM response model for cleanup mode)
- Shape: Reuse existing model, but in cleanup mode only analysis_result is populated (no duplicate_parts, no analysis_failure_reason unless error)
  ```json
  {
    "analysis_result": { /* PartAnalysisDetails */ },
    "duplicate_parts": null,  // Always null in cleanup mode
    "analysis_failure_reason": null  // Only set if cleanup cannot proceed
  }
  ```
- Refactor strategy: No schema changes; cleanup mode uses existing response model with different field population
- Evidence: app/services/ai_model.py:48-67 — PartAnalysisSuggestion with optional fields

---

- Entity / contract: Prompt template mode parameter
- Shape: Jinja2 template context gains `mode` parameter: "analysis" | "cleanup"
  ```jinja2
  {% if mode == "cleanup" %}
  # Cleanup Mode Instructions
  You are improving an existing part's data quality...
  {% else %}
  # Analysis Mode Instructions
  You are analyzing a new part...
  {% endif %}
  ```
- Refactor strategy: Extend existing template with conditionals; mode defaults to "analysis" for backward compatibility
- Evidence: app/services/prompts/part_search.md:31-33 — Existing Jinja2 usage for categories

---

## 4) API / Integration Surface

- Surface: POST /api/ai-parts/cleanup
- Inputs: JSON body with CleanupPartRequestSchema (part_key: string, 4 chars)
- Outputs: HTTP 201 with TaskStartResponse (task_id, stream_url) on success; HTTP 400 with ErrorResponseSchema on validation failure or part not found; HTTP 400 when real AI disabled without dummy response
- Errors: 400 if part_key invalid format, 400 if part not found, 400 if real AI disabled, 500 on task creation failure
- Evidence: app/api/ai_parts.py:37-124 — analyze_part() endpoint pattern; app/schemas/task_schema.py — TaskStartResponse schema

---

- Surface: GET /api/ai-parts/cleanup/<task_id>/result
- Inputs: Path parameter task_id (UUID string)
- Outputs: HTTP 200 with AIPartCleanupTaskResultSchema on completed task; HTTP 404 if task not found or not completed
- Errors: 404 task not found, 404 task not completed, 404 result validation failed
- Evidence: app/api/ai_parts.py:197-253 — get_analysis_result() endpoint pattern for result retrieval

---

- Surface: AIService.cleanup_part() (new service method)
- Inputs: part_key (str), progress_handle (ProgressHandle)
- Outputs: CleanedPartDataSchema with improved part data
- Errors: RecordNotFoundException if part not found, InvalidOperationException if AI disabled, Exception for OpenAI API failures
- Evidence: app/services/ai_service.py:72-229 — analyze_part() method pattern with error handling

---

## 5) Algorithms & State Machines (step-by-step)

- Flow: AI Part Cleanup Task Execution
- Steps:
  1. Validate part_key format (4 uppercase chars) and fetch Part from database with relationships (type, seller) via selectinload
  2. Raise RecordNotFoundException if part does not exist
  3. Send progress "Initializing cleanup analysis" (0%)
  4. Check cancellation; return AIPartCleanupTaskCancelledResultSchema if cancelled
  5. Fetch all parts except target from database with selectinload(Part.type, Part.seller)
  6. Serialize all parts to JSON context list (key, manufacturer_code, type.name, description, manufacturer, tags, package, pin_count, pin_pitch, voltage_rating, input_voltage, output_voltage, mounting_type, series, dimensions, product_page, seller.name if seller else null, seller_link)
  7. Serialize target part to same JSON structure
  8. Send progress "AI cleaning part data" (5%)
  9. Call AIService.cleanup_part() with part_key and progress_handle
  10. AIService builds prompt with mode="cleanup", categories=type_names, all_parts=context_json, target_part=target_json
  11. AIService calls AIRunner with URLClassifierFunction only (no DuplicateSearchFunction)
  12. Check cancellation after AI response; return cancelled schema if cancelled
  13. Parse AI response as PartAnalysisSuggestion, extract analysis_result field
  14. Send progress "Processing cleanup suggestions" (80%)
  15. Map PartAnalysisDetails fields to CleanedPartDataSchema (type from product_category; AI populates seller field based on manufacturer/product_page analysis)
  16. Send progress "Cleanup complete" (100%)
  17. Return AIPartCleanupTaskResultSchema with success=true and cleaned_part data
  18. On any exception, return AIPartCleanupTaskResultSchema with success=false and error_message
- States / transitions: None (linear task flow with cancellation checks)
- Hotspots: Step 5-6 loads all parts into memory; acceptable for <10k parts but could exceed memory/JSON limits at scale. Step 11 AI call can take 10-30s depending on complexity.
- Evidence: app/services/ai_part_analysis_task.py:38-129 — Phase-based progress reporting with cancellation checks; app/services/ai_service.py:72-134 — AI runner orchestration pattern

---

## 6) Derived State & Invariants (stacked bullets)

- Derived value: Context parts JSON array
  - Source: Unfiltered query of all Part records excluding target, joined with Type and Seller relationships
  - Writes / cleanup: None (read-only context for AI)
  - Guards: Part count check before serialization (warn if >5000 parts, fail if >10000 to prevent OOM)
  - Invariant: Context must include all existing parts except target; AI must see complete inventory state
  - Evidence: app/services/ai_part_cleanup_task.py (new) — Part query and serialization logic

---

- Derived value: Type name in cleaned response
  - Source: AI's product_category field from PartAnalysisDetails, filtered through existing type names or "Proposed:" prefix handling
  - Writes / cleanup: None (returned to frontend; frontend creates new type if needed before applying update)
  - Guards: Type validation happens in frontend; backend returns type name string verbatim from AI
  - Invariant: Cleaned part data must include type name even if type doesn't exist yet
  - Evidence: app/services/ai_service.py:186-196 — Existing type matching logic in analyze_part()

---

- Derived value: Seller name in cleaned response
  - Source: For INPUT context, serialize Part.seller.name if seller exists, else null. For OUTPUT, AI populates seller field based on manufacturer/product_page analysis (may suggest a seller name even if original was null)
  - Writes / cleanup: None (returned to frontend; frontend resolves seller name→id before applying, creating seller if needed)
  - Guards: Seller reference is nullable in both input and output; AI may leave null if uncertain
  - Invariant: Seller field in context and response is always a name string (or null), never an ID
  - Evidence: app/models/part.py:48-50, 85-87 — seller_id FK and seller relationship

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: Task execution wrapped in BaseSessionTask.execute() session lifecycle (app/services/base_task.py:84-96)
- Atomic requirements: None (read-only task; no database writes)
- Retry / idempotency: Task can be retried safely (no side effects); same part_key produces consistent output given same inventory state
- Ordering / concurrency controls: No locking required (read-only); concurrent cleanup tasks on different parts are safe; concurrent cleanups of same part waste resources but don't corrupt state
- Evidence: app/services/base_task.py:84-96 — Session commit/rollback pattern; app/services/ai_part_cleanup_task.py (new) — Read-only queries with selectinload

---

## 8) Errors & Edge Cases

- Failure: Part key does not exist in database
- Surface: POST /ai-parts/cleanup endpoint
- Handling: Return HTTP 400 with ErrorResponseSchema; message "Part with key XXXX not found"
- Guardrails: Validate part existence before starting task; fail fast
- Evidence: app/api/ai_parts.py:37-124 — Error response pattern; app/exceptions.py — RecordNotFoundException

---

- Failure: Part key invalid format (not 4 uppercase chars)
- Surface: POST /ai-parts/cleanup endpoint
- Handling: Pydantic validation error converted to HTTP 400 with field-level error details
- Guardrails: CleanupPartRequestSchema with regex pattern constraint on part_key field
- Evidence: app/schemas/ai_part_analysis.py:231-339 — Schema validation with Field constraints

---

- Failure: Real AI disabled and no dummy response configured
- Surface: POST /ai-parts/cleanup endpoint or task execution
- Handling: Return HTTP 400 with InvalidOperationException message "real AI usage is disabled in testing mode"
- Guardrails: Check Settings.real_ai_allowed before starting task; short-circuit in endpoint
- Evidence: app/api/ai_parts.py:102-112 — AI disabled check in analyze_part()

---

- Failure: OpenAI API call fails (network, rate limit, invalid response)
- Surface: AIPartCleanupTask.execute_session()
- Handling: Catch exception, return AIPartCleanupTaskResultSchema with success=false, error_message="AI cleanup failed: <error>"
- Guardrails: Wrap AI service call in try/except; log full error with traceback; return user-friendly message
- Evidence: app/services/ai_part_analysis_task.py:69-74 — AI failure handling pattern

---

- Failure: AI returns incomplete or invalid data (missing required fields)
- Surface: AIPartCleanupTask result parsing
- Handling: Pydantic validation on CleanedPartDataSchema; if fails, return error result
- Guardrails: Schema validation with required fields; default to original part values for missing optionals
- Evidence: app/schemas/ai_part_analysis.py:33-133 — PartAnalysisDetailsSchema with nullable fields

---

- Failure: Part count exceeds memory limits (>10,000 parts)
- Surface: AIPartCleanupTask context building
- Handling: Check part count before serialization; if >10000, return error result "Too many parts for cleanup context (limit: 10000)"
- Guardrails: Early count query; fail before loading full result set
- Evidence: app/services/ai_part_cleanup_task.py (new) — Count check before context serialization

---

- Failure: Task cancelled by user during AI call
- Surface: AIPartCleanupTask.execute_session()
- Handling: Check is_cancelled after AI response; return AIPartCleanupTaskCancelledResultSchema
- Guardrails: Cancellation checks at phase boundaries (before AI call, after AI response)
- Evidence: app/services/ai_part_analysis_task.py:54-56, 76-78, 96-98 — Cancellation check pattern

---

## 9) Observability / Telemetry

- Signal: ai_cleanup_requests_total
- Type: Counter
- Trigger: When cleanup task starts (AIPartCleanupTask.execute_session entry)
- Labels / fields: {"status": "started" | "success" | "error" | "cancelled"}
- Consumer: Grafana dashboard for AI feature usage monitoring
- Evidence: app/services/metrics_service.py — Existing AI analysis metrics pattern

---

- Signal: ai_cleanup_duration_seconds
- Type: Histogram
- Trigger: When cleanup task completes (success or error, not cancelled)
- Labels / fields: {"status": "success" | "error"}
- Consumer: Latency monitoring for AI cleanup operations
- Evidence: app/services/metrics_service.py — record_operation_duration pattern

---

- Signal: ai_cleanup_part_count
- Type: Gauge
- Trigger: When building context (after querying all parts)
- Labels / fields: None
- Consumer: Operational visibility into context size for performance analysis
- Evidence: app/services/metrics_service.py — update_gauge pattern

---

- Signal: Structured log "AI cleanup started for part {part_key}"
- Type: Structured log (INFO level)
- Trigger: At task start (after part existence validation)
- Labels / fields: {"part_key": string, "task_id": UUID}
- Consumer: Log aggregation for debugging and audit trail
- Evidence: app/services/ai_part_analysis_task.py:52-56 — Logging pattern

---

- Signal: Structured log "AI cleanup completed for part {part_key}"
- Type: Structured log (INFO level)
- Trigger: At task success (before returning result)
- Labels / fields: {"part_key": string, "task_id": UUID, "fields_changed": list[string]}
- Consumer: Audit trail of cleanup operations
- Evidence: app/services/ai_part_analysis_task.py:112-115 — Completion logging pattern

---

## 10) Background Work & Shutdown

- Worker / job: AIPartCleanupTask (background task in TaskService thread pool)
- Trigger cadence: Event-driven (triggered by POST /ai-parts/cleanup API call)
- Responsibilities: Query part data, build context JSON, call AI service, parse response, return cleaned data
- Shutdown handling: TaskService.shutdown() waits for running tasks with timeout (app/services/task_service.py); cleanup task checks is_cancelled and returns early if shutdown requested
- Evidence: app/services/task_service.py — Task lifecycle management with graceful shutdown; app/services/base_task.py:51-58 — Cancellation protocol

---

## 11) Security & Permissions (if applicable)

Not applicable. No authentication/authorization in this single-user application. No sensitive data exposure (part data already accessible via other endpoints). No rate limiting beyond existing OpenAI API quota management.

---

## 12) UX / UI Impact (if applicable)

- Entry point: Part detail page or inventory table (frontend initiates cleanup via API call)
- Change: New "Clean up part data" action button/menu item on part pages
- User interaction: Click cleanup → see SSE progress updates → review diff of original vs cleaned data → accept/reject changes
- Dependencies: Frontend must implement diff visualization, field-by-field acceptance, type creation flow for new type suggestions, seller resolution for seller name→id mapping
- Evidence: docs/features/ai_part_cleanup/change_brief.md:66-70 — "The UI will handle showing a diff and helping the user apply changes"

---

## 13) Deterministic Test Plan (new/changed behavior only)

- Surface: AIPartCleanupTask.execute_session()
- Scenarios:
  - Given part exists with minimal data, When cleanup executes, Then returns CleanedPartDataSchema with all fields populated
  - Given part exists with complete data, When cleanup executes, Then AI improves data quality without losing existing values
  - Given part does not exist, When cleanup executes, Then raises RecordNotFoundException before starting task
  - Given cleanup task running, When user cancels, Then returns AIPartCleanupTaskCancelledResultSchema
  - Given OpenAI API fails, When cleanup executes, Then returns error result with user-friendly message
  - Given 100 other parts in inventory, When cleanup executes, Then context includes all 100 parts serialized correctly
  - Given part has type and seller, When cleanup executes, Then context includes type.name and seller.name strings
  - Given part has null seller, When cleanup executes, Then context includes seller: null
  - Given AI suggests type change, When cleanup executes, Then cleaned data includes new type name
  - Given AI returns invalid data, When cleanup executes, Then schema validation fails and returns error result
  - Given >10,000 parts in inventory, When cleanup executes, Then returns error "Too many parts for cleanup context"
- Fixtures / hooks: PartFactory for creating test parts with various field combinations; AIService mock for controlled AI responses; Settings fixture for real_ai_allowed=False with dummy response path
- Gaps: None (comprehensive coverage planned)
- Evidence: tests/services/test_ai_part_analysis_task.py — Existing task testing patterns with fixtures

---

- Surface: AIService.cleanup_part()
- Scenarios:
  - Given part_key and context, When cleanup_part() called, Then builds prompt with mode="cleanup" and all_parts context
  - Given cleanup mode, When building tools, Then includes URLClassifier but excludes DuplicateSearchFunction
  - Given AI response with analysis_result, When parsing response, Then maps fields to CleanedPartDataSchema correctly
  - Given AI response missing analysis_result, When parsing response, Then raises exception
  - Given real_ai_allowed=False, When cleanup_part() called, Then raises InvalidOperationException
- Fixtures / hooks: Mock AIRunner for response control; PartFactory for test data; TypeFactory for type relationships
- Gaps: None
- Evidence: tests/services/test_ai_service.py — Existing AI service testing patterns

---

- Surface: POST /api/ai-parts/cleanup
- Scenarios:
  - Given valid part_key, When POST cleanup, Then returns HTTP 201 with TaskStartResponse
  - Given invalid part_key format, When POST cleanup, Then returns HTTP 400 with validation error
  - Given part_key does not exist, When POST cleanup, Then returns HTTP 400 with "Part not found" error
  - Given real_ai_allowed=False without dummy response, When POST cleanup, Then returns HTTP 400 with "AI disabled" error
  - Given valid request, When task completes, Then SSE stream returns AIPartCleanupTaskResultSchema
- Fixtures / hooks: FlaskClient for API testing; PartFactory for test parts; TaskService reset between tests
- Gaps: None
- Evidence: tests/api/test_ai_parts.py — Existing AI endpoint testing patterns

---

- Surface: GET /api/ai-parts/cleanup/<task_id>/result
- Scenarios:
  - Given completed cleanup task, When GET result, Then returns HTTP 200 with AIPartCleanupTaskResultSchema
  - Given task does not exist, When GET result, Then returns HTTP 404
  - Given task not completed, When GET result, Then returns HTTP 404 with "Task not completed" message
- Fixtures / hooks: Pre-completed tasks via TaskService; mock task results
- Gaps: None
- Evidence: tests/api/test_ai_parts.py:197-253 — get_analysis_result() test pattern

---

- Surface: Prompt template mode parameter
- Scenarios:
  - Given mode="cleanup", When rendering template, Then includes cleanup instructions and excludes duplicate search guidance
  - Given mode="analysis", When rendering template, Then includes analysis instructions and duplicate search guidance
  - Given mode unspecified, When rendering template, Then defaults to analysis mode
- Fixtures / hooks: Jinja2 template rendering tests with different mode values
- Gaps: None
- Evidence: tests/services/test_ai_service.py — Prompt building test pattern

---

## 14) Implementation Slices (only if large)

- Slice: Prompt template refactoring
- Goal: Rename and add mode conditionals without breaking analysis flow
- Touches: app/services/prompts/part_search.md → part_analysis.md, app/services/ai_service.py:240-242
- Dependencies: Must deploy atomically; verify all tests pass after rename

---

- Slice: Schemas and service method
- Goal: Define cleanup contracts and AIService.cleanup_part() logic
- Touches: app/schemas/ai_part_cleanup.py, app/services/ai_service.py (new method)
- Dependencies: Requires prompt template refactoring completed

---

- Slice: Task implementation
- Goal: Implement AIPartCleanupTask with context building and error handling
- Touches: app/services/ai_part_cleanup_task.py, tests/services/test_ai_part_cleanup_task.py
- Dependencies: Requires schemas and service method

---

- Slice: API endpoint
- Goal: Wire cleanup endpoint and result retrieval
- Touches: app/api/ai_parts.py, tests/api/test_ai_parts_cleanup.py
- Dependencies: Requires task implementation; full E2E testing possible

---

- Slice: Test data update
- Goal: Ensure test data has realistic cleanup-relevant fields for integration testing
- Touches: app/data/test_data/parts.json
- Dependencies: None; can be done in parallel with other slices

---

## 15) Risks & Open Questions

- Risk: Part count exceeds 10,000 causing OOM or AI context window overflow
- Impact: Task fails or AI produces degraded results due to truncated context
- Mitigation: Early count check with hard limit; document limit in API docs; consider pagination or sampling strategy for large inventories

---

- Risk: AI response time unpredictable (10-60s depending on context size and API load)
- Impact: User perceives cleanup as slow; potential SSE timeout issues
- Mitigation: Progress reporting every 5% to show activity; document expected duration in UI; TaskService timeout configured to 120s (existing)

---

- Risk: Type name collisions or inconsistencies (AI suggests "Microcontroller" but existing type is "Microcontrollers")
- Impact: Frontend creates duplicate type or fails to match existing type
- Mitigation: Case-insensitive type matching in frontend; normalize type names to singular form; consider backend fuzzy matching helper

---

- Risk: Seller name resolution ambiguous (multiple sellers with similar names)
- Impact: Frontend assigns wrong seller_id when applying changes
- Mitigation: Return seller_link alongside seller name for frontend to validate match; seller creation flow requires user confirmation

---

- Risk: Prompt template mode conditionals grow complex and hard to maintain
- Impact: Dual-mode prompt diverges in quality or breaks analysis mode
- Mitigation: Keep shared rules in common sections; use clear mode guards; test both modes independently

---

- Question: RESOLVED - Mouser API tool does not exist as separate AIFunction
- Resolution: The AI model has inherent web search capabilities that can query Mouser and other sites. There is no separate MouserAPIFunction tool. Cleanup mode will use URLClassifierFunction (already instantiated in AIService) and rely on the AI's built-in web search for Mouser queries.
- Evidence: Grep of app/utils/ai/ shows only url_classification.py and duplicate_search.py; no Mouser-specific tool exists

---

- Question: Should cleanup results be persisted in database for audit/history?
- Why it matters: No requirement specified but could be valuable for tracking data quality improvements over time
- Owner / follow-up: Product decision; if needed, add CleanupHistory model in separate feature

---

- Question: What should happen if AI removes data (e.g., sets manufacturer to null)?
- Why it matters: Prompt says "without losing data" but AI might correct wrong values by nulling them
- Owner / follow-up: Prompt engineering; instruct AI to only null fields when correcting definitively wrong data, not on uncertainty

---

## 16) Confidence (one line)

Confidence: High — Implementation follows established patterns from AIPartAnalysisTask and AIService; prompt template refactoring is low-risk atomic change; read-only task eliminates transaction complexity; comprehensive test coverage planned.
