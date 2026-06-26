# Device Provisioning MDM - Frontend Technical Plan

## 0) Research Log & Findings

**Discovery areas searched:**

- `docs/commands/plan_feature.md` - planning template and structure requirements
- `docs/features/device_provisioning_mdm/change_brief.md` - requirements and scope
- `docs/contribute/architecture/application_overview.md` - React 19 + TanStack architecture patterns
- `docs/contribute/testing/playwright_developer_guide.md` - testing conventions, factory patterns, instrumentation requirements
- `docs/contribute/testing/factories_and_fixtures.md` - factory bundle structure

**Relevant components/hooks identified:**

- `src/hooks/use-devices.ts` - existing device hooks using old `/api/configs` endpoints (will be replaced)
- `src/components/devices/device-editor.tsx` - JSON editor with Monaco, form handling patterns
- `src/components/devices/device-list-table.tsx` - table component with sorting
- `src/components/layout/sidebar.tsx` - navigation items configuration
- `src/routes/devices/` - existing device routes structure

**Instrumentation helpers:**

- `src/lib/test/query-instrumentation.ts` - `useListLoadingInstrumentation` hook for list loading events
- `src/types/test-events.ts` - test event types for Playwright integration

**Test infrastructure:**

- `tests/api/factories/devices.ts` - current factory using old `/api/configs` endpoints (broken)
- `tests/e2e/devices/DevicesPage.ts` - page object for devices
- `tests/e2e/devices/devices-crud.spec.ts` - existing CRUD specs (will need updates)
- `tests/support/fixtures.ts` - test fixture setup

**OpenAPI schema review:**

- New endpoints: `/api/devices`, `/api/device-models`, `/api/rotation/*`
- Device model schema includes `config_schema` for JSON Schema validation
- Devices now use `key` (8-char auto-generated) instead of MAC address
- Rotation dashboard returns devices grouped by `healthy`, `warning`, `critical`

**Conflicts resolved:**

- The existing `use-devices.ts` hooks reference old `/api/configs` endpoints which no longer exist in the OpenAPI spec; the file must be rewritten entirely
- Test factory at `tests/api/factories/devices.ts` also uses old endpoints and must be updated

---

## 1) Intent & Scope

**User intent**

Migrate the frontend from a MAC-address-based device configuration system to a device/device-model architecture with automated secret rotation and health monitoring. This includes creating new management pages for device models and a rotation dashboard, while updating the existing devices page to work with the new API structure.

**Prompt quotes**

- "Replace the MAC-address-based system"
- "Device Models: Hardware type definitions with optional JSON Schema for config validation"
- "Devices: Now identified by auto-generated 8-character keys (not MAC addresses)"
- "Secret Rotation: Automated credential rotation with health status tracking (healthy/warning/critical)"
- "Monaco Editor supports JSON Schema validation via monaco.languages.json.jsonDefaults.setDiagnosticsOptions()"

**In scope**

- Navigation updates: rename "Device Configs" to "Devices", add "Device Models" and "Rotation"
- Device models CRUD pages (list, create, edit with JSON Schema editor)
- Device management updates (new fields, model selector, provisioning download, rotation badges)
- Rotation dashboard with health grouping and fleet-wide trigger
- Custom hooks for device models and rotation endpoints
- Monaco editor JSON Schema validation for both config editing and schema editing
- Test factory updates and new Playwright specs

**Out of scope**

- Firmware upload UI (pipeline only per change brief)
- IoT device endpoints (`/iot/*`) - device consumption, not admin UI
- Backend changes (API is already ready)

**Assumptions / constraints**

- Backend API at `/api/devices`, `/api/device-models`, `/api/rotation/*` is stable and deployed
- Generated API client will be regenerated with `pnpm generate:api` before implementation
- JSON Schema meta-schema (draft-07) is available for config_schema validation
- Provisioning download endpoint returns binary `.bin` file for direct download

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

Navigation:
- [ ] Add "Device Models" as a top-level navigation item
- [ ] Add "Rotation" as a top-level navigation item
- [ ] Rename existing "Device Configs" to "Devices"

Device Models Management:
- [ ] Create device models list page showing: code, name, has_config_schema, device_count, firmware_version
- [ ] Create device model create form with: code (pattern validated), name, config_schema (JSON editor)
- [ ] Create device model edit form with: name (editable), config_schema (editable), code (read-only display)
- [ ] Config schema editor must validate that the schema is a valid JSON Schema (use JSON Schema meta-schema)
- [ ] Delete button disabled when device_count > 0

Devices Management:
- [ ] Update devices list to show: key, device_name, device_entity_id, enable_ota, model name, rotation_state badge
- [ ] Remove MAC address input from device creation - key is auto-generated
- [ ] Add device model selector dropdown to device create form
- [ ] Device config JSON editor should use model's config_schema for validation and autocomplete
- [ ] Device edit form shows key and model as read-only
- [ ] Add provisioning download button to device edit view
- [ ] Rotation state badges: OK (green), QUEUED (yellow), PENDING (blue+spinner), TIMEOUT (red)

Rotation Dashboard:
- [ ] Create dedicated rotation dashboard page
- [ ] Show summary counts with colored indicators (healthy=green, warning=orange, critical=red)
- [ ] Display device lists grouped by health status (healthy, warning, critical)
- [ ] Each device row shows: key, device_name, model_code, rotation_state, days_since_rotation
- [ ] Add "Trigger Rotation" button for fleet-wide rotation
- [ ] Show link to pending device if rotation in progress

Test Infrastructure:
- [ ] Update test factory to use new /api/devices endpoints (currently broken using old /api/configs)
- [ ] Add test factory for device models
- [ ] Update Playwright specs for device CRUD with new model selector flow
- [ ] Add Playwright specs for device models CRUD
- [ ] Add Playwright specs for rotation dashboard

