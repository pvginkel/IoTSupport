# Code Review — LVGL Image Proxy

## 1) Summary & Decision

**Readiness**

The LVGL Image Proxy implementation is well-structured and follows project patterns consistently. The code correctly implements all plan requirements: external image fetching with header forwarding, aspect-ratio-preserving resize (downscale only), and LVGL format conversion. Error handling properly distinguishes 400/502/500 status codes via custom exceptions. Tests provide comprehensive coverage of success paths, error scenarios, and edge cases. The implementation adheres to CLAUDE.md layering (API → Service), uses dependency injection correctly, integrates metrics, and uses `time.perf_counter()` for duration measurements. Minor issues exist around metrics error type tracking in the API layer and potential temp file cleanup edge cases.

**Decision**

`GO-WITH-CONDITIONS` — Implementation is functionally complete and well-tested, but metrics tracking in the API layer has a logic flaw where error types are not properly propagated for ExternalServiceException and ProcessingException. Fix required before merging.

---

## 2) Conformance to Plan (with evidence)

**Plan alignment**

- **Plan Section 2 (Affected Areas)** ↔ All expected files created:
  - `app/api/images.py:1-112` — API endpoint with query validation and error handling
  - `app/services/image_proxy_service.py:1-248` — Service layer with fetch, resize, and LVGL conversion logic
  - `app/schemas/image_proxy.py:1-36` — Pydantic schema for query parameters with HttpUrl validation and Field constraints
  - `app/exceptions.py:42-59` — New `ExternalServiceException` (502) and `ProcessingException` (500) exceptions
  - `app/utils/error_handling.py:89-105` — Extended `@handle_api_errors` to map new exceptions to 502 and 500
  - `app/services/container.py:104-109` — `ImageProxyService` registered as Factory provider with `metrics_service` dependency
  - `app/services/metrics_service.py:116-178` — Four new metrics (operations_total, operation_duration, fetch_duration, image_size)
  - `app/__init__.py:40` — `app.api.images` wired to DI container
  - `app/api/__init__.py:14,18` — images_bp registered
  - `pyproject.toml:23-26,633` — Dependencies added (Pillow, httpx, pypng, lz4) with ruff/mypy ignore rules for LVGLImage.py
  - `app/utils/lvgl/__init__.py:1-6` — Re-exports `LVGLImage`, `ColorFormat`, `CompressMethod` for clean imports
  - `app/utils/lvgl/README.md:1-28` — Documents upstream source and maintenance instructions
  - `tests/services/test_image_proxy_service.py:1-323` — Service tests covering all scenarios from plan Section 13
  - `tests/api/test_images.py:1-310` — API tests covering request validation, error codes, headers

- **Plan Section 4 (API Surface)** ↔ Implemented correctly:
  - `GET /api/images/lvgl` query params: `url` (HttpUrl, required), `headers` (str, optional), `width/height` (int > 0, optional) — `app/schemas/image_proxy.py:9-33`
  - Response: binary data with `Cache-Control: no-store`, `Content-Type: application/octet-stream` — `app/api/images.py:88-90`
  - Error responses: 400 (missing url, invalid params, missing header) at `app/api/images.py:69-73`; 502 (external fetch) via `ExternalServiceException`; 500 (processing) via `ProcessingException`

- **Plan Section 5 (Algorithms)** ↔ Service implementation matches:
  - Header forwarding: API parses comma-separated `headers` param, validates each header exists in request — `app/api/images.py:60-74`
  - Image fetch: `httpx.Client` with 30s timeout, `follow_redirects=True` — `app/services/image_proxy_service.py:61-79`
  - Decode: `Image.open(BytesIO(...))`, convert to RGBA — `app/services/image_proxy_service.py:100-109`
  - Resize: Aspect ratio calculation with downscale-only constraint — `app/services/image_proxy_service.py:131-205`
  - LVGL conversion: Save PIL image as temp PNG, call `LVGLImage.from_png()`, `to_bin()` with `ARGB8888` and `NONE` compression — `app/services/image_proxy_service.py:207-247`

- **Plan Section 9 (Observability)** ↔ Metrics implemented:
  - `iot_image_proxy_operations_total` Counter with labels `status`, `error_type` — `app/services/metrics_service.py:117-121`
  - `iot_image_proxy_operation_duration_seconds` Histogram — `app/services/metrics_service.py:123-126`
  - `iot_image_proxy_external_fetch_duration_seconds` Histogram — `app/services/metrics_service.py:128-131`
  - `iot_image_proxy_image_size_bytes` Histogram — `app/services/metrics_service.py:133-136`
  - Metrics recording method `record_image_proxy_operation()` with proper exception handling — `app/services/metrics_service.py:145-178`

