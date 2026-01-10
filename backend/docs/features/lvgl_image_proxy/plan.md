# LVGL Image Proxy — Technical Plan

## 0) Research Log & Findings

**Areas Researched:**

1. **Existing API patterns** — Reviewed `app/api/configs.py` to understand the Flask blueprint structure, SpectTree validation patterns, error handling decorators (`@handle_api_errors`), dependency injection (`@inject`), and metrics integration patterns.

2. **Service layer conventions** — Examined `app/services/config_service.py` to understand service patterns. Found that services without database access use simple classes (not inheriting `BaseService`), and that the `ConfigService` is a Factory provider in the DI container for thread safety.

3. **Error handling architecture** — Analyzed `app/utils/error_handling.py` and `app/exceptions.py` to understand the exception hierarchy. Found existing exceptions: `RecordNotFoundException` (404), `InvalidOperationException` (400), `ValidationException` (400), and generic `Exception` (500). No built-in support for HTTP 502 errors exists in current handlers. **Important:** `InvalidOperationException` maps to 400, so a new exception type is needed for processing failures that should return 500.

4. **Metrics infrastructure** — Reviewed `app/services/metrics_service.py` to understand Prometheus metrics patterns (Counter, Gauge, Histogram). Service uses on-demand metrics updates rather than background polling.

5. **Dependency injection container** — Examined `app/services/container.py` and `app/__init__.py` to understand how services are registered and wired. Services without database dependencies use simple Factory providers, and new API modules must be added to the `wire_modules` list in `app/__init__.py`.

6. **Testing infrastructure** — Reviewed `tests/conftest.py` to understand test fixtures. Found Flask app fixture, test client fixture, container fixture, and Prometheus registry cleanup (autouse). Service tests get service instances from the container.

7. **LVGLImage.py upstream** — The change brief specifies keeping `LVGLImage.py` as a verbatim copy from https://github.com/lvgl/lvgl/blob/master/scripts/LVGLImage.py. This is an external Python module that converts images to LVGL binary format. We will import and use its classes directly rather than invoking it as a subprocess.

**Key Findings:**

- The project has no database (filesystem-based), so services don't inherit `BaseService`.
- All API endpoints use blueprints, SpectTree validation, `@handle_api_errors`, and dependency injection.
- Error handling needs extension: current code maps exceptions to 400/404/500, but this feature needs 502 for external fetch failures and a new exception type for processing failures (500) since `InvalidOperationException` maps to 400.
- Metrics integration is standard: Counter for operations (with status labels), Histogram for durations.
- New dependencies required: `Pillow` (image resizing), `httpx` (async HTTP client), `pypng` and `lz4` (LVGLImage.py dependencies).
- The service will be stateless and use Factory provider for thread safety during concurrent requests.

**Conflicts Resolved:**

- **502 vs 500 for external fetch failures**: The change brief explicitly requires 502 for external URL fetch failures to distinguish them from internal processing errors (500). This requires extending the error handler in `app/utils/error_handling.py` to recognize two new exception types: `ExternalServiceException` (502) and `ProcessingException` (500). Note: `InvalidOperationException` cannot be used for processing failures as it maps to 400.
- **Time measurement**: Per CLAUDE.md, use `time.perf_counter()` for duration measurements, not `time.time()`.
- **Header forwarding**: The `headers` query parameter is a comma-separated list of header names. Each name is read from the incoming request and forwarded to the external URL. If a requested header is missing, return 400 per the change brief.

---

## 1) Intent & Scope

**User intent**

Provide a proxying endpoint that fetches images from external URLs (e.g., Home Assistant entity cameras), optionally resizes them to fit ESP32 display constraints, and converts them to LVGL binary format (ARGB8888) for direct consumption by ESP32 devices running LVGL. The endpoint supports forwarding authentication headers (e.g., bearer tokens) from the incoming request to the external URL, enabling secure access to protected resources.

**Prompt quotes**

"GET /api/images/lvgl with query parameters: url (required), headers (comma-separated list of header names to forward), width/height (optional resize dimensions)"

"Header forwarding: For each header name in the headers parameter, read the corresponding header from the incoming request and forward it to the external URL"

"Resize (if width/height specified): Resize the image while maintaining aspect ratio. Only downsize - if the image is smaller than the target dimensions, don't upscale."

"Convert to LVGL format: Convert the image to LVGL binary format (ARGB8888) using the upstream LVGLImage.py script from the LVGL project."

"The LVGLImage.py file must be kept as a verbatim copy from https://github.com/lvgl/lvgl/blob/master/scripts/LVGLImage.py"

"Return 400 if required url parameter is missing; Return 400 if a header specified in headers is not present in the request; Return 502 if the external URL fetch fails; Return 500 if image processing or conversion fails"

"Set Cache-Control: no-store to prevent caching"

**In scope**

- New API endpoint `GET /api/images/lvgl` with query parameter validation (url required, headers/width/height optional)
- Service layer for image proxy operations (fetch, resize, LVGL conversion)
- HTTP client integration (fetch external images with forwarded headers)
- Image resizing with aspect ratio preservation (downscale only, using Pillow)
- LVGL binary format conversion using upstream `LVGLImage.py` classes
- Custom exception types: `ExternalServiceException` for HTTP 502 (external fetch failures) and `ProcessingException` for HTTP 500 (image processing failures)
- Response headers: `Cache-Control: no-store` and appropriate binary content type
- Prometheus metrics for image proxy operations (duration, status, error types)
- Comprehensive test coverage (API tests, service tests, error scenarios)
- Poetry dependency additions: `Pillow`, `httpx`, `pypng`, `lz4`

