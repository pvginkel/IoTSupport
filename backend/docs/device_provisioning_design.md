# Device Provisioning and Authentication - Functional Design

## Overview

This document describes how ESP32 IoT devices are provisioned with unique identities and how they authenticate to both the IoT Support backend and the MQTT broker. The design leverages Keycloak as the identity provider, enabling a unified credential model where devices use OAuth2 tokens for all service access.

## Problem Statement

Devices need unique identities to:

1. Authenticate to the IoT Support backend to fetch their configuration and assets
2. Authenticate to the MQTT broker to receive commands and publish telemetry
3. Be individually managed, monitored, and revoked if compromised

A shared credential approach (single password for all devices) creates security risks and prevents per-device management. This design establishes per-device credentials managed through Keycloak.

## Credential Model

Each device is registered as a confidential client in Keycloak with its own client ID and client secret. The device uses OAuth2 client credentials grant to obtain JWT access tokens.

These JWT tokens serve dual purpose:

- **Backend API access**: Device includes the JWT in API requests as a Bearer token
- **MQTT access**: Device uses the JWT as its MQTT password (with client ID as username), validated by Mosquitto's JWT authentication plugin

This unified model means:

- Single source of truth for device identity (Keycloak)
- Consistent authentication across all services
- Centralized revocation capability
- Audit trail through Keycloak

## Provisioning Workflow

### Actors

- **Administrator**: Person provisioning a new device
- **Frontend**: Web UI for device management
- **Backend**: IoT Support backend service
- **Keycloak**: Identity provider
- **Device**: ESP32 hardware being provisioned

### Provisioning Steps

1. Administrator opens the device provisioning UI in the frontend
2. Administrator enters device details: friendly name, MAC address (optional), WiFi credentials
3. Frontend submits provisioning request to backend
4. Backend creates a new confidential client in Keycloak via the admin API
5. Backend generates a provisioning package containing: device identifier, Keycloak client ID, client secret, WiFi credentials, and backend/Keycloak URLs
6. Backend stores device record in its database for fleet management
7. Backend returns provisioning package to frontend
8. Administrator downloads the provisioning package as a binary file
9. Administrator flashes the provisioning package to the device's dedicated storage partition
10. Device is now provisioned and ready for operation

### Provisioning Package Contents

The provisioning package contains everything the device needs to bootstrap:

- Device identifier (friendly name)
- Keycloak client ID
- Keycloak client secret
- WiFi network name and password
- Keycloak token endpoint URL
- Backend API base URL

This data is written to a dedicated partition on the device's flash storage that survives firmware updates and OTA upgrades.

## Device Runtime Behavior

### Boot Sequence

When a provisioned device boots:

1. Device reads credentials from its provisioning partition
2. Device connects to the configured WiFi network
3. Device requests a JWT access token from Keycloak using client credentials grant
4. Device fetches its configuration from the backend API using the JWT
5. Device connects to MQTT using its client ID and JWT as credentials
6. Device begins normal operation

### Token Lifecycle

JWT tokens have a limited lifetime (typically hours). The device must refresh tokens before they expire:

- Device tracks token expiration time
- Before expiration, device requests a new token from Keycloak
- If MQTT connection drops, device obtains fresh token before reconnecting
- MQTT connections persist even if the token used at connection time expires (validation occurs only at connect time)

### Authentication Failures

If authentication fails (expired token, revoked credentials, Keycloak unavailable):

- Device retries with exponential backoff
- Device cannot operate without valid configuration
- Persistent failures indicate the device needs re-provisioning or the infrastructure is down

## Secret Rotation

Device secrets should be rotated periodically or when compromise is suspected. Rotation is backend-initiated but device-executed, accommodating devices that may be offline.

### Rotation Actors

- **Backend**: Initiates rotation, generates new secrets, tracks completion
- **MQTT**: Delivers rotation requests via retained messages
- **Device**: Executes rotation when online, confirms completion
- **Keycloak**: Stores and validates secrets

### Rotation Workflow

1. Administrator (or scheduled job) triggers rotation for a device through the backend
2. Backend publishes a rotation request to the device's MQTT topic as a retained message
3. Backend records that rotation has been requested and tracks the timestamp
4. Device receives the rotation request (immediately if online, or upon reconnecting)
5. Device calls the backend rotation endpoint, authenticating with its current JWT
6. Backend generates a new secret for the device's Keycloak client via the admin API
7. Backend returns the new secret to the device (old secret is now invalid)
8. Device writes the new secret to its provisioning partition
9. Device obtains a new JWT from Keycloak using the new secret
10. Device calls the backend confirmation endpoint using the new JWT, proving the rotation succeeded
11. Backend clears the retained MQTT message and marks rotation complete

### Handling Offline Devices

