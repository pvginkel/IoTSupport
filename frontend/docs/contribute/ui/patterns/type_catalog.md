# Type Catalog Pattern

## When To Use
Apply this pattern to CRUD experiences for lightweight reference data: entities with a single primary attribute, small edit surfaces, and minimal cross-entity dependencies. The existing Types feature is the canonical implementation and lives in `src/components/types`.

## UX Expectations
- Landing view is a simple list of cards with search and count summaries (`TypeList`). Keep the page header, add/search buttons, and summary strip intact.
- Support three explicit states: loading (skeleton cards), empty (call to action + context), and "no search results" (guidance to adjust filters). Each state uses dedicated `data-testid` hooks (`types.list.loading`, `types.list.empty`, etc.).
- Creation and editing happen in modal dialogs (`TypeForm`) invoked from buttons in the header and card actions. The modal titles, aria labels, and button copy distinguish create vs. edit operations.
- Deletion requires confirmation via `useConfirm` + `ConfirmDialog`. Confirmations must reiterate destructive impact (“This action cannot be undone.”).

## Implementation Checklist
- Fetch data with `useGetTypesWithStats` (`src/hooks/use-types.ts`) so the list has access to part counts and instrumentation metadata. Mutations run through `useCreateType`, `useUpdateType`, and `useDeleteType`.
- Manage local UI state with React hooks: `useState` for modal visibility, `useEffect` for loading transitions, and `useNavigate` to sync the search box with `/types` route search params.
- Render cards using `TypeCard` (`src/components/types/TypeCard.tsx`) and keep layout responsive (`grid-cols-1 md:grid-cols-2 lg:grid-cols-3`). Sort results in-memory with locale-aware compare to ensure deterministic ordering.
- Wire `TypeForm` with trimmed submission payloads, 255-character limits, and cancel/reset behavior as documented in the form conventions.
- Ensure all interactive elements expose `data-testid` selectors as already defined (`types.create.button`, `types.form.submit`, etc.) so tests stay stable.

## Testing & Instrumentation
- Call `useListLoadingInstrumentation` (`src/lib/test/query-instrumentation.ts`) with the scope `types.list` and provide `getReadyMetadata` / `getErrorMetadata` callbacks mirroring the existing implementation. Feature-level work must extend that metadata instead of bypassing it.
- Forms rely on `useFormInstrumentation` (`src/hooks/use-form-instrumentation.ts`) with IDs from `generateFormId` (`src/lib/test/form-instrumentation.ts`). Preserve those hooks when adding fields.
- Since tests run against the real backend, avoid mocking: plans must describe any new data setup requirements and coordinate with backend factories per [Testing → Factories & Fixtures](../../testing/factories_and_fixtures.md).

## Extensions & Variations
- Additional fields should still fit within the modal form. If the entity grows beyond a simple dialog (multi-tab, attachments, etc.), migrate toward the [Part Management Pattern](./part_management.md).
- To surface per-type analytics (e.g., usage stats), extend the summary row and card badges but keep the base skeleton and instrumentation naming stable.
- If inline creation is required elsewhere, reuse `TypeSelector` (`src/components/types/type-selector.tsx`) + `SearchableSelect` (`src/components/ui/searchable-select.tsx`) rather than inventing a new picker.

## References
- `TypeList` (`src/components/types/TypeList.tsx`) — list layout, search orchestration, instrumentation.
- `TypeForm` (`src/components/types/TypeForm.tsx`) — modal form, validation, form instrumentation.
- `type-create-dialog` (`src/components/types/type-create-dialog.tsx`) + `TypeSelector` (`src/components/types/type-selector.tsx`) — inline creation pattern shared with other forms.
