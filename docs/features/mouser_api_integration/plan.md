# Mouser API Integration - Technical Plan

## 0) Research Log & Findings

### Areas Researched

1. **Existing AI Function Tool Patterns**
   - Examined `app/utils/ai/duplicate_search.py` and `app/utils/ai/url_classification.py`
   - Both implement `AIFunction` abstract base class from `app/utils/ai/ai_runner.py`
   - Function tools are registered in `AIService` and passed to `AIRunner.run()`
   - Functions receive `ProgressHandle` for user feedback during execution

2. **Download Caching Infrastructure**
   - `DownloadCacheService` provides `get_cached_content()` method with 1-day TTL
   - Returns `DownloadResult(content: bytes, content_type: str)`
   - Uses `TempFileManager` for disk-based caching with hash-based keys (SHA256 of URL string)
   - Already configured with proper User-Agent headers (matches DocumentService requirements)
   - **Cache key for POST requests**: TempFileManager hashes whatever string is passed as "url". For POST requests, construct composite key: `f"{url}#POST#{hashlib.sha256(body).hexdigest()}"` before passing to cache methods. This ensures different request bodies to same URL produce different cache keys.

3. **Dependency Injection Patterns**
   - Services wired in `app/services/container.py` using `dependency-injector`
   - AI functions created as Factory providers and injected into `AIService`
   - Config values accessed via `providers.Dependency(instance_of=Settings)`

4. **Prompt Templating**
   - `app/services/prompts/part_search.md` uses Jinja2 for dynamic content
   - Conditional sections enabled via `{% if condition %}` blocks
   - Existing example: `{%- for category in categories %}` loop

5. **Testing Patterns**
   - Service tests use mock dependencies and verify method calls
   - Function tool tests verify schema validation and execution behavior
   - AI integration tests mock `AIRunner` responses with proper Pydantic models

### Key Findings

- **No existing HTTP API client service**: Need to create new `MouserService` for API calls
- **Conditional feature registration**: Function tools can be selectively registered based on config
- **HTML parsing precedent**: `HtmlDocumentHandler` already does HTML parsing for metadata extraction
- **Nested LLM calls**: `DuplicateSearchService` shows pattern for using `AIRunner` within a function tool
- **Error handling philosophy**: Return errors in function response rather than raising; LLM handles gracefully

### Special Considerations

- Mouser API responses must be filtered to exclude pricing/compliance fields (per change brief)
- Image extraction requires parsing `application/ld+json` script tags in HTML
- Spec extraction function needs to call LLM internally (similar to DuplicateSearchFunction pattern)
- Prompt must conditionally include Mouser instructions only when API key configured

### Mouser API Response Structure (from user-provided sample)

The Mouser API response has this structure:
```json
{
  "Errors": [],
  "SearchResults": {
    "NumberOfResult": 607,
    "Parts": [
      {
        "Availability": "23212 In Stock",
        "DataSheetUrl": "https://...",
        "Description": "...",
        "FactoryStock": "0",
        "ImagePath": "https://...",           // EXCLUDE
        "Category": "...",
        "LeadTime": "...",
        "LifecycleStatus": null,
        "Manufacturer": "...",
        "ManufacturerPartNumber": "04CPT-B1-2A",
        "Min": "1",
        "Mult": "1",
        "MouserPartNumber": "306-04CPT-B1-2A",  // EXCLUDE
        "ProductAttributes": [...],            // EXCLUDE
        "PriceBreaks": [...],                  // EXCLUDE
        "ProductDetailUrl": "https://...",
        "ROHSStatus": "...",
        "ProductCompliance": [...]             // EXCLUDE
      }
    ]
  }
}
```

**Filtering strategy**: Use whitelist approach—define Pydantic schema with only desired fields. Pydantic's `model_validate()` with `from_attributes=True` will ignore extra fields.

### Part Model Seller Fields (already exist)

The Part model (`app/models/part.py:48-51`) already has:
- `seller_id: Mapped[int | None]` — FK to sellers table
- `seller_link: Mapped[str | None]` — URL to seller page
- `seller: Mapped[Optional["Seller"]]` — relationship

The PartAnalysisDetails schema will add `seller` (string name) and `seller_url` (string URL) fields that map to these existing Part model fields during part creation.

## 1) Intent & Scope

**User intent**

Add Mouser Electronics API integration to the AI part analysis system, enabling the LLM to search Mouser's catalog by part number or keyword, extract high-quality product images from Mouser pages, and extract structured specifications from any product page URL using LLM analysis.

**Prompt quotes**

"Add Mouser API integration as function tools available to the LLM during part analysis."

"Use existing `DownloadCacheService.get_cached_content()` for caching Mouser API responses."

"Prompt instructions for Mouser search are conditionally included via Jinja2 templating."

"Return Mouser API errors verbatim in the function response. The LLM will handle errors appropriately."

**In scope**

