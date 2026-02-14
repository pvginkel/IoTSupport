# Development Guidelines - Backend

This document defines the code architecture, patterns, and testing requirements for the backend project. Follow these guidelines to ensure consistency and maintainability.

## Project Architecture

This Flask backend implements an **IoT support application** as described in `docs/product_brief.md`. The architecture follows a layered pattern with clear separation of concerns:

```
app/
├── api/          # HTTP endpoints and request handling
├── services/     # Business logic layer
├── schemas/      # Pydantic request/response schemas
└── utils/        # Shared utilities and error handling
```

## Sandbox Environment

- Backend and frontend worktrees are bind-mounted into `/work` inside the container.
- Each repository’s `.git` directory is mapped read-only, so staging or committing must happen outside the sandbox.
- The container includes the standard project toolchain; request Dockerfile updates if more tooling is needed.
- With Git safeguarded externally, no additional safety guardrails are enforced beyond the project’s own guidelines.

## Deprecation and Backwards Compatibility

This app follows the BFF pattern—the backend serves only this frontend. Changes to the backend are immediately accompanied by frontend updates, so:

- Make breaking changes freely; no backwards compatibility needed.
- Remove replaced/unused code and endpoints entirely (no deprecation markers).
- Don't include migration hints in error messages.
- Document frontend impact in `docs/features/<FEATURE>/frontend_impact.md` when the frontend dev needs update instructions.

## Code Organization Patterns

### 1. API Layer (`app/api/`)

API endpoints handle HTTP concerns only - no business logic.

**Pattern:**
- Each resource gets its own module (e.g., `parts.py`, `boxes.py`)
- Use Flask blueprints with URL prefixes
- Validate requests with Pydantic schemas via `@api.validate`
- Delegate all business logic to service classes
- Handle errors with `@handle_api_errors` decorator
- Return data using response schemas

**Example structure:**
```python
@parts_bp.route("", methods=["POST"])
@api.validate(json=PartCreateSchema, resp=SpectreeResponse(HTTP_201=PartResponseSchema))
@handle_api_errors
@inject
def create_part(part_service=Provide[ServiceContainer.part_service]):
    data = PartCreateSchema.model_validate(request.get_json())
    part = part_service.create_part(**data.model_dump())
    return PartResponseSchema.model_validate(part).model_dump(), 201
```

### 2. Service Layer (`app/services/`)

Services contain all business logic and database operations using instance-based dependency injection.

**Requirements:**
- Services are instance-based classes. Inherit from `BaseService` when a database session is required; use a simple class when no database access is needed.
- For services inheriting `BaseService`, inject the database session via the constructor (stored as `self.db`).
- Return SQLAlchemy model instances, not dicts
- Raise typed exceptions (`RecordNotFoundException`, `InvalidOperationException`)
- No HTTP-specific code (no Flask imports)
- Services can depend on other services via dependency injection

**Example pattern:**
```python
class PartService(BaseService):
    def create_part(self, description: str, **kwargs) -> Part:
        # Validation and business logic here
        part = Part(description=description, **kwargs)
        self.db.add(part)
        self.db.flush()  # Get ID immediately if needed
        return part
```

### 3. Model Layer (`app/models/`)

SQLAlchemy models represent database entities.

**Requirements:**
- One file per model (e.g., `part.py`, `box.py`)
- Use typed annotations with `Mapped[Type]`
- Include relationships with proper lazy loading
- Add `__repr__` methods for debugging
- Use proper cascade settings for relationships
- Include timestamps (`created_at`, `updated_at`) where appropriate
- Follow the numbering scheme for schema migration files

### 4. Schema Layer (`app/schemas/`)

Pydantic schemas for request/response validation.

**Naming conventions:**
- `*CreateSchema` - Creating new resources
- `*UpdateSchema` - Updating existing resources  
- `*ResponseSchema` - Full API responses with relationships
- `*ListSchema` - Lightweight listings

