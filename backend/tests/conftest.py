"""Pytest configuration and fixtures."""

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask
from prometheus_client import REGISTRY

from app import create_app
from app.config import Settings
from app.services.container import ServiceContainer


@pytest.fixture(autouse=True)
def clear_prometheus_registry() -> Generator[None, None, None]:
    """Clear Prometheus registry before and after each test to ensure isolation.

    This is necessary for tests that create multiple Flask app instances or services
    that register Prometheus metrics, as metrics cannot be registered twice in the
    same registry. Clearing before AND after each test ensures proper isolation.
    """
    # Clear collectors before test
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except (KeyError, ValueError):
            # Collector may have already been unregistered or not exist
            pass
    yield
    # Clean up after test
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except (KeyError, ValueError):
            pass


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test configs."""
    return tmp_path


@pytest.fixture
def test_settings(config_dir: Path, tmp_path: Path) -> Settings:
    """Create test settings with temporary config directory."""
    # Create temporary assets directory and signing key for tests
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()

    # Create a valid RSA signing key file for all tests
    signing_key_path = tmp_path / "test_signing_key.pem"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    signing_key_path.write_bytes(pem)

    return Settings(
        ESP32_CONFIGS_DIR=config_dir,
        ASSETS_DIR=assets_dir,
        SIGNING_KEY_PATH=signing_key_path,
        TIMESTAMP_TOLERANCE_SECONDS=300,
        SECRET_KEY="test-secret-key",
        DEBUG=True,
        CORS_ORIGINS=["http://localhost:3000"],
    )


@pytest.fixture
def app(test_settings: Settings) -> Generator[Flask, None, None]:
    """Create Flask app for testing."""
    app = create_app(test_settings)
    yield app


@pytest.fixture
def client(app: Flask) -> Any:
    """Create test client."""
    return app.test_client()


@pytest.fixture
def container(app: Flask) -> ServiceContainer:
    """Access to the DI container for testing."""
    return app.container


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Sample configuration data."""
    return {
        "deviceName": "Living Room Sensor",
        "deviceEntityId": "sensor.living_room",
        "enableOTA": True,
        "mqttBroker": "mqtt.local",
        "updateInterval": 60,
    }


@pytest.fixture
def sample_config_minimal() -> dict[str, Any]:
    """Sample configuration with minimal fields."""
    return {
        "mqttBroker": "mqtt.local",
    }


@pytest.fixture
def make_config_file(config_dir: Path) -> Any:
    """Factory fixture for creating config files."""

    def _make(mac_address: str, content: dict[str, Any]) -> Path:
        file_path = config_dir / f"{mac_address}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
        return file_path

    return _make


@pytest.fixture
def make_asset_file(test_settings: Settings) -> Any:
    """Factory fixture for creating asset files."""

    def _make(filename: str, content: bytes) -> Path:
        file_path = test_settings.ASSETS_DIR / filename
        file_path.write_bytes(content)
        return file_path

    return _make


@pytest.fixture
def valid_mac() -> str:
    """Valid MAC address for testing."""
    return "aa-bb-cc-dd-ee-ff"


@pytest.fixture
def another_valid_mac() -> str:
    """Another valid MAC address for testing."""
    return "11-22-33-44-55-66"
