# Tooltip Guidelines

This guide documents when and how to use tooltips in the Electronics Inventory application.

## Overview

Tooltips provide contextual information when users hover over or focus on UI elements. The application provides a unified `Tooltip` component that supports both simple text tooltips and rich content tooltips, with automatic handling for disabled elements.

## Decision Tree: When to Use What

### Use Plain `title` Attribute When:

- Content is simple text (no formatting, icons, or multiline)
- Element is **not** disabled (or doesn't need tooltip when disabled)
- No special positioning or styling needed

```tsx
<button title="Save changes">Save</button>
<span title="Created on 2024-01-15">2024-01-15</span>
```

### Use `Tooltip` with `title` Prop When:

- Content is simple text
- Element **is disabled** and needs explanatory tooltip
- You want consistent timing/behavior across the app

```tsx
<Tooltip title="Add parts before ordering">
  <Button disabled={!hasParts}>Order Stock</Button>
</Tooltip>
```

### Use `Tooltip` with `content` Prop When:

- Content includes formatting, icons, or multiline text
- Content is structured (lists, key-value pairs, etc.)
- Need special placement (e.g., `placement="center"` for modal-like overlay)
- Content is dynamic or complex

```tsx
<Tooltip
  content={
    <div>
      <div className="font-medium">Active Reservations</div>
      <ul className="text-xs">
        <li>Kit A: 50 units</li>
        <li>Kit B: 30 units</li>
      </ul>
    </div>
  }
>
  <ReservationIcon />
</Tooltip>
```

## Component API

### TooltipProps

```typescript
interface TooltipProps {
  // Content (mutually exclusive - provide one or the other)
  title?: string;           // Simple text tooltip
  content?: ReactNode;      // Rich tooltip content

  // Common props
  children: ReactElement;   // Trigger element (must accept ref)
  enabled?: boolean;        // Whether tooltip is enabled (default: true)
  placement?: 'top' | 'right' | 'bottom' | 'left' | 'auto' | 'center';
  showArrow?: boolean;      // Show arrow indicator (default: true for content, false for center)
  offset?: number;          // Distance from trigger in px (default: 8)
  delay?: number;           // Open delay in ms (default: 200)
  testId?: string;          // data-testid for Playwright
  className?: string;       // Additional classes for tooltip content (content mode only)
}
```

## Placement Options

### Standard Placements

- `'top'` - Above the trigger
- `'bottom'` - Below the trigger
- `'left'` - Left of the trigger
- `'right'` - Right of the trigger
- `'auto'` (default) - Automatically choose best position based on viewport space

### Special Placement

- `'center'` - Centers tooltip over the trigger element (modal-like overlay)
  - Used for rich, interactive-looking content that acts as a temporary overlay
  - No arrow indicator shown
  - Example: Health score breakdown tooltip

```tsx
<Tooltip
  content={<ComplexBreakdown />}
  placement="center"
>
  <div>Click for details</div>
</Tooltip>
```

## Automatic Disabled Element Handling

The Tooltip component **automatically detects** when its child has a `disabled` prop and applies a wrapper pattern to ensure the tooltip still works.

### Title Mode (Simple Text)

```tsx
// Tooltip automatically wraps disabled button
<Tooltip title="Add parts before ordering">
  <Button disabled>Order Stock</Button>
</Tooltip>

// Rendered as:
// <div tabIndex={0} title="...">
//   <Button disabled className="pointer-events-none">...</Button>
// </div>
```

### Content Mode (Rich Content)

```tsx
// Tooltip automatically wraps disabled button
<Tooltip content={<ExplanationPanel />}>
  <Button disabled>Edit Kit</Button>
</Tooltip>

// Rendered with wrapper that captures hover/focus events
```

### No Special Code Needed

You don't need to manually detect disabled state or wrap elements. The Tooltip component handles this automatically.

## Arrow Indicators

Content mode tooltips show a small arrow pointing from the tooltip to the trigger element by default.

- Arrow automatically positioned based on placement direction
- Arrow hidden for `placement="center"` (modal-like overlays)
- Can be disabled via `showArrow={false}` if needed

```tsx
// Default: arrow shown
<Tooltip content={<Info />}>
  <InfoIcon />
</Tooltip>

// No arrow for center placement
<Tooltip content={<Details />} placement="center">
  <Trigger />
</Tooltip>

// Explicitly disable arrow
<Tooltip content={<Info />} showArrow={false}>
  <InfoIcon />
</Tooltip>
```

## Conditional Tooltips

Use the `enabled` prop to conditionally show tooltips:

```tsx
<Tooltip
  title="Archived kits are read-only"
  enabled={isArchived}
>
  <Button disabled={isArchived}>Edit Kit</Button>
</Tooltip>
```

Note: `enabled` is independent of the child's `disabled` state. A disabled button can have `enabled={false}` to suppress the tooltip entirely.

## Content Restrictions

**IMPORTANT**: Tooltips must contain **only informational content**. Do not include:

- Buttons or clickable actions
- Form inputs
- Interactive elements
- Critical information that's not available elsewhere

Tooltips are dismissible on mouse leave or Escape key, so users must be able to access all functionality without them.

### Good Examples

```tsx
// ✓ Simple explanation
<Tooltip title="Part ID is auto-generated">
  <InfoIcon />
</Tooltip>

// ✓ Structured information
<Tooltip content={
  <div>
    <div>Reservation Details:</div>
    <ul>
      <li>Kit: {name}</li>
      <li>Qty: {qty}</li>
    </ul>
  </div>
}>
  <ReservationIcon />
</Tooltip>
```

### Bad Examples

```tsx
// ✗ Interactive button in tooltip
<Tooltip content={
  <div>
    Are you sure?
    <Button>Confirm</Button>
  </div>
}>
  <DeleteIcon />
</Tooltip>

// ✗ Critical action only in tooltip
<Tooltip content={<a href="/help">Get help</a>}>
  <HelpIcon />
</Tooltip>
```

For interactive overlays, use a Dialog or Popover component instead.

## Accessibility

The Tooltip component handles accessibility automatically:

- `role="tooltip"` on tooltip content
- `aria-describedby` linking trigger to tooltip
- Keyboard support: Escape to close, focus to open
- Focus management: Returns focus to trigger on close
- Disabled element handling: Focusable wrapper with `tabIndex={0}`

## Testing with Playwright

Tooltips are tested using visibility assertions, not test events.

### Pattern

```typescript
// Hover over trigger
await trigger.hover();

// Assert tooltip is visible
await expect(page.getByTestId('feature.tooltip')).toBeVisible();

// Assert tooltip content
await expect(page.getByTestId('feature.tooltip')).toContainText('Expected text');

// Tooltip disappears on mouse leave
await page.mouse.move(0, 0);
await expect(page.getByTestId('feature.tooltip')).not.toBeVisible();
```

### TestId Convention

**Content mode** (rich tooltips): When providing `testId` prop with `content`, the tooltip element gets `${testId}.tooltip` suffix:

```tsx
<Tooltip testId="reservations" content={...}>
  <Icon />
</Tooltip>

// In test:
await expect(page.getByTestId('reservations.tooltip')).toBeVisible();
```

**Title mode** (simple tooltips): When providing `testId` prop with `title`, the testId is applied to the trigger element without suffix:

```tsx
<Tooltip testId="action-button" title="Click to submit">
  <Button>Submit</Button>
</Tooltip>

// The trigger gets the testId (native title tooltips are typically not tested)
await expect(page.getByTestId('action-button')).toBeVisible();
```

**Why the difference?** Content mode tooltips are testable React components that render via portal, while title mode uses native browser tooltips that are not easily testable. The testId in title mode identifies the trigger element for test interaction, not the tooltip itself.

## Migration Checklist

When migrating existing tooltip implementations:

1. **Identify tooltip type**: Simple text or rich content?
2. **Choose mode**: Plain `title`, `Tooltip` with `title`, or `Tooltip` with `content`
3. **Remove custom code**: Delete manual positioning, portal code, state management
4. **Delete bespoke components**: Remove custom tooltip components entirely
5. **Add testId**: Ensure Playwright tests can target the tooltip
6. **Verify tests**: Run existing specs to ensure they still pass
7. **Update page objects**: If needed, update locator methods

## Prohibition on Bespoke Tooltip Implementations

**DO NOT** create new custom tooltip implementations. Always use:

- Plain `title` attribute for simple cases, or
- The shared `Tooltip` component for all other cases

### What Counts as a Bespoke Tooltip?

- Manual `createPortal` with tooltip-like positioning
- Inline tooltip divs with `isHovered` state
- CSS-only `group-hover` tooltip patterns
- Custom positioning logic (getBoundingClientRect, viewport collision detection)
- Timer-based show/hide logic

### PR Checklist Item

Before merging:

- [ ] Verify no custom tooltip implementations (check for createPortal, inline tooltip divs, custom positioning logic)
- [ ] All tooltips use either plain `title` attribute or shared `Tooltip` component
- [ ] No `role="tooltip"` outside of shared Tooltip component

### Why This Rule?

Custom tooltip implementations:

- Create inconsistent behavior (different timing, positioning bugs)
- Duplicate complex code (event coordination, viewport handling, accessibility)
- Are harder to test (no standard selectors, inconsistent structure)
- Accumulate bugs (quick mouse movement, click behavior, memory leaks)

The shared `Tooltip` component consolidates all this complexity into a single, tested implementation.

## Examples

### Simple Disabled Button Tooltip

```tsx
<Tooltip title="Part must have quantity before adding to kit">
  <Button disabled={quantity === 0}>
    Add to Kit
  </Button>
</Tooltip>
```

### Reservation Indicator Tooltip

```tsx
<Tooltip
  testId="kits.detail.table.row.reservations"
  content={
    <div className="space-y-2">
      <div className="flex items-center gap-2 font-medium">
        <AlertTriangle className="h-4 w-4 text-amber-500" />
        <span>Active Reservations</span>
      </div>
      <ul className="space-y-1 text-xs">
        {reservations.map(r => (
          <li key={r.id}>
            <div>{r.kitName}</div>
            <div>Reserved: {r.quantity}</div>
          </li>
        ))}
      </ul>
    </div>
  }
>
  <Users className="h-4 w-4 text-muted-foreground" />
</Tooltip>
```

### Health Score Breakdown (Center Placement)

```tsx
<Tooltip
  content={<HealthBreakdownPanel />}
  placement="center"
  testId="dashboard.health"
>
  <div className="health-gauge">
    {scoreValue}
  </div>
</Tooltip>
```

### Conditional Tooltip

```tsx
<Tooltip
  title="Type is used by existing parts"
  enabled={isUsed}
>
  <Button disabled={isUsed}>
    Delete Type
  </Button>
</Tooltip>
```

## Mobile Considerations

- Touch devices show tooltip on tap
- Tooltip dismisses on tap outside or scroll
- For simple cases on mobile, prefer plain `title` attribute
- Rich tooltips work on tap but consider if a Dialog would be better UX

## Summary

- **Plain `title`**: Simple text, no disabled handling needed
- **`Tooltip` with `title`**: Simple text on disabled elements
- **`Tooltip` with `content`**: Rich content, formatting, or special placement
- **Never**: Create custom tooltip implementations
- **Always**: Informational content only (no interactive elements)
- **Testing**: Use visibility assertions, not test events
