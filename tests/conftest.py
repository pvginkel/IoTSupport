"""Pytest configuration and fixtures."""

import sqlite3
import struct
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from app.services.device_model_service import DeviceModelService
    from app.services.device_service import DeviceService
from flask import Flask
from prometheus_client import REGISTRY
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import create_app
from app.config import Settings
from app.database import upgrade_database
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


def _build_test_settings(tmp_path: Path) -> Settings:
    """Construct base Settings object for tests.

    Settings is now a plain Pydantic BaseModel with lowercase fields.
    For tests, we construct it directly instead of using Settings.load().
    """
    # Create temporary assets directory for firmware storage
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(exist_ok=True)

    # Create temporary coredumps directory
    coredumps_dir = tmp_path / "coredumps"
    coredumps_dir.mkdir(exist_ok=True)

    return Settings(
        # Flask settings
        secret_key="test-secret-key",
        flask_env="development",
        debug=True,
        # Database settings
        database_url="sqlite:///:memory:",
        # Firmware storage
        assets_dir=assets_dir,
        # Coredump storage
        coredumps_dir=coredumps_dir,
        # Coredump parsing sidecar (not configured by default in tests)
        parse_sidecar_xfer_dir=None,
        parse_sidecar_url=None,
        max_coredumps=20,
        # CORS settings
        cors_origins=["http://localhost:3000"],
        # MQTT settings
        mqtt_url="mqtt://mqtt.example.com:1883",
        device_mqtt_url="mqtt://mqtt.example.com:1883",
        mqtt_username=None,
        mqtt_password=None,
        # OIDC settings (disabled for most tests)
        baseurl="http://localhost:3200",
        device_baseurl="http://localhost:3200",
        oidc_enabled=False,
        oidc_issuer_url="https://auth.example.com/realms/iot",
        oidc_client_id="iot-support",
        oidc_client_secret=None,
        oidc_scopes="openid profile email",
        oidc_audience="iot-support",
        oidc_clock_skew_seconds=30,
        oidc_cookie_name="access_token",
        oidc_cookie_secure=False,
        oidc_cookie_samesite="Lax",
        oidc_refresh_cookie_name="refresh_token",
        # Keycloak Admin API settings
        oidc_token_url="https://auth.example.com/realms/iot/protocol/openid-connect/token",
        keycloak_base_url="https://auth.example.com",
        keycloak_realm="iot",
        keycloak_admin_client_id="iot-admin",
        keycloak_admin_client_secret="admin-secret",
        keycloak_device_scope_name="iot-device-audience",
        keycloak_admin_url="https://auth.example.com/admin/realms/iot",
        keycloak_console_base_url="https://auth.example.com/admin/master/console/#/iot/clients",
        # WiFi credentials for provisioning
        wifi_ssid="TestNetwork",
        wifi_password="test-wifi-password",
        # Rotation settings
        rotation_cron="0 8 * * 6#1",
        rotation_timeout_seconds=300,
        rotation_critical_threshold_days=7,
        # Elasticsearch settings
        elasticsearch_url="http://elasticsearch.test:9200",
        elasticsearch_username=None,
        elasticsearch_password=None,
        elasticsearch_index_pattern="logstash-http-*",
        # MQTT client ID
        mqtt_client_id="iotsupport-backend",
        # Graceful shutdown timeout
        graceful_shutdown_timeout=30,
        # Fernet key (derived from "test-secret-key" using SHA256 + base64)
        fernet_key="LOrG82NjxiRqZMyoBc1DynoBsU6y_MUyzuw_YPL33xw=",
    )


def _override_settings_for_sqlite(settings: Settings, conn: sqlite3.Connection) -> Settings:
    """Create a copy of settings configured for SQLite with static pool."""
    new_settings = settings.model_copy(
        update={
            "database_url": "sqlite://",
            "sqlalchemy_engine_options": {
                "poolclass": StaticPool,
                "creator": lambda: conn,
            },
        }
    )
    return new_settings


