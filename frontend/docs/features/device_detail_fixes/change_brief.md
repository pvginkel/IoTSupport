# Change Brief: Device Detail UX Fixes

## Overview

Three fixes/enhancements to the device detail experience, two of which are regressions from previous attempts.

## Fix 1: COM Port Must Disconnect After Flash

**Commit**: edbd14d — added `await cleanup()` on the success path in `use-provisioning.ts`.

**Problem**: The COM port stays locked after a successful flash. The `cleanup()` function (line 119) always calls `abortControllerRef.current.abort()` first, which fires the abort signal. On the success path this is counter-productive: there are no pending operations to abort, and firing the abort signal may interfere with the transport's internal reader/writer stream locks, preventing the serial port from actually closing. The transport's `disconnect()` method needs to cleanly release reader/writer locks before `port.close()` can succeed, and aborting signals can corrupt that teardown sequence.

**Fix**: Split cleanup into two concerns. On the success path, only disconnect the transport and close the serial port — do NOT fire the abort controller. The abort should only happen when explicitly cancelling in-flight operations (user abort or error).

**Files**: `src/hooks/use-provisioning.ts`

## Fix 2: Remember Selected Device Tab Across Navigation

**Commit**: acb4f64 — added localStorage persistence + `beforeLoad` redirect in the index route.

**Problem**: When a user switches to the Logs tab on device A, navigates back to the device list, and opens device B, the Configuration tab always shows. The `beforeLoad` redirect in `$deviceId/index.tsx` reads from localStorage and throws a `redirect()`, but this mechanism does not reliably trigger navigation for the index route in TanStack Router's file-based routing.

**Fix**: Replace the `beforeLoad` redirect with a component-level approach. In the index route's component (`ConfigurationTabRoute`), use `useEffect` + `useNavigate` to read the stored tab preference and navigate to the correct tab on mount. This is more reliable because it runs within the React lifecycle after the component tree is mounted, avoiding any `beforeLoad` timing/redirect issues.

**Files**: `src/routes/devices/$deviceId/index.tsx`, `src/lib/utils/device-tab-preference.ts`, `src/components/devices/device-detail-header.tsx`

## Fix 3: Switch to Logs Tab After Saving Device Config

**New feature**: After successfully saving device configuration (edit mode), navigate to the device's Logs tab instead of back to the device list. This provides immediate feedback by showing the device's live log stream.

**Fix**: In `use-device-form.ts`, change the `onSuccess` handler for edit mode to navigate to `/devices/$deviceId/logs` instead of `/devices`. Also update the tab preference in localStorage so subsequent visits remember the logs tab.

**Files**: `src/hooks/use-device-form.ts`