**Gaps / deviations**

- **No meaningful gap**: Plan Section 3 specified "ProcessingException for HTTP 500" but warned that "InvalidOperationException maps to 400 and cannot be used for 500 errors". Implementation correctly adds `ProcessingException` and maps it to 500 in error handler (`app/utils/error_handling.py:98-105`). No deviation.

- **Metrics error type tracking issue** (see Correctness findings): `app/api/images.py:93-103` sets `error_type` only for `InvalidOperationException`, but not for `ExternalServiceException` or `ProcessingException`. This means 502/500 errors will always record `error_type="unknown"` instead of the specific error type, reducing observability value. Plan Section 9 explicitly lists error types (`external_fetch_failed`, `decode_failed`, `lvgl_conversion_failed`) that should be tracked but are not being set in the API layer's exception handlers.

---

## 3) Correctness — Findings (ranked)

**Major — Metrics error type not set for ExternalServiceException and ProcessingException**

- Evidence: `app/api/images.py:93-103`
  ```python
  except InvalidOperationException:
      status = "error"
      if error_type == "none":
          error_type = "invalid_operation"
      raise

  except Exception:
      status = "error"
      if error_type == "none":
          error_type = "unknown"
      raise
  ```
- Impact: When `ExternalServiceException` or `ProcessingException` are raised by the service, they are caught by the generic `except Exception` handler. Since these exceptions don't set `error_type` before raising, the metrics will record `error_type="unknown"` instead of specific error types like `"external_fetch_failed"`, `"decode_failed"`, `"resize_failed"`, or `"lvgl_conversion_failed"`. This defeats the purpose of the `error_type` label in the `iot_image_proxy_operations_total` Counter metric, making it harder to diagnose production failures.
- Fix: Add explicit exception handlers for `ExternalServiceException` and `ProcessingException` before the generic `except Exception` handler. Map exception operation/cause to specific error types:
  ```python
  except ExternalServiceException:
      status = "error"
      error_type = "external_fetch_failed"
      raise

  except ProcessingException as e:
      status = "error"
      # Map operation to specific error type
      if "decode image" in e.operation:
          error_type = "decode_failed"
      elif "resize image" in e.operation:
          error_type = "resize_failed"
      elif "convert to LVGL format" in e.operation:
          error_type = "lvgl_conversion_failed"
      else:
          error_type = "processing_failed"
      raise

  except InvalidOperationException:
      status = "error"
      if error_type == "none":
          error_type = "invalid_operation"
      raise
  ```
- Confidence: High — This is a clear logic bug. The generic exception handler shadows the custom exceptions, preventing proper error type classification.

**Failure reasoning**: When `service.fetch_and_convert_image()` raises `ExternalServiceException("fetch image", "HTTP 404")` at line 73, the exception propagates to the API layer's try/except block. It bypasses the `InvalidOperationException` handler at line 93 (not an instance match), then gets caught by `except Exception:` at line 99. At that point, `error_type` is still `"none"` (set at line 53), so line 101 sets it to `"unknown"`. The exception re-raises and `@handle_api_errors` converts it to 502, but the metrics recorded in the finally block at line 107 show `error_type="unknown"` instead of `"external_fetch_failed"`.

---

**Minor — Potential temp file cleanup failure leaves orphaned files**

- Evidence: `app/services/image_proxy_service.py:241-247`
  ```python
  finally:
      # Clean up temporary files
      try:
          temp_png_path.unlink(missing_ok=True)
          temp_bin_path.unlink(missing_ok=True)
      except Exception as e:
          logger.warning("Failed to clean up temporary files: %s", e)
  ```
- Impact: If the first `unlink()` raises an exception (e.g., permission error), the second file (`temp_bin_path`) won't be deleted, leaving an orphaned temp file. Over many requests, this could fill up the temp directory.
- Fix: Catch exceptions separately for each unlink:
  ```python
  finally:
      # Clean up temporary files (handle each separately to avoid leaving orphans)
      try:
          temp_png_path.unlink(missing_ok=True)
      except Exception as e:
          logger.warning("Failed to clean up temp PNG file: %s", e)

      try:
          temp_bin_path.unlink(missing_ok=True)
      except Exception as e:
          logger.warning("Failed to clean up temp BIN file: %s", e)
  ```
