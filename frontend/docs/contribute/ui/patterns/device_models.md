# Device Models Pattern

## When To Use
Apply this pattern to an entity with a handful of fields and perhaps a JSON document, listed in a sortable table and edited on its own page, with no view beyond its editor. Device models are the implementation: `src/components/device-models/` and the routes under `src/routes/device-models/`.

## Routes
| Route | File | Renders |
|-------|------|---------|
| `/device-models` | `src/routes/device-models/index.tsx` | The page header, then `DeviceModelListTable`, or the empty or error state |
| `/device-models/new` | `src/routes/device-models/new.tsx` | `DeviceModelEditor` with `mode="new"` |
| `/device-models/$modelId` | `src/routes/device-models/$modelId.tsx` | Loads the model with `useDeviceModel`, then `DeviceModelEditor` with `mode="edit"` and the model's code, name and schema as initial values |

## UX Expectations
- **List.** Columns Code, Name and Devices sort (name ascending by default, held in component state); Schema shows Defined or None, Firmware the version the model's devices get or a dash. Clicking a row opens the model's editor.
- **Delete.** Each row has a delete button whose `title` reads "Delete model", or "Cannot delete: model has devices" when it has devices. For a model with devices the confirmation is informational ("Cannot Delete Model") and nothing is deleted; otherwise a destructive "Delete Device Model" confirmation ends with "This action cannot be undone."
- **Editor.** A header with the title (`New Device Model`, or `Edit Device Model: <code>`) and Cancel / Save, over three fields: Model Code (an input when new, read-only text once created), Model Name, and the configuration JSON Schema in Monaco with an **Insert Template** button that fills in a starter schema. An empty schema means the model's devices are not validated.
- Saving shows a toast and returns to `/device-models`. Cancel with unsaved changes asks before discarding; leaving the page any other way with unsaved changes opens the navigation-blocker dialog.
- Firmware is not edited here: each firmware repository's CI uploads its builds ([product brief → Device Models](../../../product_brief.md#device-models)).

## Implementation Checklist
- Read through `useDeviceModels()` (returns `deviceModels: DeviceModelSummary[]` with the query state) and `useDeviceModel(id)` (returns `deviceModel`, including `configSchema`); write through `useCreateDeviceModel`, `useUpdateDeviceModel` and `useDeleteDeviceModel`. All live in `src/hooks/use-device-models.ts`, wrap the generated hooks (`useGetDeviceModels`, `usePostDeviceModels`, `usePutDeviceModelsByModelId`, …), map snake_case to camelCase, invalidate `getDeviceModels` (and `getDeviceModelsByModelId` on update) and toast the outcome.
- Parse the route param with `parseInt(modelId, 10)`; an unparseable id renders "Invalid model ID" and a **Back to Device Models** button, and a failed load or a missing model renders its message with the same button.
- Build the list page's loading, empty and error states and the table's sort headers and clickable rows as described in [Data Display Conventions](../data_display.md).
- Build the editor as described in [Form Conventions](../forms.md): `useState` fields, a `useMemo` dirty check, `useBlocker` with its `ConfirmDialog`, `useConfirm` on Cancel, and `isNavigatingRef` around the editor's own navigation.

## Testing & Instrumentation
- The list registers `useListLoadingInstrumentation` with the scope `device-models.list` and `{ visible, total }` as its ready metadata.
- The editor calls `useFormInstrumentation` with the form id `DeviceModelEditor_new` or `DeviceModelEditor_edit`.
- Test ids: `device-models.list.table`, `.list.row` (with `data-model-id` and `data-model-code`), `.list.row.delete-button`, `.list.header.<code|name|deviceCount>`, `.list.header.new-model`, `.list.loading`, `.list.empty`, `.list.error`; `device-models.delete.confirm-dialog`; and on the editor `device-models.editor`, `.editor.code-input`, `.editor.code-display`, `.editor.name-input`, `.editor.schema-editor` (with `data-state`), `.editor.insert-template`, `.editor.save`, `.editor.cancel`, `.editor.unsaved-changes-dialog`, `.editor.navigation-blocker-dialog`.
- No Playwright spec covers this surface; the device specs seed models through the `deviceModels` factory (`tests/api/factories/device-models.ts`). A change here ships with a spec and page object under `tests/e2e/device-models/`, following the foldering in [Testing](../../testing/index.md#test-taxonomy).

## Extensions & Variations
- A new field adds its `useState`, its term in the dirty check, and its mapping in the domain hook's request body; it stays on the editor page.
- A field that references another entity uses `Select` from `src/components/ui/select.tsx`, as the device editor's model picker does.
- An entity that needs views beyond its editor — related records, live data, actions that run in steps — follows the [Devices Pattern](./devices.md) instead: a detail layout route with routed tabs.

## References
- `src/routes/device-models/index.tsx` — the list page: data, sort state, delete flow, states and instrumentation.
- `DeviceModelListTable` (`src/components/device-models/device-model-list-table.tsx`) — the sortable table and its loading skeleton.
- `DeviceModelEditor` (`src/components/device-models/device-model-editor.tsx`) — the editor for both modes, its validation, blocker and form instrumentation.
- `src/hooks/use-device-models.ts` — the domain hooks and the camelCase models.