**Out of scope**

- Caching of fetched or converted images (explicitly excluded per change brief)
- Rate limiting (not mentioned in brief)
- Image format detection/validation beyond Pillow's built-in support (change brief notes this is out of scope)
- Support for LVGL color formats other than ARGB8888 (brief notes "can be added later")
- Upscaling images (only downscaling allowed)
- Authentication/authorization on the proxy endpoint itself (project has no auth per product brief)
- Retry logic for external URL fetches (fail fast per CLAUDE.md error handling philosophy)

**Assumptions / constraints**

- External URLs return image data in formats Pillow can decode (JPEG, PNG, BMP, GIF, etc.)
- The upstream `LVGLImage.py` script is compatible with Python 3.11+ and does not have breaking API changes
- Header names in the `headers` parameter are case-insensitive (Flask headers are case-insensitive)
- Timeout for external HTTP requests is reasonable (e.g., 30 seconds) to prevent hanging requests
- Image processing memory usage is acceptable for ESP32-scale images (typically ≤320x240 pixels)
- The `LVGLImage.py` module can be imported directly and does not require subprocess execution

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Add API endpoint `GET /api/images/lvgl` that converts images to LVGL binary format
- [ ] Forward specified headers from incoming request to external URL for authentication
- [ ] Support optional image resizing with aspect ratio preservation (downscale only)
- [ ] Keep `LVGLImage.py` as a verbatim copy from https://github.com/lvgl/lvgl/blob/master/scripts/LVGLImage.py
- [ ] Place `LVGLImage.py` in `app/utils/lvgl/` with filename unchanged
- [ ] Add README.md in the lvgl folder documenting the upstream source
- [ ] Use LVGLImage classes directly via import (no subprocess calls)
- [ ] Return appropriate HTTP error codes (400, 502, 500) for different failure modes
- [ ] Set Cache-Control: no-store response header

---

## 2) Affected Areas & File Map

- Area: `app/utils/lvgl/LVGLImage.py` (new file)
- Why: Upstream LVGL image conversion script, copied verbatim from https://github.com/lvgl/lvgl/blob/master/scripts/LVGLImage.py
- Evidence: Change brief:34-37 — "The LVGLImage.py file must be kept as a verbatim copy from https://github.com/lvgl/lvgl/blob/master/scripts/LVGLImage.py; Place it in app/utils/lvgl/LVGLImage.py"

- Area: `app/utils/lvgl/README.md` (new file)
- Why: Documents the upstream source of LVGLImage.py for maintainability
- Evidence: Change brief:36 — "Include a README.md in that folder documenting the source"

- Area: `app/utils/lvgl/__init__.py` (new file)
- Why: Makes the lvgl directory a Python package and re-exports `LVGLImage` and `ColorFormat` classes for cleaner imports (`from app.utils.lvgl import LVGLImage, ColorFormat`)
- Evidence: Standard Python packaging convention for directory modules; re-export pattern for cleaner API

- Area: `app/services/image_proxy_service.py` (new file)
- Why: Service layer for business logic (fetch external image, resize, convert to LVGL format)
- Evidence: CLAUDE.md:59-69 — "Services contain all business logic... Return SQLAlchemy model instances, not dicts. Raise typed exceptions. No HTTP-specific code."

- Area: `app/schemas/image_proxy.py` (new file)
- Why: Pydantic schemas for request query parameters validation
- Evidence: CLAUDE.md:95-109 — "Pydantic schemas for request/response validation. Use Field() with descriptions and examples."

- Area: `app/api/images.py` (new file)
- Why: API endpoint for GET /api/images/lvgl with query parameter validation and error handling
- Evidence: CLAUDE.md:35-57 — "API endpoints handle HTTP concerns only. Use Flask blueprints with URL prefixes. Validate requests with Pydantic schemas via @api.validate."

- Area: `app/exceptions.py` (modify)
- Why: Add two new exception types: `ExternalServiceException` (502 Bad Gateway for external fetch failures) and `ProcessingException` (500 Internal Server Error for image processing failures). Note: `InvalidOperationException` maps to 400 and cannot be used for 500 errors.
- Evidence: Change brief:41 — "Return 502 if the external URL fetch fails"; change brief:44 — "Return 500 if image processing or conversion fails"; app/exceptions.py:1-40 — Current exception hierarchy includes 400/404 but no 502/500-specific mapping; app/utils/error_handling.py:87-94 — `InvalidOperationException` maps to 400

- Area: `app/utils/error_handling.py` (modify)
- Why: Extend `@handle_api_errors` decorator to catch `ExternalServiceException` (502) and `ProcessingException` (500) with appropriate status codes
- Evidence: app/utils/error_handling.py:46-120 — Current handler maps RecordNotFoundException→404, InvalidOperationException→400, generic Exception→500; needs explicit 502 and 500 cases for new exception types

- Area: `app/services/container.py` (modify)
- Why: Register `ImageProxyService` as a Factory provider in the DI container with `MetricsService` dependency injection. Pattern: `image_proxy_service = providers.Factory(ImageProxyService, metrics_service=metrics_service)`
- Evidence: app/services/container.py:10-23 — "Container for service dependency injection"; CLAUDE.md:310-326 — Service container example; CLAUDE.md:321-325 — Service dependency injection pattern