Technical:
- [ ] Regenerate API client with `pnpm generate:api`
- [ ] Create `useFormInstrumentation` hook for form lifecycle events (Playwright deterministic assertions)
- [ ] Create custom hooks for device models (useDeviceModels, useDeviceModel, useCreateDeviceModel, etc.)
- [ ] Create custom hooks for rotation (useRotationDashboard, useRotationStatus, useTriggerRotation)
- [ ] Update existing device hooks to use new API schema
- [ ] Configure Monaco editor JSON Schema validation using URI-based schema association (not global defaults)
- [ ] Device list fetches device models for client-side model name lookup

---

## 2) Affected Areas & File Map

### Navigation

- Area: `src/components/layout/sidebar.tsx`
- Why: Add "Device Models" and "Rotation" navigation items; rename "Device Configs" to "Devices"
- Evidence: `sidebar.tsx:23-25` defines `navigationItems` array with single "Device Configs" entry

### Device Hooks (Complete Rewrite)

- Area: `src/hooks/use-devices.ts`
- Why: Completely rewrite to use new `/api/devices` endpoints with new schema (key, device_model_id, rotation_state)
- Evidence: `use-devices.ts:4-11` imports old `useGetConfigs`, `usePostConfigs` etc. from generated hooks; these will be replaced with new device endpoint hooks

### Device Model Hooks (New)

- Area: `src/hooks/use-device-models.ts` (new file)
- Why: Create hooks for device model CRUD operations
- Evidence: OpenAPI spec at lines 1320-1563 defines `/api/device-models` and `/api/device-models/{model_id}` endpoints

### Rotation Hooks (New)

- Area: `src/hooks/use-rotation.ts` (new file)
- Why: Create hooks for rotation dashboard, status, and trigger endpoints
- Evidence: OpenAPI spec at lines 2104-2205 defines `/api/rotation/dashboard`, `/api/rotation/status`, `/api/rotation/trigger`

### Device List Page

- Area: `src/routes/devices/index.tsx`
- Why: Update to show new fields (key, model name, rotation state badges) and remove MAC address column
- Evidence: `devices/index.tsx:17-30` uses `useDevices()` hook and passes `devices` to `DeviceListTable`

### Device List Table

- Area: `src/components/devices/device-list-table.tsx`
- Why: Update columns from MAC-based to key-based; add model name and rotation state badge columns
- Evidence: `device-list-table.tsx:77-80` renders MAC address column header and cells

### Device Editor (Major Update)

- Area: `src/components/devices/device-editor.tsx`
- Why: Remove MAC input, add model selector, add provisioning download, add schema-based validation
- Evidence: `device-editor.tsx:42-43` manages MAC address state; `device-editor.tsx:281-294` renders Monaco without schema validation

### Device Create Route

- Area: `src/routes/devices/new.tsx`
- Why: Update to support new creation flow with model selector (no MAC address)
- Evidence: `devices/new.tsx:17-38` passes through config for duplicate flow but no model selection

### Device Edit Route

- Area: `src/routes/devices/$deviceId.tsx`
- Why: Update to display key and model as read-only; add provisioning download button
- Evidence: `$deviceId.tsx:10-56` uses `useDevice` hook and renders `DeviceEditor` with MAC address

### Device Models List Route (New)

- Area: `src/routes/device-models/index.tsx` (new file)
- Why: Create list page for device models with CRUD actions
- Evidence: OpenAPI `GET /api/device-models` returns `DeviceModelListResponseSchema` with model summaries

### Device Models Create Route (New)

- Area: `src/routes/device-models/new.tsx` (new file)
- Why: Create form for new device models with JSON Schema editor
- Evidence: OpenAPI `POST /api/device-models` accepts `code`, `name`, `config_schema`

### Device Models Edit Route (New)

- Area: `src/routes/device-models/$modelId.tsx` (new file)
- Why: Edit form for device models (name, config_schema editable; code read-only)
- Evidence: OpenAPI `PUT /api/device-models/{model_id}` accepts `name`, `config_schema`

### Device Model Editor Component (New)

- Area: `src/components/device-models/device-model-editor.tsx` (new file)
- Why: Shared form component for create/edit with JSON Schema meta-validation
- Evidence: Pattern from existing `device-editor.tsx` with Monaco editor

### Device Model List Table (New)

- Area: `src/components/device-models/device-model-list-table.tsx` (new file)
- Why: Table component for device models list display
- Evidence: Pattern from existing `device-list-table.tsx`

### Rotation Dashboard Route (New)

- Area: `src/routes/rotation/index.tsx` (new file)
- Why: Create rotation dashboard page with health groupings
- Evidence: OpenAPI `GET /api/rotation/dashboard` returns devices grouped by healthy/warning/critical

### Rotation Dashboard Component (New)

- Area: `src/components/rotation/rotation-dashboard.tsx` (new file)
- Why: Dashboard UI with counts, device lists, and trigger button
- Evidence: OpenAPI `DashboardResponseSchema` includes `counts`, `healthy`, `warning`, `critical` arrays

### Rotation State Badge Component (New)

- Area: `src/components/devices/rotation-state-badge.tsx` (new file)
- Why: Reusable badge for rotation state display (OK/QUEUED/PENDING/TIMEOUT)
- Evidence: Requirements specify color coding: OK (green), QUEUED (yellow), PENDING (blue+spinner), TIMEOUT (red)

### Form Instrumentation Hook (New)

- Area: `src/lib/test/form-instrumentation.ts` (new file)
- Why: Create `useFormInstrumentation` hook to emit form lifecycle events for Playwright; `FormTestEvent` interface exists in `test-events.ts` but no emission helpers exist
- Evidence: `src/types/test-events.ts:44-55` defines interface; device/device-model forms need deterministic test assertions

### Monaco Schema Validation Utility (New)

- Area: `src/lib/utils/monaco-schema.ts` (new file)
- Why: Configure Monaco JSON Schema validation using URI-based schema association (not global defaults) to prevent interference between multiple editors
- Evidence: Brief notes "Monaco Editor supports JSON Schema validation"; must avoid global state pollution when switching models or having multiple editors

### Test Factory - Devices (Update)

- Area: `tests/api/factories/devices.ts`
- Why: Update to use new `/api/devices` endpoints with `device_model_id` and remove MAC address
- Evidence: `devices.ts:56-62` calls `POST /api/configs` which no longer exists

