# No-Sleep Patterns

Never rely on fixed delays in Playwright tests. This reference shows how to wait for observable
signals instead of `waitForTimeout`.

## Rules of Thumb

1. **Every wait needs a signal** – UI visibility, a URL, a test-event payload, a browser event
   (download, request), or backend state polled with `expect(...).toPass()`.
2. **Prefer UI assertions** – `expect(locator)` assertions retry until they pass or time out; if
   the user can see it, assert it.
3. **Reserve test events for what the UI does not show** – the metadata of a flash, the outcome of
   provisioning, a list that finished loading empty.

## Common Scenarios

### Dialogs & Modals

```typescript
// Avoid
await page.waitForTimeout(500);

// Do this instead
await devicesPage.deleteDeviceByKey(device.key);
await expect(devicesPage.deleteConfirmDialog).toBeVisible();

await devicesPage.cancelDelete();
await expect(devicesPage.deleteConfirmDialog).not.toBeVisible();
```

`DevicesPage.openFlashModal()` and `openProvisionModal()` click the button and wait for the modal
to show, so a spec can use the modal straight after.

### Saving a Form

Wait for what the save does — the device editor navigates on success:

```typescript
await devicesPage.save();

// After saving in edit mode, the user is taken to the device's logs tab
await expect(page).toHaveURL(`/devices/${device.id}/logs`);
await expect(devicesPage.tabLogs).toHaveAttribute('aria-current', 'page');
```

Validation shows on the element, so assert its state rather than waiting for it to settle:

```typescript
await devicesPage.setJsonContent('{ invalid json }');

await expect(devicesPage.saveButton).toBeDisabled();
await expect(devicesPage.jsonEditorContainer).toHaveAttribute('data-state', 'invalid');
```

### Lists

```typescript
// Avoid substring :has-text selectors over every row
await expect(page.locator('[data-testid="devices.list.row"]:has-text("Kitchen")')).toBeVisible();

// Do this instead: the row keyed by its data attribute
await expect(devicesPage.rowByKey(device.key)).toBeVisible();
// or the text filtered within a test-id'd collection
await expect(devicesPage.logsEntries.filter({ hasText: message })).toBeVisible({ timeout: 10_000 });
```

`DevicesPage.waitForListLoaded()` waits for whichever shows first, the table or the empty state.
List components also emit `list_loading` events — scopes `devices.list`, `device-models.list`,
`coredumps.list`, `rotation.dashboard` and `devices.logs` — for
`waitForListLoading(page, scope, 'ready')`.

### Navigation

```typescript
await devicesPage.clickTab('coredumps');
await expect(page).toHaveURL(`/devices/${device.id}/coredumps`);
await expect(devicesPage.tabCoredumps).toHaveAttribute('aria-current', 'page');
```

### Toast Notifications

Toasts render as `app-shell.toast.item`; the `toastHelper` fixture waits on them:

```typescript
await toastHelper.expectSuccessToast(/updated successfully/i);
// or
await toastHelper.waitForToastWithText('Device created successfully');
```

### Downloads and Requests

Start waiting before the action that causes the event:

```typescript
const [download] = await Promise.all([
  page.waitForEvent('download'),
  devicesPage.logsDownloadDialogSubmit.click(),
]);
```

`auth.spec.ts` does the same with `page.waitForRequest(...)` to catch the login redirect.

### Server-Sent Events

The SSE stream does not connect by itself in test mode. Connect it with the `deploymentSse` fixture
before the action whose event the page must receive:

```typescript
await devicesPage.gotoEdit(device.id);
await deploymentSse.ensureConnected();
await devicesPage.clickTab('logs');
```

### Backend State the Page Does Not Show

Poll it with `expect(...).toPass()` rather than a sleep-and-retry loop — `devices-logs-sse.spec.ts`
waits for the backend to register the page's log subscription:

```typescript
await expect(async () => {
  const resp = await page.request.get(
    `${frontendUrl}/api/testing/devices/logs/subscriptions?device_entity_id=${encodeURIComponent(entityId)}`,
  );
  expect(resp.ok()).toBe(true);
  const data = await resp.json();
  expect(data.subscriptions?.length).toBeGreaterThan(0);
}).toPass({ timeout: 15_000 });
```

## Test Events When Necessary

Use `waitTestEvent` and its wrappers when no UI signal carries what the spec asserts. Provision
device ends on a `provisioning` event:

```typescript
import { waitTestEvent } from '../../support/helpers';

await devicesPage.startProvisioning();
const ended = await waitTestEvent<ProvisioningTestEvent>(
  page,
  'provisioning',
  event => event.deviceId === deviceId && (event.phase === 'complete' || event.phase === 'error')
);
```

Flash device reports through `ui_state` scopes, which `waitForUiState` waits on:

```typescript
await devicesPage.flashModalConnectButton.click();
const flashed = await waitForUiState(page, 'devices.flash-modal.flash', 'ready');
expect(flashed.metadata).toMatchObject({ outcome: 'success', firmwareVersion: '2.3.4' });
```

The suite runs the app under React StrictMode, which mounts a component twice; a scope the first
mount opened ends with `metadata.status === 'aborted'`. Filter those out when the first `ready`
could be the aborted one, as `devices-flashing.spec.ts` does for `devices.flash-modal.images`.

## Animation Guardrails

The `page` fixture emulates reduced motion and sets every transition and animation duration to
zero, so a spec does not wait out animations.

## Checklist

- [ ] No `waitForTimeout` or magic numbers.
- [ ] Assertions describe observable behavior.
- [ ] Test-event helpers used where the UI has no signal, not instead of one.
- [ ] Page objects expose meaningful locators to keep waits readable.

Related docs: [Playwright Developer Guide](./playwright_developer_guide.md), [Factories & Fixtures](./factories_and_fixtures.md), [Test Instrumentation](../architecture/test_instrumentation.md).
