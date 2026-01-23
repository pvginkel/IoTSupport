# NVS Provisioning - Technical Plan

## 0) Research Log & Findings

**Searched areas:**
- `src/components/devices/device-editor.tsx` - Current "Download Provisioning" button implementation (lines 353-365)
- `src/hooks/use-devices.ts` - `downloadDeviceProvisioning` function (lines 267-291)
- `src/lib/api/generated/` - Generated API types for provisioning endpoint
- `src/lib/test/` - Instrumentation patterns (`form-instrumentation.ts`, `event-emitter.ts`)
- `src/types/test-events.ts` - Event taxonomy and payload types
- `src/components/ui/dialog.tsx` - Modal patterns using Radix UI
- `tests/e2e/devices/` - Existing Playwright test patterns
- `tests/api/factories/devices.ts` - Device factory for test data

**Relevant components/hooks:**
- `DeviceEditor` component handles the editor header with action buttons
- `useFormInstrumentation` hook provides form lifecycle event patterns
- `Dialog`, `DialogInnerContent`, `DialogHeader`, `DialogFooter` for modals
- `Button` component with `loading` prop for async states
- Generated `useGetDevicesProvisioningByDeviceId` hook for API calls
- `NvsProvisioningResponseSchema_d48fbce` type with `size` and `data` fields

**Conflicts resolved:**
- The existing `downloadDeviceProvisioning` function in `use-devices.ts` will be replaced, not extended
- New instrumentation event kind `provisioning` must be added to `TestEventKind` enum

---

## 1) Intent & Scope

**User intent**

Replace the current file download provisioning workflow with an in-browser ESP32 flashing experience using Web Serial API and esptool-js. The modal should show progress, handle all error cases gracefully, and emit instrumentation events for Playwright testing.

**Prompt quotes**

- "Replace the current 'Download Provisioning' file download with an in-browser 'Provision Device' flow"
- "flashes NVS credentials directly to an ESP32 device via Web Serial API and esptool-js"
- "Mock ESPLoader class at module level for Playwright tests (exception to no-mock rule)"
- "Show modal with progress bar and current-action label during provisioning"
- "Device remains in bootloader mode after successful flash"

**In scope**

- Remove "Download Provisioning" button and replace with "Provision Device" button
- Move provisioning button to left side of header (separated from form actions)
- Create `ProvisionDeviceModal` component with progress UI
- Create `useProvisioning` hook wrapping device communication logic
- Create `useProvisioningInstrumentation` hook for test events
- Add `esptool-js` dependency for ESP32 communication
- Web Serial API detection and error handling
- Partition table reading and NVS partition discovery
- Backend API integration with partition size parameter
- Flash write and MD5 verification
- Comprehensive error handling for all failure scenarios

**Out of scope**

- Fallback file download for unsupported browsers
- Device type verification
- Flash history tracking
- Multiple device flashing in sequence
- Automatic device reset after flash

**Assumptions / constraints**

- Web Serial API requires HTTPS in production (localhost works for development)
- esptool-js from Espressif provides reliable ESP32 communication primitives
- User must manually reset device after successful flash
- Playwright tests will mock ESPLoader at module level since Web Serial is unavailable in headless browsers
- The backend API now returns JSON with base64 NVS blob (partition_size query param required)

---

## 1a) User Requirements Checklist

**User Requirements Checklist**

- [ ] Replace "Download Provisioning" button with "Provision Device" button in device editor
- [ ] Move button to left side of header, separate from form action buttons (Cancel/Duplicate/Save on right)
- [ ] Check Web Serial API availability and show error if unsupported
- [ ] Connect to ESP32 via Web Serial at 115200 baud with automatic reset attempt
- [ ] Read partition table from 0x8000 and find NVS partition by name "nvs"
- [ ] Cross-check NVS partition subtype is 2; fail if not found or subtype wrong
- [ ] Call backend API with partition size from device's partition table
- [ ] Validate response blob size matches partition size
- [ ] Write NVS blob to partition offset and verify via MD5 checksum
- [ ] Show modal with progress bar and current-action label during provisioning
- [ ] Allow closing modal at any time (user accepts device may be in inconsistent state)
- [ ] Display technical error messages for all error scenarios
- [ ] Device remains in bootloader mode after successful flash; show success message instructing manual reset
- [ ] Create useProvisioningInstrumentation hook with events: ProvisioningStarted, ProvisioningProgress, ProvisioningComplete, ProvisioningError
- [ ] Mock ESPLoader class at module level for Playwright tests (exception to no-mock rule)
- [ ] Use official esptool-js package from Espressif