@pytest.fixture(scope="session")
def session_tmp_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped temporary path for test fixtures."""
    return tmp_path_factory.mktemp("session")


@pytest.fixture(scope="session")
def template_connection(session_tmp_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Create a template SQLite database once and apply migrations."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)

    settings = _override_settings_for_sqlite(_build_test_settings(session_tmp_path), conn)

    template_app = create_app(settings)
    with template_app.app_context():
        upgrade_database(recreate=True)

    yield conn

    conn.close()


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Create test settings with in-memory database."""
    return _build_test_settings(tmp_path)


@pytest.fixture
def app(test_settings: Settings, template_connection: sqlite3.Connection) -> Generator[Flask, None, None]:
    """Create Flask app for testing using a fresh copy of the template database."""
    clone_conn = sqlite3.connect(":memory:", check_same_thread=False)
    template_connection.backup(clone_conn)

    settings = _override_settings_for_sqlite(test_settings, clone_conn)

    app = create_app(settings)

    try:
        yield app
    finally:
        with app.app_context():
            from app.extensions import db as flask_db

            flask_db.session.remove()

        clone_conn.close()


@pytest.fixture
def session(container: ServiceContainer) -> Generator[Session, None, None]:
    """Create a new database session for a test."""
    session = container.db_session()

    exc = None
    try:
        yield session
    except Exception as e:
        exc = e

    if exc:
        session.rollback()
    else:
        session.commit()
    session.close()

    container.db_session.reset()


@pytest.fixture
def client(app: Flask) -> Any:
    """Create test client."""
    return app.test_client()


@pytest.fixture
def container(app: Flask) -> ServiceContainer:
    """Access to the DI container for testing with session provided."""
    container = app.container

    with app.app_context():
        # Ensure SessionLocal is initialized for tests
        from sqlalchemy.orm import sessionmaker

        from app.extensions import db as flask_db

        SessionLocal = sessionmaker(
            bind=flask_db.engine, autoflush=True, expire_on_commit=False
        )

    container.session_maker.override(SessionLocal)

    return container


@pytest.fixture
def sample_device_config() -> str:
    """Sample device configuration as JSON string."""
    return '{"deviceName": "Living Room Sensor", "deviceEntityId": "sensor.living_room", "enableOTA": true, "mqttBroker": "mqtt.local", "updateInterval": 60}'


@pytest.fixture
def sample_device_config_dict() -> dict[str, Any]:
    """Sample device configuration as dict (for assertions)."""
    return {
        "deviceName": "Living Room Sensor",
        "deviceEntityId": "sensor.living_room",
        "enableOTA": True,
        "mqttBroker": "mqtt.local",
        "updateInterval": 60,
    }


@pytest.fixture
def device_model_service(container: ServiceContainer) -> "DeviceModelService":
    """Create DeviceModelService instance via the container.

    Use this fixture in service tests to avoid app.app_context() boilerplate.
    """
    return container.device_model_service()


@pytest.fixture
def device_service(container: ServiceContainer) -> "DeviceService":
    """Create DeviceService instance via the container.

    Use this fixture in service tests to avoid app.app_context() boilerplate.
    """
    return container.device_service()


@pytest.fixture
def make_device_model(container: ServiceContainer) -> Any:
    """Factory fixture for creating device model records in tests.

    Usage:
        model = make_device_model("tempsensor", "Temperature Sensor")
    """
    from app.models.device import DeviceModel

    def _make(code: str, name: str) -> DeviceModel:
        service = container.device_model_service()
        return service.create_device_model(code=code, name=name)

    return _make


@pytest.fixture
def make_device(container: ServiceContainer) -> Any:
    """Factory fixture for creating device records in tests.

    Usage:
        device = make_device(model.id, '{"setting": "value"}')
    """
    from unittest.mock import MagicMock, patch

    from app.models.device import Device

    def _make(device_model_id: int, config: str = "{}") -> Device:
        # Mock Keycloak for device creation in tests
        with patch.object(
            container.keycloak_admin_service(),
            "create_client",
            return_value=MagicMock(client_id="test", secret="test-secret"),
        ), patch.object(
            container.keycloak_admin_service(),
            "update_client_metadata",
        ):
            service = container.device_service()
            return service.create_device(device_model_id=device_model_id, config=config)

    return _make


@pytest.fixture
def make_asset_file(test_settings: Settings) -> Any:
    """Factory fixture for creating asset files."""

    def _make(filename: str, content: bytes) -> Path:
        file_path = test_settings.assets_dir / filename
        file_path.write_bytes(content)
        return file_path

    return _make


