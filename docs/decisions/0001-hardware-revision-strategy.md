# ADR 0001 — Hardware revision strategy: separate DeviceModels, eFuse-anchored identity

- **Status:** Accepted
- **Date:** 2026-06-04
- **Context owner:** Pieter van Ginkel

## Context

A device type (e.g. `tempsensor`) has gained a second hardware version. In the
immediate case the only change is pin assignment, but **this is not guaranteed to
stay pin-only** — future revisions of this or other device types may diverge
further (different peripherals, sensors, flash layout, or config schema).

We needed to decide how the system distinguishes hardware revisions and how a
device ends up running firmware with the correct pin map.

### Relevant existing structure

- Firmware is selected purely by `DeviceModel.code` + `DeviceModel.firmware_version`
  (`app/services/firmware_service.py:123-145`). The model code is the **only**
  firmware-selection axis. Every device of a model receives that one firmware
  version.
- A `Device` carries an opaque, user-editable `config` JSON
  (`app/models/device.py:58`; fields extracted at
  `app/services/device_service.py:170-180`) and is delivered a set-once NVS
  provisioning blob (`app/services/device_service.py:498-507`,
  `app/api/iot.py:332-341`).
- There is no notion of hardware version / revision / variant anywhere in
  `app/models/`.
- Target platform is the ESP32-S3.
- Homelab scale: ≤200 devices, hand-flashed.

## Options considered

### A. One firmware that adapts at runtime, revision supplied as data

A single firmware binary contains pin tables for all revisions and selects one at
boot based on a `hardware_version` value delivered through provisioning. The value
belongs in **NVS** (not `config`): it must be readable before the network is up,
and it is an immutable physical fact, not user-editable device configuration.

- **Pro:** one firmware, one OTA channel, one `DeviceModel`.
- **Con:** runtime branching rots as revisions diverge beyond pins — starts as one
  `if (rev == 2)` and ends an `#ifdef` swamp. Only attractive if the delta stays
  pin-only forever, which we cannot assume.

### B. Separate `DeviceModel` per hardware revision (chosen)

Each hardware revision is its own `DeviceModel` (e.g. `tempsensor` /
`tempsensor_v2`) with its own firmware, pins compiled in. This is what "two
firmwares" actually means in our schema, because firmware is keyed per model.

- **Pro:** dead simple, no runtime branching, **no backend schema change or
  migration** — created through the existing DeviceModel CRUD. Scales cleanly as
  revisions diverge (separate firmwares is then the *correct* behavior, not a tax).
  Per-revision fleet visibility (v1 vs v2 counts) is a feature at our scale.
- **Con:** no parent-product grouping in the schema — mitigated by naming
  convention. Two OTA channels — but this is correct once the firmwares genuinely
  differ.

### ESP32-S3 self-identification (orthogonal, adopted as a guardrail)

The S3 can identify its own board revision:

- **eFuse `BLOCK_USR_DATA` (BLOCK3), 256 bits, OTP — preferred.** Burned at
  flash/manufacture time (`espefuse.py burn_block_data` or the `esp_efuse` API).
  Loaded by ROM, so readable *before flash is mounted* — earlier than NVS. Survives
  reflash; cannot be edited by mistake.
- **ADC + ID resistor** — cheap alternative, needs ADC init, doesn't survive a
  mis-populated resistor.
- **Strapping pins — avoided.** GPIO0/3/45/46 are already spoken for (boot mode,
  VDD_SPI voltage, ROM messaging) on the S3.

## Decision

1. **Model each hardware revision as a separate `DeviceModel`** with its own
   firmware and compiled-in pin map. No `hardware_version` column, no NVS field,
   no migration. Use a naming convention (`<code>` / `<code>_v2`) to keep
   revisions visibly related.
2. **Burn the board revision into eFuse `BLOCK_USR_DATA`** and have each firmware
   **assert at the top of boot that it is running on the board it was built for**,
   refusing to run on a mismatch rather than driving the wrong pin map into
   populated hardware.

The NVS provisioning blob is unchanged; it keeps doing exactly what it does today.
Reporting the eFuse revision back as telemetry is an optional nice-to-have, not
load-bearing.

## Consequences

- A pin-map mismatch is potentially **destructive** (an output driven into a pin
  wired as an input/peripheral). The human "pick the right firmware/board" step
  exists under any option; the eFuse boot-time assert turns that failure mode from
  *unlikely* into *impossible* — a mismatched flash refuses to run.
- Backend impact is essentially nil: a second `DeviceModel` row and a firmware
  upload through existing endpoints. No schema, migration, or service changes.
- Firmware gains a small per-revision build matrix and a boot-time eFuse check.
- When a third revision appears, revisit whether the divergence is still small
  enough that separate models remain the right call (it should — divergence makes
  separation *more* correct, not less).

## Notes for the future

The load-bearing assumption that flipped this decision is **"not pin-only
forever."** If a future revision is provably a trivial, permanent pin-only tweak
*and* we want to avoid a new model, option A (single firmware, revision in NVS)
remains a valid fallback for that specific case — but the default is separate
models.
