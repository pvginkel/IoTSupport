# Device Provisioning MDM - Frontend Update

## Overview

Update the frontend to support the new MDM (Mobile Device Management) backend that replaces the MAC-address-based config system with a device/device-model architecture featuring automated secret rotation.

## Context

The backend has been overhauled to introduce:
- **Device Models**: Hardware type definitions with optional JSON Schema for config validation
- **Devices**: Now identified by auto-generated 8-character keys (not MAC addresses), linked to a device model
- **Secret Rotation**: Automated credential rotation with health status tracking (healthy/warning/critical)
- **Keycloak Integration**: Each device has a Keycloak client for authentication

The backend API is ready. The frontend is currently broken because it still references the old `/api/configs` endpoints and data model.

## Scope of Changes

### 1. Navigation Updates
Add three top-level navigation items:
- Devices (existing, needs update)
- Device Models (new)
- Rotation (new dashboard page)

### 2. Device Models Management (New)
- **List page**: Show code, name, has_config_schema indicator, device_count, firmware_version (read-only)
- **Create form**: code (immutable after creation, pattern `[a-z0-9_]+`), name, config_schema (JSON editor)
- **Edit form**: name, config_schema (code is read-only)
- **Delete**: Only allowed if device_count = 0

The config_schema field should use a Monaco JSON editor with JSON Schema meta-validation (validate that the entered schema is itself a valid JSON Schema).

### 3. Devices Management (Update Existing)
Replace the MAC-address-based system:
- **List page**: Show key (8-char), device_name, device_entity_id, enable_ota, model name, rotation_state badge
- **Create form**:
  - Model selector dropdown (required)
  - JSON config editor with schema-based validation and autocomplete (if model has config_schema)
  - No MAC address input (key is auto-generated)
- **Edit form**:
  - Key and model displayed read-only
  - JSON config editor with schema validation
  - Provisioning download button
- **Delete**: Standard confirmation

### 4. Rotation Dashboard (New)
Dedicated page showing fleet health status:
- Summary counts (healthy, warning, critical) with colored indicators
- Device lists grouped by health status
- Each device shows: key, device_name, model_code, rotation_state, days_since_rotation
- Fleet-wide "Trigger Rotation" button
- Link to pending device if rotation in progress

### 5. Test Infrastructure
- Update test factory to use new `/api/devices` endpoints
- Add test factory for device models
- Update Playwright specs for new flows

## API Endpoints

### Device Models
- `GET /api/device-models` - List all models
- `POST /api/device-models` - Create model `{ code, name, config_schema? }`
- `GET /api/device-models/{id}` - Get model (includes parsed config_schema)
- `PUT /api/device-models/{id}` - Update `{ name?, config_schema? }`
- `DELETE /api/device-models/{id}` - Delete (fails if has devices)

### Devices
- `GET /api/devices` - List devices
- `POST /api/devices` - Create `{ device_model_id, config }`
- `GET /api/devices/{id}` - Get device (includes embedded model info with config_schema)
- `PUT /api/devices/{id}` - Update `{ config }`
- `DELETE /api/devices/{id}` - Delete device
- `GET /api/devices/{id}/provisioning` - Download provisioning .bin file
- `POST /api/devices/{id}/rotate` - Trigger single device rotation

### Rotation
- `GET /api/rotation/dashboard` - Get devices grouped by health (healthy/warning/critical)
- `GET /api/rotation/status` - Get rotation status and scheduling info
- `POST /api/rotation/trigger` - Trigger fleet-wide rotation

## Technical Notes

- Monaco Editor supports JSON Schema validation via `monaco.languages.json.jsonDefaults.setDiagnosticsOptions()` - use this for both config editing (with model's schema) and config_schema editing (with JSON Schema meta-schema)
- The backend extracts `device_name`, `device_entity_id`, `enable_ota` from the config JSON for list display
- Rotation states: OK (green), QUEUED (yellow), PENDING (blue), TIMEOUT (red)
- Dashboard health categories: healthy (green), warning (orange), critical (red)

## Out of Scope

- Firmware upload UI (pipeline only)
- IoT device endpoints (`/iot/*`) - these are for device consumption, not admin UI
