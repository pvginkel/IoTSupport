# Plan Review: Database Configuration Storage

## 1) Summary & Decision

**Readiness**

The plan is well-researched and comprehensive, demonstrating solid understanding of both the current IoT Support codebase and the ElectronicsInventory reference implementation. The file map is detailed, the API surface is clearly defined, and test scenarios cover the critical paths. All previously identified gaps have been addressed: the plan now correctly uses `RecordExistsException` for duplicate MAC conflicts, explicitly documents transaction boundaries and the ConfigService Factory provider pattern, includes backward-compatible MAC format normalization in the `.json` endpoint, details the health check flow with database connectivity, and addresses `updated_at` timestamp handling.

**Decision**

`GO` - The plan addresses all major concerns and is ready for implementation. The patterns are well-established from ElectronicsInventory, the API contracts are clear, and test coverage is comprehensive.

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `CLAUDE.md` (Layering) - Pass - `plan.md:319-374` - API endpoints delegate to ConfigService; service handles business logic
- `CLAUDE.md` (BaseService pattern) - Pass - `plan.md:141-143,475` - Plan correctly references `BaseService` from ElectronicsInventory and confirms Factory provider pattern
- `CLAUDE.md` (Test coverage) - Pass - `plan.md:579-628` - Comprehensive test scenarios for both service and API layers
- `CLAUDE.md` (No native PostgreSQL ENUMs) - Pass - `plan.md:238-251` - Config table uses standard types only
- `CLAUDE.md` (Transaction management) - Pass - `plan.md:467-475` - Explicitly documents that services must not call `db.commit()`
- `product_brief.md` (No authentication) - Pass - `plan.md:556-559` - Security section confirms no changes to auth model

**Fit with codebase**

- `app/services/container.py` - `plan.md:191-193,475` - Plan correctly identifies ConfigService transition to Factory with `db=db_session` injection
- `app/exceptions.py` - `plan.md:211-213,481-485` - Plan correctly uses existing `RecordExistsException` for duplicate MAC conflicts
- `app/api/configs.py` - `plan.md:389-391` - MQTT publish pattern maintained correctly

---

## 3) Open Questions & Ambiguities

All significant ambiguities have been resolved in the updated plan. The Open Questions section (`plan.md:708-722`) documents six resolved questions covering:

1. MAC format backward compatibility
2. Content validation approach
3. Timestamp handling with `onupdate=func.now()`
4. Exception usage for duplicate MAC
5. ConfigService provider pattern
6. Transaction management boundaries

No blocking questions remain.

---

## 4) Deterministic Backend Coverage (new/changed behavior only)

- Behavior: POST /api/configs (create new config)
- Scenarios:
  - Given valid MAC and content, When POST /api/configs, Then 201 with config including `id` (`tests/api/test_configs.py::test_create_config_success`)
  - Given duplicate MAC, When POST /api/configs, Then 409 (`tests/api/test_configs.py::test_create_config_duplicate_mac`)
  - Given invalid MAC format, When POST /api/configs, Then 400 (`tests/api/test_configs.py::test_create_config_invalid_mac`)
- Instrumentation: `config_operation_duration_seconds{operation="create"}` histogram
- Persistence hooks: Alembic migration for `configs` table; test fixtures using database session
- Gaps: None
- Evidence: `plan.md:329-335`, `plan.md:610-612`

- Behavior: GET /api/configs/<id> (get by surrogate ID)
- Scenarios:
  - Given config exists, When GET /api/configs/1, Then 200 with full config (`tests/api/test_configs.py::test_get_config_by_id`)
  - Given config not found, When GET /api/configs/999, Then 404 (`tests/api/test_configs.py::test_get_config_by_id_not_found`)
- Instrumentation: `config_operation_duration_seconds{operation="get"}` histogram
- Persistence hooks: Database query by primary key
- Gaps: None
- Evidence: `plan.md:337-343`, `plan.md:613-614`

- Behavior: PUT /api/configs/<id> (update by ID)
- Scenarios:
  - Given config exists, When PUT /api/configs/1 with content, Then 200 with updated config (`tests/api/test_configs.py::test_update_config`)
  - Given config not found, When PUT /api/configs/999, Then 404 (`tests/api/test_configs.py::test_update_config_not_found`)
- Instrumentation: `config_operation_duration_seconds{operation="update"}` histogram
- Persistence hooks: Database update; MQTT publish
- Gaps: None
- Evidence: `plan.md:345-351`, `plan.md:615-616`

- Behavior: DELETE /api/configs/<id>
- Scenarios:
  - Given config exists, When DELETE /api/configs/1, Then 204 (`tests/api/test_configs.py::test_delete_config`)
  - Given config not found, When DELETE /api/configs/999, Then 404 (`tests/api/test_configs.py::test_delete_config_not_found`)
- Instrumentation: `config_operation_duration_seconds{operation="delete"}` histogram
- Persistence hooks: Database delete
- Gaps: None
- Evidence: `plan.md:353-358`, `plan.md:617-618`

