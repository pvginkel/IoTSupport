# Devices Pattern

## When To Use
Follow this pattern for an entity that users browse in a table, open into a page with several views, create and duplicate on their own pages, and act on outside the request/response cycle — over USB from the browser, or live over the SSE stream. Devices are the implementation: `src/components/devices/`, the routes under `src/routes/devices/`, and the hooks `use-devices.ts`, `use-device-form.ts`, `use-coredumps.ts`, `use-device-logs.ts`, `use-flash-device.ts` and `use-provisioning.ts` in `src/hooks/`.

## Routes
| Route | File | Renders |
|-------|------|---------|
| `/devices` | `src/routes/devices/index.tsx` | The page header, then `DeviceListTable`, or the empty or error state |
| `/devices/new` | `src/routes/devices/new.tsx` | `DeviceEditor` with `mode="new"`; the search params `config`, `modelId` and `from` prefill it |
| `/devices/$deviceId` | `src/routes/devices/$deviceId.tsx` | Layout route: loads the device, renders `DeviceDetailHeader` and the tab's `<Outlet />`; under `/duplicate` it renders the outlet alone |
| `/devices/$deviceId/` | `src/routes/devices/$deviceId/index.tsx` | Redirects to the last-used tab with `useRestoreTab` (default `edit`) |
| `/devices/$deviceId/edit` | `src/routes/devices/$deviceId/edit.tsx` | `DeviceConfigurationTab` |
| `/devices/$deviceId/logs` | `src/routes/devices/$deviceId/logs.tsx` | `DeviceLogsTab` |
| `/devices/$deviceId/coredumps` | `src/routes/devices/$deviceId/coredumps.tsx` (an outlet) and `coredumps/index.tsx` | `CoredumpAccordionTable` |
| `/devices/$deviceId/coredumps/$coredumpId` | `src/routes/devices/$deviceId/coredumps/$coredumpId.tsx` | `CoredumpAccordionTable` with that dump expanded |
| `/devices/$deviceId/duplicate` | `src/routes/devices/$deviceId/duplicate.tsx` | Loads the device, then `DeviceEditor` with `mode="duplicate"` prefilled with its model and configuration |