---

## 2) Affected Areas & File Map

- Area: `src/components/devices/device-editor.tsx`
- Why: Replace "Download Provisioning" button, restructure header layout, add modal trigger
- Evidence: `src/components/devices/device-editor.tsx:353-365` - current Download Provisioning button

- Area: `src/components/devices/provision-device-modal.tsx` (new)
- Why: New modal component managing the multi-step provisioning workflow UI
- Evidence: No existing file; follows pattern from `src/components/ui/dialog.tsx`

- Area: `src/hooks/use-provisioning.ts` (new)
- Why: Hook wrapping esptool-js communication, partition reading, and API calls
- Evidence: Pattern from `src/hooks/use-devices.ts:267-291` for API integration

- Area: `src/lib/test/provisioning-instrumentation.ts` (new)
- Why: Test instrumentation hook for provisioning events
- Evidence: Pattern from `src/lib/test/form-instrumentation.ts:119-176`

- Area: `src/types/test-events.ts`
- Why: Add `provisioning` event kind, `ProvisioningTestEvent` interface, and extend `TestEvent` union type
- Changes required:
  1. Add `PROVISIONING: 'provisioning'` to `TestEventKind` const object (line 19)
  2. Add `ProvisioningTestEvent` interface with `kind: 'provisioning'` literal type
  3. Add `| ProvisioningTestEvent` to the `TestEvent` union type (line 157)
- Evidence: `src/types/test-events.ts:9-19` - TestEventKind enum, `src/types/test-events.ts:148-157` - TestEvent union

- Area: `src/hooks/use-devices.ts`
- Why: Remove deprecated `downloadDeviceProvisioning` function
- Evidence: `src/hooks/use-devices.ts:263-291` - function to remove

- Area: `tests/e2e/devices/DevicesPage.ts`
- Why: Add locators and actions for provisioning modal
- Evidence: `tests/e2e/devices/DevicesPage.ts:62-98` - existing editor locators

- Area: `tests/e2e/devices/devices-provisioning.spec.ts` (new)
- Why: Playwright specs for provisioning workflow
- Evidence: Pattern from `tests/e2e/devices/devices-crud.spec.ts`

- Area: `tests/support/mocks/esptool-mock.ts` (new)
- Why: Module-level mock for ESPLoader class in test environment with configurable failure modes
- Mock injection mechanism: Use Vite's `resolve.alias` in test configuration to replace `esptool-js` with the mock module when `VITE_TEST_MODE=true`
- Configuration API:
  ```typescript
  interface ESPLoaderMockConfig {
    connectionResult: 'success' | 'timeout' | 'error';
    partitionTable: PartitionInfo[] | null;  // null simulates read failure
    flashWriteResult: 'success' | 'error';
    verificationResult: 'match' | 'mismatch';
  }
  export function configureESPLoaderMock(config: Partial<ESPLoaderMockConfig>): void;
  export function resetESPLoaderMock(): void;
  ```
- Evidence: Sanctioned exception documented in change brief

- Area: `package.json`
- Why: Add `esptool-js` dependency
- Evidence: `package.json:21-42` - current dependencies

---

## 3) Data Model / Contracts

- Entity / contract: `NvsProvisioningResponse` (API response)
- Shape:
  ```typescript
  interface NvsProvisioningResponse {
    size: number;   // Partition size in bytes
    data: string;   // Base64-encoded NVS binary blob
  }
  ```
- Mapping: Already snake_case in API; UI model can use camelCase wrapper if needed
- Evidence: `src/lib/api/generated/types.ts:1221-1235`

- Entity / contract: `PartitionInfo` (parsed from device)
- Shape:
  ```typescript
  interface PartitionInfo {
    name: string;       // e.g., "nvs"
    type: number;       // Partition type (1 = data)
    subtype: number;    // Subtype (2 = NVS)
    offset: number;     // Start address in flash
    size: number;       // Partition size in bytes
  }
  ```
