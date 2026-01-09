# Error Handling & Validation Patterns

The frontend ships with a centralized instrumentation layer that surfaces error states to Playwright through structured test-event payloads and console policies. This guide explains how to integrate forms, mutations, and validation flows so tests can assert on observable signals.

## Form Instrumentation

Use helpers from `@/lib/test/form-instrumentation` to emit lifecycle events. Generate a stable `formId` and emit events at each phase.

```typescript
import {
  generateFormId,
  trackFormOpen,
  trackFormSubmit,
  trackFormSuccess,
  trackFormError,
  trackFormValidationError,
  trackFormValidationErrors,
} from '@/lib/test/form-instrumentation';

const formId = generateFormId('TypeForm', mode); // mode: 'create' | 'edit'

trackFormOpen(formId);
trackFormSubmit(formId, formData);
try {
  await mutation.mutateAsync(formData);
  trackFormSuccess(formId, formData);
} catch (error) {
  trackFormError(formId, error);
}
```

### Validation Events

Emit field-level or aggregate validation errors so tests can assert precise behavior.

```typescript
if (fieldError) {
  trackFormValidationError(formId, 'name', fieldError.message);
}

const errors = form.validate();
if (Object.keys(errors).length) {
  trackFormValidationErrors(formId, errors);
}
```

Event payload shape:

```json
{
  "kind": "form",
  "phase": "validation_error",
  "formId": "TypeForm_create",
  "metadata": {
    "field": "name",
    "error": "Name is required"
  }
}
```

## Query & Mutation Errors

React Query hooks are wrapped by `@/lib/test/query-instrumentation` and `@/lib/test/error-instrumentation`:

- Automatically emits a `query_error` test event with `{ queryKey, status, message, correlationId }` on failures.
- Marks HTTP `409` conflicts with `metadata.isConflict=true` to support optimistic concurrency tests.
- Captures network failures and normalized error messages produced by `src/lib/utils/error-parsing.ts`.

Tests can wait for these events when validating fallback UI:

```typescript
import { expectConflictError } from '../support/helpers';

await expectConflictError(page);
await expect(page.getByRole('status')).toContainText(/already exists/i);
```

## Console Error Policy

The Playwright fixture fails tests on unexpected `console.error` messages. Allow expected errors explicitly:

```typescript
import { expectConsoleError } from '../support/helpers';

await expectConsoleError(page, /cannot delete type/i);
await types.attemptDelete(blockedType.name);
```

Avoid sprinkling `console.error` in production code—rely on the centralized error handling system so instrumentation stays consistent.

## Toast Notifications

`@/lib/test/toast-instrumentation` emits `toast` test events with `{ level, code, message }` whenever the toast provider shows a message. Prefer asserting on the UI element (`getByRole('status')`) and use the event stream for supplementary checks in complex flows.

## Router & API Events

- `@/lib/test/router-instrumentation` emits `route` test events for navigation, including `from`, `to`, and optional params.
- `@/lib/test/api-instrumentation` (optional integration) captures REST calls with `operation`, `method`, `status`, `correlationId`, `durationMs`.

These events help correlate UI state with backend activity when debugging failures.

## Test-Event Taxonomy Reference

| Kind | Use case |
| --- | --- |
| `route` | Navigation changes (`from`, `to`, `params`) |
| `form` | Form lifecycle: `open`, `submit`, `success`, `error`, `validation_error` |
| `api` | API request metrics: name, method, status, correlationId |
| `toast` | Toast notifications: level, code, message |
| `error` | Global errors surfaced to users |
| `query_error` | React Query failures with metadata |
| `sse` | Server-sent event stream lifecycle (`open`, `message`, `error`, `close`) |

Details live in [Test Instrumentation](../architecture/test_instrumentation.md) and the source file `src/types/test-events.ts`.

## Implementation Checklist

- [ ] Forms call `generateFormId` and emit lifecycle events.
- [ ] Validation errors emit `validation_error` phase.
- [ ] Mutations rely on centralized error handling; no inline `onError` unless absolutely necessary.
- [ ] Tests mark intentional console errors with `expectConsoleError`.
- [ ] New instrumentation is guarded by `isTestMode()`.
