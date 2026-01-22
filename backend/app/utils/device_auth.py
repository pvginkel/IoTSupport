"""Device authentication utilities for the /iot blueprint."""

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import g, request

from app.exceptions import AuthenticationException

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

# Pattern for device client ID: iotdevice-<model_code>-<device_key>
DEVICE_CLIENT_ID_PATTERN = re.compile(r"^iotdevice-([a-z0-9_]+)-([a-z0-9]{8})$")


@dataclass
class DeviceAuthContext:
    """Authentication context for device requests."""

    device_key: str  # 8-character device key
    model_code: str  # Device model code
    client_id: str  # Full Keycloak client ID
    token_iat: int | None  # Token issued-at timestamp (for rotation detection)


def extract_token_from_request(config: "Settings") -> str | None:
    """Extract JWT token from Authorization header.

    Device authentication only uses Authorization header (no cookies).

    Args:
        config: Application settings (not used currently, for consistency)

    Returns:
        JWT token string or None if not found
    """
    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    return None


def parse_device_client_id(client_id: str) -> tuple[str, str]:
    """Parse device client ID to extract model code and device key.

    Args:
        client_id: Keycloak client ID (format: iotdevice-<model>-<key>)

    Returns:
        Tuple of (model_code, device_key)

    Raises:
        AuthenticationException: If client ID format is invalid
    """
    match = DEVICE_CLIENT_ID_PATTERN.match(client_id)
    if not match:
        raise AuthenticationException(
            f"Invalid device client ID format: {client_id}"
        )
    return match.group(1), match.group(2)


def authenticate_device_request(
    auth_service: "AuthService",
    config: "Settings",
) -> None:
    """Authenticate a device request and store context in flask.g.

    Validates the JWT token from the Authorization header, extracts
    the device key from the authorized party (azp) claim, and stores
    the device auth context in flask.g.device_auth_context.

    Args:
        auth_service: AuthService for token validation
        config: Application settings

    Raises:
        AuthenticationException: If authentication fails
    """
    # Extract token from request
    token = extract_token_from_request(config)
    if not token:
        raise AuthenticationException("No valid token provided")

    # Validate token - this will raise AuthenticationException if invalid
    auth_service.validate_token(token)

    # For M2M device tokens, the authorized party (azp) contains the client ID
    # We need to decode the token again to get the azp claim
    import jwt

    # Decode without verification just to get claims (already verified above)
    try:
        unverified_payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as e:
        raise AuthenticationException(f"Failed to decode token claims: {e}") from e

    # Get client ID from azp (authorized party) claim
    client_id = unverified_payload.get("azp")
    if not client_id:
        raise AuthenticationException("Token missing 'azp' claim")

    # Parse device info from client ID
    try:
        model_code, device_key = parse_device_client_id(client_id)
    except AuthenticationException:
        raise

    # Get token issued-at time for rotation detection
    token_iat = unverified_payload.get("iat")

    # Store device auth context
    g.device_auth_context = DeviceAuthContext(
        device_key=device_key,
        model_code=model_code,
        client_id=client_id,
        token_iat=token_iat,
    )

    logger.debug(
        "Device authenticated: key=%s model=%s client_id=%s",
        device_key,
        model_code,
        client_id,
    )


def get_device_auth_context() -> DeviceAuthContext | None:
    """Get the current device authentication context.

    Returns:
        DeviceAuthContext if device is authenticated, None otherwise
    """
    return getattr(g, "device_auth_context", None)


def require_device_auth() -> DeviceAuthContext:
    """Get device auth context, raising if not authenticated.

    Returns:
        DeviceAuthContext

    Raises:
        AuthenticationException: If device is not authenticated
    """
    ctx = get_device_auth_context()
    if ctx is None:
        raise AuthenticationException("Device authentication required")
    return ctx
