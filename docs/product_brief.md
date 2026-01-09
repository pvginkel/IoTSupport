# IoT Support Backend - Product Brief

## Project Overview

The IoT Support Backend is a lightweight REST API for managing configuration files for ESP32-based IoT devices in a homelab environment. It replaces a manual workflow where device configurations were stored in Helm chart files and required a full Kubernetes redeployment for every change.

The application provides a simple CRUD interface for JSON configuration files, where each file corresponds to a single IoT device identified by its MAC address. Configurations are stored directly on the filesystem (CephFS in production), making changes immediately available to devices without redeployment.

## Target Audience

- Homelab administrators managing a fleet of ESP32 IoT devices
- Users in trusted network environments (no authentication required)
- Expected scale: up to 200 device configurations

## Primary Benefits and Features

### Core Functionality

1. **List Configurations** - Retrieve an overview of all device configurations with key metadata (MAC address, device name, entity ID, OTA status)

2. **Get Configuration** - Retrieve the complete JSON configuration for a specific device by MAC address

3. **Save Configuration** - Create or update a device configuration (upsert semantics) with validation that:
   - The filename is a valid MAC address (lowercase, hyphen-separated format: `xx-xx-xx-xx-xx-xx`)
   - The content is valid JSON

4. **Delete Configuration** - Remove a device configuration by MAC address

### Operational Features

- **Health Endpoint** - Kubernetes liveness/readiness probe support at `/api/health`
- **Prometheus Metrics** - Operational metrics at `/metrics` for monitoring
- **OpenAPI Documentation** - Auto-generated API docs at `/api/docs`

### Key Design Decisions

- **No schema validation** - Configuration content is not validated beyond being valid JSON, allowing flexibility for different device types
- **No authentication** - Designed for trusted homelab environments
- **No database** - Configurations stored as JSON files on the filesystem
- **Immediate availability** - Changes are written directly to disk, instantly available to devices

## Technology and Architecture

### Stack

- **Python 3.12** with Flask web framework
- **Pydantic** for request/response validation and schemas
- **SpectTree** for OpenAPI documentation generation
- **dependency-injector** for dependency injection
- **prometheus-flask-exporter** for metrics
- **Waitress** as WSGI server

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Flask App                          │
├─────────────────────────────────────────────────────────┤
│  API Layer (app/api/)                                   │
│  - configs.py: CRUD endpoints for device configs        │
│  - health.py: Health check endpoint                     │
│  - metrics.py: Prometheus metrics endpoint              │
├─────────────────────────────────────────────────────────┤
│  Service Layer (app/services/)                          │
│  - config_service.py: Business logic for config mgmt    │
│  - metrics_service.py: Prometheus metrics management    │
├─────────────────────────────────────────────────────────┤
│  Schema Layer (app/schemas/)                            │
│  - config.py: Pydantic models for API validation        │
├─────────────────────────────────────────────────────────┤
│  Filesystem (CephFS)                                    │
│  - JSON config files named by MAC address               │
└─────────────────────────────────────────────────────────┘
```

### Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `ESP32_CONFIGS_DIR` | Path to configuration files directory | `/data/esp32-configs` |
| `CORS_ORIGINS` | Allowed CORS origins | `["http://localhost:3000"]` |

### Deployment Context

- Runs as a separate service alongside existing iotsupport application
- API mounted at `/api` path, proxied through main iotsupport nginx
- CephFS volume provides persistent configuration storage

Note: Deployment configuration (Dockerfile, Helm, Kubernetes) is managed separately.
