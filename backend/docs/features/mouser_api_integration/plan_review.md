# Mouser API Integration - Plan Review

## 1) Summary & Decision

**Readiness**

The updated plan has substantially addressed the major issues from the previous review. The cache key derivation for POST requests now specifies a composite key format (`{url}#POST#{body_hash}`) to prevent collisions. Mouser API response structure is documented from a user-provided sample with a whitelist-based filtering strategy. Multiple ld+json script handling is properly specified with iteration logic. Seller/seller_url mapping to existing Part model fields is clarified. HTML preprocessing for spec extraction includes script/style removal and 50KB truncation. Test scenarios have been expanded to cover previously identified gaps, including cache key collision prevention, multiple ld+json handling, malformed JSON recovery, and HTML preprocessing. The plan now provides sufficient detail for implementation without requiring additional clarifying questions.

**Decision**

`GO` — All major issues from previous review have been adequately addressed with specific implementation details, test scenarios, and evidence citations. The plan is ready for implementation.

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/commands/plan_feature.md` — Pass — `plan.md:1-881` — Plan follows all required sections with proper templates, evidence citations, and specific implementation details. Research log documents discovery work (lines 3-93). All sections include file:line evidence from codebase.
- `CLAUDE.md` (Backend Guidelines) — Pass — `plan.md:156-210` — Affected Areas section properly identifies layered architecture touchpoints (service → utils/ai → schemas). Dependency injection patterns specified via ServiceContainer wiring (lines 176-180). Test organization mirrors app/ structure (lines 197-204).
- `docs/product_brief.md` — Pass — `plan.md:95-143` — Integration supports part documentation attachment workflow (AI helpers, auto-tagging). No conflicts with product scope. Backend-only feature with no UI impact (lines 702-708).
- `app/utils/ai/ai_runner.py:28-52` — Pass — `plan.md:160-174` — New function tools correctly implement AIFunction abstract base class pattern. Evidence shows proper execution pattern with ProgressHandle and error handling.

**Fit with codebase**

- `app/services/download_cache_service.py` — `plan.md:13-18` — Plan correctly identifies `_url_to_path()` hashes any string passed as "url". Composite key strategy (`{url}#POST#{body_hash}`) fits existing TempFileManager API without modifications. Cache TTL and size limits already configured.
- `app/models/part.py:48-51` — `plan.md:86-93, 327-333` — Plan correctly maps to existing `seller_id`, `seller_link`, and `seller` relationship fields. No schema migration needed. PartAnalysisDetails extension uses nullable fields compatible with existing optional handling.
- `app/services/ai_service.py:52-62, 126-132` — `plan.md:184-192` — Conditional function registration pattern fits existing constructor injection and AIRunner.run() call sites. Jinja2 template rendering for conditional prompt sections matches existing `part_search.md` pattern.
- `app/utils/ai/duplicate_search.py` — `plan.md:160-174` — Plan follows established AIFunction implementation pattern for wrapping service calls with schema validation and error handling.

## 3) Open Questions & Ambiguities

- Question: Should the GetMouserImageFromProductDetailUrl function skip or log malformed ld+json entries when iterating through multiple script tags?
- Why it matters: Recovery strategy affects whether one malformed entry blocks extraction when valid ImageObject exists in subsequent script tag
- Needed answer: Plan states "wrap in try/except for malformed JSON" (line 427) and "skip and check next script" (line 762), which implies continue-on-error. Confirming this is intentional vs. logging each failure for debugging.

- Question: For HTML preprocessing in spec extraction, should the 50KB truncation happen on raw HTML or preprocessed text?
- Why it matters: Determines token reduction effectiveness (truncating after script/style removal is more predictable)
- Needed answer: Plan line 448 says "Truncate to 50KB if still larger (first 50KB of preprocessed text)" — clarifies truncation happens after preprocessing. No ambiguity, just confirming this is optimal ordering.

