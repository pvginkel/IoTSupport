"""Image proxy API endpoints."""

import time
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, Response, request
from spectree import Response as SpectreeResponse

from app.exceptions import (
    ExternalServiceException,
    InvalidOperationException,
    ProcessingException,
)
from app.schemas.error import ErrorResponseSchema
from app.schemas.image_proxy import LvglImageQuerySchema
from app.services.container import ServiceContainer
from app.services.image_proxy_service import ImageProxyService
from app.services.metrics_service import MetricsService
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

images_bp = Blueprint("images", __name__, url_prefix="/images")


@images_bp.route("/lvgl", methods=["GET"])
@api.validate(
    query=LvglImageQuerySchema,
    resp=SpectreeResponse(
        HTTP_200=None,  # Binary response, no schema
        HTTP_400=ErrorResponseSchema,
        HTTP_500=ErrorResponseSchema,
        HTTP_502=ErrorResponseSchema,
    ),
)
@handle_api_errors
@inject
def get_lvgl_image(
    image_proxy_service: ImageProxyService = Provide[
        ServiceContainer.image_proxy_service
    ],
    metrics_service: MetricsService = Provide[ServiceContainer.metrics_service],
) -> Any:
    """Fetch and convert an image to LVGL binary format.

    Query Parameters:
        url: URL of the image to fetch
        headers: Comma-separated list of header names to forward
        width: Target width for resizing (optional, downscale only)
        height: Target height for resizing (optional, downscale only)

    Returns:
        Binary LVGL image data with Cache-Control: no-store header
    """
    start_time = time.perf_counter()
    status = "success"
    error_type = "none"

    try:
        # Validate and parse query parameters
        query_params = LvglImageQuerySchema.model_validate(request.args.to_dict())

        # Parse headers to forward
        headers_to_forward: dict[str, str] = {}
        if query_params.headers:
            header_names = [
                name.strip() for name in query_params.headers.split(",") if name.strip()
            ]
            for header_name in header_names:
                # Check if header exists in incoming request
                header_value = request.headers.get(header_name)
                if header_value is None:
                    error_type = "missing_header"
                    raise InvalidOperationException(
                        "forward headers",
                        f"header '{header_name}' not present in request",
                    )
                headers_to_forward[header_name] = header_value

        # Convert Pydantic HttpUrl to string for service
        url_str = str(query_params.url)

        # Fetch and convert image
        lvgl_data = image_proxy_service.fetch_and_convert_image(
            url=url_str,
            headers=headers_to_forward,
            width=query_params.width,
            height=query_params.height,
        )

        # Create binary response with Cache-Control header
        response = Response(lvgl_data, mimetype="application/octet-stream")
        response.headers["Cache-Control"] = "no-store"

        return response

    except ExternalServiceException:
        status = "error"
        error_type = "external_fetch_failed"
        raise

    except ProcessingException as e:
        status = "error"
        # Map operation to specific error type
        if "decode image" in e.operation:
            error_type = "decode_failed"
        elif "resize image" in e.operation:
            error_type = "resize_failed"
        elif "convert to LVGL format" in e.operation:
            error_type = "lvgl_conversion_failed"
        else:
            error_type = "processing_failed"
        raise

    except InvalidOperationException:
        status = "error"
        if error_type == "none":
            error_type = "invalid_operation"
        raise

    except Exception:
        status = "error"
        if error_type == "none":
            error_type = "unknown"
        raise

    finally:
        duration = time.perf_counter() - start_time
        metrics_service.record_image_proxy_operation(
            status=status,
            error_type=error_type,
            operation_duration=duration,
        )