- Area: `app/services/metrics_service.py` (modify)
- Why: Add Prometheus metrics for image proxy operations (counter, histogram for duration)
- Evidence: app/services/metrics_service.py:1-85 — Existing metrics service with Counter, Gauge, Histogram patterns; CLAUDE.md:264-295 — "When implementing features that need operational visibility: Add metrics to MetricsService"

- Area: `app/__init__.py` (modify)
- Why: Wire the new `app.api.images` module with the DI container for dependency injection
- Evidence: app/__init__.py:36-42 — "Wire container with API modules" shows wire_modules list where new modules must be registered

- Area: `app/api/__init__.py` (modify)
- Why: Register the images blueprint under the main API blueprint at /api/images
- Evidence: app/api/__init__.py — Standard pattern for registering sub-blueprints (must inspect file to confirm pattern)

- Area: `tests/services/test_image_proxy_service.py` (new file)
- Why: Service layer tests for fetch, resize, and LVGL conversion logic with error scenarios
- Evidence: CLAUDE.md:136-162 — "Required test coverage for services: All public methods, Success paths with various input combinations, Error conditions and exception handling, Edge cases"

- Area: `tests/api/test_images.py` (new file)
- Why: API tests for GET /api/images/lvgl endpoint validation, error codes, response headers
- Evidence: CLAUDE.md:164-170 — "Required test coverage for APIs: All HTTP endpoints and methods, Request validation (invalid payloads, missing fields), Response format validation, HTTP status codes, Error responses"

- Area: `pyproject.toml` (modify)
- Why: Add new dependencies (Pillow, httpx, pypng, lz4) to Poetry configuration
- Evidence: Change brief:51-57 — "New Python packages required: pypng, lz4, Pillow, httpx or requests"

---

## 3) Data Model / Contracts

- Entity / contract: Query parameters for `GET /api/images/lvgl`
- Shape: `{ "url": "string (required)", "headers": "string (optional, comma-separated)", "width": "int (optional)", "height": "int (optional)" }`
- Refactor strategy: No backwards compatibility needed (new endpoint). Query parameters are validated by Pydantic schema with Field() constraints (url must be valid URL, width/height must be positive integers if provided).
- Evidence: Change brief:11-18 — Table of query parameters; CLAUDE.md:27-31 — "Make breaking changes freely; no backwards compatibility needed"

- Entity / contract: Response body for `GET /api/images/lvgl`
- Shape: Binary data (LVGL image format, application/octet-stream or application/x-lvgl-image content type) with headers `Cache-Control: no-store`
- Refactor strategy: No backwards compatibility needed (new endpoint). Response is raw binary data, not JSON, so no schema validation on response side.
- Evidence: Change brief:30 — "Return the LVGL binary data with appropriate content type"; change brief:47-49 — "Set Cache-Control: no-store"

- Entity / contract: Error responses
- Shape: Standard error response schema from existing `app/schemas/error.py` — `{ "error": "string", "details": { "message": "string" }, "code": "string (optional)", "correlationId": "string (optional)" }`
- Refactor strategy: Reuse existing error response schema. Add new exception type `ExternalServiceException` for 502 errors to map cleanly via `@handle_api_errors`.
- Evidence: app/utils/error_handling.py:23-43 — `_build_error_response` function shows standard error response structure

- Entity / contract: Service class and method signatures
- Shape: `class ImageProxyService` with constructor `__init__(self, metrics_service: MetricsService)` and method `fetch_and_convert_image(url: str, headers: dict[str, str], width: int | None, height: int | None) -> bytes`
- Refactor strategy: Service returns raw bytes (LVGL binary data). No database models involved (stateless service). Service receives `MetricsService` via constructor injection to record operation metrics internally.
- Evidence: CLAUDE.md:59-80 — "Services contain all business logic... Return SQLAlchemy model instances, not dicts" (note: no models in this feature, service returns bytes); CLAUDE.md:328-337 — Service dependency injection pattern

---

## 4) API / Integration Surface

- Surface: `GET /api/images/lvgl`
- Inputs: Query parameters: `url` (string, required, valid HTTP/HTTPS URL), `headers` (string, optional, comma-separated list of header names to forward from request to external URL), `width` (int, optional, positive, target width for resizing), `height` (int, optional, positive, target height for resizing). HTTP headers from incoming request (forwarded based on `headers` query param).
- Outputs: Success (200): Binary response body (LVGL image data), `Content-Type: application/octet-stream`, `Cache-Control: no-store`. Error responses: 400 (missing url, invalid parameters, missing requested header), 502 (external URL fetch failed), 500 (image processing or LVGL conversion failed).
- Errors: 400 Bad Request — `url` parameter missing, `url` is not a valid URL, `width`/`height` are not positive integers, a header name in `headers` param is not present in the incoming request. 502 Bad Gateway — External URL fetch failed (timeout, DNS failure, HTTP error from external server, network unreachable). 500 Internal Server Error — Image decoding failed (Pillow cannot decode), resizing failed, LVGL conversion failed (LVGLImage.py raised exception).
- Evidence: Change brief:11-18 (query parameters), change brief:39-44 (error codes), change brief:47-49 (response headers); app/api/configs.py:26-66 (existing endpoint pattern with @api.validate, @handle_api_errors, @inject)

