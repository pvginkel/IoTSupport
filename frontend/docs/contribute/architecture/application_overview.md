# Application Overview

The Electronics Inventory frontend is a React 19 + TypeScript application organized around domain-driven folders. This overview orients contributors to the architecture and highlights the pieces most relevant when extending tests or features.

## High-Level Stack

- **Framework**: React 19 with function components and hooks
- **Routing**: TanStack Router (`src/routes/`) with file-based route modules
- **Data Fetching**: TanStack Query (`@tanstack/react-query`) wrapped by generated OpenAPI hooks
- **Styling**: Tailwind CSS with a library of reusable UI components in `src/components/ui`
- **Build Tool**: Vite
- **Testing Mode**: Custom instrumentation under `src/lib/test/*`

## Directory Highlights

```
src/
├── components/          # UI components grouped by domain (parts, boxes, types, layout, ui)
├── contexts/            # Global React contexts (e.g., ToastContext)
├── hooks/               # Domain-specific hooks; wrap generated API hooks and add business logic
├── lib/
│   ├── api/             # Generated OpenAPI client + ApiError wrapper
│   ├── test/            # Playwright instrumentation helpers
│   ├── config/          # Environment detection (test mode, feature flags)
│   └── utils/           # Pure functions shared across features
├── routes/              # TanStack Router route modules
└── types/               # Shared TypeScript declarations (including `test-events`)
```

## Generated API Client

- `pnpm generate:api` produces type-safe hooks and clients under `src/lib/api/generated/`.
- Custom hooks in `src/hooks/` adapt API responses to frontend domain models (snake_case → camelCase, computed fields).
- Errors surface through `ApiError` (`src/lib/api/api-error.ts`), which integrates with the global toast handler.

## Server State & Error Handling

- React Query handles caching and background refresh.
- Mutation errors surface through a centralized toast system and emit structured test-event payloads in test mode.
- Forms rely on `useFormState` hooks and instrumentation helpers to keep validation synchronized with tests.

## Test Mode Architecture

- `src/lib/config/test-mode.ts` exposes `isTestMode()` and `TEST_MODE` constants.
- When true, modules in `src/lib/test/` instrument forms, router transitions, API calls, React Query errors, and toasts.
- `src/types/test-events.ts` defines the canonical payload types consumed by Playwright.

## UI Composition

- Layout components (`src/components/layout/`) define app shell, navigation, and responsive behavior.
- Domain components (e.g., `src/components/types/`) encapsulate feature-specific UI such as forms and tables.
- Shared UI building blocks live in `src/components/ui/` and accept `data-testid` props to support testing.

## Key Contexts & Providers

- `ToastContext` supplies toast operations; instrumentation hooks into this provider.
- Query client (`src/lib/query-client.ts`) centralizes React Query configuration, including default error handling.
- Router provider lives in the app root, ensuring instrumentation sees navigations consistently.

## Callouts for Test Authors

- Prefer adding instrumentation by reusing existing helpers (see [Test Instrumentation](./test_instrumentation.md)).
- When adding `data-testid` attributes, wire them through the component props so production builds remain unaffected.
- Keep new hooks colocated within `src/hooks/` and ensure they return camelCase data for UI components.

For a deeper dive into specific features, consult the feature plans under `docs/features/` and the product context in `docs/product_brief.md`.
