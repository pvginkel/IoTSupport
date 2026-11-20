# Test Instrumentation

The frontend exposes deterministic telemetry while running in test mode (`VITE_TEST_MODE=true`). Instrumentation lives under `src/lib/test/` and publishes structured test-event payloads through a Playwright binding. Fixtures capture those payloads in a shared buffer so tests can assert on them without scraping the console.

## Runtime Flow

1. `isTestMode()` (from `src/lib/config/test-mode.ts`) checks `import.meta.env.VITE_TEST_MODE === 'true'`; Vite's `define` fixes that value when the app is served or built.
2. When true, UI code emits through hooks such as `useListLoadingInstrumentation`, `useUiStateInstrumentation` and `useFormInstrumentation`, or calls `emitTestEvent` directly.
3. `emitTestEvent` (`src/lib/test/event-emitter.ts`) adds a `timestamp`, throws on a kind outside `TestEventKind`, and forwards the payload through the Playwright binding (`window.__playwright_emitTestEvent`).
4. Playwright's `page` and `testEvents` fixtures register the binding (`ensureTestEventBridge` in `tests/support/helpers/test-events.ts`) and capture events in a per-page 500-entry buffer; overflowing it fails the test. Helpers (`waitTestEvent`, `waitForListLoading`, `waitForUiState`, `waitForSseEvent`, `expectConflictError`) read from that buffer for typed payloads. A wait takes the first matching event no earlier wait has taken, so one event satisfies one wait.

## Event Taxonomy (`src/lib/test/test-events.ts`)

| Kind | Payload fields | Emitted by |
| --- | --- | --- |
| `route` | `from`, `to`, `params?` | `setupRouterInstrumentation`, on every resolved navigation |
| `form` | `phase` (`open`\|`submit`\|`success`\|`error`\|`validation_error`), `formId`, `fields?`, `metadata?` | `useFormInstrumentation` and the `trackForm*` helpers |
| `api` | `operation`, `method`, `status`, `correlationId`, `durationMs` | `setupApiInstrumentation` — not installed on the API client, so the app emits no `api` events |
| `toast` | `level` (`success`\|`error`\|`warning`\|`info`), `message`, `code?`, `action?`, `exception?` | The toast provider |
| `error` | `scope`, `code?`, `message`, `correlationId?` | `setupErrorInstrumentation`: scope `global` for an uncaught error, `promise` for an unhandled rejection |
| `query_error` | `queryKey`, `status?`, `message`, `correlationId?`, `metadata?` | `setupQueryInstrumentation`: a failed query, or a failed mutation as `mutation:<key>`; a 409 sets `metadata.isConflict` |
| `ui_state` | `scope`, `phase` (`loading`\|`ready`\|`open`\|`submit`\|`success`\|`error`\|`forbidden`), `metadata?` | `useUiStateInstrumentation`, `beginUiState` / `endUiState`, `AuthProvider` |
| `list_loading` | `scope`, `phase` (`loading`\|`ready`\|`error`\|`aborted`\|`filtered`\|`cleared`), `metadata?` | `useListLoadingInstrumentation`, `useDeviceLogs` |
| `sse` | `streamId`, `phase` (`open`\|`message`\|`error`\|`close`), `event`, `data?` | `SseContextProvider`, the SSE worker, `useSSETask` |

All payloads include a `timestamp` (injected by the emitter).

### Provisioning Events

Provision device reports a `provisioning` kind that sits outside the `TestEvent` union: its type is `ProvisioningTestEvent` in `src/types/provisioning-events.ts`, and `src/lib/test/provisioning-instrumentation.ts` calls the Playwright binding directly instead of `emitTestEvent`. `useProvisioning` reports through `useProvisioningInstrumentation(deviceId)`; every event carries the `deviceId`.

| `phase` | `metadata` |
| --- | --- |
| `started` | — |
| `progress` | `provisioningPhase` (a `ProvisioningPhase`: `connecting`, `reading_partition`, `fetching_nvs`, `flashing`, `verifying`, …), `progress` |
| `complete` | — |
| `error` | `provisioningPhase`, `error` |

Specs wait for the end of a run with `waitTestEvent<ProvisioningTestEvent>(page, 'provisioning', …)`, matching the `deviceId` and a `complete` or `error` phase.

