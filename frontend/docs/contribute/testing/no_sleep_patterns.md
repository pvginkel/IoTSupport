# No-Sleep Patterns

Never rely on fixed delays in Playwright tests. This reference shows how to wait for observable signals instead of `waitForTimeout`.

## Rules of Thumb

1. **Every wait needs a signal** – UI visibility, network completion, or a test-event payload.
2. **Prefer UI assertions** – If the user can see it, assert it.
3. **Reserve helpers for gaps** – Use network waits or test-event helpers only when UI signals are insufficient.

## Common Scenarios

### Dialogs & Modals

```typescript
// Avoid
await page.waitForTimeout(500);

// Do this instead
await page.getByRole('button', { name: /open/i }).click();
await expect(page.getByRole('dialog')).toBeVisible();
```

### Form Submission

```typescript
// Avoid
await page.waitForTimeout(2000);

// Do this instead
await Promise.all([
  page.waitForResponse(res => res.url().endsWith('/api/types') && res.ok()),
  page.getByRole('button', { name: /save/i }).click(),
]);
await expect(page.getByRole('dialog')).toBeHidden();
```

### List Updates

```typescript
// Avoid substring :has-text selectors
await expect(page.locator('[data-testid="type-row"]:has-text("Resistor")')).toBeVisible();

// Do this instead
const row = page.locator('[data-testid="type-row"]').filter({ hasText: name });
await expect(row).toBeVisible();
```

### Navigation

```typescript
await page.getByRole('link', { name: /types/i }).click();
await expect(page.getByTestId('types.page')).toBeVisible();
await expect(page).toHaveURL(/\/types$/);
```

### Toast Notifications

```typescript
await expect(page.getByRole('status')).toContainText(/saved/i);
// or
await expect(page.getByTestId('toast')).toBeVisible();
```

## Test Events When Necessary

Use `waitTestEvent` only when no reliable UI or network signal exists.

```typescript
import { waitTestEvent } from '../support/helpers';

await waitTestEvent(page, 'form', evt =>
  evt.formId === 'TypeForm_edit' && evt.phase === 'success'
);
```

## Animation Guardrails

The shared fixture disables CSS transitions and animations by default. You rarely need to compensate for animation delays.

## Checklist

- [ ] No `waitForTimeout` or magic numbers.
- [ ] Assertions describe observable behavior.
- [ ] Test-event helpers used sparingly.
- [ ] Page objects expose meaningful locators to keep waits readable.

Related docs: [Playwright Developer Guide](./playwright_developer_guide.md), [Factories & Fixtures](./factories_and_fixtures.md).