- Create `MouserService` for HTTP API calls to Mouser search endpoints
- Implement `SearchMouserByPartNumber` function tool (POST /api/v1/search/partnumber)
- Implement `SearchMouserByKeyword` function tool (POST /api/v1/search/keyword)
- Implement `GetMouserImageFromProductDetailUrl` function tool (HTML parsing)
- Implement `ExtractPartSpecsFromURL` function tool (LLM-based extraction)
- Add `MOUSER_SEARCH_API_KEY` configuration field
- Conditionally register search functions only when API key present
- Update `part_search.md` prompt with conditional Mouser usage instructions
- Cache all Mouser API responses using existing `DownloadCacheService`
- Filter Mouser API responses to exclude pricing/compliance data
- Wire new services and functions through dependency injection container

**Out of scope**

- Mouser API rate limiting or quota management
- Mouser API error retry logic beyond existing DownloadCacheService capabilities
- Cost tracking for Mouser API usage (no billing/metering)
- Mouser API authentication beyond simple API key header
- Historical tracking of Mouser API usage
- Direct database storage of Mouser search results
- UI changes (backend-only feature)

**Assumptions / constraints**

- User has obtained valid Mouser Search API key and configured it in environment
- Mouser API responses conform to documented schema (no versioning handled)
- 1-day cache TTL is acceptable for Mouser search results
- HTML structure of Mouser product pages remains stable for image extraction
- LLM-based spec extraction is acceptable trade-off vs parsing structured data
- Existing `DownloadCacheService` User-Agent headers work with Mouser endpoints
- API key presence check is sufficient (no key validation/test on startup)

## 2) Affected Areas & File Map

- Area: `app/config.py`
- Why: Add `MOUSER_SEARCH_API_KEY` environment variable configuration
- Evidence: `app/config.py:113-134` — Existing OpenAI configuration fields follow this pattern with Field() descriptors

---

- Area: `app/services/mouser_service.py` (NEW)
- Why: Create service for Mouser API HTTP calls with request/response handling
- Evidence: `app/services/duplicate_search_service.py:25-60` — Pattern for service that calls external APIs with config injection

---

- Area: `app/utils/ai/mouser_search.py` (NEW)
- Why: Implement SearchMouserByPartNumber and SearchMouserByKeyword function tools
- Evidence: `app/utils/ai/duplicate_search.py:16-72` — Pattern for AIFunction implementation with service delegation

---

- Area: `app/utils/ai/mouser_image.py` (NEW)
- Why: Implement GetMouserImageFromProductDetailUrl function tool with HTML parsing
- Evidence: `app/services/html_document_handler.py` (referenced in container.py:111-116) — Shows HTML parsing patterns; `app/utils/ai/url_classification.py:29-46` — Pattern for URL-based function tools

---

- Area: `app/utils/ai/extract_specs.py` (NEW)
- Why: Implement ExtractPartSpecsFromURL function tool using LLM
- Evidence: `app/services/duplicate_search_service.py:61-100` — Pattern for service using AIRunner; `app/utils/ai/duplicate_search.py:16-72` — Pattern for function wrapping service call

---

- Area: `app/services/container.py`
- Why: Wire MouserService and new function tools into dependency injection container
- Evidence: `app/services/container.py:216-229` — Pattern for wiring duplicate_search_service and duplicate_search_function; `app/services/container.py:232-242` — Pattern for injecting functions into AIService

---

- Area: `app/services/ai_service.py`
- Why: Register new function tools conditionally based on MOUSER_SEARCH_API_KEY presence
- Evidence: `app/services/ai_service.py:52-62` — Constructor receives function dependencies; `app/services/ai_service.py:126-132` — Pattern for passing functions to AIRunner.run()

---

- Area: `app/services/prompts/part_search.md`
- Why: Add conditional Mouser usage instructions and always-present sections for image/spec extraction
- Evidence: `app/services/prompts/part_search.md:30-33` — Existing Jinja2 template with category loop; `app/services/ai_service.py:235-249` — Prompt rendering with Jinja2 Environment

---

- Area: `tests/services/test_mouser_service.py` (NEW)
- Why: Unit tests for MouserService API calls and response filtering
- Evidence: `tests/test_duplicate_search_service.py:1-100` — Pattern for testing services that call external APIs with mocked responses

---

- Area: `tests/utils/ai/test_mouser_functions.py` (NEW)
- Why: Unit tests for all Mouser-related function tools
- Evidence: `tests/test_ai_service.py:86-108` — Pattern for testing AI functions with mocked dependencies

---

- Area: `app/schemas/mouser.py` (NEW)
- Why: Pydantic schemas for Mouser API request/response validation
- Evidence: `app/schemas/duplicate_search.py` — Pattern for request/response schemas used by function tools

---

- Area: `app/services/ai_model.py`
- Why: Add optional seller/seller_url fields to PartAnalysisDetails for Mouser seller information
- Evidence: `app/services/ai_model.py:24-46` — PartAnalysisDetails schema definition with optional fields

## 3) Data Model / Contracts

- Entity / contract: MouserSearchByPartNumberRequest
- Shape:
  ```json
  {
    "part_number": "string"  // Mouser part number or manufacturer part number
  }
  ```
- Refactor strategy: New schema, no backwards compatibility needed
- Evidence: `app/utils/ai/duplicate_search.py:44` — AIFunction.get_model() returns Pydantic request model

---

- Entity / contract: MouserSearchByKeywordRequest
- Shape:
  ```json
  {
    "keyword": "string",
    "record_count": 10,  // optional, default 10
    "starting_record": 0  // optional, default 0
  }
  ```
