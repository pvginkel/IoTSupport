# Device Provisioning MDM - Frontend Impact

This document describes the frontend changes required to support the new Device Provisioning MDM backend feature.

## Breaking Changes

### Removed Endpoints

The following endpoints are **removed** and must not be called:

| Removed Endpoint | Replacement |
|------------------|-------------|
| `GET /api/configs` | `GET /api/devices` |
| `POST /api/configs` | `POST /api/devices` |
| `GET /api/configs/<id>` | `GET /api/devices/<id>` |
| `PUT /api/configs/<id>` | `PUT /api/devices/<id>` |
| `DELETE /api/configs/<id>` | `DELETE /api/devices/<id>` |
| `GET /api/configs/<mac>.json` | `GET /iot/config` (device JWT auth) |

### Data Model Changes

**Config** is replaced by **Device**:

| Old Field (Config) | New Field (Device) | Notes |
|-------------------|-------------------|-------|
| `mac_address` | `key` | 8-char alphanumeric, auto-generated |
| `device_name` | N/A | Removed (use config JSON if needed) |
| `device_entity_id` | N/A | Removed (use config JSON if needed) |
| `enable_ota` | N/A | Removed (use config JSON if needed) |
| `content` | `config` | Same JSON string field |
| N/A | `device_model_id` | **Required** FK to DeviceModel |
| N/A | `rotation_state` | New enum field |
| N/A | `secret_created_at` | New timestamp |
| N/A | `last_rotation_attempt_at` | New timestamp |
| N/A | `last_rotation_completed_at` | New timestamp |

## New Features to Implement

### 1. Device Models Management

New page or section for managing hardware types.

**Endpoints:**
- `GET /api/device-models` - List all models
- `POST /api/device-models` - Create model `{ "code": string, "name": string }`
- `GET /api/device-models/<id>` - Get model details
- `PUT /api/device-models/<id>` - Update model `{ "name": string }`
- `DELETE /api/device-models/<id>` - Delete model (fails if has devices)

**Firmware Management:**
- `POST /api/device-models/<id>/firmware` - Upload firmware (multipart form)
- `GET /api/device-models/<id>/firmware` - Download firmware

**UI Requirements:**
- List view showing code, name, firmware_version, device_count
- Create form with code (immutable after creation, pattern `[a-z0-9_]+`) and name
- Edit form for name only
- Firmware upload with drag-and-drop or file picker
- Firmware download button
- Delete button (disabled if device_count > 0)

### 2. Devices Management (Replaces Configs)

Updated page replacing the old configs management.

**Endpoints:**
- `GET /api/devices` - List all devices (supports `?model_id=N` filter)
- `POST /api/devices` - Create device `{ "device_model_id": int, "config": string }`
- `GET /api/devices/<id>` - Get device details
- `PUT /api/devices/<id>` - Update device `{ "config": string }`
- `DELETE /api/devices/<id>` - Delete device
- `GET /api/devices/<id>/provisioning` - Download provisioning package (.bin file)
- `POST /api/devices/<id>/rotate` - Trigger single-device rotation

**UI Requirements:**
- List view showing key, model name, rotation_state, secret_age
- Create form:
  - Model selector (dropdown from `/api/device-models`)
  - Config JSON editor (validate JSON before submit)
- Edit form for config only (key and model are immutable)
- Provisioning download button (saves as `provisioning-<key>.bin`)
- Rotate button (triggers rotation for single device)
- Delete button

**Rotation State Display:**
- `OK` - Green badge
- `QUEUED` - Yellow badge
- `PENDING` - Blue badge with spinner
- `TIMEOUT` - Red badge

**Secret Age Display:**
- Normal (within half rotation interval) - No indicator
- Late (past half rotation interval) - Orange warning
- Very late (past full rotation interval) - Red warning

### 3. Rotation Dashboard

New page or section for fleet-wide rotation status.

**Endpoints:**
- `GET /api/rotation/status` - Fleet-wide statistics
- `POST /api/rotation/trigger` - Trigger fleet-wide rotation

**Response from `GET /api/rotation/status`:**
```json
{
  "counts_by_state": {
    "OK": 150,
    "QUEUED": 10,
    "PENDING": 1,
    "TIMEOUT": 2
  },
  "pending_device_id": 42,
  "last_rotation_completed_at": "2026-01-22T10:30:00Z"
}
```

**UI Requirements:**
- State counts with colored badges/cards
- Progress bar showing rotation completion percentage
- "Trigger Rotation" button to queue all OK devices
- Link to pending device if one is in progress
- Timestamp of last completed rotation

### 4. Navigation Updates

- Rename "Configs" to "Devices" in navigation
- Add "Device Models" link
- Add "Rotation" link (or embed in Devices page)

## Response Schema Changes

### Device List Response

```typescript
interface DeviceListResponse {
  devices: DeviceSummary[];
  count: number;
}

interface DeviceSummary {
  id: number;
  key: string;  // 8-char alphanumeric
  device_model_id: number;
  rotation_state: "OK" | "QUEUED" | "PENDING" | "TIMEOUT";
  secret_created_at: string | null;  // ISO 8601
}
```

### Device Detail Response

```typescript
interface DeviceResponse {
  id: number;
  key: string;
  device_model_id: number;
  device_model: {
    id: number;
    code: string;
    name: string;
    firmware_version: string | null;
  };
  config: object;  // Parsed JSON
  rotation_state: "OK" | "QUEUED" | "PENDING" | "TIMEOUT";
  client_id: string;  // Keycloak client ID: iotdevice-<model_code>-<key>
  secret_created_at: string | null;
  last_rotation_attempt_at: string | null;
  last_rotation_completed_at: string | null;
  created_at: string;
  updated_at: string;
}
```

### Device Model Response

```typescript
interface DeviceModelResponse {
  id: number;
  code: string;
  name: string;
  firmware_version: string | null;
  device_count: number;
  created_at: string;
  updated_at: string;
}
```

## Error Handling Updates

New error codes to handle:

| Code | HTTP Status | When |
|------|-------------|------|
| `RECORD_NOT_FOUND` | 404 | Device or model not found |
| `RECORD_EXISTS` | 409 | Duplicate model code |
| `INVALID_OPERATION` | 400 | Invalid code format, delete model with devices |
| `EXTERNAL_SERVICE_ERROR` | 502 | Keycloak unavailable |

## Migration Checklist

1. [ ] Remove all references to `mac_address` in frontend code
2. [ ] Update API client to use new `/api/devices` endpoints
3. [ ] Create DeviceModel management UI
4. [ ] Update Devices list to show rotation state
5. [ ] Add provisioning download functionality
6. [ ] Add rotation trigger buttons (single and fleet-wide)
7. [ ] Create rotation dashboard or status section
8. [ ] Update navigation menu
9. [ ] Update TypeScript types for new schemas
10. [ ] Remove old config-related components
