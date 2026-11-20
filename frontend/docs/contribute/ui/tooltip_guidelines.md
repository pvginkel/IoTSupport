# Tooltip Guidelines

This guide documents when and how to show tooltips in the IoT Support frontend.

## Overview

Tooltips give contextual information when the user hovers over or focuses an element. There are two mechanisms:

- the native `title` attribute, which the app's screens use throughout — the device model list's delete button ("Delete model", or "Cannot delete: model has devices"), the **Flash Device** and **Provision Device** buttons ("Flash firmware via USB", "Provision device via USB"), each log entry's timestamp, the rotation dashboard's bar segments;
- the shared `Tooltip` component (`src/components/primitives/tooltip.tsx`, exported from `@/components/primitives`), for simple text on a disabled element and for rich content. No screen uses it; the template's `LinkChip` primitive does.

The sketches below use the app's components to show the API; none of them is in the screens.

## Decision Tree: When to Use What

### Use a Plain `title` Attribute When:

- The content is simple text (no formatting, icons or multiple lines)
- The element is **not** disabled, or needs no tooltip while disabled
- No special positioning or styling is needed

```tsx
<Button variant="outline" onClick={() => setFlashModalOpen(true)} title="Flash firmware via USB">
  <Zap className="h-4 w-4 mr-2" />
  Flash Device
</Button>
```

### Use `Tooltip` with the `title` Prop When:

- The content is simple text
- The element **is disabled** and the user needs to know why: a disabled element does not receive pointer events, so `Tooltip` puts the `title` on a focusable wrapper instead

```tsx
<Tooltip title="Web Serial needs a desktop Chromium browser">
  <Button variant="outline" disabled={!isWebSerialSupported()}>Flash Device</Button>
</Tooltip>
```

### Use `Tooltip` with the `content` Prop When:

- The content has formatting, icons or several lines
- The content is structured (a list, key–value pairs)
- It needs a placement, such as `placement="center"` for an overlay on the trigger
- The content is dynamic

```tsx
<Tooltip
  testId="feature"
  content={
    <div>
      <div className="font-medium">Rotation State</div>
      <ul className="text-xs">
        <li>Healthy: {healthy}</li>
        <li>Warning: {warning}</li>
        <li>Critical: {critical}</li>
      </ul>
    </div>
  }
>
  <span>{healthy + warning + critical} devices</span>
</Tooltip>
```

## Component API

### TooltipProps

```typescript
interface TooltipProps {
  // Content (mutually exclusive - provide one or the other)
  title?: string;           // Simple text tooltip (native title attribute)
  content?: ReactNode;      // Rich tooltip content, rendered in a portal

  // Common props
  children: ReactElement;   // Trigger element (must accept ref)
  enabled?: boolean;        // Whether the tooltip is enabled (default: true)
  placement?: 'top' | 'right' | 'bottom' | 'left' | 'auto' | 'center'; // default: 'auto'
  showArrow?: boolean;      // Arrow indicator (default: true, false for 'center')
  offset?: number;          // Distance from the trigger in px (default: 8; ignored for 'center')
  delay?: number;           // Open delay in ms (default: 200)
  testId?: string;          // data-testid for Playwright
}
```

If both `title` and `content` are given, `content` wins, and in development the component logs a warning.

`placement`, `showArrow`, `offset` and `delay` apply to content mode only: in title mode the browser shows the native tooltip with its own timing. In content mode the tooltip closes 120 ms after the pointer leaves, and stays open while the pointer is over the tooltip itself.

## Placement Options

### Standard Placements

- `'top'`, `'bottom'`, `'left'`, `'right'` — on that side of the trigger, centred on it, and kept inside the viewport with a 12 px margin. A side that lacks room is not swapped for another.
- `'auto'` (default) — the side with the most room, if the tooltip fits there; otherwise below the trigger.

The tooltip repositions on scroll and resize while it is open.

### Special Placement

- `'center'` — centres the tooltip over the trigger element, as an overlay on it
  - For rich content that reads as a temporary panel
  - No arrow

```tsx
<Tooltip content={<RotationBreakdown />} placement="center">
  <div>{healthy} healthy</div>
</Tooltip>
```

## Automatic Disabled Element Handling

`Tooltip` detects when its child has `disabled={true}` and wraps it so the tooltip still works.

### Title Mode (Simple Text)

```tsx
<Tooltip title="Web Serial needs a desktop Chromium browser">
  <Button disabled>Flash Device</Button>
</Tooltip>

// Rendered as:
// <div class="inline-flex cursor-not-allowed" tabIndex={0} title="…">
//   <Button disabled className="… pointer-events-none">…</Button>
// </div>
```

For an enabled child, title mode adds the `title` to the child itself and renders no wrapper.

### Content Mode (Rich Content)

Content mode always renders a wrapper `div` that captures hover and focus. For a disabled child, the wrapper also gets `tabIndex={0}` and `cursor-not-allowed`, and the child gets `pointer-events-none`.

### No Special Code Needed

You do not need to detect the disabled state or wrap the element yourself.

## Arrow Indicators

Content-mode tooltips show a small arrow pointing at the trigger, on the side the tooltip opened on.

- Hidden for `placement="center"`
- Turned off with `showArrow={false}`

```tsx
// Default: arrow shown
<Tooltip content={<Info />}>
  <InfoIcon />
</Tooltip>

// No arrow for center placement
<Tooltip content={<Details />} placement="center">
  <Trigger />
</Tooltip>

// Arrow turned off
<Tooltip content={<Info />} showArrow={false}>
  <InfoIcon />
</Tooltip>
```