- Refactor strategy: New schema, no backwards compatibility needed
- Evidence: `app/schemas/duplicate_search.py:10-15` — Pattern for request schemas with optional fields

---

- Entity / contract: MouserSearchResponse
- Shape:
  ```json
  {
    "parts": [
      {
        "ManufacturerPartNumber": "string",
        "Manufacturer": "string",
        "Description": "string",
        "ProductDetailUrl": "string",
        "DataSheetUrl": "string",
        "Category": "string",
        "LeadTime": "string",
        "LifecycleStatus": "string",
        "Min": "number",
        "Mult": "number"
        // EXCLUDED: MouserPartNumber, ProductAttributes, PriceBreaks, ProductCompliance, ImagePath
      }
    ],
    "total_results": 0
  }
  ```
- Refactor strategy: New schema, filters raw Mouser API response to exclude pricing/compliance
- Evidence: Change brief lines 14-15 specify fields to exclude

---

- Entity / contract: GetMouserImageRequest
- Shape:
  ```json
  {
    "product_url": "string"  // Mouser product detail page URL
  }
  ```
- Refactor strategy: New schema, no backwards compatibility needed
- Evidence: `app/utils/ai/url_classification.py:10-13` — Pattern for URL-based request schemas

---

- Entity / contract: GetMouserImageResponse
- Shape:
  ```json
  {
    "image_url": "string | null",  // High-quality image URL from ld+json, or null if not found
    "error": "string | null"  // Error message if extraction failed
  }
  ```
- Refactor strategy: New schema, error field allows LLM to handle failures gracefully
- Evidence: Change brief line 59 — "Return Mouser API errors verbatim in the function response"

---

- Entity / contract: ExtractSpecsRequest
- Shape:
  ```json
  {
    "url": "string"  // Product page URL to extract specs from
  }
  ```
- Refactor strategy: New schema, no backwards compatibility needed
- Evidence: `app/utils/ai/url_classification.py:10-13` — Pattern for URL request schemas

---

- Entity / contract: ExtractSpecsResponse
- Shape:
  ```json
  {
    "specs": {
      // Dynamic JSON object with extracted specs
      // Example: {"voltage": "5V", "current": "1A", "package": "SOT-23"}
    },
    "error": "string | null"  // Error if LLM call or parsing failed
  }
  ```
- Refactor strategy: New schema, dynamic specs object accommodates any product type
- Evidence: Change brief line 32-33 — LLM returns "all specs that are mentioned on the page as JSON"

---

- Entity / contract: PartAnalysisDetails (MODIFIED)
- Shape:
  ```python
  # Add two new optional fields:
  seller: str | None = Field(default=None)      # Maps to Part.seller.name (via Seller lookup/creation)
  seller_url: str | None = Field(default=None)  # Maps to Part.seller_link
  ```
- Refactor strategy: Extend existing schema with nullable fields; no migration needed (model not persisted). During part creation, `seller` string triggers Seller lookup/creation and sets `Part.seller_id`; `seller_url` directly maps to `Part.seller_link`.
- Evidence: `app/services/ai_model.py:24-46` — PartAnalysisDetails with optional fields; `app/models/part.py:48-51` — Part.seller_id and Part.seller_link already exist; change brief line 44-45 specify seller as "Mouser" and seller_url as ProductDetailUrl

---

- Entity / contract: Config.MOUSER_SEARCH_API_KEY
- Shape: `str = Field(default="", description="Mouser Search API key")`
- Refactor strategy: New config field, empty default means feature disabled
- Evidence: `app/config.py:113-114` — OPENAI_API_KEY follows same pattern with empty default

## 4) API / Integration Surface

- Surface: Mouser Search API — POST https://api.mouser.com/api/v1/search/partnumber
- Inputs: JSON body `{"SearchByPartRequest": {"mouserPartNumber": "string", "partSearchOptions": "string"}}`, header `apiKey: {MOUSER_SEARCH_API_KEY}`
- Outputs: JSON response with parts array, filtered to exclude MouserPartNumber/ProductAttributes/PriceBreaks/ProductCompliance/ImagePath
- Errors: HTTP errors (401 unauthorized, 429 rate limit, 500 server error) returned verbatim in function response
- Evidence: Change brief lines 10-15 specify API endpoint and filtering; line 59 specifies error handling

---

- Surface: Mouser Search API — POST https://api.mouser.com/api/v1/search/keyword
- Inputs: JSON body `{"SearchByKeywordRequest": {"keyword": "string", "records": 10, "startingRecord": 0}}`, header `apiKey: {MOUSER_SEARCH_API_KEY}`
- Outputs: Same filtered JSON response as part number search
- Errors: Same HTTP error handling as part number search
- Evidence: Change brief lines 17-22 specify keyword search API

---

- Surface: Function tool — find_mouser_part_by_number (internal to LLM)
- Inputs: Pydantic schema `MouserSearchByPartNumberRequest` with part_number field
- Outputs: Pydantic schema `MouserSearchResponse` with filtered parts array or error
- Errors: Network/API errors captured in response error field, LLM decides how to proceed
- Evidence: `app/utils/ai/ai_runner.py:166-190` — Function call execution pattern

