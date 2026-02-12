"""IoT device-authenticated API endpoints.

This blueprint provides endpoints for ESP32 devices to:
- Fetch their configuration
- Download firmware for their model
- Retrieve new provisioning data during rotation

All endpoints require device JWT authentication.
"""

import logging
import time
from datetime import datetime
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, Response, send_file

from app.config import Settings
from app.exceptions import AuthenticationException, ValidationException
from app.models.device import RotationState
from app.services.auth_service import AuthService
from app.services.container import ServiceContainer
from app.services.coredump_service import CoredumpService
from app.services.device_service import DeviceService
from app.services.firmware_service import FirmwareService
from app.services.keycloak_admin_service import KeycloakAdminService
from app.services.metrics_service import MetricsService
from app.services.rotation_service import RotationService
from app.utils.auth import public
from app.utils.device_auth import (
    authenticate_device_request,
    get_device_auth_context,
)
from app.utils.error_handling import handle_api_errors

logger = logging.getLogger(__name__)

iot_bp = Blueprint("iot", __name__, url_prefix="/iot")


@iot_bp.before_request
@inject
def before_request_device_auth(
    auth_service: AuthService = Provide[ServiceContainer.auth_service],
    config: Settings = Provide[ServiceContainer.config],
) -> None | tuple[dict[str, str], int]:
    """Authenticate all requests to /iot endpoints.

    This hook validates the device JWT token before every request.
    """
    # Skip authentication if OIDC is disabled (for testing)
    if not config.oidc_enabled:
        logger.debug("OIDC disabled - skipping device authentication")
        return None

    try:
        authenticate_device_request(auth_service, config)
        return None
    except AuthenticationException as e:
        logger.warning("Device authentication failed: %s", str(e))
        return {"error": str(e)}, 401


