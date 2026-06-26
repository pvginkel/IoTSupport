# IoT Support Frontend

A web application for managing configuration files for ESP32-based IoT devices in a homelab environment. It provides a visual interface to list, create, edit, and delete device configurations that were previously managed through manual file editing and Helm chart deployments.

## Features

- **Device Configuration List** - View all device configurations with sortable columns (MAC address, device name, entity ID, OTA status)
- **Configuration Editor** - Full-featured Monaco JSON editor with syntax highlighting, code folding, and validation
- **Create & Duplicate** - Start from a minimal template or copy existing configurations
- **Delete with Confirmation** - Safe removal of configurations with confirmation dialog
- **Dark Mode Interface** - Modern dark theme with skeleton loaders during data fetching

## Tech Stack

- **React 19** with TypeScript (strict mode)
- **TanStack Router** - File-based routing with type-safe navigation
- **TanStack Query** - Server state management and caching
- **Monaco Editor** - JSON editing with full IDE features
- **Tailwind CSS 4** - Utility-first styling with dark mode
- **Radix UI** - Accessible component primitives
- **Vite** - Fast development and optimized builds
- **openapi-typescript** - Generated API types and hooks
- **Playwright** - End-to-end testing

## Prerequisites

- **Node.js 18+**
- **pnpm** package manager (`npm install -g pnpm`)
- **Backend service** running locally on port 5000 (see backend repository)

## Getting Started

### Installation

```bash
# Install dependencies
pnpm install

# Generate type-safe API client from backend OpenAPI spec
pnpm generate:api

# Generate route types (optional, auto-generated on dev)
pnpm generate:routes
```

### Environment Setup

Copy `.env.example` to `.env` and adjust values as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_URL` | `http://localhost:5000` | Backend API origin |
| `SSE_GATEWAY_URL` | `http://localhost:3001` | SSE Gateway origin |
| `VITE_TEST_MODE` | `false` | Enable test instrumentation |

### Development

```bash
# Start dev server on http://localhost:3200
pnpm dev

# Run linting and type checking
pnpm check

# Build for production
pnpm build

# Preview production build
pnpm preview
```

## Project Structure

```
src/
├── components/
│   ├── devices/          # Device-specific components
│   │   ├── device-editor.tsx
│   │   └── device-list-table.tsx
│   ├── layout/           # Layout components (sidebar)
│   └── ui/               # Reusable UI primitives
├── contexts/             # React contexts (toast)
├── hooks/                # Custom hooks (useDevices, useConfirm)
├── lib/
│   ├── api/              # Generated API client and hooks
│   ├── config/           # App configuration
│   ├── test/             # Test instrumentation
│   └── utils/            # Utility functions
├── routes/               # TanStack Router file-based routes
│   ├── devices/
│   │   ├── index.tsx     # Device list
│   │   ├── new.tsx       # Create new device
│   │   ├── $macAddress.tsx        # Edit device
│   │   └── $macAddress/duplicate.tsx  # Duplicate device
│   └── __root.tsx        # Root layout
└── types/                # TypeScript type definitions
```

## URL Routes

| Route | Purpose |
|-------|---------|
| `/` | Redirects to `/devices` |
| `/devices` | List all device configurations |
| `/devices/new` | Create new device configuration |
| `/devices/:macAddress` | Edit existing device configuration |
| `/devices/:macAddress/duplicate` | Duplicate existing configuration |

## Testing

```bash
# Install Playwright browsers (one-time)
pnpm exec playwright install

# Run all tests headless
pnpm playwright test

# Run tests with UI
pnpm playwright test --ui

# Run specific test file
pnpm playwright test tests/example.spec.ts
```

Playwright automatically manages frontend and backend services during test runs with per-worker isolation.

## API Integration

The frontend connects to a REST API backend that stores configurations as JSON files on CephFS. The Vite dev server proxies `/api/**` requests to the backend.

API types are generated from the backend's OpenAPI specification:

```bash
# Regenerate after backend API changes
pnpm generate:api
```

## Documentation

Detailed documentation is available in the `docs/` directory:

- [Product Brief](docs/product_brief.md) - Product context and workflows
- [Getting Started](docs/contribute/getting_started.md) - Setup guide
- [Architecture Overview](docs/contribute/architecture/application_overview.md) - Technical architecture
- [Testing Guide](docs/contribute/testing/index.md) - Testing principles and patterns
- [Playwright Guide](docs/contribute/testing/playwright_developer_guide.md) - E2E test authoring

## License

Private - All rights reserved