The retained MQTT message ensures offline devices receive rotation requests when they reconnect. The backend tracks rotation status per device:

- **Requested**: Rotation message published, awaiting device response
- **In Progress**: Device has fetched new secret, awaiting confirmation
- **Completed**: Device confirmed successful rotation
- **Failed**: Device did not complete rotation within the timeout period

Devices that remain in "requested" or "in progress" state beyond a threshold appear in fleet management as requiring attention.

### Rotation Failure Recovery

If a device fails to complete rotation (crashes after receiving new secret but before confirming):

- Device reboots and reads credentials from partition
- If new secret was written, device can authenticate and confirm
- If new secret was not written, device still has old secret but old secret is already invalid
- In the latter case, device cannot authenticate and needs re-provisioning

This failure mode is rare (requires crash during the brief write window) and acceptable for a homelab environment where physical access enables re-provisioning.

## Fleet Management

The backend maintains a device registry for fleet visibility and management.

### Device Records

For each device, the backend tracks:

- Device identifier and optional MAC address
- Keycloak client reference
- Provisioning timestamp
- Last successful communication timestamp
- Current secret age (when the secret was created or last rotated)
- Rotation status (if rotation is in progress)

### Fleet Operations

Administrators can:

- View all provisioned devices and their status
- See which devices have communicated recently
- Identify devices with old secrets needing rotation
- Identify devices not responding to rotation requests
- Trigger rotation for individual devices or the entire fleet
- Revoke a device (disable its Keycloak client)
- Delete a device from the registry

### Monitoring and Alerts

The system provides visibility into:

- Devices that haven't checked in within expected intervals
- Devices with pending rotations older than threshold
- Devices that failed rotation
- Overall fleet health metrics

## MQTT Integration

### Authentication

Mosquitto is configured with a JWT authentication plugin that validates tokens against Keycloak:

- Username: Device's Keycloak client ID
- Password: JWT access token
- Plugin validates token signature, expiration, and issuer

### Topic Structure

Devices communicate on namespaced topics:

- Backend publishes to device-specific topics for rotation requests and configuration updates
- Devices subscribe to their own topics
- Devices publish telemetry to designated topics
- Retained messages used for state that must survive device restarts

### Token Expiration Behavior

MQTT connections established with a valid JWT remain connected even after the token expires. The broker validates the token only at connection time. This means:

- Long-running connections are not disrupted by token expiration
- Devices should refresh tokens proactively to ensure they can reconnect if disconnected
- Token lifetime can be set to hours without causing excessive MQTT reconnections

## Keycloak Configuration

### Backend Service Account

The backend requires a Keycloak service account with administrative permissions:

- Create clients (for device provisioning)
- Regenerate client secrets (for rotation)
- Disable/delete clients (for revocation)

### Device Clients

Each device is represented as a confidential client in Keycloak:

- Service account enabled for client credentials grant
- Assigned a device role for authorization
- No user interaction required (machine-to-machine authentication)

### Token Configuration

Device tokens are configured with:

- Appropriate lifetime for the use case (hours recommended)
- Required claims for backend and MQTT validation (issuer, audience, expiration)
- Device role for authorization decisions

## Security Considerations

### Credential Storage

Device credentials are stored in a dedicated flash partition that:

- Survives OTA firmware updates
- Is not easily readable without physical access
- Contains only the device's own credentials

### Compromise Response

If a device is suspected compromised:

1. Disable the device's Keycloak client immediately (instant revocation)
2. Device can no longer obtain new tokens
3. Existing MQTT connections persist until disconnected, but device cannot reconnect
4. Backend can also reject requests from the device based on its disabled status

### Network Security

- All communication uses TLS (HTTPS for API, TLS for MQTT)
- Tokens are transmitted only over encrypted channels
- WiFi credentials in provisioning package should use WPA2/WPA3 networks

### Rotation as Defense in Depth

Regular secret rotation limits the window of opportunity if a secret is compromised:

- Attacker must extract secret AND use it before rotation
- Rotation can be triggered immediately upon suspected compromise
- Fleet-wide rotation possible for broad response

## Limitations and Accepted Tradeoffs

### Single Secret Transition

Keycloak does not support multiple active secrets per client. When a new secret is generated, the old secret becomes invalid immediately. This creates a brief window during rotation where a device crash could leave it unable to authenticate. For a homelab with physical access to devices, re-provisioning is an acceptable recovery path.

### No Offline Operation

Devices cannot operate without network access to Keycloak and the backend. This is appropriate for IoT devices that inherently require network connectivity for their primary function.

### Trust in Keycloak

The security model trusts Keycloak as the identity provider. Keycloak compromise would affect all device authentication. This is acceptable given Keycloak's role as the existing identity infrastructure.