- Mapping: Parsed from binary partition table at 0x8000
- Evidence: ESP32 partition table format specification

- Entity / contract: `ProvisioningState` (modal state)
- Shape:
  ```typescript
  type ProvisioningPhase =
    | 'idle'
    | 'connecting'
    | 'reading_partition'
    | 'fetching_nvs'
    | 'flashing'
    | 'verifying'
    | 'success'
    | 'error';

  interface ProvisioningState {
    phase: ProvisioningPhase;
    progress: number;        // 0-100
    message: string;         // Current action label
    error: string | null;    // Technical error message
  }
  ```
- Mapping: Local React state in modal
- Evidence: New contract for UI state machine

---

## 4) API / Integration Surface

- Surface: `GET /api/devices/{device_id}/provisioning?partition_size={size}`
- Inputs: `device_id` (path), `partition_size` (query, integer bytes)
- Outputs: `{ size: number, data: string }` - JSON with base64 NVS blob
- Errors:
  - 400: Invalid partition size (< 12KB or not multiple of 4KB)
  - 404: Device not found
  - 502: Keycloak unavailable
- Evidence: `src/lib/api/generated/types.ts:2066-2099`

- Surface: Web Serial API (browser native)
- Inputs: User port selection, baud rate 115200
- Outputs: Serial port connection for ESP32 communication
- Errors: NotFoundError (user cancelled), NetworkError (connection failed)
- Evidence: Web Serial API specification

- Surface: esptool-js ESPLoader
- Inputs: Serial port, baud rate, terminal callback
- Outputs: Flash read/write operations, partition table parsing
- Errors: Connection timeout, flash write failure, verification failure
- Evidence: esptool-js library API

---

## 5) Algorithms & UI Flows

- Flow: Provision Device workflow
- Steps:
  1. User clicks "Provision Device" button in device editor
  2. Modal opens with "Connect Device" prompt
  3. Check `'serial' in navigator`; if false, show error and abort
  4. User clicks "Connect"; browser shows native port selection dialog
  5. If user cancels, close modal silently
  6. Create ESPLoader instance with selected port at 115200 baud
  7. Attempt automatic reset via RTS/DTR signals
  8. If reset fails, show message asking user to manually enter bootloader
  9. Read 3072 bytes from flash address 0x8000 (partition table)
  10. Parse partition table entries, find entry where name === "nvs"
  11. Validate NVS partition has subtype === 2
  12. Extract partition offset and size from entry
  13. Call backend API: `GET /api/devices/{id}/provisioning?partition_size={size}`
  14. Validate response size matches partition size from device
  15. Decode base64 data to ArrayBuffer
  16. Write ArrayBuffer to flash at partition offset
  17. Read back written data, compute MD5, compare with expected
  18. If verification passes, show success message with manual reset instruction
  19. If any step fails, show technical error message
- States / transitions:
  ```
  idle -> connecting -> reading_partition -> fetching_nvs -> flashing -> verifying -> success
                   |                |              |           |           |
                   v                v              v           v           v
                 error           error          error       error       error
  ```
- Hotspots: Serial connection timing, partition table parsing correctness
- Evidence: Change brief functional requirements

- Flow: Modal close during operation
- Steps:
  1. User clicks X or presses Escape while operation in progress
  2. Show confirmation: "Closing now may leave the device in an inconsistent state"
  3. If confirmed, abort operation, close serial port, close modal
  4. If cancelled, continue operation
- States / transitions: Any active phase -> abort -> closed
- Hotspots: Clean serial port closure to avoid resource leaks
- Evidence: "Allow closing modal at any time" requirement

---

## 6) Derived State & Invariants

- Derived value: `canProvision`
  - Source: `mode === 'edit' && deviceId !== undefined`
  - Writes / cleanup: Controls button visibility in editor header
  - Guards: Only available in edit mode with valid device ID
  - Invariant: Button must not appear for new/duplicate modes
  - Evidence: `src/components/devices/device-editor.tsx:353` - existing mode check

- Derived value: `isWebSerialSupported`
  - Source: `'serial' in navigator && typeof navigator.serial !== 'undefined'`
  - Writes / cleanup: Determines whether to show error or proceed
  - Guards: Check once on modal open
  - Invariant: Must check before any serial operations
  - Evidence: Web Serial API browser compatibility

