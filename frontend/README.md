# IoT Support Frontend

The web UI for IoT Support: managing the ESP32 device fleet in a homelab. It provisions, edits and
duplicates devices, manages device models and shows their firmware versions, shows each device's
logs and coredumps, and follows the fleet's credential rotation. It talks only to the IoTSupport
backend in `../backend`, through the generated OpenAPI client.

## Tech Stack

- **React 19** with TypeScript (strict mode)
- **TanStack Router** - File-based routing with type-safe navigation
- **TanStack Query** - Server state management and caching
- **Monaco Editor** - JSON editing for device and model configuration
- **Tailwind CSS 4** - Utility-first styling with dark mode
- **Radix UI** - Accessible component primitives
- **Vite** - Development server and production builds
- **openapi-typescript** - Generated API types and hooks
- **Playwright** - End-to-end testing

## Development

Node, pnpm and the Playwright browsers come from the KubeCoder environment's `modern-app` tool
container. Run the `kc project` verbs from the repository root:

```bash
kc project setup frontend   # pnpm install and the Playwright browser
kc project build frontend   # production build
kc project lint frontend    # ESLint, TypeScript, knip
kc project test frontend    # Playwright, booting the frontend and a backend per worker
```

`scripts/dev.py` at the repository root starts the whole dev stack — the frontend on
`http://localhost:3100`, the backend on 3101 and the SSE gateway on 3102. Stop it with `^C`. The
Vite dev server proxies `/api/**` to the backend.

After a backend API change, regenerate the API client from `frontend/`:

```bash
cexec modern-app pnpm generate:api
```

The generated client is never edited by hand.

## URL Routes

| Route | Purpose |
|-------|---------|
| `/` | Redirects to `/devices` |
| `/devices` | Device list |
| `/devices/new` | Provision a new device |
| `/devices/:deviceId` | Device detail; opens the last-used tab |
| `/devices/:deviceId/edit` | Edit the device |
| `/devices/:deviceId/logs` | Device logs |
| `/devices/:deviceId/coredumps` | Device coredumps |
| `/devices/:deviceId/duplicate` | Duplicate the device |
| `/device-models` | Device model list |
| `/device-models/new` | Create a device model |
| `/device-models/:modelId` | Edit a device model |
| `/rotation` | Credential rotation dashboard |

## Documentation

`CLAUDE.md` is the launchpad; the contributor documentation lives under `docs/contribute/`:

- [Contributor hub](docs/contribute/index.md)
- [Getting Started](docs/contribute/getting_started.md) - Setup guide
- [Environment Reference](docs/contribute/environment.md) - Environment variables and ports
- [Architecture Overview](docs/contribute/architecture/application_overview.md) - Technical architecture
- [Testing Guide](docs/contribute/testing/index.md) - Testing principles and patterns
- [Playwright Guide](docs/contribute/testing/playwright_developer_guide.md) - E2E test authoring

## License

Private - All rights reserved