## Instrumentation Modules

- **`event-emitter.ts`** – `emitTestEvent`, the core emitter that forwards payloads to the Playwright bridge.
- **`test-events.ts`** – `TestEventKind` and the payload types.
- **`router-instrumentation.ts`** – `setupRouterInstrumentation(router)` subscribes to TanStack Router's `onResolved`; `App.tsx` installs it.
- **`form-instrumentation.ts`** – `trackFormOpen`, `trackFormSubmit`, `trackFormSuccess`, `trackFormError`, `trackFormValidationError(s)`. Components use them through `useFormInstrumentation({ formId, isOpen })` (`src/hooks/use-form-instrumentation.ts`), which emits `open` when `isOpen` turns true or the form ID changes.
- **`toast-instrumentation.ts`** – `createInstrumentedToastWrapper` wraps `showToast`, `showError`, `showSuccess`, `showWarning`, `showInfo` and `showException` to emit `toast` events; `ToastProvider` applies it in test mode.
- **`error-instrumentation.ts`** – `setupErrorInstrumentation()` listens for the window's `error` and `unhandledrejection` events and emits `error` events; `main.tsx` installs it.
- **`query-instrumentation.ts`** – `setupQueryInstrumentation(queryClient)` watches the query and mutation caches and emits `query_error` events; `src/lib/query-client.ts` installs it. Also exports `useListLoadingInstrumentation`, which emits `loading` and then `ready` or `error` around a TanStack Query fetch, `ready` at once when the data is cached at mount, and `aborted` when the component unmounts mid-load.
- **`ui-state.ts`** – `beginUiState` / `endUiState` for workflow readiness signals where `list_loading` does not apply, plus `useUiStateInstrumentation(scope, { isLoading, … })` to bind a widget's lifecycle to the event bus. It emits `ready` on mount when nothing is loading, unless `readyOnMount: false` (an action scope, idle at mount); unmounting mid-load emits `ready` with `metadata.status: 'aborted'`.
- **`provisioning-instrumentation.ts`** – `useProvisioningInstrumentation`; see [Provisioning Events](#provisioning-events).
- **`api-instrumentation.ts`** – `setupApiInstrumentation(client)` adds an `X-Request-Id` header to each request and emits `api` events; nothing installs it on the generated client.
- **`console-policy.ts`** – `setupConsolePolicy()` wraps `console.error` to record each call (`getConsoleErrors`, `clearConsoleErrors`) while still logging it; `main.tsx` installs it. Failing the test is the Playwright `page` fixture's job: it throws on a page error and on a `console.error` that neither its allowlist nor a pattern registered with `expectConsoleError` covers.

## Scopes, Form IDs and Streams the App Emits

### `list_loading` scopes

| Scope | Source | `ready` metadata |
| --- | --- | --- |
| `devices.list` | `src/routes/devices/index.tsx` | `visible`, `total` |
| `device-models.list` | `src/routes/device-models/index.tsx` | `visible`, `total` |
| `coredumps.list` | `src/components/devices/coredump-accordion-table.tsx` | `visible`, `total` |
| `rotation.dashboard` | `src/components/rotation/rotation-dashboard.tsx` | `visible`, `total` — the healthy, warning and critical devices |
| `devices.logs` | `src/hooks/use-device-logs.ts`, which emits `loading` and `ready` itself | `deviceId`, `logCount` |

### `ui_state` scopes

| Scope | Source | Phases and metadata |
| --- | --- | --- |
| `auth` | `src/contexts/auth-context.tsx` | `loading`, then `ready` (`userId`), `forbidden`, or `error` (`message`) |
| `devices.flash-modal.images` | `src/components/devices/flash-device-modal.tsx` — the flash images Flash device fetches when it opens | `ready`: `flashStatus`, `firmwareVersion`, `imageCount`, `error` |
| `devices.flash-modal.flash` | `src/components/devices/flash-device-modal.tsx` — one flash run (`readyOnMount: false`) | `ready`: `outcome`, `firmwareVersion`, `failedPhase`, `error` |
| `worker.services` | The Playwright `page` and `testEvents` fixtures, not the app | `ready`: `backendUrl`, `frontendUrl` |

### Form IDs

| `formId` | Source |
| --- | --- |
| `DeviceModelEditor_new`, `DeviceModelEditor_edit` | `src/components/device-models/device-model-editor.tsx` |
| `DeviceEditor_new`, `DeviceEditor_edit`, `DeviceEditor_duplicate` | `src/hooks/use-device-form.ts` — the new-device editor, the Configuration tab, and the duplicate editor |
| `CoredumpDelete` | `src/components/devices/coredump-accordion-table.tsx` — deleting a core dump |

Each emits `open` on mount, and `submit` followed by `success` or `error` when it saves (or, for `CoredumpDelete`, deletes).

### SSE streams

| `streamId` | `event` (`phase`) | Source |
| --- | --- | --- |
| `connection` | `connected` (`open`, `data.requestId`); `rejected` (`message`, `data.status`, `data.message`); `error` (`error`, shared worker only) | `SseContextProvider`, `src/workers/sse-worker.ts` |
| The event's type: `version`, `device-logs`, `rotation-updated`, `task_event` | The same type (`message`), with the event's payload as `data` | Every event the stream delivers |
| `task` | `task_subscription` (`open`), `task_started` and `progress_update` (`message`), `task_completed` (`message`, or `error` when the task failed), `task_failed` (`error`) | `useSSETask`, which no screen mounts |

Specs wait on these with `waitForSseEvent(page, { streamId, phase?, event?, matcher? })` and read the payload with `extractSseData`.

## Adding New Emitters

1. Reuse the hooks first: `useListLoadingInstrumentation` for a query-backed list or panel, `useUiStateInstrumentation` for a widget or workflow that is not a list, `useFormInstrumentation` for an editor or a mutation. They check `isTestMode()` themselves.
2. A hand-written emitter imports `isTestMode()` to guard emissions and calls `emitTestEvent` from `event-emitter.ts`.
3. A new kind goes into `TestEventKind` and the `TestEvent` union in `src/lib/test/test-events.ts`: `emitTestEvent` throws on a kind outside `TestEventKind`.
4. Update this document so contributors know how to consume the new signal.

Example: the flash run in `src/components/devices/flash-device-modal.tsx`, an action scope that is idle until the user starts a flash:

```typescript
import { useUiStateInstrumentation } from '@/lib/test/ui-state';

useUiStateInstrumentation('devices.flash-modal.flash', {
  isLoading: isFlashing,
  readyOnMount: false,
  getReadyMetadata: () => ({
    outcome: state.phase,
    firmwareVersion: state.firmwareVersion,
    failedPhase: state.failedPhase,
    error: state.error,
  }),
});
```

`tests/e2e/devices/devices-flashing.spec.ts` waits for it with `waitForUiState(page, 'devices.flash-modal.flash', 'ready')` and asserts on its `metadata`.

> Remember: a build without `VITE_TEST_MODE=true` defines it as `'false'`, so every `isTestMode()` guard is false in production; `pnpm build` runs `verify:build` (`scripts/verify-production-build.cjs`), which reports test markers left in the bundle. Keep new emitters behind the same check.

## Backend Logs

- The `backendLogs` fixture attaches the worker backend's output to each test, so a failing test's report carries the backend's side of the story.

## Debugging Test Events

- Inside a spec, `console.log(await testEvents.dumpEvents())` prints the payloads captured so far; `testEvents.getEventsByKind(kind)` and `testEvents.countEvents(matcher)` narrow them.
- `waitTestEvent(page, kind, filter)` matches on any payload field — `scope`, `formId`, `streamId`, `deviceId`; `waitForFormValidationError` filters by `formId` and field.
- Tests should assert on event sequences sparingly—prefer UI assertions first, and reach for test events when state would otherwise be invisible (forms, toasts, SSE, the USB workflows).

## Maintenance Checklist

- [ ] Keep `src/lib/test/test-events.ts` synchronized with this doc.
- [ ] Document new emitters, scopes and form IDs when added.
- [ ] Ensure instrumentation modules short-circuit when `isTestMode()` is false.
- [ ] Update the Playwright helpers (`tests/support/helpers.ts`, `tests/support/helpers/test-events.ts`) if payload shapes evolve.

Related docs: [Error Handling & Validation](../testing/error_handling_and_validation.md), [No-Sleep Patterns](../testing/no_sleep_patterns.md), [Troubleshooting](../testing/troubleshooting.md).
