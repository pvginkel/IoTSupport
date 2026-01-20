"""Asset upload API endpoints."""

import logging
import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request, send_file
from spectree import Response as SpectreeResponse

from app.exceptions import RecordNotFoundException, ValidationException
from app.schemas.asset_upload import AssetUploadResponseSchema
from app.schemas.error import ErrorResponseSchema
from app.services.asset_upload_service import AssetUploadService
from app.services.container import ServiceContainer
from app.services.metrics_service import MetricsService
from app.services.mqtt_service import MqttService
from app.utils.auth import public
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

logger = logging.getLogger(__name__)

assets_bp = Blueprint("assets", __name__, url_prefix="/assets")


@assets_bp.route("/<filename>", methods=["GET"])
@public
@handle_api_errors
@inject
def get_asset(
    filename: str,
    asset_upload_service: AssetUploadService = Provide[
        ServiceContainer.asset_upload_service
    ],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Serve raw asset file for ESP32 device consumption.

    This endpoint serves binary firmware files directly to devices.
    Validates filename to prevent path traversal attacks.
    """
    start_time = time.perf_counter()
    status = "success"

    try:
        # Validate filename for path traversal
        asset_upload_service.validate_filename(filename)

        # Construct file path
        file_path = asset_upload_service.assets_dir / filename

        # Check file existence before send_file (for proper error handling)
        if not file_path.exists():
            raise RecordNotFoundException("Asset", filename)

        # Serve file with Cache-Control header
        response = send_file(
            file_path,
            mimetype="application/octet-stream",
            as_attachment=False,
        )
        response.headers["Cache-Control"] = "no-cache"
        return response

    except Exception:
        status = "error"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_operation("asset_serve", status, duration)


@assets_bp.route("", methods=["POST"])
@api.validate(
    resp=SpectreeResponse(
        HTTP_200=AssetUploadResponseSchema,
        HTTP_400=ErrorResponseSchema,
        HTTP_500=ErrorResponseSchema,
    )
)
@handle_api_errors
@inject
def upload_asset(
    asset_upload_service: AssetUploadService = Provide[
        ServiceContainer.asset_upload_service
    ],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
    mqtt_service: MqttService = Provide[ServiceContainer.mqtt_service],
) -> Any:
    """Upload asset file with cryptographic signature verification.

    Expects multipart/form-data with:
    - file: Binary file data
    - timestamp: ISO 8601 timestamp string
    - signature: Base64-encoded RSA signature of timestamp

    Returns:
        200: Upload successful with file metadata
        400: Validation error (missing fields, invalid filename, timestamp, or signature)
        500: Server error (filesystem write failure)
    """
    start_time = time.perf_counter()
    status = "success"
    error_type = "none"
    file_size = None

    try:
        # Validate required fields are present in multipart form
        if "file" not in request.files:
            raise ValidationException("Missing required field 'file'")

        if "timestamp" not in request.form:
            raise ValidationException("Missing required field 'timestamp'")

        if "signature" not in request.form:
            raise ValidationException("Missing required field 'signature'")

        # Extract form data
        uploaded_file = request.files["file"]
        timestamp_str = request.form["timestamp"]
        signature_str = request.form["signature"]

        # Validate filename is present
        if not uploaded_file.filename:
            raise ValidationException("Missing filename in uploaded file")

        filename = uploaded_file.filename

        # Log upload attempt (excluding signature for security)
        logger.info(
            "Asset upload attempt: filename='%s', timestamp='%s'",
            filename,
            timestamp_str,
        )

        # Process upload through service (validates and saves)
        try:
            file_path, file_size, upload_time = asset_upload_service.upload_asset(
                filename=filename,
                timestamp_str=timestamp_str,
                signature_str=signature_str,
                file_data=uploaded_file.stream,
            )
        except ValidationException as e:
            # Determine error type from exception message
            if "filename" in str(e).lower():
                error_type = "filename"
            elif "timestamp" in str(e).lower():
                error_type = "timestamp"
            elif "signature" in str(e).lower():
                error_type = "signature"
            else:
                error_type = "validation"

            status = "validation_error"
            raise

        # Publish MQTT notification after successful upload
        mqtt_service.publish_asset_update(filename)

        # Return success response
        response = AssetUploadResponseSchema(
            filename=filename,
            size=file_size,
            uploaded_at=upload_time.isoformat(),
        )

        logger.info(
            "Asset upload successful: filename='%s', size=%d bytes",
            filename,
            file_size,
        )

        return response.model_dump(), 200

    except ValidationException:
        # Re-raise validation exceptions to be handled by @handle_api_errors
        raise

    except OSError as e:
        # Filesystem errors
        error_type = "filesystem"
        status = "server_error"
        logger.error("Filesystem error during asset upload: %s", e)
        raise

    except Exception as e:
        # Unexpected errors
        error_type = "unknown"
        status = "server_error"
        logger.error("Unexpected error during asset upload: %s", e, exc_info=True)
        raise

    finally:
        # Record metrics
        duration = time.perf_counter() - start_time
        metrics_service.record_asset_upload(
            status=status,
            error_type=error_type,
            duration=duration,
            file_size=file_size,
        )
