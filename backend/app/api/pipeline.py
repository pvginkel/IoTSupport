"""Pipeline API endpoints for CI/CD integration."""

import logging
import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, Response, request
from spectree import Response as SpectreeResponse

from app.config import Settings
from app.exceptions import RecordNotFoundException
from app.schemas.device_model import DeviceModelFirmwareResponseSchema
from app.schemas.error import ErrorResponseSchema
from app.schemas.pipeline import FirmwareVersionResponseSchema
from app.services.container import ServiceContainer
from app.services.device_model_service import DeviceModelService
from app.services.metrics_service import MetricsService
from app.utils.auth import allow_roles, public
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

logger = logging.getLogger(__name__)

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/pipeline")


@pipeline_bp.route("/models/<string:code>/firmware", methods=["POST"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=DeviceModelFirmwareResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@allow_roles("pipeline")
@inject
def upload_firmware(
    code: str,
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Upload firmware binary for a device model by code.

    Expects raw binary content in request body or multipart file upload.
    The firmware must be a valid ESP32 binary with AppInfo header.

    Args:
        code: Device model code (e.g., 'tempsensor')
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        # Look up model by code
        model = device_model_service.get_device_model_by_code(code)

        # Handle multipart file upload or raw body
        if request.files and "file" in request.files:
            file = request.files["file"]
            content = file.read()
        else:
            content = request.get_data()

        if not content:
            from app.exceptions import ValidationException
            raise ValidationException("No firmware content provided")

        model = device_model_service.upload_firmware(model.id, content)

        logger.info(
            "Pipeline uploaded firmware for model %s: version %s",
            code,
            model.firmware_version,
        )

        return DeviceModelFirmwareResponseSchema.model_validate(model).model_dump()

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("pipeline_upload_firmware", status, duration)


@pipeline_bp.route("/models/<string:code>/firmware-version", methods=["GET"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=FirmwareVersionResponseSchema,
        HTTP_404=ErrorResponseSchema,
    )
)
@handle_api_errors
@allow_roles("pipeline")
@inject
def get_firmware_version(
    code: str,
    device_model_service: DeviceModelService = Provide[ServiceContainer.device_model_service],
) -> Any:
    """Get the current firmware version for a device model.

    Useful for CI/CD pipelines to check if firmware needs to be uploaded.

    Args:
        code: Device model code (e.g., 'tempsensor')
    """
    model = device_model_service.get_device_model_by_code(code)
    if model is None:
        raise RecordNotFoundException(f"Device model with code '{code}' not found")

    return FirmwareVersionResponseSchema(
        code=model.code,
        firmware_version=model.firmware_version,
    ).model_dump()


@pipeline_bp.route("/upload.sh", methods=["GET"])
@public
@inject
def get_upload_script(
    config: Settings = Provide[ServiceContainer.config],
) -> Response:
    """Serve a shell script for uploading firmware from CI/CD pipelines.

    The script is customized with the backend URL (inferred from request)
    and token endpoint (from server config). Users only need to provide
    CLIENT_ID and CLIENT_SECRET environment variables.

    Usage:
        curl -fsSL https://iotsupport/api/pipeline/upload.sh | sh -s -- <model_code> <firmware.bin>

    Environment variables required by the script:
        IOTSUPPORT_CLIENT_ID - OAuth2 client ID with pipeline role
        IOTSUPPORT_CLIENT_SECRET - OAuth2 client secret
    """
    from flask import render_template

    # Infer backend URL from request
    # Use X-Forwarded-Proto/Host if behind a reverse proxy, otherwise use request host
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    backend_url = f"{proto}://{host}"

    # Get token URL from config
    token_url = config.OIDC_TOKEN_URL or ""

    script = render_template(
        "upload_firmware.sh.j2",
        backend_url=backend_url,
        token_url=token_url,
    )

    return Response(
        script,
        mimetype="text/x-shellscript",
        headers={"Content-Disposition": "inline; filename=upload.sh"},
    )


@pipeline_bp.route("/upload.ps1", methods=["GET"])
@public
@inject
def get_upload_script_powershell(
    config: Settings = Provide[ServiceContainer.config],
) -> Response:
    """Serve a PowerShell script for uploading firmware from Windows CI/CD pipelines.

    The script is customized with the backend URL (inferred from request)
    and token endpoint (from server config). Users only need to provide
    CLIENT_ID and CLIENT_SECRET environment variables.

    Usage:
        irm https://iotsupport/api/pipeline/upload.ps1 | iex; Upload-Firmware <model_code> <firmware.bin>

    Environment variables required by the script:
        IOTSUPPORT_CLIENT_ID - OAuth2 client ID with pipeline role
        IOTSUPPORT_CLIENT_SECRET - OAuth2 client secret
    """
    from flask import render_template

    # Infer backend URL from request
    # Use X-Forwarded-Proto/Host if behind a reverse proxy, otherwise use request host
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    backend_url = f"{proto}://{host}"

    # Get token URL from config
    token_url = config.OIDC_TOKEN_URL or ""

    script = render_template(
        "upload_firmware.ps1.j2",
        backend_url=backend_url,
        token_url=token_url,
    )

    return Response(
        script,
        mimetype="text/plain",
        headers={"Content-Disposition": "inline; filename=upload.ps1"},
    )
