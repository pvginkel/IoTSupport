# NVS Provisioning - Plan Review

## 1) Summary & Decision

**Readiness**

The plan is well-researched and thorough, demonstrating clear understanding of the existing codebase patterns and the technical requirements for ESP32 provisioning via Web Serial API. The research log correctly identifies relevant components, hooks, and instrumentation patterns. The plan covers the full scope from UI changes through error handling and testing, with clear state machine design. The plan now includes complete specifications for test event type integration and the ESPLoader mock configuration mechanism, addressing the initial conformance gaps.

**Decision**

`GO` - The plan is implementation-ready. All previously identified conditions have been addressed in the updated plan:
1. Test event type integration is fully specified (lines 116-122)
2. ESPLoader mock configuration API and Vite alias injection are documented (lines 136-150, 607-624)
3. Graceful cleanup with timeout is specified for serial port operations (lines 458-477)
4. Retry workflow test scenario added (lines 590-596)

---

## 2) Conformance & Fit (with evidence)

**Conformance to refs**

- `docs/commands/plan_feature.md` - Pass - Plan follows all required sections (0-16) and uses proper templates. Evidence: `plan.md:1-675` contains all headings with appropriate content.

- `docs/product_brief.md` - Pass - The device editor feature aligns with the product context of managing ESP32 device configurations. Evidence: `plan.md:29-33` "Replace the current file download provisioning workflow with an in-browser ESP32 flashing experience" aligns with device configuration management in the brief.

- `docs/contribute/architecture/application_overview.md` - Pass - Plan correctly leverages existing patterns: domain hooks in `src/hooks/`, test instrumentation in `src/lib/test/`, generated API client usage. Evidence: `plan.md:108-110` "Hook wrapping esptool-js communication, partition reading, and API calls" follows the pattern from `application_overview.md:33-34`.

- `docs/contribute/testing/playwright_developer_guide.md` - Pass - Plan fully specifies the ESPLoader mock injection mechanism using Vite's resolve.alias and provides a configuration API for deterministic test scenarios. Evidence: `plan.md:136-150` specifies the mock configuration API, `plan.md:607-624` documents the Vite alias setup.

**Fit with codebase**

- `src/types/test-events.ts` - `plan.md:116-122` - Plan explicitly specifies all three required changes: add `PROVISIONING` to TestEventKind, create `ProvisioningTestEvent` interface, and extend the `TestEvent` union type. Fully aligned.

- `src/lib/test/form-instrumentation.ts` - `plan.md:112-114` - Plan correctly references this as the pattern for `useProvisioningInstrumentation`. The proposed event structure (Started, Progress, Complete, Error) mirrors the form lifecycle pattern.

- `src/components/devices/device-editor.tsx` - `plan.md:100-102` - Plan correctly identifies lines 353-365 as the current Download Provisioning button location and proposes header restructure.

- `src/hooks/use-devices.ts` - `plan.md:124-126` - Plan correctly identifies `downloadDeviceProvisioning` (lines 267-291) for removal.

- `tests/e2e/devices/DevicesPage.ts` - `plan.md:128-130` - Plan proposes extending the page object with provisioning modal locators, which fits the existing pattern at lines 62-98.

---

## 3) Open Questions & Ambiguities

All previously identified questions have been resolved in the updated plan:

- ESPLoader mock injection mechanism: Resolved at `plan.md:136-150` and `plan.md:607-624` - Uses Vite's resolve.alias with `VITE_TEST_MODE` flag.

- Progress percentage granularity: Resolved at `plan.md:296-307` - Plan now specifies hybrid phase-based and byte-level progress, with byte-level granularity during flashing phase using ESPLoader's write callbacks.

- Web Serial mock in Playwright: Resolved at `plan.md:546-551` - Plan specifies using `page.addInitScript()` to mock `navigator.serial` as undefined.

---

## 4) Deterministic Playwright Coverage (new/changed behavior only)