### Test Factory - Device Models (New)

- Area: `tests/api/factories/device-models.ts` (new file)
- Why: Create factory for device model test data
- Evidence: Pattern from existing `devices.ts` factory

### Test Fixtures Update

- Area: `tests/support/fixtures.ts`
- Why: Add `deviceModels` factory fixture
- Evidence: `fixtures.ts:34-41` defines `devices` fixture; add similar for device models

### Playwright Page Object - Device Models (New)

- Area: `tests/e2e/device-models/DeviceModelsPage.ts` (new file)
- Why: Page object for device models E2E tests
- Evidence: Pattern from `tests/e2e/devices/DevicesPage.ts`

### Playwright Page Object - Rotation (New)

- Area: `tests/e2e/rotation/RotationPage.ts` (new file)
- Why: Page object for rotation dashboard E2E tests
- Evidence: Pattern from existing page objects

### Playwright Specs - Devices (Update)

- Area: `tests/e2e/devices/devices-crud.spec.ts`
- Why: Update specs for new device creation flow (model selector, no MAC)
- Evidence: `devices-crud.spec.ts:107-142` tests create with MAC address; needs model selector

### Playwright Specs - Device Models (New)

- Area: `tests/e2e/device-models/device-models.spec.ts` (new file)
- Why: E2E tests for device models CRUD
- Evidence: Requirements checklist includes device models CRUD specs

### Playwright Specs - Rotation (New)

- Area: `tests/e2e/rotation/rotation.spec.ts` (new file)
- Why: E2E tests for rotation dashboard
- Evidence: Requirements checklist includes rotation dashboard specs

---

## 3) Data Model / Contracts

### Device Model Summary (List)

- Entity / contract: `DeviceModelListResponseSchema.DeviceModelSummarySchema`
- Shape:
  ```typescript
  interface DeviceModelSummary {
    id: number
    code: string          // e.g., "thermostat"
    name: string          // e.g., "Smart Thermostat"
    hasConfigSchema: boolean
    deviceCount: number
    firmwareVersion: string | null
  }
  ```
- Mapping: `has_config_schema` -> `hasConfigSchema`, `device_count` -> `deviceCount`, `firmware_version` -> `firmwareVersion`
- Evidence: OpenAPI schema lines 391-442

### Device Model Detail

- Entity / contract: `DeviceModelResponseSchema`
- Shape:
  ```typescript
  interface DeviceModel {
    id: number
    code: string
    name: string
    hasConfigSchema: boolean
    configSchema: Record<string, unknown> | null  // Parsed JSON Schema
    deviceCount: number
    firmwareVersion: string | null
    createdAt: string
    updatedAt: string
  }
  ```
- Mapping: `config_schema` -> `configSchema` (already parsed object from API)
- Evidence: OpenAPI schema lines 443-522

### Device Summary (List)

- Entity / contract: `DeviceListResponseSchema.DeviceSummarySchema`
- Shape:
  ```typescript
  interface DeviceSummary {
    id: number
    key: string              // 8-char auto-generated
    deviceModelId: number
    deviceName: string | null
    deviceEntityId: string | null
    enableOta: boolean | null
    rotationState: string    // OK | QUEUED | PENDING | TIMEOUT
    secretCreatedAt: string | null
  }
  ```
- Mapping: `device_model_id` -> `deviceModelId`, `device_name` -> `deviceName`, `device_entity_id` -> `deviceEntityId`, `enable_ota` -> `enableOta`, `rotation_state` -> `rotationState`, `secret_created_at` -> `secretCreatedAt`
- Evidence: OpenAPI schema lines 209-294

### Device Detail

- Entity / contract: `DeviceResponseSchema`
- Shape:
  ```typescript
  interface Device {
    id: number
    key: string
    deviceModelId: number
    deviceModel: {
      id: number
      code: string
      name: string
      firmwareVersion: string | null
    }
    config: Record<string, unknown>
    deviceName: string | null
    deviceEntityId: string | null
    enableOta: boolean | null
    rotationState: string
    clientId: string
    secretCreatedAt: string | null
    lastRotationAttemptAt: string | null
    lastRotationCompletedAt: string | null
    createdAt: string
    updatedAt: string
  }
  ```
- Mapping: Nested `device_model` object with embedded model info including config_schema for validation
- Evidence: OpenAPI schema lines 558-743

### Dashboard Device

- Entity / contract: `DashboardResponseSchema.DashboardDeviceSchema`
- Shape:
  ```typescript
  interface DashboardDevice {
    id: number
    key: string
    deviceModelCode: string
    deviceName: string | null
    rotationState: string
    lastRotationCompletedAt: string | null
    daysSinceRotation: number | null
  }
  ```
- Mapping: `device_model_code` -> `deviceModelCode`, `days_since_rotation` -> `daysSinceRotation`, `last_rotation_completed_at` -> `lastRotationCompletedAt`
- Evidence: OpenAPI schema lines 92-164

### Rotation Status

- Entity / contract: `RotationStatusSchema`
- Shape:
  ```typescript
  interface RotationStatus {
    countsByState: Record<string, number>  // { OK: 10, QUEUED: 2, PENDING: 1, TIMEOUT: 0 }
    pendingDeviceId: number | null
    lastRotationCompletedAt: string | null
    nextScheduledRotation: string | null
  }
  ```
- Mapping: `counts_by_state` -> `countsByState`, `pending_device_id` -> `pendingDeviceId`, `last_rotation_completed_at` -> `lastRotationCompletedAt`, `next_scheduled_rotation` -> `nextScheduledRotation`
- Evidence: OpenAPI schema lines 920-985

---

## 4) API / Integration Surface

### List Device Models

- Surface: `GET /api/device-models` -> `useGetDeviceModels()`
- Inputs: None
- Outputs: `{ device_models: DeviceModelSummary[], count: number }`; cache key `['getDeviceModels']`
- Errors: Global error handler via toast
- Evidence: OpenAPI lines 1320-1349

