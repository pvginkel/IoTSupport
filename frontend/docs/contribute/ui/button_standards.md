# Button Labeling Standards

This document defines the standard for button labels in the IoT Support frontend, so labels stay consistent, clear and accessible.

## Core Principle: `<verb> <noun>` Format

Every button label follows the **`<verb> <noun>`** pattern and names the business function it performs.

### Examples

✅ **Good** (from the app)
- "Flash Device"
- "Provision Device"
- "Recreate Client"
- "Insert Template"
- "Trigger Fleet Rotation"
- "Create Device Model"

❌ **Bad**
- "Add" (missing noun — add what?)
- "Save" (missing noun — save what?)
- "Retry" (missing noun — retry what?)
- "Done" (not action-oriented)

Some existing labels do not follow the standard — the editors' **Save** and **Duplicate**, the log viewer's **Download**, and the USB modals' **Connect**, **Retry** and **Done**. They are not precedents: a new or changed button follows the standard.

## Style Guidelines

### 1. Title Case

Use title case for every button label, capitalizing the first letter of each major word.

✅ **Good**
- "Trigger Fleet Rotation"
- "Create Device Model"

❌ **Bad**
- "Trigger fleet rotation"
- "create device model"

### 2. Business-Function Naming

Use the domain's language for what the user accomplishes, not the technical operation underneath.

✅ **Good**
- "Provision Device" (the user gives the device its credentials)
- "Trigger Fleet Rotation" (the user starts a credential rotation across the fleet)

❌ **Bad**
- "Write NVS Partition" (the mechanism, not the goal)
- "Queue Devices" (a state change, not what the user is doing)

### 3. No Emojis

Do not put emojis in button labels. For visual distinction, add a `lucide-react` icon: through the `icon` prop of `Button` (`src/components/primitives/button.tsx`), or as the first child, as the Configuration tab's device actions do.

✅ **Good**
```tsx
<Button variant="outline" onClick={() => setFlashModalOpen(true)}>
  <Zap className="h-4 w-4 mr-2" />
  Flash Device
</Button>
```

❌ **Bad**
```tsx
<Button variant="outline">
  ⚡ Flash
</Button>
```

### 4. No Abbreviations

Avoid abbreviations unless the domain uses them as words (OTA, JSON, USB).

✅ **Good**
- "Insert Template"
- "Provision Device"

❌ **Bad**
- "Ins Tmpl"
- "Prov Dev"

## Icon-Only Buttons

An icon-only button (no visible text) **must** carry an `aria-label` that follows the same `<verb> <noun>` pattern. A `title` adds a hover hint but does not replace the label.

✅ **Good**
```tsx
<Button variant="destructive" size="sm" aria-label="Delete Device" onClick={handleDelete}>
  <Trash2 className="h-4 w-4" />
</Button>
```

❌ **Bad**
```tsx
<Button variant="destructive" size="sm" onClick={handleDelete}>
  <Trash2 className="h-4 w-4" />
</Button>
```

The app's icon-only buttons — the list rows' delete buttons, the rotation dashboard's per-device rotate button, the Keycloak resync button — carry a `title` and no `aria-label`, and the device header's back link carries neither; they do not meet this rule.

## Acceptable Exceptions

### Generic "Cancel"

Editors and dialogs may use a plain "Cancel" when the title and context make clear what is being cancelled, as the device and device model editors and the Flash Device and Provision Device modals do.

### Loading States

Pass `loading` to `Button` instead of swapping the label for "Saving…": it overlays a spinner, keeps the label in the layout so the button keeps its width, and disables the button.

```tsx
<Button variant="primary" onClick={handleTriggerRotation} loading={triggerRotation.isPending}>
  Trigger Fleet Rotation
</Button>
```

## Testing & Verification

### Manual Review Checklist

When adding or changing a button:

1. ✅ The label follows `<verb> <noun>` (or is an accepted exception)
2. ✅ The label uses business-function language, not technical jargon
3. ✅ The label is in title case
4. ✅ No emojis or unnecessary abbreviations
5. ✅ An icon-only button has a descriptive `aria-label`

### Accessibility Testing

Test icon-only buttons with a screen reader:
- Every button announces its purpose
- No button is announced as just "button"
- Tools like axe DevTools or Lighthouse flag missing labels

### Playwright Tests

Update test selectors when a label changes:

```ts
// Role and accessible name, matched loosely
await page.getByRole('button', { name: /flash device/i }).click();

// Test id, unaffected by the label
await page.getByTestId('devices.editor.flash-device').click();
```

## Fixing a Non-Compliant Label

1. **Identify the business function**: what is the user trying to accomplish?
2. **Choose an action verb**: Create, Save, Delete, Flash, Provision, and so on.
3. **Add the object noun**: Device, Device Model, Client, Template, and so on.
4. **Update related tests**: check for selectors that match on the button text.
5. **Verify accessibility**: make sure icon-only buttons have an `aria-label`.

## Questions?

If you are unsure whether a label meets the standard:

1. Ask yourself: "If I saw this button out of context, would I know exactly what it does?"
2. Look for a similar compliant button among the good examples above.
3. Raise it in review when the business function is ambiguous.

## References

- [WCAG 2.1 Success Criterion 4.1.2: Name, Role, Value](https://www.w3.org/WAI/WCAG21/Understanding/name-role-value.html)
- [Button Labeling Best Practices](https://www.nngroup.com/articles/button-design-principles/)
- [Architecture → Application Overview](../architecture/application_overview.md)
