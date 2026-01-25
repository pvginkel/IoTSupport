# IoT Support Backend

A lightweight REST API for managing configuration files for ESP32-based IoT devices. Configurations are stored as JSON files on the filesystem, making changes immediately available to devices without redeployment.

## Features

- **Configuration Management** - CRUD operations for device configurations identified by MAC address
- **No Database Required** - Configurations stored directly on filesystem (CephFS in production)
- **Asset Upload** - Upload and manage device assets with cryptographic signing
- **LVGL Image Proxy** - Convert images to LVGL-compatible format for ESP32 displays
- **OpenAPI Documentation** - Auto-generated API docs at `/api/docs`
- **Prometheus Metrics** - Operational metrics at `/metrics`
- **Health Checks** - Kubernetes liveness/readiness probes at `/api/health`

## Requirements

- Python 3.11+
- Poetry

## Quick Start

1. **Install dependencies**
   ```bash
   poetry install
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Run the development server**
   ```bash
   poetry run dev
   ```

   The API will be available at `http://localhost:3201`

## Configuration

Environment variables (can be set in `.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `ESP32_CONFIGS_DIR` | Path to configuration files directory | (required) |
| `ASSETS_DIR` | Path to assets upload directory | (required) |
| `SIGNING_KEY_PATH` | Path to RSA signing key for asset uploads | (required) |
| `CORS_ORIGINS` | Allowed CORS origins (JSON array) | `["http://localhost:3000"]` |
| `DEBUG` | Enable debug mode | `true` |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `3201` |

## API Endpoints

### Device Configurations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/configs` | List all configurations |
| `GET` | `/api/configs/{mac}` | Get configuration by MAC address |
| `PUT` | `/api/configs/{mac}` | Create or update configuration |
| `DELETE` | `/api/configs/{mac}` | Delete configuration |

MAC addresses must be in lowercase, hyphen-separated format: `xx-xx-xx-xx-xx-xx`

#### Save Configuration Request

```json
{
  "content": { ... },
  "allow_overwrite": true
}
```

Set `allow_overwrite` to `false` to prevent overwriting existing configurations (returns 409 Conflict if exists).

### Assets

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/assets/upload` | Upload a signed asset |

### Images

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/images/proxy` | Proxy and convert image to LVGL format |

### Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check (returns 200/503) |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/api/docs` | OpenAPI documentation |

## Development

### Running Tests

```bash
poetry run pytest
```

With coverage:
```bash
poetry run pytest --cov=app --cov-report=term-missing
```

### Linting

```bash
poetry run ruff check .
```

### Type Checking

```bash
poetry run mypy .
```

## Architecture

```
app/
├── api/           # HTTP endpoints (Flask blueprints)
│   ├── configs.py # Device configuration CRUD
│   ├── assets.py  # Asset upload
│   ├── images.py  # LVGL image proxy
│   ├── health.py  # Health checks
│   └── metrics.py # Prometheus metrics
├── services/      # Business logic layer
│   ├── config_service.py
│   ├── asset_upload_service.py
│   ├── image_proxy_service.py
│   └── metrics_service.py
├── schemas/       # Pydantic request/response models
├── utils/         # Shared utilities
└── config.py      # Application settings
```

## Keycloak configuration

Need an `iotsupport` client for authentication. It's authenticated and Direct access grants must be set.

Also need an `iotsupport-admin` client with administrative access. That's also authenticated. The **only** authentication flow that needs to be checked is Service account roles. This enables the Service account roles tab. `manage-clients` must be added.



## License

See LICENSE file for details.
