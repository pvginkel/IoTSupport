# Factories & Fixtures

Factories and fixtures power the API-first testing strategy. They create deterministic data, expose shared helpers, and keep specs concise—so that every spec can hit the real backend without relying on request interception.

## API Client & Data Bundle

`tests/api/index.ts` exports both the raw API client and a factory bundle.

```typescript
import { createApiClient, createTestDataBundle } from '../api';

const apiClient = createApiClient({ baseUrl: backendUrlFromFixture });
const testData = createTestDataBundle(apiClient, { backendUrl: backendUrlFromFixture });
```

### Factories

- **`TypeTestFactory` (`tests/api/factories/type-factory.ts`)**
  - `create(overrides?)` – POST `/api/types`
  - `randomTypeName(prefix?)` – deterministic prefix-shortId generator
- **`PartTestFactory` (`tests/api/factories/part-factory.ts`)**
  - `create({ typeId?, overrides? })` – creates dependent Type automatically when omitted
  - Random helpers for descriptions, manufacturer codes, etc.
- Pending factories live under `tests/api/factories/`; extend the bundle when new domains gain coverage.

All factories follow the same shape: accept overrides, return structured DTOs, and expose random helpers for collision-free runs.
- If a factory is missing behavior you need, add it here and extend the backend as required. Do **not** replace the gap with Playwright `page.route` stubs.
- Before writing a spec, land the factory/helper first so the test seeds state via `testData` instead of ad hoc API calls.

## Test Fixtures (`tests/support/fixtures.ts`)

Custom fixtures extend Playwright’s base test:

| Fixture | Type | Description |
| --- | --- | --- |
| `frontendUrl` | `string` | Worker-scoped frontend origin. Defaults to the Vite proxy launched for the worker; falls back to `FRONTEND_URL` when managed services are disabled. |
| `backendUrl` | `string` | Worker-scoped backend origin. Defaults to the in-memory backend launched for the worker; falls back to `BACKEND_URL` when managed services are disabled. |
| `backendLogs` | `BackendLogCollector` | Streams worker backend stdout/stderr and attaches `backend.log` to each spec. |
| `sseTimeout` | `number` | 35s timeout for SSE heavy flows. |
| `apiClient` | Return of `createApiClient()` | Raw OpenAPI client for advanced usage. |
| `testData` | Return of `createTestDataBundle()` | Aggregated factories. |
| `types` | `TypesPage` instance | Feature page object for the Types flow. |
| `page` override | `Page` | Registers the Playwright test-event bridge, enforces console error policy, and disables animations. |
| `testEvents` | `TestEventCapture` | Access to the Playwright-managed buffer of test-event payloads. |
| `aiAnalysisMock` | `(options?: AiAnalysisMockOptions) => Promise<AiAnalysisMockSession>` | Shared helper that registers the sanctioned AI analysis SSE mock and disposes it between specs. |

Extend `TestFixtures` when adding new domains (e.g., `parts: PartsPage`). Keep fixture code minimal and reusable; complexity belongs in page objects or factories.

### AI Analysis Flow Helper

`tests/support/helpers/ai-analysis-mock.ts` centralizes the single approved mock for `/api/ai-parts/analyze`. Call the `aiAnalysisMock` fixture to create a session, wait for `waitForConnection`, and drive the flow with `emitStarted`, `emitProgress`, and `emitCompleted` instead of wiring `page.route` by hand.

## Global Setup (`tests/support/global-setup.ts`)

- Loads `.env.test` via `dotenv`.
- Skips readiness checks when `PLAYWRIGHT_MANAGED_SERVICES` is truthy so worker fixtures can launch per-worker services.
- Falls back to the legacy health probes when `PLAYWRIGHT_MANAGED_SERVICES=false`.

## Helpers (`tests/support/helpers.ts`)

Provides convenience utilities used across specs:

- `makeUnique(prefix)` – deterministic-length unique IDs for test data
- `waitTestEvent(page, kind, filter?, timeout?)`
- `waitForFormValidationError(page, formId, field?)`
- `expectConflictError(page, correlationId?)`
- `expectConsoleError(page, pattern)`
- `emitTestEvent(page, payload)` from `tests/support/helpers/test-events` for ad-hoc instrumentation

Avoid duplicating helper logic in specs—centralize shared behaviors here.

## Random Data Strategy

- Use factory helpers (e.g., `testData.types.randomTypeName('Resistor')`).
- Prefix identifiers with domain-specific tokens to aid debugging.
- Keep randomization deterministic length-wise to avoid UI layout drift.
- Seed fresh data per spec. Even if two tests need identical state, create separate records to avoid hidden coupling.
- `Date.now()` is eslint-blocked—use `makeUnique` or domain helpers for uniqueness, and document any rare inline exemptions where a real timestamp is required.

## Deterministic Testing Content

Use the backend-provided `/api/testing/content/*` endpoints whenever specs need static assets:

- `GET /api/testing/content/image?text=<label>` – stable placeholder PNG (supersedes `/api/testing/fake-image`).
- `GET /api/testing/content/pdf` – deterministic PDF stream with canned metadata.
- `GET /api/testing/content/html?title=<text>` – plain HTML response without banners.
- `GET /api/testing/content/html-with-banner?title=<text>` – HTML response that includes the standard marketing banner.

Build URLs with the `backendUrl` fixture so the same calls work locally and in CI (swap `localhost` for `127.0.0.1` when necessary so backend validation passes), and avoid hand-rolling data URLs or intercepting document fetches.

## Extending the Bundle

When a new feature needs coverage:

1. Add API helper functions under `tests/api/` if the backend endpoint is missing convenience wrappers.
2. Create a new factory in `tests/api/factories/` that mirrors the domain API.
3. Export it from `tests/api/index.ts` and include it in `createTestDataBundle`.
4. Update `tests/support/fixtures.ts` to expose the new factory via `testData` (already automatic).
5. If the feature warrants a page object, add a fixture (e.g., `parts: PartsPage`).

Document significant additions in this file to keep contributors aligned.

## References

- [Playwright Developer Guide](./playwright_developer_guide.md)
- [Page Objects](./page_objects.md)
- [How to Add an E2E Test](../howto/add_e2e_test.md)
