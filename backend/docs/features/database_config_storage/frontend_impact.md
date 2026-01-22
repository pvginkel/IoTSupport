# Frontend Impact: Database Configuration Storage

This document describes the API changes that require frontend updates.

## Breaking Changes

### 1. MAC Address Format

**Change:** MAC addresses now use colon-separated format instead of dash-separated.

**Before:** `aa-bb-cc-dd-ee-ff`
**After:** `aa:bb:cc:dd:ee:ff`

**Frontend Action:** Update all MAC address displays and inputs to use colon-separated format.

### 2. Config CRUD Operations Use Surrogate IDs

**Change:** Create, read, update, and delete operations now use auto-increment integer IDs instead of MAC addresses.

**Before:**
- `GET /api/configs/<mac>.json` - get config
- `PUT /api/configs/<mac>.json` - create/update config
- `DELETE /api/configs/<mac>.json` - delete config

**After:**
- `GET /api/configs` - list all configs (includes `id` field)
- `POST /api/configs` - create new config (returns `id`)
- `GET /api/configs/<id>` - get config by ID
- `PUT /api/configs/<id>` - update config by ID
- `DELETE /api/configs/<id>` - delete config by ID
- `GET /api/configs/<mac>.json` - raw config for ESP32 (unchanged, for device access only)

**Frontend Action:**
- Store and use `id` from list/create responses for subsequent operations
- Update delete and edit functions to use ID-based endpoints

### 3. Create Config Request Body

**Change:** Creating a config now requires `mac_address` as a top-level field in the request body.

**Before:**
```json
PUT /api/configs/aa-bb-cc-dd-ee-ff.json
{
  "deviceName": "Kitchen Sensor",
  "enableOTA": true
}
```

**After:**
```json
POST /api/configs
{
  "mac_address": "aa:bb:cc:dd:ee:ff",
  "content": {
    "deviceName": "Kitchen Sensor",
    "enableOTA": true
  }
}
```

**Frontend Action:** Update create config form/logic to:
1. Collect MAC address as a separate field
2. Wrap device configuration in a `content` object
3. Use POST method instead of PUT

### 4. Update Config Request Body

**Change:** Updating a config uses ID in the URL and only sends `content`.

**Before:**
```json
PUT /api/configs/aa-bb-cc-dd-ee-ff.json
{
  "deviceName": "Kitchen Sensor",
  "enableOTA": true
}
```

**After:**
```json
PUT /api/configs/123
{
  "content": {
    "deviceName": "Kitchen Sensor",
    "enableOTA": true
  }
}
```

**Frontend Action:** Update edit config form/logic to:
1. Use the config's `id` in the URL path
2. Wrap device configuration in a `content` object

### 5. Response Schema Changes

**Change:** All responses now include `id`, `created_at`, and `updated_at` fields.

**List Response:**
```json
{
  "configs": [
    {
      "id": 1,
      "mac_address": "aa:bb:cc:dd:ee:ff",
      "device_name": "Kitchen Sensor",
      "device_entity_id": "sensor.kitchen",
      "enable_ota": true,
      "created_at": "2026-01-21T10:00:00Z",
      "updated_at": "2026-01-21T10:00:00Z"
    }
  ],
  "count": 1
}
```

**Single Config Response:**
```json
{
  "id": 1,
  "mac_address": "aa:bb:cc:dd:ee:ff",
  "device_name": "Kitchen Sensor",
  "device_entity_id": "sensor.kitchen",
  "enable_ota": true,
  "content": { ... },
  "created_at": "2026-01-21T10:00:00Z",
  "updated_at": "2026-01-21T10:00:00Z"
}
```

**Frontend Action:** Update TypeScript interfaces/types to include new fields.

## Unchanged Endpoints

The following endpoint remains unchanged for ESP32 device access:

- `GET /api/configs/<mac>.json` - Returns raw JSON configuration
  - Accepts both colon and dash-separated MACs for backward compatibility
  - Normalizes to lowercase automatically

## Migration Checklist

- [ ] Update MAC address display format to use colons
- [ ] Update config list to store and display `id` field
- [ ] Update create config to use `POST /api/configs` with `mac_address` and `content` fields
- [ ] Update edit config to use `PUT /api/configs/<id>` with `content` field
- [ ] Update delete config to use `DELETE /api/configs/<id>`
- [ ] Update TypeScript types for new response schemas
- [ ] Test all CRUD operations with new API format
