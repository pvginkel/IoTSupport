# Firmware flashing

How a firmware build reaches IoT Support with everything a full flash needs, how a version is
stored, and what Flash device writes to a device from the browser. The upload is part of the
`/pipeline/*` contract other repositories' CI runs ([change-discipline.md](change-discipline.md)),
which is why this design lives at the root.

## The upload

Each firmware repository's `scripts/upload.sh` is a stub that runs the script IoT Support serves,
`GET /api/pipeline/upload.sh` (`upload.ps1` is its PowerShell twin), from the project root after
`idf.py build`. Given no arguments, as the stub gives none, the served script finds the build
through `build/project_description.json`; it packs a ZIP and posts it to
`POST /api/pipeline/models/<model>/firmware`. Its members are named after their files:

- the five artifacts every version has: `<model>.bin`, `<model>.elf`, `<model>.map`, `sdkconfig`
  and `version.json`;
- the build's flash images: `flasher_args.json`, which ESP-IDF writes to the build directory, and
  every other file its `flash_files` lists for `idf.py flash` — the bootloader, the partition
  table, the otadata. The app among them is the `<model>.bin` already packed.

The flash images go in all or none. When the build directory has no `flasher_args.json`, a file it
lists is missing, two files would share a member name, or it does not flash `<model>.bin`, the
script prints `Note: packaging without flash images (…)` and uploads the five artifacts alone.

The upload — the same `FirmwareService.save_firmware` behind the pipeline route and the admin
firmware upload — accepts a ZIP of the five artifacts alone, which stores a version without flash
images. A ZIP that carries `flasher_args.json` is validated against it before anything is stored,
and refused with `Invalid firmware ZIP: …` when:

- `flasher_args.json` is not JSON or lacks `flash_settings`, `flash_files` keyed by `0x…` offsets,
  or `extra_esptool_args.chip`;
- it does not flash `<model>.bin`, so the app a flash writes is always the one `/iot/firmware`
  serves;
- a file it lists is missing, a member is one it does not list, or two members share a name;
- an image is empty, or two images overlap.

Every offset is the build's own: an app the build places at `0x20000` rather than the usual
`0x10000` is written there.

## Storage

A version lives in S3 under `firmware/{model}/{version}/`: `firmware.bin` (the app),
`firmware.elf`, `firmware.map`, `sdkconfig` and `version.json`. A version uploaded with its flash
images also holds each image but the app as `flash/<offset>.bin` (`flash/0x8000.bin`), and
`flash.json`, its `FlashManifest`:

- `chip` — the chip the build targets, as ESP-IDF names it (`esp32s3`);
- `flash_mode`, `flash_size` and `flash_freq` — the build's settings, verbatim;
- `images` — every image in ascending offset, each with its `offset`, its `file` as the build
  names it, its `artifact` under the version's prefix (`firmware.bin` for the app) and its `size`.

The database tracks versions only; the flash set is a version artifact like `version.json`. A
version is flashable exactly when its `flash.json` exists. Validation runs before any S3 call, so a
refused upload leaves what is stored as it was. An accepted one deletes the version's `flash.json`
and `flash/` before it uploads the artifacts and writes `flash.json` last, so a version is
flashable only while every image its manifest lists is in place. Retention pruning and model
deletion delete whole prefixes, the flash images with them.

A version stored before the upload carried flash images has none. It is not flashed in part: Flash
device says so, and the model becomes flashable with its next build.

## Flash device

`GET /api/devices/{device_id}/flash-images` serves what a flash writes for the device's model's
current firmware version, the one `/iot/firmware` serves. It answers 200 with a `status`:

| `status` | `firmware_version` | `flash` |
|---|---|---|
| `flashable` | the current version | the build's `chip` and flash settings, and every image with its `offset`, `file`, `size` and base64 `data` |
| `no_flash_images` | the current version, stored without flash images | null |
| `no_firmware` | null: the model has no firmware | null |

It answers 404 for an unknown device and 400 when an image the manifest lists cannot be read from
S3. Every image comes from the one version's prefix, so a flash never mixes two versions.

In the UI, Flash Device sits beside Provision Device on the device editor's Configuration tab. Its
modal fetches the images each time it opens, never from cache, since the response carries the
whole app. It names the firmware version and lists each image with its offset and size; for the
other two statuses it says why there is nothing to write and offers no Connect. Connect asks the
browser for the device's serial port (Web Serial, in a desktop Chromium browser) and, through
esptool-js:

1. connects through the chip's ROM loader at 115200 baud and identifies the chip, refusing one the
   build does not target before anything is written;
2. writes every image at its offset at 460800 baud, `idf.py flash`'s rate, with no erase-all, so
   NVS and the device's provisioning stay as they are; the flash settings are kept as the build
   wrote them into its bootloader's header;
3. checks each image against the MD5 the chip computes over what it wrote, and on a failure names
   the image;
4. hard-resets the device — RTS holds EN low, then releases it — so it boots the new firmware.

Closing the modal mid-flash asks first, since a cancelled flash can leave the device without
bootable firmware. Provision Device stays the separate step after it, for a device that has no
credentials yet ([device provisioning](../backend/docs/device_provisioning_design.md)). Flash
device burns no eFuse: the board-revision burn of
[ADR 0001](../backend/docs/decisions/0001-hardware-revision-strategy.md) stays outside it.

## How it is tested

No suite can flash hardware, so the seams stand in for what a test cannot reach and nothing else:

- `TestPipelineUploadScriptRun` (`backend/tests/api/test_pipeline.py`) runs the served `upload.sh`
  under `/bin/sh` on an ESP-IDF-shaped build directory, with stand-ins only for `zip` and `curl`,
  once on the system's tools and once without jq, and posts the ZIP it packed to the real upload.
- `POST /api/testing/device-models/{model_id}/firmware` seeds a model's current version through
  the real upload, flashable or not and for any chip (`DeviceModelsFactory.seedFirmware`).
- The Playwright suite drives the flash against the esptool-js mock Vite aliases in test mode.
  `installFakeEspDevice(page, chip?)` before the page loads hands out a fake serial port and chip,
  and `readFakeEspDevice(page)` reads back every write and reset signal
  (`frontend/tests/support/mocks/fake-esp-device.ts`). Every request still goes to the real
  backend.
