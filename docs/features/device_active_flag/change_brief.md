# Change Brief: Device Active Flag

Add an `active` boolean field to the Device model (default `True`) that controls whether a device participates in automatic credential rotation and how it appears on the rotation dashboard.

## Behavior

- **Automatic rotation (CRON job):** Inactive devices are skipped when queuing devices for rotation.
- **Fleet-wide manual trigger (`POST /rotation/trigger`):** Inactive devices are skipped.
- **Single-device manual rotation (`POST /devices/<id>/rotate`):** Still works for inactive devices.
- **Authentication, firmware, config, provisioning:** All unaffected. Inactive devices can still authenticate and use all device-facing endpoints.
- **In-flight rotation:** Deactivating a device mid-rotation (QUEUED/PENDING) does not cancel the in-flight rotation. The flag only affects future automatic selection.
- **Reactivation:** Device naturally rejoins the next scheduled rotation cycle. No special handling.

## Dashboard & Status

- **Rotation dashboard (`GET /rotation/dashboard`):** Inactive devices are shown in a new fourth group called "inactive" (separate from healthy/warning/critical). They are excluded from the healthy/warning/critical groups.
- **Rotation status (`GET /rotation/status`):** Include an `inactive` count alongside the existing state counts.

## API Surface

- The `active` field is a regular field on the Device model, updated via `PATCH /devices/<id>`.
- The field is surfaced in all GET device endpoints (list and detail).
- No new endpoints. No filter parameters on the device list.
