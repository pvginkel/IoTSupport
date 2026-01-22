"""Testing API endpoints for Playwright test suite support."""

import logging
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, Response, current_app, make_response, request
from spectree import Response as SpectreeResponse

from app.config import Settings
from app.exceptions import RouteNotAvailableException
from app.schemas.testing import (
    ForceErrorQuerySchema,
    TestSessionCreateSchema,
    TestSessionResponseSchema,
)
from app.services.container import ServiceContainer
from app.services.testing_service import TestingService
from app.utils.auth import get_cookie_secure, public
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

logger = logging.getLogger(__name__)

testing_bp = Blueprint("testing", __name__, url_prefix="/testing")


@testing_bp.before_request
def check_testing_mode() -> Any:
    """Check if the server is running in testing mode before processing any testing endpoint."""
    from app.utils.error_handling import _build_error_response

    container = current_app.container
    settings = container.config()

    if not settings.is_testing:
        # Return error response directly since before_request handlers don't go through @handle_api_errors
        exception = RouteNotAvailableException()
        return _build_error_response(
            exception.message,
            {"message": "Testing endpoints require FLASK_ENV=testing"},
            code=exception.error_code,
            status_code=400,
        )

    return None


@testing_bp.route("/auth/session", methods=["POST"])
@public
@api.validate(
    json=TestSessionCreateSchema,
    resp=SpectreeResponse(HTTP_201=TestSessionResponseSchema),
)
@handle_api_errors
@inject
def create_test_session(
    testing_service: TestingService = Provide[ServiceContainer.testing_service],
    config: Settings = Provide[ServiceContainer.config],
) -> Response:
    """Create an authenticated test session, bypassing the real OIDC flow.

    This endpoint creates a test session with controllable user fields
    and sets the same session cookie that the real OIDC callback would set.

    Request Body:
        subject: User subject identifier (required)
        name: User display name (optional)
        email: User email address (optional)
        roles: User roles (optional, defaults to empty list)

    Returns:
        201: Session created successfully with session cookie set
    """
    data = TestSessionCreateSchema.model_validate(request.get_json())

    # Create test session and get token
    token = testing_service.create_session(
        subject=data.subject,
        name=data.name,
        email=data.email,
        roles=data.roles,
    )

    # Build response
    response_data = TestSessionResponseSchema(
        subject=data.subject,
        name=data.name,
        email=data.email,
        roles=data.roles,
    )

    # Determine cookie security settings (same as real auth flow)
    cookie_secure = get_cookie_secure(config)

    # Create response with cookie
    response = make_response(response_data.model_dump(), 201)

    # Set the same cookie that the real OIDC callback would set
    response.set_cookie(
        config.OIDC_COOKIE_NAME,
        token,
        httponly=True,
        secure=cookie_secure,
        samesite=config.OIDC_COOKIE_SAMESITE,
        max_age=3600,  # 1 hour for test sessions
    )

    logger.info(
        "Created test session: subject=%s name=%s email=%s roles=%s",
        data.subject,
        data.name,
        data.email,
        data.roles,
    )

    return response


@testing_bp.route("/auth/clear", methods=["POST"])
@public
@handle_api_errors
@inject
def clear_test_session(
    testing_service: TestingService = Provide[ServiceContainer.testing_service],
    config: Settings = Provide[ServiceContainer.config],
) -> Response:
    """Clear the current test session for test isolation.

    Returns:
        204: Session cleared successfully with cookie invalidated
    """
    # Get current token from cookie (if any)
    token = request.cookies.get(config.OIDC_COOKIE_NAME)
    if token:
        testing_service.clear_session(token)

    # Determine cookie security settings
    cookie_secure = get_cookie_secure(config)

    # Create response that clears the cookie
    response = make_response("", 204)

    # Clear the session cookie
    response.set_cookie(
        config.OIDC_COOKIE_NAME,
        "",
        httponly=True,
        secure=cookie_secure,
        samesite=config.OIDC_COOKIE_SAMESITE,
        max_age=0,
    )

    logger.info("Cleared test session")

    return response


@testing_bp.route("/auth/force-error", methods=["POST"])
@public
@api.validate(query=ForceErrorQuerySchema)
@handle_api_errors
@inject
def force_auth_error(
    testing_service: TestingService = Provide[ServiceContainer.testing_service],
) -> tuple[str, int]:
    """Configure /api/auth/self to return an error on the next request.

    This is a single-shot error - subsequent requests will behave normally.

    Query Parameters:
        status: HTTP status code to return (e.g., 500, 503)

    Returns:
        204: Error configured successfully
    """
    query = ForceErrorQuerySchema.model_validate(request.args.to_dict())

    testing_service.set_forced_auth_error(query.status)

    logger.info("Configured forced auth error: status=%d", query.status)

    return "", 204
