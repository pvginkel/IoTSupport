# IoT Support Backend - Implementation Plan

This document outlines the implementation plan for the IoT Support Backend, organized into six phases. Deployment (Dockerfile, docker-compose, Helm, Kubernetes) is out of scope.

## User Requirements Checklist

- [ ] List endpoint (`GET /api/configs`) returns MAC address, deviceName, deviceEntityId, enableOTA for all configs
- [ ] Get endpoint (`GET /api/configs/<mac>`) returns full JSON content for a specific MAC address
- [ ] Save endpoint (`PUT /api/configs/<mac>`) creates or updates config (upsert semantics)
- [ ] Delete endpoint (`DELETE /api/configs/<mac>`) removes config for a MAC address
- [ ] Validate MAC address format: lowercase, hyphen-separated (`xx-xx-xx-xx-xx-xx`)
- [ ] Validate content is valid JSON object (no schema validation beyond that)
- [ ] Return null for missing optional fields (deviceName, deviceEntityId, enableOTA)
- [ ] Health endpoint at `/api/health` for Kubernetes probes
- [ ] Prometheus metrics at `/metrics`
- [ ] OpenAPI documentation at `/api/docs`
- [ ] Config directory path from `ESP32_CONFIGS_DIR` environment variable

## Phase 1: Project Foundation

### 1.1 Project Configuration

**File: `pyproject.toml`**

Set up Poetry project with dependencies:
- Flask 3.x
- Pydantic 2.x with pydantic-settings
- SpectTree 1.x
- dependency-injector 4.x
- prometheus-flask-exporter
- waitress
- pytest, pytest-cov (dev)
- ruff, mypy (dev)

**File: `.env.example`**

Document environment variables:
```
ESP32_CONFIGS_DIR=/data/esp32-configs
CORS_ORIGINS=["http://localhost:3000"]
DEBUG=true
```

### 1.2 Application Configuration

**File: `app/config.py`**

Pydantic Settings class:
- `ESP32_CONFIGS_DIR`: Path to config files (required)
- `CORS_ORIGINS`: List of allowed origins
- `DEBUG`: Debug mode flag
- `SECRET_KEY`: Flask secret key

**Startup behavior:** The application does NOT auto-create `ESP32_CONFIGS_DIR`. If the directory does not exist, the health endpoint will report unhealthy and operations will fail with appropriate errors. This is intentional - the directory should be provisioned by the deployment (e.g., CephFS mount).

### 1.3 Application Factory

**File: `app/__init__.py`**

Create Flask application factory (`create_app`):
1. Load configuration from environment
2. Configure CORS
3. Initialize SpectTree for OpenAPI
4. Initialize service container
5. Wire container to API modules
6. Register blueprints
7. Register error handlers
8. Set up request teardown

**File: `app/app.py`**

Custom Flask class with container reference (pattern from ElectronicsInventory).

**File: `run.py`**

Entry point for development server.

---

## Phase 2: Core Infrastructure

### 2.1 Exception Handling

**File: `app/exceptions.py`**

Define custom exceptions:
- `BusinessLogicException` - Base exception with message and error code
- `RecordNotFoundException` - Config file not found
- `InvalidOperationException` - Invalid operation (e.g., invalid MAC format)
- `ValidationException` - Content validation failed (invalid JSON)

### 2.2 Error Handling Utilities

**File: `app/utils/error_handling.py`**

- `@handle_api_errors` decorator - catches exceptions and returns consistent JSON error responses
- Error response schema with: `error`, `code`, `details`, `correlationId`

### 2.3 SpectTree Configuration

**File: `app/utils/spectree_config.py`**

Configure SpectTree:
- Title: "IoT Support API"
- Path: `/api/docs`
- Validation error status: 400

---

## Phase 3: Service Layer

### 3.1 Service Container

**File: `app/services/container.py`**

Dependency injection container:
- `config` provider - `providers.Singleton(Settings)` - Application settings
- `config_service` provider - `providers.Factory(ConfigService, config_dir=...)` - New instance per request for thread safety
- `metrics_service` provider - `providers.Singleton(MetricsService)` - Single instance for app lifetime

### 3.2 Configuration Service

**File: `app/services/config_service.py`**

`ConfigService` class with methods:

```python
class ConfigService:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir

    def list_configs(self) -> list[ConfigSummary]:
        """List all config files with summary data."""
        # Read directory, parse each JSON, extract summary fields
        # Skip files that fail JSON parsing (log warning, don't fail entire list)
        # Return list sorted by filename

    def get_config(self, mac_address: str) -> ConfigDetail:
        """Get full config content by MAC address."""
        # Validate MAC format
        # Read and parse JSON file
        # Raise RecordNotFoundException if not found

    def save_config(self, mac_address: str, content: dict) -> ConfigDetail:
        """Create or update config (upsert)."""
        # Validate MAC format
        # Validate content is dict (already parsed JSON)
        # Write atomically: see "Atomic File Write Pattern" below
        # Return saved config

    def delete_config(self, mac_address: str) -> None:
        """Delete config by MAC address."""
        # Validate MAC format
        # Delete file
        # Raise RecordNotFoundException if not found

    @staticmethod
    def validate_mac_address(mac: str) -> bool:
        """Validate MAC is lowercase, hyphen-separated format."""
        # Pattern: ^[0-9a-f]{2}(-[0-9a-f]{2}){5}$
```

