# Device Provisioning MDM - Change Brief

## Overview

Transform the IoT Support backend from a simple configuration file manager into a full Mobile Device Management (MDM) application supporting device provisioning, fleet management, and automated secret rotation.

## Core Changes

### 1. Replace MAC Address with Device Key

- Remove all MAC address usage from the application
- Generate unique 8-character device keys (`[a-z0-9]`) as device identifiers
- Device keys are baked into provisioning packages and used by devices to identify themselves

### 2. New Data Model

**DeviceModel** (hardware type, one-to-many with devices):
- `id`: Surrogate primary key
- `code`: Unique, immutable identifier (`[a-z0-9_]+`)
- `name`: Human-readable name
- `firmware_version`: Extracted from uploaded firmware binary (ESP32 AppInfo)
- Timestamps

**Device**:
- `id`: Surrogate primary key
- `key`: Unique 8-character identifier (`[a-z0-9]`)
- `device_model_id`: FK to DeviceModel (required)
- `config`: JSON configuration content (required)
- `rotation_state`: Enum (OK, QUEUED, PENDING, TIMEOUT)
- `secret_created_at`: When current Keycloak secret was created
- `last_rotation_attempt_at`: When MQTT rotation message was last sent
- `last_rotation_completed_at`: When rotation last succeeded
- Timestamps

Firmware stored on filesystem as `firmware-<model_code>.bin`.

### 3. Keycloak Integration for Device Identity

Each device is registered as a Keycloak client:
- Client ID format: `iotdevice-<model_code>-<device_key>`
- Confidential client with service account enabled
- Assigned `iotdevice` role

Backend uses a service account (`iotsupport-admin`) with `manage-clients` permission to:
- Create clients during device provisioning
- Regenerate secrets during rotation
- Delete clients when devices are removed

### 4. Device Provisioning Flow

1. Admin creates device via API (provides model code + JSON config)
2. Backend generates 8-char device key
3. Backend creates Keycloak client `iotdevice-<model>-<key>`
4. Backend returns provisioning package as downloadable `.bin` file (JSON content)

**Provisioning Package Contents**:
- Device key
- Keycloak client ID
- Keycloak client secret
- Token endpoint URL (from `OIDC_TOKEN_URL` env var)
- Backend base URL (from `BASEURL` env var)
- MQTT URL (from `MQTT_URL` env var)
- WiFi SSID and password (from `WIFI_SSID`, `WIFI_PASSWORD` env vars)

### 5. Device API (`/iot` blueprint)

Endpoints authenticated via JWT (device extracts key from client ID in token):

- `GET /iot/config` - Returns raw JSON config for the authenticated device
- `GET /iot/firmware` - Returns firmware binary for the device's model
- `GET /iot/provisioning` - Returns new provisioning data during rotation (generates new Keycloak secret)

### 6. Admin API Changes

**Remove**: `/api/configs` endpoints (replaced by devices)

**Add Device Models** (`/api/device-models`):
- `POST /api/device-models` - Create model (code, name)
- `GET /api/device-models` - List models
- `GET /api/device-models/<id>` - Get model details
- `PUT /api/device-models/<id>` - Update name
- `DELETE /api/device-models/<id>` - Delete (only if no devices)
- `POST /api/device-models/<id>/firmware` - Upload firmware (extracts version via ESP32 AppInfo)
- `GET /api/device-models/<id>/firmware` - Download firmware

**Add Devices** (`/api/devices`):
- `POST /api/devices` - Create device (model_id, config JSON) → creates Keycloak client
- `GET /api/devices` - List devices with rotation status
- `GET /api/devices/<id>` - Get device details
- `PUT /api/devices/<id>` - Update config
- `DELETE /api/devices/<id>` - Delete device + Keycloak client
- `GET /api/devices/<id>/provisioning` - Re-download provisioning package
- `POST /api/devices/<id>/rotate` - Manually trigger rotation for one device

**Add Rotation Management** (`/api/rotation`):
- `GET /api/rotation/status` - Fleet-wide stats (counts by state, timing metrics)
- `POST /api/rotation/trigger` - Manually trigger fleet-wide rotation

### 7. Automated Secret Rotation

**Rotation States**: OK, QUEUED, PENDING, TIMEOUT

**Hourly Job**:
1. Check if monthly CRON schedule (`ROTATION_CRON`) has passed since last run → set all OK devices to QUEUED
2. Check PENDING devices: if timed out (`ROTATION_TIMEOUT_SECONDS`) → restore old secret in Keycloak, set TIMEOUT
3. If any PENDING device is not timed out → exit (rotation in progress)
4. Find device to rotate: first QUEUED (oldest `secret_created_at`), else first TIMEOUT
5. Cache current secret, generate new secret in Keycloak
6. Publish MQTT to `iotsupport/<client_id>/rotation` (fire-and-forget, no retention)
7. Set device to PENDING, record `last_rotation_attempt_at`

**Device Rotation Flow**:
1. Device receives MQTT message
2. Device calls `GET /iot/provisioning` → backend returns new provisioning JSON (with new secret already generated)
3. Device writes to partition, reboots
4. Device calls `GET /iot/config` with new JWT → backend verifies JWT created after rotation, marks rotation complete (OK), records `last_rotation_completed_at`

**Timeout Handling**: If device doesn't complete within `ROTATION_TIMEOUT_SECONDS` (default 300s), restore old secret in Keycloak, set state to TIMEOUT.

**Metrics**: Track time from MQTT → provisioning call, and provisioning call → config call.

### 8. Firmware Version Extraction

Parse ESP32 firmware binary to extract version using ESP-IDF AppInfo structure:
- Offset: 32 bytes (24-byte image header + 8-byte segment header)
- Magic word: `0xABCD5432`
- Structure size: 256 bytes
- Version field: 32 chars at offset 16 within structure

### 9. New Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OIDC_TOKEN_URL` | Full token endpoint URL (not Keycloak-specific) | Required |
| `KEYCLOAK_ADMIN_URL` | Keycloak admin API base URL | Required |
| `KEYCLOAK_REALM` | Keycloak realm name | Required |
| `KEYCLOAK_ADMIN_CLIENT_ID` | Service account client ID | Required |
| `KEYCLOAK_ADMIN_CLIENT_SECRET` | Service account secret | Required |
| `WIFI_SSID` | WiFi network name for provisioning | Required |
| `WIFI_PASSWORD` | WiFi password for provisioning | Required |
| `ROTATION_CRON` | Rotation schedule | `0 8 * * 6#1` (first Sat 8am) |
| `ROTATION_TIMEOUT_SECONDS` | Per-device rotation timeout | `300` |
| `ROTATION_RETRY_INTERVAL_SECONDS` | Retry job interval | `3600` |

### 10. Dashboard Support (Backend Only)

Provide API endpoints for frontend rotation dashboard:
- Fleet-wide status: counts by rotation state
- Per-device details: state, timing, secret age
- Visual grouping: OK (green), late (orange, within half rotation interval), very late (red)

Frontend implementation documented in `frontend_impact.md`.

## Out of Scope

- Bluetooth provisioning
- Multiple firmware versions per model (rollback)
- Automatic device expiration/revocation
- Frontend implementation (backend APIs only)
