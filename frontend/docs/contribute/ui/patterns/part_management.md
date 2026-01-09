# Part Management Pattern

## When To Use
Follow this pattern for resource-heavy domains where users need to browse, inspect, edit, duplicate, and enrich entities in one workspace. Parts combine list, detail, form, AI-assisted creation, document management, and stock actions—future inventory-like modules should do the same.

## UX Expectations
- **List view (`PartList`)**: supports search synced to router params, multi-button header (`Add Part`, `Add with AI`), and responsive grids of rich cards. Each card surfaces key metadata (quantity, type badges, vendor info) and is entirely clickable when navigation is enabled.
- **Detail view (`PartDetails`)**: renders a summary grid with part metadata, cover image, locations, documents, and action buttons (`Edit`, `Delete`, `Duplicate`). Editing swaps in `PartForm` without route changes.
- **Creation flows**: standard form creation (`PartForm`), duplication (`duplicateFromPartId`), and AI analysis via `AIPartDialog` (`src/components/parts/ai-part-dialog.tsx`) which steps through input → progress → review. Keep these entry points consistent and surfaced from the list header and detail overflow menu.
- **Supporting widgets**: selectors (`TypeSelector`, `SellerSelector`), tags, mounting type pickers, and document grids are shared between flows. Reuse them instead of rebuilding per feature.

## Implementation Checklist
- Fetch list data with `useGetPartsWithLocations` (`src/lib/api/generated/hooks.ts`) and the complementary `useGetTypes` call to map type IDs. Memoize derived values with `useMemo` to avoid recomputation during re-renders.
- Route search state through `useNavigate` so `/parts?search=...` deep links stay stable. Provide clear buttons using `ClearButtonIcon` as in the existing implementation.
- For detail views, load the entity via `useGetPartsByPartKey`, and handle null/error by rendering the standard "Part not found" card before the instrumentation triggers.
- Mutation hooks: `usePutPartsByPartKey`, `useDeletePartsByPartKey`, `usePostParts`, and `usePostPartsCopyAttachment` cover the primary workflows. Wrap attachment duplication in progress indicators (`copyProgress`) and toast feedback via `useToast` (`src/hooks/use-toast.ts`).
- Attachments and AI flows depend on helper hooks (`useDuplicatePart`, `useAIPartAnalysis`, `useClipboardPaste`, `usePartDocuments`, `useCoverAttachment`). Extend those utilities rather than forking logic in the component tree.
- Maintain responsive grid layouts (`grid-cols-1 lg:grid-cols-2`) and ensure interactive controls remain accessible (aria labels, focus management, `Dialog` semantics).

## Testing & Instrumentation
- List instrumentation must call `useListLoadingInstrumentation` (`src/lib/test/query-instrumentation.ts`) with the scope `parts.list` and capture both parts and types query statuses. Include metadata for counts so Playwright can assert on loaded state.
- `PartForm` already wires `useFormInstrumentation` (`src/hooks/use-form-instrumentation.ts`) and tracks validation via `trackValidationErrors`. Preserve that plumbing when adding fields or new sections.
- AI dialog steps should continue to emit progress through `useAIPartAnalysis` and rely on query/mutation hooks for backend communication. Do not replace them with mocked requests—coordinate with backend fixtures per [Testing → Playwright Developer Guide](../../testing/playwright_developer_guide.md).
- Every distinct state has dedicated `data-testid` attributes (`parts.list.loading`, `parts.detail`, `parts.ai.dialog`, etc.). Extend the taxonomy rather than renaming existing selectors so suites stay deterministic.

## Extensions & Variations
- Introducing new sub-flows (e.g., BOM exports, supplier quoting) should plug into the existing header/overflow menu affordances and reuse the modal/dialog scaffolding established by the AI assistant.
- For additional metadata, add badges or summary rows to `PartListItem` and detail cards while keeping the base structure intact. Complex edits belong in the form step, not inline.
- If a future domain needs nested stock management, prefer hooking into the generated API client and existing instrumentation utilities instead of manually orchestrating side effects.

## References
- `PartList` (`src/components/parts/part-list.tsx`) — list orchestration, search, instrumentation, card layout.
- `PartDetails` (`src/components/parts/part-details.tsx`) — summary grid, document handling, duplicate/delete flows.
- `PartForm` (`src/components/parts/part-form.tsx`) — multi-section form, duplication workflow, instrumentation.
- `AIPartDialog` (`src/components/parts/ai-part-dialog.tsx`) + supporting steps — AI-assisted creation flow.
