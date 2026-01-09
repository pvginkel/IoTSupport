"""Utility modules for the IoT support backend."""

import uuid


def get_current_correlation_id() -> str:
    """Get or generate a correlation ID for the current request.

    Returns:
        A unique correlation ID string
    """
    # In a production setup, this would read from flask.g or request headers
    # For now, generate a new UUID
    return str(uuid.uuid4())
