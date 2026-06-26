# IoT Support Frontend - Implementation Plan

This document outlines the implementation phases for the IoT Support frontend application.

**Important**: Implementation is split into two deliverables:
- **Phase A**: Project scaffolding, app shell, and complete Playwright test infrastructure
- **Phase B**: Feature implementation (device list, editor, delete flow)

Phase A must be fully working before Phase B begins. This ensures all features are testable from the start.

---

## Phase A: Foundation & Test Infrastructure

### A1. Project Scaffolding

#### A1.1 Initialize Project Structure

- Copy and adapt `package.json` from ElectronicsInventory with required dependencies:
  - React 19, TypeScript, Vite
  - TanStack Router and Query
  - Tailwind CSS 4
  - Radix UI primitives
  - Monaco Editor (`@monaco-editor/react`)
  - openapi-fetch and openapi-typescript
  - Playwright and test utilities
- Set up TypeScript configuration (strict mode)
- Configure Vite with:
  - React plugin
  - Tailwind CSS plugin
  - Proxy for `/api` to `localhost:3201`
  - Dev server on port 3200
  - Test mode environment variable handling
- Initialize Tailwind with dark mode configuration
- Set up ESLint and Prettier

#### A1.2 API Generation Pipeline

- Copy and adapt `scripts/generate-api.js` from ElectronicsInventory
- Configure to fetch OpenAPI spec from `http://localhost:3201/api/docs`
- Generate TypeScript types to `src/lib/api/generated/types.ts`
- Generate TanStack Query hooks to `src/lib/api/generated/hooks.ts`
- Add `pnpm generate:api` script

#### A1.3 Core Application Setup

- Create `src/main.tsx` entry point
- Create `src/App.tsx` with:
  - TanStack Router provider
  - TanStack Query provider
  - Toast context provider
- Set up file-based routing structure in `src/routes/`
- Create root layout with dark mode styling

### A2. App Shell

#### A2.1 Layout Components

- Create `src/components/layout/AppShell.tsx`:
  - Dark mode styling
  - Fixed sidebar with "IoT Support" branding
  - Main content area with outlet
  - Test ID: `app-shell`
- Create `src/components/layout/Sidebar.tsx`:
  - "Device Configs" navigation item
  - Active state styling
  - Prepared for future expansion
  - Test ID: `sidebar`

#### A2.2 Basic Routing

- Create route files:
  - `src/routes/__root.tsx` - Root layout with AppShell
  - `src/routes/index.tsx` - Redirect to /devices
  - `src/routes/devices/index.tsx` - Placeholder device list page
- Verify navigation works between routes

### A3. Playwright Test Infrastructure

> **Detailed implementation**: See [Playwright Implementation Plan](./playwright_implementation_plan.md)

This phase implements the complete test infrastructure before any feature work begins.

#### A3.1 Configuration & Environment

- Create `playwright.config.ts` with per-worker isolation
- Create `.env.test` with managed services configuration
- Create `tests/support/global-setup.ts`

#### A3.2 Service Management

- Create `scripts/testing-server.sh` for frontend test server
- Create `tests/support/process/servers.ts` for service startup
- Create `tests/support/process/log-collector.ts` for log capture
- Implement port allocation with `get-port`
- Implement health check polling

#### A3.3 Test Fixtures

- Create `tests/support/fixtures.ts` with:
  - `_serviceManager` (worker-scoped): Manages backend + frontend per worker
  - `backendUrl`, `frontendUrl`: Service URLs
  - `apiClient`: OpenAPI client for test data
  - `testData`: Factory bundle
  - `page`: Enhanced page with test event bridge
  - `testEvents`: Event capture buffer
  - `devices`: Page object fixture

#### A3.4 Test Event System

- Create `src/types/test-events.ts` with event type definitions
- Create `src/lib/config/test-mode.ts` with `isTestMode()` guard
- Create `src/lib/test/event-emitter.ts` for emitting events
- Create `tests/support/helpers/test-events.ts` for capturing events

#### A3.5 API Factories

- Create `tests/api/client.ts` with OpenAPI client wrapper
- Create `tests/api/factories/config-factory.ts` with:
  - `randomMacAddress()` - Generate valid MAC addresses
  - `create()` - Create config via API
  - `createMany()` - Bulk creation
  - `delete()` - Delete config via API
- Create `tests/api/index.ts` exporting test data bundle