## UX Expectations
- **List.** Device Key, Device Name, Model, Entity ID, Rotation State, OTA Status, Last Core Dump and Active all sort; the sort persists in localStorage. Clicking a row opens `/devices/$deviceId`. Delete asks "Delete device <key>? This action cannot be undone."
- **New device.** A model `Select` (with the selected model's device count and firmware version below it), a checked, disabled Active checkbox ("New devices are always created as active"), and the configuration JSON in Monaco, prefilled with a `deviceName` / `deviceEntityId` / `enableOTA` template and validated against the model's schema. Saving returns to `/devices`.
- **Duplicate.** The Configuration tab's **Duplicate** button opens `/devices/new` with the editor's current JSON, the model id and the source key in the search params, titled "Duplicate Device: <key>". `/devices/$deviceId/duplicate` does the same from the stored device. Either way the save creates a new device.
- **Detail.** The sticky `DeviceDetailHeader`: a back link, "Edit Device: " and the device's name (or entity id, or key), its key, a link to its model, the rotation-state badge and OTA status, then the Configuration, Logs and Core Dumps tabs, the last with a count when the device has dumps. The active tab is stored under `DEVICE_TAB_STORAGE_KEY`, and `/devices/$deviceId` reopens it.
- **Configuration tab.** `KeycloakClientStatus` (the client id with a console link and a resync button, or "Client not found in Keycloak" with **Recreate Client**), the model as a link, the Active checkbox ("Whether device participates in automatic fleet rotation"), and the configuration JSON. Below them, **Flash Device** and **Provision Device** on the left and Cancel, Duplicate and Save on the right. Saving moves to the Logs tab.
- **Logs tab.** An empty state when the device has no entity id; otherwise `DeviceLogsViewer`, live over the SSE stream, loading older entries when scrolled to the top, with a **Download** button that opens `DeviceLogsDownloadDialog` (100, 500, 1,000, 5,000 or 10,000 lines).
- **Core dumps tab.** Newest first: uploaded at, firmware, size and parse status, with a download link and a delete button per row. A row click expands it — one at a time — and the URL follows (see [Data Display → Detail Surfaces](../data_display.md#detail-surfaces)).
- **Flash Device.** `FlashDeviceModal` checks for Web Serial (`isWebSerialSupported` from `src/lib/esptool`), loads the device's flash images with `useDeviceFlashImages`, and shows the firmware version and its images (offset, image, size), or why there is nothing to flash. **Connect** runs `useFlashDevice().startFlash`; a progress bar and status line follow, then success or the error with **Retry**. Closing mid-flash asks "Cancel Flashing?". The design is in [Firmware flashing → Flash device](../../../../../docs/firmware-flashing.md#flash-device).
- **Provision Device.** `ProvisionDeviceModal` drives `useProvisioning` the same way: instructions and **Connect**, progress, then "Provisioning Complete" or the error with **Retry**; closing mid-run asks "Cancel Provisioning?". The design is in [device provisioning](../../../../../backend/docs/device_provisioning_design.md).

## Implementation Checklist
- **Hooks.** `src/hooks/use-devices.ts` has `useDevices`, `useDevice`, `useCreateDevice`, `useUpdateDevice`, `useDeleteDevice`, `useDeviceKeycloakStatus`, `useSyncDeviceKeycloak` and `useDeviceFlashImages`. `useDeviceForm` (`src/hooks/use-device-form.ts`) serves the editor in all three modes. Core dumps go through `useCoredumps`, `useCoredump` and `useDeleteCoredump` (`src/hooks/use-coredumps.ts`), logs through `useDeviceLogs` (`src/hooks/use-device-logs.ts`), and the USB actions through `useFlashDevice` and `useProvisioning`.
- **Layout route.** Fetch in the layout and handle the invalid id, loading and not-found states there. The child routes call `useDevice` with the same id, answered from the query cache, and render `null` until it resolves.
- **Routed tabs.** Define the tabs as `RoutedTabDefinition[]` (`to`, `params`, `value`, `label`, `testId`) and render `RoutedTabs` with `testIdPrefix`, `storageKey` and a `basePath` ending in a slash. The index route calls `useRestoreTab({ storageKey, validValues, defaultValue, toPath })`. Export the storage key and the valid tab values beside the header (`DEVICE_TAB_STORAGE_KEY`, `DEVICE_TAB_VALUES`) so the index route and `useDeviceForm` share them.
- **URL-synced expansion.** Update the URL with `window.history.replaceState` rather than `navigate`, so expanding a row does not remount the route.
- **USB modals.** Each owns a `Dialog` with its test id on `contentProps`. `FlashDeviceModal` mounts its body only while open, so every opening fetches the images afresh. Both intercept `onOpenChange(false)` while running and confirm before aborting.
- **Live data.** Subscribe through `useSseContext` (`src/contexts/sse-context.ts`), as `useDeviceLogs` and `useRotationDashboard` do.

## Testing & Instrumentation
- `list_loading` scopes: `devices.list` and `coredumps.list` (through `useListLoadingInstrumentation`), and `devices.logs` (emitted by `useDeviceLogs`).
- `ui_state` scopes: `devices.flash-modal.images` and `devices.flash-modal.flash` (through `useUiStateInstrumentation`).
- Provisioning emits `provisioning` events — `started`, `progress`, `complete`, `error` — through `useProvisioningInstrumentation` (`src/lib/test/provisioning-instrumentation.ts`), which calls the Playwright binding directly because the kind is not in the template's `TestEvent` union.
- Form ids: `DeviceEditor_new` (including a duplicate opened through `/devices/new`), `DeviceEditor_duplicate`, `DeviceEditor_edit`, and `CoredumpDelete` for a core dump's deletion.
- Test-id families: `devices.list.*`, `devices.delete.confirm-dialog`, `devices.detail.header.*`, `devices.detail.tabs` and `devices.detail.tab.<configuration|logs|coredumps>`, `devices.editor.*` (shared by the editor and the Configuration tab), `devices.logs.*`, `coredumps.table.*`, `coredumps.accordion.*`, `coredumps.delete.confirm-dialog`, `devices.flash-modal.*` and `devices.provision-modal.*`.
- The specs live in `tests/e2e/devices/` with the page object `DevicesPage.ts`; [Testing](../../testing/index.md#test-taxonomy) lists them. Flash and provisioning run against the fake USB device ([Factories & Fixtures → The Fake USB Device](../../testing/factories_and_fixtures.md#the-fake-usb-device)).

## Extensions & Variations
- **A new tab** adds a child route under `src/routes/devices/$deviceId/`, a `RoutedTabDefinition` in `DeviceDetailHeader`, and its value in `DEVICE_TAB_VALUES` so `useRestoreTab` accepts it.
- **A new device action** gets a button in the Configuration tab's action row and a modal built like `FlashDeviceModal`: its own hook for the work, `useUiStateInstrumentation` for its data and its action, and a confirmation before closing mid-run.
- **A new list column** adds the field to `DeviceSummary`, a header and cell in `DeviceListTable`, and the column to `SortPreference` in `src/lib/utils/sort-preferences.ts`, including its list of valid columns.

## References
- `src/routes/devices/index.tsx` and `DeviceListTable` (`src/components/devices/device-list-table.tsx`) — the list, its persisted sort and delete flow.
- `src/routes/devices/$deviceId.tsx` and `DeviceDetailHeader` (`src/components/devices/device-detail-header.tsx`) — the layout route, header and routed tabs.
- `DeviceEditor` (`src/components/devices/device-editor.tsx`), `DeviceConfigurationTab` (`src/components/devices/device-configuration-tab.tsx`) and `useDeviceForm` — the three editor modes.
- `DeviceLogsTab`, `DeviceLogsViewer` and `DeviceLogsDownloadDialog` (`src/components/devices/`) — the live log view and its download.
- `CoredumpAccordionTable` (`src/components/devices/coredump-accordion-table.tsx`) — the accordion table and its URL sync.
- `FlashDeviceModal` and `ProvisionDeviceModal` (`src/components/devices/`) — the USB actions.
