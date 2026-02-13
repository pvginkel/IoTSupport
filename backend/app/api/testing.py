"""Testing API endpoints for Playwright test suite support."""

import logging
from datetime import UTC, datetime
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, Response, current_app, make_response, request
from spectree import Response as SpectreeResponse

from app.config import Settings
from app.exceptions import RouteNotAvailableException
from app.models.coredump import CoreDump, ParseStatus
from app.schemas.coredump import CoredumpDetailSchema
from app.schemas.testing import (
    ForceErrorQuerySchema,
    KeycloakCleanupSchema,
    TestCoredumpCreateSchema,
    TestSessionCreateSchema,
    TestSessionResponseSchema,
)
from app.services.container import ServiceContainer
from app.services.device_service import DeviceService
from app.services.keycloak_admin_service import KeycloakAdminService
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
        config.oidc_cookie_name,
        token,
        httponly=True,
        secure=cookie_secure,
        samesite=config.oidc_cookie_samesite,
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
    token = request.cookies.get(config.oidc_cookie_name)
    if token:
        testing_service.clear_session(token)

    # Determine cookie security settings
    cookie_secure = get_cookie_secure(config)

    # Create response that clears the cookie
    response = make_response("", 204)

    # Clear the session cookie
    response.set_cookie(
        config.oidc_cookie_name,
        "",
        httponly=True,
        secure=cookie_secure,
        samesite=config.oidc_cookie_samesite,
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


@testing_bp.route("/keycloak-cleanup", methods=["POST"])
@public
@handle_api_errors
@inject
def cleanup_keycloak_clients(
    keycloak_service: KeycloakAdminService = Provide[ServiceContainer.keycloak_admin_service],
) -> tuple[dict[str, Any], int]:
    """Delete Keycloak clients matching a regex pattern.

    This endpoint is used by Playwright tests to clean up Keycloak clients
    created during test runs. The pattern is matched against client IDs.

    Request Body:
        pattern: Regular expression to match against client IDs (required, non-empty)

    Returns:
        200: Cleanup completed with count and list of deleted client IDs
    """
    data = KeycloakCleanupSchema.model_validate(request.get_json())

    deleted_client_ids = keycloak_service.delete_clients_by_pattern(data.pattern)

    logger.info(
        "Keycloak cleanup completed: deleted %d clients matching %r",
        len(deleted_client_ids),
        data.pattern,
    )

    return {
        "deleted_count": len(deleted_client_ids),
        "deleted_client_ids": deleted_client_ids,
    }, 200


@testing_bp.route("/coredumps", methods=["POST"])
@public
@api.validate(
    json=TestCoredumpCreateSchema,
    resp=SpectreeResponse(HTTP_201=CoredumpDetailSchema),
)
@handle_api_errors
@inject
def create_test_coredump(
    device_service: DeviceService = Provide[ServiceContainer.device_service],
) -> tuple[dict[str, Any], int]:
    """Create a coredump database record for testing.

    Seeds a CoreDump row directly in the database without filesystem I/O
    or sidecar parsing. Used by Playwright tests to set up coredump UI scenarios.

    Request Body:
        device_id: Device ID (required, must exist)
        chip: Chip type (default: esp32s3)
        firmware_version: Firmware version (default: 0.0.0-test)
        size: Coredump size in bytes (default: 262144)
        parse_status: PENDING, PARSED, or ERROR (default: PARSED)
        parsed_output: Parsed output text (auto-set for PARSED if omitted)

    Returns:
        201: Coredump record created successfully
    """
    data = TestCoredumpCreateSchema.model_validate(request.get_json())

    # Verify the device exists (raises RecordNotFoundException if not)
    device_service.get_device(data.device_id)

    now = datetime.now(UTC)

    # Default parsed_output for PARSED status
    parsed_output = data.parsed_output
    if data.parse_status == ParseStatus.PARSED.value and parsed_output is None:
        parsed_output = "Test coredump parsed output"

    # Set parsed_at for terminal states (PARSED or ERROR)
    parsed_at = now if data.parse_status in (ParseStatus.PARSED.value, ParseStatus.ERROR.value) else None

    # Create the coredump record with a placeholder filename
    coredump = CoreDump(
        device_id=data.device_id,
        filename="placeholder.dmp",
        chip=data.chip,
        firmware_version=data.firmware_version,
        size=data.size,
        parse_status=data.parse_status,
        parsed_output=parsed_output,
        uploaded_at=now,
        parsed_at=parsed_at,
    )

    session = current_app.container.db_session()
    session.add(coredump)
    session.flush()

    # Update filename with the actual ID
    coredump.filename = f"test_coredump_{coredump.id}.dmp"
    session.flush()

    logger.info("Created test coredump: id=%d device_id=%d status=%s", coredump.id, data.device_id, data.parse_status)

    return CoredumpDetailSchema.model_validate(coredump).model_dump(), 201