### Create Device Model

- Surface: `POST /api/device-models` -> `usePostDeviceModels()`
- Inputs: `{ code: string, name: string, config_schema?: string }`
- Outputs: `DeviceModelResponseSchema`; invalidates `['getDeviceModels']`
- Errors: 400 (validation), 409 (duplicate code) - show toast
- Evidence: OpenAPI lines 1350-1398

### Get Device Model

- Surface: `GET /api/device-models/{model_id}` -> `useGetDeviceModelsByModelId()`
- Inputs: `{ path: { model_id: number } }`
- Outputs: `DeviceModelResponseSchema` with parsed `config_schema`
- Errors: 404 (not found) - show error state
- Evidence: OpenAPI lines 1454-1503

### Update Device Model

- Surface: `PUT /api/device-models/{model_id}` -> `usePutDeviceModelsByModelId()`
- Inputs: `{ path: { model_id }, body: { name?: string, config_schema?: string } }`
- Outputs: `DeviceModelResponseSchema`; invalidates `['getDeviceModels']`, `['getDeviceModelsByModelId', model_id]`
- Errors: 400 (validation), 404 (not found) - show toast
- Evidence: OpenAPI lines 1504-1563

### Delete Device Model

- Surface: `DELETE /api/device-models/{model_id}` -> `useDeleteDeviceModelsByModelId()`
- Inputs: `{ path: { model_id: number } }`
- Outputs: 204 No Content; invalidates `['getDeviceModels']`
- Errors: 404 (not found), 409 (has devices) - show toast with error message
- Evidence: OpenAPI lines 1401-1453

### List Devices

- Surface: `GET /api/devices` -> `useGetDevices()`
- Inputs: None
- Outputs: `{ devices: DeviceSummary[], count: number }`; cache key `['getDevices']`
- Errors: Global error handler
- Evidence: OpenAPI lines 1636-1665

### Create Device

- Surface: `POST /api/devices` -> `usePostDevices()`
- Inputs: `{ device_model_id: number, config: string }`
- Outputs: `DeviceResponseSchema` with auto-generated `key`; invalidates `['getDevices']`
- Errors: 400 (validation), 404 (model not found), 502 (Keycloak error) - show toast
- Evidence: OpenAPI lines 1666-1724

### Get Device

- Surface: `GET /api/devices/{device_id}` -> `useGetDevicesByDeviceId()`
- Inputs: `{ path: { device_id: number } }`
- Outputs: `DeviceResponseSchema` with embedded `device_model` including `config_schema`
- Errors: 404 (not found) - show error state
- Evidence: OpenAPI lines 1780-1829

### Update Device

- Surface: `PUT /api/devices/{device_id}` -> `usePutDevicesByDeviceId()`
- Inputs: `{ path: { device_id }, body: { config: string } }`
- Outputs: `DeviceResponseSchema`; invalidates `['getDevices']`, `['getDevicesByDeviceId', device_id]`
- Errors: 400 (validation), 404 (not found) - show toast
- Evidence: OpenAPI lines 1830-1889

### Delete Device

- Surface: `DELETE /api/devices/{device_id}` -> `useDeleteDevicesByDeviceId()`
- Inputs: `{ path: { device_id: number } }`
- Outputs: 204 No Content; invalidates `['getDevices']`
- Errors: 404 (not found), 502 (Keycloak error) - show toast
- Evidence: OpenAPI lines 1727-1778

### Download Provisioning

- Surface: `GET /api/devices/{device_id}/provisioning`
- Inputs: `{ path: { device_id: number } }`
- Outputs: Binary `.bin` file download (no hook needed, direct fetch with download trigger)
- Errors: 404 (not found) - show toast
- Evidence: OpenAPI lines 1891-1911

### Trigger Device Rotation

- Surface: `POST /api/devices/{device_id}/rotate` -> `usePostDevicesRotateByDeviceId()`
- Inputs: `{ path: { device_id: number } }`
- Outputs: `{ status: 'queued' | 'already_pending' }`; invalidates dashboard/status queries
- Errors: 404 (not found) - show toast
- Evidence: OpenAPI lines 1912-1962

### Get Rotation Dashboard

- Surface: `GET /api/rotation/dashboard` -> `useGetRotationDashboard()`
- Inputs: None
- Outputs: `{ healthy: DashboardDevice[], warning: DashboardDevice[], critical: DashboardDevice[], counts: Record<string, number> }`
- Errors: Global error handler
- Evidence: OpenAPI lines 2104-2133

### Get Rotation Status

- Surface: `GET /api/rotation/status` -> `useGetRotationStatus()`
- Inputs: None
- Outputs: `RotationStatusSchema`
- Errors: Global error handler
- Evidence: OpenAPI lines 2135-2164

### Trigger Fleet Rotation

- Surface: `POST /api/rotation/trigger` -> `usePostRotationTrigger()`
- Inputs: None
- Outputs: `{ queued_count: number }`; invalidates `['getRotationDashboard']`, `['getRotationStatus']`
- Errors: 500 (internal error) - show toast
- Evidence: OpenAPI lines 2166-2205

---

## 5) Algorithms & UI Flows

### Device Creation Flow

- Flow: User creates new device with model selection
- Steps:
  1. User navigates to `/devices/new`
  2. Component fetches device models list via `useDeviceModels()`
  3. User selects model from dropdown
  4. If model has `configSchema`, Monaco editor loads schema for validation/autocomplete
  5. User edits JSON config
  6. On save, form validates JSON against schema (if present)
  7. `useCreateDevice()` mutation called with `{ device_model_id, config }`
  8. On success, invalidate queries and navigate to `/devices`
  9. List shows new device with auto-generated `key`
- States / transitions: `idle` -> `selecting_model` -> `editing_config` -> `submitting` -> `success|error`
- Hotspots: Model selection triggers schema loading; schema validation on every keystroke may need debouncing
- Evidence: `device-editor.tsx:104-153` shows existing save flow pattern

### Device Model Creation Flow

