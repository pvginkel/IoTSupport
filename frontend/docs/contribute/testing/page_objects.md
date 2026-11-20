# Page Objects

Page objects encapsulate feature-specific UI interactions so specs stay focused on behavior. They
live next to their specs under `tests/e2e/<feature>/` and expose both locators and the actions
several specs share.

## Structure

A trimmed excerpt of `tests/e2e/rotation/RotationPage.ts`:

```typescript
import type { Page, Locator } from '@playwright/test';

export class RotationPage {
  constructor(private page: Page) {}

  // Navigation
  async goto() {
    await this.page.goto('/rotation');
  }

  // Locators
  get dashboard(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard"]');
  }

  get panels(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.panels"]');
  }

  get confirmDialog(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.confirm-dialog"]');
  }

  rowByDeviceId(deviceId: number): Locator {
    return this.page.locator(`[data-testid="rotation.dashboard.row"][data-device-id="${deviceId}"]`);
  }

  // Actions
  async waitForDashboardLoaded() {
    await this.dashboard.waitFor({ state: 'visible', timeout: 15_000 });
    await this.panels.waitFor({ state: 'visible', timeout: 15_000 });
  }

  async confirmTrigger() {
    await this.confirmDialog.locator('button:has-text("Trigger Rotation")').click();
  }
}
```

### Guidelines

- **Locators as getters** – one getter per element a spec touches, each a `Locator` on the
  element's `data-testid` ([Selector Patterns](./selector_patterns.md)).
- **Rows keyed by data attribute** – `DevicesPage.rowByKey(key)`, `rowById(id)`,
  `coredumpRowById(id)` and `RotationPage.rowByDeviceId(id)` match the row's test id plus its
  `data-*` attribute.
- **Navigation apart from readiness** – the app's `goto*()` methods only navigate; the page's own
  `waitFor*()` method waits for its signal: `DevicesPage.waitForListLoaded()` (the table or the
  empty state), `waitForEditorLoaded()` (the editor and Monaco), `waitForCoredumpsTabLoaded()`,
  `RotationPage.waitForDashboardLoaded()`, `AuthPage.waitForAuthenticated()` (the top bar).
- **Actions for shared workflows** – `clickTab('configuration' | 'logs' | 'coredumps')`,
  `selectModel(name)`, `setJsonObject(obj)`, `deleteDeviceByKey(key)` then `confirmDelete()`.
- **Keep assertions intentional** – an action waits only for what is its contract:
  `openFlashModal()` and `openProvisionModal()` click the button and wait for the modal to show,
  `closeProvisionModal()` waits for it to hide. Everything else is the spec's to assert.

## Ownership & Organization

- Each feature folder has one page object beside its specs: `tests/e2e/devices/DevicesPage.ts`
  (the device list, the editor and its duplicate route, the detail header and tabs, logs, core
  dumps, and the Flash device and Provision device modals), `tests/e2e/rotation/RotationPage.ts`
  and `tests/e2e/auth/AuthPage.ts`.
- Page objects are not fixtures: a spec constructs its own (`new DevicesPage(page)`); the
  [fixtures](./factories_and_fixtures.md#test-fixtures) are factories and helpers.
- A multi-step flow only one spec file needs stays in that file as a local function — `provision()`
  in `devices-provisioning.spec.ts` and `openFlashModal()` in `devices-flashing.spec.ts` open the
  modal through `DevicesPage`, then wait on a test event (the provisioning outcome, the flash
  images loaded).
- The template ships two page objects in `tests/support/page-objects/`, which change through
  `copier update`: `BasePage` (`goto(path)`, `waitForPageLoad()`, `getButton()`, `getLink()`,
  `waitForToast()`, `expectToast()`) and `AppShellPage`, which extends it with the top bar, sidebar,
  mobile menu, toast viewport and deployment banner, and is the `appShell` fixture.

## Navigation Methods

`DevicesPage` has one `goto*()` per route a spec opens:

| Method | Route |
| --- | --- |
| `goto()` | `/devices` |
| `gotoNew()` | `/devices/new` |
| `gotoEdit(id)` | `/devices/<id>`, which redirects to the tab last used in the browser — `edit` (the Configuration tab) in a test's fresh context |
| `gotoDuplicate(id)` | `/devices/<id>/duplicate` |
| `gotoLogs(id)` | `/devices/<id>/logs` |
| `gotoCoredumps(id)` | `/devices/<id>/coredumps` |
| `gotoCoredumpDetail(id, coredumpId)` | `/devices/<id>/coredumps/<coredumpId>` |

## Interacting with Components

- **Confirm dialogs** – each `ConfirmDialog` carries a test id, and the page object clicks its
  buttons by label inside it: `confirmDelete()`/`cancelDelete()`, `confirmDiscard()`/
  `cancelDiscard()` on the unsaved-changes dialog, `confirmCoredumpDelete()`/
  `cancelCoredumpDelete()`, `confirmCloseProvisioning()` (`Yes, Cancel`) and
  `cancelCloseProvisioning()` (`Continue`).
- **Selects** – `selectModel(name)` and `selectDownloadLineCount(count)` open the select by its test
  id and click the matching `[role="option"]`.
- **Monaco** – `setJsonContent(content)` sets the editor's value through `window.monaco`;
  `setJsonObject(obj)` serializes an object into it.
- **USB** – Flash device and Provision device need the fake USB device installed before the page
  loads (`installFakeEspDevice(page)`); the page object only clicks Connect
  (`flashModalConnectButton`, `startProvisioning()`). See
  [Factories & Fixtures → The Fake USB Device](./factories_and_fixtures.md#the-fake-usb-device).
- **Toasts** – use the `toastHelper` fixture, which reads `app-shell.toast.item`, rather than a
  page-object locator.

## Relation to Helpers

- Page objects drive the UI; `tests/support/helpers.ts` waits on instrumentation (`waitTestEvent`,
  `waitForUiState`, `waitForListLoading`) and registers expected console errors.
- Seed what the test needs through the `devices` and `deviceModels` factories before calling the
  page object:

```typescript
test('confirms delete removes device', async ({ page, devices }) => {
  const device = await devices.create({ deviceName: 'Delete Me' });

  const devicesPage = new DevicesPage(page);
  await devicesPage.goto();
  await devicesPage.waitForListLoaded();

  await devicesPage.deleteDeviceByKey(device.key);
  await devicesPage.confirmDelete();

  await expect(devicesPage.rowByKey(device.key)).not.toBeVisible({ timeout: 10000 });
});
```

## Checklist for New Page Objects

- [ ] Lives in `tests/e2e/<feature>/` as `<Feature>Page.ts`.
- [ ] Has a `goto*()` method per route its specs open, and a `waitFor*()` method that waits for the
      page's own signal.
- [ ] Exposes locators as getters and keys rows by their data attribute.
- [ ] Uses the selector order outlined in [Selector Patterns](./selector_patterns.md).
- [ ] Constructed by the spec; shared seeding goes into a factory fixture, not the page object.

Related docs: [Playwright Developer Guide](./playwright_developer_guide.md), [Factories & Fixtures](./factories_and_fixtures.md).
