# Selector Patterns

Selectors must be stable and owned by the feature under test. The app's page objects find the
elements a spec drives by `data-testid`, and keep every selector inside the page object so a markup
change stays local. This guide covers the selector order, the test-id naming scheme, and what the
shared selector files in `tests/support/` are.

## Principles

1. **Test IDs for what a spec drives** – Every element a spec clicks or asserts on carries a
   `data-testid`, and the page object locates it by that id.
2. **Page objects, not selector maps** – Specs reach elements through the feature's page object
   (`DevicesPage`, `RotationPage`, `AuthPage`), which returns Playwright `Locator`s and actions
   rather than selector strings.
3. **Feature ownership** – Page objects sit beside the specs that use them (`tests/e2e/<feature>/`).
4. **Roles and text inside a scope** – A dialog's buttons and a select's options are found by their
   label, inside a test-id'd container.
5. **Avoid CSS/XPath** – Class selectors are for third-party widgets that cannot carry a test id,
   such as the Monaco editor (`.monaco-editor`).

## Shared Selector Files

`tests/support/` holds three selector modules; no spec or page object imports any of them:

- `tests/support/test-id.ts` (template) – `testId(id)`, which returns `[data-testid="<id>"]`.
- `tests/support/selectors.ts` (template) – re-exports `testId`, a `selectors.common` map
  (`loading`, `error`, `toast`, `search`, `pagination.*`) and
  `buildSelector(domain, section, element, id?)`. No element in this app carries those common ids.
- `tests/support/selectors-domain.ts` (app-owned) – holds only a comment: the place the template
  leaves for a domain selector map.

`knip-template-ignore.json` lists all three, so knip does not report them as unused. A new
selector goes into the feature's page object as a locator or method; if the element has no
`data-testid`, add one to the component and use it from the page object.

## Page Object Structure

The app's page objects are plain classes over a `Page` that expose locators as getters. A trimmed
excerpt of `tests/e2e/devices/DevicesPage.ts`:

```typescript
import type { Page, Locator } from '@playwright/test';

export class DevicesPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/devices');
  }

  get list(): Locator {
    return this.page.locator('[data-testid="devices.list.table"]');
  }

  rowByKey(key: string): Locator {
    return this.page.locator(`[data-testid="devices.list.row"][data-device-key="${key}"]`);
  }

  get deleteConfirmDialog(): Locator {
    return this.page.locator('[data-testid="devices.delete.confirm-dialog"]');
  }

  async deleteDeviceByKey(key: string) {
    await this.rowByKey(key).locator('[data-testid="devices.list.row.delete-button"]').click();
  }

  async confirmDelete() {
    await this.deleteConfirmDialog.locator('button:has-text("Delete")').click();
  }
}
```

Key takeaways:
- Return `Locator` instances so specs can assert on them and chain from them.
- Key a row on the data attribute the component puts on it (`data-device-key`, `data-device-id`,
  `data-coredump-id`), not on its text.
- Find a dialog's buttons inside the dialog's locator, so a same-named button elsewhere cannot
  match.

[Page Objects](./page_objects.md) covers the rest of the class.

## Selector Priority Order

1. **`data-testid`** – The page objects write it as `page.locator('[data-testid="…"]')`, which
   combines with attribute filters (`[data-testid="devices.list.row"][data-device-id="42"]`); the
   template's `AppShellPage` uses `page.getByTestId(...)`. Both read the same attribute.
2. **Roles and text within a test-id'd scope** – dialog buttons
   (`deleteConfirmDialog.locator('button:has-text("Delete")')`), select options
   (`[role="option"]:has-text("…")` in `selectModel`), headings
   (`page.getByRole('heading', { name: 'Devices' })` in `smoke.spec.ts`), and
   `locator.filter({ hasText })` on a list of test-id'd entries.
3. **CSS** – last resort, for third-party widgets (`.monaco-editor`).