---

## 5) Algorithms & State Machines

- Flow: Image fetch, resize, and LVGL conversion
- Steps:
  1. API layer validates query parameters (url required, width/height positive integers if provided, headers optional string).
  2. API layer parses `headers` query parameter (comma-separated) into list of header names.
  3. API layer reads each header name from the incoming Flask request; if any header is missing, raise `InvalidOperationException` with 400.
  4. API layer calls `image_proxy_service.fetch_and_convert_image(url, headers_dict, width, height)`.
  5. Service uses `httpx.Client` to fetch external URL with forwarded headers and timeout (30 seconds). On network/HTTP error, raise `ExternalServiceException` with 502.
  6. Service decodes fetched bytes using `Pillow.Image.open(BytesIO(response.content))`. On decode error, raise `ProcessingException` with 500.
  7. If width/height provided, service resizes image: calculate aspect-preserving dimensions (fit within bounds, downscale only), use `Image.resize()` with `LANCZOS` filter. If only one dimension is provided, preserve aspect ratio using that dimension as constraint.
  8. Service converts PIL Image to LVGL binary format: import `LVGLImage` and `ColorFormat` from `app.utils.lvgl`, create `LVGLImage` instance from PIL Image, call `LVGLImage.to_bin()` with `ColorFormat.ARGB8888`. On conversion error, raise `ProcessingException` with 500.
  9. Service returns binary bytes to API layer.
  10. API layer sets `Cache-Control: no-store` header and returns binary response with 200.
- States / transitions: No state machine. Stateless request/response flow.
- Hotspots: External URL fetch (network latency, timeout handling), image decoding (memory allocation for large images), resizing (CPU-intensive for large images), LVGL conversion (CPU/memory for format transformation). Expected volumes: Low (homelab scale, <200 devices, infrequent image updates).
- Evidence: Change brief:20-30 (processing pipeline), CLAUDE.md:195-210 (time.perf_counter for duration measurements)

---

## 6) Derived State & Invariants

This feature is stateless with no persistent storage or cross-context derived state. Each request is independent and produces a one-time response (binary image data). However, there are ephemeral derived values within the request lifecycle:

- Derived value: Resized image dimensions
  - Source: Input `width` and `height` query parameters, combined with the fetched image's intrinsic dimensions (`image.width`, `image.height` from Pillow). Unfiltered inputs (query params validated by Pydantic).
  - Writes / cleanup: No persistent writes. Resized image exists only in memory during the request and is discarded after LVGL conversion.
  - Guards: Aspect ratio calculation ensures dimensions are positive integers. Downscale-only constraint: if resized dimensions would upscale, use original dimensions instead.
  - Invariant: Resized dimensions must maintain aspect ratio within the requested bounding box. Resized dimensions must not exceed original dimensions (no upscaling).
  - Evidence: Change brief:26 — "Resize the image while maintaining aspect ratio. Only downsize"

- Derived value: Forwarded HTTP headers dictionary
  - Source: Filtered from incoming Flask request headers based on the `headers` query parameter (comma-separated list). Filtered inputs (only specified header names are included).
  - Writes / cleanup: No persistent writes. Dictionary is passed to `httpx.Client` for the external request and then discarded.
  - Guards: Validation that each requested header name exists in the incoming request. Raise 400 if missing.
  - Invariant: All header names in the `headers` query param must be present in the incoming request. Forwarded headers dictionary must only contain headers explicitly requested by the client.
  - Evidence: Change brief:22 — "For each header name in the headers parameter, read the corresponding header from the incoming request and forward it to the external URL"; change brief:42 — "Return 400 if a header specified in headers is not present in the request"

- Derived value: LVGL binary output
  - Source: Unfiltered PIL Image object (after decode and optional resize), converted using `LVGLImage.to_bin()` with `ColorFormat.ARGB8888`.
  - Writes / cleanup: No persistent writes. Binary data is returned directly in the HTTP response body and then discarded.
  - Guards: LVGLImage conversion may fail if the image is malformed or unsupported. Catch exceptions and raise `InvalidOperationException` with 500.
  - Invariant: Binary output must be valid LVGL format (ARGB8888). Conversion must complete or fail explicitly (no partial data returned).
  - Evidence: Change brief:28 — "Convert to LVGL format using LVGLImage.py"; change brief:44 — "Return 500 if image processing or conversion fails"

---

## 7) Consistency, Transactions & Concurrency

- Transaction scope: No database transactions. Filesystem read-only (reading upstream LVGLImage.py module). No persistent state changes. Each request is atomic at the HTTP level (request/response cycle).
- Atomic requirements: None. No multi-step persistent operations. External URL fetch, image processing, and response generation are a single read-only pipeline.
- Retry / idempotency: No retry logic implemented (fail fast per CLAUDE.md error handling philosophy). Requests are idempotent by nature (same inputs produce same outputs), but no client-side idempotency keys needed (no persistent side effects).
- Ordering / concurrency controls: Service is stateless and thread-safe. Factory provider in DI container creates a new service instance per request. No shared mutable state. External HTTP client (`httpx.Client`) is created per request to avoid connection pooling issues across threads.
- Evidence: CLAUDE.md:212-218 — "Fail fast and fail often. Use custom exceptions. Let @handle_api_errors convert exceptions to HTTP responses. Avoid defensive try/catch blocks."; app/services/container.py:19-23 — ConfigService is Factory for thread safety (same pattern applies here)

