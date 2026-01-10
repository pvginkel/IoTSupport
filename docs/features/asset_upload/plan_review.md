# Asset Upload API - Plan Review

## 1) Summary & Decision

**Readiness**

The plan is well-researched and demonstrates a solid understanding of both the legacy PHP implementation and the existing Flask backend patterns. The research log accurately captures the PHP behavior, correctly identifies the multipart form-data handling challenge with SpectTree, and proposes appropriate solutions. The plan follows established patterns from ConfigService for filesystem operations and properly maps all affected files. However, there are several areas requiring clarification or adjustment before implementation can proceed confidently.

**Decision**

`GO-WITH-CONDITIONS` - The plan is fundamentally sound but requires addressing: (1) a cryptographic verification detail mismatch with PHP, (2) missing validation for directory separators beyond `..`, (3) clarification on service provider type (Factory vs Singleton), and (4) minor schema/exception type alignment with existing patterns.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md:59-69` - Service layer patterns - Pass - `plan.md:107-109` - Plan correctly identifies no BaseService inheritance needed since no database access
- `CLAUDE.md:95-109` - Schema layer patterns - Pass - `plan.md:113-116` - Plan references Pydantic patterns with Field descriptions
- `CLAUDE.md:195-210` - Time measurements - Pass - `plan.md:384-389` - Plan explicitly mentions `time.perf_counter()` for duration measurements
- `CLAUDE.md:264-295` - Metrics integration - Pass - `plan.md:143-146` - Plan includes MetricsService updates with appropriate metric types
- `docs/product_brief.md:35-40` - No authentication, filesystem storage - Pass - `plan.md:67-69` - Correctly scoped for trusted environment

**Fit with codebase**

- `app/services/container.py:19-23` - ConfigService uses `providers.Factory` - `plan.md:131-134` - Plan states "providers.Factory pattern for ConfigService, need similar for AssetUploadService" but doesn't specify whether key caching implies Singleton preference. Service initialization loads the RSA key; if Factory, key is loaded per-request (inefficient). Needs clarification.
- `app/api/__init__.py:11-15` - Blueprint registration pattern - `plan.md:125-128` - Plan correctly identifies pattern
- `app/exceptions.py:25-32` - InvalidOperationException signature - `plan.md:306` - Plan uses InvalidOperationException for filename validation but should consider ValidationException for input validation errors (see Section 5)
- `app/__init__.py:36-42` - Wire modules list - `plan.md:137-140` - Plan correctly identifies wiring requirement

---

## 3) Open Questions & Ambiguities

- Question: Should AssetUploadService be a Singleton (caching RSA key for lifetime) or Factory (loading key per-request)?
- Why it matters: A Factory would reload and parse the RSA key file on every upload request, adding ~10ms latency per request. A Singleton would load once but requires consideration for key rotation scenarios.
- Needed answer: Confirm whether key rotation during runtime is a requirement. If not, Singleton is preferable for performance.

---

- Question: What exact timestamp format do ESP32 devices send?
- Why it matters: The plan assumes ISO 8601 (`datetime.fromisoformat()`), but PHP's `DateTime` constructor is more lenient and accepts various formats. If devices send Unix timestamps or non-standard formats, parsing will fail.
- Needed answer: Sample timestamps from actual device uploads to confirm format compatibility.

---

- Question: Does the existing RSA key use PKCS#1 v1.5 or PSS padding?
- Why it matters: `plan.md:579-583` identifies this as a risk. PHP's `openssl_verify` with `OPENSSL_ALGO_SHA256` defaults to PKCS#1 v1.5 padding. Using incorrect padding in Python will cause all signature verifications to fail.
- Needed answer: Test with actual device signatures during implementation, or inspect key usage in device firmware.

---

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: AssetUploadService.validate_filename()
- Scenarios:
  - Given valid filename "firmware.bin", When validate_filename called, Then no exception raised (`tests/services/test_asset_upload_service.py::TestValidateFilename::test_valid_filename`)
  - Given filename with path traversal "../etc/passwd", When validate_filename called, Then exception raised (`tests/services/test_asset_upload_service.py::TestValidateFilename::test_path_traversal_rejected`)
  - Given filename with forward slash "subdir/file.bin", When validate_filename called, Then exception raised - **Plan mentions this at line 435 but test scenario at line 483 omits backslash validation**
  - Given empty filename "", When validate_filename called, Then exception raised (`tests/services/test_asset_upload_service.py::TestValidateFilename::test_empty_rejected`)
- Instrumentation: Validation failures logged at WARNING level per `plan.md:419-425`
- Persistence hooks: None (validation only)
- Gaps: Test scenario for backslash separator (`\`) missing from test plan despite security section mentioning it at `plan.md:435`
- Evidence: `plan.md:479-488`

---

- Behavior: AssetUploadService.validate_timestamp()
- Scenarios:
  - Given timestamp within tolerance, When validate_timestamp called, Then no exception raised
  - Given timestamp 301 seconds in past, When validate_timestamp called, Then exception raised
  - Given non-ISO8601 timestamp, When validate_timestamp called, Then exception raised
- Instrumentation: Validation failures logged at WARNING level
- Persistence hooks: None
- Gaps: None - coverage appears complete
- Evidence: `plan.md:492-502`

---

- Behavior: AssetUploadService.verify_signature()
- Scenarios:
  - Given valid signature, When verify_signature called, Then no exception raised
  - Given invalid signature, When verify_signature called, Then exception raised
  - Given non-base64 signature, When verify_signature called, Then exception raised
- Instrumentation: `asset_upload_signature_verification_duration_seconds` histogram per `plan.md:402-408`
- Persistence hooks: RSA key loaded at service initialization
- Gaps: None - coverage appears complete
- Evidence: `plan.md:506-515`

---

- Behavior: POST /api/assets endpoint
- Scenarios:
  - Given valid upload, When POST /api/assets, Then 200 with metadata response
  - Given missing required field, When POST /api/assets, Then 400 with specific error
  - Given invalid signature, When POST /api/assets, Then 400
- Instrumentation: `asset_upload_requests_total`, `asset_upload_duration_seconds`, `asset_upload_file_size_bytes`
- Persistence hooks: File written to ASSETS_DIR
- Gaps: None - coverage appears complete
- Evidence: `plan.md:532-544`

---

## 5) Adversarial Sweep (must find >=3 credible issues or declare why none exist)

**Major - Directory separator validation incomplete**

**Evidence:** `plan.md:435` states "validate filename does not contain directory separators (`/`, `\`)" but the test scenarios at `plan.md:479-488` only explicitly test forward slash. Additionally, the primary validation at `plan.md:306` only mentions `..` sequences.

**Why it matters:** On Windows or with certain filesystem abstractions, backslash could be interpreted as a path separator, potentially allowing path traversal via `subdir\file.bin`. While the homelab deployment is Linux-only, defense in depth requires validating both separators.

**Fix suggestion:** Add explicit backslash test scenario at `plan.md:483` and ensure implementation rejects both `\` and `/` in filenames. Consider using `os.path.basename()` on the filename and comparing to original to catch any path component.

**Confidence:** Medium - Linux deployments are not vulnerable to backslash, but code portability and defense in depth warrant the check.

---

**Major - Exception type inconsistency with codebase patterns**

**Evidence:** `plan.md:306` states "raise InvalidOperationException" for filename validation, but examining `app/exceptions.py:35-39` shows `ValidationException` exists specifically for validation failures. The plan also mentions "ValidationException" at `plan.md:314, 322, 329, 338` for timestamp and signature validation but uses "InvalidOperationException" at `plan.md:306`.

**Why it matters:** Inconsistent exception types lead to inconsistent error responses. Per `app/utils/error_handling.py:96-103`, ValidationException returns `VALIDATION_FAILED` error code, while InvalidOperationException returns `INVALID_OPERATION`. Input validation failures should consistently use ValidationException.

**Fix suggestion:** Standardize on ValidationException for all input validation errors (filename, timestamp format, signature format) and InvalidOperationException only for operation-level failures (signature verification failure is arguably validation).

**Confidence:** High - Direct code reference confirms exception type discrepancy.

---

**Major - Cryptographic key extraction differs from PHP**

**Evidence:** `plan.md:273-274` states "Public key extracted from RSA private key" and references PHP at lines 25-26. Examining `/work/iotsupport/src/html/assetctl/upload.php:25-27`:
```php
$key = openssl_pkey_get_private(file_get_contents("$root/assets/kubernetes-signing-key"));
$public_key = openssl_pkey_get_details($key)['key'];
$verification = openssl_verify($timestamp, $signature, $public_key, OPENSSL_ALGO_SHA256);
```

The PHP code loads a **private key** file but extracts the **public key** from it for verification. This is unusual - typically the verifier only has the public key. The plan acknowledges this at `plan.md:274` but doesn't address why the device would sign with the corresponding private key. If devices have the private key, any device can forge signatures.

**Why it matters:** This security architecture suggests either (1) all devices share the same signing key (unusual but valid for homelab), or (2) there's a misunderstanding of the key distribution. The plan should confirm the key architecture.

**Fix suggestion:** Add clarifying note that this is a shared-secret model where trusted devices possess the private key. Document this security model explicitly. Alternatively, confirm the key distribution model with the device firmware.

**Confidence:** Medium - The PHP implementation works, so the plan should be fine, but the security model should be explicitly documented.

---

**Minor - Service provider type affects key loading performance**

**Evidence:** `plan.md:131-134` references ConfigService's Factory pattern but `plan.md:254-255` states "Key loading: One-time cost at service initialization; ~10ms to parse PEM file". If AssetUploadService uses Factory (like ConfigService), the key is loaded on every request.

**Why it matters:** 10ms per request for key loading adds latency and unnecessary I/O. ConfigService uses Factory because it's stateless filesystem operations. AssetUploadService benefits from caching the parsed key.

**Fix suggestion:** Use `providers.Singleton` for AssetUploadService to cache the RSA key, or add a separate key provider that caches the key.

**Confidence:** High - Performance impact is measurable.

---

## 6) Derived-Value & Persistence Invariants (stacked entries)

- Derived value: Uploaded file destination path
  - Source dataset: `ASSETS_DIR` (config) + `filename` (user input, filtered)
  - Write / cleanup triggered: File written to derived path; existing file overwritten
  - Guards: Filename validation rejects `..` and directory separators; atomic write via temp + rename
  - Invariant: Final path must remain within ASSETS_DIR boundaries
  - Evidence: `plan.md:278-283`

---

- Derived value: Timestamp validity window
  - Source dataset: Server UTC time (unfiltered) + configured tolerance (default 300s)
  - Write / cleanup triggered: None - validation only
  - Guards: Timezone-aware comparison using UTC
  - Invariant: Timestamp validation prevents replay attacks outside tolerance window
  - Evidence: `plan.md:260-265`

---

- Derived value: Public key from private key file
  - Source dataset: SIGNING_KEY_PATH file contents (filtered: must be valid PEM)
  - Write / cleanup triggered: Key cached in memory at service init; no disk writes
  - Guards: Key loading failure prevents service initialization (fail fast)
  - Invariant: Key must match device signing key
  - Evidence: `plan.md:269-274`

---

## 7) Risks & Mitigations (top 3)

- Risk: RSA signature padding mismatch causes all verifications to fail
- Mitigation: Test with actual device-generated signatures before deployment; PHP default is PKCS1v15
- Evidence: `plan.md:579-583`

---

- Risk: Timestamp format incompatibility with device timestamps
- Mitigation: Obtain sample timestamps from devices; consider `dateutil.parser.isoparse()` for lenient parsing
- Evidence: `plan.md:587-590`

---

- Risk: Factory provider pattern causes key reload on every request (10ms overhead)
- Mitigation: Use Singleton provider or separate cached key provider
- Evidence: `plan.md:131-134, 254-255`

---

## 8) Confidence

Confidence: Medium - The plan is well-researched and follows established patterns, but the cryptographic verification and exception type inconsistencies require resolution before implementation. The timestamp format question is lower risk since it can be addressed during implementation with device testing.
