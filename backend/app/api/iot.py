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
from flask import Blueprint, Response

from app.config import Settings
from app.exceptions import AuthenticationException, RecordNotFoundException
from app.models.device import RotationState
from app.services.auth_service import AuthService
from app.services.container import ServiceContainer
from app.services.device_service import DeviceService
from app.services.firmware_service import FirmwareService
from app.services.keycloak_admin_service import KeycloakAdminService
from app.services.metrics_service import MetricsService
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
    if not config.OIDC_ENABLED:
        logger.debug("OIDC disabled - skipping device authentication")
        return None

    try:
        authenticate_device_request(auth_service, config)
        return None
    except AuthenticationException as e:
        logger.warning("Device authentication failed: %s", str(e))
        return {"error": str(e)}, 401


@iot_bp.route("/config", methods=["GET"])
@handle_api_errors
@inject
def get_config(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
    config: Settings = Provide[ServiceContainer.config],
) -> Any:
    """Get raw JSON configuration for the device.

    This endpoint is called by ESP32 devices to fetch their configuration.
    If the device is in PENDING rotation state and the token was issued
    after the rotation attempt, the rotation is marked as complete.

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

        # Check for rotation completion
        if device.rotation_state == RotationState.PENDING.value:
            _check_rotation_completion(device, device_ctx, device_service)

        # Return raw config
        config_data = device_service.get_config_for_device(device)

        return (
            config_data,
            200,
            {"Cache-Control": "no-cache"},
        )

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("iot_get_config", status, duration)


def _check_rotation_completion(device: Any, device_ctx: Any, device_service: DeviceService) -> None:
    """Check if rotation should be marked complete based on token timestamp.

    If the token was issued after the rotation attempt started, the device
    has successfully obtained new credentials and rotation is complete.

    Args:
        device: Device instance
        device_ctx: Device auth context with token_iat
        device_service: Device service for updates
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


@iot_bp.route("/firmware", methods=["GET"])
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
        else:
            model_code = device_ctx.model_code

        # Get firmware content
        if not firmware_service.firmware_exists(model_code):
            raise RecordNotFoundException("Firmware", model_code)

        content = firmware_service.get_firmware(model_code)

        return Response(
            content,
            mimetype="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename=firmware-{model_code}.bin",
                "Cache-Control": "no-cache",
            },
        )

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("iot_get_firmware", status, duration)


@iot_bp.route("/provisioning", methods=["GET"])
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

        # Regenerate secret in Keycloak
        new_secret = keycloak_admin_service.regenerate_secret(client_id)

        # Build provisioning package
        package = {
            "device_key": device.key,
            "client_id": client_id,
            "client_secret": new_secret,
            "token_url": app_config.OIDC_TOKEN_URL,
            "base_url": app_config.BASEURL,
            "mqtt_url": app_config.MQTT_URL,
            "wifi_ssid": app_config.WIFI_SSID,
            "wifi_password": app_config.WIFI_PASSWORD,
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