---

## 8) Errors & Edge Cases

- Failure: `url` query parameter missing
- Surface: API endpoint `GET /api/images/lvgl`
- Handling: Pydantic validation fails before handler is invoked. SpectTree returns 422 or `@api.validate` raises ValidationError, caught by `@handle_api_errors` → 400 response with validation error details.
- Guardrails: Pydantic schema marks `url` as required field. SpectTree enforces validation at API layer.
- Evidence: Change brief:40 — "Return 400 if required url parameter is missing"; app/api/configs.py:69-76 (SpectTree validation pattern)

- Failure: `url` query parameter is not a valid URL
- Surface: API endpoint `GET /api/images/lvgl`
- Handling: Pydantic schema validates URL format using `HttpUrl` or custom validator. Validation failure → 400 response.
- Guardrails: Pydantic `HttpUrl` type or regex validator for URL format.
- Evidence: Change brief:40 (implicit requirement: url must be valid); Pydantic docs: `HttpUrl` validator

- Failure: `width` or `height` query parameter is not a positive integer
- Surface: API endpoint `GET /api/images/lvgl`
- Handling: Pydantic schema validates `width` and `height` as `int` with `gt=0` constraint. Validation failure → 400 response.
- Guardrails: Pydantic `Field(gt=0)` constraint for positive integers.
- Evidence: Change brief:17-18 (width/height are integers); resize logic requires positive values

- Failure: A header name in `headers` query param is not present in the incoming request
- Surface: API endpoint `GET /api/images/lvgl` (header forwarding logic)
- Handling: API layer checks each header name in the incoming request. If missing, raise `InvalidOperationException("forward headers", "header 'X-Auth-Token' not present in request")` → 400 response.
- Guardrails: Explicit header presence check before calling service.
- Evidence: Change brief:42 — "Return 400 if a header specified in headers is not present in the request"

- Failure: External URL fetch fails (network timeout, DNS failure, HTTP 4xx/5xx from external server)
- Surface: Service layer `fetch_and_convert_image()` method
- Handling: `httpx.Client.get()` raises exception (RequestError, HTTPStatusError, Timeout). Catch and raise `ExternalServiceException("fetch image", "external URL returned 404")` → 502 response via `@handle_api_errors`.
- Guardrails: Timeout set on httpx client (30 seconds). No retry logic (fail fast). Log external error details for debugging.
- Evidence: Change brief:41 — "Return 502 if the external URL fetch fails"

- Failure: External URL returns non-image content (e.g., HTML error page)
- Surface: Service layer `fetch_and_convert_image()` method
- Handling: `Pillow.Image.open()` raises exception (UnidentifiedImageError). Catch and raise `ProcessingException("decode image", "response is not a valid image format")` → 500 response via `@handle_api_errors`.
- Guardrails: No content-type validation (Pillow determines format automatically). Fail on decode error.
- Evidence: Change brief:44 — "Return 500 if image processing or conversion fails"

- Failure: Image is too large or corrupt, Pillow cannot decode
- Surface: Service layer `fetch_and_convert_image()` method
- Handling: `Pillow.Image.open()` raises exception (OSError, DecompressionBombError). Catch and raise `ProcessingException("decode image", "image is corrupt or too large")` → 500 response via `@handle_api_errors`.
- Guardrails: Pillow's built-in decompression bomb protection (default limit 89478485 pixels). No additional size limits enforced (homelab use case, images are expected to be small).
- Evidence: Change brief:44 — "Return 500 if image processing or conversion fails"

- Failure: Image resize fails (e.g., invalid dimensions after aspect ratio calculation)
- Surface: Service layer `fetch_and_convert_image()` method
- Handling: `Image.resize()` raises exception. Catch and raise `ProcessingException("resize image", "resize operation failed")` → 500 response via `@handle_api_errors`.
- Guardrails: Aspect ratio calculation ensures positive integer dimensions. Downscale-only constraint prevents upscaling.
- Evidence: Change brief:44 — "Return 500 if image processing or conversion fails"

- Failure: LVGL conversion fails (LVGLImage.py raises exception)
- Surface: Service layer `fetch_and_convert_image()` method
- Handling: `LVGLImage.to_bin()` raises exception. Catch and raise `ProcessingException("convert to LVGL format", "LVGL conversion failed")` → 500 response via `@handle_api_errors`.
- Guardrails: LVGLImage.py is upstream code (assumed stable). Log exception details for debugging.
- Evidence: Change brief:44 — "Return 500 if image processing or conversion fails"

- Failure: `headers` query parameter contains invalid syntax (e.g., not comma-separated)
- Surface: API endpoint `GET /api/images/lvgl`
- Handling: API layer splits `headers` param by comma. Empty strings or whitespace-only names are filtered out. No validation error unless a resulting header name is genuinely missing from the request.
- Guardrails: Lenient parsing (strip whitespace, ignore empty parts). Missing header check is the true validation.
- Evidence: Change brief:22 (comma-separated list); error handling focuses on missing headers, not syntax

---

## 9) Observability / Telemetry

