# Change Brief: Database Configuration Storage

## Summary

Migrate device configuration storage from filesystem-based JSON files to PostgreSQL database storage. This involves copying the complete database infrastructure from the ElectronicsInventory backend and adapting it for this application.

## Functional Changes

### Database Infrastructure

Copy the following from `/work/ElectronicsInventory/backend`:
- Flask-SQLAlchemy setup and extensions
- Alembic migration framework
- Database session management with context-local sessions
- BaseService class for services requiring database access
- ServiceContainer updates for dependency injection with database sessions
- Domain exceptions (RecordNotFoundException, InvalidOperationException, etc.)
- Database utility functions (init, upgrade, health checks)
- Test fixtures for database testing with SQLite
- Scripts for database creation, upgrade, and test data loading

### Data Model

Create a `Config` model with the following fields:
- `id`: Integer, primary key, auto-increment (surrogate key)
- `mac_address`: String, unique, not null, colon-separated format (e.g., `aa:bb:cc:dd:ee:ff`)
- `device_name`: String, nullable (extracted from JSON content)
- `device_entity_id`: String, nullable (extracted from JSON content)
- `enable_ota`: Boolean, nullable (extracted from JSON content)
- `content`: Text, not null (full JSON configuration as text)
- `created_at`: Timestamp with server default
- `updated_at`: Timestamp with server default and on-update

### API Changes

Update routes to use surrogate IDs instead of MAC addresses:

| Current Route | New Route | Method | Description |
|--------------|-----------|--------|-------------|
| `GET /api/configs` | `GET /api/configs` | GET | List all configs (returns summaries with IDs) |
| `PUT /api/configs/<mac>.json` | `POST /api/configs` | POST | Create new config (mac_address + content in body) |
| - | `GET /api/configs/<id>` | GET | Get config by ID |
| - | `PUT /api/configs/<id>` | PUT | Update config by ID |
| `DELETE /api/configs/<mac>.json` | `DELETE /api/configs/<id>` | DELETE | Delete config by ID |
| `GET /api/configs/<mac>.json` | `GET /api/configs/<mac>.json` | GET | Raw config for ESP32 device (MAC lookup, kept) |

### MAC Address Format

Change MAC address format from dash-separated (`aa-bb-cc-dd-ee-ff`) to colon-separated (`aa:bb:cc:dd:ee:ff`) throughout the application.

### Field Extraction

On save (create/update), extract the following optional fields from the JSON content:
- `device_name`
- `device_entity_id`
- `enable_ota`

The MAC address is provided as a top-level field in the request body, not extracted from content.

### MQTT Integration

Maintain existing MQTT publishing behavior when configurations change.

### Test Data

Create sample test JSON files for loading via database scripts.

## Out of Scope

- Assets endpoint (`/api/assets`) - remains file-based
- Data migration from existing files - assume clean installation
- ShutdownCoordinator - not needed for database implementation

## Removals

- `ESP32_CONFIGS_DIR` environment variable and configuration
- Filesystem-based configuration storage in ConfigService
- All file I/O operations for configuration management
