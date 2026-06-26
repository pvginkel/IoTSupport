# Form Conventions

## Scope
Use this guidance for any interactive form surface—dialogs, inline cards, or wizard steps—that collect data before calling the generated API client. The examples reference the current TypeForm (`src/components/types/TypeForm.tsx`) and PartForm (`src/components/parts/part-form.tsx`) implementations, but the same principles apply system-wide.

## Core Building Blocks
- Compose forms with the primitives in `src/components/ui`: `Dialog`/`DialogContent` for modal shells, `Form`, `FormField`, and `FormLabel` for structure, `Input`/`SearchableSelect`/domain-specific controls for inputs, and `Button` for actions.
- Respect the existing spacing and layout patterns (`space-y-*`, section headers) visible in the parts form. Group related fields under labeled sub-sections instead of ad hoc dividers.
- Primary actions belong on the right within `DialogFooter`; destructive or cancel actions use `variant="outline"` and may opt into `preventValidation` to avoid triggering submit handlers.
- Keep accessibility affordances from the base components (e.g., `FormLabel required`, `Input` error states) intact. If you introduce a new field type, make sure it exposes error messaging the same way.

## Validation & Submission
- Manage local state with `useFormState` (`src/hooks/use-form-state.ts`). Supply per-field validation rules rather than inlining validation logic in submit handlers. For complex domains, wrap shared rules in utility functions like `validatePartData` (`src/lib/utils/parts.ts`).
- Trim and normalize values before sending them to the API client. Follow the Type Form example, which trims names and enforces a 255-character limit.
- Run mutations through the generated TanStack hooks (`usePostTypes`, `usePutPartsByPartKey`, etc.). They already integrate with the centralized error handling documented in [Architecture → Application Overview](../architecture/application_overview.md), so avoid manual `fetch` calls.

## Instrumentation & Analytics
- Every form must emit deterministic events for Playwright. Generate stable IDs with `generateFormId` (`src/lib/test/form-instrumentation.ts`) and wire `useFormInstrumentation` (`src/hooks/use-form-instrumentation.ts`) to track open/submit/success/error states.
- When performing validation, call `trackValidationError` / `trackValidationErrors` on failure so the "no route mocks" test strategy can await those events. See `TypeForm` and `PartForm` for reference.
- For mutation-level telemetry, rely on the existing query instrumentation setup; avoid double-logging.

## Error Handling & Toasts
- Let the generated hooks surface API errors via TanStack Query; the shared error boundary and query instrumentation will emit the appropriate events. Only display toasts for domain-specific messaging (e.g., duplicate documents copy failures in the parts flow) via `useToast` (`src/hooks/use-toast.ts`).
- Keep optimistic UI in sync with backend requirements. For destructive flows, run confirmation via `useConfirm` (`src/hooks/use-confirm.ts`) + `ConfirmDialog` and defer to the mutation state to disable buttons.

## Referenced Patterns
- The [Type Catalog Pattern](./patterns/type_catalog.md) shows the standard single-entity modal form flow.
- The [Part Management Pattern](./patterns/part_management.md) demonstrates how to scale the same infrastructure across multi-step experiences (edit, duplicate, AI-assisted creation).
Use these references before introducing new form shells or instrumentation paths.
