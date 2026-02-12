"""Tests for devices API endpoints."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from app.models.coredump import CoreDump
from app.models.device import RotationState
from app.services.container import ServiceContainer


class TestDevicesList:
    """Tests for GET /api/devices."""

    def test_list_devices_empty(self, client: FlaskClient) -> None:
        """Test listing when no devices exist."""
        response = client.get("/api/devices")

        assert response.status_code == 200
        data = response.get_json()
        assert data["devices"] == []

    def test_list_devices_returns_all(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that list returns all devices."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="list1", name="List Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device_service.create_device(device_model_id=model.id, config="{}")
                device_service.create_device(device_model_id=model.id, config="{}")

        response = client.get("/api/devices")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["devices"]) == 2

    def test_list_devices_includes_last_coredump_at_null(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that last_coredump_at is null when device has no coredumps."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="lcd1", name="LCD Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device_service.create_device(device_model_id=model.id, config="{}")

        response = client.get("/api/devices")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["devices"]) == 1
        assert data["devices"][0]["last_coredump_at"] is None

    def test_list_devices_includes_last_coredump_at_with_coredumps(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that last_coredump_at returns the most recent coredump timestamp."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="lcd2", name="LCD Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id, config="{}"
                )

                # Add two coredumps with different timestamps
                session = container.db_session()
                older = CoreDump(
                    device_id=device.id,
                    filename="old.dmp",
                    chip="esp32s3",
                    firmware_version="1.0.0",
                    size=1024,
                    uploaded_at=datetime(2026, 1, 1, 12, 0, 0),
                )
                newer = CoreDump(
                    device_id=device.id,
                    filename="new.dmp",
                    chip="esp32s3",
                    firmware_version="1.0.1",
                    size=2048,
                    uploaded_at=datetime(2026, 2, 10, 8, 30, 0),
                )
                session.add_all([older, newer])
                session.flush()

        response = client.get("/api/devices")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["devices"]) == 1
        # Should return the newer timestamp
        assert data["devices"][0]["last_coredump_at"] is not None
        assert "10 Feb 2026" in data["devices"][0]["last_coredump_at"]

    def test_list_devices_filter_by_model(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test filtering devices by model ID."""
        with app.app_context():
            model_service = container.device_model_service()
            model1 = model_service.create_device_model(code="filt1", name="Filter One")
            model2 = model_service.create_device_model(code="filt2", name="Filter Two")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device_service.create_device(device_model_id=model1.id, config="{}")
                device_service.create_device(device_model_id=model2.id, config="{}")
                model_id = model1.id

        response = client.get(f"/api/devices?model_id={model_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["devices"]) == 1


class TestDevicesCreate:
    """Tests for POST /api/devices."""

    def test_create_device_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test creating a device."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="create1", name="Create Test")
            model_id = model.id

        with patch.object(
            container.keycloak_admin_service(),
            "create_client",
            return_value=MagicMock(client_id="test", secret="test-secret"),
        ), patch.object(
            container.keycloak_admin_service(),
            "update_client_metadata",
        ):
            response = client.post(
                "/api/devices",
                json={
                    "device_model_id": model_id,
                    "config": '{"setting": "value"}',
                },
            )

        assert response.status_code == 201
        data = response.get_json()
        assert data["device_model_id"] == model_id
        assert len(data["key"]) == 8
        # Config is returned as an opaque JSON string
        assert data["config"] == '{"setting": "value"}'

    def test_create_device_invalid_model_id(self, client: FlaskClient) -> None:
        """Test creating device with invalid model ID returns 404."""
        response = client.post(
            "/api/devices",
            json={
                "device_model_id": 99999,
                "config": "{}",
            },
        )

        assert response.status_code == 404

    def test_create_device_invalid_json_config(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test creating device with invalid JSON config returns 400."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="create2", name="Create Test 2")
            model_id = model.id

        response = client.post(
            "/api/devices",
            json={
                "device_model_id": model_id,
                "config": "not valid json",
            },
        )

        assert response.status_code == 400


class TestDevicesGet:
    """Tests for GET /api/devices/<id>."""

    def test_get_device_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting a device by ID."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="get1", name="Get Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id
                device_key = device.key

        response = client.get(f"/api/devices/{device_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["key"] == device_key

    def test_get_device_not_found(self, client: FlaskClient) -> None:
        """Test getting a nonexistent device returns 404."""
        response = client.get("/api/devices/99999")

        assert response.status_code == 404


class TestDevicesUpdate:
    """Tests for PUT /api/devices/<id>."""

    def test_update_device_config_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test updating a device's configuration."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="upd1", name="Update Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id, config='{"old": "value"}'
                )
                device_id = device.id

        with patch.object(container.keycloak_admin_service(), "update_client_metadata"):
            response = client.put(
                f"/api/devices/{device_id}",
                json={"config": '{"new": "value"}'},
            )

        assert response.status_code == 200
        data = response.get_json()
        # Config is returned as an opaque JSON string
        assert data["config"] == '{"new": "value"}'

    def test_update_device_not_found(self, client: FlaskClient) -> None:
        """Test updating a nonexistent device returns 404."""
        response = client.put(
            "/api/devices/99999",
            json={"config": "{}"},
        )

        assert response.status_code == 404

    def test_update_device_publishes_mqtt_with_json_payload(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that updating a device publishes MQTT with JSON payload."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="upd_mqtt", name="Update MQTT")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id, config='{"setting": "old"}'
                )
                device_id = device.id
                expected_client_id = device.client_id

        mqtt_service = app.container.mqtt_service()

        with patch.object(mqtt_service, "publish") as mock_publish, patch.object(
            app.container.keycloak_admin_service(), "update_client_metadata"
        ):
            response = client.put(
                f"/api/devices/{device_id}",
                json={"config": '{"setting": "new"}'},
            )

            assert response.status_code == 200

            # Verify MQTT was published with correct topic and JSON payload
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args[0]
            topic = call_args[0]
            payload_str = call_args[1]

            assert topic == "iotsupport/updates/config"
            payload = json.loads(payload_str)
            assert payload == {"client_id": expected_client_id}


class TestDevicesDelete:
    """Tests for DELETE /api/devices/<id>."""

    def test_delete_device_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test deleting a device."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="del1", name="Delete Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        with patch.object(container.keycloak_admin_service(), "delete_client"):
            response = client.delete(f"/api/devices/{device_id}")

        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f"/api/devices/{device_id}")
        assert response.status_code == 404

    def test_delete_device_not_found(self, client: FlaskClient) -> None:
        """Test deleting a nonexistent device returns 404."""
        response = client.delete("/api/devices/99999")

        assert response.status_code == 404


class TestDevicesProvisioning:
    """Tests for GET /api/devices/<id>/provisioning."""

    # Standard test partition size (12KB minimum)
    TEST_PARTITION_SIZE = 0x3000

    def test_get_provisioning_returns_json_with_nvs_format(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that provisioning endpoint returns JSON with size and data fields."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="prov1", name="Provisioning Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        with patch.object(
            container.keycloak_admin_service(), "get_client_secret", return_value="secret123"
        ):
            response = client.get(
                f"/api/devices/{device_id}/provisioning?partition_size={self.TEST_PARTITION_SIZE}"
            )

        assert response.status_code == 200
        assert response.content_type == "application/json"
        data = response.get_json()
        assert "size" in data
        assert "data" in data
        assert data["size"] == self.TEST_PARTITION_SIZE

    def test_get_provisioning_data_is_valid_base64(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that data field contains valid base64-encoded NVS blob."""
        import base64

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="prov2", name="Provisioning Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        with patch.object(
            container.keycloak_admin_service(), "get_client_secret", return_value="secret123"
        ):
            response = client.get(
                f"/api/devices/{device_id}/provisioning?partition_size={self.TEST_PARTITION_SIZE}"
            )

        assert response.status_code == 200
        data = response.get_json()

        # Data should be valid base64
        decoded = base64.b64decode(data["data"])
        # NVS blob should match the requested partition size
        assert len(decoded) == self.TEST_PARTITION_SIZE

    def test_get_provisioning_blob_contains_device_key(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that the NVS blob contains the device key."""
        import base64

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="prov3", name="Provisioning Test 3")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id
                device_key = device.key

        with patch.object(
            container.keycloak_admin_service(), "get_client_secret", return_value="secret123"
        ):
            response = client.get(
                f"/api/devices/{device_id}/provisioning?partition_size={self.TEST_PARTITION_SIZE}"
            )

        data = response.get_json()
        decoded = base64.b64decode(data["data"])

        # Device key should be present in the binary blob
        assert device_key.encode("utf-8") in decoded

    def test_get_provisioning_blob_contains_keycloak_secret(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that the NVS blob contains the Keycloak secret."""
        import base64

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="prov4", name="Provisioning Test 4")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        secret_value = "keycloak-secret-xyz789"
        with patch.object(
            container.keycloak_admin_service(), "get_client_secret", return_value=secret_value
        ):
            response = client.get(
                f"/api/devices/{device_id}/provisioning?partition_size={self.TEST_PARTITION_SIZE}"
            )

        data = response.get_json()
        decoded = base64.b64decode(data["data"])

        # Keycloak secret should be present in the binary blob
        assert secret_value.encode("utf-8") in decoded

    def test_get_provisioning_not_found(self, client: FlaskClient) -> None:
        """Test getting provisioning for nonexistent device returns 404."""
        response = client.get(
            f"/api/devices/99999/provisioning?partition_size={self.TEST_PARTITION_SIZE}"
        )

        assert response.status_code == 404

    def test_get_provisioning_missing_partition_size(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that missing partition_size parameter returns 400."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="prov6", name="Provisioning Test 6")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        # Missing partition_size parameter
        response = client.get(f"/api/devices/{device_id}/provisioning")

        # SpectTree returns 400 for validation errors
        assert response.status_code == 400

    def test_get_provisioning_invalid_partition_size(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that invalid partition_size parameter returns 400."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="prov7", name="Provisioning Test 7")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        # partition_size too small (below 12KB minimum)
        response = client.get(f"/api/devices/{device_id}/provisioning?partition_size=4096")

        # SpectTree returns 400 for validation errors
        assert response.status_code == 400

    def test_get_provisioning_keycloak_failure_returns_502(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that Keycloak failure returns 502."""
        from app.exceptions import ExternalServiceException

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="prov5", name="Provisioning Test 5")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        with patch.object(
            container.keycloak_admin_service(),
            "get_client_secret",
            side_effect=ExternalServiceException("get secret", "connection refused"),
        ):
            response = client.get(
                f"/api/devices/{device_id}/provisioning?partition_size={self.TEST_PARTITION_SIZE}"
            )

        assert response.status_code == 502


class TestDevicesRotate:
    """Tests for POST /api/devices/<id>/rotate."""

    def test_trigger_rotation_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test triggering rotation for a device."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="rot1", name="Rotation Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        response = client.post(f"/api/devices/{device_id}/rotate")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "queued"

    def test_trigger_rotation_already_pending(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test triggering rotation when already pending."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="rot2", name="Rotation Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device.rotation_state = RotationState.PENDING.value
                device_id = device.id

        response = client.post(f"/api/devices/{device_id}/rotate")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "already_pending"

    def test_trigger_rotation_not_found(self, client: FlaskClient) -> None:
        """Test triggering rotation for nonexistent device returns 404."""
        response = client.post("/api/devices/99999/rotate")

        assert response.status_code == 404


class TestDevicesKeycloakStatus:
    """Tests for GET /api/devices/<id>/keycloak-status."""

    def test_keycloak_status_client_exists(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting Keycloak status when client exists."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="kcs1", name="KC Status Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id
                expected_client_id = device.client_id

        with patch.object(
            container.keycloak_admin_service(),
            "get_client_status",
            return_value=(True, "uuid-123"),
        ):
            response = client.get(f"/api/devices/{device_id}/keycloak-status")

        assert response.status_code == 200
        data = response.get_json()
        assert data["exists"] is True
        assert data["client_id"] == expected_client_id
        assert data["keycloak_uuid"] == "uuid-123"

    def test_keycloak_status_client_missing(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting Keycloak status when client is missing (returns 200, not 404)."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="kcs2", name="KC Status Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        with patch.object(
            container.keycloak_admin_service(),
            "get_client_status",
            return_value=(False, None),
        ):
            response = client.get(f"/api/devices/{device_id}/keycloak-status")

        assert response.status_code == 200
        data = response.get_json()
        assert data["exists"] is False
        assert data["keycloak_uuid"] is None
        assert data["console_url"] is None

    def test_keycloak_status_device_not_found(self, client: FlaskClient) -> None:
        """Test getting Keycloak status for nonexistent device returns 404."""
        response = client.get("/api/devices/99999/keycloak-status")

        assert response.status_code == 404


class TestDevicesKeycloakSync:
    """Tests for POST /api/devices/<id>/keycloak-sync."""

    def test_keycloak_sync_creates_missing_client(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test syncing creates a missing Keycloak client."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="kcsync1", name="KC Sync Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        with patch.object(
            container.keycloak_admin_service(),
            "create_client",
            return_value=MagicMock(client_id="test", secret="new-secret"),
        ), patch.object(
            container.keycloak_admin_service(),
            "update_client_metadata",
        ), patch.object(
            container.keycloak_admin_service(),
            "get_client_status",
            return_value=(True, "uuid-new"),
        ):
            response = client.post(f"/api/devices/{device_id}/keycloak-sync")

        assert response.status_code == 200
        data = response.get_json()
        assert data["exists"] is True
        assert data["keycloak_uuid"] == "uuid-new"

    def test_keycloak_sync_idempotent(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test syncing is idempotent when client already exists."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="kcsync2", name="KC Sync Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(device_model_id=model.id, config="{}")
                device_id = device.id

        with patch.object(
            container.keycloak_admin_service(),
            "create_client",
            return_value=MagicMock(client_id="test", secret="existing-secret"),
        ), patch.object(
            container.keycloak_admin_service(),
            "update_client_metadata",
        ), patch.object(
            container.keycloak_admin_service(),
            "get_client_status",
            return_value=(True, "existing-uuid"),
        ):
            response = client.post(f"/api/devices/{device_id}/keycloak-sync")

        assert response.status_code == 200
        data = response.get_json()
        assert data["exists"] is True

    def test_keycloak_sync_device_not_found(self, client: FlaskClient) -> None:
        """Test syncing for nonexistent device returns 404."""
        response = client.post("/api/devices/99999/keycloak-sync")

        assert response.status_code == 404


class TestDevicesLogs:
    """Tests for GET /api/devices/<id>/logs."""

    def test_get_logs_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting device logs successfully."""
        from datetime import datetime

        from app.services.elasticsearch_service import LogEntry, LogQueryResult

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="logs1", name="Logs Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id,
                    config='{"deviceEntityId": "sensor.test"}',
                )
                device_id = device.id

        mock_result = LogQueryResult(
            logs=[
                LogEntry(
                    timestamp=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                    message="Log message 1",
                ),
                LogEntry(
                    timestamp=datetime(2026, 2, 1, 14, 1, 0, tzinfo=UTC),
                    message="Log message 2",
                ),
            ],
            has_more=False,
            window_start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
            window_end=datetime(2026, 2, 1, 14, 1, 0, tzinfo=UTC),
        )

        with patch.object(
            container.elasticsearch_service(),
            "query_logs",
            return_value=mock_result,
        ):
            response = client.get(f"/api/devices/{device_id}/logs")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["logs"]) == 2
        assert data["logs"][0]["message"] == "Log message 1"
        assert data["has_more"] is False
        assert data["window_start"] is not None
        assert data["window_end"] is not None

    def test_get_logs_with_time_range(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting logs with start and end parameters."""
        from datetime import datetime

        from app.services.elasticsearch_service import LogQueryResult

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="logs2", name="Logs Test 2")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id,
                    config='{"deviceEntityId": "sensor.test"}',
                )
                device_id = device.id

        mock_result = LogQueryResult(
            logs=[],
            has_more=False,
            window_start=None,
            window_end=None,
        )

        with patch.object(
            container.elasticsearch_service(),
            "query_logs",
            return_value=mock_result,
        ) as mock_query:
            response = client.get(
                f"/api/devices/{device_id}/logs"
                "?start=2026-02-01T14:00:00Z&end=2026-02-01T15:00:00Z"
            )

        assert response.status_code == 200

        # Verify query was called with parsed timestamps
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args[1]
        assert call_kwargs["start"] == datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC)
        assert call_kwargs["end"] == datetime(2026, 2, 1, 15, 0, 0, tzinfo=UTC)

    def test_get_logs_with_query_param(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting logs with wildcard query parameter."""
        from app.services.elasticsearch_service import LogQueryResult

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="logs3", name="Logs Test 3")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id,
                    config='{"deviceEntityId": "sensor.test"}',
                )
                device_id = device.id

        mock_result = LogQueryResult(
            logs=[],
            has_more=False,
            window_start=None,
            window_end=None,
        )

        with patch.object(
            container.elasticsearch_service(),
            "query_logs",
            return_value=mock_result,
        ) as mock_query:
            response = client.get(f"/api/devices/{device_id}/logs?query=error*")

        assert response.status_code == 200

        # Verify query parameter was passed
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args[1]
        assert call_kwargs["query"] == "error*"

    def test_get_logs_device_without_entity_id(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting logs for device without entity_id returns empty array."""
        from app.services.elasticsearch_service import LogQueryResult

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="logs4", name="Logs Test 4")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                # Config without deviceEntityId
                device = device_service.create_device(
                    device_model_id=model.id,
                    config='{"deviceName": "Test"}',
                )
                device_id = device.id

        # Service returns empty result for None entity_id
        mock_result = LogQueryResult(
            logs=[],
            has_more=False,
            window_start=None,
            window_end=None,
        )

        with patch.object(
            container.elasticsearch_service(),
            "query_logs",
            return_value=mock_result,
        ):
            response = client.get(f"/api/devices/{device_id}/logs")

        assert response.status_code == 200
        data = response.get_json()
        assert data["logs"] == []
        assert data["has_more"] is False

    def test_get_logs_device_not_found(self, client: FlaskClient) -> None:
        """Test getting logs for nonexistent device returns 404."""
        response = client.get("/api/devices/99999/logs")

        assert response.status_code == 404

    def test_get_logs_elasticsearch_unavailable_returns_503(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that Elasticsearch unavailability returns 503."""
        from app.exceptions import ServiceUnavailableException

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="logs5", name="Logs Test 5")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id,
                    config='{"deviceEntityId": "sensor.test"}',
                )
                device_id = device.id

        with patch.object(
            container.elasticsearch_service(),
            "query_logs",
            side_effect=ServiceUnavailableException("Elasticsearch", "Connection failed"),
        ):
            response = client.get(f"/api/devices/{device_id}/logs")

        assert response.status_code == 503

    def test_get_logs_has_more_when_paginated(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test has_more is true when results are truncated."""
        from datetime import datetime

        from app.services.elasticsearch_service import LogEntry, LogQueryResult

        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="logs6", name="Logs Test 6")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id,
                    config='{"deviceEntityId": "sensor.test"}',
                )
                device_id = device.id

        mock_result = LogQueryResult(
            logs=[
                LogEntry(
                    timestamp=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
                    message="Log message",
                ),
            ],
            has_more=True,
            window_start=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
            window_end=datetime(2026, 2, 1, 14, 0, 0, tzinfo=UTC),
        )

        with patch.object(
            container.elasticsearch_service(),
            "query_logs",
            return_value=mock_result,
        ):
            response = client.get(f"/api/devices/{device_id}/logs")

        assert response.status_code == 200
        data = response.get_json()
        assert data["has_more"] is True
        assert data["window_start"] is not None
        assert data["window_end"] is not None

    def test_get_logs_invalid_datetime_returns_400(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that invalid datetime in query params returns 400."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="logs7", name="Logs Test 7")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="test", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id,
                    config='{"deviceEntityId": "sensor.test"}',
                )
                device_id = device.id

        response = client.get(f"/api/devices/{device_id}/logs?start=not-a-date")

        assert response.status_code == 400