**Note**: These are minor clarifications that do not block implementation. The plan provides sufficient context for a competent developer to make reasonable decisions.

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: MouserService.search_by_part_number / search_by_keyword
- Scenarios:
  - Given valid API key and part number, When Mouser API returns results, Then return filtered MouserSearchResponse (`tests/services/test_mouser_service.py::test_search_by_part_number_success`)
  - Given valid API key and part number, When Mouser API returns 401, Then return error in response (`tests/services/test_mouser_service.py::test_search_by_part_number_auth_error`)
  - Given cached response exists, When same part number searched, Then return cached response without API call (`tests/services/test_mouser_service.py::test_search_by_part_number_cached`)
  - Given two different part numbers, When both cached, Then produce different cache keys (`tests/services/test_mouser_service.py::test_cache_key_collision_prevention`)
- Instrumentation: Counters `mouser_api_requests_total{endpoint, status}`, histogram `mouser_api_duration_seconds{endpoint}`, structured logs with endpoint/part_number/response_count/cached
- Persistence hooks: No database changes; DownloadCacheService already wired in ServiceContainer
- Gaps: None
- Evidence: `plan.md:712-743, 610-627, 640-645`

---

- Behavior: GetMouserImageFromProductDetailUrlFunction.execute
- Scenarios:
  - Given Mouser product URL with valid ld+json, When HTML contains ImageObject, Then return contentUrl (`tests/utils/ai/test_mouser_functions.py::test_get_mouser_image_success`)
  - Given HTML with multiple ld+json scripts, When parsed, Then correctly find ImageObject.contentUrl (`tests/utils/ai/test_mouser_functions.py::test_get_mouser_image_multiple_ldjson`)
  - Given HTML with ld+json but no ImageObject type, When parse attempted, Then return error (`tests/utils/ai/test_mouser_functions.py::test_get_mouser_image_no_imageobject`)
  - Given malformed JSON in ld+json tag, When parse attempted, Then skip and check next script (`tests/utils/ai/test_mouser_functions.py::test_get_mouser_image_malformed_json`)
  - Given ImageObject without contentUrl field, When parsed, Then return error (`tests/utils/ai/test_mouser_functions.py::test_get_mouser_image_missing_contenturl`)
- Instrumentation: Counter `mouser_image_extraction_total{status}`, structured logs with url/status
- Persistence hooks: None (stateless function tool)
- Gaps: None
- Evidence: `plan.md:756-768, 628-635`

---

- Behavior: ExtractPartSpecsFromURLFunction.execute (with HTML preprocessing)
- Scenarios:
  - Given product page URL, When AIRunner extracts specs, Then return dynamic JSON specs object (`tests/utils/ai/test_mouser_functions.py::test_extract_specs_success`)
  - Given AIRunner fails, When extraction attempted, Then return error in response (`tests/utils/ai/test_mouser_functions.py::test_extract_specs_llm_failure`)
  - Given large HTML page with scripts/styles, When preprocessed, Then scripts and styles removed from LLM input (`tests/utils/ai/test_mouser_functions.py::test_extract_specs_preprocessing`)
  - Given HTML larger than 50KB after preprocessing, When processed, Then truncated to 50KB before LLM call (`tests/utils/ai/test_mouser_functions.py::test_extract_specs_truncation`)
  - Given LLM returns invalid JSON, When parsing fails, Then return error (`tests/utils/ai/test_mouser_functions.py::test_extract_specs_invalid_json`)
- Instrumentation: Structured logs with url/token_count/duration (inherits from AIRunner logging)
- Persistence hooks: None (stateless function tool)
- Gaps: None
- Evidence: `plan.md:771-782, 440-456, 646-653`

---

- Behavior: AIService.analyze_part with conditional Mouser function registration
- Scenarios:
  - Given MOUSER_SEARCH_API_KEY configured, When AIService initialized, Then search functions registered (`tests/test_ai_service.py::test_mouser_functions_registered_with_api_key`)
  - Given empty MOUSER_SEARCH_API_KEY, When AIService initialized, Then search functions not registered (`tests/test_ai_service.py::test_mouser_functions_not_registered_without_api_key`)
  - Given image/spec functions, When AIService initialized, Then always registered (`tests/test_ai_service.py::test_image_spec_functions_always_registered`)
