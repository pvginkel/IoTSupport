"""Tests for configuration API endpoints."""

import json
from typing import Any
from unittest.mock import patch

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import Session

from app.services.container import ServiceContainer


class TestListConfigs:
    """Tests for GET /api/configs."""

    def test_list_configs_empty(self, client: FlaskClient, session: Session):
        """Empty database returns empty list with 200."""
        response = client.get("/api/configs")

        assert response.status_code == 200
        data = response.get_json()
        assert data["configs"] == []
        assert data["count"] == 0

    def test_list_configs_returns_summary(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
    ):
        """Configs are returned with correct summary format including ID."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config("aa:bb:cc:dd:ee:ff", sample_config)
            config_id = created.id

        response = client.get("/api/configs")

        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 1
        assert len(data["configs"]) == 1

        config = data["configs"][0]
        assert config["id"] == config_id
        assert config["mac_address"] == "aa:bb:cc:dd:ee:ff"
        assert config["device_name"] == "Living Room Sensor"
        assert config["device_entity_id"] == "sensor.living_room"
        assert config["enable_ota"] is True

    def test_list_configs_sorted_by_mac(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
    ):
        """Configs are returned sorted by MAC address."""
        with app.app_context():
            service = container.config_service()
            # Create in non-sorted order
            service.create_config("cc:cc:cc:cc:cc:cc", sample_config)
            service.create_config("aa:aa:aa:aa:aa:aa", sample_config)
            service.create_config("bb:bb:bb:bb:bb:bb", sample_config)

        response = client.get("/api/configs")

        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 3

        macs = [c["mac_address"] for c in data["configs"]]
        assert macs == ["aa:aa:aa:aa:aa:aa", "bb:bb:bb:bb:bb:bb", "cc:cc:cc:cc:cc:cc"]


class TestCreateConfig:
    """Tests for POST /api/configs."""

    def test_create_config_success(
        self, client: FlaskClient, session: Session, sample_config: str, sample_config_dict: dict[str, Any], valid_mac: str
    ):
        """Creating new config returns 201 with created config."""
        response = client.post(
            "/api/configs",
            json={"mac_address": valid_mac, "content": sample_config},
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["id"] is not None
        assert data["mac_address"] == valid_mac
        assert data["content"] == sample_config_dict  # Response parses JSON
        assert data["device_name"] == sample_config_dict["deviceName"]
        assert data["device_entity_id"] == sample_config_dict["deviceEntityId"]
        assert data["enable_ota"] == sample_config_dict["enableOTA"]
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_config_minimal(
        self, client: FlaskClient, session: Session, sample_config_minimal: str, valid_mac: str
    ):
        """Creating config with minimal content sets optional fields to None."""
        response = client.post(
            "/api/configs",
            json={"mac_address": valid_mac, "content": sample_config_minimal},
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["mac_address"] == valid_mac
        assert data["device_name"] is None
        assert data["device_entity_id"] is None
        assert data["enable_ota"] is None

    def test_create_config_normalizes_mac(
        self, client: FlaskClient, session: Session, sample_config: str
    ):
        """MAC address is normalized to lowercase colon-separated."""
        response = client.post(
            "/api/configs",
            json={"mac_address": "AA:BB:CC:DD:EE:FF", "content": sample_config},
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["mac_address"] == "aa:bb:cc:dd:ee:ff"

    def test_create_config_duplicate_mac_returns_409(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
        valid_mac: str,
    ):
        """Creating config with duplicate MAC returns 409."""
        # Create first config
        with app.app_context():
            service = container.config_service()
            service.create_config(valid_mac, sample_config)

        # Try to create duplicate
        response = client.post(
            "/api/configs",
            json={"mac_address": valid_mac, "content": sample_config},
            content_type="application/json",
        )

        assert response.status_code == 409
        data = response.get_json()
        assert data["code"] == "RECORD_EXISTS"
        assert valid_mac in data["error"]

    def test_create_config_invalid_mac_returns_400(
        self, client: FlaskClient, session: Session, sample_config: str
    ):
        """Creating config with invalid MAC format returns 400."""
        response = client.post(
            "/api/configs",
            json={"mac_address": "invalid-mac", "content": sample_config},
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "INVALID_OPERATION"
        assert "invalid format" in data["error"].lower()

    def test_create_config_short_mac_returns_400(
        self, client: FlaskClient, session: Session, sample_config: str
    ):
        """Creating config with short MAC returns 400."""
        response = client.post(
            "/api/configs",
            json={"mac_address": "aa:bb:cc", "content": sample_config},
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "INVALID_OPERATION"

    def test_create_config_missing_mac_address_returns_400(
        self, client: FlaskClient, session: Session, sample_config: str
    ):
        """Missing mac_address field returns 400."""
        response = client.post(
            "/api/configs",
            json={"content": sample_config},
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_create_config_missing_content_returns_400(
        self, client: FlaskClient, session: Session, valid_mac: str
    ):
        """Missing content field returns 400."""
        response = client.post(
            "/api/configs",
            json={"mac_address": valid_mac},
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_create_config_invalid_json_content_returns_400(
        self, client: FlaskClient, session: Session, valid_mac: str
    ):
        """Invalid JSON in content field returns 400."""
        response = client.post(
            "/api/configs",
            json={"mac_address": valid_mac, "content": "not valid json"},
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_create_config_invalid_json_returns_400(
        self, client: FlaskClient, session: Session
    ):
        """Invalid JSON body returns 400."""
        response = client.post(
            "/api/configs",
            data="not json",
            content_type="application/json",
        )

        assert response.status_code == 400


class TestGetConfigById:
    """Tests for GET /api/configs/<config_id>."""

    def test_get_config_success(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
        sample_config_dict: dict[str, Any],
        valid_mac: str,
    ):
        """Existing config returns 200 with full content."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)
            config_id = created.id

        response = client.get(f"/api/configs/{config_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == config_id
        assert data["mac_address"] == valid_mac
        assert data["content"] == sample_config_dict  # Response parses JSON
        assert data["device_name"] == sample_config_dict["deviceName"]

    def test_get_config_not_found(self, client: FlaskClient, session: Session):
        """Non-existent config ID returns 404."""
        response = client.get("/api/configs/99999")

        assert response.status_code == 404
        data = response.get_json()
        assert data["code"] == "RECORD_NOT_FOUND"
        assert "Config" in data["error"]
        assert "99999" in data["error"]


class TestUpdateConfig:
    """Tests for PUT /api/configs/<config_id>."""

    def test_update_config_success(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
        valid_mac: str,
    ):
        """Updating config returns 200 with updated content."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)
            config_id = created.id

        updated_content_dict = {
            "deviceName": "Updated Name",
            "deviceEntityId": "sensor.updated",
            "enableOTA": False,
            "mqttBroker": "mqtt.new",
        }
        updated_content = json.dumps(updated_content_dict)

        response = client.put(
            f"/api/configs/{config_id}",
            json={"content": updated_content},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == config_id
        assert data["mac_address"] == valid_mac  # MAC unchanged
        assert data["content"] == updated_content_dict  # Response parses JSON
        assert data["device_name"] == "Updated Name"
        assert data["device_entity_id"] == "sensor.updated"
        assert data["enable_ota"] is False

    def test_update_config_removes_optional_fields(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
        valid_mac: str,
    ):
        """Update with content lacking optional fields sets them to None."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)
            config_id = created.id

        minimal_content = json.dumps({"mqttBroker": "mqtt.local"})

        response = client.put(
            f"/api/configs/{config_id}",
            json={"content": minimal_content},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["device_name"] is None
        assert data["device_entity_id"] is None
        assert data["enable_ota"] is None

    def test_update_config_not_found(
        self, client: FlaskClient, session: Session, sample_config: str
    ):
        """Updating non-existent config returns 404."""
        response = client.put(
            "/api/configs/99999",
            json={"content": sample_config},
            content_type="application/json",
        )

        assert response.status_code == 404
        data = response.get_json()
        assert data["code"] == "RECORD_NOT_FOUND"

    def test_update_config_missing_content_returns_400(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
        valid_mac: str,
    ):
        """Missing content field returns 400."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)
            config_id = created.id

        response = client.put(
            f"/api/configs/{config_id}",
            json={},
            content_type="application/json",
        )

        assert response.status_code == 400


class TestDeleteConfig:
    """Tests for DELETE /api/configs/<config_id>."""

    def test_delete_config_success(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
        valid_mac: str,
    ):
        """Deleting existing config returns 204."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)
            config_id = created.id

        response = client.delete(f"/api/configs/{config_id}")

        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f"/api/configs/{config_id}")
        assert response.status_code == 404

    def test_delete_config_not_found(self, client: FlaskClient, session: Session):
        """Deleting non-existent config returns 404."""
        response = client.delete("/api/configs/99999")

        assert response.status_code == 404
        data = response.get_json()
        assert data["code"] == "RECORD_NOT_FOUND"


class TestGetConfigRaw:
    """Tests for GET /api/configs/<mac_address>.json (raw endpoint for ESP32 devices)."""

    def test_get_config_raw_success_colon_format(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
        sample_config_dict: dict[str, Any],
        valid_mac: str,
    ):
        """Existing config returns 200 with raw JSON content and Cache-Control header."""
        with app.app_context():
            service = container.config_service()
            service.create_config(valid_mac, sample_config)

        response = client.get(f"/api/configs/{valid_mac}.json")

        assert response.status_code == 200
        # Response should be raw JSON content, not wrapped
        data = response.get_json()
        assert data == sample_config_dict
        # Verify Cache-Control header is present
        assert response.headers.get("Cache-Control") == "no-cache"

    def test_get_config_raw_dash_format_backward_compat(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
        sample_config_dict: dict[str, Any],
    ):
        """Dash-separated MAC is normalized to colon format (backward compatibility)."""
        # Create config with colon-separated MAC
        with app.app_context():
            service = container.config_service()
            service.create_config("aa:bb:cc:dd:ee:ff", sample_config)

        # Request with dash-separated MAC
        response = client.get("/api/configs/aa-bb-cc-dd-ee-ff.json")

        assert response.status_code == 200
        data = response.get_json()
        assert data == sample_config_dict

    def test_get_config_raw_uppercase_normalized(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config: str,
        sample_config_dict: dict[str, Any],
    ):
        """Uppercase MAC is normalized to lowercase."""
        with app.app_context():
            service = container.config_service()
            service.create_config("aa:bb:cc:dd:ee:ff", sample_config)

        # Request with uppercase MAC
        response = client.get("/api/configs/AA:BB:CC:DD:EE:FF.json")

        assert response.status_code == 200
        data = response.get_json()
        assert data == sample_config_dict

    def test_get_config_raw_not_found(self, client: FlaskClient, session: Session, valid_mac: str):
        """Non-existent config returns 404."""
        response = client.get(f"/api/configs/{valid_mac}.json")

        assert response.status_code == 404
        data = response.get_json()
        assert data["code"] == "RECORD_NOT_FOUND"

    def test_get_config_raw_invalid_mac(self, client: FlaskClient, session: Session):
        """Invalid MAC format returns 400."""
        response = client.get("/api/configs/invalid-mac.json")

        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "INVALID_OPERATION"

    def test_get_config_raw_minimal_fields(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        container: ServiceContainer,
        sample_config_minimal: str,
        sample_config_minimal_dict: dict[str, Any],
        valid_mac: str,
    ):
        """Config with minimal fields returns correctly."""
        with app.app_context():
            service = container.config_service()
            service.create_config(valid_mac, sample_config_minimal)

        response = client.get(f"/api/configs/{valid_mac}.json")

        assert response.status_code == 200
        data = response.get_json()
        assert data == sample_config_minimal_dict


class TestConfigsWithMqtt:
    """Tests for MQTT integration in config API endpoints."""

    def test_create_config_publishes_mqtt_notification(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        sample_config: str,
        valid_mac: str,
        container: ServiceContainer,
    ):
        """Successful config create publishes MQTT notification."""
        mqtt_service = container.mqtt_service()
        with patch.object(mqtt_service, "publish_config_update") as mock_publish:
            response = client.post(
                "/api/configs",
                json={"mac_address": valid_mac, "content": sample_config},
                content_type="application/json",
            )

            assert response.status_code == 201

            # Verify MQTT notification was published with correct filename
            mock_publish.assert_called_once_with(f"{valid_mac}.json")

    def test_update_config_publishes_mqtt_notification(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        sample_config: str,
        sample_config_dict: dict[str, Any],
        valid_mac: str,
        container: ServiceContainer,
    ):
        """Updating config publishes MQTT notification."""
        # Create config first
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)
            config_id = created.id

        mqtt_service = container.mqtt_service()
        with patch.object(mqtt_service, "publish_config_update") as mock_publish:
            updated_content = json.dumps({**sample_config_dict, "deviceName": "Updated Name"})
            response = client.put(
                f"/api/configs/{config_id}",
                json={"content": updated_content},
                content_type="application/json",
            )

            assert response.status_code == 200
            mock_publish.assert_called_once_with(f"{valid_mac}.json")

    def test_create_config_failure_does_not_publish_mqtt(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        valid_mac: str,
        container: ServiceContainer,
    ):
        """Failed config create does not publish MQTT notification."""
        mqtt_service = container.mqtt_service()
        with patch.object(mqtt_service, "publish_config_update") as mock_publish:
            # Invalid request - missing content
            response = client.post(
                "/api/configs",
                json={"mac_address": valid_mac},
                content_type="application/json",
            )

            assert response.status_code == 400

            # MQTT should not be published on failure
            mock_publish.assert_not_called()

    def test_delete_config_does_not_publish_mqtt(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        sample_config: str,
        valid_mac: str,
        container: ServiceContainer,
    ):
        """Config deletion does NOT publish MQTT notification."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)
            config_id = created.id

        mqtt_service = container.mqtt_service()
        with patch.object(mqtt_service, "publish_config_update") as mock_publish:
            response = client.delete(f"/api/configs/{config_id}")

            assert response.status_code == 204

            # MQTT should NOT be published on delete
            mock_publish.assert_not_called()

    def test_create_config_mqtt_disabled_succeeds(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        sample_config: str,
        valid_mac: str,
        container: ServiceContainer,
    ):
        """Config create succeeds when MQTT is disabled."""
        mqtt_service = container.mqtt_service()

        # Disable MQTT by setting enabled flag
        mqtt_service.enabled = False

        response = client.post(
            "/api/configs",
            json={"mac_address": valid_mac, "content": sample_config},
            content_type="application/json",
        )

        # API should return success when MQTT is disabled
        assert response.status_code == 201


class TestConfigsMetrics:
    """Tests for metrics recording in config API endpoints."""

    def test_list_configs_records_metrics(
        self, client: FlaskClient, session: Session, container: ServiceContainer
    ):
        """List configs records operation metrics."""
        metrics_service = container.metrics_service()
        with patch.object(metrics_service, "record_operation") as mock_record:
            response = client.get("/api/configs")

            assert response.status_code == 200

            # Verify metrics were recorded
            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == "list"
            assert args[1] == "success"
            assert args[2] > 0  # duration should be positive

    def test_create_config_records_metrics_success(
        self,
        client: FlaskClient,
        session: Session,
        sample_config: str,
        valid_mac: str,
        container: ServiceContainer,
    ):
        """Successful config create records metrics with success status."""
        metrics_service = container.metrics_service()
        with patch.object(metrics_service, "record_operation") as mock_record:
            response = client.post(
                "/api/configs",
                json={"mac_address": valid_mac, "content": sample_config},
                content_type="application/json",
            )

            assert response.status_code == 201

            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == "create"
            assert args[1] == "success"

    def test_get_config_raw_records_metrics_success(
        self,
        app: Flask,
        client: FlaskClient,
        session: Session,
        sample_config: str,
        valid_mac: str,
        container: ServiceContainer,
    ):
        """Successful raw config get records metrics with success status."""
        with app.app_context():
            service = container.config_service()
            service.create_config(valid_mac, sample_config)

        metrics_service = container.metrics_service()
        with patch.object(metrics_service, "record_operation") as mock_record:
            response = client.get(f"/api/configs/{valid_mac}.json")

            assert response.status_code == 200

            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == "get_raw"
            assert args[1] == "success"

    def test_get_config_raw_records_metrics_error(
        self, client: FlaskClient, session: Session, valid_mac: str, container: ServiceContainer
    ):
        """Failed raw config get records metrics with error status."""
        metrics_service = container.metrics_service()
        with patch.object(metrics_service, "record_operation") as mock_record:
            # Request non-existent config
            response = client.get(f"/api/configs/{valid_mac}.json")

            assert response.status_code == 404

            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == "get_raw"
            assert args[1] == "error"
