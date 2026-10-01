# IoT Support Backend

The Flask REST API behind IoT Support: device and device-model management, firmware storage and
distribution, provisioning packages, and automatic rotation of device OAuth2 credentials. Device
metadata lives in PostgreSQL, firmware and other blobs in S3, and every device is a Keycloak client
that authenticates machine-to-machine. Rotation notifications go out over MQTT.

The API has three audiences, each on its own blueprint:

- `/api/*` (the rest) — the frontend (a BFF: this API serves only the IoTSupport frontend).
- `/api/iot/*` — deployed device firmware, authenticated with the device's own Keycloak client.
- `/api/pipeline/*` — other repositories' CI, e.g. firmware uploads, with the `pipeline` role.

`docs/product_brief.md` describes the domain model; `CLAUDE.md` the architecture, layering and
testing conventions; `docs/decisions/` the ADRs.

## Development

Python, Poetry and the services the backend needs (PostgreSQL, S3 storage, OpenSearch) come with
the KubeCoder environment; commands run in the `modern-app` tool container. Run the `kc project`
verbs from the repository root:

```bash
kc project setup backend   # poetry install, generate .env/.env.test, create and migrate the database
kc project test backend    # pytest
kc project lint backend    # ruff, mypy, vulture
```

`scripts/dev.py` at the repository root starts the whole dev stack — the API on
`http://localhost:3101`, the frontend on 3100 and the SSE gateway on 3102. Stop it with `^C`.

### Configuration

Settings are read from the environment and from `.env`. `kc project setup` generates `.env` and
`.env.test` with local defaults (`scripts/generate-dev-env.sh`); it leaves existing files alone.
The settings themselves, with their defaults, are in `app/config.py` and `app/app_config.py`.

### API documentation

The OpenAPI documentation is served at `/api/docs`, Prometheus metrics at `/metrics`, and the
Kubernetes probes under `/health`.

## Keycloak configuration

### User authentication client

Need an `iotsupport` client for user authentication. It's authenticated and Direct access grants must be set. Custom roles named `admin` and `pipeline` need to be added.

#### Audience mapper (required)

The `iotsupport` client needs an audience mapper so that access tokens include the client in the `aud` claim. Without this, authentication fails with "Token issuer or audience does not match expected values".

1. Go to **Clients** → **iotsupport**
2. Go to **Client scopes** tab
3. Click on **iotsupport-dedicated**
4. Go to **Mappers** tab → **Add mapper** → **By configuration**
5. Select **Audience** and configure:
   - **Name**: `iotsupport-audience`
   - **Included Client Audience**: `iotsupport`
   - **Add to ID token**: OFF
   - **Add to access token**: ON

#### User role assignment

Users need the `admin` role assigned to access the application:

1. Go to **Users** → select the user
2. Go to **Role mapping** tab
3. Click **Assign role** → filter by **clients** → select `iotsupport` → `admin`

### Admin client

Need an `iotsupport-admin` client with administrative access. That's also authenticated. The **only** authentication flow that needs to be checked is Service account roles. This enables the Service account roles tab. `manage-clients` must be added.

### Pipeline client

Need an `iotsupport-pipeline` client for CI/CD pipeline access (e.g., firmware uploads).

1. Create a new client named `iotsupport-pipeline`
2. Set **Client authentication** to ON
3. Under **Authentication flow**, check **only** "Service account roles"
4. Save the client

#### Audience mapper (required)

1. Go to **Client scopes** tab
2. Click on **iotsupport-pipeline-dedicated**
3. Go to **Mappers** tab → **Add mapper** → **By configuration**
4. Select **Audience** and configure:
   - **Name**: `iotsupport-pipeline-audience`
   - **Included Client Audience**: `iotsupport`
   - **Add to ID token**: OFF
   - **Add to access token**: ON

#### Service account role assignment

1. Go to **Service account roles** tab
2. Click **Assign role** → filter by **clients** → select `iotsupport` → `pipeline`

### Device client scope configuration

Device clients (created automatically when provisioning devices) need specific scopes in their tokens:

1. **Audience mapper** - Required for backend authentication. Without this, device authentication fails with "Token issuer or audience does not match expected values".

2. **Standard OIDC scopes** - Required for Mosquitto MQTT broker JWT validation:
   - `openid` - Required for OIDC compliance
   - `profile` - Includes name claims
   - `email` - Includes email claim

Configure a client scope for the audience mapper:

1. Go to **Client scopes** and create a new scope named `iot-device-audience` (or set `KEYCLOAK_DEVICE_SCOPE_NAME` to use a different name)
2. In the scope's **Mappers** tab, create a new mapper:
   - **Mapper type**: Audience
   - **Name**: iot-device-audience
   - **Included Client Audience**: Set to the value of `OIDC_AUDIENCE` (or `OIDC_CLIENT_ID` if `OIDC_AUDIENCE` is not set)
   - **Add to access token**: ON

The backend automatically adds the following scopes to device clients when they are created:
- `iot-device-audience` (or custom name from `KEYCLOAK_DEVICE_SCOPE_NAME`)
- `profile`
- `email`

Note: The `openid` scope is automatically included for all OIDC clients and doesn't need to be explicitly assigned.

If any scope doesn't exist in Keycloak, a warning is logged but client creation continues.

## License

See LICENSE file for details.
