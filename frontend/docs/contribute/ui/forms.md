# Form Conventions

## Scope
The app's forms are full-page editors reached by their own routes, not dialogs:

- `DeviceModelEditor` (`src/components/device-models/device-model-editor.tsx`) on `/device-models/new` and `/device-models/$modelId`;
- `DeviceEditor` (`src/components/devices/device-editor.tsx`) on `/devices/new` and `/devices/$deviceId/duplicate`;
- `DeviceConfigurationTab` (`src/components/devices/device-configuration-tab.tsx`), the device's Configuration tab on `/devices/$deviceId/edit`.

Dialogs carry confirmations and the device actions that run in steps — the log download, Flash device and Provision device — not entity forms.

## Core Building Blocks
- **Page shell.** A header bar (`border-b border-border bg-background p-4`) with the title on the left and the actions on the right, over a scrolling body (`flex-1 overflow-auto p-6`) whose fields sit in `mx-auto max-w-4xl space-y-6`. `DeviceConfigurationTab` renders under the device's header and tabs instead, and puts its actions in a row below the fields.
- **Fields.** A plain `<label>` (`text-sm font-medium text-muted-foreground`), the control, and a hint below it (`text-xs text-muted-foreground`). Text inputs are `Input` (`src/components/primitives/input.tsx`); choices are `Select` with `SelectTrigger`, `SelectValue`, `SelectContent` and `SelectItem` (`src/components/ui/select.tsx`), as in the device editor's model picker.
- **JSON.** Configuration and schemas are edited in Monaco (`@monaco-editor/react`) inside a bordered container that carries the field's test id (`devices.editor.json-editor`, `device-models.editor.schema-editor`) and `data-state="valid"` or `"invalid"`. The device editors give Monaco `path="device-config.json"`, and `useDeviceForm` calls `configureMonacoSchemaValidation` (`src/lib/utils/monaco-schema.ts`) with the selected model's schema, so the editor validates the configuration against it.
- **Actions.** `Button` from `src/components/primitives/button.tsx`: `variant="outline"` for Cancel and secondary actions, `variant="primary"` for Save with `loading={isPending}` and `disabled={!isValid}`. While loading, `Button` overlays a spinner and keeps its label in the layout, so it keeps its width.

## State & Validation
- Field values live in `useState`; the editor derives `isDirty` with `useMemo` by comparing them to the initial values. `useDeviceForm` (`src/hooks/use-device-form.ts`) holds that state, validation, the blocker and the save / cancel / duplicate handlers for all three device modes (`new`, `edit`, `duplicate`); `DeviceModelEditor` keeps the same logic inline.
- Validation runs on every change. A JSON parse failure sets an error message shown beside the field's label and flips the container's `data-state` to `invalid`; Save stays disabled while there is an error or a required value (model code and name, a new device's model) is missing. A model schema must be a JSON object; an empty schema means no validation.
- `useFormState` (`src/hooks/use-form-state.ts`) offers per-field validation rules for a form that needs them; the existing editors do not use it.

## Unsaved Changes
- Each editor blocks navigation while dirty with TanStack Router's `useBlocker({ shouldBlockFn, enableBeforeUnload, withResolver: true })` and renders a `ConfirmDialog` bound to the blocker's `status`, `proceed` and `reset` ("Discard Changes", test id `<scope>.editor.navigation-blocker-dialog`).
- Cancel asks through `useConfirm` + `ConfirmDialog` when the form is dirty (test id `<scope>.editor.unsaved-changes-dialog`).
- An `isNavigatingRef` set before the editor's own navigation — after a save, a confirmed cancel, or Duplicate — lets it past the blocker.

## Submission
- Mutations run through the domain hooks: `useCreateDeviceModel` and `useUpdateDeviceModel` (`src/hooks/use-device-models.ts`), `useCreateDevice` and `useUpdateDevice` (`src/hooks/use-devices.ts`). They wrap the generated hooks, map the editor's camelCase values to the API's snake_case body, invalidate the list (and detail) queries, and show the success and error toasts through `useToast`. Do not call `fetch` or the generated client from a component.
- After a successful save, the model editor returns to `/device-models`, a new or duplicated device to `/devices`, and the Configuration tab moves to the device's Logs tab (`/devices/$deviceId/logs`), writing that tab as the device's tab preference.

## Instrumentation
- Every editor calls `useFormInstrumentation` (`src/hooks/use-form-instrumentation.ts`) with `isOpen: true`, so the form's `open` event fires on mount. It calls `trackSubmit` before the mutation and `trackSuccess` / `trackError` from the mutation's callbacks.
- Form ids are literal strings: `DeviceModelEditor_new`, `DeviceModelEditor_edit`, `DeviceEditor_new`, `DeviceEditor_duplicate`, `DeviceEditor_edit`. The core dump delete in `CoredumpAccordionTable` uses the same hook with `CoredumpDelete`.
- The hook also returns `trackValidationError` / `trackValidationErrors`, which emit the `validation_error` phase that `waitForFormValidationError` in `tests/support/helpers.ts` waits on. The existing editors show validation inline and do not emit it.

## Error Handling & Toasts
- The domain hooks' `onError` shows the mutation's error toast; the query client's default mutation `onError` (`src/lib/query-client.ts`) toasts the error of a mutation that sets none. Components do not add their own error toasts for these.
- Confirmations use `useConfirm` (`src/hooks/use-confirm.ts`): `confirm(options)` returns a promise of the user's answer, and `confirmProps` spreads onto `ConfirmDialog` (`src/components/primitives/dialog.tsx`). Give the dialog a test id through `contentProps={{ 'data-testid': … }}` and pass `destructive: true` for deletes and discards.

## Dialogs
- Build a dialog from `Dialog`, `DialogInnerContent`, `DialogHeader`, `DialogTitle`, `DialogDescription` and `DialogFooter` (`src/components/primitives/dialog.tsx`), with the test id on `contentProps`. `Dialog` ignores clicks outside it unless `preventOutsideClose={false}`; Escape and its own buttons still close it.
- `DeviceLogsDownloadDialog`, `FlashDeviceModal` and `ProvisionDeviceModal` are the references. The USB modals intercept closing while they run and ask first ("Cancel Flashing?", "Cancel Provisioning?").

## Referenced Patterns
- The [Device Models Pattern](./patterns/device_models.md) shows the single-page editor for new and edit.
- The [Devices Pattern](./patterns/devices.md) shows one form hook serving three modes, an editor inside a routed tab, and the USB modals.