- Signal: `iot_image_proxy_operations_total`
- Type: Counter
- Trigger: At the end of each `GET /api/images/lvgl` request, increment counter with labels `status` (success/error) and `error_type` (missing_param, invalid_url, external_fetch_failed, decode_failed, resize_failed, lvgl_conversion_failed, or none for success).
- Labels / fields: `status` (success, error), `error_type` (specific failure reason or none)
- Consumer: Prometheus dashboard tracking image proxy usage, error rates, error types
- Evidence: app/services/metrics_service.py:28-43 (Counter pattern with labels); CLAUDE.md:264-295 (metrics integration requirements)

- Signal: `iot_image_proxy_operation_duration_seconds`
- Type: Histogram
- Trigger: At the end of each `GET /api/images/lvgl` request, observe duration (elapsed time from start to response).
- Labels / fields: No labels (or optionally `operation=fetch_and_convert`)
- Consumer: Prometheus dashboard tracking image proxy latency (p50, p95, p99)
- Evidence: app/services/metrics_service.py:39-43 (Histogram pattern); app/api/configs.py:35,64-65,99-100 (duration measurement pattern with time.perf_counter)

- Signal: `iot_image_proxy_external_fetch_duration_seconds`
- Type: Histogram
- Trigger: Within service layer, measure duration of external URL fetch (before image processing).
- Labels / fields: No labels
- Consumer: Prometheus dashboard isolating external fetch latency from internal processing
- Evidence: app/services/metrics_service.py:39-43 (Histogram pattern)

- Signal: `iot_image_proxy_image_size_bytes`
- Type: Histogram
- Trigger: After successful fetch, observe size of fetched image data (before processing).
- Labels / fields: No labels
- Consumer: Prometheus dashboard tracking typical image sizes fetched
- Evidence: app/services/metrics_service.py:39-43 (Histogram pattern)

- Signal: Structured logs at INFO level
- Type: Structured log
- Trigger: Log at key points: "Fetching image from external URL", "Image fetched successfully (size: X bytes)", "Resizing image (original: WxH, target: WxH)", "LVGL conversion successful (output size: X bytes)". Log at ERROR level for all exceptions with details (URL, error message, exception type).
- Labels / fields: log message, URL (sanitized), duration, sizes, error details
- Consumer: Log aggregation system (e.g., Loki) for debugging and auditing
- Evidence: app/services/config_service.py:13,89-91 (logger usage pattern)

---

## 10) Background Work & Shutdown

This feature has no background workers, threads, or long-running jobs. All operations are synchronous request/response processing. No shutdown hooks required.

- Worker / job: None
- Trigger cadence: N/A
- Responsibilities: N/A
- Shutdown handling: N/A
- Evidence: CLAUDE.md:389-442 (graceful shutdown integration only needed for background threads/jobs)

---

## 11) Security & Permissions