**Requirements:**
- Use `Field()` with descriptions and examples
- Set `model_config = ConfigDict(from_attributes=True)` for ORM integration
- For calculated/derived properties: define them as `@property` on the SQLAlchemy model, then declare a regular `Field()` in the schema. Pydantic's `from_attributes=True` will read model properties automatically. Avoid `@computed_field` in schemas as it doesn't integrate well with OpenAPI/SpectTree.
- Include proper type hints and optional fields

## File Placement Rules

### New Features
When implementing new features:

1. **Models first** - Create SQLAlchemy model in `app/models/`
2. **Services** - Business logic in `app/services/` 
3. **Schemas** - Request/response validation in `app/schemas/`
4. **API endpoints** - HTTP layer in `app/api/`
5. **Database migration** - Alembic migration in `alembic/versions/`

### Utilities
- Error handling: `app/utils/error_handling.py`
- Shared validation: `app/utils/` 
- Configuration: `app/config.py`

## Testing Requirements (Definition of Done)

**Every piece of code must have comprehensive tests.** No feature is complete without tests.

### Test Organization
- Tests mirror the `app/` structure in `tests/`
- Test files named `test_{module_name}.py`
- Test classes named `TestServiceName` or `TestApiEndpoint`

### Service Testing
**Required test coverage for services:**
- ✅ All public methods
- ✅ Success paths with various input combinations  
- ✅ Error conditions and exception handling
- ✅ Edge cases (empty data, boundary conditions)
- ✅ Database constraints and validation

**Example service test structure:**
```python
class TestPartService:
    def test_create_part_minimal(self, app: Flask, session: Session, container: ServiceContainer):
        # Get service instance from container
        service = container.part_service()
        # Test creating with minimum required fields
        
    def test_create_part_full_data(self, app: Flask, session: Session, container: ServiceContainer):
        # Get service instance from container
        service = container.part_service()
        # Test creating with all fields populated
        
    def test_get_part_nonexistent(self, app: Flask, session: Session, container: ServiceContainer):
        # Test error handling
        service = container.part_service()
        with pytest.raises(RecordNotFoundException):
            service.get_part("INVALID")
```

### API Testing
**Required test coverage for APIs:**
- ✅ All HTTP endpoints and methods
- ✅ Request validation (invalid payloads, missing fields)
- ✅ Response format validation
- ✅ HTTP status codes
- ✅ Error responses

### Database Testing
- ✅ Model constraints and relationships
- ✅ Cascade behavior
- ✅ Data integrity

### Readability Comments
- Add short “guidepost” comments in non-trivial functions to outline the flow or highlight invariants.
- Keep existing explanatory comments unless they are clearly wrong; prefer updating over deleting.
- Focus on intent-level commentary (why/what) rather than narrating obvious statements (how).

## Code Quality Standards

### Linting and Formatting
Before committing, run:
```bash
poetry run ruff check .      # Linting
poetry run mypy .           # Type checking
poetry run pytest          # Full test suite
```

### Type Hints
- Use type hints for all function parameters and return types

### Time Measurements
- **NEVER use `time.time()` for measuring durations or relative time**
- Always use `time.perf_counter()` for duration measurements and performance timing
- `time.time()` is only appropriate for absolute timestamps (e.g., logging when something occurred)
- Example:
  ```python
  # WRONG - time.time() can be affected by system clock adjustments
  start = time.time()
  do_work()
  duration = time.time() - start
  
  # CORRECT - perf_counter() is monotonic and precise
  start = time.perf_counter()
  do_work()
  duration = time.perf_counter() - start
  ```

### Error Handling Philosophy
- **Fail fast and fail often** - Don't swallow exceptions or hide errors from users
- Use custom exceptions from `app.exceptions`
- Include context in error messages
- Let `@handle_api_errors` convert exceptions to HTTP responses
- **Avoid defensive try/catch blocks** that silently continue on errors
- If an operation fails, the user should know about it immediately

## Database Patterns

### Relationships
- Use `lazy="selectin"` for commonly accessed relationships
- Set proper cascade options: `cascade="all, delete-orphan"` for owned entities
- Use foreign key constraints

### Queries
- Build queries with `select()` statements
- Use `scalar_one_or_none()` for single results that may not exist
- Use `scalars().all()` for multiple results
- Always handle the case where records don't exist

