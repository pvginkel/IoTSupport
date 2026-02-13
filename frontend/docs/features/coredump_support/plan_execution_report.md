# Core Dump Support — Plan Execution Report

## Status

**DONE-WITH-CONDITIONS** — Slices 1-3 of the plan are fully implemented and pass TypeScript strict mode. Slice 4 (Playwright tests) is deferred pending backend support for coredump data seeding.

## Summary

All UI functionality for core dump support has been implemented:

- **Slice 1 (Data layer):** Custom `use-coredumps.ts` hook with camelCase domain models, `lastCoredumpAt` added to `DeviceSummary` interface and the device list table as a sortable column.
- **Slice 2 (Core dumps table):** `CoredumpTable` component rendered below the device logs viewer on the device editor page. Includes empty state, loading skeleton, error state, row click navigation, download links, and delete with confirmation dialog.
- **Slice 3 (Core dump detail page):** New route at `/devices/$deviceId/coredumps/$coredumpId` with metadata display, download link, and read-only Monaco editor (plain text, no syntax highlighting) for parsed output.

Playwright tests (Slice 4) are deferred because the backend must expose a mechanism to seed coredump data from the test harness (see plan Section 15 risk).

## Files Created

| File | Purpose |
|------|---------|
| `src/hooks/use-coredumps.ts` | Custom hook wrapping generated coredump API hooks |
| `src/components/devices/coredump-table.tsx` | Core dumps table component |
| `src/components/devices/coredump-detail.tsx` | Core dump detail page component |
| `src/routes/devices/$deviceId/coredumps/$coredumpId.tsx` | Detail page route |
| `src/lib/utils/format.ts` | `formatFileSize` utility |

## Files Modified

| File | Change |
|------|--------|
| `src/hooks/use-devices.ts` | Added `lastCoredumpAt` to `DeviceSummary` and transform |
| `src/lib/utils/sort-preferences.ts` | Added `lastCoredumpAt` to sort column union and validation |
| `src/components/devices/device-list-table.tsx` | Added sortable "Last Core Dump" column |
| `src/components/devices/device-editor.tsx` | Renders `CoredumpTable` below device logs viewer |
| `src/routeTree.gen.ts` | Auto-regenerated to include the new coredump detail route |

## Code Review Summary

- **Decision:** GO-WITH-CONDITIONS
- **BLOCKER:** 0
- **MAJOR:** 2 (both resolved)
  1. No Playwright tests — acknowledged as deferred (Slice 4, backend dependency)
  2. Two-layer callback risk for instrumentation tracking — fixed by forwarding call-site callbacks through the hook's `mutate` wrapper
- **MINOR:** 2 (both resolved)
  1. `formatFileSize` co-located with hooks — moved to `src/lib/utils/format.ts`
  2. Unreachable `ConfirmDialog` in empty state — removed

## Verification Results

- `pnpm check` (lint + TypeScript): **PASS**
- `pnpm generate:routes`: **PASS** (route tree regenerated)
- Requirements verification: **9/9 PASS** (see `requirements_verification.md`)
- Git diff reviewed: Changes are focused and match plan scope

## Outstanding Work & Suggested Improvements

- **Playwright tests (Slice 4):** Factory extensions for `DevicesFactory`, page object updates for `DevicesPage`, and `devices-coredumps.spec.ts` must be delivered once backend coredump seeding is available. The instrumentation hooks (`coredumps.list` scope, `CoredumpDelete` form events, all `data-testid` attributes) are already in place.
- **Backend verification:** Confirm the download endpoint sets `Content-Disposition: attachment` so the browser downloads rather than navigating. The `download` attribute on the anchor tag provides a fallback hint.