- Behavior: Provision Device button visibility and placement
- Scenarios:
  - Given device editor in edit mode, When page loads, Then "Provision Device" button is visible on left side of header (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given device editor in new mode, When page loads, Then "Provision Device" button is not visible (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given device editor in duplicate mode, When page loads, Then "Provision Device" button is not visible (`tests/e2e/devices/devices-provisioning.spec.ts`)
- Instrumentation: `devices.editor.provision-device` button locator
- Backend hooks: None required - UI state only
- Gaps: None
- Evidence: `plan.md:533-540`

- Behavior: Web Serial unsupported error display
- Scenarios:
  - Given browser without Web Serial API, When user clicks "Provision Device", Then modal shows "Web Serial API not supported" error (`tests/e2e/devices/devices-provisioning.spec.ts`)
- Instrumentation: `ProvisioningError` event, `devices.provision-modal.error-message` locator
- Backend hooks: Test uses `page.addInitScript()` to remove `navigator.serial`
- Gaps: None
- Evidence: `plan.md:542-553`

- Behavior: Provisioning workflow success (mocked ESPLoader)
- Scenarios:
  - Given mocked ESPLoader with valid partition table (NVS at 0x9000, size 20480), When provisioning completes, Then `ProvisioningComplete` event is emitted (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given successful flash and verification, When modal shows success, Then message instructs manual reset (`tests/e2e/devices/devices-provisioning.spec.ts`)
- Instrumentation: `ProvisioningStarted`, `ProvisioningProgress`, `ProvisioningComplete` events, `devices.provision-modal.status-message` locator
- Backend hooks: Device factory must create device with valid ID for API call
- Gaps: Real hardware testing deferred to manual QA (acceptable)
- Evidence: `plan.md:555-561`

- Behavior: Provisioning workflow error scenarios (mocked ESPLoader)
- Scenarios:
  - Given mocked ESPLoader failing connection, When user clicks Connect, Then `ProvisioningError` event emitted with phase "connecting" (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given mocked partition table without NVS entry, When reading partition, Then error "NVS partition not found" displayed (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given mocked NVS partition with subtype 3 (not 2), When reading partition, Then error "unexpected subtype" displayed (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given backend returning size mismatch (e.g., response.size=16384 vs partition.size=20480), When fetching NVS, Then error "size mismatch" displayed (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given mocked flash write failure, When flashing, Then error "Failed to write to flash" displayed (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given mocked MD5 verification failure, When verifying, Then error "MD5 mismatch" displayed (`tests/e2e/devices/devices-provisioning.spec.ts`)
- Instrumentation: `ProvisioningError` events with phase and error fields, mock configuration via `configureESPLoaderMock()`
- Backend hooks: Device factory for API calls
- Gaps: None - mock configuration API fully specified at `plan.md:572-577`
- Evidence: `plan.md:563-579`

- Behavior: Modal close during active operation
- Scenarios:
  - Given provisioning in progress (any active phase), When user clicks close button, Then confirmation dialog appears (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given confirmation dialog visible, When user confirms close, Then modal closes and `ProvisioningError` event emitted with abort (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given confirmation dialog visible, When user cancels, Then dialog closes and operation continues (`tests/e2e/devices/devices-provisioning.spec.ts`)
- Instrumentation: `devices.provision-modal.close-button`, confirmation dialog locators, `ProvisioningError` event on abort
- Backend hooks: None - client-side only
- Gaps: None
- Evidence: `plan.md:581-588`

- Behavior: Retry after error
- Scenarios:
  - Given provisioning error displayed (any error type), When user clicks retry button, Then `ProvisioningStarted` event emitted and workflow restarts (`tests/e2e/devices/devices-provisioning.spec.ts`)
  - Given retry initiated after connection error, When connection succeeds on retry, Then provisioning continues normally (`tests/e2e/devices/devices-provisioning.spec.ts`)
- Instrumentation: `devices.provision-modal.retry-button`, `ProvisioningStarted` event on retry
- Backend hooks: None - mock state reset between attempts
- Gaps: None
- Evidence: `plan.md:590-596`

---

## 5) Adversarial Sweep (must find >=3 credible issues or declare why none exist)

All previously identified Major issues have been resolved. Performing additional adversarial checks:

- Checks attempted: Test event TypeScript integration completeness
- Evidence: `plan.md:116-122` explicitly lists all three required changes to `src/types/test-events.ts`
- Why the plan holds: The plan now specifies adding the event to the TestEventKind const, creating the interface with proper literal type, and extending the union type

- Checks attempted: ESPLoader mock configuration for deterministic testing
- Evidence: `plan.md:136-150` provides complete configuration API, `plan.md:572-577` shows per-scenario configuration
- Why the plan holds: Each error scenario has explicit mock configuration, enabling deterministic test coverage

- Checks attempted: Serial port cleanup race condition
- Evidence: `plan.md:458-477` specifies graceful cleanup sequence with 500ms grace period
- Why the plan holds: Cleanup now waits for in-flight operations before port closure

- Checks attempted: Retry workflow coverage
- Evidence: `plan.md:590-596` adds retry test scenarios
- Why the plan holds: Button instrumentation and retry flow are now covered

**Minor remaining observations (not blocking):**

**Minor - ProvisioningTestEvent interface shape not fully specified**

**Evidence:** `plan.md:116-122` specifies creating the interface but does not show the full TypeScript shape.

**Why it matters:** Implementation could interpret the interface differently. However, the events are well-documented at `plan.md:411-437` with all required fields.

**Fix suggestion:** For completeness, add the interface shape to the plan:
```typescript
interface ProvisioningTestEvent extends BaseTestEvent {
  kind: 'provisioning';
  phase: 'started' | 'progress' | 'complete' | 'error';
  deviceId: number;
  progress?: number;
  error?: string;
}
```
This is a minor clarification and does not block implementation.

**Confidence:** High

---

## 6) Derived-Value & State Invariants (table)

- Derived value: `canProvision`
  - Source dataset: Unfiltered - `mode === 'edit' && deviceId !== undefined`
  - Write / cleanup triggered: Controls button visibility in editor header (render only, no side effects)
  - Guards: Mode check prevents provisioning in new/duplicate states
  - Invariant: Provisioning must never be attempted without a saved device ID (required for API call)
  - Evidence: `plan.md:282-287`

- Derived value: `isWebSerialSupported`
  - Source dataset: Unfiltered - `'serial' in navigator && typeof navigator.serial !== 'undefined'`
  - Write / cleanup triggered: Determines whether error is shown or workflow proceeds (no persistent write)
  - Guards: Check performed once on modal open; stored in local state
  - Invariant: Must be true before any `navigator.serial.*` call is made
  - Evidence: `plan.md:289-294`

- Derived value: `partitionValid`
  - Source dataset: Filtered - Parsed partition table entries where `name === "nvs"` AND `subtype === 2`
  - Write / cleanup triggered: Enables transition to `fetching_nvs` phase; partition size used in API call
  - Guards: Both name and subtype conditions enforced; size validation (>= 12288, multiple of 4096)
  - Invariant: API call must only proceed if partition is valid; size parameter must match device partition exactly
  - Evidence: `plan.md:309-314`

- Derived value: `progressPercentage`
  - Source dataset: Hybrid - Phase transitions plus byte-level callbacks from ESPLoader during flashing
  - Write / cleanup triggered: Updates progress bar UI (visual only)
  - Guards: Progress only increases during normal flow; byte-level granularity during flashing prevents "stuck" appearance
  - Invariant: Progress must reach 100 only on `success` phase; intermediate phases never show 100
  - Evidence: `plan.md:296-307`

---

## 7) Risks & Mitigations (top 3)

- Risk: esptool-js API may differ from expected interface, causing implementation delays or requiring workarounds
- Mitigation: Prototype partition table reading in a standalone script before full integration. Validate against ESP-IDF documentation for partition table binary format.
- Evidence: `plan.md:650-652`

- Risk: ESPLoader mock complexity may introduce test brittleness if mock does not accurately simulate real device behavior
- Mitigation: Mock configuration API is well-specified with explicit scenario mappings. Document expected ESPLoader behavior in mock file. Consider integration test with real hardware in manual QA phase.
- Evidence: `plan.md:136-150`, `plan.md:572-577`

- Risk: Serial port cleanup during active flash may corrupt device NVS or leave device in unrecoverable state
- Mitigation: Graceful abort with 500ms timeout before port closure is now specified. User-facing error message documents that device may need manual recovery if closed mid-flash.
- Evidence: `plan.md:458-477`

---

## 8) Confidence

Confidence: High - The plan is comprehensive, addresses all identified concerns, and provides sufficient detail for implementation. The mock configuration API, test event integration, and graceful cleanup sequence are well-specified. The plan is ready for implementation.
