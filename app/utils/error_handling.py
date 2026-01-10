"""Centralized error handling utilities."""

import functools
import logging
from collections.abc import Callable
from typing import Any

from flask import jsonify
from flask.wrappers import Response
from pydantic import ValidationError

from app.exceptions import (
    BusinessLogicException,
    ExternalServiceException,
    InvalidOperationException,
    ProcessingException,
    RecordExistsException,
    RecordNotFoundException,
    ValidationException,
)
from app.utils import get_current_correlation_id

logger = logging.getLogger(__name__)


def _build_error_response(
    error: str,
    details: dict[str, Any],
    code: str | None = None,
    status_code: int = 400,
) -> tuple[Response, int]:
    """Build error response with correlation ID and optional error code."""
    response_data: dict[str, Any] = {
        "error": error,
        "details": details,
    }

    # Add error code if provided
    if code:
        response_data["code"] = code

    correlation_id = get_current_correlation_id()
    if correlation_id:
        response_data["correlationId"] = correlation_id

    return jsonify(response_data), status_code


def handle_api_errors(
    func: Callable[..., Any],
) -> Callable[..., Response | tuple[Response | str, int]]:
    """Decorator to handle common API errors consistently.

    Handles ValidationError, custom exceptions, and generic exceptions
    with appropriate HTTP status codes and error messages.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log all exceptions with stack trace
            logger.error("Exception in %s: %s", func.__name__, str(e), exc_info=True)

            # Handle specific exception types
            try:
                raise
            except ValidationError as e:
                # Pydantic validation errors
                error_details = []
                for error in e.errors():
                    field = ".".join(str(x) for x in error["loc"])
                    message = error["msg"]
                    error_details.append({"message": message, "field": field})

                return _build_error_response(
                    "Validation failed", {"errors": error_details}, status_code=400
                )

            except RecordNotFoundException as e:
                # Custom domain exception for not found resources
                return _build_error_response(
                    e.message,
                    {"message": "The requested resource could not be found"},
                    code=e.error_code,
                    status_code=404,
                )

            except RecordExistsException as e:
                # Custom domain exception for duplicate resources
                return _build_error_response(
                    e.message,
                    {"message": "The resource already exists"},
                    code=e.error_code,
                    status_code=409,
                )

            except ExternalServiceException as e:
                # External service failure (HTTP 502 Bad Gateway)
                return _build_error_response(
                    e.message,
                    {"message": "External service request failed"},
                    code=e.error_code,
                    status_code=502,
                )

            except ProcessingException as e:
                # Internal processing failure (HTTP 500 Internal Server Error)
                return _build_error_response(
                    e.message,
                    {"message": "Processing operation failed"},
                    code=e.error_code,
                    status_code=500,
                )

            except InvalidOperationException as e:
                # Custom domain exception for invalid operations (includes invalid MAC)
                return _build_error_response(
                    e.message,
                    {"message": "The requested operation cannot be performed"},
                    code=e.error_code,
                    status_code=400,
                )

            except ValidationException as e:
                # Custom validation exception
                return _build_error_response(
                    e.message,
                    {"message": "Validation failed"},
                    code=e.error_code,
                    status_code=400,
                )

            except BusinessLogicException as e:
                # Generic business logic exception (fallback for custom exceptions)
                return _build_error_response(
                    e.message,
                    {"message": "A business logic operation failed"},
                    code=e.error_code,
                    status_code=400,
                )

            except Exception as e:
                # Generic error handler
                return _build_error_response(
                    "Internal server error", {"message": str(e)}, status_code=500
                )

    return wrapper
