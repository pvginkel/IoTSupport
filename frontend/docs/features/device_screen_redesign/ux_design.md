# Device Screen Redesign — UX Design

## Problem Statement

The device edit screen has grown organically and now stacks six unrelated
concerns into a single long scroll:

1. Device Key (read-only identifier)
2. Keycloak Client Status (security / ops)
3. Device Model selector
4. JSON Configuration Editor (300 px Monaco)
5. Device Logs Viewer (480 px terminal)
6. Core Dumps Table

That is 1 300+ px of content mixing **configuration**, **operational status**,
**live diagnostics**, and **crash analysis** into one page. A user editing
config has to scroll past Keycloak status; a user tailing logs has to scroll
past the editor. Every task competes for attention and none of them get the
space they need.

---

## Design Principles

| Principle | Rationale |
|-----------|-----------|
| **One intent per view** | Each tab answers a single question: "How is this device configured?", "What is it doing right now?", "Has it crashed?" |
| **Identity always visible** | Device key, name, model, and health indicators belong in the header so the user never loses context. |
| **Actions near their data** | Save/Cancel appear only on the Configuration tab; Download appears on Core Dumps. No orphaned buttons. |
| **Progressive disclosure** | Rare operations (provisioning) and secondary details (Keycloak sync) are available but not prominent. |
| **Maximise space for content** | Logs and parsed core-dump output benefit from as much vertical space as the viewport allows. |

---

## Proposed Layout

### Header (sticky, always visible)

The header consolidates identity and at-a-glance status.

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back    Edit Device: living-room-sensor                  │
│                                                             │
│  Device Key: d-a1b2c3f4      Model: ESP32-S3 (esp32s3)     │
│  Rotation: [OK]              OTA: Enabled                   │
│                                                             │
│  [ Configuration ]  [ Logs ]  [ Core Dumps (3) ]            │
└─────────────────────────────────────────────────────────────┘
```

**Details:**

- **Title row** — back link + heading ("Edit Device: {name || entityId || key}").
- **Identity row** — device key (mono) and model name + code. These are
  read-only identifiers that tell the user *which* device they are looking at.
  On the New / Duplicate flows this row is hidden or replaced by the model
  selector.
- **Status badges** — rotation state (colour-coded: green/yellow/blue/red) and
  OTA enabled/disabled. Pulled up from the list-only table columns so they are
  visible on the detail screen too.
- **Tabs** — sit at the bottom of the header. The Core Dumps tab shows a count
  badge when dumps exist.

### Tab 1 — Configuration (default)

The primary editing workflow. Focused on changing what the device does.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Keycloak Client                                            │
│  ● Connected: d-a1b2c3f4-client            [↻ Sync]        │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Configuration (JSON)                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  {                                                  │    │
│  │    "deviceName": "Living Room Sensor",              │    │
│  │    "deviceEntityId": "sensor.living_room",          │    │
│  │    "enableOTA": true                                │    │
│  │  }                                                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│                      [Cancel]  [Duplicate]  [Save]          │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Provisioning                                               │
│  Write credentials to the physical device via USB.          │
│  [Provision Device →]                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Rationale:**

- Keycloak status is security configuration — it stays here but is compact.
- The Monaco editor can grow taller now that it is not squeezed between five
  other sections.
- Save / Cancel / Duplicate are contextual to this tab; they disappear when
  the user switches to Logs or Core Dumps.
- Provisioning moves to the bottom as a secondary, rarely-used action with a
  short explanation. It opens the same modal it does today.

### Tab 2 — Logs

Full-height, immersive log viewing.

```
┌─────────────────────────────────────────────────────────────┐
│                                              [✓ Live]       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  12:03:01.234  WiFi connected                       │    │
│  │  12:03:01.456  MQTT broker connected                │    │
│  │  12:03:02.100  Sensor reading: 22.4°C               │    │
│  │  12:03:05.200  Sensor reading: 22.5°C               │    │
│  │  12:03:08.300  Sensor reading: 22.4°C               │    │
│  │                                                     │    │
│  │                                                     │    │
│  │                                                     │    │
│  │                                                     │    │
│  │                                                     │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Rationale:**

- The log viewer gets the **full content area** (`calc(100vh - header)`)
  instead of a fixed 480 px box buried below other content. Tailing logs is a
  sit-and-watch activity — give it room.
- The "Live Updates" toggle stays top-right.
- If the device has no entity ID, show a simple empty state:
  *"No entity ID configured — logs require an entity ID."*

### Tab 3 — Core Dumps

Crash diagnostics in one dedicated place.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ┌──────────────┬──────────┬────────┬────────┬──────────┐   │
│  │ Uploaded      │ Firmware │ Size   │ Status │          │   │
│  ├──────────────┼──────────┼────────┼────────┼──────────┤   │
│  │ Feb 12, 2026 │ v1.4.2   │ 256 KB │ Parsed │ [⬇] [✕] │   │
│  │ Feb 10, 2026 │ v1.4.1   │ 128 KB │ Parsed │ [⬇] [✕] │   │
│  │ Jan 28, 2026 │ v1.3.0   │ 256 KB │ Failed │ [⬇] [✕] │   │
│  └──────────────┴──────────┴────────┴────────┴──────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Rationale:**

