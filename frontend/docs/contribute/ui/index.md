# UI Guidelines Overview

## About This Suite
This section of the contributor docs describes how the IoT Support frontend's screens are built: the components they compose, the hooks they fetch and mutate through, and the instrumentation Playwright waits on. What the screens are for is in the [product brief](../../product_brief.md); the stack is in [Architecture → Application Overview](../architecture/application_overview.md). Treat these pages as the description of the frontend as it is; a feature plan cites them and describes only what changes.

## How To Use These Docs
1. Start with the **Pattern Library** below and pick the surface closest to the one you are touching. Each pattern lists its routes, components, hooks, instrumentation scopes and test ids.
2. Check the **Shared Building Blocks** for the form, data-display, button and tooltip conventions before adding a new UI element. Reuse what the screens already use.
3. When drafting a plan, cite sections (for example, "see UI → Devices → Implementation Checklist") and limit the plan to deltas.
4. Cross-check the plan against [Testing](../testing/index.md) and the [Playwright Developer Guide](../testing/playwright_developer_guide.md) so the instrumentation it needs is in it.

## Pattern Library
- [Device Models Pattern](./patterns/device_models.md) – a sortable table and a full-page editor reached by its own route; the shape for an entity that has no view beyond its editor.
- [Devices Pattern](./patterns/devices.md) – a sortable table, a detail layout route with URL-driven tabs, full-page editors for new and duplicate, and the Flash device / Provision device modals over USB.

The Rotation Dashboard (`src/components/rotation/rotation-dashboard.tsx`, route `/rotation`) has no pattern page; [Data Display Conventions](./data_display.md) covers its states and instrumentation.

## Component Folders
- `src/components/device-models/`, `src/components/devices/`, `src/components/rotation/` – the app's own screen components.
- `src/components/primitives/` – what the screens build with: `Button`, `Dialog` and `ConfirmDialog`, `Input`, and `RoutedTabs` with its `useRestoreTab` / `setTabPreference` helpers.
- `src/components/ui/` – `Skeleton`, `EmptyState` and the Radix-based `Select`.
- `src/components/layout/` – the app shell that `src/routes/__root.tsx` renders (`Sidebar`, `TopBar`). The sidebar's entries are `navigationItems` in `src/components/layout/sidebar-nav.ts`.

`layout/`, `primitives/` and `ui/` are template-owned (listed in `knip-template-ignore.json`) and carry more than the screens use: `ListScreenLayout`, `DetailScreenLayout`, `FormScreenLayout`, `ListScreenCounts`, `Tooltip`, `SegmentedTabs`, `SearchableSelect`, `DescriptionList`, `Form` / `FormField` / `FormLabel` and others are imported by no screen. `ui/` also has a `button.tsx`, `dialog.tsx` and `input.tsx`; the screens import `Button`, `Dialog` and `Input` from `primitives/`.

## Shared Building Blocks
- [Button Labeling Standards](./button_standards.md) – the `<verb> <noun>` pattern, business-function naming, accessibility requirements and the accepted exceptions for button labels.
- [Form Conventions](./forms.md) – full-page editors, unsaved-changes handling, mutations through the domain hooks, and `useFormInstrumentation`.
- [Data Display Conventions](./data_display.md) – tables, sorting, loading / empty / error states, the detail surfaces, and `useListLoadingInstrumentation` / `useUiStateInstrumentation`.
- [Tooltip Guidelines](./tooltip_guidelines.md) – when to use a plain `title` and when the shared `Tooltip` component, its disabled-element handling and placement modes, and the prohibition on bespoke tooltip implementations.

## Related References
- [Contributor Hub](../index.md) for setup, environment, and process guidance.
- [Architecture → Test Instrumentation](../architecture/test_instrumentation.md) for the test-event taxonomy.
- [Testing → Playwright Developer Guide](../testing/playwright_developer_guide.md) and [Testing → Factories & Fixtures](../testing/factories_and_fixtures.md) for real-backend execution rules, the fake USB device and selector strategy.
- [Firmware flashing](../../../../docs/firmware-flashing.md) for the design behind Flash device.