- Derived value: `progressPercentage`
  - Source: Hybrid phase-based and byte-level calculation:
    - connecting: 5-10 (animate during connection)
    - reading_partition: 10-25 (fixed, quick operation)
    - fetching_nvs: 25-40 (fixed, depends on network)
    - flashing: 40-90 (byte-level progress from ESPLoader write callbacks)
    - verifying: 90-98 (byte-level progress during readback)
    - success: 100
  - Writes / cleanup: Updates progress bar UI
  - Guards: Only increases during normal flow; byte-level granularity during flashing prevents "stuck" appearance
  - Invariant: Must reach 100 only on success phase; flashing phase uses ESPLoader's `writeFlash` progress callback for smoother UX
  - Evidence: UI progress bar requirement, esptool-js write progress callbacks

- Derived value: `partitionValid`
  - Source: Parsed partition table entry with name === "nvs" && subtype === 2
  - Writes / cleanup: Enables NVS fetch step
  - Guards: Both conditions must be true
  - Invariant: Size must be >= 12288 and multiple of 4096
  - Evidence: "Cross-check NVS partition subtype is 2" requirement

---

## 7) State Consistency & Async Coordination

- Source of truth: Local React state in `ProvisionDeviceModal` via `useReducer`
- Coordination:
  - Modal state machine controls UI rendering
  - Serial port reference held in ref to survive re-renders
  - AbortController for cancellation propagation
- Async safeguards:
  - Serial operations wrapped in try-catch with cleanup
  - Port closure in useEffect cleanup and on unmount
  - AbortSignal passed to fetch for API call cancellation
  - Timeouts for serial connection (10s) and flash operations (30s)
- Instrumentation:
  - `ProvisioningStarted` on workflow begin (includes deviceId)
  - `ProvisioningProgress` on phase transitions (includes phase, progress)
  - `ProvisioningComplete` on success (includes deviceId)
  - `ProvisioningError` on failure (includes phase, error message)
- Evidence: `src/lib/test/form-instrumentation.ts` for event emission pattern

---

## 8) Errors & Edge Cases

- Failure: Web Serial API not supported
- Surface: `ProvisionDeviceModal` immediately on open
- Handling: Show error message "Web Serial API is not supported in this browser. Please use Chrome, Edge, or Opera on desktop."
- Guardrails: Feature detection before any operation
- Evidence: Browser compatibility requirement

- Failure: User cancels port selection
- Surface: Native browser dialog
- Handling: Close modal silently, no error toast
- Guardrails: Check for `NotFoundError` from `navigator.serial.requestPort()`
- Evidence: "User cancels port selection - Close modal, no error"

- Failure: Serial connection failed
- Surface: `ProvisionDeviceModal` during connecting phase
- Handling: Show "Failed to connect to device: [technical details]"
- Guardrails: Catch ESPLoader connection errors, include device path in message
- Evidence: Error table in change brief

- Failure: Automatic reset failed
- Surface: `ProvisionDeviceModal` during connecting phase
- Handling: Show "Please put device in bootloader mode manually and click Retry"
- Guardrails: Detect reset failure via timeout or ESPLoader error code
- Evidence: "Auto-reset failed" error case

- Failure: Partition table not readable
- Surface: `ProvisionDeviceModal` during reading_partition phase
- Handling: Show "Could not read partition table at 0x8000"
- Guardrails: Flash read timeout, data length validation
- Evidence: Error table in change brief

- Failure: NVS partition not found
- Surface: `ProvisionDeviceModal` during reading_partition phase
- Handling: Show "NVS partition not found in partition table"
- Guardrails: Iterate all entries, explicit not-found check
- Evidence: Error table in change brief

- Failure: NVS partition wrong subtype
- Surface: `ProvisionDeviceModal` during reading_partition phase
- Handling: Show "Partition 'nvs' has unexpected subtype: [found] (expected 2)"
- Guardrails: Explicit subtype check after name match
- Evidence: "NVS subtype mismatch" error case

- Failure: Blob size mismatch
- Surface: `ProvisionDeviceModal` during fetching_nvs phase
- Handling: Show "NVS blob size mismatch: expected [device] bytes, got [api] bytes"
- Guardrails: Compare response.size with partition.size before write
- Evidence: "Validate response blob size matches partition size"

