# Asset Upload API Migration Plan

## Summary

This document outlines the steps required to migrate all projects from the legacy PHP endpoint (`/assetctl/upload.php`) to the new Flask API endpoint (`/api/assets`).

## API Changes

| Aspect | Old (PHP) | New (Flask) |
|--------|-----------|-------------|
| **Endpoint** | `/assetctl/upload.php` | `/api/assets` |
| **Method** | POST | POST |
| **Content-Type** | multipart/form-data | multipart/form-data |
| **Fields** | `file`, `timestamp`, `signature` | `file`, `timestamp`, `signature` (unchanged) |
| **Success Response** | `200 OK` | `200 {"filename": "...", "size": ..., "uploaded_at": "..."}` |
| **Error Response** | `400 Bad Request` | `400 {"error": "...", "detail": "..."}` |

The form data structure is **identical** - only the URL path changes.

## Affected Repositories

Based on a search of your Gitblit repositories, the following projects reference the old endpoint:

### IoT Device Projects (8 repositories)

| Repository | File | Current URL |
|------------|------|-------------|
| `pvginkel/CalendarDisplay.git` | `scripts/upload.sh` | `http://iotsupport.iotsupport.svc.cluster.local/assetctl/upload.php` |
| `pvginkel/InfraStatisticsDisplay.git` | `scripts/upload.sh` | `http://iotsupport.iotsupport.svc.cluster.local/assetctl/upload.php` |
| `pvginkel/PaperClock.git` | `scripts/upload.sh` | `http://iotsupport.iotsupport.svc.cluster.local/assetctl/upload.php` |
| `pvginkel/ThermostatDisplay.git` | `scripts/upload.sh` | `http://iotsupport.iotsupport.svc.cluster.local/assetctl/upload.php` |
| `pvginkel/Intercom.git` | `scripts/upload.sh` | Configurable host + `/assetctl/upload.php` |
| `pvginkel/SomfyRemote.git` | `scripts/upload.sh` | Configurable host + `/assetctl/upload.php` |
| `pvginkel/ThermostatProxy.git` | `scripts/upload.sh` | Configurable host + `/assetctl/upload.php` |
| `pvginkel/UnderfloorHeatingController.git` | `scripts/upload.sh` | Configurable host + `/assetctl/upload.php` |

### Test/Development Scripts (1 repository)

| Repository | File | Current URL |
|------------|------|-------------|
| `pvginkel/DockerImages.git` | `iotsupport/scripts/upload-test.sh` | `http://127.0.0.1/assetctl/upload.php` |

## Migration Steps

### Step 1: Update Simple Upload Scripts (4 repositories)

These scripts have hardcoded URLs. Change the curl target from:
```bash
http://iotsupport.iotsupport.svc.cluster.local/assetctl/upload.php
```
to:
```bash
http://iotsupport.iotsupport.svc.cluster.local/api/assets
```

**Repositories:**
- [ ] `pvginkel/CalendarDisplay.git` - `scripts/upload.sh:13`
- [ ] `pvginkel/InfraStatisticsDisplay.git` - `scripts/upload.sh:13`
- [ ] `pvginkel/PaperClock.git` - `scripts/upload.sh:13`
- [ ] `pvginkel/ThermostatDisplay.git` - `scripts/upload.sh:13`

### Step 2: Update Configurable Upload Scripts (4 repositories)

These scripts allow host override via `$3` argument. Change the path suffix from `/assetctl/upload.php` to `/api/assets`.

**Repositories:**
- [ ] `pvginkel/Intercom.git` - `scripts/upload.sh:14`
- [ ] `pvginkel/SomfyRemote.git` - `scripts/upload.sh:14`
- [ ] `pvginkel/ThermostatProxy.git` - `scripts/upload.sh:14`
- [ ] `pvginkel/UnderfloorHeatingController.git` - `scripts/upload.sh:14`

### Step 3: Update Test Script (1 repository)

Update the local test script in DockerImages:
- [ ] `pvginkel/DockerImages.git` - `iotsupport/scripts/upload-test.sh:17`

Change from `http://127.0.0.1/assetctl/upload.php` to `http://127.0.0.1/api/assets`

### Step 4: Deprecate Legacy PHP Endpoint

Once all projects are migrated:
- [ ] Remove `/assetctl/upload.php` from the iotsupport container
- [ ] Update any nginx/routing configuration that proxied to the PHP endpoint

## Example Migration

### Before (simple script pattern)
```bash
curl \
    --output - \
    -F "file=@$2" \
    -F "timestamp=$TIMESTAMP" \
    -F "signature=$SIGNATURE" \
    http://iotsupport.iotsupport.svc.cluster.local/assetctl/upload.php
```

### After
```bash
curl \
    --output - \
    -F "file=@$2" \
    -F "timestamp=$TIMESTAMP" \
    -F "signature=$SIGNATURE" \
    http://iotsupport.iotsupport.svc.cluster.local/api/assets
```

### Before (configurable host pattern)
```bash
HOST=${3:-iotsupport.iotsupport.svc.cluster.local}
curl \
    --output - \
    -F "file=@$2" \
    -F "timestamp=$TIMESTAMP" \
    -F "signature=$SIGNATURE" \
    http://$HOST/assetctl/upload.php
```

### After
```bash
HOST=${3:-iotsupport.iotsupport.svc.cluster.local}
curl \
    --output - \
    -F "file=@$2" \
    -F "timestamp=$TIMESTAMP" \
    -F "signature=$SIGNATURE" \
    http://$HOST/api/assets
```

## Validation

After updating each script, verify the upload works:

```bash
# Test with a sample file
./scripts/upload.sh /path/to/signing-key test-file.bin

# Expected output: JSON response with filename, size, uploaded_at
# {"filename": "test-file.bin", "size": 12345, "uploaded_at": "2026-01-13T..."}
```

## Rollback Strategy

If issues arise, the old PHP endpoint can remain active in parallel until all projects are confirmed working. No backwards compatibility shim is needed since:
1. The form data format is identical
2. Both endpoints can coexist during migration

## Notes

- The FCKeditor `upload.php` files found in `josegosschalk.nl`, `karelbesseling.nl`, `OurMarriage`, and `paul-jacobs.com` are **unrelated** - these are legacy web projects with their own file upload functionality.
- Some repositories have the upload script on multiple branches (e.g., Intercom has `main` and `reorganize-schemas`). Update all active branches.