- Confidence: Medium — The risk is low in practice (unlink rarely fails on modern filesystems with proper permissions), but the fix is trivial and defensive programming is worthwhile for long-running services.

---

**Minor — Metrics recorded twice on success path (service + API layer)**

- Evidence: `app/services/image_proxy_service.py:92-97` records `fetch_success` metrics, then `app/api/images.py:106-111` records overall operation metrics including `operation_duration`. Both metrics calls happen on the success path.
- Impact: The `iot_image_proxy_operations_total` Counter will be incremented twice per successful request: once with `status="fetch_success", error_type="none"` (service layer) and once with `status="success", error_type="none"` (API layer). This inflates the counter and makes it harder to interpret.
- Fix: Remove the metrics recording in the service layer for "fetch_success" (lines 92-97 in `image_proxy_service.py`). The service should only record granular metrics (`fetch_duration`, `image_size`) but not the overall operation status — that's the API layer's responsibility. Alternatively, change the service metric to use a different status label like `"fetch"` instead of `"fetch_success"` to distinguish it from the top-level operation metric.
- Confidence: Low — This is more of a design inconsistency than a correctness bug. The metrics still provide value, just with some redundancy.

---

## 4) Over-Engineering & Refactoring Opportunities

No hotspots identified. The code is appropriately engineered for the feature's scope. The resize logic in `_resize_image()` is verbose but necessary for correct aspect ratio handling with one or two dimensions specified. The temp file approach for LVGL conversion is required by the upstream `LVGLImage.py` API (which expects file paths, not in-memory data).

---

## 5) Style & Consistency

**Pattern: Time measurement uses `time.perf_counter()` consistently**

- Evidence: `app/api/images.py:51,106` and `app/services/image_proxy_service.py:59,81` all use `time.perf_counter()` for duration tracking
- Impact: Correct adherence to CLAUDE.md:195-210 requirement ("NEVER use `time.time()` for measuring durations"). No consistency issues.
- Recommendation: None needed — implementation is correct.

**Pattern: Dependency injection follows project convention**

- Evidence: `app/services/container.py:104-109` registers `ImageProxyService` as Factory with `metrics_service` dependency. API endpoint uses `@inject` decorator at `app/api/images.py:33-38` to receive both `image_proxy_service` and `metrics_service` from container.
- Impact: Matches CLAUDE.md:308-387 DI patterns. Consistent with existing services like `ConfigService`.
- Recommendation: None needed.

**Pattern: Logging uses proper levels and includes context**

- Evidence: Service logs at INFO for successful operations (`app/services/image_proxy_service.py:84-89`, `122-127`, `182-197`) and ERROR for failures (`66`, `71`, `76`, `106`, `119`, `204`).
- Impact: Appropriate for debugging and production monitoring. Matches `ConfigService` logging pattern.
- Recommendation: None needed.

---

## 6) Tests & Deterministic Coverage (new/changed behavior only)

**Surface: Service `ImageProxyService.fetch_and_convert_image()`**

- Scenarios:
  - Given valid URL and no headers, When fetch_and_convert_image, Then returns LVGL binary bytes with magic number 0x19 (`tests/services/test_image_proxy_service.py::TestImageProxyService::test_fetch_and_convert_basic`)
  - Given valid URL and headers dict, When fetch_and_convert_image, Then httpx.get called with forwarded headers (`test_fetch_with_headers`)
  - Given network timeout, When fetch_and_convert_image, Then raises ExternalServiceException with "timeout" message (`test_fetch_timeout`)
  - Given HTTP 404 from external URL, When fetch_and_convert_image, Then raises ExternalServiceException with "404" (`test_fetch_http_error`)
  - Given network error, When fetch_and_convert_image, Then raises ExternalServiceException with "network error" (`test_fetch_network_error`)
  - Given non-image response (HTML), When fetch_and_convert_image, Then raises ProcessingException with "decode image" (`test_invalid_image_data`)
  - Given 200x200 image and width=100&height=100, When fetch_and_convert_image, Then resized to fit bounding box (`test_resize_downscale_both_dimensions`)
  - Given 50x50 image and width=100&height=100, When fetch_and_convert_image, Then no upscaling (original 50x50) (`test_resize_no_upscale`)
  - Given 200x100 image and width=100 only, When fetch_and_convert_image, Then resizes width and preserves aspect ratio (`test_resize_width_only`)
  - Given 100x200 image and height=100 only, When fetch_and_convert_image, Then resizes height and preserves aspect ratio (`test_resize_height_only`)
  - Given 100x100 image and no resize params, When fetch_and_convert_image, Then returns LVGL data without resizing (`test_no_resize`)
  - Given 400x200 image (2:1 ratio) and width=100&height=100, When fetch_and_convert_image, Then preserves aspect ratio within bounds (`test_aspect_ratio_preservation`)

