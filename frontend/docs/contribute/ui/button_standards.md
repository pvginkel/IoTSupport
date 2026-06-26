# Button Labeling Standards

This document defines the standards for button labels across the Electronics Inventory application to ensure consistency, clarity, and accessibility.

## Core Principle: `<verb> <noun>` Format

All button labels should follow the **`<verb> <noun>`** pattern that clearly describes the business function being performed.

### Examples

✅ **Good**
- "Add Part"
- "Delete Item"
- "Save Quantity"
- "Complete List"
- "Order Stock"
- "Reload Data"

❌ **Bad**
- "Add" (missing noun - add what?)
- "Save" (missing noun - save what?)
- "Retry" (missing noun - retry what?)
- "Done" (not action-oriented)

## Style Guidelines

### 1. Title Case

Use title case for all button labels, capitalizing the first letter of each major word.

✅ **Good**
- "Save & Next"
- "Add to Shopping List"
- "View All Boxes"

❌ **Bad**
- "Save & next"
- "add to shopping list"
- "View all boxes"

### 2. Business-Function Naming

Use business domain language that describes what the user is accomplishing, not technical operations.

✅ **Good**
- "Complete List" (user completes their shopping list)
- "Order Stock" (user orders inventory)
- "Capture Photo" (user captures a photo)

❌ **Bad**
- "Mark Done" (technical state change)
- "Create Shopping List" (when adding to existing list)
- "Use Camera" (tool-focused, not action-focused)

### 3. No Emojis

Do not use emoji prefixes or suffixes in button labels. Use the Button component's `icon` prop for visual distinction if needed.

✅ **Good**
```tsx
<Button icon={<ShoppingCart />}>
  Add to Shopping List
</Button>
```

❌ **Bad**
```tsx
<Button>
  🛒 Add to List
</Button>
```

### 4. No Abbreviations

Avoid abbreviations unless they are universally understood in the business context.

✅ **Good**
- "Add Documentation"
- "Edit Description"

❌ **Bad**
- "Add Docs"
- "Edit Desc"

## Icon-Only Buttons

Icon-only buttons (buttons with no visible text) **must** include an `aria-label` attribute that follows the same `<verb> <noun>` pattern.

### Examples

✅ **Good**
```tsx
<Button variant="ghost" size="icon" aria-label="More Actions">
  <MoreVerticalIcon />
</Button>

<button aria-label="Clear search" onClick={handleClear}>
  <ClearButtonIcon />
</button>

<Button aria-label="View Part">
  →
</Button>
```

❌ **Bad**
```tsx
<Button variant="ghost" size="icon">
  <MoreVerticalIcon />
</Button>

<button onClick={handleClear}>
  <ClearButtonIcon />
</button>
```

## Acceptable Exceptions

### Generic "Cancel" in Dialogs

Modal dialogs and forms may use a generic "Cancel" button when the dialog title and context make it clear what action is being cancelled.

✅ **Acceptable**
```tsx
<Dialog title="Edit Part Quantity">
  {/* form content */}
  <Button variant="outline">Cancel</Button>
  <Button>Save Quantity</Button>
</Dialog>
```

However, if the dialog purpose is unclear or contains multiple actions, use specific labels:

✅ **Better**
```tsx
<Dialog title="Processing...">
  {/* complex workflow */}
  <Button variant="outline">Cancel Analysis</Button>
  <Button>Continue</Button>
</Dialog>
```

### Pagination Controls

Standard progressive disclosure patterns like "Show More" and "Show Less" are acceptable exceptions to the strict `<verb> <noun>` rule.

✅ **Acceptable**
- "Show More"
- "Show Less"
- "Load More Results"

### Loading States

Loading state labels using present continuous tense do not need to follow the `<verb> <noun>` pattern:

✅ **Acceptable**
```tsx
<Button loading={isSubmitting}>
  {isSubmitting ? "Creating..." : "Create Part"}
</Button>
```

## Common Patterns

### Navigation Actions

Use action verbs rather than navigation language:

✅ **Good**
- "View All Boxes"
- "Go Back"

❌ **Bad**
- "Back to Boxes"
- "Return"

### Error Recovery

Error state buttons should describe what will be retried or reloaded:

✅ **Good**
- "Reload Data"
- "Reload List"
- "Retry Analysis"

❌ **Bad**
- "Retry"
- "Try Again"

### Completion Actions

Use completion language appropriate to the business domain:

✅ **Good**
- "Complete List" (shopping list)
- "Complete Item" (shopping list item)
- "Accept Photo" (camera capture)

❌ **Bad**
- "Mark Done"
- "Finish"
- "Use Photo"

### Dropdown Menu Triggers

Icon-only dropdown menu triggers should use "More Actions" as a standard aria-label:

✅ **Good**
```tsx
<DropdownMenuTrigger asChild>
  <Button variant="outline" aria-label="More Actions">
    <MoreVerticalIcon />
  </Button>
</DropdownMenuTrigger>
```

### Sort Controls

Sort dropdown triggers should describe their function:

✅ **Good**
```tsx
<Button aria-label="Change sort order" title={`Current sort: ${sortLabel}`}>
  <ArrowDownAZ />
</Button>
```

## Testing & Verification

### Manual Review Checklist

When adding or modifying buttons:

1. ✅ Label follows `<verb> <noun>` format (or is an acceptable exception)
2. ✅ Label uses business-function language, not technical jargon
3. ✅ Label is in title case
4. ✅ No emojis or unnecessary abbreviations
5. ✅ Icon-only buttons have descriptive `aria-label` attributes

### Accessibility Testing

Test icon-only buttons with screen readers:
- All buttons should announce their purpose clearly
- Buttons should not be announced as just "button" without context
- Use tools like axe DevTools or Lighthouse to audit for missing labels

### Playwright Tests

Update test selectors when changing button labels:

```ts
// Good - uses flexible regex matching
await page.getByRole('button', { name: /save quantity/i }).click();

// Also good - uses data-testid
await page.getByTestId('parts.locations.save').click();
```

## Migration Guide

When updating existing non-compliant buttons:

1. **Identify the business function**: What is the user trying to accomplish?
2. **Choose an action verb**: Add, Save, Delete, Complete, etc.
3. **Add the object noun**: Part, Quantity, List, etc.
4. **Update related tests**: Check for test selectors that rely on button text
5. **Verify accessibility**: Ensure icon-only buttons have aria-labels

### Example Migration

**Before:**
```tsx
<Button onClick={handleSave}>Save</Button>
```

**After:**
```tsx
<Button onClick={handleSave}>Save Quantity</Button>
```

**Test Update:**
```ts
// Before
await page.getByRole('button', { name: /save/i }).click();

// After - more specific
await page.getByRole('button', { name: /save quantity/i }).click();
```

## Questions?

If you're unsure whether a button label follows these standards:

1. Ask yourself: "If I saw this button out of context, would I know exactly what it does?"
2. Check for similar patterns in existing compliant buttons
3. Consult with the team if the business function is ambiguous

## References

- [WCAG 2.1 Success Criterion 4.1.2: Name, Role, Value](https://www.w3.org/WAI/WCAG21/Understanding/name-role-value.html)
- [Button Labeling Best Practices](https://www.nngroup.com/articles/button-design-principles/)
- Project architecture: `docs/contribute/architecture/application_overview.md`
