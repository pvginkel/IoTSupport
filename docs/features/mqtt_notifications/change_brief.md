# Change Brief: MQTT Notifications for Config and Asset Changes

## Summary

Implement MQTT publishing to notify IoT devices when configuration files or firmware assets are updated. Devices subscribe to MQTT topics and pull updated files via HTTP when notified.

## Functional Requirements

1. **Config Save Notifications**: When a config file is saved (created or updated), publish a notification to `iotsupport/updates/configs` with payload `{"filename": "<mac-address>.json"}`.

2. **Asset Upload Notifications**: When a firmware asset is uploaded, publish a notification to `iotsupport/updates/assets` with payload `{"filename": "<asset-filename>"}`.

3. **No Delete Notifications**: Config deletions should NOT publish MQTT notifications (devices would restart unnecessarily, and deletes are likely errors that may be corrected quickly).

## Technical Requirements

- **MQTT Broker**: Mosquitto MQTT 5 server
- **Environment Variables**: `MQTT_URL`, `MQTT_USERNAME`, `MQTT_PASSWORD`
- **Connection**: Persistent connection as singleton service, reconnects on disconnect
- **Optional**: If MQTT is not configured (no `MQTT_URL`), skip publishing silently
- **QoS Level**: QoS 1 (at least once delivery)
- **Retain Flag**: Do not retain messages
- **Topic Format**: No leading slash (e.g., `iotsupport/updates/configs`)
- **Failure Handling**: Fire-and-forget - if MQTT publish fails, log the error but let the API operation succeed
