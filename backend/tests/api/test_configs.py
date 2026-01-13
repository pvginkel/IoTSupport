"""Tests for configuration API endpoints."""

from typing import Any
from unittest.mock import patch

from flask import Flask
from flask.testing import FlaskClient

from app.services.container import ServiceContainer


class TestListConfigs:
    """Tests for GET /api/configs."""

    def test_list_configs_empty(self, client: FlaskClient):
        """Empty directory returns empty list with 200."""
        response = client.get("/api/configs")

        assert response.status_code == 200
        data = response.get_json()
        assert data["configs"] == []
        assert data["count"] == 0

    def test_list_configs_returns_summary(
        self, client: FlaskClient, make_config_file: Any, sample_config: dict[str, Any]
    ):
        """Configs are returned with correct summary format."""
        make_config_file("aa-bb-cc-dd-ee-ff", sample_config)

        response = client.get("/api/configs")

        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert len(data["configs"]) == 1

        config = data["configs"][0]
        assert config["mac_address"] == "aa-bb-cc-dd-ee-ff"
        assert config["device_name"] == "Living Room Sensor"
        assert config["device_entity_id"] == "sensor.living_room"
        assert config["enable_ota"] is True


class TestGetConfig:
    """Tests for GET /api/configs/<mac_address>."""

    def test_get_config_success(
        self, client: FlaskClient, make_config_file: Any, sample_config: dict[str, Any], valid_mac: str
    ):
        """Existing config returns 200 with full content."""
        make_config_file(valid_mac, sample_config)

        response = client.get(f"/api/configs/{valid_mac}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["mac_address"] == valid_mac
        assert data["content"] == sample_config

    def test_get_config_not_found(self, client: FlaskClient, valid_mac: str):
        """Non-existent config returns 404."""
        response = client.get(f"/api/configs/{valid_mac}")

        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        assert data["code"] == "RECORD_NOT_FOUND"

    def test_get_config_invalid_mac(self, client: FlaskClient):
        """Invalid MAC format returns 400."""
        response = client.get("/api/configs/invalid-mac")

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert data["code"] == "INVALID_OPERATION"


class TestSaveConfig:
    """Tests for PUT /api/configs/<mac_address>."""

    def test_save_config_create(
        self, client: FlaskClient, sample_config: dict[str, Any], valid_mac: str
    ):
        """Creating new config returns 200."""
        response = client.put(
            f"/api/configs/{valid_mac}",
            json={"content": sample_config},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["mac_address"] == valid_mac
        assert data["content"] == sample_config

    def test_save_config_update(
        self,
        client: FlaskClient,
        make_config_file: Any,
        sample_config: dict[str, Any],
        valid_mac: str,
    ):
        """Updating existing config returns 200."""
        make_config_file(valid_mac, sample_config)

        updated_config = {**sample_config, "deviceName": "Updated Name"}
        response = client.put(
            f"/api/configs/{valid_mac}",
            json={"content": updated_config},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["device_name"] == "Updated Name"

    def test_save_config_invalid_mac(self, client: FlaskClient, sample_config: dict[str, Any]):
        """Invalid MAC format returns 400."""
        response = client.put(
            "/api/configs/INVALID-MAC",
            json={"content": sample_config},
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "INVALID_OPERATION"

    def test_save_config_invalid_json(self, client: FlaskClient, valid_mac: str):
        """Invalid request body returns 400."""
        response = client.put(
            f"/api/configs/{valid_mac}",
            data="not json",
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_save_config_missing_content(self, client: FlaskClient, valid_mac: str):
        """Missing content field returns 400."""
        response = client.put(
            f"/api/configs/{valid_mac}",
            json={},
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_save_config_allow_overwrite_false_new(
        self, client: FlaskClient, sample_config: dict[str, Any], valid_mac: str
    ):
        """Creating new config with allow_overwrite=false returns 200."""
        response = client.put(
            f"/api/configs/{valid_mac}",
            json={"content": sample_config, "allow_overwrite": False},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["mac_address"] == valid_mac

    def test_save_config_allow_overwrite_false_existing(
        self,
        client: FlaskClient,
        make_config_file: Any,
        sample_config: dict[str, Any],
        valid_mac: str,
    ):
        """Updating existing config with allow_overwrite=false returns 409."""
        make_config_file(valid_mac, sample_config)

        updated_config = {**sample_config, "deviceName": "Updated Name"}
        response = client.put(
            f"/api/configs/{valid_mac}",
            json={"content": updated_config, "allow_overwrite": False},
            content_type="application/json",
        )

        assert response.status_code == 409
        data = response.get_json()
        assert data["code"] == "RECORD_EXISTS"
        assert valid_mac in data["error"]

    def test_save_config_allow_overwrite_defaults_true(
        self,
        client: FlaskClient,
        make_config_file: Any,
        sample_config: dict[str, Any],
        valid_mac: str,
    ):
        """Updating existing config without allow_overwrite param returns 200 (default True)."""
        make_config_file(valid_mac, sample_config)

        updated_config = {**sample_config, "deviceName": "Updated Name"}
        response = client.put(
            f"/api/configs/{valid_mac}",
            json={"content": updated_config},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["device_name"] == "Updated Name"


class TestDeleteConfig:
    """Tests for DELETE /api/configs/<mac_address>."""

    def test_delete_config_success(
        self, client: FlaskClient, make_config_file: Any, sample_config: dict[str, Any], valid_mac: str
    ):
        """Deleting existing config returns 204."""
        make_config_file(valid_mac, sample_config)

        response = client.delete(f"/api/configs/{valid_mac}")

        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f"/api/configs/{valid_mac}")
        assert response.status_code == 404

    def test_delete_config_not_found(self, client: FlaskClient, valid_mac: str):
        """Deleting non-existent config returns 404."""
        response = client.delete(f"/api/configs/{valid_mac}")

        assert response.status_code == 404
        data = response.get_json()
        assert data["code"] == "RECORD_NOT_FOUND"

    def test_delete_config_invalid_mac(self, client: FlaskClient):
        """Invalid MAC format returns 400."""
        response = client.delete("/api/configs/bad-mac")

        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "INVALID_OPERATION"


class TestConfigsWithMqtt:
    """Tests for MQTT integration in config API endpoints."""

    def test_save_config_publishes_mqtt_notification(
        self, app: Flask, client: FlaskClient, sample_config: dict[str, Any], valid_mac: str, container: ServiceContainer
    ):
        """Successful config save publishes MQTT notification."""
        # Get the mqtt_service from container and mock its publish method
        mqtt_service = container.mqtt_service()
        with patch.object(mqtt_service, "publish_config_update") as mock_publish:
            response = client.put(
                f"/api/configs/{valid_mac}",
                json={"content": sample_config},
                content_type="application/json",
            )

            assert response.status_code == 200

            # Verify MQTT notification was published with correct filename
            mock_publish.assert_called_once_with(f"{valid_mac}.json")

    def test_save_config_update_publishes_mqtt_notification(
        self,
        app: Flask,
        client: FlaskClient,
        make_config_file: Any,
        sample_config: dict[str, Any],
        valid_mac: str,
        container: ServiceContainer,
    ):
        """Updating existing config publishes MQTT notification."""
        make_config_file(valid_mac, sample_config)

        mqtt_service = container.mqtt_service()
        with patch.object(mqtt_service, "publish_config_update") as mock_publish:
            updated_config = {**sample_config, "deviceName": "Updated Name"}
            response = client.put(
                f"/api/configs/{valid_mac}",
                json={"content": updated_config},
                content_type="application/json",
            )

            assert response.status_code == 200
            mock_publish.assert_called_once_with(f"{valid_mac}.json")

    def test_save_config_failure_does_not_publish_mqtt(
        self, app: Flask, client: FlaskClient, valid_mac: str, container: ServiceContainer
    ):
        """Failed config save does not publish MQTT notification."""
        mqtt_service = container.mqtt_service()
        with patch.object(mqtt_service, "publish_config_update") as mock_publish:
            # Invalid request - missing content
            response = client.put(
                f"/api/configs/{valid_mac}",
                json={},
                content_type="application/json",
            )

            assert response.status_code == 400

            # MQTT should not be published on failure
            mock_publish.assert_not_called()

    def test_delete_config_does_not_publish_mqtt(
        self,
        app: Flask,
        client: FlaskClient,
        make_config_file: Any,
        sample_config: dict[str, Any],
        valid_mac: str,
        container: ServiceContainer,
    ):
        """Config deletion does NOT publish MQTT notification."""
        make_config_file(valid_mac, sample_config)

        mqtt_service = container.mqtt_service()
        with patch.object(mqtt_service, "publish_config_update") as mock_publish:
            response = client.delete(f"/api/configs/{valid_mac}")

            assert response.status_code == 204

            # MQTT should NOT be published on delete
            mock_publish.assert_not_called()

    def test_save_config_mqtt_disabled_succeeds(
        self, app: Flask, client: FlaskClient, sample_config: dict[str, Any], valid_mac: str, container: ServiceContainer
    ):
        """Config save succeeds when MQTT is disabled."""
        mqtt_service = container.mqtt_service()

        # Disable MQTT by setting enabled flag
        mqtt_service.enabled = False

        response = client.put(
            f"/api/configs/{valid_mac}",
            json={"content": sample_config},
            content_type="application/json",
        )

        # API should return success when MQTT is disabled
        assert response.status_code == 200
