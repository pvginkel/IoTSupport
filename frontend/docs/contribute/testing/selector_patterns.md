# Selector Patterns

Selectors must be stable, accessible, and owned by the feature under test. This guide expands on the Playwright page object strategy and clarifies how legacy selector maps fit into the migration plan.

## Principles

1. **Semantic first** – Prefer ARIA roles, labels, and text when possible (`getByRole`, `getByLabel`, `getByText`).
2. **Page objects, not selector maps** – Expose Playwright `Locator` instances and high-level actions instead of raw selector strings.
3. **Feature ownership** – Store page objects next to the specs that use them (`tests/e2e/<feature>/`).
4. **Test IDs as fallback** – Use `data-testid` only when semantic selectors are insufficient or ambiguous.
5. **Avoid CSS/XPath** – Reserve CSS selectors for third-party controls you cannot tag.

## Anti-Pattern: Centralized Selector Maps

`tests/support/selectors.ts` is a legacy artifact that exposes string constants and builder helpers. Do not expand it. When you need a new selector:

- Add a method or locator to the relevant page object instead.
- If a `data-testid` is missing, add it to the component and consume it through the page object.
- Keep selector knowledge close to the test that uses it so refactors stay local.

Document any remaining use of the legacy selector map as transitional, and plan migrations to feature-owned page objects when touching those areas.

## Page Object Structure

```typescript
// tests/e2e/types/TypesPage.ts
import { expect, Locator, Page } from '@playwright/test';

export class TypesPage {
  readonly page: Page;
  readonly root: Locator;
  readonly createButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.root = page.getByTestId('types.page');
    this.createButton = this.root
      .getByRole('button', { name: /add type/i })
      .or(this.root.getByTestId('types.create.button'));
  }

  async goto() {
    await this.page.goto('/types');
    await expect(this.root).toBeVisible();
  }

  cardByName(name: string) {
    return this.root.locator('[data-testid="types.list.card"]').filter({ hasText: name });
  }

  async createType(name: string) {
    await this.createButton.click();
    await expect(this.page.getByRole('dialog')).toBeVisible();
    await this.page.getByLabel(/type name/i).fill(name);
    await this.page.getByRole('button', { name: /save/i }).click();
    await expect(this.cardByName(name)).toBeVisible();
  }
}
```

Key takeaways:
- Store a `root` locator to scope queries.
- Return `Locator` instances for composability.
- Provide high-level actions when the workflow is shared across tests.

## Selector Priority Order

1. **Semantic selectors** – roles, labels, placeholder, text
2. **`data-testid`** – `feature.section.element` naming (e.g., `types.form.submit`)
3. **CSS/XPath** – last resort for third-party widgets

```typescript
// Preferred patterns
page.getByRole('button', { name: 'Submit' });
page.getByLabel('Type name');
page.getByPlaceholder('Search...');
page.getByText(/no results/i);

// Fallback when semantics fail
page.getByTestId('types.form.submit');
page.getByTestId('parts.list.card');
```

## Adding New Test IDs

- Place attributes on the smallest stable element (`data-testid="types.form.submit"`).
- Keep names consistent with the feature structure.
- Guard new instrumentation with `isTestMode()` only when emitting test events—`data-testid` attributes are safe for production builds.

## Accessibility Matters

Selectors based on accessibility roles double as accessibility tests. When the UI lacks the necessary roles or labels, add them instead of skipping straight to `data-testid`.

## Migration Checklist

- [ ] When touching a test that still uses `selectors.testId(...)`, port it to a page object.
- [ ] Remove unused selectors from `tests/support/selectors.ts` as coverage moves to page objects.
- [ ] Update documentation if new patterns emerge.

Related reading: [Page Objects](./page_objects.md) and [No-Sleep Patterns](./no_sleep_patterns.md).