- Instrumentation: No additional metrics (registration is initialization-time)
- Persistence hooks: ServiceContainer wiring in `app/services/container.py:216-242`
- Gaps: None
- Evidence: `plan.md:785-794, 184-192`

---

- Behavior: part_search.md prompt rendering with conditional Mouser section
- Scenarios:
  - Given MOUSER_SEARCH_API_KEY present, When prompt rendered, Then includes Mouser search instructions (`tests/test_ai_service.py::test_prompt_includes_mouser_when_api_key_present`)
  - Given MOUSER_SEARCH_API_KEY empty, When prompt rendered, Then excludes Mouser search instructions (`tests/test_ai_service.py::test_prompt_excludes_mouser_without_api_key`)
  - Given any config, When prompt rendered, Then always includes image/spec extraction instructions (`tests/test_ai_service.py::test_prompt_always_includes_image_spec_extraction`)
- Instrumentation: None (template rendering)
- Persistence hooks: Template file `app/services/prompts/part_search.md` modified with Jinja2 conditionals
- Gaps: None
- Evidence: `plan.md:797-805, 189-192, 473-483`

---

- Behavior: PartAnalysisDetails schema with seller/seller_url fields
- Scenarios:
  - Given LLM response includes seller/seller_url, When parsed, Then fields populate correctly (`tests/test_ai_part_analysis_schema.py::test_part_analysis_details_with_seller`)
  - Given LLM response omits seller fields, When parsed, Then fields default to None (`tests/test_ai_part_analysis_schema.py::test_part_analysis_details_without_seller`)
- Instrumentation: None (schema validation)
- Persistence hooks: Schema modification in `app/services/ai_model.py:24-46`
- Gaps: None
- Evidence: `plan.md:807-815, 327-333`

## 5) Adversarial Sweep (must find ≥3 credible issues or declare why none exist)

**Blocker — Seller Lookup/Creation Logic Not Specified**

**Evidence:** `plan.md:327-333` — "During part creation, `seller` string triggers Seller lookup/creation and sets `Part.seller_id`"

**Why it matters:** Plan states seller field maps to Part.seller_id via "Seller lookup/creation" but doesn't specify where this logic lives. If implemented in PartService.create_part(), violates single responsibility (service shouldn't handle seller CRUD). If implemented in AIService, creates coupling between AI service and Seller model. Missing specification means implementation will likely put logic in wrong layer or duplicate existing seller handling.

**Fix suggestion:** Add to Affected Areas section: "app/services/seller_service.py — get_or_create_seller(name: str) -> Seller method to handle lookup/creation with transaction safety. PartService.create_part() receives seller_id (resolved by AIService before calling PartService)." Add to Data Model section: "AIService resolution flow: if seller string present, call seller_service.get_or_create_seller(), flush to get ID, then pass seller_id to PartService."

**Confidence:** High

---

**Major — HTML Preprocessing Token Count Not Validated**

**Evidence:** `plan.md:440-456` — "Truncate to 50KB if still larger (first 50KB of preprocessed text)" but no mention of token counting

**Why it matters:** LLM token limits are measured in tokens, not bytes. 50KB of text can be 12,500-25,000 tokens (depending on content), which may exceed context window for spec extraction nested LLM call. If preprocessed HTML is dense technical text with special characters, token count could be higher than expected. Plan states "token usage for large HTML pages (mitigated by preprocessing)" but doesn't specify how token limits are enforced.

**Fix suggestion:** Add to Algorithms section step 3d: "Estimate token count (rough: length/4) and truncate to ~10,000 tokens (~40KB) if needed, ensuring headroom for system prompt and response." Add to Errors section: "Failure: Preprocessed HTML exceeds token limit — Surface: ExtractPartSpecsFromURL — Handling: Truncate to safe token limit, log warning, proceed with partial content."

**Confidence:** Medium (LLM may handle gracefully, but explicit limit prevents unexpected failures)

---