- Hooks: `unittest.mock.patch` for `httpx.Client`, `MagicMock` for responses, `_create_test_image()` helper generates PNG data via Pillow, `container` fixture provides service instances

- Gaps: None — comprehensive coverage of success paths, error paths, and resize logic edge cases.

- Evidence: `tests/services/test_image_proxy_service.py:1-323`

**Surface: API endpoint `GET /api/images/lvgl`**

- Scenarios:
  - Given url="https://example.com/image.png", When GET /api/images/lvgl, Then 200 with binary LVGL data, Cache-Control: no-store, Content-Type: application/octet-stream (`tests/api/test_images.py::TestImagesApi::test_get_lvgl_image_success`)
  - Given no query parameters, When GET /api/images/lvgl, Then 400 validation error (url required) (`test_get_lvgl_image_missing_url`)
  - Given url="not-a-valid-url", When GET /api/images/lvgl, Then 400 validation error (url format invalid) (`test_get_lvgl_image_invalid_url`)
  - Given url and headers="Authorization" with Authorization header present, When GET /api/images/lvgl, Then 200 and header forwarded to external URL (`test_get_lvgl_image_with_headers`)
  - Given url and headers="Authorization" without Authorization header in request, When GET /api/images/lvgl, Then 400 error with "Authorization" in message (`test_get_lvgl_image_missing_required_header`)
  - Given url and width=100&height=100, When GET /api/images/lvgl, Then 200 with resized LVGL data (`test_get_lvgl_image_with_resize`)
  - Given url and width=-10, When GET /api/images/lvgl, Then 400 validation error (positive integers required) (`test_get_lvgl_image_invalid_width`)
  - Given url and height=0, When GET /api/images/lvgl, Then 400 validation error (`test_get_lvgl_image_invalid_height`)
  - Given external URL timeout, When GET /api/images/lvgl, Then 502 with error code EXTERNAL_SERVICE_ERROR (`test_get_lvgl_image_external_timeout`)
  - Given external URL returns 404, When GET /api/images/lvgl, Then 502 with error details (`test_get_lvgl_image_external_404`)
  - Given network error, When GET /api/images/lvgl, Then 502 (`test_get_lvgl_image_network_error`)
  - Given non-image response (HTML), When GET /api/images/lvgl, Then 500 with error code PROCESSING_ERROR (`test_get_lvgl_image_invalid_image_data`)
  - Given headers="Authorization,X-API-Key" with both headers present, When GET /api/images/lvgl, Then 200 and both headers forwarded (`test_get_lvgl_image_multiple_headers`)
  - Given width=100 only, When GET /api/images/lvgl, Then 200 with resized image (`test_get_lvgl_image_width_only`)
  - Given height=100 only, When GET /api/images/lvgl, Then 200 with resized image (`test_get_lvgl_image_height_only`)
  - Given any valid request, When GET /api/images/lvgl, Then Cache-Control: no-store header is set (`test_get_lvgl_image_cache_control_header`)

- Hooks: `client` fixture for Flask test client, `unittest.mock.patch` for httpx, `_create_test_image()` helper

- Gaps: None — tests cover all query parameter combinations, error codes (400, 502, 500), header forwarding, and response headers.

- Evidence: `tests/api/test_images.py:1-310`

**Surface: Exception handling in `@handle_api_errors`**

- Scenarios:
  - Given ExternalServiceException raised, When @handle_api_errors catches it, Then 502 response with error code EXTERNAL_SERVICE_ERROR (`tests/api/test_images.py::TestImagesApi::test_get_lvgl_image_external_timeout`, `test_get_lvgl_image_external_404`, `test_get_lvgl_image_network_error`)
  - Given ProcessingException raised, When @handle_api_errors catches it, Then 500 response with error code PROCESSING_ERROR (`test_get_lvgl_image_invalid_image_data`)
  - Given InvalidOperationException raised (missing header), When @handle_api_errors catches it, Then 400 response with error details (`test_get_lvgl_image_missing_required_header`)

- Hooks: API tests implicitly test error handler by triggering exceptions via mocked service failures

- Gaps: None — error handler coverage is complete.

