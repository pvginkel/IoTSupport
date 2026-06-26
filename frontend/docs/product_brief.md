# IoT Support Frontend - Product Brief

## Project Overview

IoT Support is a web application for managing configuration files for ESP32-based IoT devices in a homelab environment. It provides a visual interface to list, create, edit, and delete device configurations that were previously managed through manual file editing and Helm chart deployments.

The application connects to an existing REST API backend that stores configurations as JSON files on CephFS. Changes made through the UI are immediately available to devices without redeployment.

## Target Audience

- Homelab administrators managing ESP32 IoT devices
- Users in trusted network environments (no authentication required)
- Expected scale: up to 200 device configurations

## Primary Benefits and Features

### Core Functionality

1. **Device Configuration List** - View all device configurations with sortable columns showing MAC address, device name, entity ID, and OTA status. Sorting preferences persist in local storage.

2. **Configuration Editor** - Full-featured Monaco JSON editor for editing device configurations with:
   - Syntax highlighting and code folding
   - Editable MAC address field
   - Save, Cancel, and Duplicate actions
   - Unsaved changes warning on navigation
   - Backend validation error display via toast notifications

3. **Create New Device** - Start with a minimal template (`deviceName`, `deviceEntityId`, `enableOTA: false`) and configure from scratch.

4. **Duplicate Device** - Copy an existing configuration to quickly set up similar devices with a new MAC address.

5. **Delete Device** - Remove configurations with confirmation dialog.

### User Experience

- Single sidebar navigation with "Device Configs" entry
- Dark mode interface
- Skeleton loaders during data fetching
- Empty state guidance when no devices exist

## Technology and Architecture

### Stack

- **React 19** with TypeScript (strict mode)
- **TanStack Router** for file-based routing with type-safe navigation
- **TanStack Query** for server state management and caching
- **Monaco Editor** for JSON editing
- **Tailwind CSS 4** with dark mode
- **Radix UI** for accessible component primitives
- **Vite** for development and builds
- **openapi-typescript** for generated API types and hooks
- **Playwright** for end-to-end testing

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     React Application                        │
├─────────────────────────────────────────────────────────────┤
│  Routes (TanStack Router)                                   │
│  - /devices              → Device list                      │
│  - /devices/new          → New device editor                │
│  - /devices/:mac         → Edit device                      │
│  - /devices/:mac/duplicate → Duplicate device               │
├─────────────────────────────────────────────────────────────┤
│  Components                                                  │
│  - Layout with sidebar navigation                           │
│  - DeviceList with sortable table                           │
│  - DeviceEditor with Monaco + MAC input                     │
│  - ConfirmDialog for delete actions                         │
├─────────────────────────────────────────────────────────────┤
│  Hooks & API Layer                                          │
│  - Generated API client from OpenAPI spec                   │
│  - Custom hooks wrapping queries/mutations                  │
│  - Toast notifications for errors                           │
├─────────────────────────────────────────────────────────────┤
│  Backend API (localhost:3201)                               │
│  - GET/PUT/DELETE /api/configs/:mac                         │
│  - Proxied through Vite in development                      │
└─────────────────────────────────────────────────────────────┘
```

### URL Structure

| Route | Purpose |
|-------|---------|
| `/` | Redirects to `/devices` |
| `/devices` | List all device configurations |
| `/devices/new` | Create new device configuration |
| `/devices/:macAddress` | Edit existing device configuration |
| `/devices/:macAddress/duplicate` | Create new device from existing config |

### Development Setup

- Frontend runs on port **3200**
- Backend API proxied from port **3201**
- API types generated from backend OpenAPI spec at `/api/docs`
