# Test Instrumentation

The frontend exposes deterministic telemetry while running in test mode (`VITE_TEST_MODE=true`). Instrumentation lives under `src/lib/test/` and publishes structured test-event payloads through a Playwright binding. Fixtures capture those payloads in a shared buffer so tests can assert on them without scraping the console.

## Runtime Flow

1. `isTestMode()` (from `src/lib/config/test-mode.ts`) checks `import.meta.env.VITE_TEST_MODE === 'true'`.
2. When true, UI code calls helpers such as `trackFormSubmit` or `emitTestEvent`.
3. `src/lib/test/event-emitter.ts` forwards each payload through the Playwright binding (`window.__playwright_emitTestEvent`).
4. Playwright fixtures register the binding, capture events in a 500-entry circular buffer, and helpers (`waitTestEvent`, `expectConflictError`) read from that buffer for typed payloads.

## Event Taxonomy (`src/types/test-events.ts`)

| Kind | Payload fields |
| --- | --- |
| `route` | `from`, `to`, `params?` |
| `form` | `phase` (`open`\|`submit`\|`success`\|`error`\|`validation_error`), `formId`, `fields?`, `metadata?` |
| `api` | `operation`, `method`, `status`, `correlationId`, `durationMs` |
| `toast` | `level` (`success`\|`error`\|`warning`\|`info`), `code?`, `message` |
| `error` | `scope`, `code?`, `message`, `correlationId?` |
| `query_error` | `queryKey`, `status?`, `message`, `correlationId?`, `metadata?` |
| `ui_state` | `scope`, `phase` (`loading`\|`ready`), `metadata?` |
| `list_loading` | `scope`, `phase` (`loading`\|`ready`\|`error`\|`aborted`), `metadata?` |
| `sse` | `streamId`, `phase` (`open`\|`message`\|`error`\|`close`), `event`, `data?` |

All payloads include a `timestamp` (injected by the emitter).

## Instrumentation Modules

- **`event-emitter.ts`** – Core emitter that forwards payloads to the Playwright bridge.
- **`router-instrumentation.ts`** – Subscribes to TanStack Router transitions; emits `route` events.
- **`form-instrumentation.ts`** – Exposes `trackForm*` helpers and stable `generateFormId`.
- **`toast-instrumentation.ts`** – Hooks the toast provider to emit `toast` events.
- **`error-instrumentation.ts`** – Captures global error notifications and emits `error` events.
- **`query-instrumentation.ts`** – Wraps React Query to emit `query_error` events, tag conflicts (`metadata.isConflict = true`), and expose `useListLoadingInstrumentation` for deterministic `list_loading` hooks around TanStack Query lifecycles.
- **`ui-state.ts`** – Provides `beginUiState` / `endUiState` helpers for emitting broader workflow readiness signals where `list_loading` does not apply, plus `useUiStateInstrumentation` to bind widget lifecycle to the event bus inside React components.
- **`api-instrumentation.ts`** – Optional integration for fetch wrappers to emit `api` metrics (operation, status, correlation ID).
- **`console-policy.ts`** – Enforces `console.error` -> throw during tests; Playwright’s fixture mirrors this policy to fail on unexpected errors.

## Adding New Emitters

1. Import `isTestMode()` to guard emissions.
2. Call the appropriate helper or `emitTestEvent` from `event-emitter.ts`.
3. Extend `TestEventKind` and union types in `src/types/test-events.ts` if introducing a new kind.
4. Update this document so contributors know how to consume the new signal.

Example for a custom stream:

```typescript
import { emitTestEvent } from '@/lib/test/event-emitter';
import { isTestMode } from '@/lib/config/test-mode';

function trackWizardStep(step: string) {
  if (!isTestMode()) return;
  emitTestEvent({
    kind: 'wizard',
    step,
  });
}
```

> Remember: production builds strip instrumentation dead code via `isTestMode()` guards. Keep new emitters behind the same check.

## Dashboard Instrumentation Scopes

Dashboard widgets now emit deterministic telemetry to replace brittle loading assertions:

- `dashboard.metrics` – Enhanced metrics cards (total parts, boxes, low stock, activity)
- `dashboard.health` – Inventory health gauge and breakdown tooltip
- `dashboard.storage` – Storage utilisation grid and summary stats
- `dashboard.activity` – Recent activity timeline (grouping, pagination)
- `dashboard.lowStock` – Low stock alerts (severity, quick-add)
- `dashboard.documentation` – Documentation status progress ring and quick fixes
- `dashboard.categories` – Category distribution chart and insights

Each scope uses `useListLoadingInstrumentation` for deterministic `list_loading` events and pairs it with `useUiStateInstrumentation` so tests can assert `data-state` and `ui_state` events in tandem.

## Correlation IDs & Backend Logs

- The API client propagates `X-Request-Id` into `api` test events when available.
- Backend SSE logging (`/api/testing/logs/stream`) includes the same ID, enabling cross-correlation.
- When diagnosing conflicts or errors, capture both the frontend event and backend log entry.

## Debugging Test Events

- When running managed Playwright services locally, call `await testEvents.dumpEvents()` inside a spec to inspect the buffered payloads.
- Playwright helpers can filter by `kind`, `formId`, or `correlationId`.
- Tests should assert on event sequences sparingly—prefer UI assertions first, and reach for test events when state would otherwise be invisible (forms, toasts, background API behavior).

## Maintenance Checklist

- [ ] Keep `src/types/test-events.ts` synchronized with this doc.
- [ ] Document new emitters and helper functions when added.
- [ ] Ensure instrumentation modules short-circuit when `isTestMode()` is false.
- [ ] Update Playwright helpers if payload shapes evolve.

Related docs: [Error Handling & Validation](../testing/error_handling_and_validation.md), [Troubleshooting](../testing/troubleshooting.md).