- Evidence: `app/utils/error_handling.py:89-105`, verified by API tests

---

## 7) Adversarial Sweep

**Check 1: Dependency injection wiring**

- Attack: Is `ImageProxyService` properly registered in the DI container and wired to API module?
- Evidence: `app/services/container.py:104-109` registers `image_proxy_service = providers.Factory(ImageProxyService, metrics_service=metrics_service)`. `app/__init__.py:40` includes `"app.api.images"` in `wire_modules` list. `app/api/images.py:34-38` uses `@inject` decorator with `Provide[ServiceContainer.image_proxy_service]` and `Provide[ServiceContainer.metrics_service]`.
- Why code held up: Factory provider creates a new service instance per request, ensuring thread safety. Both service dependencies (ImageProxyService and MetricsService) are correctly injected into the API endpoint. Wire modules list includes the new API module. No DI wiring issues.

**Check 2: Metrics integration**

- Attack: Are metrics properly defined, recorded, and exception-safe?
- Evidence: `app/services/metrics_service.py:117-136` defines four metrics (Counter, 3x Histogram) with proper types and labels. `record_image_proxy_operation()` method at lines 145-178 wraps all metric operations in try/except to prevent metric failures from crashing the service (logger.error at line 178). `app/api/images.py:106-111` records metrics in finally block, ensuring they execute even on exceptions.
- Caveat: Error type tracking has a bug (see Correctness finding above) where `error_type` is not set correctly for ExternalServiceException and ProcessingException.
- Why code mostly held up: Metrics are exception-safe and recorded in finally block. Metric definitions match plan Section 9. The error type bug is a logic issue, not a metric integration failure.

**Check 3: Temp file cleanup and resource leaks**

- Attack: Does LVGL conversion properly clean up temp files, even on exceptions?
- Evidence: `app/services/image_proxy_service.py:217-247` uses context managers (`with tempfile.NamedTemporaryFile`) to create temp files, but immediately assigns paths and closes them (exiting the context). Cleanup is manual in finally block (lines 241-247) with `unlink(missing_ok=True)`.
- Caveat: If first unlink fails, second file may not be deleted (see Minor finding above).
- Why code mostly held up: The finally block ensures cleanup runs even on conversion exceptions. The use of `missing_ok=True` prevents errors if files don't exist. The sequential unlink issue is a minor edge case (unlikely to happen in practice).

**Check 4: Observability and time measurement**

- Attack: Are durations measured with `time.perf_counter()` instead of `time.time()`?
- Evidence: `app/api/images.py:51` sets `start_time = time.perf_counter()`, line 106 calculates `duration = time.perf_counter() - start_time`. `app/services/image_proxy_service.py:59` sets `fetch_start = time.perf_counter()`, line 81 calculates `fetch_duration = time.perf_counter() - fetch_start`.
- Why code held up: Correct use of `time.perf_counter()` for all duration measurements, adhering to CLAUDE.md:195-210. No use of `time.time()` for durations.

**Check 5: Error handling and fail-fast philosophy**

- Attack: Does the code swallow exceptions or hide errors from users?
- Evidence: All exceptions in the service layer (`ExternalServiceException`, `ProcessingException`) are raised with `from e` chaining (e.g., `app/services/image_proxy_service.py:68-69`, `107-109`). The API layer re-raises all exceptions after setting metrics (`app/api/images.py:97`, `103`). No try/except blocks silently continue on errors.
- Why code held up: Adheres to CLAUDE.md:212-218 fail-fast philosophy. All errors surface to the user via `@handle_api_errors` decorator with proper HTTP status codes and error messages.

---

## 8) Invariants Checklist

**Invariant: LVGL binary output must start with magic number 0x19**

- Where enforced: Service returns bytes from `LVGLImage.to_bin()` (`app/services/image_proxy_service.py:239`). Tests verify magic number (`tests/services/test_image_proxy_service.py:59`, `tests/api/test_images.py:51`).
- Failure mode: If LVGLImage upstream changes binary format, devices would receive invalid data and fail to display images.
- Protection: Test assertions check `lvgl_data[0] == 0x19`. Upstream LVGLImage.py is a verbatim copy pinned to a specific version (documented in `app/utils/lvgl/README.md`).
- Evidence: `tests/services/test_image_proxy_service.py:59`, `tests/api/test_images.py:51`

**Invariant: Resized dimensions must not exceed original dimensions (no upscaling)**