## Conditional Tooltips

Use the `enabled` prop to show a tooltip only when it applies:

```tsx
<Tooltip title="A model with devices cannot be deleted" enabled={model.deviceCount > 0}>
  <Button variant="destructive" size="sm" disabled={model.deviceCount > 0}>
    Delete Model
  </Button>
</Tooltip>
```

`enabled` is independent of the child's `disabled` state. With `enabled={false}` the component renders the child untouched, and an open tooltip closes.

## Content Restrictions

**IMPORTANT**: Tooltips contain **only informational content**. Do not put in them:

- Buttons or clickable actions
- Form inputs
- Interactive elements
- Critical information that is not available elsewhere

Tooltips close on mouse leave, blur and Escape, so users must be able to reach all functionality without them.

### Good Examples

```tsx
// ✓ Simple explanation
<Tooltip title="Model code cannot be changed once the model is created">
  <InfoIcon />
</Tooltip>

// ✓ Structured information
<Tooltip content={
  <div>
    <div>Firmware {firmwareVersion}</div>
    <ul>
      <li>Chip: {chip}</li>
      <li>Images: {imageCount}</li>
    </ul>
  </div>
}>
  <InfoIcon />
</Tooltip>
```

### Bad Examples

```tsx
// ✗ Interactive button in a tooltip
<Tooltip content={
  <div>
    Are you sure?
    <Button>Delete Device</Button>
  </div>
}>
  <Trash2 />
</Tooltip>

// ✗ Critical action only in a tooltip
<Tooltip content={<a href="/rotation">Open Rotation Dashboard</a>}>
  <HelpIcon />
</Tooltip>
```

For an interactive overlay, use a `Dialog` instead.

## Accessibility

In content mode the component handles:

- `role="tooltip"` on the tooltip element
- `aria-describedby` on the wrapper, pointing at the tooltip while it is open
- Keyboard support: focus opens the tooltip, blur and Escape close it
- Disabled children: a focusable wrapper with `tabIndex={0}`

In title mode, accessibility is the browser's handling of the native `title`; a disabled child still gets the focusable wrapper.

## Testing with Playwright

Tooltips are tested with visibility assertions, not test events.

### Pattern

```typescript
// Hover over the trigger
await trigger.hover();

// Assert the tooltip is visible
await expect(page.getByTestId('feature.tooltip')).toBeVisible();

// Assert its content
await expect(page.getByTestId('feature.tooltip')).toContainText('Expected text');

// It disappears when the pointer leaves
await page.mouse.move(0, 0);
await expect(page.getByTestId('feature.tooltip')).not.toBeVisible();
```

### TestId Convention

**Content mode** (rich tooltips): with a `testId`, the tooltip element gets `${testId}.tooltip`. The wrapper gets `${testId}` itself when the child has no `data-testid` of its own, and `${testId}.disabled-wrapper` when the child is disabled.

```tsx
<Tooltip testId="feature" content={…}>
  <span>…</span>
</Tooltip>

// In the test:
await expect(page.getByTestId('feature.tooltip')).toBeVisible();
```

**Title mode** (simple tooltips): the `testId` goes on the element that carries the `title` — the child itself, or the wrapper around a disabled child — without a suffix.

```tsx
<Tooltip testId="feature.hint" title="Web Serial needs a desktop Chromium browser">
  <Button disabled>Flash Device</Button>
</Tooltip>

// The wrapper gets the testId; the native tooltip itself is not testable
await expect(page.getByTestId('feature.hint')).toHaveAttribute('title', /Web Serial/);
```

**Why the difference?** A content-mode tooltip is a React element rendered through a portal, so a test can find it. A title-mode tooltip is the browser's native tooltip, which a test cannot see; the testId identifies the element that carries it.

## Prohibition on Bespoke Tooltip Implementations

**DO NOT** create a custom tooltip implementation. Always use:

- the plain `title` attribute for simple cases, or
- the shared `Tooltip` component for everything else.

### What Counts as a Bespoke Tooltip?

- A manual `createPortal` with tooltip-like positioning
- Inline tooltip divs driven by an `isHovered` state
- CSS-only `group-hover` tooltips
- Custom positioning logic (`getBoundingClientRect`, viewport collision detection)
- Timer-based show/hide logic

### PR Checklist Item

Before merging:

- [ ] No custom tooltip implementation (check for `createPortal`, inline tooltip divs, custom positioning logic)
- [ ] Every tooltip uses either the plain `title` attribute or the shared `Tooltip` component
- [ ] No `role="tooltip"` outside the shared `Tooltip` component

### Why This Rule?

Custom tooltip implementations:

- Behave inconsistently (different timing, positioning bugs)
- Duplicate complex code (event coordination, viewport handling, accessibility)
- Are harder to test (no standard selectors, inconsistent structure)
- Accumulate bugs (quick mouse movement, click behavior, memory leaks)

The shared `Tooltip` component keeps that complexity in one implementation, with its positioning in `useTooltip` (`src/components/primitives/use-tooltip.ts`).

## Summary

- **Plain `title`**: simple text, no disabled handling needed
- **`Tooltip` with `title`**: simple text on a disabled element
- **`Tooltip` with `content`**: rich content, formatting, or a placement
- **Never**: a custom tooltip implementation
- **Always**: informational content only (no interactive elements)
- **Testing**: visibility assertions, not test events
