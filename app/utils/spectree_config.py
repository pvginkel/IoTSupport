"""SpectTree configuration with Pydantic v2 compatibility."""

from typing import Any

from flask import Flask, redirect
from spectree import SpecTree

# Global Spectree instance that can be imported by API modules.
# This will be initialized by configure_spectree() before any imports of the API modules.
api: SpecTree = None  # type: ignore


def configure_spectree(app: Flask) -> SpecTree:
    """Configure Spectree with proper Pydantic v2 integration and custom settings.

    Returns:
        SpecTree: Configured Spectree instance
    """
    global api

    # Create Spectree instance with Flask backend
    api = SpecTree(
        backend_name="flask",
        title="IoT Support API",
        version="1.0.0",
        description="REST API for managing ESP32 IoT device configurations",
        path="api/docs",  # OpenAPI docs available at /api/docs
        validation_error_status=400,
    )

    # Register the SpecTree with the Flask app to create documentation routes
    api.register(app)

    # Add redirect routes for convenience
    @app.route("/api/docs")
    @app.route("/api/docs/")
    def docs_redirect() -> Any:
        return redirect("/api/docs/swagger/", code=302)

    return api