- Flow: User creates new device model with optional JSON Schema
- Steps:
  1. User navigates to `/device-models/new`
  2. User enters `code` (validated against pattern `[a-z0-9_]+`)
  3. User enters `name`
  4. Optionally, user enters `config_schema` in Monaco editor
  5. If schema entered, validate against JSON Schema meta-schema (draft-07)
  6. On save, `useCreateDeviceModel()` mutation called
  7. On success, navigate to `/device-models`
- States / transitions: `idle` -> `editing` -> `validating_schema` -> `submitting` -> `success|error`
- Hotspots: Meta-schema validation of user's JSON Schema
- Evidence: Pattern from `device-editor.tsx` Monaco integration

### Rotation Dashboard View Flow

- Flow: User views rotation health and can trigger fleet rotation
- Steps:
  1. User navigates to `/rotation`
  2. Component fetches dashboard via `useRotationDashboard()` and status via `useRotationStatus()`
  3. Display counts with colored badges (healthy=green, warning=orange, critical=red)
  4. Display device lists grouped by health category
  5. If `pendingDeviceId` is set, show link to that device
  6. User clicks "Trigger Rotation" button
  7. Confirmation dialog appears
  8. On confirm, `useTriggerRotation()` mutation called
  9. Dashboard auto-refreshes via query invalidation
- States / transitions: `loading` -> `ready` -> `confirming_trigger` -> `triggering` -> `ready`
- Hotspots: Potential need for polling/refetch interval for real-time status updates
- Evidence: `DashboardResponseSchema` structure in OpenAPI spec

### Provisioning Download Flow

- Flow: User downloads provisioning package from device edit view
- Steps:
  1. User opens device edit page at `/devices/{id}`
  2. Download button visible in toolbar
  3. User clicks "Download Provisioning"
  4. Frontend fetches `/api/devices/{id}/provisioning` with appropriate headers
  5. Response triggers browser download of `{key}.bin` file
- States / transitions: Button click -> `downloading` -> `complete|error`
- Hotspots: Binary file handling, filename extraction from response headers
- Evidence: OpenAPI endpoint at lines 1891-1911

---

## 6) Derived State & Invariants

### Can Delete Device Model

- Derived value: `canDeleteModel`
  - Source: `deviceModel.deviceCount` from `useDeviceModel()`
  - Writes / cleanup: Enables/disables delete button
  - Guards: `deviceCount === 0` allows delete
  - Invariant: Delete button must remain disabled while `deviceCount > 0`
  - Evidence: Requirement "Delete button disabled when device_count > 0"

### Device Config Schema

- Derived value: `configSchema` for Monaco validation
  - Source: `device.deviceModel.configSchema` from `useDevice()` or selected model from dropdown
  - Writes / cleanup: Registers schema with unique URI on mount; removes schema association on unmount via `useEffect` cleanup
  - Guards: Only apply schema validation when schema is non-null; must use URI-based association (not global defaults) to avoid interference
  - Invariant: Schema must be re-applied when model selection changes (create) or page loads (edit); stale schemas cause incorrect validation
  - Evidence: Requirement "Device config JSON editor should use model's config_schema for validation"

### Model Name Map for Device List

- Derived value: `modelNameMap` (for device list display)
  - Source: Full device models list from `useDeviceModels()`, keyed by ID
  - Writes / cleanup: Used only for display lookup, no writes
  - Guards: Must handle case where model is deleted but device still references it (show ID or "Unknown")
  - Invariant: Map must be refreshed when device models are created/deleted to avoid stale lookups
  - Evidence: Device list requirement to show "model name" but API only returns `device_model_id`

**Note**: Device list component queries both `['getDevices']` and `['getDeviceModels']`; model name lookup uses a memoized map keyed by model ID.

### Rotation Health Category

- Derived value: `healthCategory` (healthy/warning/critical)
  - Source: Pre-computed by backend in dashboard response
  - Writes / cleanup: Determines which list section device appears in
  - Guards: Category assignment is server-side; UI only displays
  - Invariant: Device must appear in exactly one category
  - Evidence: OpenAPI `DashboardResponseSchema` groups by `healthy`, `warning`, `critical`

### Form Dirty State

- Derived value: `isDirty`
  - Source: Compare current form values (model selection, config JSON) against initial values
  - Writes / cleanup: Enables unsaved changes warning dialog
  - Guards: Navigation blocker only active when `isDirty === true`
  - Invariant: Dirty state must reset after successful save
  - Evidence: `device-editor.tsx:51-59` existing dirty state computation

---

## 7) State Consistency & Async Coordination

### Device List Query Cache

- Source of truth: TanStack Query cache key `['getDevices']`
- Coordination: Device mutations invalidate this cache; list component re-renders with fresh data
- Async safeguards: React Query handles stale data; no manual abort needed for list queries
- Instrumentation: `useListLoadingInstrumentation({ scope: 'devices.list', ... })` emits loading/ready events
- Evidence: `devices/index.tsx:24-30` existing instrumentation pattern

### Device Model List Query Cache

- Source of truth: TanStack Query cache key `['getDeviceModels']`
- Coordination: Model mutations invalidate; model selector dropdown in device form uses this cache
- Async safeguards: Dependent query for device creation enabled when models loaded
- Instrumentation: `useListLoadingInstrumentation({ scope: 'deviceModels.list', ... })`
- Evidence: Pattern from devices list

### Rotation Dashboard Cache

- Source of truth: TanStack Query cache keys `['getRotationDashboard']`, `['getRotationStatus']`
- Coordination: Fleet rotation trigger invalidates both; status may need periodic refetch
- Async safeguards: Consider `refetchInterval` for status to show real-time rotation progress
- Instrumentation: `useListLoadingInstrumentation({ scope: 'rotation.dashboard', ... })`
- Evidence: Pattern from existing list components

### Monaco Schema Configuration

- Source of truth: Monaco URI-based schema associations via `jsonDefaults.setDiagnosticsOptions({ schemas: [...] })`
- Coordination: Each editor uses unique model URI (e.g., `schema://device-config/${deviceModelId}`); schemas registered on mount, cleaned up on unmount
- Async safeguards: Await model fetch before configuring Monaco; cleanup in `useEffect` return to remove schema associations on unmount/model change
- Instrumentation: N/A (Monaco is external library)
- Evidence: URI-based approach avoids global state pollution when multiple editors open or navigating between devices with different models