@iot_bp.route("/config", methods=["GET"])
@public
@handle_api_errors
@inject
def get_config(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    rotation_service: RotationService = Provide[ServiceContainer.rotation_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
    config: Settings = Provide[ServiceContainer.config],
) -> Any:
    """Get raw JSON configuration for the device.

    This endpoint is called by ESP32 devices to fetch their configuration.
    If the device is in PENDING rotation state and the token was issued
    after the rotation attempt, the rotation is marked as complete and
    the next queued device is triggered.

    Returns raw JSON content without wrapping.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        device_ctx = get_device_auth_context()

        # If OIDC is disabled (testing), get device from query param
        if device_ctx is None:
            from flask import request
            device_key = request.args.get("device_key")
            if not device_key:
                raise AuthenticationException("Device authentication required")
            device = device_service.get_device_by_key(device_key)
        else:
            device = device_service.get_device_by_key(device_ctx.device_key)

        # Check for rotation completion and trigger next device
        if device.rotation_state == RotationState.PENDING.value:
            _check_rotation_completion(device, device_ctx, device_service, rotation_service)

        # Return raw config as JSON string
        config_data = device_service.get_config_for_device(device)

        return Response(
            config_data,
            status=200,
            mimetype="application/json",
            headers={"Cache-Control": "no-cache"},
        )

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("iot_get_config", status, duration)


def _check_rotation_completion(
    device: Any,
    device_ctx: Any,
    device_service: DeviceService,
    rotation_service: RotationService,
) -> None:
    """Check if rotation should be marked complete based on token timestamp.

    If the token was issued after the rotation attempt started, the device
    has successfully obtained new credentials and rotation is complete.
    After completion, triggers the next queued device to maintain rotation momentum.

    Args:
        device: Device instance
        device_ctx: Device auth context with token_iat
        device_service: Device service for updates
        rotation_service: Rotation service for triggering next device
    """
    if device_ctx is None or device_ctx.token_iat is None:
        return

    # Compare token issued-at with rotation attempt time
    if device.last_rotation_attempt_at is None:
        return

    # Token iat is Unix timestamp, convert to datetime for comparison
    token_time = datetime.utcfromtimestamp(device_ctx.token_iat)

    # Add clock skew tolerance (30 seconds)
    from datetime import timedelta
    tolerance = timedelta(seconds=30)

    if token_time > device.last_rotation_attempt_at - tolerance:
        # Token was issued after rotation started - rotation complete
        device.rotation_state = RotationState.OK.value
        device.last_rotation_completed_at = datetime.utcnow()
        device_service.clear_cached_secret(device)

        logger.info(
            "Rotation completed for device %s (token issued %s, rotation started %s)",
            device.key,
            token_time,
            device.last_rotation_attempt_at,
        )

        # Chain rotation: immediately trigger the next queued device
        # This maintains rotation momentum without waiting for the next CRON tick
        rotation_service.rotate_next_queued_device()


@iot_bp.route("/firmware", methods=["GET"])
@public
@handle_api_errors
@inject
def get_firmware(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    firmware_service: FirmwareService = Provide[ServiceContainer.firmware_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Download firmware binary for the device's model.

    Returns raw binary firmware with appropriate content type.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        device_ctx = get_device_auth_context()

        # If OIDC is disabled (testing), get device from query param
        if device_ctx is None:
            from flask import request
            device_key = request.args.get("device_key")
            if not device_key:
                raise AuthenticationException("Device authentication required")
            device = device_service.get_device_by_key(device_key)
            model_code = device.device_model.code
            firmware_version = device.device_model.firmware_version
        else:
            # Look up device to get firmware_version from the model
            device = device_service.get_device_by_key(device_ctx.device_key)
            model_code = device_ctx.model_code
            firmware_version = device.device_model.firmware_version

        # Get firmware stream (tries versioned ZIP first, falls back to legacy .bin)
        stream = firmware_service.get_firmware_stream(model_code, firmware_version)

        # Use send_file with BytesIO stream
        return send_file(  # type: ignore[call-arg]
            stream,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=f"firmware-{model_code}.bin",
        )

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("iot_get_firmware", status, duration)


@iot_bp.route("/firmware-version", methods=["GET"])
@public
@handle_api_errors
@inject
def get_firmware_version(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Get the current firmware version for the device's model.

    This lightweight endpoint allows devices to check if new firmware
    is available without downloading the binary. Devices can poll this
    periodically and only download firmware when the version changes.

    Returns JSON with the firmware version string.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        device_ctx = get_device_auth_context()

        # If OIDC is disabled (testing), get device from query param
        if device_ctx is None:
            from flask import request
            device_key = request.args.get("device_key")
            if not device_key:
                raise AuthenticationException("Device authentication required")
            device = device_service.get_device_by_key(device_key)
            model = device.device_model
        else:
            device = device_service.get_device_by_key(device_ctx.device_key)
            model = device.device_model

        # Return firmware version (may be None if no firmware uploaded)
        return {
            "firmware_version": model.firmware_version,
        }

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("iot_get_firmware_version", status, duration)


@iot_bp.route("/provisioning", methods=["GET"])
@public
@handle_api_errors
@inject
def get_provisioning_for_rotation(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    keycloak_admin_service: KeycloakAdminService = Provide[ServiceContainer.keycloak_admin_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
    app_config: Settings = Provide[ServiceContainer.config],
) -> Any:
    """Get new provisioning data during rotation.

    This endpoint is called by devices during the rotation process.
    It regenerates the client secret in Keycloak and returns the new
    provisioning package.

    This is different from admin provisioning download - it generates
    a NEW secret rather than returning the current one.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        device_ctx = get_device_auth_context()

        # If OIDC is disabled (testing), get device from query param
        if device_ctx is None:
            from flask import request
            device_key = request.args.get("device_key")
            if not device_key:
                raise AuthenticationException("Device authentication required")
            device = device_service.get_device_by_key(device_key)
            client_id = device.client_id
        else:
            device = device_service.get_device_by_key(device_ctx.device_key)
            client_id = device_ctx.client_id

        # Cache current secret for rollback in case of timeout
        # This must happen right before regeneration so we have the exact secret to restore
        current_secret = keycloak_admin_service.get_client_secret(client_id)
        device_service.cache_secret_for_rotation(device, current_secret)

        # Regenerate secret in Keycloak
        # This is the critical moment - the device's old secret becomes invalid
        new_secret = keycloak_admin_service.regenerate_secret(client_id)

        # Update secret_created_at to track when this secret was issued
        device.secret_created_at = datetime.utcnow()

        # Build provisioning package
        package = {
            "device_key": device.key,
            "client_id": client_id,
            "client_secret": new_secret,
            "token_url": app_config.oidc_token_url,
            "base_url": app_config.device_baseurl,
            "mqtt_url": app_config.device_mqtt_url,
            "wifi_ssid": app_config.wifi_ssid,
            "wifi_password": app_config.wifi_password,
        }

        logger.info("Generated rotation provisioning for device %s", device.key)

        return (
            package,
            200,
            {"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("iot_get_provisioning", status, duration)


@iot_bp.route("/coredump", methods=["POST"])
@public
@handle_api_errors
@inject
def upload_coredump(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    coredump_service: CoredumpService = Provide[ServiceContainer.coredump_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Upload a coredump from a device.

    Accepts raw binary body containing the ESP32 coredump data.
    Requires chip and firmware_version query parameters.

    The coredump is stored in COREDUMPS_DIR/{device_key}/ with a DB record
    tracking metadata and parse status. Background parsing is triggered
    if the sidecar is configured.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        from flask import request

        # Validate required query parameters before reading body
        chip = request.args.get("chip")
        if not chip:
            raise ValidationException("Missing required query parameter: chip")

        firmware_version = request.args.get("firmware_version")
        if not firmware_version:
            raise ValidationException("Missing required query parameter: firmware_version")

        # Resolve device identity from auth context or query param
        device_ctx = get_device_auth_context()

        if device_ctx is None:
            device_key = request.args.get("device_key")
            if not device_key:
                raise AuthenticationException("Device authentication required")
            device = device_service.get_device_by_key(device_key)
            device_id = device.id
            device_key = device.key
            model_code = device.device_model.code
        else:
            device_key = device_ctx.device_key
            model_code = device_ctx.model_code
            device = device_service.get_device_by_key(device_key)
            device_id = device.id

        # Read raw binary body
        content = request.get_data()

        # Delegate to service: saves file, creates DB record, enforces retention
        filename, coredump_id = coredump_service.save_coredump(
            device_id=device_id,
            device_key=device_key,
            model_code=model_code,
            chip=chip,
            firmware_version=firmware_version,
            content=content,
        )

        # Spawn background parsing thread (no-op if sidecar not configured).
        # All data is passed as arguments so the thread does not need to read
        # the DB record and is not affected by transaction timing.
        coredump_service.maybe_start_parsing(
            coredump_id=coredump_id,
            device_key=device_key,
            model_code=model_code,
            chip=chip,
            firmware_version=firmware_version,
            filename=filename,
        )

        return {"status": "ok", "filename": filename}, 201

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("iot_upload_coredump", status, duration)