- Where enforced: `app/services/image_proxy_service.py:180-189` checks if `target_width >= original_width and target_height >= original_height`, returns original image without resizing if true. Earlier logic at lines 147-175 uses `min(width, original_width)` and `min(height, original_height)` to cap target dimensions.
- Failure mode: If upscaling occurred, devices might receive images larger than their displays can handle, or quality would degrade due to interpolation.
- Protection: Explicit conditional check at line 180. Tests verify behavior with `test_resize_no_upscale` (50x50 image requested at 100x100 returns original).
- Evidence: `app/services/image_proxy_service.py:152,156,162,168,173,180-189`, `tests/services/test_image_proxy_service.py:196-220`

**Invariant: Forwarded headers must exist in incoming request**

- Where enforced: API layer at `app/api/images.py:67-73` reads each header name from `request.headers.get(header_name)`. If value is None, raises `InvalidOperationException` with 400 status.
- Failure mode: If missing header check is skipped, the service would forward `None` values to external URLs, causing unexpected behavior or auth failures.
- Protection: Explicit check with early failure (`raise InvalidOperationException`). Tests verify behavior with `test_get_lvgl_image_missing_required_header` (request without Authorization header returns 400).
- Evidence: `app/api/images.py:67-73`, `tests/api/test_images.py:96-105`

**Invariant: External URL fetch must timeout within 30 seconds**

- Where enforced: `app/services/image_proxy_service.py:61` creates httpx.Client with `timeout=30.0` seconds.
- Failure mode: Without timeout, slow or unresponsive external URLs could hang indefinitely, blocking request threads and degrading service availability.
- Protection: Explicit timeout parameter. httpx raises `TimeoutException` on timeout, caught at line 65 and converted to `ExternalServiceException` with 502.
- Evidence: `app/services/image_proxy_service.py:61`, `tests/services/test_image_proxy_service.py:86-103`, `tests/api/test_images.py:148-164`

---

## 9) Questions / Needs-Info

**Question: Should LVGLImage.py be pinned to a specific commit SHA?**

- Why it matters: The plan (Section 15, Risk 1) recommends pinning to a specific commit SHA and documenting it in README.md. Current README.md documents the source URL but doesn't specify a commit SHA. If upstream LVGLImage.py API changes, the implementation could break.
- Desired answer: Confirm whether to add a commit SHA to `app/utils/lvgl/README.md` (e.g., "Pinned to commit abc123 from 2026-01-10") or if the current approach (update manually and test) is acceptable for homelab use case.

**Question: Should metrics be recorded twice on success path?**

- Why it matters: See Minor finding above. Service layer records `status="fetch_success"` metric at `app/services/image_proxy_service.py:92-97`, and API layer records `status="success"` metric at `app/api/images.py:106-111`. This inflates the counter.
- Desired answer: Clarify whether service-level granular metrics (fetch_success) are intentional for debugging, or whether the service should only record sub-metrics (fetch_duration, image_size) and let the API layer own the overall operation counter.

---

## 10) Risks & Mitigations (top 3)

**Risk: Metrics error type tracking bug reduces production observability**

- Mitigation: Fix the exception handling in `app/api/images.py:93-103` to set specific error types for `ExternalServiceException` and `ProcessingException` before re-raising. See Correctness finding above for detailed fix.
- Evidence: `app/api/images.py:93-103`, plan Section 9 lists specific error types that are not being tracked

**Risk: Temp file cleanup failure could accumulate orphaned files**

- Mitigation: Refactor finally block in `app/services/image_proxy_service.py:241-247` to handle each unlink() separately, preventing one failure from blocking the other. See Minor finding above.
- Evidence: `app/services/image_proxy_service.py:241-247`

**Risk: Upstream LVGLImage.py API changes break conversion**

- Mitigation: Pin to specific commit SHA in README.md (per plan Section 15, Risk 1). Add integration test that verifies LVGL binary format basics (magic number, header structure) to detect upstream changes early.
- Evidence: Plan Section 15 Risk 1, `app/utils/lvgl/README.md:1-28` (missing commit SHA)

---

## 11) Confidence

Confidence: High — The implementation is well-structured, thoroughly tested, and follows project patterns correctly. The metrics error type bug is a straightforward logic fix (add two exception handlers). All core functionality (fetch, resize, convert, error handling) works as planned. Test coverage is comprehensive (26 test scenarios covering success paths, error codes, edge cases). The only open question is whether to pin LVGLImage.py to a specific commit, which is a documentation/maintenance decision rather than a code correctness issue.
