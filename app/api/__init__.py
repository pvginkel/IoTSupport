"""API blueprints for IoT Support Backend."""

import logging

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, Response, request

from app.config import Settings
from app.services.auth_service import AuthService
from app.services.container import ServiceContainer
from app.services.oidc_client_service import OidcClientService
from app.services.testing_service import TestingService
from app.utils.auth import (
    authenticate_request,
    get_cookie_secure,
    get_token_expiry_seconds,
)

logger = logging.getLogger(__name__)

# Create main API blueprint
api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.before_request
@inject
def before_request_authentication(
    auth_service: AuthService = Provide[ServiceContainer.auth_service],
    oidc_client_service: OidcClientService = Provide[ServiceContainer.oidc_client_service],
    testing_service: TestingService = Provide[ServiceContainer.testing_service],
    config: Settings = Provide[ServiceContainer.config],
) -> None | tuple[dict[str, str], int]:
    """Authenticate all requests to /api endpoints before processing.

    This hook runs before every request to endpoints under the /api blueprint.
    It checks if authentication is required and validates the JWT token.
    If the access token is expired but a refresh token is available, it will
    attempt to refresh the tokens automatically.

    Authentication is skipped if:
    - OIDC_ENABLED is False
    - The endpoint is marked with @public decorator
    - In testing mode with a valid test session

    Returns:
        None if authentication succeeds or is skipped
        Error response tuple if authentication fails
    """
    from flask import current_app, g

    from app.exceptions import AuthenticationException, AuthorizationException
    from app.services.auth_service import AuthContext
    from app.utils.auth import check_authorization

    # Get the actual view function from Flask's view_functions
    endpoint = request.endpoint
    actual_func = current_app.view_functions.get(endpoint) if endpoint else None

    # Skip authentication for public endpoints (check first to avoid unnecessary work)
    if actual_func and getattr(actual_func, "is_public", False):
        logger.debug("Public endpoint - skipping authentication")
        return None

    # In testing mode, check for test session token (bypasses OIDC)
    if config.is_testing:
        token = request.cookies.get(config.oidc_cookie_name)
        if token:
            test_session = testing_service.get_session(token)
            if test_session:
                logger.debug("Test session authenticated: subject=%s", test_session.subject)
                auth_context = AuthContext(
                    subject=test_session.subject,
                    email=test_session.email,
                    name=test_session.name,
                    roles=set(test_session.roles),
                )
                g.auth_context = auth_context
                # Check authorization using decorator-based roles
                try:
                    check_authorization(auth_context, actual_func)
                    return None
                except AuthorizationException as e:
                    logger.warning("Authorization failed: %s", str(e))
                    return {"error": str(e)}, 403

    # Skip authentication if OIDC is disabled
    if not config.oidc_enabled:
        logger.debug("OIDC disabled - skipping authentication")
        return None

    # Authenticate the request (may trigger token refresh)
    logger.debug("Authenticating request to %s %s", request.method, request.path)
    try:
        authenticate_request(auth_service, config, oidc_client_service, actual_func)
        return None
    except AuthenticationException as e:
        logger.warning("Authentication failed: %s", str(e))
        return {"error": str(e)}, 401
    except AuthorizationException as e:
        logger.warning("Authorization failed: %s", str(e))
        return {"error": str(e)}, 403


@api_bp.after_request
@inject
def after_request_set_cookies(
    response: Response,
    config: Settings = Provide[ServiceContainer.config],
) -> Response:
    """Set refreshed auth cookies on response if tokens were refreshed.

    This hook runs after every request to endpoints under the /api blueprint.
    If tokens were refreshed during authentication, it sets the new cookies
    on the response.

    Args:
        response: The Flask response object

    Returns:
        The response with updated cookies if needed
    """
    from flask import g

    # Check if we need to clear cookies (refresh failed)
    if getattr(g, "clear_auth_cookies", False):
        cookie_secure = get_cookie_secure(config)
        response.set_cookie(
            config.oidc_cookie_name,
            "",
            httponly=True,
            secure=cookie_secure,
            samesite=config.oidc_cookie_samesite,
            max_age=0,
        )
        response.set_cookie(
            config.oidc_refresh_cookie_name,
            "",
            httponly=True,
            secure=cookie_secure,
            samesite=config.oidc_cookie_samesite,
            max_age=0,
        )
        return response

    # Check if we have pending tokens from a refresh
    pending = getattr(g, "pending_token_refresh", None)
    if pending:
        cookie_secure = get_cookie_secure(config)

        # Set new access token cookie
        response.set_cookie(
            config.oidc_cookie_name,
            pending.access_token,
            httponly=True,
            secure=cookie_secure,
            samesite=config.oidc_cookie_samesite,
            max_age=pending.access_token_expires_in,
        )

        # Set new refresh token cookie (if provided)
        if pending.refresh_token:
            refresh_max_age = get_token_expiry_seconds(pending.refresh_token)
            if refresh_max_age is None:
                refresh_max_age = pending.access_token_expires_in

            response.set_cookie(
                config.oidc_refresh_cookie_name,
                pending.refresh_token,
                httponly=True,
                secure=cookie_secure,
                samesite=config.oidc_cookie_samesite,
                max_age=refresh_max_age,
            )

        logger.debug("Set refreshed auth cookies on response")

    return response


# Import and register all resource blueprints
# Note: Imports are done after api_bp creation to avoid circular imports
from app.api.auth import auth_bp  # noqa: E402
from app.api.coredumps import coredumps_bp  # noqa: E402
from app.api.device_models import device_models_bp  # noqa: E402
from app.api.devices import devices_bp  # noqa: E402
from app.api.health import health_bp  # noqa: E402
from app.api.images import images_bp  # noqa: E402
from app.api.iot import iot_bp  # noqa: E402
from app.api.pipeline import pipeline_bp  # noqa: E402
from app.api.rotation import rotation_bp  # noqa: E402
from app.api.testing import testing_bp  # noqa: E402

api_bp.register_blueprint(auth_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(coredumps_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(device_models_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(devices_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(health_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(images_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(iot_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(pipeline_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(rotation_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(testing_bp)  # type: ignore[attr-defined]