@pytest.fixture
def mock_oidc_discovery() -> dict[str, Any]:
    """Mock OIDC discovery document."""
    return {
        "issuer": "https://auth.example.com/realms/iot",
        "authorization_endpoint": "https://auth.example.com/realms/iot/protocol/openid-connect/auth",
        "token_endpoint": "https://auth.example.com/realms/iot/protocol/openid-connect/token",
        "end_session_endpoint": "https://auth.example.com/realms/iot/protocol/openid-connect/logout",
        "jwks_uri": "https://auth.example.com/realms/iot/protocol/openid-connect/certs",
    }


@pytest.fixture
def mock_jwks() -> dict[str, Any]:
    """Mock JWKS (JSON Web Key Set)."""
    return {
        "keys": [
            {
                "kid": "test-key-id",
                "kty": "RSA",
                "use": "sig",
                "n": "test-modulus",
                "e": "AQAB",
            }
        ]
    }


@pytest.fixture
def generate_test_jwt(test_settings: Settings) -> Any:
    """Factory fixture to generate test JWT tokens."""
    import time

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    # Generate RSA keypair for testing
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    def _generate(
        subject: str = "test-user",
        email: str | None = "test@example.com",
        name: str | None = "Test User",
        roles: list[str] | None = None,
        expired: bool = False,
        invalid_signature: bool = False,
        invalid_issuer: bool = False,
        invalid_audience: bool = False,
    ) -> str:
        """Generate a test JWT token.

        Args:
            subject: Subject claim (sub)
            email: Email claim
            name: Name claim
            roles: List of roles (stored in realm_access.roles)
            expired: Whether token should be expired
            invalid_signature: Whether to use wrong key for signing
            invalid_issuer: Whether to use wrong issuer
            invalid_audience: Whether to use wrong audience

        Returns:
            JWT token string
        """
        if roles is None:
            roles = ["admin"]

        now = int(time.time())
        exp = now - 3600 if expired else now + 3600

        payload = {
            "sub": subject,
            "iss": "https://wrong.example.com" if invalid_issuer else test_settings.oidc_issuer_url,
            "aud": "wrong-client-id" if invalid_audience else test_settings.oidc_client_id,
            "exp": exp,
            "iat": now,
            "realm_access": {"roles": roles},
        }

        if email:
            payload["email"] = email
        if name:
            payload["name"] = name

        # Use wrong key if invalid_signature requested
        signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if invalid_signature else private_key

        token = jwt.encode(payload, signing_key, algorithm="RS256", headers={"kid": "test-key-id"})
        return token

    # Attach public key for test verification
    _generate.public_key = public_key  # type: ignore
    _generate.private_key = private_key  # type: ignore

    return _generate


def create_test_firmware(version: bytes) -> bytes:
    """Create a test firmware binary with valid ESP32 AppInfo header.

    Shared helper used across firmware-related test files to build a
    minimal but valid ESP32 binary with the given version string.

    Args:
        version: Version bytes (e.g. b"1.0.0")

    Returns:
        Bytes representing a valid ESP32 firmware binary
    """
    # ESP32 image header (24 bytes) + segment header (8 bytes)
    image_header = bytes(24)
    segment_header = bytes(8)

    # AppInfo structure (256 bytes)
    magic = struct.pack("<I", 0xABCD5432)
    secure_version = struct.pack("<I", 0)
    reserved1 = bytes(8)
    version_field = version.ljust(32, b"\x00")[:32]
    project_name = b"test_project".ljust(32, b"\x00")
    compile_time = b"12:00:00".ljust(16, b"\x00")
    compile_date = b"Jan 01 2024".ljust(16, b"\x00")
    idf_version = b"v5.0".ljust(32, b"\x00")
    app_elf_sha256 = bytes(32)
    reserved_rest = bytes(256 - 4 - 4 - 8 - 32 - 32 - 16 - 16 - 32 - 32)

    app_info = (
        magic + secure_version + reserved1 + version_field
        + project_name + compile_time + compile_date + idf_version
        + app_elf_sha256 + reserved_rest
    )

    return image_header + segment_header + app_info