- Failure: Flash write failed
- Surface: `ProvisionDeviceModal` during flashing phase
- Handling: Show "Failed to write to flash: [technical details]"
- Guardrails: Catch ESPLoader write errors, include address in message
- Evidence: Error table in change brief

- Failure: Verification failed
- Surface: `ProvisionDeviceModal` during verifying phase
- Handling: Show "Flash verification failed: MD5 mismatch"
- Guardrails: Compute MD5 of written data, compare with read-back
- Evidence: "Verification failed" error case

- Failure: Backend API error
- Surface: `ProvisionDeviceModal` during fetching_nvs phase
- Handling: Map status codes to user messages (404: "Device not found", 502: "Unable to retrieve credentials")
- Guardrails: Standard fetch error handling with status code checks
- Evidence: Error table in change brief

---

## 9) Observability / Instrumentation

- Signal: `ProvisioningStarted`
- Type: instrumentation event
- Trigger: When user clicks "Connect" and workflow begins
- Labels / fields: `{ deviceId: number }`
- Consumer: Playwright `waitTestEvent` helper
- Evidence: `src/lib/test/form-instrumentation.ts:38-40`

- Signal: `ProvisioningProgress`
- Type: instrumentation event
- Trigger: On each phase transition
- Labels / fields: `{ deviceId: number, phase: ProvisioningPhase, progress: number }`
- Consumer: Playwright assertions on workflow progress
- Evidence: New event type

- Signal: `ProvisioningComplete`
- Type: instrumentation event
- Trigger: On successful verification
- Labels / fields: `{ deviceId: number }`
- Consumer: Playwright success assertions
- Evidence: `src/lib/test/form-instrumentation.ts:52-54`

- Signal: `ProvisioningError`
- Type: instrumentation event
- Trigger: On any failure during workflow
- Labels / fields: `{ deviceId: number, phase: ProvisioningPhase, error: string }`
- Consumer: Playwright error scenario tests
- Evidence: `src/lib/test/form-instrumentation.ts:59-65`

- Signal: `data-testid` attributes
- Type: DOM selectors
- Trigger: Component render
- Labels / fields:
  - `devices.editor.provision-device` (button)
  - `devices.provision-modal` (modal root)
  - `devices.provision-modal.progress-bar` (progress indicator)
  - `devices.provision-modal.status-message` (current action label)
  - `devices.provision-modal.error-message` (error display)
  - `devices.provision-modal.connect-button` (start button)
  - `devices.provision-modal.close-button` (close/cancel button)
  - `devices.provision-modal.retry-button` (retry on error)
- Consumer: Playwright locators
- Evidence: `tests/e2e/devices/DevicesPage.ts` patterns

---

## 10) Lifecycle & Background Work

- Hook / effect: Serial port cleanup
- Trigger cadence: On modal unmount or close
- Responsibilities: Close serial port connection, release resources
- Cleanup sequence (graceful abort with timeout):
  1. Signal abort via AbortController.abort()
  2. If ESPLoader operation is in progress, call ESPLoader.abort() if available
  3. Wait up to 500ms for any in-flight write to complete or timeout
  4. Call `port.close()` to release the serial port
  5. Clear ArrayBuffer references to release memory
- Evidence: Web Serial API resource management

- Hook / effect: Operation abort
- Trigger cadence: On modal close during active operation
- Responsibilities: Signal abort to async operations, gracefully stop device communication
- Cleanup:
  1. AbortController.abort() - stops JavaScript async operations
  2. ESPLoader disconnect (if mid-operation)
  3. Short grace period (500ms) before port.close() to avoid corrupting device state
  4. Emit `ProvisioningError` event with phase and 'aborted' error
- Evidence: Async operation cancellation pattern

- Hook / effect: ESPLoader instance management
- Trigger cadence: Created on connect, destroyed on close
- Responsibilities: Manage ESPLoader lifecycle
- Cleanup: Disconnect ESPLoader, release terminal callbacks
- Evidence: esptool-js library usage

---

## 11) Security & Permissions

- Concern: Serial port access requires user gesture
- Touchpoints: `ProvisionDeviceModal` connect button click
- Mitigation: Always trigger `navigator.serial.requestPort()` from user click handler
- Residual risk: None - browser enforces gesture requirement
- Evidence: Web Serial API security model