---

- Surface: Function tool — search_mouser_by_keyword (internal to LLM)
- Inputs: Pydantic schema `MouserSearchByKeywordRequest` with keyword/record_count/starting_record
- Outputs: Pydantic schema `MouserSearchResponse` with filtered parts array or error
- Errors: Same as part number search function
- Evidence: `app/utils/ai/duplicate_search.py:47-71` — Function execution pattern with error handling

---

- Surface: Function tool — get_mouser_image (internal to LLM)
- Inputs: Pydantic schema `GetMouserImageRequest` with product_url
- Outputs: Pydantic schema `GetMouserImageResponse` with image_url or error
- Errors: HTML parsing failures, missing ld+json, download errors captured in error field
- Evidence: Change brief lines 24-28 specify HTML parsing approach

---

- Surface: Function tool — extract_specs_from_url (internal to LLM)
- Inputs: Pydantic schema `ExtractSpecsRequest` with url
- Outputs: Pydantic schema `ExtractSpecsResponse` with dynamic specs object or error
- Errors: Download failures, LLM failures captured in error field
- Evidence: Change brief lines 30-34 specify LLM-based extraction

## 5) Algorithms & State Machines

- Flow: Mouser part number search
- Steps:
  1. Receive part_number from LLM via function call
  2. Build Mouser API request JSON with SearchByPartRequest wrapper
  3. Check cache using DownloadCacheService with URL+body hash as key
  4. If cache miss: POST to api.mouser.com/api/v1/search/partnumber with apiKey header
  5. Parse JSON response and filter out excluded fields (MouserPartNumber, ProductAttributes, PriceBreaks, ProductCompliance, ImagePath)
  6. Cache filtered response with 1-day TTL
  7. Return MouserSearchResponse to LLM
- States / transitions: None (stateless request/response)
- Hotspots: Network latency for uncached requests (~500ms-2s), JSON parsing overhead for large result sets
- Evidence: `app/services/download_cache_service.py:47-79` — Cache check/miss/store pattern

---

- Flow: Mouser keyword search
- Steps:
  1. Receive keyword, optional record_count, optional starting_record from LLM
  2. Build Mouser API request JSON with SearchByKeywordRequest wrapper
  3. Same cache/API call/filter/return flow as part number search
  4. Filter same fields from results
  5. Return MouserSearchResponse
- States / transitions: None (stateless)
- Hotspots: Keyword searches may return larger result sets (up to record_count limit)
- Evidence: Change brief lines 17-22 specify keyword endpoint structure

---

- Flow: Extract high-quality image from Mouser product page
- Steps:
  1. Receive product_url from LLM
  2. Download HTML using DownloadCacheService.get_cached_content(product_url)
  3. Parse HTML with BeautifulSoup
  4. Find ALL `<script type="application/ld+json">` tags using `soup.find_all('script', type='application/ld+json')`
  5. Iterate through each script tag:
     a. Deserialize JSON content (wrap in try/except for malformed JSON)
     b. Check if `@type` equals "ImageObject"
     c. If found, extract `contentUrl` field
     d. Break on first ImageObject match (Mouser pages typically have one)
  6. If ImageObject found with contentUrl: return GetMouserImageResponse with image_url
  7. If no ImageObject found: return error="ld+json ImageObject not found on page"
  8. On download/parse failure: return error field with specific message
- States / transitions: None (stateless)
- Hotspots: HTML parsing overhead, Mouser page structure changes breaking extractor
- Evidence: Change brief lines 24-28 specify ld+json parsing approach; `app/services/html_document_handler.py` shows HTML parsing precedent

---

- Flow: Extract specs from product page URL using LLM (with HTML preprocessing)
- Steps:
  1. Receive url from LLM
  2. Download HTML content using DownloadCacheService.get_cached_content(url)
  3. **Preprocess HTML to reduce token count**:
     a. Parse with BeautifulSoup
     b. Remove all `<script>` and `<style>` tags
     c. Extract text content, preserving structure (tables, lists, definition lists)
     d. Truncate to 50KB if still larger (first 50KB of preprocessed text)
  4. Build LLM prompt: "The following HTML is likely the HTML of an electronics component. Return all specs that are mentioned on the page as JSON."
  5. Call AIRunner with preprocessed HTML content and prompt
  6. Parse LLM response as dynamic JSON object
  7. Return ExtractSpecsResponse with specs object
  8. On failure (download, LLM error, JSON parse): return error field populated
- States / transitions: None (stateless)
- Hotspots: LLM call latency (~2-5s), token usage for large HTML pages (mitigated by preprocessing)
- Evidence: Change brief lines 30-34 specify LLM extraction; `app/services/duplicate_search_service.py:61-100` shows AIRunner usage pattern

---

- Flow: Conditional function registration
- Steps:
  1. In AIService.__init__, check config.MOUSER_SEARCH_API_KEY
  2. If present and non-empty: store search functions in instance variables
  3. In analyze_part(), build function_tools list conditionally including search functions
  4. Pass list to AIRunner.run()
  5. Image/spec extraction functions always included (no API key required)
