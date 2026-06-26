# Change Brief: Device Active Flag

## Summary

The backend has added an `active` boolean field to devices. This field indicates "whether device participates in automatic fleet rotation." The frontend needs to surface this field in three places:

1. **Device List Table** — Add a read-only "Active" column as the last column before the "Actions" column. Display it as a slider/checkbox visual (read-only, not interactive) following the existing pattern for status indicators.

2. **Device Configuration Screen (Edit)** — Add an "Active" toggle/switch above the JSON configuration editor. This should be an interactive control that is part of the device update payload (which already requires `active` alongside `config`).

3. **New Device Form** — Add the same "Active" toggle/switch, defaulting to `true`.

4. **Rotation Dashboard** — No changes needed. The dashboard already receives an `inactive` array from the API and already ignores it (only renders `healthy`, `warning`, `critical`). Inactive devices are decommissioned or dev devices and should not appear on the rotation dashboard at all.

## Technical Context

- The `active` field is already present in the OpenAPI spec and generated TypeScript types across all device schemas (list summary, detail response, dashboard, update request).
- The frontend domain models (`DeviceSummary`, `Device`) in `src/hooks/use-devices.ts` do not yet map this field.
- Transform functions (`transformDeviceSummary`, `transformDeviceResponse`) need to include the field.
- The `DeviceUpdateSchema` requires `active` (boolean) alongside `config` (string).