- Concern: Provisioning data contains secrets
- Touchpoints: API response handling, memory management
- Mitigation: Don't log decoded data, clear ArrayBuffer after write, don't persist to localStorage
- Residual risk: Data briefly in memory - acceptable for device provisioning workflow
- Evidence: Change brief security considerations

- Concern: HTTPS required for Web Serial in production
- Touchpoints: Application deployment
- Mitigation: Enforce HTTPS in production, localhost exemption for development
- Residual risk: None - browser blocks Web Serial on insecure origins
- Evidence: Web Serial API requirements

---

## 12) UX / UI Impact

- Entry point: Device editor page (edit mode only)
- Change: Move "Provision Device" button to left side of header, separate from form action buttons
- User interaction: Clear visual separation between device actions (left) and form actions (right)
- Dependencies: No backend changes for button placement
- Evidence: `src/components/devices/device-editor.tsx:338-387`

- Entry point: Provision Device modal
- Change: New modal with progress bar, status message, and action buttons
- User interaction:
  1. Click "Provision Device" -> Modal opens with instructions
  2. Click "Connect" -> Native port picker appears
  3. Select port -> Progress bar animates through phases
  4. Success -> Show success message with reset instruction
  5. Error -> Show technical error with retry option
  6. Close at any time -> Confirmation if operation active
- Dependencies: esptool-js, Web Serial API
- Evidence: Change brief UI requirements

---

## 13) Deterministic Test Plan

- Surface: Provision Device button visibility
- Scenarios:
  - Given device editor in edit mode, When page loads, Then "Provision Device" button is visible on left side of header
  - Given device editor in new mode, When page loads, Then "Provision Device" button is not visible
  - Given device editor in duplicate mode, When page loads, Then "Provision Device" button is not visible
- Instrumentation / hooks: `devices.editor.provision-device` button locator
- Gaps: None
- Evidence: `tests/e2e/devices/DevicesPage.ts` patterns

- Surface: Web Serial unsupported error
- Scenarios:
  - Given browser without Web Serial API, When user clicks "Provision Device", Then modal shows "Web Serial API not supported" error
- Instrumentation / hooks: `ProvisioningError` event with error message, `devices.provision-modal.error-message` locator
- Mock approach: Use `page.addInitScript()` in test setup to delete `navigator.serial` before page load:
  ```typescript
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'serial', { value: undefined, writable: false });
  });
  ```
- Gaps: None
- Evidence: Browser compatibility requirement

- Surface: Provisioning workflow success (mocked)
- Scenarios:
  - Given mocked ESPLoader returning valid partition table with NVS at 0x9000, size 20480, When provisioning completes, Then `ProvisioningComplete` event is emitted
  - Given successful flash and verification, When modal shows success, Then message instructs manual reset
- Instrumentation / hooks: ESPLoader mock, `ProvisioningStarted`, `ProvisioningProgress`, `ProvisioningComplete` events
- Gaps: Real hardware testing deferred to manual QA
- Evidence: "Mock ESPLoader class at module level for Playwright tests"

- Surface: Provisioning workflow errors (mocked)
- Scenarios:
  - Given mocked ESPLoader failing connection, When user clicks Connect, Then `ProvisioningError` event emitted with "connecting" phase
  - Given mocked partition table without NVS, When reading partition, Then error "NVS partition not found"
  - Given mocked NVS partition with wrong subtype, When reading partition, Then error "unexpected subtype"
  - Given backend returning mismatched size, When fetching NVS, Then error "size mismatch"
  - Given mocked flash write failure, When flashing, Then error "Failed to write to flash"
  - Given mocked verification failure, When verifying, Then error "MD5 mismatch"
- Instrumentation / hooks: ESPLoader mock configuration via `configureESPLoaderMock()`, `ProvisioningError` events
- Mock configuration per scenario:
  - Connection failure: `configureESPLoaderMock({ connectionResult: 'error' })`
  - Missing NVS: `configureESPLoaderMock({ partitionTable: [{ name: 'app', type: 0, subtype: 0, offset: 0x10000, size: 0x100000 }] })`
  - Wrong subtype: `configureESPLoaderMock({ partitionTable: [{ name: 'nvs', type: 1, subtype: 3, offset: 0x9000, size: 0x5000 }] })`
  - Flash write failure: `configureESPLoaderMock({ flashWriteResult: 'error' })`
  - Verification failure: `configureESPLoaderMock({ verificationResult: 'mismatch' })`
