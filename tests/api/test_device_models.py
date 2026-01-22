"""Tests for device models API endpoints."""

from flask import Flask
from flask.testing import FlaskClient

from app.services.container import ServiceContainer


class TestDeviceModelsList:
    """Tests for GET /api/device-models."""

    def test_list_device_models_empty(self, client: FlaskClient) -> None:
        """Test listing when no device models exist."""
        response = client.get("/api/device-models")

        assert response.status_code == 200
        data = response.get_json()
        assert data["device_models"] == []

    def test_list_device_models_returns_all(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that list returns all device models."""
        with app.app_context():
            service = container.device_model_service()
            service.create_device_model(code="model1", name="Model One")
            service.create_device_model(code="model2", name="Model Two")

        response = client.get("/api/device-models")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["device_models"]) == 2


class TestDeviceModelsCreate:
    """Tests for POST /api/device-models."""

    def test_create_device_model_success(self, client: FlaskClient) -> None:
        """Test creating a device model."""
        response = client.post(
            "/api/device-models",
            json={"code": "sensor", "name": "Temperature Sensor"},
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["code"] == "sensor"
        assert data["name"] == "Temperature Sensor"
        assert data["id"] is not None

    def test_create_device_model_duplicate_code(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test that duplicate code returns 409 CONFLICT."""
        with app.app_context():
            service = container.device_model_service()
            service.create_device_model(code="dup", name="Existing")

        response = client.post(
            "/api/device-models",
            json={"code": "dup", "name": "Duplicate"},
        )

        assert response.status_code == 409
        data = response.get_json()
        assert "already exists" in data["error"]

    def test_create_device_model_invalid_code(self, client: FlaskClient) -> None:
        """Test that invalid code returns 400."""
        response = client.post(
            "/api/device-models",
            json={"code": "Invalid-Code", "name": "Test"},
        )

        assert response.status_code == 400

    def test_create_device_model_missing_fields(self, client: FlaskClient) -> None:
        """Test that missing required fields returns 400 or 422."""
        response = client.post("/api/device-models", json={})

        assert response.status_code in [400, 422]


class TestDeviceModelsGet:
    """Tests for GET /api/device-models/<id>."""

    def test_get_device_model_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test getting a device model by ID."""
        with app.app_context():
            service = container.device_model_service()
            model = service.create_device_model(code="get1", name="Get Test")
            model_id = model.id

        response = client.get(f"/api/device-models/{model_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["code"] == "get1"
        assert data["name"] == "Get Test"

    def test_get_device_model_not_found(self, client: FlaskClient) -> None:
        """Test getting a nonexistent device model returns 404."""
        response = client.get("/api/device-models/99999")

        assert response.status_code == 404


class TestDeviceModelsUpdate:
    """Tests for PUT /api/device-models/<id>."""

    def test_update_device_model_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test updating a device model."""
        with app.app_context():
            service = container.device_model_service()
            model = service.create_device_model(code="upd1", name="Original")
            model_id = model.id

        response = client.put(
            f"/api/device-models/{model_id}",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Updated Name"

    def test_update_device_model_not_found(self, client: FlaskClient) -> None:
        """Test updating a nonexistent device model returns 404."""
        response = client.put(
            "/api/device-models/99999",
            json={"name": "Updated"},
        )

        assert response.status_code == 404


class TestDeviceModelsDelete:
    """Tests for DELETE /api/device-models/<id>."""

    def test_delete_device_model_success(
        self, app: Flask, client: FlaskClient, container: ServiceContainer
    ) -> None:
        """Test deleting a device model."""
        with app.app_context():
            service = container.device_model_service()
            model = service.create_device_model(code="del1", name="To Delete")
            model_id = model.id

        response = client.delete(f"/api/device-models/{model_id}")

        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f"/api/device-models/{model_id}")
        assert response.status_code == 404

    def test_delete_device_model_not_found(self, client: FlaskClient) -> None:
        """Test deleting a nonexistent device model returns 404."""
        response = client.delete("/api/device-models/99999")

        assert response.status_code == 404