- States / transitions: Configuration read at service initialization, immutable thereafter
- Hotspots: None
- Evidence: `app/services/ai_service.py:52-62` — Config-based initialization; line 126-132 shows function list construction

---

- Flow: Prompt template rendering with conditional Mouser section
- Steps:
  1. Load part_search.md template string
  2. Create Jinja2 Environment and parse template
  3. Build context dict with categories and mouser_api_available flag
  4. Set mouser_api_available = True if config.MOUSER_SEARCH_API_KEY non-empty
  5. Render template with context (Jinja2 conditionally includes Mouser instructions)
  6. Return rendered prompt string
- States / transitions: None (stateless template rendering)
- Hotspots: None
- Evidence: `app/services/ai_service.py:235-249` — Jinja2 template rendering pattern

## 6) Derived State & Invariants

- Derived value: Mouser API cache key (composite key for POST requests)
  - Source: URL + HTTP method + request body JSON → composite string `f"{url}#POST#{hashlib.sha256(body).hexdigest()}"`
  - Writes / cleanup: TempFileManager writes cache file using SHA256 of composite key as filename, automatic cleanup after 24 hours
  - Guards: MouserService constructs composite key before calling TempFileManager cache methods; ensures different bodies to same URL produce different cache entries
  - Invariant: Identical (URL, method, body) tuples produce identical cache keys; different bodies to same URL produce different keys (no collision)
  - Evidence: `app/utils/temp_file_manager.py:145-155` — `_url_to_path()` hashes any string passed as "url"; MouserService will pass composite key string

- Derived value: Filtered Mouser search results
  - Source: Unfiltered Mouser API JSON response
  - Writes / cleanup: Filtered response stored in cache (source-of-truth is Mouser API)
  - Guards: Filter logic must match exclusion list exactly (MouserPartNumber, ProductAttributes, PriceBreaks, ProductCompliance, ImagePath)
  - Invariant: Cached response never contains pricing/compliance data (privacy/staleness concern)
  - Evidence: Change brief lines 14-15 specify fields to exclude

- Derived value: Mouser product image URL
  - Source: Unfiltered HTML page content → ld+json script tag → ImageObject.contentUrl
  - Writes / cleanup: Image URL returned to LLM, no persistence (LLM may discard or use)
  - Guards: HTML parsing must gracefully handle missing tags, malformed JSON
  - Invariant: Extraction never throws exception on valid HTML (error returned in response)
  - Evidence: Change brief lines 24-28 specify parsing approach; line 59 specifies error handling

- Derived value: Extracted specs JSON from product page
  - Source: Filtered HTML content (unfiltered page download → LLM extraction → dynamic JSON)
  - Writes / cleanup: Specs JSON returned to main LLM, no persistence
  - Guards: LLM prompt must constrain output to valid JSON format
  - Invariant: Response always valid JSON or error field populated (never throws)
  - Evidence: Change brief lines 30-34 specify LLM extraction of "all specs as JSON"

- Derived value: Function tool registration list
  - Source: Unfiltered config.MOUSER_SEARCH_API_KEY presence check → boolean → function list
  - Writes / cleanup: Function list built once per AIService instance, no writes
  - Guards: API key validation is presence check only (no format validation or test call)
  - Invariant: Empty/missing API key never enables search functions (feature disabled)
  - Evidence: Change brief lines 12-13, 63-65 specify conditional availability

## 7) Consistency, Transactions & Concurrency

- Transaction scope: None (no database writes; all state is cached HTTP responses or transient LLM calls)
- Atomic requirements: None (function calls are idempotent read operations)
- Retry / idempotency: DownloadCacheService inherits request library retry behavior; function calls repeatable without side effects
- Ordering / concurrency controls: None (DownloadCacheService cache is file-based with TempFileManager handling concurrent access)
- Evidence: `app/services/download_cache_service.py:47-79` — Cache read/write operations; `app/utils/temp_file_manager.py` handles concurrent file access

## 8) Errors & Edge Cases