- Core dumps are no longer an afterthought at the very bottom of a long scroll.
- The tab label includes a count badge ("Core Dumps (3)") so the user can see
  at a glance whether there are crashes to investigate without switching tabs.

---

## Core Dump Detail — Inline Expansion

### Current behaviour

Clicking a core dump row navigates to
`/devices/$deviceId/coredumps/$coredumpId` — a completely separate page with
its own header and back button. For what is essentially "show me the parsed
output" this is heavyweight navigation that breaks the user's context.

### Proposed behaviour — accordion expansion

Clicking a row expands it in-place to reveal metadata and the parsed output.

```
┌──────────────┬──────────┬────────┬────────┬──────────┐
│ Uploaded      │ Firmware │ Size   │ Status │          │
├──────────────┼──────────┼────────┼────────┼──────────┤
│▼ Feb 12, 2026│ v1.4.2   │ 256 KB │ Parsed │ [⬇] [✕] │
├──────────────┴──────────┴────────┴────────┴──────────┤
│                                                       │
│  Filename: coredump-20260212-120301.elf               │
│  Chip: esp32s3         Parsed At: Feb 12 12:05        │
│                                                       │
│  Parsed Output                                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │  Guru Meditation Error: Core 0 panic'ed         │  │
│  │  (LoadProhibited). Exception was unhandled.      │  │
│  │  Core  0 register dump:                          │  │
│  │  PC  : 0x400d1234  PS  : 0x00060e30             │  │
│  │  ...                                             │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
├──────────────┬──────────┬────────┬────────┬──────────┤
│ Feb 10, 2026 │ v1.4.1   │ 128 KB │ Parsed │ [⬇] [✕] │
│ Jan 28, 2026 │ v1.3.0   │ 256 KB │ Failed │ [⬇] [✕] │
└──────────────┴──────────┴────────┴────────┴──────────┘
```

**Details:**

- Clicking a row toggles the expansion. Only one row is expanded at a time
  (accordion). Clicking another row collapses the current one and opens the new
  one.
- The expanded area shows:
  - **Metadata grid** — filename, chip, parsed-at timestamp (compact, two
    columns).
  - **Parsed output** — Monaco editor (read-only, plaintext, vs-dark). Height
    adapts to content with a sensible max (e.g. 500 px, scrollable).
  - If no parsed output is available: *"Parsed output not available."*
- The download and delete buttons remain on the table row itself — no need to
  duplicate them in the expanded area.
- **Deep-link support** — keep the route
  `/devices/$deviceId/coredumps/$coredumpId`. When loaded directly,
  auto-select the Core Dumps tab, expand the matching row, and scroll it into
  view.

### Alternative: slide-over panel

If parsed output is typically long and benefits from full width, a right-side
slide-over drawer is a viable alternative. The table stays visible on the left;
the detail fills the right panel. This works better if users need to compare
dumps side-by-side. The accordion approach is recommended as the default
because it keeps the UI simpler and avoids a second navigation layer.

---

## Before / After Summary

| Concern | Before | After |
|---------|--------|-------|
| Device identity | Scattered (key in body, name in title only) | Consolidated in sticky header |
| Rotation / OTA status | Only visible on the list page | Badge in detail header |
| Keycloak status | Prominent section above editor | Compact row in Configuration tab |
| JSON configuration | Squeezed between Keycloak and logs | Full Configuration tab, more vertical space |
| Save / Cancel | Always visible in header, even on non-edit views | Contextual to Configuration tab only |
| Provisioning | Header button competing with Save | Bottom of Configuration tab (rare action) |
| Device logs | Fixed 480 px box at the bottom of a long scroll | Full-viewport dedicated Logs tab |
| Core dumps table | Afterthought at the very bottom | Dedicated tab with count badge |
| Core dump detail | Separate page with full navigation | Inline accordion expansion |

---

## New / Duplicate Flows

The New and Duplicate flows do not have logs or core dumps. On these flows:

- The header shows only the title ("New Device" / "Duplicate Device: {key}")
  and the model selector (since it is editable in these modes).
- Tabs are **hidden** — only the Configuration content is shown, since the
  other tabs have no content yet.
- Once the device is saved and an ID exists, the full tabbed layout appears.

---

## Routing

| Route | Behaviour |
|-------|-----------|
| `/devices/$deviceId` | Device detail, Configuration tab selected |
| `/devices/$deviceId/logs` | Device detail, Logs tab selected |
| `/devices/$deviceId/coredumps` | Device detail, Core Dumps tab selected |
| `/devices/$deviceId/coredumps/$coredumpId` | Core Dumps tab, matching row auto-expanded |
| `/devices/new` | New device flow (no tabs) |
| `/devices/$deviceId/duplicate` | Duplicate device flow (no tabs) |

Switching tabs updates the URL so that browser back/forward and deep links
work naturally. TanStack Router nested routes handle this without additional
state management.