- Gaps: None
- Evidence: Error handling requirements

- Surface: Modal close during operation
- Scenarios:
  - Given provisioning in progress, When user clicks close, Then confirmation dialog appears
  - Given confirmation dialog, When user confirms close, Then modal closes and port is released
  - Given confirmation dialog, When user cancels, Then operation continues
- Instrumentation / hooks: `devices.provision-modal.close-button`, confirmation dialog locators
- Gaps: None
- Evidence: "Allow closing modal at any time" requirement

- Surface: Retry after error
- Scenarios:
  - Given provisioning error displayed (any error type), When user clicks retry button, Then `ProvisioningStarted` event emitted and workflow restarts from connecting phase
  - Given retry initiated after connection error, When connection succeeds on retry, Then provisioning continues normally
- Instrumentation / hooks: `devices.provision-modal.retry-button`, `ProvisioningStarted` event on retry
- Gaps: None
- Evidence: "Show technical error with retry option" in UI requirements

---

## 14) Implementation Slices

- Slice: 1. Instrumentation and types
- Goal: Establish test event infrastructure before UI work
- Touches: `src/types/test-events.ts`, `src/lib/test/provisioning-instrumentation.ts`
- Dependencies: None

- Slice: 2. ESPLoader mock for tests
- Goal: Enable Playwright testing before real hardware integration
- Touches:
  - `tests/support/mocks/esptool-mock.ts` - Mock implementation with configuration API
  - `src/lib/esptool/index.ts` - Wrapper module that conditionally imports real or mock ESPLoader
  - `vite.config.ts` - Add resolve.alias to redirect `esptool-js` imports in test mode
- Vite configuration:
  ```typescript
  // In vite.config.ts, when VITE_TEST_MODE=true:
  resolve: {
    alias: {
      'esptool-js': process.env.VITE_TEST_MODE === 'true'
        ? path.resolve(__dirname, 'tests/support/mocks/esptool-mock.ts')
        : 'esptool-js'
    }
  }
  ```
- Dependencies: Slice 1

- Slice: 3. Core provisioning hook
- Goal: Implement esptool-js integration with partition reading and API calls
- Touches: `src/hooks/use-provisioning.ts`, `package.json` (add esptool-js)
- Dependencies: Slice 1

- Slice: 4. Provision Device Modal
- Goal: UI component with progress and error states
- Touches: `src/components/devices/provision-device-modal.tsx`
- Dependencies: Slice 1, 3

- Slice: 5. Device editor integration
- Goal: Replace download button, restructure header
- Touches: `src/components/devices/device-editor.tsx`, remove `downloadDeviceProvisioning` from `use-devices.ts`
- Dependencies: Slice 4

- Slice: 6. Playwright tests
- Goal: Full test coverage for mocked workflow
- Touches: `tests/e2e/devices/DevicesPage.ts`, `tests/e2e/devices/devices-provisioning.spec.ts`
- Dependencies: All previous slices

---

## 15) Risks & Open Questions

- Risk: esptool-js API may differ from documentation
- Impact: Implementation delays, potential workarounds needed
- Mitigation: Prototype partition reading early, validate API against ESP32 IDF documentation

- Risk: Web Serial API browser support limitations
- Impact: Users on unsupported browsers cannot provision
- Mitigation: Clear error messaging, no fallback download per requirements

- Risk: Partition table parsing edge cases
- Impact: False negatives (NVS not found) on valid devices
- Mitigation: Test with multiple ESP32 partition configurations, follow IDF specification exactly

- Risk: MD5 verification performance on large partitions
- Impact: UI may appear frozen during verification
- Mitigation: Update progress during verification, consider chunked verification if needed

- Question: Which esptool-js package to use?
- Why it matters: Multiple forks exist on npm with varying maintenance status
- Owner / follow-up: Use official Espressif package `esptool-js` from https://github.com/espressif/esptool-js

---

## 16) Confidence

Confidence: High - Requirements are well-specified, existing patterns for instrumentation and testing are clear, and esptool-js provides the necessary primitives. The main complexity is in the multi-step async workflow, which is manageable with proper state machine design.
