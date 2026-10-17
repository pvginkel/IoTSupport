"""Pytest configuration and fixtures.

Infrastructure fixtures (app, client, session, OIDC) are defined in
conftest_infrastructure.py. This file re-exports them and adds IoT-specific
domain fixtures.
"""

import os
import struct
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import requests

from app.app_config import AppSettings
from app.config import Settings
from app.services.container import ServiceContainer

if TYPE_CHECKING:
    from app.services.device_model_service import DeviceModelService
    from app.services.device_service import DeviceService

# Import all infrastructure fixtures
from tests.conftest_infrastructure import *  # noqa: F403

# ---------------------------------------------------------------------------
# OpenSearch pre-flight, for CI. The template's pre-flight is the
# pytest_configure star-imported above (S3, PostgreSQL), and its
# scripts/wait-for-services.py waits for those two before the suites. In the
# validation pod OpenSearch is IoT's own sidecar: it starts with the pod, its
# JVM warm-up takes minutes on a memory-capped container, and the Playwright
# suite's backend reads it. The suite runner runs this suite first, so the wait
# goes here. STAGE=tst is the Jenkinsfile's, and ELASTICSEARCH_URL is in its
# env. The backend tests themselves never reach OpenSearch (test_app_settings
# points at elasticsearch.test), so a local run does not wait, as it never did.
# ---------------------------------------------------------------------------

_OPENSEARCH_WAIT_SECONDS = 180


def pytest_sessionstart(session: pytest.Session) -> None:
    """In CI, wait until OpenSearch reports yellow or green, or stop the run."""
    url = os.environ.get("ELASTICSEARCH_URL", "").rstrip("/")
    if os.environ.get("STAGE") != "tst" or not url:
        return

    # A 200 from _cluster/health can still say "red" during start-up, so gate
    # on the status. wait_for_status holds each request until it is met (or
    # 5 s pass).
    health = f"{url}/_cluster/health?wait_for_status=yellow&timeout=5s"
    deadline = time.monotonic() + _OPENSEARCH_WAIT_SECONDS
    problem = "no answer"
    while time.monotonic() < deadline:
        try:
            response = requests.get(health, timeout=10)
            status = response.json().get("status") if response.ok else None
            if status in ("yellow", "green"):
                return
            problem = f"HTTP {response.status_code}, status {status!r}"
        except (requests.RequestException, ValueError) as exc:
            problem = str(exc)
        time.sleep(2)

    pytest.exit(
        f"OpenSearch at {url!r} did not reach yellow status within "
        f"{_OPENSEARCH_WAIT_SECONDS} s ({problem}). Check the opensearch "
        "service in the Jenkinsfile.",
        returncode=1,
    )

# ---------------------------------------------------------------------------
# Override test_settings to use flask_env="development" (not "testing")
# so that testing endpoints are properly gated.
# IoT has separate testing_app/testing_client fixtures for testing mode.
# ---------------------------------------------------------------------------


@pytest.fixture
def test_settings() -> Settings:
    """Override infrastructure test_settings with flask_env=development.

    This ensures testing-only endpoints are gated behind FLASK_ENV=testing.
    Tests that need testing mode use the separate testing_client fixture.
    """
    return Settings(
        database_url="sqlite:///:memory:",
        secret_key="test-secret-key",
        debug=True,
        flask_env="development",
        cors_origins=["http://localhost:3000"],
        oidc_enabled=False,
        oidc_issuer_url="https://auth.example.com/realms/test",
        oidc_client_id="test-backend",
        oidc_audience="test-backend",
        oidc_clock_skew_seconds=30,
        oidc_cookie_name="access_token",
        oidc_cookie_secure=False,
        oidc_cookie_samesite="Lax",
        oidc_refresh_cookie_name="refresh_token",
        baseurl="http://localhost:3000",
        # S3 configuration (from environment, matching infra conftest)
        s3_endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000"),
        s3_access_key_id=os.environ.get("S3_ACCESS_KEY_ID", "admin"),
        s3_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY", "password"),
        s3_bucket_name=os.environ.get("S3_BUCKET_NAME", "test-app-test-attachments"),
        s3_region=os.environ.get("S3_REGION", "us-east-1"),
        s3_use_ssl=os.environ.get("S3_USE_SSL", "false").lower() == "true",
    )

# ---------------------------------------------------------------------------
# Override test_app_settings with IoT-specific values
# ---------------------------------------------------------------------------


@pytest.fixture
def test_app_settings(tmp_path: Path) -> AppSettings:
    """Create IoT-specific test app settings."""
    return AppSettings(
        # Coredump parsing sidecar
        parse_sidecar_xfer_dir=None,
        parse_sidecar_url=None,
        max_coredumps=20,
        # Firmware retention
        max_firmwares=5,
        # MQTT settings
        mqtt_url="mqtt://mqtt.example.com:1883",
        device_mqtt_url="mqtt://mqtt.example.com:1883",
        mqtt_username=None,
        mqtt_password=None,
        mqtt_client_id="iotsupport-backend",
        # Keycloak Admin API settings
        oidc_token_url="https://auth.example.com/realms/iot/protocol/openid-connect/token",
        keycloak_base_url="https://auth.example.com",
        keycloak_realm="iot",
        keycloak_admin_client_id="iot-admin",
        keycloak_admin_client_secret="admin-secret",
        keycloak_device_scope_name="iot-device-audience",
        keycloak_admin_url="https://auth.example.com/admin/realms/iot",
        keycloak_console_base_url="https://auth.example.com/admin/master/console/#/iot/clients",
        # Device provisioning
        device_baseurl="http://localhost:3200",
        # WiFi credentials
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
        # CAS thumbnail cache
        thumbnail_storage_path=tmp_path / "thumbnails",
        # Fernet key (derived from "test-secret-key" using SHA256 + base64)
        fernet_key="LOrG82NjxiRqZMyoBc1DynoBsU6y_MUyzuw_YPL33xw=",
    )


# ---------------------------------------------------------------------------
# IoT domain fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_cas_image(container: ServiceContainer) -> Any:
    """Factory fixture that uploads a PNG to CAS storage and returns its hash."""
    import io

    from PIL import Image

    def _make(width: int, height: int, color: tuple[int, int, int] = (200, 30, 60)) -> str:
        buffer = io.BytesIO()
        Image.new("RGBA", (width, height), color=(*color, 255)).save(buffer, format="PNG")
        content = buffer.getvalue()

        s3_service = container.s3_service()
        s3_service.upload_file(io.BytesIO(content), s3_service.generate_cas_key(content), "image/png")
        return s3_service.compute_hash(content)

    return _make


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
    """Create DeviceModelService instance via the container."""
    return container.device_model_service()


@pytest.fixture
def device_service(container: ServiceContainer) -> "DeviceService":
    """Create DeviceService instance via the container."""
    return container.device_service()


@pytest.fixture
def make_device_model(container: ServiceContainer) -> Any:
    """Factory fixture for creating device model records in tests."""
    from app.models.device import DeviceModel

    def _make(code: str, name: str) -> DeviceModel:
        service = container.device_model_service()
        return service.create_device_model(code=code, name=name)

    return _make


@pytest.fixture
def make_device(container: ServiceContainer) -> Any:
    """Factory fixture for creating device records in tests."""
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


def create_test_firmware(version: bytes) -> bytes:
    """Create a test firmware binary with valid ESP32 AppInfo header.

    Shared helper used across firmware-related test files.
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