- Concern: Uncontrolled outbound HTTP requests to arbitrary URLs (SSRF risk)
- Touchpoints: `GET /api/images/lvgl` endpoint, `ImageProxyService.fetch_and_convert_image()` method
- Mitigation: Accept risk — This is a homelab application in a trusted network environment per the product brief. No authentication required. Users are trusted to provide legitimate URLs. Consider logging all external URLs fetched for auditing.
- Residual risk: Users could provide internal URLs (e.g., http://localhost, http://192.168.x.x) to scan internal network or exfiltrate data. Acceptable for homelab use case where all users are administrators. Production deployments would require URL allowlisting or SSRF protection libraries.
- Evidence: docs/product_brief.md:12 — "Users in trusted network environments (no authentication required)"

- Concern: Header injection (forwarding arbitrary headers to external URLs)
- Touchpoints: `GET /api/images/lvgl` endpoint header forwarding logic
- Mitigation: Accept risk — The `headers` query parameter specifies header names to forward from the incoming request, not arbitrary header values. The application does not allow users to inject arbitrary header values (only forward existing headers). This limits the attack surface.
- Residual risk: Users could forward sensitive headers (e.g., cookies, auth tokens) to untrusted external URLs. Acceptable for homelab use case where users control both the proxy and the external URLs.
- Evidence: Change brief:22 — "read the corresponding header from the incoming request and forward it to the external URL"

- Concern: Denial of service via large image processing
- Touchpoints: Service layer `fetch_and_convert_image()` method
- Mitigation: Rely on Pillow's decompression bomb protection (default limit 89478485 pixels). Set httpx timeout (30 seconds) to prevent indefinite hangs. No explicit file size limits (homelab use case, images expected to be small).
- Residual risk: Users could provide URLs to very large images (e.g., 10 MB), causing high memory usage and slow processing. Acceptable for homelab scale (<200 devices, infrequent requests). Could add max content-length check if needed.
- Evidence: Pillow docs: decompression bomb protection; CLAUDE.md:212-218 (fail fast, no defensive try/catch)

- Concern: Sensitive data exposure in logs (URLs, headers)
- Touchpoints: Logging statements in service layer and API layer
- Mitigation: Log URLs and header names, but not header values (especially auth tokens). Sanitize URLs to remove query parameters or credentials in logs if present.
- Residual risk: URLs themselves may contain sensitive data (e.g., presigned URLs with tokens). Log at INFO level only for successful operations; ERROR level for failures. Users should review logs in a secure environment.
- Evidence: app/services/config_service.py:89-91 (logger.warning pattern)

---

## 12) UX / UI Impact

This feature is backend-only. No direct UX/UI impact on the existing configuration management frontend. ESP32 devices will consume this endpoint directly to fetch and display images on LVGL displays.

**Expected usage flow (from ESP32 device perspective):**
1. ESP32 device constructs URL: `GET /api/images/lvgl?url=http://homeassistant.local/api/camera_proxy/camera.front_door&headers=Authorization&width=240&height=240`
2. ESP32 sends request with `Authorization: Bearer <token>` header (forwarded to Home Assistant)
3. Backend fetches image from Home Assistant, resizes to fit 240x240 display, converts to LVGL binary format
4. ESP32 receives binary data and displays on LVGL screen

No changes to existing frontend (configuration editor, device list, etc.).

---

## 13) Deterministic Test Plan

- Surface: API endpoint `GET /api/images/lvgl`
- Scenarios:
  - Given no query parameters, When GET /api/images/lvgl, Then 400 validation error (url is required)
  - Given url="not-a-valid-url", When GET /api/images/lvgl?url=not-a-valid-url, Then 400 validation error (url format invalid)
  - Given url="http://example.com/image.png" and valid PNG at that URL, When GET /api/images/lvgl?url=..., Then 200 with binary LVGL data, Cache-Control: no-store header
  - Given url="http://example.com/image.png" and headers="Authorization", When GET /api/images/lvgl with Authorization header present, Then 200 with binary LVGL data (header forwarded)
  - Given url="http://example.com/image.png" and headers="Authorization", When GET /api/images/lvgl without Authorization header, Then 400 error (missing header)
  - Given url="http://example.com/image.png" and width=100&height=100, When GET /api/images/lvgl with 200x200 image, Then 200 with resized 100x100 LVGL data
  - Given url="http://example.com/image.png" and width=100&height=100, When GET /api/images/lvgl with 50x50 image, Then 200 with original 50x50 LVGL data (no upscaling)
  - Given url="http://unreachable.local/image.png" (network failure), When GET /api/images/lvgl, Then 502 error (external fetch failed)
  - Given url="http://example.com/not-an-image.html" (returns HTML), When GET /api/images/lvgl, Then 500 error (decode failed)
  - Given url="http://example.com/corrupt.png" (corrupt image), When GET /api/images/lvgl, Then 500 error (decode failed)
- Fixtures / hooks: Mock httpx responses with `respx` library or `pytest-mock` to simulate external URL fetches. Use sample PNG images in tests/fixtures/ directory. Use `container` fixture to get `ImageProxyService` instance for service tests. Use `client` fixture for API tests.
- Gaps: No tests for LVGL conversion edge cases (e.g., specific color formats, transparency handling) — rely on upstream LVGLImage.py correctness. Could add integration tests with real external URLs in the future, but use mocks for deterministic unit tests.
- Evidence: tests/api/test_configs.py (API test pattern), tests/services/test_config_service.py (service test pattern), tests/conftest.py:68-70 (client fixture)

- Surface: Service `ImageProxyService.fetch_and_convert_image()`
- Scenarios:
  - Given valid URL and no headers, When fetch_and_convert_image, Then returns LVGL binary bytes
  - Given valid URL and headers dict, When fetch_and_convert_image with mocked httpx, Then httpx.get called with forwarded headers
  - Given valid URL and width=100&height=100, When fetch_and_convert_image with 200x200 image, Then resized to 100x100
  - Given valid URL and width=100&height=100, When fetch_and_convert_image with 50x50 image, Then no resizing (original 50x50)
  - Given valid URL and width=100 only, When fetch_and_convert_image with 200x200 image, Then resized to 100x100 (aspect ratio preserved)
  - Given network timeout, When fetch_and_convert_image, Then raises ExternalServiceException
  - Given HTTP 404 from external URL, When fetch_and_convert_image, Then raises ExternalServiceException
  - Given non-image response, When fetch_and_convert_image, Then raises ProcessingException
  - Given corrupt image data, When fetch_and_convert_image, Then raises ProcessingException
  - Given valid image, When fetch_and_convert_image, Then LVGL binary output is non-empty and starts with expected header (validate LVGL format basics)
- Fixtures / hooks: Mock httpx.Client.get() with pytest-mock. Use PIL to generate test images (in-memory). Mock LVGLImage.to_bin() if needed to isolate resize logic tests from LVGL conversion.
- Gaps: No exhaustive tests for aspect ratio calculation edge cases (e.g., very wide or very tall images) — rely on manual verification. Could add property-based tests with Hypothesis in the future.
- Evidence: tests/services/test_config_service.py:1-100+ (service test pattern)

- Surface: Exception handling in `@handle_api_errors`
- Scenarios:
  - Given ExternalServiceException raised, When @handle_api_errors catches it, Then 502 response with error details
  - Given ProcessingException raised, When @handle_api_errors catches it, Then 500 response with error details
  - Given InvalidOperationException raised (for missing header), When @handle_api_errors catches it, Then 400 response with error details
- Fixtures / hooks: Use existing `client` fixture, mock service to raise specific exceptions
- Gaps: None (critical error handling must be tested)
- Evidence: app/utils/error_handling.py:46-120 (error handler decorator)

---

## 14) Implementation Slices

This is a small feature, but can be broken into slices for incremental delivery:

- Slice: Dependencies and upstream LVGLImage.py integration
- Goal: Add Poetry dependencies, copy upstream LVGLImage.py, verify import works
- Touches: `pyproject.toml`, `app/utils/lvgl/LVGLImage.py`, `app/utils/lvgl/README.md`, `app/utils/lvgl/__init__.py`
- Dependencies: None. Run `poetry install` after adding dependencies to verify they resolve correctly.

- Slice: Exception handling extension (502 and 500 support)
- Goal: Add `ExternalServiceException` (502) and `ProcessingException` (500), extend `@handle_api_errors` to map them correctly
- Touches: `app/exceptions.py`, `app/utils/error_handling.py`, tests for error handling
- Dependencies: Depends on slice 1 (no code dependencies, but logical ordering)

- Slice: Service layer implementation
- Goal: Implement `ImageProxyService` with fetch, resize, LVGL conversion logic. Service receives `MetricsService` via constructor injection.
- Touches: `app/services/image_proxy_service.py`, `app/services/container.py`, `tests/services/test_image_proxy_service.py`
- Dependencies: Depends on slice 1 (imports LVGLImage), slice 2 (raises ExternalServiceException/ProcessingException), and slice 4 (metrics methods)

- Slice: Metrics integration
- Goal: Add image proxy metrics to `MetricsService`
- Touches: `app/services/metrics_service.py`
- Dependencies: Depends on slice 3 (service layer defines metric trigger points)

- Slice: API layer and schemas
- Goal: Implement API endpoint with query parameter validation and error handling
- Touches: `app/schemas/image_proxy.py`, `app/api/images.py`, `app/api/__init__.py`, `app/__init__.py`, `tests/api/test_images.py`
- Dependencies: Depends on slices 1-4 (service, exceptions, metrics must exist)

- Slice: Integration testing and documentation
- Goal: End-to-end tests with mocked external URLs, update OpenAPI docs
- Touches: `tests/api/test_images.py` (integration scenarios), SpectTree auto-generates OpenAPI docs (no manual changes)
- Dependencies: Depends on slice 5 (API endpoint must be implemented)

---

## 15) Risks & Open Questions

**Risks:**

- Risk: Upstream `LVGLImage.py` API changes or incompatibilities with Python 3.11+
- Impact: LVGL conversion fails at runtime, feature is broken
- Mitigation: Pin to a specific commit SHA from https://github.com/lvgl/lvgl/blob/master/scripts/LVGLImage.py. Document the commit SHA in `app/utils/lvgl/README.md`. Add integration test that verifies LVGLImage.to_bin() produces expected output format (basic smoke test).

- Risk: Large images cause high memory usage or slow processing, degrading performance
- Impact: API latency increases, potential out-of-memory errors
- Mitigation: Rely on Pillow's decompression bomb protection. Set httpx timeout (30 seconds). Log image sizes and processing durations in metrics. Monitor Prometheus metrics for latency spikes. Acceptable for homelab scale; add size limits if needed in production.

- Risk: SSRF attacks via arbitrary URL parameter
- Impact: Users can scan internal network or exfiltrate data via external URLs
- Mitigation: Accept risk for homelab use case (trusted network, no auth). Document the risk in `app/utils/lvgl/README.md`. Log all external URLs fetched for auditing. Production deployments should add URL allowlisting or SSRF protection.

- Risk: `headers` query parameter parsing is ambiguous (comma-separated list may contain header names with commas or special characters)
- Impact: Header forwarding fails or behaves unexpectedly
- Mitigation: Document that header names must not contain commas. Split by comma, strip whitespace, filter empty strings. Flask header names are case-insensitive, so lookups are robust. Most common headers (Authorization, X-Auth-Token, etc.) do not contain commas.

- Risk: `httpx` vs `requests` library choice
- Impact: Change brief mentions "httpx or requests". httpx is async-capable and modern, but requests is more widely known.
- Mitigation: Choose `httpx` for this implementation (modern, better defaults, async-ready for future enhancements). Synchronous `httpx.Client` usage is straightforward and similar to requests API.

**Open Questions:**

- Question: Should the `Content-Type` response header be `application/octet-stream` or a custom type like `application/x-lvgl-image`?
- Why it matters: Custom content type would be more descriptive but may not be recognized by standard tools. Octet-stream is generic but universally supported.
- Owner / follow-up: Confirm with user or default to `application/octet-stream` (safer choice). ESP32 firmware consumes raw binary regardless of content type.

- Question: Should there be a maximum timeout for external URL fetches (e.g., 10s, 30s, 60s)?
- Why it matters: Long timeouts improve reliability for slow external servers but increase latency and resource usage. Short timeouts reduce wait time but may cause failures for legitimate slow responses.
- Owner / follow-up: Default to 30 seconds (httpx default is 5 seconds). Document timeout as configurable if needed. Homelab use case typically has fast local networks.

- Question: Should image size or dimensions be limited (e.g., max 5 MB, max 1920x1080)?
- Why it matters: Prevents resource exhaustion from very large images but may reject legitimate images.
- Owner / follow-up: No explicit limits for initial implementation (rely on Pillow decompression bomb protection). Add limits if monitoring shows performance issues. Homelab images are expected to be small (ESP32 displays are ≤320x240).

---

## 16) Confidence

Confidence: High — The feature is well-scoped with clear requirements. The existing codebase provides strong patterns for API endpoints, service layer, error handling, and metrics integration. The upstream `LVGLImage.py` module is a known quantity from the LVGL project. The main risks (SSRF, large images, upstream API changes) are acceptable for the homelab use case and have documented mitigations. The deterministic test plan covers all critical paths and error scenarios. The only open question is the Content-Type header, which has a safe default (application/octet-stream). Implementation is straightforward with well-defined slices.