#### A3.6 Page Objects

- Create `tests/support/page-objects/base-page.ts`
- Create `tests/support/page-objects/devices-page.ts`
- Create `tests/support/page-objects/device-editor-page.ts`

#### A3.7 Smoke Tests

- Create `tests/smoke.spec.ts` with:
  - Frontend loads and displays app shell
  - Backend health endpoint responds
  - Device list loads (empty state placeholder)

### A4. Phase A Verification

Before proceeding to Phase B:

- [ ] `pnpm check` passes (lint + typecheck)
- [ ] `pnpm build` succeeds
- [ ] `pnpm dev` starts frontend on port 3200
- [ ] `pnpm playwright test tests/smoke.spec.ts` passes
- [ ] Services start/stop cleanly per worker
- [ ] Logs attach to test results on failure
- [ ] API factories create/delete configs successfully

---

## Phase B: Feature Implementation

### B1. Shared Infrastructure

#### B1.1 Toast System

- Create `src/contexts/ToastContext.tsx`:
  - Radix UI Toast primitive
  - Support for success, error, info variants
  - Auto-dismiss with configurable duration
  - Dark mode styling

#### B1.2 Error Handling

- Create `src/lib/utils/errorHandling.ts`:
  - Parse API error responses
  - Extract user-friendly messages
  - Integrate with toast system

#### B1.3 UI Components

- Create `src/components/ui/Button.tsx` with variants
- Create `src/components/ui/Skeleton.tsx` for loading states
- Create `src/components/ui/ConfirmDialog.tsx`:
  - Radix UI Dialog primitive
  - Dark mode styling
  - Destructive styling for delete actions

### B2. Device List View

#### B2.1 List Component

- Create `src/components/devices/DeviceList.tsx`:
  - Fetch devices using generated `useGetConfigs` hook
  - Display table with columns: MAC Address, Device Name, Entity ID, OTA Status
  - OTA Status renders as check icon, cross icon, or empty for null
  - Skeleton loader during fetch
  - Empty state with "No devices configured" message and create button
  - Test IDs for all interactive elements

#### B2.2 Sorting Implementation

- Create `src/hooks/useDeviceListSort.ts`:
  - Sortable columns: all four fields
  - Sort direction toggle (asc/desc)
  - Persist sort preferences to localStorage
  - Key: `iot-support-device-sort`

#### B2.3 List Instrumentation

- Add `useListLoadingInstrumentation` to DeviceList
- Emit `list_loading` events with phase and item count

#### B2.4 List Actions

- Add "New Device" button in header
- Add row actions: Edit button, Delete button
- Wire up navigation to editor routes

#### B2.5 List Tests

- Create `tests/e2e/devices/list.spec.ts`:
  - Displays device list with seeded data
  - Sorting works on all columns
  - Sort persists after navigation
  - Empty state shows correctly
  - Navigation to editor works

### B3. Device Editor

#### B3.1 Editor Component

- Create `src/components/devices/DeviceEditor.tsx`:
  - MAC address input field (text input, editable)
  - Monaco Editor for JSON content:
    - Language: JSON
    - Theme: vs-dark
    - Minimap disabled
    - Code folding enabled
    - Auto-indent enabled
    - Tab size: 2
  - Action buttons: Save, Cancel, Duplicate (edit mode only)
  - Test IDs for all elements

#### B3.2 Editor Routes

- Create `src/routes/devices/new.tsx`:
  - Empty MAC address field
  - Pre-filled JSON template
  - No Duplicate button

- Create `src/routes/devices/$macAddress.tsx`:
  - MAC address pre-filled (still editable)
  - JSON loaded from API
  - Duplicate button available

- Create `src/routes/devices/$macAddress.duplicate.tsx`:
  - Empty MAC address field
  - JSON copied from source device

#### B3.3 Save Logic

- Create `src/hooks/useDeviceSave.ts`:
  - Use generated `usePutConfig` mutation
  - If MAC address changed in edit mode:
    - Save to new MAC address
    - Delete old MAC address
  - On success: navigate to list, show success toast
  - On error: show error toast with backend message

#### B3.4 Unsaved Changes Protection

- Create `src/hooks/useUnsavedChanges.ts`:
  - Track dirty state (MAC changed or JSON changed)
  - Register `beforeunload` handler
  - Integrate with TanStack Router navigation blocking
  - Show confirmation dialog on navigation attempt

