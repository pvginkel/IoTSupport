# Page Objects

Page objects encapsulate feature-specific UI interactions so specs stay focused on behavior. They live next to their tests under `tests/e2e/<feature>/` and expose both low-level locators and high-level actions.

## Structure

```typescript
import { expect, Locator, Page } from '@playwright/test';

export class TypesPage {
  readonly page: Page;
  readonly root: Locator;

  constructor(page: Page) {
    this.page = page;
    this.root = page.getByTestId('types.page');
  }

  async goto() {
    await this.page.goto('/types');
    await expect(this.root).toBeVisible();
  }

  cardByName(name: string) {
    return this.root.locator('[data-testid="types.list.card"]').filter({ hasText: name });
  }

  async createType(name: string) {
    await this.page.getByRole('button', { name: /add type/i }).click();
    const dialog = this.page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await this.page.getByLabel(/type name/i).fill(name);
    await this.page.getByRole('button', { name: /save/i }).click();
    await expect(dialog).toBeHidden();
    await expect(this.cardByName(name)).toBeVisible();
  }
}
```

### Guidelines

- **Scope to a root** (`getByTestId('types.page')`) to avoid cross-page collisions.
- **Expose locators** for assertions and chaining (e.g., `cardByName`).
- **Add actions** for workflows that multiple tests share (e.g., `createType`).
- **Keep assertions intentional** – only include assertions that are part of the action’s contract (e.g., confirm a modal closes after submit).

## Ownership & Organization

- Colocate page objects with their specs: `tests/e2e/<feature>/<FeatureName>Page.ts`.
- Export them via fixtures in `tests/support/fixtures.ts` when reused widely (`types: TypesPage`).
- When coverage expands, add additional page objects per domain (e.g., `PartsListPage`, `BoxDetailPage`).

## Interacting with Components

- Prefer semantic selectors; fall back to `data-testid` for ambiguous controls.
- Add helper methods for repetitive UI fragments (e.g., `toastByCode`, `openInlineCreate`).
- Consolidate modal interactions to avoid duplicating wait logic across specs.

## Relation to Helpers

- Page objects orchestrate UI; helpers in `tests/support/helpers.ts` orchestrate instrumentation or backend interactions.
- If an action requires API setup, perform that in the spec using factories before calling the page object.

## Migration from Selector Maps

When encountering references to `tests/support/selectors.ts`, port those flows to page object methods. Remove the legacy selector once no tests depend on it.

## Checklist for New Page Objects

- [ ] Lives in `tests/e2e/<feature>/` with PascalCase filename.
- [ ] Exposes a `goto()` method that verifies the page is ready.
- [ ] Provides locators/actions for repeated interactions.
- [ ] Uses the selector priority outlined in [Selector Patterns](./selector_patterns.md).
- [ ] Covered by fixtures if reused across specs.

Related docs: [Playwright Developer Guide](./playwright_developer_guide.md), [Factories & Fixtures](./factories_and_fixtures.md).
