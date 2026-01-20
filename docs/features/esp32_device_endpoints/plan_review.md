# ESP32 Device Endpoints - Plan Review

## 1) Summary & Decision

**Readiness**

The plan is well-researched and demonstrates thorough understanding of the existing codebase patterns. It correctly identifies the affected areas, error handling infrastructure, and testing requirements. The plan proposes additive endpoints that preserve existing behavior, which minimizes risk. However, there are two technical issues that need clarification: (1) the routing approach for `.json` suffix detection needs to be defined more precisely, and (2) the plan references reusing `AssetUploadService.validate_filename` but that method is only available on instances, so the plan should clarify whether to add a service method for asset retrieval or implement inline validation.

**Decision**

`GO-WITH-CONDITIONS` - The plan is sound and implementation-ready with minor clarifications needed on routing strategy and asset service architecture.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md` API Layer Pattern - Pass - `plan.md:81-84` shows endpoints will be added to existing modules (`app/api/configs.py`, `app/api/assets.py`) following the established pattern of delegating to services and using `@handle_api_errors`
- `CLAUDE.md` Service Layer Pattern - Pass - `plan.md:89-91` correctly identifies that `AssetUploadService` may need a new method for asset retrieval; service has no Flask imports per guidelines
- `CLAUDE.md` Testing Requirements - Pass - `plan.md:304-338` provides comprehensive test scenarios covering success paths, error conditions, and edge cases per Definition of Done
- `CLAUDE.md` Error Handling Philosophy - Pass - `plan.md:209-252` correctly identifies all failure modes and leverages existing exception types (`RecordNotFoundException`, `InvalidOperationException`, `ValidationException`) that propagate to users
- `CLAUDE.md` Time Measurements - Pass - `plan.md:173-174` references existing metrics patterns which use `time.perf_counter()` as shown in `app/api/configs.py:36,81`
- `product_brief.md` No Authentication - Pass - `plan.md:286-292` explicitly confirms unauthenticated endpoints per trusted homelab design
- `product_brief.md` Filesystem Storage - Pass - `plan.md:62-66` correctly assumes CephFS direct serving is appropriate for ~200 devices

**Fit with codebase**

- `app/api/configs.py` - `plan.md:81-84` - Plan assumes Flask route can detect `.json` suffix; implementation approach (separate route vs path converter) not specified but both are viable
- `app/services/asset_upload_service.py` - `plan.md:89-91` - Service currently has `validate_filename()` (line 80-103) but no `get_asset_path()` method; plan correctly identifies this gap
- `app/services/config_service.py` - `plan.md:163-174` - Existing `get_config()` returns `ConfigDetail` with `content` dict; plan correctly extracts this for raw serving
- `tests/conftest.py` - `plan.md:326` - New `make_asset_file` fixture needed; aligns with existing `make_config_file` pattern (line 119-128)

---

## 3) Open Questions & Ambiguities

- Question: What Flask routing approach will be used for `.json` suffix detection?
- Why it matters: Flask's default path matching won't distinguish `/configs/<mac>` from `/configs/<mac>.json` without explicit handling - either a separate route with suffix in the path or a path converter is needed
- Needed answer: Plan should specify whether to use a separate route (`@configs_bp.route("/<mac_address>.json")`) or a combined route with suffix detection in the handler

- Question: Should `AssetUploadService` gain a new method for asset retrieval or should the API implement inline file serving?
- Why it matters: CLAUDE.md mandates services contain all business logic, but simple file existence checks and path construction might not justify a service method for read-only operations
- Needed answer: Clarify whether to add `get_asset_path(filename: str) -> Path` method to service or handle inline with reused `validate_filename()`

- Question: How should `send_file()` integrate with the `@handle_api_errors` decorator for OSError handling?
- Why it matters: `send_file()` can raise `FileNotFoundError` after the response starts streaming, which `@handle_api_errors` may not catch cleanly
- Needed answer: Confirm file existence check before `send_file()` to ensure errors are caught within decorator scope

---

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: `GET /api/configs/<mac>.json` - Raw config serving
- Scenarios:
  - Given valid MAC with `.json` suffix for existing config, When requesting, Then return HTTP 200 with raw JSON content and `Cache-Control: no-cache` header (`tests/api/test_configs.py::TestGetRawConfig`)
  - Given valid MAC without `.json` suffix for existing config, When requesting, Then return HTTP 200 with wrapped ConfigResponseSchema (existing behavior preserved) (`tests/api/test_configs.py::TestGetConfig::test_get_config_success`)
  - Given MAC with `.json` suffix for non-existent config, When requesting, Then return HTTP 404 with error JSON (`tests/api/test_configs.py::TestGetRawConfig::test_not_found`)
  - Given invalid MAC format with `.json` suffix, When requesting, Then return HTTP 400 (`tests/api/test_configs.py::TestGetRawConfig::test_invalid_mac`)
  - Given uppercase MAC with `.json` suffix, When requesting, Then normalize and return HTTP 200 (`tests/api/test_configs.py::TestGetRawConfig::test_uppercase_normalized`)
- Instrumentation: `metrics_service.record_operation("get_raw", status, duration)` following pattern at `app/api/configs.py:65-66`
- Persistence hooks: None (read-only)
- Gaps: None
- Evidence: `plan.md:306-316`

- Behavior: `GET /api/assets/<filename>` - Binary asset serving
- Scenarios:
  - Given valid filename for existing asset, When requesting, Then return HTTP 200 with binary content and `Cache-Control: no-cache` header (`tests/api/test_assets.py::TestGetAsset::test_success`)
  - Given filename for non-existent asset, When requesting, Then return HTTP 404 (`tests/api/test_assets.py::TestGetAsset::test_not_found`)
  - Given filename with path traversal (`../`), When requesting, Then return HTTP 400 (`tests/api/test_assets.py::TestGetAsset::test_path_traversal`)
  - Given filename with directory separator (`/` or `\`), When requesting, Then return HTTP 400 (`tests/api/test_assets.py::TestGetAsset::test_directory_separator`)
  - Given empty filename, When requesting, Then return HTTP 400 (`tests/api/test_assets.py::TestGetAsset::test_empty_filename`)
- Instrumentation: New `metrics_service.record_asset_serve(status, duration)` or extend existing metrics
- Persistence hooks: None (read-only)
- Gaps: Plan mentions `make_asset_file` fixture but doesn't specify test data setup; should mirror `tests/conftest.py:119-128`
- Evidence: `plan.md:318-328`

---

## 5) Adversarial Sweep

### Major - Routing Collision Risk for `.json` Suffix

**Evidence:** `plan.md:143-147` describes `GET /api/configs/<mac>.json` but doesn't specify how Flask distinguishes this from existing `GET /api/configs/<mac>` route at `app/api/configs.py:69`

**Why it matters:** Flask's Werkzeug router uses first-match semantics. If both routes are registered with overlapping patterns, the wrong handler may be invoked. The existing route `/<mac_address>` would match `aa-bb-cc-dd-ee-ff.json` as a full MAC string, triggering invalid MAC validation.

**Fix suggestion:** Define explicit routing strategy in plan: either (a) add separate route `@configs_bp.route("/<mac_address>.json", methods=["GET"])` registered before the generic route, or (b) use Flask path converters, or (c) use a single route with suffix detection in handler. Option (a) is cleanest.

**Confidence:** High - Flask routing behavior is deterministic and testable.

---

### Major - Asset File Existence Check Before send_file()

**Evidence:** `plan.md:176-184` Step 4 says "Check file existence" then Step 5 uses `send_file()`, but doesn't specify the check happens before error handling scope ends

**Why it matters:** If `send_file()` is called and the file doesn't exist, it raises `FileNotFoundError`. The `@handle_api_errors` decorator (`app/utils/error_handling.py:49-150`) catches this as a generic `Exception` returning HTTP 500, not the intended HTTP 404. The plan must ensure the existence check raises `RecordNotFoundException` before calling `send_file()`.

**Fix suggestion:** Make explicit in plan: "Check file existence with `Path.exists()`, raise `RecordNotFoundException` if missing, only then call `send_file()`." This matches the pattern at `app/services/config_service.py:126-127`.

**Confidence:** High - Error handling decorator behavior is visible in code.

---

### Minor - Response Format for Raw Config vs Wrapped Config

**Evidence:** `plan.md:145` says raw endpoint returns "Raw JSON config content... HTTP 200" but existing wrapped endpoint at `app/api/configs.py:87-93` returns `ConfigResponseSchema.model_dump()`

**Why it matters:** The raw endpoint must return Flask's `jsonify()` result or a dict (which Flask auto-serializes), not a Pydantic model. Plan correctly says "Flask auto-serializes dict to JSON" but should confirm no SpectTree `@api.validate(resp=...)` decorator is applied to raw endpoint since response is dynamic JSON, not a schema.

**Fix suggestion:** Explicitly note that raw endpoint should NOT use `@api.validate(resp=...)` decorator since the response shape is the stored JSON, not a fixed schema.

**Confidence:** Medium - Implementation detail, but affects OpenAPI documentation consistency.

---

Adversarial checks performed:
- Filtered/derived state driving writes: N/A - endpoints are read-only
- Transaction safety: N/A - no database operations
- Session/flush patterns: N/A - filesystem only
- DI wiring: Verified services are already wired (`app/api/configs.py:32-33`, `app/api/assets.py:37-39`)
- Shutdown coordination: N/A - synchronous handlers with no background work

---

## 6) Derived-Value & Persistence Invariants

The plan correctly identifies that these endpoints have no derived state (`plan.md:195-199`). Verification:

- Derived value: None
  - Source dataset: Read-only file access
  - Write / cleanup triggered: None
  - Guards: N/A
  - Invariant: Endpoints never modify filesystem state
  - Evidence: `plan.md:195-199` "These endpoints are stateless read operations with no derived state, persistence writes, or cleanup actions"

Given the read-only nature of both endpoints, no persistence invariants apply. The plan's "None" declaration is justified.

---

## 7) Risks & Mitigations (top 3)

- Risk: Flask `send_file()` streaming may bypass error handling for late failures
- Mitigation: Perform explicit file existence check before `send_file()` call; raise `RecordNotFoundException` within `@handle_api_errors` scope
- Evidence: `plan.md:176-184` - sequence shows check before send_file but doesn't emphasize error type

- Risk: Route registration order may cause `.json` suffix route to be shadowed
- Mitigation: Register the `.json` route before the generic route, or use explicit path patterns
- Evidence: `plan.md:143-147` - route paths specified but registration order not addressed

- Risk: Large firmware files (>10MB) may cause slow responses or timeouts
- Mitigation: Plan acknowledges this at `plan.md:351-353` and suggests nginx offload as future optimization; acceptable for MVP given ~200 device scale
- Evidence: `plan.md:186-187` notes "acceptable for firmware files under ~10MB"

---

## 8) Confidence

Confidence: High - The plan demonstrates solid understanding of existing patterns, correctly identifies all affected areas and error conditions, and proposes a minimal, additive implementation. The two conditions (routing clarity and explicit file existence check) are straightforward to address during implementation.