```typescript
// The element by its test id
devicesPage.flashModalConnectButton;      // [data-testid="devices.flash-modal.connect-button"]
rotationPage.rowByDeviceId(device.id);    // [data-testid="rotation.dashboard.row"][data-device-id="…"]

// Text within a test-id'd collection
devicesPage.logsEntries.filter({ hasText: message });

// State is an attribute on the test-id'd element
await expect(devicesPage.tabLogs).toHaveAttribute('aria-current', 'page');
await expect(devicesPage.jsonEditorContainer).toHaveAttribute('data-state', 'invalid');
```

## Test ID Naming

Ids are dot-separated, lower-case, kebab-case segments that run from the feature down to the
element: `<feature>.<area>[.<section>].<element>`.

| Test id | Element |
| --- | --- |
| `devices.list.table` | The device list |
| `devices.list.row` | One device row |
| `devices.list.row.delete-button` | That row's delete button |
| `devices.editor.save` | The device editor's Save button |
| `devices.detail.tab.logs` | The Logs tab on a device |
| `devices.flash-modal.connect-button` | Flash device's Connect button |
| `devices.provision-modal.success-message` | Provision device's success message |
| `coredumps.table.row` | One core dump row |
| `rotation.dashboard.panel.healthy` | The rotation dashboard's healthy panel |
| `app-shell.sidebar.link.devices` | The sidebar's Devices link (template) |

The scheme in practice:

- **Features** – `devices`, `coredumps`, `device-models` and `rotation` are the app's; `app-shell`,
  `auth` and `deployment` come from the template.
- **Children extend their parent** – `devices.list.row` → `devices.list.row.active`,
  `devices.list.row.delete-button`.
- **States are siblings in the same area** – `devices.list.loading`, `devices.list.empty`,
  `devices.list.error`; `coredumps.table.loading`, `coredumps.table.empty`, `coredumps.table.error`.
- **Dialogs** – `devices.delete.confirm-dialog`, `coredumps.delete.confirm-dialog`,
  `devices.editor.unsaved-changes-dialog`, `rotation.dashboard.confirm-dialog`. A `ConfirmDialog`
  takes its id through `contentProps={{ 'data-testid': … }}`.
- **Generated segments keep their source value** – column headers are
  `devices.list.header.<column>` with the sort column's id (`devices.list.header.key`,
  `devices.list.header.lastCoredumpAt`); rotation panels are
  `rotation.dashboard.panel.<category>` (`healthy`, `warning`, `critical`); sidebar links are
  `app-shell.sidebar.link.<slug>`.
- **Primitives derive ids from a base** – `RoutedTabs` with `testIdPrefix="devices.detail"` renders
  `devices.detail.tabs` and a `devices.detail.tab.<value>` per tab unless the tab sets its own
  `testId` (the device header sets `devices.detail.tab.configuration`, `.logs` and `.coredumps`);
  `Alert` adds `<testId>.dismiss`, `EmptyState` adds `<testId>.cta`, and `Tooltip` adds
  `<testId>.tooltip` or `<testId>.disabled-wrapper`
  ([Tooltip Guidelines](../ui/tooltip_guidelines.md)).
- **State lives in attributes, not in the id** – rows carry `data-device-id`, `data-device-key`,
  `data-coredump-id`, `data-rotation-state` and `data-active-state`; the JSON editors carry
  `data-state="valid|invalid"`; the logs container carries `data-scroll-at-bottom` and
  `data-log-count`; the active tab carries `aria-current="page"`.

## Adding New Test IDs

- Place the attribute on the smallest stable element (`data-testid="devices.editor.save"`), and
  extend the existing id of its parent rather than starting a new prefix.
- Expose state a spec needs as a data attribute on that element instead of encoding it in the id.
- `data-testid` attributes ship in production builds; only test events are guarded with
  `isTestMode()`.

## Accessibility Matters

Selectors based on roles and labels double as accessibility checks. When a control a spec finds by
role or label lacks one, add it to the component rather than falling back to a CSS selector.

Related reading: [Page Objects](./page_objects.md) and [No-Sleep Patterns](./no_sleep_patterns.md).
