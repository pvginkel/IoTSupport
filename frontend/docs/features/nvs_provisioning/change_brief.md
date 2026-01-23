# NVS Provisioning - Change Brief

## Summary

Replace the current "Download Provisioning" file download with an in-browser "Provision Device" flow that flashes NVS credentials directly to an ESP32 device via Web Serial API and esptool-js.

## Background

The backend provisioning endpoint (`GET /api/devices/{id}/provisioning`) has been updated to return JSON with a base64-encoded NVS binary blob instead of a downloadable file. The frontend needs to consume this new format and provide a seamless flashing experience.

## Backend API Changes

**Endpoint**: `GET /api/devices/{device_id}/provisioning?partition_size={size}`

**Request**: Requires `partition_size` query parameter (integer, bytes) - must match the NVS partition size from the device's partition table.

**Response**:
```json
{
  "size": 20480,
  "data": "<base64-encoded NVS binary blob>"
}
```

## Functional Requirements

### Primary Flow

1. User clicks "Provision Device" button in device editor (edit mode only)
2. Browser checks Web Serial API availability; shows error if unsupported
3. Browser prompts user to select serial port (native browser dialog)
4. System attempts automatic reset into bootloader mode via RTS/DTR
5. System connects to ESP32 at 115200 baud
6. System reads partition table from 0x8000 to find NVS partition (by name "nvs", cross-check subtype=2)
7. System calls backend API with discovered partition size
8. System validates response blob size matches partition size
9. System writes NVS blob to the partition offset
10. System verifies write via MD5 checksum
11. Device remains in bootloader mode; user shown success message with instruction to manually reset

### UI Requirements

- Replace "Download Provisioning" button with "Provision Device" button
- Move button to left side of header (separate from form actions Cancel/Duplicate/Save)
- Show modal dialog with progress bar and current-action label during provisioning
- Allow closing modal at any time (warn that device may be in inconsistent state if mid-flash)
- Display technical error messages (helpful for debugging)

### Browser Compatibility

- Web Serial API required (Chrome 89+, Edge 89+, Opera 76+)
- If unsupported, show error message (no fallback download)
- HTTPS required in production (localhost works for development)

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Web Serial not supported | Show "Web Serial API not supported" error |
| User cancels port selection | Close modal, no error |
| Connection failed | Show "Failed to connect to device" with details |
| Auto-reset failed | Show "Please put device in bootloader mode manually" |
| Partition table not found | Show "Could not read partition table at 0x8000" |
| NVS partition not found | Show "NVS partition not found in partition table" |
| NVS subtype mismatch | Show "Partition 'nvs' has unexpected subtype" |
| Blob size mismatch | Show "NVS blob size mismatch: expected X, got Y" |
| Flash write failed | Show "Failed to write to flash" with details |
| Verification failed | Show "Flash verification failed" |
| Backend API error | Show appropriate error (404, 502, etc.) |

## Technical Approach

### Dependencies

- `esptool-js` (official Espressif package) for ESP32 communication

### New Components/Hooks

- `ProvisionDeviceModal` - Modal component managing the provisioning workflow
- `useProvisioning` - Hook wrapping the provisioning API call
- `useProvisioningInstrumentation` - Test instrumentation for Playwright

### Testing

- Mock ESPLoader class at module level for Playwright tests (exception to no-mock rule since Web Serial unavailable in headless browsers)
- Test full flow logic including error states
- Instrumentation events: `ProvisioningStarted`, `ProvisioningProgress`, `ProvisioningComplete`, `ProvisioningError`

## Out of Scope

- Fallback file download for unsupported browsers
- Device type verification (trusting user connects correct device)
- Flashing history tracking
- Multiple device flashing in sequence

## References

- Backend plan: `/work/backend/docs/features/nvs_provisioning/plan.md`
- Backend frontend impact doc: `/work/backend/docs/features/nvs_provisioning/frontend_impact.md`
- esptool-js: https://github.com/espressif/esptool-js
- ESP32 partition tables: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/partition-tables.html