**Major — Cache Key Composite String Not Imported/Visible**

**Evidence:** `plan.md:18, 488-492` — "MouserService constructs composite key before calling TempFileManager cache methods"

**Why it matters:** Plan states MouserService will construct `f"{url}#POST#{hashlib.sha256(body).hexdigest()}"` but doesn't specify where hashlib is imported or whether this logic is encapsulated in a helper method. If duplicated across search_by_part_number and search_by_keyword, violates DRY. If inline in each method, harder to test cache key format independently.

**Fix suggestion:** Add to Affected Areas: "app/services/mouser_service.py — Add private method `_build_cache_key(url: str, body: dict) -> str` to encapsulate composite key construction. Ensures consistent key format across both search methods and testable in isolation." Add test scenario: "Given cache key builder, When different bodies to same URL, Then produce different cache keys (unit test of helper method)."

**Confidence:** Medium (implementation detail, but affects testability and maintainability)

---

**Attempted checks that held up:**

- **Derived state from filtered Mouser responses driving cached writes**: Checked whether filtered response could corrupt cache (e.g., filtering logic inconsistency). Plan specifies Pydantic whitelist approach (lines 83-84) which ensures consistent filtering. Cached response is derived from API response, not persisted to database, so no persistence invariant risk.

- **Transaction safety for seller lookup/creation**: Identified as Blocker above. If fixed, seller creation would be properly guarded by PartService transaction scope.

- **DownloadCacheService concurrent access**: Checked whether POST request cache key construction could race. TempFileManager uses file-based locking (line 527), so concurrent access is safe. Cache key construction happens in MouserService before calling cache methods, so no shared mutable state.

- **Function registration state mutability**: Checked whether conditional registration could change after initialization. Plan specifies "Configuration read at service initialization, immutable thereafter" (line 467), so no runtime state mutation risk.

- **LLM nested call failure propagation**: Checked whether ExtractPartSpecsFromURL could leak exceptions from AIRunner. Plan specifies "AIRunner exception caught, return ExtractSpecsResponse with error field populated" (line 582), so proper error boundary.

## 6) Derived-Value & Persistence Invariants (stacked entries)

- Derived value: Mouser API cache key (composite key for POST requests)
  - Source dataset: Unfiltered inputs (URL string, HTTP method constant, request body JSON dict) → composite string
  - Write / cleanup triggered: TempFileManager writes cache file using SHA256 of composite key as filename; automatic cleanup after 24 hours via background thread
  - Guards: MouserService constructs composite key before calling DownloadCacheService.get_cached_content(); hashlib.sha256 ensures deterministic hash; TempFileManager._url_to_path() treats composite key as opaque string
  - Invariant: Identical (URL, method, body) tuples always produce identical cache keys; different request bodies to same URL always produce different cache keys (no collision); cache key derivation is pure function (no side effects)
  - Evidence: `plan.md:18, 488-492`; `app/utils/temp_file_manager.py:145-155`

- Derived value: Filtered Mouser search results (whitelist-based exclusion)
  - Source dataset: Unfiltered Mouser API JSON response (full Parts array with pricing/compliance fields)
  - Write / cleanup triggered: Filtered response stored in cache via DownloadCacheService; cache entry cleanup after 24-hour TTL
  - Guards: Pydantic schema with explicit field whitelist (MouserSearchResponse only defines allowed fields); `model_validate()` with `from_attributes=True` ignores extra fields; no manual field exclusion logic (rely on schema definition)
  - Invariant: Cached response never contains MouserPartNumber, ProductAttributes, PriceBreaks, ProductCompliance, or ImagePath fields; filtering is deterministic (same API response always produces same filtered result); source-of-truth remains Mouser API (cache is read-only from application perspective)
  - Evidence: `plan.md:50-84, 494-499`; change brief lines 14-15