**Atomic File Write Pattern:**
```python
def _write_atomic(self, file_path: Path, content: dict) -> None:
    """Write file atomically using temp file + rename."""
    # Create temp file in SAME directory (required for atomic rename)
    temp_path = file_path.with_suffix('.tmp')
    try:
        with open(temp_path, 'w') as f:
            json.dump(content, f, indent=2)
        # os.replace() is atomic on POSIX and overwrites existing files
        os.replace(temp_path, file_path)
    finally:
        # Clean up temp file if rename failed
        if temp_path.exists():
            temp_path.unlink()
```

**Concurrency Model:**
- This is a homelab application with trusted users
- Concurrent writes to the same MAC address use "last write wins" semantics
- No file locking is implemented; this is acceptable for the expected usage pattern
- The atomic write pattern prevents corrupted files from partial writes

### 3.3 Metrics Service

**File: `app/services/metrics_service.py`**

`MetricsService` class (singleton, on-demand metrics only - no background threads):
- Counter: `iot_config_operations_total` (labels: operation, status)
- Gauge: `iot_config_files_count`
- Histogram: `iot_config_operation_duration_seconds`

Methods:
- `record_operation(operation, status, duration)` - Called by ConfigService after each operation
- `update_config_count(count)` - Called after save/delete to update gauge

**Note:** Unlike ElectronicsInventory, this service has no background polling thread since there's no database to query. All metrics are updated on-demand during API operations. No shutdown coordinator integration is needed.

---

## Phase 4: Schema Layer

### 4.1 Configuration Schemas

**File: `app/schemas/config.py`**

Pydantic models:

```python
class ConfigSummarySchema(BaseModel):
    """Summary for list endpoint."""
    mac_address: str = Field(..., description="Device MAC address (filename)")
    device_name: str | None = Field(None, description="Device name from config")
    device_entity_id: str | None = Field(None, description="Device entity ID")
    enable_ota: bool | None = Field(None, description="OTA update enabled")

class ConfigListResponseSchema(BaseModel):
    """Response for list endpoint."""
    configs: list[ConfigSummarySchema]
    count: int

class ConfigDetailSchema(BaseModel):
    """Full config detail."""
    mac_address: str
    content: dict  # Raw JSON content

class ConfigSaveRequestSchema(BaseModel):
    """Request for save endpoint."""
    content: dict = Field(..., description="JSON configuration content")

class ConfigResponseSchema(BaseModel):
    """Response for get/save endpoints."""
    mac_address: str
    device_name: str | None
    device_entity_id: str | None
    enable_ota: bool | None
    content: dict
```

### 4.2 Error Schema

**File: `app/schemas/error.py`**

```python
class ErrorResponseSchema(BaseModel):
    """Standard error response."""
    error: str
    code: str
    details: dict | None = None
    correlation_id: str
```

---

## Phase 5: API Layer

### 5.1 API Blueprint Registration

**File: `app/api/__init__.py`**

Register all blueprints under `/api` prefix:
- `configs_bp` at `/configs`
- `health_bp` at `/health`
- `metrics_bp` at `/metrics` (at root, not under /api)

### 5.2 Configuration Endpoints

**File: `app/api/configs.py`**

```python
configs_bp = Blueprint("configs", __name__, url_prefix="/configs")

# GET /api/configs
# List all configurations
@configs_bp.route("", methods=["GET"])
@api.validate(resp=SpectreeResponse(HTTP_200=ConfigListResponseSchema))
@handle_api_errors
@inject
def list_configs(config_service=Provide[ServiceContainer.config_service]):
    ...

# GET /api/configs/<mac_address>
# Get single configuration
@configs_bp.route("/<mac_address>", methods=["GET"])
@api.validate(resp=SpectreeResponse(HTTP_200=ConfigResponseSchema, HTTP_404=ErrorResponseSchema))
@handle_api_errors
@inject
def get_config(mac_address: str, config_service=Provide[ServiceContainer.config_service]):
    ...

# PUT /api/configs/<mac_address>
# Create or update configuration
@configs_bp.route("/<mac_address>", methods=["PUT"])
@api.validate(json=ConfigSaveRequestSchema, resp=SpectreeResponse(HTTP_200=ConfigResponseSchema, HTTP_400=ErrorResponseSchema))
@handle_api_errors
@inject
def save_config(mac_address: str, config_service=Provide[ServiceContainer.config_service]):
    ...

# DELETE /api/configs/<mac_address>
# Delete configuration
@configs_bp.route("/<mac_address>", methods=["DELETE"])
@api.validate(resp=SpectreeResponse(HTTP_204=None, HTTP_404=ErrorResponseSchema))
@handle_api_errors
@inject
def delete_config(mac_address: str, config_service=Provide[ServiceContainer.config_service]):
    ...
```

### 5.3 Health Endpoint

