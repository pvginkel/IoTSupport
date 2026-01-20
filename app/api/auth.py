"""Authentication endpoints for OIDC BFF pattern."""

import logging
from typing import Any

from dependency_injector.wiring import Provide, inject
from flask import Blueprint, make_response, redirect, request
from pydantic import BaseModel, Field
from spectree import Response as SpectreeResponse

from app.config import Settings
from app.exceptions import ValidationException
from app.services.auth_service import AuthService
from app.services.container import ServiceContainer
from app.services.oidc_client_service import OidcClientService
from app.utils.auth import (
    deserialize_auth_state,
    get_auth_context,
    get_cookie_secure,
    public,
    serialize_auth_state,
    validate_redirect_url,
)
from app.utils.error_handling import handle_api_errors
from app.utils.spectree_config import api

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


class UserInfoResponseSchema(BaseModel):
    """Response schema for current user information."""

    subject: str = Field(description="User subject (sub claim from JWT)")
    email: str | None = Field(description="User email address")
    name: str | None = Field(description="User display name")
    roles: list[str] = Field(description="User roles")


@auth_bp.route("/self", methods=["GET"])
@public
@api.validate(resp=SpectreeResponse(HTTP_200=UserInfoResponseSchema))
@handle_api_errors
@inject
def get_current_user(
    auth_service: AuthService = Provide[ServiceContainer.auth_service],
    config: Settings = Provide[ServiceContainer.config],
) -> tuple[dict[str, Any], int]:
    """Get current authenticated user information.

    Returns user information from the validated JWT token in the cookie.

    This endpoint is marked @public because it handles authentication
    explicitly - it returns 401 if not authenticated rather than relying
    on the before_request hook.

    Returns:
        200: User information from validated token
        401: No valid token provided or token invalid
    """
    # Check if OIDC is enabled
    if not config.OIDC_ENABLED:
        # Return a default "admin" user when auth is disabled
        return UserInfoResponseSchema(
            subject="local-user",
            email="admin@local",
            name="Local Admin",
            roles=["admin"],
        ).model_dump(), 200

    # Try to get auth context (manually validate token)
    auth_context = get_auth_context()
    if not auth_context:
        # Auth context not set - try to validate token directly
        from app.utils.auth import extract_token_from_request

        token = extract_token_from_request(config)
        if not token:
            from app.exceptions import AuthenticationException

            raise AuthenticationException("No valid token provided")

        auth_context = auth_service.validate_token(token)

    # Return user information
    user_info = UserInfoResponseSchema(
        subject=auth_context.subject,
        email=auth_context.email,
        name=auth_context.name,
        roles=sorted(auth_context.roles),
    )

    logger.info(
        "Returned user info for subject=%s email=%s",
        auth_context.subject,
        auth_context.email,
    )

    return user_info.model_dump(), 200


@auth_bp.route("/login", methods=["GET"])
@public
@handle_api_errors
@inject
def login(
    oidc_client_service: OidcClientService = Provide[ServiceContainer.oidc_client_service],
    config: Settings = Provide[ServiceContainer.config],
) -> Any:
    """Initiate OIDC login flow with PKCE.

    Generates authorization URL and redirects to OIDC provider.
    Stores PKCE state in signed cookie.

    Query Parameters:
        redirect: URL to redirect to after successful login (required)

    Returns:
        302: Redirect to OIDC provider authorization endpoint
        400: Missing or invalid redirect parameter
    """
    # Check if OIDC is enabled
    if not config.OIDC_ENABLED:
        raise ValidationException("Authentication is not enabled")

    # Get and validate redirect parameter
    redirect_url = request.args.get("redirect")
    if not redirect_url:
        raise ValidationException("Missing required 'redirect' parameter")

    # Validate redirect URL to prevent open redirect attacks
    validate_redirect_url(redirect_url, config.BASEURL)

    # Generate authorization URL with PKCE
    authorization_url, auth_state = oidc_client_service.generate_authorization_url(
        redirect_url
    )

    # Serialize auth state into signed cookie
    signed_state = serialize_auth_state(auth_state, config.SECRET_KEY)

    # Determine cookie security settings
    cookie_secure = get_cookie_secure(config)

    # Create response with redirect
    response = make_response(redirect(authorization_url))

    # Set auth state cookie (short-lived, for callback only)
    response.set_cookie(
        "auth_state",
        signed_state,
        httponly=True,
        secure=cookie_secure,
        samesite=config.OIDC_COOKIE_SAMESITE,
        max_age=600,  # 10 minutes
    )

    logger.info("Login initiated: redirecting to OIDC provider")

    return response


