# IoT Support Frontend - Product Brief

## Project Overview

IoT Support manages a homelab's fleet of ESP32 devices. Its frontend is a React SPA over the IoT Support
backend's REST API and its SSE stream, and serves the person who runs the fleet:

- defining the **device models** — the hardware types, each with an optional JSON Schema for its
  devices' configuration and the firmware version its devices run;
- creating and editing **devices** and their JSON configuration;
- bringing a board up over USB from the browser: **Flash device** writes its model's firmware,
  **Provision device** writes its credentials;
- reading a device's **logs** live and its **core dumps**;
- watching and driving the automatic **rotation** of each device's Keycloak OAuth2 credentials.

The domain model — devices, models, firmware and credential rotation — is the backend's, described in
its [product brief](../../backend/docs/product_brief.md). How a firmware build reaches IoT Support and
what Flash device writes is in [Firmware flashing](../../docs/firmware-flashing.md).

## Target Audience

- Homelab administrators managing a fleet of ESP32 IoT devices, up to about 200 devices.
- Users sign in through the backend's OIDC login, which leaves the browser a session cookie. A user
  with none of the app's roles sees a not-authorized screen.

## Screens and Workflows

The sidebar has three entries: **Device Models**, **Devices** and **Rotation Dashboard**.

### Device Models

- **List** – code, name, device count, whether a configuration schema is defined, and the current
  firmware version. Columns sort. A model that still has devices cannot be deleted.
- **Editor** – model code (fixed once created), name, and an optional configuration JSON Schema in a
  Monaco editor.
- Firmware is not uploaded here: each firmware repository's CI uploads its builds through the
  `/pipeline/*` contract ([Firmware flashing → The upload](../../docs/firmware-flashing.md#the-upload)).
  The UI shows the version a model's devices get.

### Devices

- **List** – device key, name, model, entity ID, rotation state, OTA status, last core dump and
  whether the device is active. Columns sort, and the sort persists in local storage. Delete asks
  for confirmation.
- **New device** – pick a model, then write the configuration JSON in Monaco, validated against the
  model's schema. A new device is always active.
- **Duplicate** – a new device prefilled with an existing one's model and configuration.

A device's page has a header (key, model, rotation state, OTA status) and three tabs; it reopens on
the tab last used.

- **Configuration** – the device's Keycloak client status (with resync, or recreate when the client
  is missing), whether it takes part in automatic fleet rotation, and its configuration JSON,
  validated against the model's schema. Unsaved changes ask before they are discarded. Its actions
  include **Flash device** and **Provision device**.
- **Logs** – a terminal-style view of the device's log, live over the SSE stream, with older entries
  loaded on scrolling up, and a download of the last 100 to 10,000 lines.
- **Core dumps** – the device's uploaded core dumps: firmware, size and parse status, the parsed
  output on expanding a row, a download and a delete. An expanded row has its own URL.

### Bringing up a board over USB

Both actions run in the browser over Web Serial through esptool-js, so they need a desktop Chromium
browser and the board on the user's USB port.

1. **Flash device** writes the model's current firmware — every image of the build at its offset —
   checks each against the chip's MD5 and resets the device. It refuses a chip the build does not
   target, and NVS is left alone, so a provisioned device keeps its credentials
   ([Firmware flashing → Flash device](../../docs/firmware-flashing.md#flash-device)).
2. **Provision device** writes the device's credentials: it finds the NVS partition in the device's
   partition table and writes the NVS image the backend generates for it
   ([device provisioning](../../backend/docs/device_provisioning_design.md)).

A new board is flashed first and provisioned after; an already provisioned one is only flashed.

### Rotation Dashboard

- A healthy / warning / critical summary, the last completed and next scheduled rotation, and the
  device currently pending.
- The devices by state, with each one's secret age and last rotation.
- **Trigger Fleet Rotation** queues every device in the OK state; **Rotate device** starts one
  device's rotation. Both
  ask for confirmation. The dashboard updates from the SSE stream, not by polling.

### App Shell

- A notification bar offers a reload when a new version of the app is deployed.
- A stage indicator shows the environment, except in production.
- Errors surface as toasts.

## Technology and Architecture

### Stack

- **React 19** with TypeScript (strict mode)
- **TanStack Router** for file-based routing with type-safe navigation
- **TanStack Query** for server state, with mutations' errors surfaced as toasts
- **openapi-fetch** and **openapi-typescript** for the API client generated from the backend's
  OpenAPI spec
- **Monaco Editor** for configuration, schema and core-dump output
- **esptool-js** over Web Serial for Flash device and Provision device
- **Tailwind CSS 4**, dark mode following the system's preference, and **Radix UI** primitives
- **Vite** for development and builds
- **Playwright** for end-to-end testing

One SSE stream, `/api/sse/stream`, held by a shared web worker, carries the device logs, the
rotation updates and the new-version notice.

### URL Structure

| Route | Purpose |
|-------|---------|
| `/` | Redirects to `/devices` |
| `/devices` | Device list |
| `/devices/new` | New device |
| `/devices/:deviceId` | Opens the device's last-used tab |
| `/devices/:deviceId/edit` | Configuration tab |
| `/devices/:deviceId/logs` | Logs tab |
| `/devices/:deviceId/coredumps` | Core dumps tab |
| `/devices/:deviceId/coredumps/:coredumpId` | Core dumps tab with one dump expanded |
| `/devices/:deviceId/duplicate` | New device from an existing one |
| `/device-models` | Device model list |
| `/device-models/new` | New device model |
| `/device-models/:modelId` | Edit a device model |
| `/rotation` | Rotation dashboard |

### Development and Testing

- `scripts/dev.py` starts the dev stack: the frontend on port **3100**, which proxies `/api` — the
  SSE stream included — to the backend on port **3101**.
- The Playwright suite runs against a real backend per worker, seeded through API factories. The only
  stand-in is the fake USB device Flash device and Provision device connect to
  ([Factories & Fixtures](./contribute/testing/factories_and_fixtures.md)).
- [The contributor hub](./contribute/index.md) has the rest.
