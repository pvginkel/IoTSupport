# NVS Provisioning - Frontend Impact

This document describes the frontend changes required to support the NVS provisioning feature.

## Breaking Changes

### Changed Endpoint Response

The provisioning endpoint response format has changed from a binary file download to a JSON response:

| Aspect | Old Behavior | New Behavior |
|--------|--------------|--------------|
| Endpoint | `GET /api/devices/<id>/provisioning` | `GET /api/devices/<id>/provisioning` |
| Content-Type | `application/octet-stream` | `application/json` |
| Response | Binary file download (JSON content) | JSON with base64 NVS blob |
| Headers | `Content-Disposition: attachment; filename=provisioning-<key>.bin` | Standard JSON response headers |

### Old Response (Removed)

```
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename=provisioning-abc12345.bin

{"device_key": "abc12345", "client_id": "...", ...}
```

### New Request

The endpoint now requires a `partition_size` query parameter:

```
GET /api/devices/<id>/provisioning?partition_size=20480
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `partition_size` | integer | Yes | NVS partition size in bytes. Must match the partition table on the device. Minimum 12288 (0x3000), must be a multiple of 4096 (0x1000). |

**Common partition sizes:**
- `16384` (0x4000) - 16KB
- `20480` (0x5000) - 20KB
- `24576` (0x6000) - 24KB

### New Response

```json
{
  "size": 20480,
  "data": "<base64-encoded NVS binary blob>"
}
```

## New Features to Implement

### 1. Web Serial Flash Integration

Replace the file download with an in-browser flashing workflow using esptool-js.

**Flow:**
1. User clicks "Flash Provisioning" button on device detail page
2. Frontend fetches `GET /api/devices/<id>/provisioning`
3. Modal opens prompting user to connect ESP32 via USB
4. User grants Web Serial permission and selects device
5. Frontend uses esptool-js to:
   - Connect to ESP32
   - Read partition table to find `nvs` partition offset
   - Write the decoded NVS blob to that offset
   - Verify by reading back
6. Display success/failure message

**Libraries Required:**
- [esptool-js](https://github.com/nicknameprofile/nicknameprofile-esptool-js) or equivalent
- Web Serial API (Chrome/Edge 89+, requires HTTPS or localhost)

### 2. Provisioning Response Handling

```typescript
interface NvsProvisioningResponse {
  size: number;       // Partition size in bytes
  data: string;       // Base64-encoded NVS binary
}

// Fetch provisioning with partition size
async function fetchProvisioning(deviceId: number, partitionSize: number): Promise<NvsProvisioningResponse> {
  const response = await fetch(
    `/api/devices/${deviceId}/provisioning?partition_size=${partitionSize}`
  );
  if (!response.ok) throw new Error('Failed to fetch provisioning');
  return response.json();
}

// Decode the base64 data to ArrayBuffer for flashing
function decodeNvsData(response: NvsProvisioningResponse): ArrayBuffer {
  const binaryString = atob(response.data);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}
```

### 3. Flash Modal Component

Create a modal component for the flashing workflow:

**States:**
- `idle` - Initial state, "Connect Device" button visible
- `connecting` - Waiting for user to select serial port
- `reading_partition` - Reading partition table from device
- `flashing` - Writing NVS data to device
- `verifying` - Reading back data to verify
- `success` - Flash completed successfully
- `error` - Error occurred (with message)

**UI Elements:**
- Progress indicator for multi-step process
- Serial port selection (browser-native dialog)
- Cancel button (aborts operation, closes port)
- Retry button (on error)
- Success confirmation with device details

### 4. Browser Compatibility

Web Serial API is only available in:
- Chrome 89+ (desktop)
- Edge 89+ (desktop)
- Opera 76+ (desktop)

**Fallback behavior:**
- Detect Web Serial support: `'serial' in navigator`
- If unsupported, show a message explaining the requirement
- Optionally provide a "Download NVS File" button that saves the decoded blob as a `.bin` file for manual flashing via command-line tools

## Response Schema

```typescript
interface NvsProvisioningResponse {
  size: number;       // Partition size in bytes (matches the request)
  data: string;       // Base64-encoded binary data (size bytes when decoded)
}
```

## Error Handling

| HTTP Status | When | Action |
|-------------|------|--------|
| 200 | Success | Process JSON response |
| 400 | Missing/invalid partition_size | Show "Invalid partition size" error (must be ≥12KB and multiple of 4KB) |
| 404 | Device not found | Show "Device not found" error |
| 502 | Keycloak unavailable | Show "Unable to retrieve credentials" error |

## Migration Checklist

1. [ ] Remove existing file download logic for provisioning
2. [ ] Add esptool-js dependency
3. [ ] Create FlashProvisioningModal component
4. [ ] Implement Web Serial connection flow
5. [ ] Implement partition table reading to determine NVS partition offset and size
6. [ ] **Pass partition size from device's partition table as `partition_size` query param**
7. [ ] Implement NVS flashing with progress
8. [ ] Add verification step
9. [ ] Handle browser compatibility (show message if unsupported)
10. [ ] Update device detail page to use new modal
11. [ ] Add fallback "Download NVS File" option for unsupported browsers
12. [ ] Update TypeScript types for new response format (includes `size` field)

## Security Considerations

- Web Serial requires HTTPS in production (or localhost for development)
- User must explicitly grant permission for each serial port access
- Provisioning data contains secrets (client_secret, wifi_password) - same security posture as before
- Consider clearing the decoded NVS data from memory after flashing completes
