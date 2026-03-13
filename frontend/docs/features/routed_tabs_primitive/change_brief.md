# Change Brief: Routed Tabs Primitive

## Summary

Extract the URL-driven tab bar and "remember last tab" persistence logic from `src/components/devices/device-detail-header.tsx` into a reusable primitive component at `src/components/primitives/`. Then refactor the devices domain to consume the new primitive.

## Current State

- `device-detail-header.tsx` bundles device-specific header content, a tab bar (using `Link` components with underline indicators), and localStorage-based tab preference persistence.
- `device-tab-preference.ts` provides `getDeviceTabPreference()` / `setDeviceTabPreference()` for localStorage read/write with validation.
- The index route (`devices/$deviceId/index.tsx`) reads the preference and redirects to the last-used tab.
- Tabs are route-driven via TanStack Router — each tab corresponds to a child route.
- The "Core Dumps" tab includes a count badge as part of its label.

## Desired State

1. A new **reusable `RoutedTabs` primitive** in `src/components/primitives/` that provides:
   - A tab bar rendering TanStack Router `Link` components with active-state underline styling.
   - Tab definitions accepting `ReactNode` labels (allowing consumers to compose badges or other content).
   - Built-in localStorage preference persistence via a configurable `storageKey`.
   - A helper/hook for index-route redirect logic (restore last tab on bare URL visit).
   - Proper `data-testid` support with a configurable prefix.

2. The **devices domain refactored** to consume this primitive:
   - `DeviceDetailHeader` uses the new `RoutedTabs` for its tab bar, keeping only device-specific header content.
   - The device tab preference utility is replaced by the primitive's built-in persistence.
   - The index route redirect uses the primitive's helper.
   - The "Core Dumps" badge is passed as a `ReactNode` label by the consumer.

3. Existing Playwright tests updated to work with any changed test IDs.

## Non-Goals

- Per-entity tab persistence (e.g., different tab per device ID) — may be added later.
- Replacing or extending `SegmentedTabs` — that primitive serves a different purpose (in-page state switching).
- Adding badge/count as a first-class feature of the primitive — consumers compose this via `ReactNode` labels.
