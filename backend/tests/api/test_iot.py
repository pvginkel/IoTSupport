"""Tests for IoT device API endpoints."""

from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from app.models.coredump import CoreDump, ParseStatus
from app.models.device import RotationState
from app.services.container import ServiceContainer


def create_test_device(
    app: Flask, container: ServiceContainer, model_code: str = "testmodel", config: str = "{}"
) -> tuple[int, str, str]:
    """Helper to create a test device.

    Returns:
        Tuple of (device_id, device_key, model_code)
    """
    with app.app_context():
        model_service = container.device_model_service()
        model = model_service.create_device_model(code=model_code, name="Test Model")

        keycloak_service = container.keycloak_admin_service()
        with patch.object(
            keycloak_service,
            "create_client",
            return_value=MagicMock(client_id=f"iotdevice-{model_code}-abc12345", secret="test-secret"),
        ), patch.object(
            keycloak_service,
            "update_client_metadata",
        ):
            device_service = container.device_service()
            device = device_service.create_device(device_model_id=model.id, config=config)
            return device.id, device.key, model.code


class TestIotConfig:
    """Tests for GET /api/iot/config."""

    def test_get_config_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting device config."""
        config_data = '{"deviceName": "Test Device", "enableOTA": true}'
        device_id, device_key, _ = create_test_device(
            app, container, model_code="cfg1", config=config_data
        )

        # OIDC is disabled in tests, so we use query param
        response = client.get(f"/api/iot/config?device_key={device_key}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["deviceName"] == "Test Device"
        assert data["enableOTA"] is True

    def test_get_config_missing_key(self, client: FlaskClient) -> None:
        """Test getting config without device key."""
        response = client.get("/api/iot/config")

        assert response.status_code == 401

    def test_get_config_invalid_key(self, client: FlaskClient) -> None:
        """Test getting config with invalid device key."""
        response = client.get("/api/iot/config?device_key=invalid1")

        assert response.status_code == 404

    def test_get_config_completes_rotation(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that getting config after rotation completes the rotation."""
        _, device_key, _ = create_test_device(app, container, model_code="rot1")

        # Set device to PENDING state
        with app.app_context():
            device_service = container.device_service()
            device = device_service.get_device_by_key(device_key)
            device.rotation_state = RotationState.PENDING.value
            from datetime import datetime, timedelta
            device.last_rotation_attempt_at = datetime.utcnow() - timedelta(minutes=1)
            container.db_session().flush()

        # Get config - should complete rotation (in test mode without real JWT validation)
        response = client.get(f"/api/iot/config?device_key={device_key}")
        assert response.status_code == 200


class TestIotFirmware:
    """Tests for GET /api/iot/firmware."""

    def test_get_firmware_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test downloading firmware from S3."""
        _, device_key, model_code = create_test_device(app, container, model_code="fw1")

        from tests.services.test_firmware_service import _create_test_zip

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.get_device_model_by_code(model_code)
            zip_content = _create_test_zip(model_code, b"1.0.0")
            model_service.upload_firmware(model.id, zip_content)

        response = client.get(f"/api/iot/firmware?device_key={device_key}")

        assert response.status_code == 200
        assert response.content_type == "application/octet-stream"
        assert len(response.data) > 0

    def test_get_firmware_not_uploaded(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting firmware when none uploaded."""
        _, device_key, _ = create_test_device(app, container, model_code="fw2")

        response = client.get(f"/api/iot/firmware?device_key={device_key}")

        assert response.status_code == 404

    def test_get_firmware_missing_key(self, client: FlaskClient) -> None:
        """Test getting firmware without device key."""
        response = client.get("/api/iot/firmware")

        assert response.status_code == 401


