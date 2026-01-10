# Change Brief: Asset Upload API

## Summary

Migrate the signed asset upload functionality from the legacy PHP endpoint (`/work/iotsupport/src/html/assetctl/upload.php`) to the Python/Flask backend.

## Current PHP Functionality

The existing PHP endpoint accepts multipart form uploads with cryptographic signature verification:

1. **Input**: Multipart form-data with:
   - `file`: The uploaded file binary
   - `timestamp`: ISO timestamp string
   - `signature`: Base64-encoded RSA/SHA256 signature of the timestamp

2. **Security validations**:
   - Filename must not contain `..` (path traversal prevention)
   - Timestamp must be within ±5 minutes of server time (replay attack prevention)
   - Signature must verify against a Kubernetes signing key using RSA/SHA256

3. **Output**: Saves the uploaded file to an assets directory on the filesystem

## Required Backend Implementation

Create a new `/api/assets` endpoint in the Flask backend that:

1. Accepts multipart/form-data POST requests with `file`, `timestamp`, and `signature` fields
2. Validates the filename does not contain path traversal sequences
3. Validates the timestamp is within a configurable tolerance window (default 5 minutes)
4. Verifies the signature using RSA/SHA256 against a configured signing key
5. Saves valid uploads to a configurable assets directory
6. Returns appropriate error responses for validation failures
7. Follows existing backend patterns (service layer, Pydantic schemas, dependency injection, error handling)

## Configuration Requirements

New environment variables needed:
- `ASSETS_DIR`: Path to the assets directory for uploads
- `SIGNING_KEY_PATH`: Path to the RSA private key file for signature verification
