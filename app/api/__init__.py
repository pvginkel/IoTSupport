"""API blueprints for IoT Support Backend."""

import logging

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, request

from app.config import Settings
from app.services.auth_service import AuthService
from app.services.container import ServiceContainer
from app.services.testing_service import TestingService
from app.utils.auth import authenticate_request

logger = logging.getLogger(__name__)

# Create main API blueprint
api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.before_request
@inject
def before_request_authentication(
    auth_service: AuthService = Provide[ServiceContainer.auth_service],
    testing_service: TestingService = Provide[ServiceContainer.testing_service],
    config: Settings = Provide[ServiceContainer.config],
) -> None | tuple[dict[str, str], int]:
    """Authenticate all requests to /api endpoints before processing.

    This hook runs before every request to endpoints under the /api blueprint.
    It checks if authentication is required and validates the JWT token.

    Authentication is skipped if:
    - OIDC_ENABLED is False
    - The endpoint is marked with @public decorator
    - In testing mode with a valid test session

    Returns:
        None if authentication succeeds or is skipped
        Error response tuple if authentication fails
    """
    from flask import g

    from app.exceptions import AuthenticationException, AuthorizationException
    from app.services.auth_service import AuthContext

    # Skip authentication for public endpoints (check first to avoid unnecessary work)
    view_func = request.endpoint
    if view_func:
        # Get the actual view function from Flask's view_functions
        from flask import current_app

        actual_func = current_app.view_functions.get(view_func)
        if actual_func and getattr(actual_func, "is_public", False):
            logger.debug("Public endpoint - skipping authentication")
            return None

    # In testing mode, check for test sessions (before OIDC check to avoid JWKS discovery)
    if config.is_testing:
        token = request.cookies.get(config.OIDC_COOKIE_NAME)
        if token and token.startswith("test-session-"):
            test_session = testing_service.get_session(token)
            if test_session:
                # Create auth context from test session
                g.auth_context = AuthContext(
                    subject=test_session.subject,
                    email=test_session.email,
                    name=test_session.name,
                    roles=set(test_session.roles),
                )
                logger.debug("Test session authenticated: subject=%s", test_session.subject)
                return None
        # In testing mode without valid test session, require authentication
        # (don't skip even if OIDC is disabled - return 401)
        if not config.OIDC_ENABLED:
            logger.warning("Testing mode: No valid test session and OIDC disabled")
            return {"error": "No valid test session provided"}, 401

    # Skip authentication if OIDC is disabled (non-testing mode only)
    if not config.OIDC_ENABLED:
        logger.debug("OIDC disabled - skipping authentication")
        return None

    # Authenticate the request
    logger.debug("Authenticating request to %s %s", request.method, request.path)
    try:
        authenticate_request(auth_service, config)
        return None
    except AuthenticationException as e:
        logger.warning("Authentication failed: %s", str(e))
        return {"error": str(e)}, 401
    except AuthorizationException as e:
        logger.warning("Authorization failed: %s", str(e))
        return {"error": str(e)}, 403


# Import and register all resource blueprints
# Note: Imports are done after api_bp creation to avoid circular imports
from app.api.assets import assets_bp  # noqa: E402
from app.api.auth import auth_bp  # noqa: E402
from app.api.configs import configs_bp  # noqa: E402
from app.api.health import health_bp  # noqa: E402
from app.api.images import images_bp  # noqa: E402
from app.api.testing import testing_bp  # noqa: E402

api_bp.register_blueprint(assets_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(auth_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(configs_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(health_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(images_bp)  # type: ignore[attr-defined]
api_bp.register_blueprint(testing_bp)  # type: ignore[attr-defined]