class TestIotFirmwareVersion:
    """Tests for GET /api/iot/firmware-version."""

    def test_get_firmware_version_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting firmware version."""
        _, device_key, model_code = create_test_device(app, container, model_code="fv1")

        from tests.services.test_firmware_service import _create_test_zip

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.get_device_model_by_code(model_code)
            zip_content = _create_test_zip(model_code, b"2.1.0")
            model_service.upload_firmware(model.id, zip_content)

        response = client.get(f"/api/iot/firmware-version?device_key={device_key}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["firmware_version"] == "2.1.0"

    def test_get_firmware_version_no_firmware(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting firmware version when no firmware uploaded."""
        _, device_key, _ = create_test_device(app, container, model_code="fv2")

        response = client.get(f"/api/iot/firmware-version?device_key={device_key}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["firmware_version"] is None

    def test_get_firmware_version_missing_key(self, client: FlaskClient) -> None:
        """Test getting firmware version without device key."""
        response = client.get("/api/iot/firmware-version")

        assert response.status_code == 401

    def test_get_firmware_version_invalid_key(self, client: FlaskClient) -> None:
        """Test getting firmware version with invalid device key."""
        response = client.get("/api/iot/firmware-version?device_key=invalid1")

        assert response.status_code == 404


class TestIotProvisioning:
    """Tests for GET /api/iot/provisioning."""

    def test_get_provisioning_regenerates_secret(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that provisioning endpoint regenerates the secret."""
        _, device_key, _ = create_test_device(app, container, model_code="prov1")

        with app.app_context():
            keycloak_service = container.keycloak_admin_service()

            with patch.object(
                keycloak_service, "get_client_secret", return_value="old-secret"
            ), patch.object(
                keycloak_service, "regenerate_secret", return_value="new-secret"
            ) as mock_regen:
                response = client.get(f"/api/iot/provisioning?device_key={device_key}")

                assert response.status_code == 200
                mock_regen.assert_called_once()

                data = response.get_json()
                assert data["client_secret"] == "new-secret"
                assert data["device_key"] == device_key

    def test_get_provisioning_caches_old_secret(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that provisioning caches the old secret for rollback."""
        _, device_key, _ = create_test_device(app, container, model_code="prov2")

        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            device_service = container.device_service()

            # Verify no cached secret initially
            device = device_service.get_device_by_key(device_key)
            assert device.cached_secret is None

            with patch.object(
                keycloak_service, "get_client_secret", return_value="old-secret"
            ), patch.object(
                keycloak_service, "regenerate_secret", return_value="new-secret"
            ):
                response = client.get(f"/api/iot/provisioning?device_key={device_key}")
                assert response.status_code == 200

            # Verify old secret was cached (encrypted)
            container.db_session().expire_all()
            device = device_service.get_device_by_key(device_key)
            assert device.cached_secret is not None

    def test_get_provisioning_updates_secret_created_at(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that provisioning updates secret_created_at."""
        _, device_key, _ = create_test_device(app, container, model_code="prov3")

        with app.app_context():
            keycloak_service = container.keycloak_admin_service()
            device_service = container.device_service()

            # Get initial state
            device = device_service.get_device_by_key(device_key)
            initial_secret_created = device.secret_created_at

            with patch.object(
                keycloak_service, "get_client_secret", return_value="old-secret"
            ), patch.object(
                keycloak_service, "regenerate_secret", return_value="new-secret"
            ):
                response = client.get(f"/api/iot/provisioning?device_key={device_key}")
                assert response.status_code == 200

                # Check secret_created_at was updated
                container.db_session().expire_all()
                device = device_service.get_device_by_key(device_key)
                assert device.secret_created_at is not None
                if initial_secret_created:
                    assert device.secret_created_at > initial_secret_created

    def test_get_provisioning_missing_key(self, client: FlaskClient) -> None:
        """Test getting provisioning without device key."""
        response = client.get("/api/iot/provisioning")

        assert response.status_code == 401

    def test_get_provisioning_contains_required_fields(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that provisioning response contains all required fields."""
        _, device_key, _ = create_test_device(app, container, model_code="prov4")

        with app.app_context():
            keycloak_service = container.keycloak_admin_service()

            with patch.object(
                keycloak_service, "get_client_secret", return_value="old-secret"
            ), patch.object(
                keycloak_service, "regenerate_secret", return_value="new-secret"
            ):
                response = client.get(f"/api/iot/provisioning?device_key={device_key}")

                assert response.status_code == 200
                data = response.get_json()

                # Check all required fields are present
                assert "device_key" in data
                assert "client_id" in data
                assert "client_secret" in data
                assert "token_url" in data
                assert "base_url" in data
                assert "mqtt_url" in data
                assert "wifi_ssid" in data
                assert "wifi_password" in data


class TestIotCoredump:
    """Tests for POST /api/iot/coredump."""

    def test_upload_coredump_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test successful coredump upload stores in S3 and creates DB record."""
        _, device_key, model_code = create_test_device(app, container, model_code="cd1")

        content = b"\xDE\xAD\xBE\xEF" * 64

        response = client.post(
            f"/api/iot/coredump?device_key={device_key}&chip=esp32s3&firmware_version=1.0.0",
            data=content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["status"] == "ok"
        assert "coredump_id" in data
        coredump_id = data["coredump_id"]

        # Verify S3 object was written
        s3 = container.s3_service()
        s3_key = f"coredumps/{device_key}/{coredump_id}.dmp"
        assert s3.file_exists(s3_key)
        stream = s3.download_file(s3_key)
        assert stream.read() == content

        # Verify DB record was created with correct metadata
        with app.app_context():
            session = container.db_session()
            stmt = select(CoreDump).where(CoreDump.id == coredump_id)
            coredump = session.execute(stmt).scalar_one_or_none()
            assert coredump is not None
            assert coredump.chip == "esp32s3"
            assert coredump.firmware_version == "1.0.0"
            assert coredump.size == len(content)
            assert coredump.parse_status == ParseStatus.PENDING.value
            assert coredump.parsed_output is None
            assert coredump.uploaded_at is not None

    def test_upload_coredump_missing_chip(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that missing chip query param returns 400."""
        _, device_key, _ = create_test_device(app, container, model_code="cd2")

        response = client.post(
            f"/api/iot/coredump?device_key={device_key}&firmware_version=1.0.0",
            data=b"\x00" * 10,
            content_type="application/octet-stream",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "chip" in data["error"]

    def test_upload_coredump_missing_firmware_version(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that missing firmware_version query param returns 400."""
        _, device_key, _ = create_test_device(app, container, model_code="cd3")

        response = client.post(
            f"/api/iot/coredump?device_key={device_key}&chip=esp32",
            data=b"\x00" * 10,
            content_type="application/octet-stream",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "firmware_version" in data["error"]

    def test_upload_coredump_empty_body(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that empty body returns 400."""
        _, device_key, _ = create_test_device(app, container, model_code="cd4")

        response = client.post(
            f"/api/iot/coredump?device_key={device_key}&chip=esp32&firmware_version=1.0.0",
            data=b"",
            content_type="application/octet-stream",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "No coredump content" in data["error"]

    def test_upload_coredump_exceeds_max_size(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that body exceeding 1MB returns 400."""
        _, device_key, _ = create_test_device(app, container, model_code="cd5")

        # 1MB + 1 byte
        content = b"\x00" * (1_048_576 + 1)

        response = client.post(
            f"/api/iot/coredump?device_key={device_key}&chip=esp32&firmware_version=1.0.0",
            data=content,
            content_type="application/octet-stream",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "exceeds maximum size" in data["error"]

    def test_upload_coredump_no_auth(self, client: FlaskClient) -> None:
        """Test that missing device authentication returns 401."""
        response = client.post(
            "/api/iot/coredump?chip=esp32&firmware_version=1.0.0",
            data=b"\x00" * 10,
            content_type="application/octet-stream",
        )

        assert response.status_code == 401

    def test_upload_coredump_invalid_device_key(self, client: FlaskClient) -> None:
        """Test that invalid device key returns 404."""
        response = client.post(
            "/api/iot/coredump?device_key=invalid1&chip=esp32&firmware_version=1.0.0",
            data=b"\x00" * 10,
            content_type="application/octet-stream",
        )

        assert response.status_code == 404