#### B3.5 Editor Instrumentation

- Add form instrumentation to DeviceEditor
- Emit `form` events for submit, success, error

#### B3.6 Editor Tests

- Create `tests/e2e/devices/create.spec.ts`:
  - Can create new device with valid data
  - Shows validation errors from backend
  - Cancel navigates back without saving
  - Unsaved changes warning works

- Create `tests/e2e/devices/edit.spec.ts`:
  - Loads existing device data
  - Can update device content
  - Can change MAC address (rename)
  - Duplicate creates new device with empty MAC

### B4. Delete Flow

#### B4.1 Delete Implementation

- Create `src/hooks/useDeviceDelete.ts`:
  - Use generated `useDeleteConfig` mutation
  - Trigger confirmation dialog before delete
  - On success: refresh list, show success toast
  - On error: show error toast

#### B4.2 Delete Tests

- Create `tests/e2e/devices/delete.spec.ts`:
  - Delete shows confirmation dialog
  - Cancel keeps device
  - Confirm removes device from list

### B5. Phase B Verification

Final verification before handoff:

- [ ] `pnpm check` passes
- [ ] `pnpm build` succeeds
- [ ] All Playwright tests pass: `pnpm playwright test`
- [ ] Manual testing of all workflows complete

---

## File Structure

```
src/
├── main.tsx
├── App.tsx
├── routes/
│   ├── __root.tsx
│   ├── index.tsx
│   └── devices/
│       ├── index.tsx
│       ├── new.tsx
│       ├── $macAddress.tsx
│       └── $macAddress.duplicate.tsx
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   └── Sidebar.tsx
│   ├── devices/
│   │   ├── DeviceList.tsx
│   │   ├── DeviceEditor.tsx
│   │   └── DeviceListSkeleton.tsx
│   └── ui/
│       ├── ConfirmDialog.tsx
│       ├── Skeleton.tsx
│       └── Button.tsx
├── hooks/
│   ├── useDevices.ts
│   ├── useDevice.ts
│   ├── useDeviceSave.ts
│   ├── useDeviceDelete.ts
│   ├── useDeviceListSort.ts
│   └── useUnsavedChanges.ts
├── contexts/
│   └── ToastContext.tsx
├── lib/
│   ├── api/
│   │   ├── client.ts
│   │   └── generated/
│   │       ├── types.ts
│   │       └── hooks.ts
│   ├── config/
│   │   └── test-mode.ts
│   ├── test/
│   │   ├── event-emitter.ts
│   │   ├── useListLoadingInstrumentation.ts
│   │   └── useFormInstrumentation.ts
│   └── utils/
│       └── errorHandling.ts
└── types/
    ├── index.ts
    └── test-events.ts

tests/
├── api/
│   ├── client.ts
│   ├── index.ts
│   └── factories/
│       └── config-factory.ts
├── e2e/
│   └── devices/
│       ├── list.spec.ts
│       ├── create.spec.ts
│       ├── edit.spec.ts
│       └── delete.spec.ts
├── support/
│   ├── fixtures.ts
│   ├── global-setup.ts
│   ├── helpers/
│   │   ├── test-events.ts
│   │   └── index.ts
│   ├── page-objects/
│   │   ├── base-page.ts
│   │   ├── devices-page.ts
│   │   └── device-editor-page.ts
│   └── process/
│       ├── servers.ts
│       └── log-collector.ts
└── smoke.spec.ts

scripts/
├── generate-api.js
└── testing-server.sh
```

## Dependencies

```json
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@tanstack/react-router": "^1.x",
    "@tanstack/react-query": "^5.x",
    "@monaco-editor/react": "^4.x",
    "@radix-ui/react-dialog": "^1.x",
    "@radix-ui/react-toast": "^1.x",
    "openapi-fetch": "^0.x",
    "clsx": "^2.x"
  },
  "devDependencies": {
    "typescript": "^5.x",
    "vite": "^6.x",
    "@vitejs/plugin-react": "^4.x",
    "@tailwindcss/vite": "^4.x",
    "tailwindcss": "^4.x",
    "openapi-typescript": "^7.x",
    "@playwright/test": "^1.x",
    "dotenv": "^16.x",
    "get-port": "^7.x",
    "split2": "^4.x",
    "eslint": "^9.x"
  }
}
```
