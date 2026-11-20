# Error Handling & Validation Patterns

In test mode the frontend surfaces form lifecycles, failed requests and toasts to Playwright as
structured test events, and the `page` fixture fails a test on an unexpected console error. This
guide explains how forms, mutations and validation flows integrate with that, so tests can assert
on observable signals.

## Form Instrumentation

Forms use `useFormInstrumentation({ formId, isOpen, snapshotFields? })` from
`src/hooks/use-form-instrumentation.ts`, which wraps the `trackForm*` helpers in
`@/lib/test/form-instrumentation`. It emits `open` when `isOpen` turns true and returns
`trackOpen`, `trackSubmit`, `trackSuccess`, `trackError`, `trackValidationError` and
`trackValidationErrors`; each takes an optional fields snapshot that lands in the event's `fields`
and `metadata`.

A trimmed excerpt of the device editor's save (`src/hooks/use-device-form.ts`):

```typescript
const formId = mode === 'edit' ? 'DeviceEditor_edit' : mode === 'duplicate' ? 'DeviceEditor_duplicate' : 'DeviceEditor_new'
const { trackSubmit, trackSuccess, trackError } = useFormInstrumentation({ formId, isOpen: true })

trackSubmit({ deviceId, mode })
updateDevice.mutate(
  { id: deviceId, config: jsonConfig, active },
  {
    onSuccess: () => {
      trackSuccess({ deviceId })
      // ...navigate to the device's logs tab
    },
    onError: (err) => {
      isNavigatingRef.current = false
      trackError({ error: err instanceof Error ? err.message : 'Unknown error' })
    }
  }
)
```

The app's form ids:

| `formId` | Form |
| --- | --- |
| `DeviceEditor_new`, `DeviceEditor_edit`, `DeviceEditor_duplicate` | The device editor (`src/hooks/use-device-form.ts`) |
| `DeviceModelEditor_new`, `DeviceModelEditor_edit` | The device model editor (`src/components/device-models/device-model-editor.tsx`) |
| `CoredumpDelete` | Deleting a core dump (`src/components/devices/coredump-accordion-table.tsx`) |

The forms set these ids as literals. `generateFormId(componentName, identifier?)` in the same module
derives one instead, lower-cased with a trailing `Form` dropped
(`generateFormId('DeviceForm', 'edit')` is `device_edit`).

A spec waits on a form event through `waitTestEvent`:

```typescript
import type { FormTestEvent } from '@/lib/test/test-events';
import { waitTestEvent } from '../../support/helpers';

await waitTestEvent<FormTestEvent>(page, 'form', evt =>
  evt.formId === 'DeviceEditor_edit' && evt.phase === 'success'
);
```

### Validation Events

`trackValidationError(field, message)` and `trackValidationErrors(errors)` emit the
`validation_error` phase, one event per field, and `waitForFormValidationError(page, formId, field?)`
waits for one. The payload:

```json
{
  "kind": "form",
  "phase": "validation_error",
  "formId": "<formId>",
  "fields": { "...": "the snapshot, when one was passed" },
  "metadata": {
    "field": "<field>",
    "error": "<message>"
  },
  "timestamp": "<ISO 8601>"
}
```

No form in the app emits `validation_error`. The device and device model editors validate their
JSON as it is typed and show the result on the element: the editor container
(`devices.editor.json-editor`, `device-models.editor.schema-editor`) carries
`data-state="valid|invalid"`, the editor shows the parse error, and Save is disabled. Specs assert
on that:

```typescript
await devicesPage.setJsonContent('{ invalid json }');

// Save button should be disabled due to JSON error
await expect(devicesPage.saveButton).toBeDisabled();

// Error indicator should be visible
await expect(devicesPage.jsonEditorContainer).toHaveAttribute('data-state', 'invalid');
```

## Query & Mutation Errors

`setupQueryInstrumentation(queryClient)` (`src/lib/test/query-instrumentation.ts`, called from
`src/lib/query-client.ts`) watches the query and mutation caches:

- Every failed query or mutation emits a `query_error` event with
  `{ queryKey, status, message, correlationId }`; a mutation's `queryKey` is
  `mutation:<mutationKey>`, or `mutation:unknown` without one.
- An HTTP `409` adds `metadata.isConflict = true` and the error body as
  `metadata.conflictDetails`.

`expectConflictError(page, correlationId?)` waits for a `query_error` with status 409:

```typescript
import { expectConflictError } from '../../support/helpers';

const conflict = await expectConflictError(page);
expect(conflict.metadata.isConflict).toBe(true);
```

What the user sees:

