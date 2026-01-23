# NVS Provisioning Change Brief

## Summary

Update the `/api/devices/{id}/provisioning` endpoint to return an NVS binary blob suitable for direct flashing to ESP32 devices via the browser using Web Serial API and esptool-js.

## Current Behavior

The endpoint returns a JSON file containing provisioning data (credentials, WiFi config, URLs) as a downloadable `.bin` file. The device firmware would need to parse this JSON.

## New Behavior

The endpoint returns a JSON response with:
- `partition`: The NVS partition name (always `"nvs"`)
- `data`: Base64-encoded NVS binary blob

The NVS blob contains the same provisioning data in ESP-IDF NVS format, which the device can read natively using `nvs_get_str()` etc.

## Provisioning Data

The following fields are included in the NVS blob. Key names match the `/iot/provisioning` JSON response (no prefix needed since they're in the `prov` namespace):

| NVS Key | Source | Description |
|---------|--------|-------------|
| `device_key` | device.key | 8-character device key |
| `client_id` | device.client_id | Keycloak client ID |
| `client_secret` | Keycloak | Client secret |
| `token_url` | config | OIDC token endpoint |
| `base_url` | config | Backend base URL |
| `mqtt_url` | config | MQTT broker URL (optional) |
| `wifi_ssid` | config | WiFi SSID (optional) |
| `wifi_password` | config | WiFi password (optional) |

## Frontend Impact

The frontend will use esptool-js to:
1. Fetch the provisioning data from this endpoint
2. Connect to ESP32 via Web Serial API
3. Read the partition table to find the `nvs` partition offset
4. Write the binary blob to that offset
5. Verify by reading back the written data

A separate plan will be created for the frontend implementation.