**Important**: Do NOT use global `jsonDefaults` configuration. Instead, associate schemas with specific URIs:
```typescript
monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
  schemas: [{
    uri: `schema://device-config/${deviceModelId}`,
    fileMatch: [`device-config-${deviceModelId}.json`],
    schema: configSchema
  }]
});
// Set editor model URI to match fileMatch pattern
```

---

## 8) Errors & Edge Cases

### Device Model Has Devices - Cannot Delete

- Failure: User tries to delete model with `device_count > 0`
- Surface: Device models list page delete button
- Handling: Button disabled when `deviceCount > 0`; tooltip explains why
- Guardrails: Backend returns 409 if attempted via API directly
- Evidence: Requirement "Delete button disabled when device_count > 0"

### Invalid JSON Schema in Model Editor

- Failure: User enters invalid JSON Schema syntax
- Surface: Device model create/edit form
- Handling: Monaco shows red squiggles; save button disabled; inline error message
- Guardrails: Client-side meta-schema validation before submission
- Evidence: Requirement "Config schema editor must validate that the schema is a valid JSON Schema"

### Config Does Not Match Model Schema

- Failure: Device config fails JSON Schema validation
- Surface: Device create/edit form
- Handling: Monaco shows validation errors; save button remains enabled but submission may fail
- Guardrails: Client-side validation pre-submit; backend validates and returns 400
- Evidence: OpenAPI 400 error response on device endpoints

### Device Model Not Found

- Failure: Navigate to `/device-models/{id}` for deleted model
- Surface: Device model edit page
- Handling: Show error state with "Back to Device Models" link
- Guardrails: Query returns 404; component renders error UI
- Evidence: Pattern from `$deviceId.tsx:34-43`

### Provisioning Download Fails

- Failure: Backend error fetching provisioning package
- Surface: Device edit page download button
- Handling: Show error toast; log correlation ID
- Guardrails: Try/catch around fetch; use global error handler
- Evidence: Standard error handling pattern

### Fleet Rotation Already In Progress

- Failure: User triggers rotation while device is PENDING
- Surface: Rotation dashboard trigger button
- Handling: Show info toast "Rotation already in progress"
- Guardrails: Backend handles gracefully (queues additional devices)
- Evidence: OpenAPI trigger response may indicate partial queueing

---

## 9) Observability / Instrumentation

### Device Models List Loading

- Signal: `list_loading` event with `scope: 'deviceModels.list'`
- Type: Instrumentation event
- Trigger: On mount and query fetch in device models list page
- Labels / fields: `phase: 'loading' | 'ready' | 'error'`, `metadata: { visible, total }`
- Consumer: Playwright `waitForListLoading(page, 'deviceModels.list', 'ready')`
- Evidence: `devices/index.tsx:24-30` pattern

### Devices List Loading

- Signal: `list_loading` event with `scope: 'devices.list'`
- Type: Instrumentation event
- Trigger: On mount and query fetch in devices list page
- Labels / fields: `phase: 'loading' | 'ready' | 'error'`, `metadata: { visible, total }`
- Consumer: Playwright `waitForListLoading(page, 'devices.list', 'ready')`
- Evidence: Existing instrumentation at `devices/index.tsx:24-30`

### Rotation Dashboard Loading

- Signal: `list_loading` event with `scope: 'rotation.dashboard'`
- Type: Instrumentation event
- Trigger: On mount and query fetch in rotation dashboard
- Labels / fields: `phase: 'loading' | 'ready' | 'error'`, `metadata: { healthy, warning, critical }`
- Consumer: Playwright `waitForListLoading(page, 'rotation.dashboard', 'ready')`
- Evidence: Pattern from devices list

### Device Model Form Events

- Signal: `form` event with `formId: 'DeviceModelForm_create' | 'DeviceModelForm_edit'`
- Type: Instrumentation event
- Trigger: Form open, submit, success, error
- Labels / fields: `phase: 'open' | 'submit' | 'success' | 'error'`
- Consumer: Playwright `waitTestEvent(page, 'form', e => e.formId === 'DeviceModelForm_create')`
- Evidence: `test-events.ts:44-55` defines interface; `useFormInstrumentation` hook to be created in Slice 1

**Implementation**: Create `useFormInstrumentation` hook in `src/lib/test/form-instrumentation.ts`:
```typescript
useFormInstrumentation({
  formId: mode === 'edit' ? 'DeviceModelForm_edit' : 'DeviceModelForm_create',
  isPending: createModel.isPending || updateModel.isPending,
  isSuccess: createModel.isSuccess || updateModel.isSuccess,
  isError: createModel.isError || updateModel.isError,
});
```

### Device Form Events

- Signal: `form` event with `formId: 'DeviceForm_create' | 'DeviceForm_edit'`
- Type: Instrumentation event
- Trigger: Form open, submit, success, error
- Labels / fields: `phase: 'open' | 'submit' | 'success' | 'error'`, `metadata: { modelId }`
- Consumer: Playwright form event helpers
- Evidence: `test-events.ts:44-55` defines interface; `useFormInstrumentation` hook to emit events

### Data Test IDs

New test IDs to add:
- `device-models.list.table`, `device-models.list.row`, `device-models.list.header.new`
- `device-models.editor`, `device-models.editor.code`, `device-models.editor.name`, `device-models.editor.schema-editor`
- `devices.editor.model-selector`, `devices.editor.download-provisioning`
- `devices.list.row.rotation-badge`
- `rotation.dashboard`, `rotation.dashboard.counts`, `rotation.dashboard.healthy`, `rotation.dashboard.warning`, `rotation.dashboard.critical`
- `rotation.dashboard.trigger-button`, `rotation.dashboard.pending-link`

---

## 10) Lifecycle & Background Work

### Rotation Status Polling

- Hook / effect: `useRotationStatus()` with `refetchInterval`
- Trigger cadence: Every 30 seconds while dashboard is mounted and rotation is active
- Responsibilities: Refresh rotation status to show progress of active rotation
- Cleanup: `refetchInterval` disabled when no PENDING devices; unmount cleans up interval
- Evidence: TanStack Query `refetchInterval` option; needed for real-time UX

### Monaco Editor Schema Configuration

- Hook / effect: `useEffect` to configure Monaco when model/schema changes
- Trigger cadence: On model selection change (create) or on device load (edit)
- Responsibilities: Call `monaco.languages.json.jsonDefaults.setDiagnosticsOptions()` with schema
- Cleanup: Reset to default schema options on unmount or model change
- Evidence: Change brief mentions Monaco schema validation

### Provisioning Download

- Hook / effect: Event handler (not an effect)
- Trigger cadence: On user click
- Responsibilities: Fetch binary, create blob URL, trigger download, revoke URL
- Cleanup: `URL.revokeObjectURL()` after download triggered
- Evidence: Standard browser download pattern

---

## 11) Security & Permissions

- Concern: Authorization for device/model management and rotation triggers
- Touchpoints: All API endpoints require authentication (existing auth gate)
- Mitigation: Existing `AuthGate` component wraps app; backend validates JWT on all requests
- Residual risk: No role-based access control specified; all authenticated users can manage devices
- Evidence: `auth-gate.tsx` component; backend auth middleware

---

## 12) UX / UI Impact

### Navigation Updates

- Entry point: Sidebar navigation
- Change: Add "Device Models" and "Rotation" items; rename "Device Configs" to "Devices"
- User interaction: User sees three navigation items instead of one
- Dependencies: Sidebar component, route definitions
- Evidence: `sidebar.tsx:23-25` navigationItems array

### Device List New Columns

- Entry point: `/devices` route
- Change: Replace MAC column with Key; add Model Name and Rotation State columns
- User interaction: User sees device key (8 chars), model name, and rotation status badge
- Dependencies: Updated hooks, new badge component
- Evidence: `device-list-table.tsx` column definitions

### Device Create Form Updates

- Entry point: `/devices/new` route
- Change: Remove MAC input; add model selector dropdown with schema-based config validation
- User interaction: User selects model first, then sees schema-aware JSON editor
- Dependencies: Device model hooks, Monaco schema configuration
- Evidence: `device-editor.tsx` form layout

### Device Edit Form Updates

- Entry point: `/devices/{id}` route
- Change: Show Key and Model as read-only; add provisioning download button
- User interaction: User can download `.bin` file for device provisioning
- Dependencies: Provisioning API endpoint
- Evidence: `device-editor.tsx` toolbar

### Rotation Dashboard

- Entry point: `/rotation` route (new)
- Change: New page showing fleet health status with device lists
- User interaction: User sees counts, device lists by health category, can trigger rotation
- Dependencies: Rotation hooks, dashboard components
- Evidence: Requirements in change brief

---

## 13) Deterministic Test Plan

### Device Models CRUD Spec

- Surface: `/device-models` pages
- Scenarios:
  - Given no models exist, When user views list, Then empty state shown
  - Given user creates model with code "sensor_v1", When save clicked, Then model appears in list
  - Given model exists with code "sensor_v1", When user edits name, Then list shows updated name
  - Given model exists with device_count=0, When user clicks delete, Then model removed from list
  - Given model exists with device_count>0, When user views list, Then delete button is disabled
  - Given user enters invalid JSON Schema, When editing config_schema, Then save button disabled and error shown
- Instrumentation / hooks: `deviceModels.list` loading events, `DeviceModelForm_*` form events, `data-testid` selectors
- Gaps: None
- Evidence: Pattern from `devices-crud.spec.ts`

### Devices CRUD Spec (Updated)

- Surface: `/devices` pages
- Scenarios:
  - Given device models exist, When user creates device selecting model, Then device appears with auto-generated key
  - Given device exists, When user edits config, Then changes saved
  - Given device exists, When user clicks download provisioning, Then .bin file downloads
  - Given device with model that has config_schema, When user edits config, Then Monaco shows validation
  - Given device list displays, When viewing row, Then rotation state badge shows correct color
- Instrumentation / hooks: `devices.list` loading events, `DeviceForm_*` form events, model selector `data-testid`
- Gaps: None
- Evidence: Existing `devices-crud.spec.ts` needs updating for model selector flow

### Rotation Dashboard Spec

- Surface: `/rotation` page
- Scenarios:
  - Given devices exist in various states, When user views dashboard, Then counts shown correctly
  - Given devices in warning state, When viewing list, Then warning section shows those devices
  - Given no pending rotation, When user clicks trigger, Then devices queued and count shown
  - Given device is pending, When viewing dashboard, Then link to pending device shown
- Instrumentation / hooks: `rotation.dashboard` loading events, trigger button `data-testid`
- Gaps: Testing actual rotation completion requires backend time manipulation (may be deferred)
- Evidence: Pattern from device list specs

### Test Factory Updates

- Surface: `tests/api/factories/devices.ts`
- Scenarios:
  - Factory creates device via POST /api/devices with device_model_id
  - Factory accepts model override, creates model first if not provided
  - Factory exposes helper methods: `randomDeviceName()`, `findByKey()`
- Instrumentation / hooks: N/A (factory is test infrastructure)
- Gaps: None
- Evidence: Existing factory pattern at `devices.ts`

### Device Model Factory

- Surface: `tests/api/factories/device-models.ts` (new)
- Scenarios:
  - Factory creates device model via POST /api/device-models
  - Factory supports optional config_schema parameter
  - Factory exposes helper: `randomModelCode()`, `randomModelName()`
- Instrumentation / hooks: N/A
- Gaps: None
- Evidence: Pattern from `devices.ts` factory

---

## 14) Implementation Slices

### Slice 0: Test Infrastructure Migration (FIRST)

- Slice: Fix broken test factories before any UI work
- Goal: Restore green CI baseline so tests can run during development
- Touches:
  - `tests/api/factories/devices.ts` - update to use `/api/devices` endpoints with `device_model_id`
  - `tests/api/factories/device-models.ts` (new) - factory for device model test data
  - `tests/support/fixtures.ts` - add `deviceModels` fixture
- Dependencies: None (first slice)
- Verification: Run `pnpm playwright test tests/e2e/devices/` to confirm existing tests pass with updated factory

### Slice 1: API Regeneration & Hook Foundation

- Slice: API client regeneration, custom hooks, and form instrumentation
- Goal: Establish working API layer and test infrastructure before UI changes
- Touches:
  - Run `pnpm generate:api`
  - Create `src/lib/test/form-instrumentation.ts` - `useFormInstrumentation` hook for form lifecycle events
  - Create `src/hooks/use-device-models.ts`
  - Create `src/hooks/use-rotation.ts`
  - Update `src/hooks/use-devices.ts` to use new endpoints
- Dependencies: Slice 0 (test factory working)

### Slice 2: Navigation & Routing

- Slice: Navigation updates and new route files
- Goal: Establish navigation structure and empty route placeholders
- Touches:
  - `src/components/layout/sidebar.tsx`
  - Create `src/routes/device-models/index.tsx` (placeholder)
  - Create `src/routes/device-models/new.tsx` (placeholder)
  - Create `src/routes/device-models/$modelId.tsx` (placeholder)
  - Create `src/routes/rotation/index.tsx` (placeholder)
- Dependencies: Slice 1 (hooks available)

### Slice 3: Device Models UI

- Slice: Complete device models management
- Goal: Ship device models CRUD functionality
- Touches:
  - `src/components/device-models/device-model-editor.tsx` (with `useFormInstrumentation`)
  - `src/components/device-models/device-model-list-table.tsx`
  - `src/lib/utils/monaco-schema.ts` (URI-based meta-schema validation)
  - Complete route implementations
  - Add list loading instrumentation
- Dependencies: Slice 2 (routes exist)

### Slice 4: Devices UI Update

- Slice: Update devices pages for new data model
- Goal: Ship updated device management with model selector
- Touches:
  - `src/components/devices/device-editor.tsx` (major update, add `useFormInstrumentation`)
  - `src/components/devices/device-list-table.tsx` (add model name via client-side join)
  - `src/components/devices/rotation-state-badge.tsx`
  - `src/routes/devices/index.tsx`, `new.tsx`, `$deviceId.tsx`
  - Monaco URI-based schema validation for config
- Dependencies: Slice 3 (device models available for selector)

### Slice 5: Rotation Dashboard

- Slice: New rotation dashboard page
- Goal: Ship rotation monitoring and fleet trigger
- Touches:
  - `src/routes/rotation/index.tsx`
  - `src/components/rotation/rotation-dashboard.tsx`
  - Add refetch interval for status when rotation active
  - Add list loading instrumentation
- Dependencies: Slice 4 (devices with rotation states visible)

### Slice 6: Playwright Specs

- Slice: Add and update Playwright E2E tests
- Goal: Ship automated test coverage for all new flows
- Touches:
  - `tests/e2e/device-models/DeviceModelsPage.ts` (page object)
  - `tests/e2e/device-models/device-models.spec.ts` (CRUD specs)
  - `tests/e2e/devices/devices-crud.spec.ts` (update for model selector)
  - `tests/e2e/rotation/RotationPage.ts` (page object)
  - `tests/e2e/rotation/rotation.spec.ts` (dashboard specs)
- Dependencies: Slices 3-5 (UI complete)

---

## 15) Risks & Open Questions

### Risk: Monaco Schema Validation Complexity

- Risk: JSON Schema meta-validation for config_schema editor may be complex to set up correctly
- Impact: Users may be able to save invalid schemas, causing downstream validation failures
- Mitigation: Use official JSON Schema draft-07 meta-schema; use URI-based schema association to avoid global state pollution; test with edge cases; add backend validation as backstop

### Risk: Monaco Global State Pollution

- Risk: Multiple Monaco editors or navigation between devices could cause schema interference
- Impact: Wrong schema applied, showing incorrect validation errors
- Mitigation: Use URI-based schema association (not global `jsonDefaults`); clean up schema associations in `useEffect` return; each editor uses unique model URI

### Risk: Breaking Change for Existing Users

- Risk: Frontend completely changes device identification from MAC to key
- Impact: Users familiar with MAC-based workflow need to adapt
- Mitigation: Clear UI labeling; key is auto-generated and displayed prominently

### Risk: Test Factory Migration (MITIGATED)

- Risk: Existing test factory is broken; migration may introduce test flakiness
- Impact: CI failures, blocked development
- Mitigation: **Moved to Slice 0** - Update factory first before any UI work; run full device test suite to confirm green baseline before proceeding

### Risk: Rotation Dashboard Polling Performance

- Risk: Frequent polling for rotation status may impact performance
- Impact: Unnecessary API calls, potential rate limiting
- Mitigation: Only poll when rotation is active (PENDING/QUEUED devices exist); use reasonable interval (30s)

### Open Question: Provisioning File Naming

- Question: Should provisioning download use `{key}.bin` or `provisioning-{key}.bin`?
- Why it matters: Affects user experience and device flashing workflows
- Owner / follow-up: Check backend Content-Disposition header; align with IoT team conventions

### Open Question: Rotation Trigger Confirmation

- Question: Should fleet-wide rotation require additional confirmation beyond dialog?
- Why it matters: Accidental fleet rotation could disrupt all devices
- Owner / follow-up: Product decision; current plan includes confirmation dialog

---

## 16) Confidence

Confidence: High - The requirements are clearly specified in the change brief, the backend API is already deployed and documented in OpenAPI, and the frontend patterns for CRUD pages, hooks, and testing are well-established in the codebase. Plan review conditions have been addressed:
- Form instrumentation hook added to Slice 1 before form components
- Monaco schema validation uses URI-based association to avoid global state pollution
- Test factory migration moved to Slice 0 to establish green CI baseline first
- Device list model name display clarified with client-side join strategy