- **Mutations** – the query client's default `mutations.onError` toasts `parseApiError(error)`
  (`src/lib/utils/error-parsing.ts`) through `showException`. A mutation hook that passes its own
  `onError` to the generated hook — as `useCreateDevice`, `useUpdateDevice` and `useDeleteCoredump`
  do — replaces that default and toasts the error's message through `showError`. A form's
  per-call `onError`, like the one above, tracks the error and resets local state; it does not
  toast.
- **Queries** – the component shows its error state (`devices.list.error`,
  `coredumps.table.error`, `rotation.dashboard.error`). Queries do not retry a 4xx and retry other
  failures up to three times with backoff, so a 5xx error state takes the retries to appear;
  mutations do not retry.

## Console Error Policy

The `page` fixture (`tests/support/fixtures-infrastructure.ts`) fails the test on any page error,
and on any `console.error` it does not expect. It lets through, without registration, messages
that contain:

- `409`, `CONFLICT`, `already exists`, `duplicate`, `cannot delete` or `in use`
- `400`, `401`, `403`, `404`, `500` or their status texts, and `/api/auth/`
- `Form submission error` or `Toast exception`
- the browser's `Unable to preventDefault inside passive event listener invocation.`

Any other expected error is registered before the action that logs it, with
`expectConsoleError(page, pattern)`. The pattern holds for the rest of the test; unless it already
names a toast exception, the helper also registers `Toast exception…<pattern>`. The template's
`test-infrastructure.spec.ts` registers the log `showException` writes:

```typescript
import { expectConsoleError } from '../support/helpers';

await expectConsoleError(page, /Toast exception/);
```

`showException` logs `console.error('Toast exception', error)` outside production builds. Avoid
adding `console.error` calls to app code — surface errors through toasts and the error states
above so instrumentation stays consistent.

## Toast Notifications

In test mode `createInstrumentedToastWrapper` (`src/lib/test/toast-instrumentation.ts`) wraps the
toast context: `showToast`, `showSuccess`, `showError`, `showWarning`, `showInfo` and
`showException` each emit a `toast` event with `{ level, message, code?, exception?, action? }`.
Assert on the toast itself through the `toastHelper` fixture (`app-shell.toast.item`), and use the
event for what the toast does not show, such as the `exception` behind it.

## Router & API Events

- `setupRouterInstrumentation(router)`, called from `src/App.tsx` in test mode, emits a `route`
  event on every resolved navigation, with `from`, `to` and `params`.
- `src/lib/test/api-instrumentation.ts` exports `setupApiInstrumentation(client)` for `api`
  events; nothing in the app calls it, so the app emits no `api` events.

## Test-Event Taxonomy Reference

| Kind | Use case |
| --- | --- |
| `route` | Navigation changes (`from`, `to`, `params`) |
| `form` | Form lifecycle: `open`, `submit`, `success`, `error`, `validation_error` |
| `api` | API request metrics; not emitted (see above) |
| `toast` | Toast notifications: `level`, `message`, `code?`, `exception?`, `action?` |
| `error` | Uncaught errors (`scope: 'global'`) and unhandled promise rejections (`scope: 'promise'`) |
| `query_error` | React Query failures with metadata |
| `ui_state` | Workflow readiness: `auth`, `devices.flash-modal.images`, `devices.flash-modal.flash` |
| `list_loading` | List loading lifecycle: `devices.list`, `device-models.list`, `coredumps.list`, `rotation.dashboard`, `devices.logs` |
| `sse` | Server-sent event stream lifecycle (`open`, `message`, `error`, `close`) |
| `provisioning` | The app's own: Provision device's `started`, `progress`, `complete` and `error`, with `deviceId` and `metadata.provisioningPhase` |

The template's kinds are `TestEventKind` in `src/lib/test/test-events.ts`. `provisioning` is
outside that union: `src/types/provisioning-events.ts` types it, and
`src/lib/test/provisioning-instrumentation.ts` emits it. Details live in
[Test Instrumentation](../architecture/test_instrumentation.md).

## Implementation Checklist

- [ ] Forms and mutation flows call `useFormInstrumentation` with a stable `formId`, and
      `trackSubmit`, `trackSuccess` and `trackError` around the mutation.
- [ ] Validation a spec asserts on is visible on the element (`data-state`, a disabled Save) or
      emitted through `trackValidationError`.
- [ ] Error toasts come from the mutation hook's `onError` or the query client's default; a
      component's own `onError` only tracks the error and resets local state.
- [ ] Tests mark intentional console errors with `expectConsoleError`.
- [ ] New instrumentation is guarded by `isTestMode()`.
