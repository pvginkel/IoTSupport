# Phase B: Feature Implementation - Change Brief

## Overview

Implement the complete device configuration management features for the IoT Support frontend. This phase builds on the Phase A foundation (app shell, routing, Playwright infrastructure) to deliver the full user-facing functionality.

## Functional Requirements

### Device List View (`/devices`)

1. Display all device configurations in a sortable table with columns:
   - MAC Address
   - Device Name
   - Entity ID
   - OTA Status (check icon for true, cross icon for false, empty for null)

2. Sorting:
   - All columns are sortable
   - Click column header to toggle sort direction (asc/desc)
   - Persist sort preferences to localStorage (`iot-support-device-sort`)

3. Loading States:
   - Show skeleton loader during initial fetch
   - Show empty state with "No devices configured" message and create button when list is empty

4. Actions:
   - "New Device" button in header navigates to `/devices/new`
   - Edit button on each row navigates to `/devices/:macAddress`
   - Delete button on each row triggers delete flow

### Device Editor

5. New Device (`/devices/new`):
   - Empty MAC address input field
   - Monaco JSON editor pre-filled with template: `{"deviceName": "", "deviceEntityId": "", "enableOTA": false}`
   - Save and Cancel buttons (no Duplicate button)

6. Edit Device (`/devices/:macAddress`):
   - MAC address input field pre-filled (editable for rename)
   - Monaco JSON editor with device's current configuration loaded
   - Save, Cancel, and Duplicate buttons

7. Duplicate Device (`/devices/:macAddress/duplicate`):
   - Empty MAC address input field
   - Monaco JSON editor with source device's configuration copied
   - Save and Cancel buttons (no Duplicate button)

8. Monaco Editor Configuration:
   - Language: JSON
   - Theme: vs-dark
   - Minimap: disabled
   - Code folding: enabled
   - Tab size: 2

9. Save Behavior:
   - Validate and save via PUT `/api/configs/:macAddress`
   - If MAC address changed during edit: save to new MAC, delete old MAC
   - On success: navigate to list, show success toast
   - On error: show error toast with backend validation message

10. Unsaved Changes:
    - Track dirty state (MAC changed or JSON changed from original)
    - Show browser beforeunload warning
    - Show confirmation dialog when navigating away with unsaved changes

### Delete Flow

11. Delete Confirmation:
    - Show styled confirmation dialog (not browser confirm)
    - Dialog shows device MAC address being deleted
    - Cancel button closes dialog without action
    - Confirm button deletes via DELETE `/api/configs/:macAddress`

12. Delete Result:
    - On success: refresh list, show success toast
    - On error: show error toast

### UI Components

13. Toast Notifications:
    - Support success, error, and info variants
    - Auto-dismiss after configurable duration
    - Dark mode styling

14. Confirmation Dialog:
    - Radix UI Dialog primitive
    - Dark mode styling
    - Destructive styling for delete actions

### API Integration

15. Use generated API hooks from openapi-typescript/openapi-fetch
16. Custom hooks wrap generated hooks and handle error display
17. All API calls go through Vite proxy (`/api/*`)

### Testing

18. Playwright tests for all user flows:
    - Device list display and sorting
    - Create new device
    - Edit existing device
    - Rename device (change MAC address)
    - Duplicate device
    - Delete device with confirmation
    - Unsaved changes warning
    - Error handling (backend validation errors)

19. API factories for test data setup/teardown
20. Page objects for test maintainability

## Backend API Reference

- `GET /api/configs` - List all configurations
- `GET /api/configs/:mac_address` - Get single configuration
- `PUT /api/configs/:mac_address` - Create or update configuration
- `DELETE /api/configs/:mac_address` - Delete configuration

## Design Notes

- Match ElectronicsInventory patterns for hooks, components, and testing
- Dark mode only (no light mode toggle)
- App name: "IoT Support"