- Behavior: GET /api/configs/<mac>.json (ESP32 device lookup with backward compatibility)
- Scenarios:
  - Given config exists with MAC, When GET /api/configs/aa:bb:cc:dd:ee:ff.json, Then 200 with raw JSON (`tests/api/test_configs.py::test_get_raw_config`)
  - Given uppercase MAC, When GET /api/configs/AA:BB:CC:DD:EE:FF.json, Then normalizes and returns 200 (`tests/api/test_configs.py::test_get_raw_config_uppercase`)
  - Given dash-separated MAC, When GET /api/configs/aa-bb-cc-dd-ee-ff.json, Then normalizes and returns 200 (`tests/api/test_configs.py::test_get_raw_config_dash_format`)
  - Given config not found, When GET /api/configs/xx:xx:xx:xx:xx:xx.json, Then 404 (`tests/api/test_configs.py::test_get_raw_config_not_found`)
- Instrumentation: `config_operation_duration_seconds{operation="get_raw"}` histogram
- Persistence hooks: Database query by mac_address (indexed via unique constraint)
- Gaps: None
- Evidence: `plan.md:361-367,412-427`, `plan.md:619-622`

- Behavior: Health check endpoint with database connectivity
- Scenarios:
  - Given database connected, When GET /api/health, Then 200 with healthy status
  - Given database disconnected, When GET /api/health, Then 503 with unhealthy status
- Instrumentation: Health status for Kubernetes probes
- Persistence hooks: `check_db_connection()` from database utilities
- Gaps: None
- Evidence: `plan.md:429-438`

---

## 5) Adversarial Sweep (must find >=3 credible issues or declare why none exist)

- Checks attempted: Transaction boundary violations, exception type mismatches, missing health check integration, updated_at timestamp auto-update, MAC format backward compatibility, ConfigService provider pattern
- Evidence: `plan.md:467-475` (transaction boundaries), `plan.md:481-485` (exception usage), `plan.md:429-438` (health check flow), `plan.md:255` (updated_at handling), `plan.md:412-427` (MAC normalization), `plan.md:475` (Factory provider pattern)
- Why the plan holds: All previously identified issues have been addressed in the updated plan. Transaction boundaries are explicitly documented with the prohibition on `db.commit()` in services. The existing `RecordExistsException` is correctly referenced for duplicate MAC conflicts. Health check flow is detailed with database connectivity verification. The `updated_at` timestamp handling via `onupdate=func.now()` is documented. MAC format backward compatibility is implemented via normalization in the `.json` endpoint. ConfigService Factory provider pattern is explicitly confirmed.

---

## 6) Derived-Value & Persistence Invariants (stacked entries)

- Derived value: `device_name`
  - Source dataset: `content` JSON field, extracted on every create/update
  - Write / cleanup triggered: Updated in `configs` table row; no cleanup needed
  - Guards: Optional field, stored as NULL if not present in content
  - Invariant: `device_name` column always reflects current `content.deviceName` value (denormalized)
  - Evidence: `plan.md:444-449`

- Derived value: `device_entity_id`
  - Source dataset: `content` JSON field, extracted on every create/update
  - Write / cleanup triggered: Updated in `configs` table row; no cleanup needed
  - Guards: Optional field, stored as NULL if not present in content
  - Invariant: `device_entity_id` column always reflects current `content.deviceEntityId` value
  - Evidence: `plan.md:451-456`

- Derived value: `enable_ota`
  - Source dataset: `content` JSON field, extracted on every create/update
  - Write / cleanup triggered: Updated in `configs` table row; no cleanup needed
  - Guards: Optional field, stored as NULL if not present in content
  - Invariant: `enable_ota` column always reflects current `content.enableOTA` value
  - Evidence: `plan.md:458-463`

- Derived value: `config_count` metric
  - Source dataset: Count of all rows in `configs` table (unfiltered)
  - Write / cleanup triggered: Prometheus gauge updated after create/delete operations
  - Guards: Recalculated on each list operation; eventual consistency acceptable
  - Invariant: Gauge approximately reflects actual row count (may lag by one request)
  - Evidence: `plan.md:528-533`

---

## 7) Risks & Mitigations (top 3)

- Risk: SQLite vs PostgreSQL dialect differences causing tests to pass but production to fail
- Mitigation: Use only standard SQL features in queries; avoid PostgreSQL-specific functions. The plan acknowledges this risk.
- Evidence: `plan.md:696-698`

- Risk: ESP32 devices using dash-separated MAC format will receive errors after migration
- Mitigation: Implemented MAC format normalization in `.json` endpoint to accept both colon and dash separators, converting internally to colon format. Explicit test scenario added.
- Evidence: `plan.md:412-427,622,700-702,712`

- Risk: Concurrent requests creating configs with same MAC could cause race condition
- Mitigation: Rely on database unique constraint as primary guard; service-level check provides better error message but database constraint ensures integrity.
- Evidence: `plan.md:471-472,484`

---

## 8) Confidence

Confidence: High - The plan is comprehensive, follows established patterns from ElectronicsInventory, addresses all previously identified gaps, and provides clear implementation guidance. Test coverage is thorough with explicit scenarios for all new behaviors including backward compatibility.
