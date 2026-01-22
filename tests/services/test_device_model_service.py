"""Tests for DeviceModelService."""

import pytest
from flask import Flask

from app.exceptions import (
    RecordExistsException,
    RecordNotFoundException,
    ValidationException,
)
from app.services.container import ServiceContainer


class TestDeviceModelServiceCreate:
    """Tests for creating device models."""

    def test_create_device_model_minimal(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test creating a device model with minimal fields."""
        with app.app_context():
            service = container.device_model_service()
            model = service.create_device_model(code="tempsensor", name="Temperature Sensor")

            assert model.id is not None
            assert model.code == "tempsensor"
            assert model.name == "Temperature Sensor"
            assert model.firmware_version is None
            assert model.created_at is not None
            assert model.updated_at is not None

    def test_create_device_model_duplicate_code_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that duplicate codes are rejected."""
        with app.app_context():
            service = container.device_model_service()
            service.create_device_model(code="sensor1", name="Sensor One")

            with pytest.raises(RecordExistsException) as exc_info:
                service.create_device_model(code="sensor1", name="Another Sensor")

            assert "already exists" in str(exc_info.value)

    def test_create_device_model_invalid_code_format_uppercase(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that uppercase codes are rejected."""
        with app.app_context():
            service = container.device_model_service()

            with pytest.raises(ValidationException) as exc_info:
                service.create_device_model(code="TempSensor", name="Test")

            assert "lowercase" in str(exc_info.value)

    def test_create_device_model_invalid_code_format_special_chars(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that special characters in codes are rejected."""
        with app.app_context():
            service = container.device_model_service()

            with pytest.raises(ValidationException) as exc_info:
                service.create_device_model(code="temp-sensor", name="Test")

            assert "alphanumeric" in str(exc_info.value) or "lowercase" in str(exc_info.value)

    def test_create_device_model_empty_code_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that empty codes are rejected."""
        with app.app_context():
            service = container.device_model_service()

            with pytest.raises(ValidationException):
                service.create_device_model(code="", name="Test")


class TestDeviceModelServiceGet:
    """Tests for retrieving device models."""

    def test_get_device_model_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test retrieving an existing device model."""
        with app.app_context():
            service = container.device_model_service()
            created = service.create_device_model(code="test1", name="Test Model")

            fetched = service.get_device_model(created.id)

            assert fetched.id == created.id
            assert fetched.code == "test1"
            assert fetched.name == "Test Model"

    def test_get_device_model_nonexistent_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that getting a nonexistent model raises RecordNotFoundException."""
        with app.app_context():
            service = container.device_model_service()

            with pytest.raises(RecordNotFoundException) as exc_info:
                service.get_device_model(99999)

            assert "DeviceModel" in str(exc_info.value)

    def test_get_device_model_by_code_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test retrieving a device model by code."""
        with app.app_context():
            service = container.device_model_service()
            created = service.create_device_model(code="bycode", name="By Code Model")

            fetched = service.get_device_model_by_code("bycode")

            assert fetched.id == created.id
            assert fetched.code == "bycode"

    def test_get_device_model_by_code_nonexistent_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that getting by nonexistent code raises RecordNotFoundException."""
        with app.app_context():
            service = container.device_model_service()

            with pytest.raises(RecordNotFoundException):
                service.get_device_model_by_code("nonexistent")


class TestDeviceModelServiceList:
    """Tests for listing device models."""

    def test_list_device_models_empty(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test listing when no models exist."""
        with app.app_context():
            service = container.device_model_service()
            models = service.list_device_models()

            assert models == []

    def test_list_device_models_returns_all(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that list returns all created models."""
        with app.app_context():
            service = container.device_model_service()
            service.create_device_model(code="model1", name="Model One")
            service.create_device_model(code="model2", name="Model Two")
            service.create_device_model(code="model3", name="Model Three")

            models = service.list_device_models()

            assert len(models) == 3
            codes = {m.code for m in models}
            assert codes == {"model1", "model2", "model3"}

    def test_list_device_models_ordered_by_code(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that models are returned ordered by code."""
        with app.app_context():
            service = container.device_model_service()
            service.create_device_model(code="zmodel", name="Z Model")
            service.create_device_model(code="amodel", name="A Model")
            service.create_device_model(code="mmodel", name="M Model")

            models = service.list_device_models()

            codes = [m.code for m in models]
            assert codes == ["amodel", "mmodel", "zmodel"]


class TestDeviceModelServiceUpdate:
    """Tests for updating device models."""

    def test_update_device_model_name(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test updating a device model's name."""
        with app.app_context():
            service = container.device_model_service()
            model = service.create_device_model(code="update1", name="Original Name")

            updated = service.update_device_model(model.id, name="Updated Name")

            assert updated.name == "Updated Name"
            assert updated.code == "update1"  # Code unchanged

    def test_update_device_model_nonexistent_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that updating a nonexistent model raises RecordNotFoundException."""
        with app.app_context():
            service = container.device_model_service()

            with pytest.raises(RecordNotFoundException):
                service.update_device_model(99999, name="New Name")


class TestDeviceModelServiceDelete:
    """Tests for deleting device models."""

    def test_delete_device_model_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test deleting an existing device model."""
        with app.app_context():
            service = container.device_model_service()
            model = service.create_device_model(code="delete1", name="To Delete")
            model_id = model.id

            # delete_device_model returns None
            service.delete_device_model(model_id)

            # Verify it's gone
            with pytest.raises(RecordNotFoundException):
                service.get_device_model(model_id)

    def test_delete_device_model_nonexistent_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that deleting a nonexistent model raises RecordNotFoundException."""
        with app.app_context():
            service = container.device_model_service()

            with pytest.raises(RecordNotFoundException):
                service.delete_device_model(99999)