- Failure: Mouser API returns 401 Unauthorized (invalid API key)
- Surface: SearchMouserByPartNumber or SearchMouserByKeyword function
- Handling: Capture HTTP 401, return MouserSearchResponse with error field populated, LLM decides whether to retry or bail
- Guardrails: Config validation ensures API key is string (but doesn't test validity); error message logged for operator visibility
- Evidence: Change brief line 59 — "Return Mouser API errors verbatim in the function response"

---

- Failure: Mouser API returns 429 Too Many Requests (rate limit)
- Surface: Search functions during high request volume
- Handling: Return error in response, LLM receives rate limit message and can choose to skip Mouser search
- Guardrails: Cache mitigates rate limits for repeated queries; no client-side rate limiting implemented
- Evidence: Standard HTTP error handling in DownloadCacheService

---

- Failure: Mouser API returns empty results (part not found)
- Surface: Search functions when part number doesn't exist in Mouser catalog
- Handling: Return empty parts array, LLM interprets as "not available" and proceeds with other sources
- Guardrails: None needed (valid empty response)
- Evidence: Mouser API design returns empty array for no matches

---

- Failure: Product page HTML missing ld+json script tag
- Surface: GetMouserImageFromProductDetailUrl function
- Handling: Return GetMouserImageResponse with image_url=null and error="ld+json ImageObject not found"
- Guardrails: HTML parsing wrapped in try/except; error returned rather than exception raised
- Evidence: Change brief line 59 — error handling philosophy

---

- Failure: Product page HTML ld+json malformed or missing contentUrl
- Surface: GetMouserImageFromProductDetailUrl function
- Handling: JSON parse exception caught, return error="Failed to parse image metadata"
- Guardrails: Defensive parsing with multiple fallback checks
- Evidence: Standard JSON parsing error handling

---

- Failure: ExtractSpecsFromURL receives non-HTML content (PDF, image)
- Surface: ExtractPartSpecsFromURL function
- Handling: LLM receives content, attempts extraction, likely returns minimal/empty specs
- Guardrails: Content type check could warn but not block (LLM may still extract useful text from PDF)
- Evidence: Change brief line 30 says "any product page URL" (not restricted to HTML)

---

- Failure: ExtractSpecsFromURL LLM call fails or times out
- Surface: ExtractPartSpecsFromURL function during nested LLM call
- Handling: AIRunner exception caught, return ExtractSpecsResponse with error field populated
- Guardrails: Timeout controlled by AIRunner configuration; error doesn't propagate to main LLM
- Evidence: `app/utils/ai/ai_runner.py:236-258` — APIError handling with retry logic

---

- Failure: MOUSER_SEARCH_API_KEY empty but search functions called
- Surface: Should never happen (functions not registered if key missing)
- Handling: Defensive check in MouserService raises exception if API key empty
- Guardrails: Function registration logic prevents LLM from seeing unavailable functions
- Evidence: `app/services/ai_service.py:66-70` — Pattern of checking config before using API

---

- Failure: Network timeout downloading Mouser API response or product page
- Surface: All functions that use DownloadCacheService
- Handling: DownloadCacheService raises requests.RequestException, caught by function, returned as error
- Guardrails: 30-second download timeout configured in DownloadCacheService
- Evidence: `app/services/download_cache_service.py:33-34, 124-125` — Download timeout configuration

---

- Failure: Mouser API response JSON schema changes (new/renamed fields)
- Surface: MouserService parsing logic
- Handling: Pydantic validation may fail if required fields missing; return error in function response
- Guardrails: Pydantic schemas with optional fields reduce brittleness; error logged for investigation
- Evidence: Change brief acknowledges no versioning handled (assumption: schema stable)

## 9) Observability / Telemetry

- Signal: mouser_api_requests_total
- Type: Counter with labels (endpoint, status)
- Trigger: After each Mouser API call in MouserService, increment with endpoint="partnumber"|"keyword", status="success"|"error"|"cached"
- Labels / fields: endpoint, status
- Consumer: Prometheus dashboard showing Mouser API usage and cache hit rate
- Evidence: `app/services/metrics_service.py` — Existing metrics patterns for API calls

---

- Signal: mouser_api_duration_seconds
- Type: Histogram
- Trigger: On each Mouser API call completion, record duration
- Labels / fields: endpoint
- Consumer: Latency monitoring for Mouser API performance
- Evidence: `app/services/metrics_service.py` — record_operation_duration pattern

---

- Signal: mouser_image_extraction_total
- Type: Counter with labels (status)
- Trigger: After each GetMouserImageFromProductDetailUrl execution, increment with status="success"|"error"
- Labels / fields: status
- Consumer: Track image extraction success rate
- Evidence: Existing metrics patterns in services

---

- Signal: structured log entry for Mouser API calls
- Type: Structured log (logger.info)
- Trigger: Before and after each Mouser API call
- Labels / fields: endpoint, part_number/keyword, response_count, duration, cached
- Consumer: Application logs for debugging and audit trail
- Evidence: `app/services/duplicate_search_service.py:84-86` — Logging pattern for external API calls

---

- Signal: structured log entry for spec extraction
- Type: Structured log (logger.info)
- Trigger: Before calling nested LLM for spec extraction
- Labels / fields: url, token_count, duration
- Consumer: Track LLM usage for spec extraction feature
- Evidence: `app/utils/ai/ai_runner.py:138-140` — LLM call logging

---

- Signal: error log for Mouser API failures
- Type: Structured log (logger.error)
- Trigger: On HTTP errors, parsing failures, timeout exceptions
- Labels / fields: error_type, endpoint, status_code, url
- Consumer: Alert on repeated API failures
- Evidence: `app/services/download_cache_service.py:162-167` — Error logging pattern

## 10) Background Work & Shutdown

None. All Mouser integration work is synchronous request/response within LLM function calls. No background threads, scheduled jobs, or cleanup required.

Evidence: `app/utils/ai/duplicate_search.py` and `app/utils/ai/url_classification.py` — Existing function tools have no shutdown integration.

## 11) Security & Permissions

- Concern: API key exposure in logs or error messages
- Touchpoints: MouserService logging, error responses
- Mitigation: Never log full API key (redact to first 4 characters); API key only sent in HTTP header, not in response bodies
- Residual risk: API key visible in process environment variables (acceptable for single-user hobby app)
- Evidence: `app/config.py` — API keys stored in environment variables (standard practice)

---

- Concern: SSRF (Server-Side Request Forgery) via user-controlled URLs
- Touchpoints: GetMouserImageFromProductDetailUrl, ExtractPartSpecsFromURL
- Mitigation: Both functions restricted to HTTP/HTTPS URLs (no file:// or internal IPs); DownloadCacheService validates URL scheme
- Residual risk: User could target internal services on HTTP (acceptable for single-user app; no sensitive internal services expected)
- Evidence: `app/services/download_cache_service.py:96-100` — URL validation checks for http/https only

---

- Concern: HTML/JavaScript injection via Mouser API responses
- Touchpoints: Mouser API JSON fields displayed in UI
- Mitigation: Backend returns raw JSON; frontend responsible for escaping (not in scope for this backend change)
- Residual risk: XSS if frontend doesn't escape (frontend team's responsibility)
- Evidence: Backend API design (no backend-rendered HTML)

---

- Concern: Excessive token usage from large HTML pages in spec extraction
- Touchpoints: ExtractPartSpecsFromURL function
- Mitigation: DownloadCacheService enforces 100MB max file size; typical HTML pages under 1MB; OpenAI token limits will truncate
- Residual risk: User could target very large pages and incur high token costs (acceptable for hobby app; user controls their own API key)
- Evidence: `app/services/download_cache_service.py:72-73` — MAX_FILE_SIZE config

## 12) UX / UI Impact

None. This is a backend-only feature that adds function tools for the LLM. No API endpoint changes, no UI modifications.

The LLM's responses may include Mouser-sourced data (seller="Mouser", seller_url=ProductDetailUrl), but the frontend already renders seller information from PartAnalysisDetails schema.

Evidence: Change brief scope limited to backend integration; `app/schemas/ai_part_analysis.py` shows frontend consumes PartAnalysisDetailsSchema.

## 13) Deterministic Test Plan

- Surface: MouserService.search_by_part_number
- Scenarios:
  - Given valid API key and part number, When Mouser API returns results, Then return filtered MouserSearchResponse with ManufacturerPartNumber/Description/etc
  - Given valid API key and part number, When Mouser API returns 404, Then return empty parts array
  - Given valid API key and part number, When Mouser API returns 401, Then return error in response
  - Given cached response exists, When same part number searched, Then return cached response without API call
- Fixtures / hooks: Mock requests.post to return sample Mouser JSON; mock DownloadCacheService.get_cached_content
- Gaps: None
- Evidence: `tests/test_duplicate_search_service.py:1-100` — Pattern for testing services with mocked API calls

---

- Surface: MouserService.search_by_keyword
- Scenarios:
  - Given valid keyword, When Mouser returns 5 results, Then return filtered response with 5 parts
  - Given keyword with record_count=20, When Mouser returns partial results, Then return available parts
  - Given cached keyword search, When repeated, Then return cached response
- Fixtures / hooks: Mock Mouser keyword API responses
- Gaps: None
- Evidence: Same test patterns as part number search

---

- Surface: MouserService cache key derivation (POST request collision prevention)
- Scenarios:
  - Given two different part numbers to same partnumber endpoint, When both cached, Then produce different cache keys (no collision)
  - Given same part number searched twice, When second search called, Then cache hit (same key)
  - Given part number "ABC123" via partnumber endpoint and keyword "ABC123" via keyword endpoint, When both cached, Then produce different cache keys (different URLs)
- Fixtures / hooks: Mock TempFileManager to capture cache keys; verify composite key format `{url}#POST#{body_hash}`
- Gaps: None
- Evidence: `app/utils/temp_file_manager.py:145-155` — `_url_to_path()` hashes any string; MouserService constructs composite key

---

- Surface: SearchMouserByPartNumberFunction.execute
- Scenarios:
  - Given MouserSearchByPartNumberRequest, When service returns results, Then return MouserSearchResponse
  - Given service raises exception, When execute called, Then return error in response (graceful degradation)
- Fixtures / hooks: Mock MouserService instance; ProgressHandle stub
- Gaps: None
- Evidence: `app/utils/ai/duplicate_search.py:47-71` — Function execute pattern with error handling

---

- Surface: GetMouserImageFromProductDetailUrlFunction.execute
- Scenarios:
  - Given Mouser product URL with valid ld+json, When HTML contains ImageObject, Then return contentUrl
  - Given HTML with multiple ld+json scripts (Product, Offer, ImageObject), When parsed, Then correctly find and return ImageObject.contentUrl
  - Given HTML with ld+json but no ImageObject type, When parse attempted, Then return error="ld+json ImageObject not found"
  - Given HTML with missing ld+json tag, When parse attempted, Then return error="ld+json ImageObject not found"
  - Given malformed JSON in ld+json tag, When parse attempted, Then skip and check next script (or return error if no valid ImageObject)
  - Given ImageObject without contentUrl field, When parsed, Then return error="ImageObject missing contentUrl"
  - Given cached HTML, When same URL requested, Then return cached result
- Fixtures / hooks: Mock HTML responses with various ld+json configurations; mock DownloadCacheService
- Gaps: None
- Evidence: `tests/test_ai_service.py:75-78` — Pattern for mocking document service operations

---

- Surface: ExtractPartSpecsFromURLFunction.execute
- Scenarios:
  - Given product page URL, When AIRunner extracts specs, Then return dynamic JSON specs object
  - Given AIRunner fails, When extraction attempted, Then return error in response
  - Given cached HTML, When same URL requested, Then use cached content (AIRunner still called)
  - Given large HTML page with scripts/styles, When preprocessed, Then scripts and styles removed from LLM input
  - Given HTML larger than 50KB after preprocessing, When processed, Then truncated to 50KB before LLM call
  - Given LLM returns invalid JSON, When parsing fails, Then return error="Failed to parse JSON specs"
- Fixtures / hooks: Mock AIRunner.run to return sample specs JSON; mock DownloadCacheService; provide large HTML fixture
- Gaps: None
- Evidence: `tests/test_duplicate_search_service.py:116-142` — Pattern for testing nested AIRunner calls

---

- Surface: AIService.analyze_part with Mouser functions registered
- Scenarios:
  - Given MOUSER_SEARCH_API_KEY configured, When AIService initialized, Then search functions registered
  - Given empty MOUSER_SEARCH_API_KEY, When AIService initialized, Then search functions not registered
  - Given search functions registered, When AIRunner.run called, Then functions available to LLM
  - Given image/spec functions, When AIService initialized, Then always registered (no API key required)
- Fixtures / hooks: Mock config with/without API key; verify function_tools list passed to AIRunner
- Gaps: None
- Evidence: `tests/test_ai_service.py:86-108` — Pattern for testing AIService initialization and function registration

---

- Surface: part_search.md prompt rendering
- Scenarios:
  - Given MOUSER_SEARCH_API_KEY present, When prompt rendered, Then includes Mouser search instructions
  - Given MOUSER_SEARCH_API_KEY empty, When prompt rendered, Then excludes Mouser search instructions
  - Given any config, When prompt rendered, Then always includes image/spec extraction instructions
- Fixtures / hooks: Mock config; inspect rendered prompt string for presence of Mouser section
- Gaps: None
- Evidence: `app/services/ai_service.py:235-249` — Prompt rendering test pattern

---

- Surface: PartAnalysisDetails schema with seller fields
- Scenarios:
  - Given LLM response includes seller/seller_url, When parsed, Then fields populate correctly
  - Given LLM response omits seller fields, When parsed, Then fields default to None
- Fixtures / hooks: Sample PartAnalysisSuggestion JSON with/without seller fields
- Gaps: None
- Evidence: `tests/test_ai_part_analysis_schema.py` — Pattern for testing schema validation

---

- Surface: Mouser response field filtering
- Scenarios:
  - Given Mouser API returns full response with pricing, When parsed, Then PriceBreaks/ProductCompliance excluded
  - Given Mouser response with all fields, When filtered, Then only allowed fields present
- Fixtures / hooks: Sample Mouser JSON with all fields; verify filtered output
- Gaps: None
- Evidence: Standard Pydantic schema validation testing

## 14) Implementation Slices

Not needed (feature is cohesive and small enough to implement atomically).

## 15) Risks & Open Questions

- Risk: Mouser API schema changes break integration
- Impact: Mouser search functions return errors, LLM falls back to web search (degraded but functional)
- Mitigation: Log errors prominently; add integration tests with real API (manual, not in CI)

---

- Risk: HTML structure of Mouser product pages changes, breaking image extraction
- Impact: Image extraction returns errors, LLM doesn't get high-quality images (minor degradation)
- Mitigation: Graceful error handling; LLM can still use web search to find images

---

- Risk: Spec extraction LLM calls add significant latency and cost
- Impact: Part analysis takes longer and consumes more tokens when extracting specs
- Mitigation: Caching mitigates repeated calls; LLM only calls when needed (user controls usage)

---

- Risk: Conditional prompt rendering introduces complexity in testing
- Impact: Hard to verify Mouser instructions only appear when API key present
- Mitigation: Explicit test cases for both configurations; prompt rendering is deterministic

---

- Risk: Large HTML pages exceed LLM token limits in spec extraction
- Impact: LLM truncates content or fails to extract specs from very long pages
- Mitigation: HTML preprocessing removes scripts/styles and truncates to 50KB before LLM call; extraction quality may degrade on extremely content-heavy pages but won't fail unexpectedly

---

- Question: Should MouserService validate API key format (length, prefix)?
- Why it matters: Invalid key will fail on first API call; early validation could improve error messages
- Owner / follow-up: Accept current design (presence check only); API call failure is clear enough

---

- Question: Should spec extraction use a smaller/faster LLM model?
- Why it matters: Could reduce latency and cost for nested LLM call
- Owner / follow-up: Use same model as main analysis for consistency; optimize later if needed

---

- Question: Should image extraction function validate URL is actually a Mouser domain?
- Why it matters: Function name implies Mouser-specific, but implementation works on any page
- Owner / follow-up: Keep generic implementation; rename to GetImageFromProductDetailUrl (remove "Mouser" prefix) for clarity

## 16) Confidence

Confidence: High — All patterns well-established in codebase (AIFunction, DownloadCacheService, Jinja2 templates, dependency injection). No novel algorithms or complex state management. Risks are external dependencies (Mouser API, HTML structure) with graceful error handling.