### Enumerations
- Model domain enums in SQLAlchemy with `native_enum=False` (or explicit check constraints) so they are stored as text in the database.
- **Do not create PostgreSQL native ENUM types.** They make migrations and reset workflows brittle; prefer plain string columns with constrained values instead.

## S3 Storage Consistency

Every feature that stores data in both PostgreSQL and S3 **must** follow these two invariants. They guarantee that the database is always the source of truth and that the system never references S3 objects that don't exist.

### Golden Rule 1 — Creates: S3 before commit

When creating data, the S3 upload must succeed **before** the database transaction is committed.

```
1. flush()          — get the DB-generated ID (row is not yet visible to other transactions)
2. s3 upload        — use the ID / known key; if this fails the transaction rolls back automatically
3. commit()         — only now is the row visible; it is guaranteed to have a matching S3 object
```

A failed S3 upload aborts the request, the transaction rolls back, and no dangling DB row is created.

### Golden Rule 2 — Deletes: commit before S3

When deleting data, the database transaction must be committed **before** the S3 delete is initiated.

```
1. delete row + commit()   — the row is gone; no reader can reference the S3 object any more
2. s3 delete (best-effort) — log and swallow errors; an orphaned S3 object is harmless
```

A failed S3 delete leaves an orphan blob that is invisible to the application. This is acceptable and can be cleaned up out-of-band. The alternative (deleting S3 first) risks the DB still referencing a missing object.

### Corollary — Copies

When copying a resource (e.g., cloning an attachment), create and flush the new DB row first, then copy the S3 object within the same request. Surface any S3 failure as an `InvalidOperationException` so the transaction rolls back.

## Development Workflow

1. **Plan** - Understand requirements from `docs/product_brief.md`
2. **Model** - Design database schema and relationships
3. **Service** - Implement business logic with comprehensive error handling
4. **Test services** - Write thorough service tests first
5. **API** - Create HTTP endpoints that delegate to services  
6. **Test APIs** - Validate HTTP behavior and response formats
7. **Lint/Type check** - Ensure code quality standards
8. **Integration test** - Verify end-to-end functionality

## Key Project Concepts

Reference `docs/product_brief.md` for domain understanding:

- **Parts** have unique 4-character IDs and live in **Locations** within numbered **Boxes**
- **Inventory tracking** with quantity history
- **Projects** plan builds and track part requirements
- **Smart organization** suggests optimal part placement
- **Search** across all part attributes and documentation

## Prometheus Metrics Infrastructure

The application includes a comprehensive Prometheus metrics system for operational monitoring:

### Available Metrics Infrastructure
- **MetricsService** (`app/services/metrics_service.py`) - Central service for managing all metrics
- **`/metrics` endpoint** - Prometheus scraping endpoint via `app/api/metrics.py`
- **Background metric updates** - Automatic collection of inventory and system metrics

### Using Metrics in New Features
When implementing features that need operational visibility:

1. **Add metrics to MetricsService** - Define new Prometheus metrics (Gauges, Counters, Histograms)
2. **Update metrics in business logic** - Call `metrics_service` methods when events occur
3. **Use appropriate metric types**:
   - `Gauge` - Current state values (active connections, queue depth)
   - `Counter` - Cumulative totals (requests processed, errors)
   - `Histogram` - Duration measurements (request latency, processing time)

**Example pattern:**
```python
# In service method
self.metrics_service.record_operation_duration("operation_name", duration)
self.metrics_service.increment_counter("operation_total", labels={"status": "success"})
```

**Existing metrics include:**
- Inventory statistics (parts count, quantities, categories)
- Storage utilization (box usage percentages)
- Activity tracking (quantity changes, recent activity)
- AI analysis metrics (requests, tokens, costs, duration)
- System metrics (HTTP requests, response times, exceptions)

## Dependencies

- **Flask** - Web framework
- **Pydantic** - Request/response validation 
- **SpectTree** - OpenAPI documentation generation
- **pytest** - Testing framework
- **dependency-injector** - Dependency injection container
- **prometheus-flask-exporter** - Prometheus metrics integration

Focus on creating well-tested, maintainable code that follows these established patterns.