**File: `app/api/health.py`**

```python
health_bp = Blueprint("health", __name__, url_prefix="/health")

# GET /api/health
@health_bp.route("", methods=["GET"])
def health_check():
    # Check config directory is accessible
    # Return {"status": "healthy"} or {"status": "unhealthy", "reason": "..."}
```

### 5.4 Metrics Endpoint

**File: `app/api/metrics.py`**

```python
metrics_bp = Blueprint("metrics", __name__)

# GET /metrics
@metrics_bp.route("/metrics", methods=["GET"])
def metrics():
    # Return Prometheus metrics in text format
```

---

## Phase 6: Testing

### 6.1 Test Configuration

**File: `tests/conftest.py`**

Fixtures:
- `app` - Flask test application with temp config directory
- `client` - Flask test client
- `config_dir` - Temporary directory for test configs
- `container` - Service container
- `sample_config` - Factory for creating test config files

### 6.2 Service Tests

**File: `tests/services/test_config_service.py`**

Test cases for `ConfigService`:
- `test_list_configs_empty` - Empty directory
- `test_list_configs_multiple` - Multiple config files
- `test_list_configs_extracts_fields` - Correct field extraction
- `test_list_configs_handles_missing_fields` - Returns None for missing fields
- `test_list_configs_skips_invalid_json` - Invalid JSON files are skipped, not causing failure
- `test_get_config_success` - Retrieve existing config
- `test_get_config_not_found` - Raises RecordNotFoundException
- `test_get_config_invalid_mac` - Raises InvalidOperationException
- `test_save_config_create` - Create new config
- `test_save_config_update` - Update existing config
- `test_save_config_invalid_mac` - Raises InvalidOperationException
- `test_save_config_atomic_write` - Temp file cleanup on failure
- `test_delete_config_success` - Delete existing config
- `test_delete_config_not_found` - Raises RecordNotFoundException
- `test_validate_mac_address_valid` - Various valid formats
- `test_validate_mac_address_invalid` - Invalid formats rejected

### 6.3 API Tests

**File: `tests/api/test_configs.py`**

Test cases:
- `test_list_configs_empty` - 200 with empty list
- `test_list_configs_returns_summary` - Correct response format
- `test_get_config_success` - 200 with full content
- `test_get_config_not_found` - 404 response
- `test_get_config_invalid_mac` - 400 response
- `test_save_config_create` - 200 on create
- `test_save_config_update` - 200 on update
- `test_save_config_invalid_mac` - 400 response
- `test_save_config_invalid_json` - 400 response
- `test_delete_config_success` - 204 response
- `test_delete_config_not_found` - 404 response

**File: `tests/api/test_health.py`**

- `test_health_check_healthy` - 200 when config dir accessible
- `test_health_check_unhealthy` - 503 when config dir inaccessible

---

## Implementation Order

Recommended implementation sequence:

1. **Project setup** - pyproject.toml, basic app structure
2. **Configuration** - app/config.py, environment handling
3. **Exceptions** - app/exceptions.py
4. **Schemas** - app/schemas/*.py
5. **Config service** - app/services/config_service.py with tests
6. **Error handling** - app/utils/error_handling.py
7. **API endpoints** - app/api/configs.py with tests
8. **Health endpoint** - app/api/health.py with tests
9. **Metrics** - metrics_service.py, app/api/metrics.py
10. **Application factory** - app/__init__.py, wiring everything together
11. **Integration testing** - End-to-end tests

---

## File Summary

```
backend/
├── app/
│   ├── __init__.py          # Application factory
│   ├── app.py               # Custom Flask class
│   ├── config.py            # Pydantic settings
│   ├── exceptions.py        # Custom exceptions
│   ├── api/
│   │   ├── __init__.py      # Blueprint registration
│   │   ├── configs.py       # Config CRUD endpoints
│   │   ├── health.py        # Health check endpoint
│   │   └── metrics.py       # Prometheus metrics endpoint
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── config.py        # Config request/response schemas
│   │   └── error.py         # Error response schema
│   ├── services/
│   │   ├── __init__.py
│   │   ├── container.py     # DI container
│   │   ├── config_service.py # Config file operations
│   │   └── metrics_service.py # Prometheus metrics
│   └── utils/
│       ├── __init__.py
│       ├── error_handling.py # Error handler decorator
│       └── spectree_config.py # OpenAPI configuration
├── tests/
│   ├── conftest.py          # Test fixtures
│   ├── api/
│   │   ├── test_configs.py  # API endpoint tests
│   │   └── test_health.py   # Health endpoint tests
│   └── services/
│       └── test_config_service.py # Service tests
├── pyproject.toml           # Project dependencies
├── run.py                   # Entry point
└── .env.example             # Environment template
```

---

## Acceptance Criteria

The implementation is complete when:

1. All endpoints work as documented in the product brief
2. All test cases pass with >90% coverage
3. `ruff check .` passes with no errors
4. `mypy .` passes with no errors
5. OpenAPI docs are accessible at `/api/docs`
6. Prometheus metrics are accessible at `/metrics`
7. Health endpoint returns appropriate status
