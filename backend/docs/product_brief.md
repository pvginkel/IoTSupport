# IoT Support Backend - Product Brief

## Project Overview

The IoT Support Backend is a REST API for managing ESP32-based IoT devices in a homelab environment. It provides device lifecycle management including provisioning, configuration, firmware distribution, and automatic credential rotation.

The application uses a PostgreSQL database to store device metadata, Keycloak for device authentication (machine-to-machine), and the filesystem for firmware binaries.

## Target Audience

- Homelab administrators managing a fleet of ESP32 IoT devices
- Users in trusted network environments
- Expected scale: up to 200 devices

## Primary Benefits and Features

### Device Management

1. **Device Models** - Hardware type definitions with:
   - Unique code identifier (e.g., `tempsensor`, `relay_4ch`)
   - Human-readable name
   - Firmware binary storage and version tracking

2. **Device Provisioning** - Individual device management:
   - Auto-generated 8-character device keys
   - JSON configuration per device
   - Keycloak OAuth2 client creation/deletion
   - Provisioning package download (JSON with credentials, URLs, WiFi config)

3. **Device Authentication** - M2M authentication via Keycloak:
   - Device-specific client credentials
   - JWT token validation for device endpoints
   - Separate /iot blueprint for device-facing APIs

### Credential Rotation

Automatic rotation of device OAuth2 credentials:

1. **State Machine** - Each device has a rotation state:
   - `OK` - Normal operation, credentials valid
   - `QUEUED` - Scheduled for rotation
   - `PENDING` - Rotation in progress, waiting for device acknowledgment
   - `TIMEOUT` - Device did not acknowledge rotation, will retry

2. **Fleet-Wide Scheduling** - CRON-based rotation schedule:
   - Configurable via `ROTATION_CRON` (default: first Saturday of month at 8am)
   - Kubernetes CronJob invokes `python -m app.cli rotation-job`
   - Rotates one device at a time to limit blast radius

3. **Timeout Handling** - Graceful failure recovery:
   - Configurable timeout (default: 300 seconds)
   - Old secret cached and restored on timeout
   - Failed devices moved to TIMEOUT state and retried later

4. **MQTT Notifications** - Real-time rotation triggers:
   - Publishes to `iotsupport/<client_id>/rotation`
   - Device fetches new credentials on notification

### Device-Facing API (/iot)

Authenticated endpoints for devices:

- `GET /iot/config` - Retrieve device configuration
- `GET /iot/firmware` - Download firmware binary
- `GET /iot/provisioning` - Get provisioning package (config + secrets)

### Admin API (/api)

Management endpoints for administrators:

- **Device Models**: CRUD + firmware upload/download
- **Devices**: CRUD + provisioning download + rotation trigger
- **Rotation**: Status overview + fleet-wide trigger

### Operational Features

- **Health Endpoint** - Kubernetes liveness/readiness probe at `/api/health`
- **Prometheus Metrics** - Operational metrics at `/metrics`
- **OpenAPI Documentation** - Auto-generated API docs at `/api/docs`

## Technology and Architecture

### Stack

- **Python 3.12** with Flask web framework
- **PostgreSQL** for device and model data
- **Keycloak** for device OAuth2 clients
- **Pydantic** for request/response validation
- **SpectTree** for OpenAPI documentation
- **dependency-injector** for dependency injection
- **croniter** for CRON schedule parsing
- **Fernet** for encrypting cached secrets
- **paho-mqtt** for MQTT notifications

### Architecture

```
+-----------------------------------------------------------+
|                      Flask App                             |
+-----------------------------------------------------------+
|  API Layer (app/api/)                                      |
|  - device_models.py: Device model CRUD + firmware         |
|  - devices.py: Device CRUD + provisioning                 |
|  - rotation.py: Rotation status + fleet trigger           |
|  - iot.py: Device-authenticated endpoints                 |
|  - health.py, metrics.py, auth.py, assets.py              |
+-----------------------------------------------------------+
|  Service Layer (app/services/)                             |
|  - device_model_service.py: Device model business logic   |
|  - device_service.py: Device lifecycle management         |
|  - rotation_service.py: Rotation state machine            |
|  - keycloak_admin_service.py: Keycloak client management  |
|  - firmware_service.py: ESP32 binary parsing/storage      |
|  - auth_service.py, mqtt_service.py, metrics_service.py   |
+-----------------------------------------------------------+
|  Model Layer (app/models/)                                 |
|  - device_model.py: DeviceModel SQLAlchemy model          |
|  - device.py: Device SQLAlchemy model + RotationState     |
+-----------------------------------------------------------+
|  External Services                                         |
|  - PostgreSQL: Device/model data                          |
|  - Keycloak: Device OAuth2 clients                        |
|  - MQTT Broker: Rotation notifications                    |
|  - Filesystem: Firmware binaries                          |
+-----------------------------------------------------------+
```

### Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host/db` |
| `OIDC_TOKEN_URL` | Keycloak token endpoint | `https://keycloak.local/realms/iot/protocol/openid-connect/token` |
| `KEYCLOAK_BASE_URL` | Keycloak base URL (admin API derived from this + realm) | `https://keycloak.local` |
| `KEYCLOAK_REALM` | Keycloak realm name | `iot` |
| `KEYCLOAK_ADMIN_CLIENT_ID` | Admin client ID | `iot-admin` |
| `KEYCLOAK_ADMIN_CLIENT_SECRET` | Admin client secret | (secret) |
| `MQTT_URL` | MQTT broker URL | `mqtt://mqtt.local:1883` |
| `WIFI_SSID` | WiFi network SSID for provisioning | `MyNetwork` |
| `WIFI_PASSWORD` | WiFi password for provisioning | (secret) |
| `ROTATION_CRON` | Rotation schedule | `0 8 * * 6#1` (first Sat 8am) |
| `ROTATION_TIMEOUT_SECONDS` | Rotation timeout | `300` |
| `BASEURL` | Backend base URL for provisioning | `https://iot.local` |
| `ASSETS_DIR` | Firmware storage directory | `/data/firmware` |

### Deployment Context

- Runs as a Kubernetes deployment
- Database migration via Alembic
- Rotation job via Kubernetes CronJob: `python -m app.cli rotation-job`
- Keycloak for both user authentication and device client management
- MQTT broker for real-time device notifications

### CLI Commands

- `python -m app.cli rotation-job` - Execute one rotation cycle (for K8s CronJob)
- `python -m app.cli load-test-data` - Load test data for development