@auth_bp.route("/callback", methods=["GET"])
@public
@handle_api_errors
@inject
def callback(
    oidc_client_service: OidcClientService = Provide[ServiceContainer.oidc_client_service],
    auth_service: AuthService = Provide[ServiceContainer.auth_service],
    config: Settings = Provide[ServiceContainer.config],
) -> Any:
    """Handle OIDC callback after user authorization.

    Exchanges authorization code for tokens and sets access token cookie.

    Query Parameters:
        code: Authorization code from OIDC provider
        state: CSRF token from OIDC provider

    Returns:
        302: Redirect to original redirect URL with access token cookie set
        400: Invalid or missing callback parameters
        401: Token exchange failed
    """
    # Check if OIDC is enabled
    if not config.OIDC_ENABLED:
        raise ValidationException("Authentication is not enabled")

    # Get callback parameters
    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        raise ValidationException("Missing 'code' parameter in callback")
    if not state:
        raise ValidationException("Missing 'state' parameter in callback")

    # Retrieve and verify auth state cookie
    signed_state = request.cookies.get("auth_state")
    if not signed_state:
        raise ValidationException("Missing authentication state cookie")

    auth_state = deserialize_auth_state(signed_state, config.SECRET_KEY)

    # Verify state matches
    if state != auth_state.nonce:
        raise ValidationException("State parameter does not match")

    # Exchange authorization code for tokens
    token_response = oidc_client_service.exchange_code_for_tokens(
        code, auth_state.code_verifier
    )

    # Validate access token
    auth_context = auth_service.validate_token(token_response.access_token)

    logger.info(
        "OIDC callback completed: subject=%s email=%s redirecting to %s",
        auth_context.subject,
        auth_context.email,
        auth_state.redirect_url,
    )

    # Determine cookie security settings
    # Determine cookie security settings
    cookie_secure = get_cookie_secure(config)

    # Create response with redirect to original URL
    response = make_response(redirect(auth_state.redirect_url))

    # Set access token cookie (long-lived)
    response.set_cookie(
        config.OIDC_COOKIE_NAME,
        token_response.access_token,
        httponly=True,
        secure=cookie_secure,
        samesite=config.OIDC_COOKIE_SAMESITE,
        max_age=token_response.expires_in,
    )

    # Clear auth state cookie
    response.set_cookie(
        "auth_state",
        "",
        httponly=True,
        secure=cookie_secure,
        samesite=config.OIDC_COOKIE_SAMESITE,
        max_age=0,
    )

    return response


@auth_bp.route("/logout", methods=["GET"])
@public
@inject
def logout(
    config: Settings = Provide[ServiceContainer.config],
) -> Any:
    """Log out current user.

    Clears access token cookie and redirects to specified URL.

    Query Parameters:
        redirect: URL to redirect to after logout (default: /)

    Returns:
        302: Redirect to logout URL with cookie cleared
    """
    # Get redirect parameter (default to /)
    redirect_url = request.args.get("redirect", "/")

    # Validate redirect URL to prevent open redirect attacks
    validate_redirect_url(redirect_url, config.BASEURL)

    # Determine cookie security settings
    # Determine cookie security settings
    cookie_secure = get_cookie_secure(config)

    # Create response with redirect
    response = make_response(redirect(redirect_url))

    # Clear access token cookie
    response.set_cookie(
        config.OIDC_COOKIE_NAME,
        "",
        httponly=True,
        secure=cookie_secure,
        samesite=config.OIDC_COOKIE_SAMESITE,
        max_age=0,
    )

    logger.info("User logged out: redirecting to %s", redirect_url)

    return response