## Dependency Injection

### Service Container

The project uses `dependency-injector` to manage service dependencies through a centralized container (`app/services/container.py`):

```python
class ServiceContainer(containers.DeclarativeContainer):
    # Database session provider
    db_session = providers.Dependency(instance_of=Session)
    
    # Service providers
    part_service = providers.Factory(PartService, db=db_session)
    inventory_service = providers.Factory(
        InventoryService, 
        db=db_session,
        part_service=part_service  # Service dependency
    )
```

### Service Dependencies

Services that depend on other services receive them via constructor injection:

```python
class InventoryService(BaseService):
    def __init__(self, db: Session, part_service: PartService):
        super().__init__(db)
        self.part_service = part_service
```

Only use BaseService for factory services that use the database. Singletons need to implement the following pattern when they need database access:

```python
# db_session() returns a context local session (new if this is the first
# call in the context).
session = self.container.db_session()

try:
    # Do something with the session...

    session.commit()

except Exception:
    # Rollback the session on exception.
    session.rollback()
    raise

finally:
    # Important: reset the session in a finally block. This ensures that
    # the next call to container.db_session() creates a fresh session.
    self.container.db_session.reset()
```

### API Injection

API endpoints use the `@inject` decorator to receive services:

```python
from dependency_injector.wiring import Provide, inject
from app.services.container import ServiceContainer

@inject
def create_part(part_service=Provide[ServiceContainer.part_service]):
    # Use injected service instance
    return part_service.create_part(...)
```

### Container Wiring

The service container is wired to API modules in the application factory (`app/__init__.py`):

```python
# Initialize service container
container = ServiceContainer()
container.wire(modules=[
    'app.api.parts', 'app.api.boxes', 'app.api.inventory', 
    'app.api.types', 'app.api.testing'
])
```

## Graceful Shutdown Integration

Services with background threads or long-running operations must integrate with the graceful shutdown coordinator to ensure clean shutdowns during Kubernetes deployments.

### When to Integrate

Services need shutdown integration if they:
- Run background threads (cleanup, metrics updates, etc.)
- Have long-running operations that should complete before shutdown
- Need to stop accepting new requests during shutdown

### Integration Patterns

**Constructor pattern:**
```python
def __init__(self, shutdown_coordinator: ShutdownCoordinatorProtocol, ...):
    self.shutdown_coordinator = shutdown_coordinator
    # Register for notifications and/or waiters
```

**Two registration types:**

1. **Lifetime notifications** (immediate, non-blocking):
   ```python
   shutdown_coordinator.register_lifetime_notification(self._on_lifetime_event)
   
   def _on_lifetime_event(self, event: LifetimeEvent) -> None:
       match event:
           case LifetimeEvent.PREPARE_SHUTDOWN:
               # Stop accepting new work, set shutdown flags
           case LifetimeEvent.SHUTDOWN: 
               # Final cleanup
   ```

2. **Shutdown waiters** (block shutdown until complete):
   ```python
   shutdown_coordinator.register_shutdown_waiter("ServiceName", self._wait_for_completion)
   
   def _wait_for_completion(self, timeout: float) -> bool:
       # Wait for operations to complete within timeout
       # Return True if ready, False if timeout
   ```

### Examples

- **TaskService**: Uses both notification (stop accepting tasks) and waiter (wait for task completion)
- **MetricsService**: Uses only notification (stop background thread, record shutdown metrics)
- **TempFileManager**: Uses only notification (stop cleanup thread)

### Testing

- Use `StubShutdownCoordinator` for unit tests (dependency injection only)
- Use `TestShutdownCoordinator` for integration tests (simulates shutdown behavior)
- Both available in `tests.testing_utils`

## Command Templates

The repository includes command templates for specific development workflows:

- When writing a product brief: @docs/commands/create_brief.md
- When planning a new feature: @docs/commands/plan_feature.md
- When reviewing a plan: @docs/commands/review_plan.md
- When doing code review: @docs/commands/code_review.md
- When planning or implementing a new feature, reference the product brief at @docs/product_brief.md

Use these files when the user asks you to perform the applicable action.
