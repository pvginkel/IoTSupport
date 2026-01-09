"""Custom Flask application class."""

from flask import Flask

from app.services.container import ServiceContainer


class App(Flask):
    """Custom Flask application with container reference."""

    container: ServiceContainer
