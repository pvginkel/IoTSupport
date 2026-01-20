# Change Brief: ESP32 Device Endpoints

## Summary

Add endpoints to serve raw config and asset files directly to ESP32 devices, replacing the current NGINX static file serving. This allows the backend to fully manage device file access while preserving the existing management API.

## Background

Currently, ESP32 devices fetch their configuration and firmware assets via NGINX static file serving:
- `/esp32/config/<mac-address>.json` - raw JSON config files
- `/assets/<filename>` - firmware binaries

The user wants to move this serving into the Flask backend so that:
1. All file access goes through the backend (single point of control)
2. NGINX can simply proxy these URLs to the backend via rewrite rules
3. The existing management API (`/api/configs/<mac>`) continues working

## Required Changes

### 1. Raw Config Endpoint

Add `GET /api/configs/<mac>.json` that:
- Returns the raw JSON configuration content (not wrapped in a response schema)
- The `.json` extension triggers raw mode vs. the existing wrapped response
- Returns HTTP 404 if config doesn't exist
- Includes `Cache-Control: no-cache` header
- Unauthenticated (trusted network)

### 2. Asset Serving Endpoint

Add `GET /api/assets/<filename>` that:
- Serves raw firmware binary files from `ASSETS_DIR`
- Returns HTTP 404 if asset doesn't exist
- Includes `Cache-Control: no-cache` header
- Uses `application/octet-stream` MIME type for firmware files
- Unauthenticated (trusted network)

### 3. Preserve Existing Behavior

- `GET /api/configs/<mac>` must continue returning the wrapped JSON response with metadata
- `POST /api/assets` must continue handling asset uploads

## URL Routing (NGINX responsibility)

The legacy device URLs will be rewritten by NGINX:
- `/esp32/config/<mac>.json` → `/api/configs/<mac>.json`
- `/assets/<filename>` → `/api/assets/<filename>`

This is out of scope for the backend implementation.