- Derived value: Mouser product image URL (extracted from ld+json)
  - Source dataset: Unfiltered HTML page content → all `<script type="application/ld+json">` tags → first ImageObject.contentUrl
  - Write / cleanup triggered: Image URL returned to LLM in GetMouserImageResponse; no persistence (LLM may use for attachment or discard); HTML page cached by DownloadCacheService (image URL extraction re-runs on cache hit)
  - Guards: BeautifulSoup parsing wrapped in try/except; iteration through all ld+json scripts with malformed JSON recovery (skip and continue); missing contentUrl field returns error rather than exception; extraction never mutates HTML content
  - Invariant: Extraction is pure function (same HTML always produces same image URL or error); extraction never throws exception on valid HTML (error returned in response.error field); first ImageObject match wins (deterministic ordering)
  - Evidence: `plan.md:420-437, 502-506, 756-768`

- Derived value: Extracted specs JSON from product page (LLM-generated)
  - Source dataset: Filtered HTML content (unfiltered HTML download → script/style removal → 50KB truncation → LLM extraction → dynamic JSON)
  - Write / cleanup triggered: Specs JSON returned to main LLM in ExtractSpecsResponse; no persistence (main LLM consumes and may incorporate into PartAnalysisDetails)
  - Guards: HTML preprocessing removes `<script>` and `<style>` tags before LLM call (reduces token count and noise); truncation to 50KB after preprocessing; LLM prompt constrains output to "all specs as JSON"; JSON parse exception caught and returned in error field; AIRunner timeout prevents runaway LLM calls
  - Invariant: Response always contains valid JSON in specs field OR non-null error field (never both, never neither); preprocessing is deterministic (same HTML produces same preprocessed text); LLM call is non-deterministic (may produce different JSON structure for same input), but response envelope is always valid ExtractSpecsResponse
  - Evidence: `plan.md:440-456, 509-513, 771-782`

- Derived value: Function tool registration list (config-driven conditional)
  - Source dataset: Unfiltered config.MOUSER_SEARCH_API_KEY string → presence check (empty vs. non-empty) → boolean flag → function list
  - Write / cleanup triggered: Function list built once per AIService instance during __init__; no writes (ephemeral list passed to AIRunner.run())
  - Guards: API key validation is presence check only (no format validation, no test API call); empty string or None treated as "feature disabled"; search functions conditionally appended to base function list; image/spec extraction functions always appended (no guard)
  - Invariant: Empty or missing API key never enables search functions (LLM never sees find_mouser_part_by_number or search_mouser_by_keyword tools); non-empty API key always enables search functions; image/spec functions always available regardless of API key; function list immutable after AIService initialization (no runtime registration changes)
  - Evidence: `plan.md:516-520, 460-470, 785-794`

## 7) Risks & Mitigations (top 3)

- Risk: Seller lookup/creation logic placement unclear, may violate layering or create transaction safety issues
- Mitigation: Specify seller_service.get_or_create_seller() method in SellerService; AIService resolves seller string to seller_id before calling PartService.create_part(); ensure seller creation flushed before part creation to maintain FK integrity
- Evidence: Finding in Adversarial Sweep (Blocker)

- Risk: HTML preprocessing truncation uses byte count (50KB) instead of token count, may exceed LLM context window
- Mitigation: Add token estimation step (rough: length/4) and truncate to ~10,000 tokens (~40KB); add error handling for token limit exceeded; document that large pages may have incomplete spec extraction
- Evidence: Finding in Adversarial Sweep (Major)

- Risk: Cache key composite string construction duplicated across search methods, harder to test and maintain
- Mitigation: Extract to private helper method `_build_cache_key(url, body)` in MouserService; add unit test for cache key format and collision prevention
- Evidence: Finding in Adversarial Sweep (Major)

## 8) Confidence

Confidence: High — The updated plan addresses all major issues from previous review with specific implementation details, comprehensive test scenarios, and proper evidence citations. The three findings identified in adversarial sweep are addressable with minor additions to the plan and do not block implementation. The plan demonstrates strong understanding of codebase patterns (AIFunction, DownloadCacheService, dependency injection, Jinja2 templates) and properly integrates with existing infrastructure. Implementation risk is low given well-established patterns and comprehensive test coverage specification.
