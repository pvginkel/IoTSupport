"""Authentication utilities for OIDC integration."""

import functools
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from flask import g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings
from app.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ValidationException,
)
from app.services.auth_service import AuthContext, AuthService
from app.services.oidc_client_service import AuthState

logger = logging.getLogger(__name__)


def public(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to mark an endpoint as publicly accessible (no authentication required).

    Usage:
        @some_bp.route("/health")
        @public
        def health_check():
            return {"status": "healthy"}
    """
    func.is_public = True  # type: ignore[attr-defined]
    return func


def get_auth_context() -> AuthContext | None:
    """Get the current authentication context from flask.g.

    Returns:
        AuthContext if user is authenticated, None otherwise
    """
    return getattr(g, "auth_context", None)


def requires_role(role: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to require a specific role for endpoint access.

    Args:
        role: Required role name

    Usage:
        @some_bp.route("/admin")
        @requires_role("admin")
        def admin_endpoint():
            return {"data": "sensitive"}
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            auth_context = get_auth_context()
            if not auth_context:
                raise AuthenticationException("Authentication required")

            if role not in auth_context.roles:
                raise AuthorizationException(
                    f"Insufficient permissions - '{role}' role required"
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator


def extract_token_from_request(config: Settings) -> str | None:
    """Extract JWT token from request cookie or Authorization header.

    Checks cookie first, then Authorization header with Bearer prefix.

    Args:
        config: Application settings for cookie name

    Returns:
        JWT token string or None if not found
    """
    # Check cookie first
    token = request.cookies.get(config.OIDC_COOKIE_NAME)
    if token:
        logger.debug("Token extracted from cookie")
        return token

    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            logger.debug("Token extracted from Authorization header")
            return parts[1]

    return None


def check_authorization(auth_context: AuthContext, config: Settings) -> None:
    """Check if user has required authorization for the current request.

    Authorization rules:
    - Admin role grants full access to all endpoints
    - Asset-uploader role grants access only to POST /api/assets
    - No other roles are recognized

    Args:
        auth_context: Authenticated user context
        config: Application settings for role names

    Raises:
        AuthorizationException: If user lacks required permissions
    """
    # Admin role grants full access
    if config.OIDC_ADMIN_ROLE in auth_context.roles:
        logger.debug("User has admin role - full access granted")
        return

    # Asset-uploader role grants access only to POST /api/assets
    if config.OIDC_ASSET_ROLE in auth_context.roles:
        if request.method == "POST" and request.path == "/api/assets":
            logger.debug("User has asset-uploader role - asset upload granted")
            return
        else:
            raise AuthorizationException(
                f"Insufficient permissions - '{config.OIDC_ASSET_ROLE}' role only permits uploading assets"
            )

    # No recognized roles
    raise AuthorizationException(
        "Insufficient permissions - no recognized roles in token"
    )


def authenticate_request(auth_service: AuthService, config: Settings) -> None:
    """Authenticate the current request and store auth context in flask.g.

    This function is called by the before_request hook for all /api requests.

    Args:
        auth_service: AuthService instance for token validation
        config: Application settings

    Raises:
        AuthenticationException: If token is missing, invalid, or expired
        AuthorizationException: If user lacks required permissions
    """
    # Extract token from request
    token = extract_token_from_request(config)
    if not token:
        raise AuthenticationException("No valid token provided")

    # Validate token and get auth context
    auth_context = auth_service.validate_token(token)

    # Store auth context in flask.g
    g.auth_context = auth_context

    # Check authorization for this request
    check_authorization(auth_context, config)

    logger.info(
        "Request authenticated: subject=%s email=%s roles=%s",
        auth_context.subject,
        auth_context.email,
        auth_context.roles,
    )


def serialize_auth_state(auth_state: AuthState, secret_key: str) -> str:
    """Serialize and sign AuthState for storage in cookie.

    Args:
        auth_state: AuthState to serialize
        secret_key: Secret key for signing

    Returns:
        Signed serialized auth state string
    """
    serializer = URLSafeTimedSerializer(secret_key)
    data = {
        "code_verifier": auth_state.code_verifier,
        "redirect_url": auth_state.redirect_url,
        "nonce": auth_state.nonce,
    }
    return serializer.dumps(data)


def deserialize_auth_state(signed_data: str, secret_key: str, max_age: int = 600) -> AuthState:
    """Deserialize and verify AuthState from signed cookie.

    Args:
        signed_data: Signed serialized auth state
        secret_key: Secret key for verification
        max_age: Maximum age in seconds (default 10 minutes)

    Returns:
        AuthState instance

    Raises:
        ValidationException: If signature is invalid or data expired
    """
    serializer = URLSafeTimedSerializer(secret_key)
    try:
        data = serializer.loads(signed_data, max_age=max_age)
        return AuthState(
            code_verifier=data["code_verifier"],
            redirect_url=data["redirect_url"],
            nonce=data["nonce"],
        )
    except SignatureExpired as e:
        raise ValidationException("Authentication state expired") from e
    except BadSignature as e:
        raise ValidationException("Invalid authentication state") from e
    except (KeyError, TypeError) as e:
        raise ValidationException("Malformed authentication state") from e


def get_cookie_secure(config: Settings) -> bool:
    """Determine if cookies should use Secure flag.

    If OIDC_COOKIE_SECURE is explicitly set, use that value.
    Otherwise, infer from BASEURL (true for HTTPS, false for HTTP).

    Args:
        config: Application settings

    Returns:
        True if cookies should use Secure flag, False otherwise
    """
    if config.OIDC_COOKIE_SECURE is not None:
        return config.OIDC_COOKIE_SECURE
    return config.BASEURL.startswith("https://")


def validate_redirect_url(redirect_url: str, base_url: str) -> None:
    """Validate redirect URL to prevent open redirect attacks.

    Only allows relative URLs or URLs matching the base URL origin.

    Args:
        redirect_url: URL to validate
        base_url: Base URL (BASEURL from config)

    Raises:
        ValidationException: If redirect URL is invalid or external
    """
    # Parse URLs
    redirect_parsed = urlparse(redirect_url)
    base_parsed = urlparse(base_url)

    # Allow relative URLs (no scheme or netloc)
    if not redirect_parsed.scheme and not redirect_parsed.netloc:
        return

    # Allow URLs with same origin as base URL
    if (
        redirect_parsed.scheme == base_parsed.scheme
        and redirect_parsed.netloc == base_parsed.netloc
    ):
        return

    # Reject external URLs
    raise ValidationException(
        "Invalid redirect URL - external redirects not allowed"
    )
