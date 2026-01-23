"""Tests for DeviceService."""

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.exceptions import (
    ExternalServiceException,
    RecordNotFoundException,
    ValidationException,
)
from app.models.device import RotationState
from app.services.container import ServiceContainer


class TestDeviceServiceCreate:
    """Tests for creating devices."""

    def test_create_device_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test creating a device with Keycloak client mocked."""
        with app.app_context():
            # Create a device model first
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="sensor", name="Sensor")

            # Mock Keycloak service
            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                return_value=MagicMock(client_id="iotdevice-sensor-abc12345", secret="test-secret"),
            ), patch.object(
                keycloak_service,
                "update_client_metadata",
            ):
                device_service = container.device_service()
                device = device_service.create_device(
                    device_model_id=model.id,
                    config='{"setting": "value"}'
                )

                assert device.id is not None
                assert len(device.key) == 8
                assert device.device_model_id == model.id
                assert device.config == '{"setting": "value"}'
                assert device.rotation_state == RotationState.OK.value
                assert device.secret_created_at is not None

    def test_create_device_invalid_model_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that creating a device with invalid model ID raises error."""
        with app.app_context():
            device_service = container.device_service()

            with pytest.raises(RecordNotFoundException):
                device_service.create_device(device_model_id=99999, config="{}")

    def test_create_device_invalid_json_config_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that invalid JSON config raises ValidationException."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="test1", name="Test")

            device_service = container.device_service()

            with pytest.raises(ValidationException) as exc_info:
                device_service.create_device(device_model_id=model.id, config="not json")

            assert "valid JSON" in str(exc_info.value)

    def test_create_device_keycloak_failure_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that Keycloak failure during creation raises ExternalServiceException."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="test2", name="Test")

            keycloak_service = container.keycloak_admin_service()
            with patch.object(
                keycloak_service,
                "create_client",
                side_effect=ExternalServiceException("create client", "connection failed"),
            ):
                device_service = container.device_service()

                with pytest.raises(ExternalServiceException):
                    device_service.create_device(device_model_id=model.id, config="{}")


class TestDeviceServiceGet:
    """Tests for retrieving devices."""

    def test_get_device_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test retrieving a device by ID."""
        with app.app_context():
            # Create model and device
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
                created = device_service.create_device(device_model_id=model.id, config="{}")

                fetched = device_service.get_device(created.id)

                assert fetched.id == created.id
                assert fetched.key == created.key

    def test_get_device_nonexistent_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that getting nonexistent device raises RecordNotFoundException."""
        with app.app_context():
            device_service = container.device_service()

            with pytest.raises(RecordNotFoundException):
                device_service.get_device(99999)

    def test_get_device_by_key_success(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test retrieving a device by key."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="key1", name="Key Test")

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
                created = device_service.create_device(device_model_id=model.id, config="{}")

                fetched = device_service.get_device_by_key(created.key)

                assert fetched.id == created.id

    def test_get_device_by_key_nonexistent_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that getting by nonexistent key raises RecordNotFoundException."""
        with app.app_context():
            device_service = container.device_service()

            with pytest.raises(RecordNotFoundException):
                device_service.get_device_by_key("notexist")


class TestDeviceServiceList:
    """Tests for listing devices."""

    def test_list_devices_empty(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test listing when no devices exist."""
        with app.app_context():
            device_service = container.device_service()
            devices = device_service.list_devices()

            assert devices == []

    def test_list_devices_returns_all(
        self, app: Flask, container: ServiceContainer
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
                device_service.create_device(device_model_id=model.id, config="{}")

                devices = device_service.list_devices()

                assert len(devices) == 3

    def test_list_devices_filter_by_model_id(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test filtering devices by model ID."""
        with app.app_context():
            model_service = container.device_model_service()
            model1 = model_service.create_device_model(code="filter1", name="Filter One")
            model2 = model_service.create_device_model(code="filter2", name="Filter Two")

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
                device_service.create_device(device_model_id=model1.id, config="{}")
                device_service.create_device(device_model_id=model2.id, config="{}")

                devices = device_service.list_devices(model_id=model1.id)

                assert len(devices) == 2
                assert all(d.device_model_id == model1.id for d in devices)

    def test_list_devices_filter_by_rotation_state(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test filtering devices by rotation state."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="state1", name="State Test")

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
                d1 = device_service.create_device(device_model_id=model.id, config="{}")
                d2 = device_service.create_device(device_model_id=model.id, config="{}")

                # Manually change one device's state
                d2.rotation_state = RotationState.QUEUED.value

                devices = device_service.list_devices(rotation_state=RotationState.OK.value)

                assert len(devices) == 1
                assert devices[0].id == d1.id


class TestDeviceServiceUpdate:
    """Tests for updating devices."""

    def test_update_device_config(
        self, app: Flask, container: ServiceContainer
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
                    device_model_id=model.id,
                    config='{"old": "value"}'
                )

                updated = device_service.update_device(
                    device.id,
                    config='{"new": "value"}'
                )

                assert updated.config == '{"new": "value"}'

    def test_update_device_invalid_json_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that invalid JSON config update raises ValidationException."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="upd2", name="Update Test 2")

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

                with pytest.raises(ValidationException):
                    device_service.update_device(device.id, config="not json")

    def test_update_device_nonexistent_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that updating nonexistent device raises RecordNotFoundException."""
        with app.app_context():
            device_service = container.device_service()

            with pytest.raises(RecordNotFoundException):
                device_service.update_device(99999, config="{}")


class TestDeviceServiceDelete:
    """Tests for deleting devices."""

    def test_delete_device_success(
        self, app: Flask, container: ServiceContainer
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
                device_key = device.key

                with patch.object(keycloak_service, "delete_client"):
                    key = device_service.delete_device(device_id)

                assert key == device_key

                # Verify it's gone
                with pytest.raises(RecordNotFoundException):
                    device_service.get_device(device_id)

    def test_delete_device_nonexistent_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that deleting nonexistent device raises RecordNotFoundException."""
        with app.app_context():
            device_service = container.device_service()

            with pytest.raises(RecordNotFoundException):
                device_service.delete_device(99999)


class TestDeviceServiceRotation:
    """Tests for rotation-related device operations."""

    def test_trigger_rotation_from_ok_state(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test triggering rotation for a device in OK state."""
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

                result = device_service.trigger_rotation(device.id)

                assert result == "queued"
                assert device.rotation_state == RotationState.QUEUED.value

    def test_trigger_rotation_already_pending(
        self, app: Flask, container: ServiceContainer
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

                result = device_service.trigger_rotation(device.id)

                assert result == "already_pending"

    def test_get_device_by_client_id(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test getting device by Keycloak client ID."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="client1", name="Client Test")

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

                # Build the expected client_id format
                client_id = f"iotdevice-{model.code}-{device.key}"

                fetched = device_service.get_device_by_client_id(client_id)

                assert fetched.id == device.id

    def test_get_device_by_client_id_invalid_format(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that invalid client ID format raises ValidationException."""
        with app.app_context():
            device_service = container.device_service()

            with pytest.raises(ValidationException):
                device_service.get_device_by_client_id("invalid-format")


class TestDeviceServiceSecretCaching:
    """Tests for secret caching during rotation."""

    def test_cache_and_retrieve_secret(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test caching and retrieving a secret."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="cache1", name="Cache Test")

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

                # Cache a secret
                device_service.cache_secret_for_rotation(device, "my-secret-value")

                # Retrieve it
                cached = device_service.get_cached_secret(device)

                assert cached == "my-secret-value"

    def test_clear_cached_secret(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test clearing a cached secret."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="cache2", name="Cache Test 2")

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

                # Cache and then clear
                device_service.cache_secret_for_rotation(device, "secret")
                device_service.clear_cached_secret(device)

                cached = device_service.get_cached_secret(device)

                assert cached is None

    def test_get_cached_secret_when_not_set(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test getting cached secret when none is set."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="cache3", name="Cache Test 3")

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

                cached = device_service.get_cached_secret(device)

                assert cached is None


class TestDeviceServiceFieldExtraction:
    """Tests for config field extraction."""

    def test_create_device_extracts_fields(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that creating a device extracts fields from config."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="extract1", name="Extract Test")

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
                config = '{"deviceName": "Living Room Sensor", "deviceEntityId": "sensor.living_room", "enableOTA": true}'
                device = device_service.create_device(
                    device_model_id=model.id,
                    config=config
                )

                assert device.device_name == "Living Room Sensor"
                assert device.device_entity_id == "sensor.living_room"
                assert device.enable_ota is True

    def test_update_device_extracts_fields(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that updating a device extracts fields from config."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="extract2", name="Extract Test 2")

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
                    config='{"deviceName": "Old Name"}'
                )

                assert device.device_name == "Old Name"

                # Update with new values
                updated = device_service.update_device(
                    device.id,
                    config='{"deviceName": "New Name", "enableOTA": false}'
                )

                assert updated.device_name == "New Name"
                assert updated.enable_ota is False

    def test_create_device_handles_missing_fields(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test that missing config fields result in None values."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="extract3", name="Extract Test 3")

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
                    config='{"otherField": "value"}'
                )

                assert device.device_name is None
                assert device.device_entity_id is None
                assert device.enable_ota is None


class TestDeviceServiceKeycloakStatus:
    """Tests for Keycloak status methods."""

    def test_get_keycloak_status_client_exists(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test get_keycloak_status when client exists in Keycloak."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="kc1", name="Keycloak Test")

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

                # Mock get_client_status to return exists=True
                with patch.object(
                    keycloak_service,
                    "get_client_status",
                    return_value=(True, "uuid-123"),
                ):
                    status = device_service.get_keycloak_status(device.id)

                    assert status["exists"] is True
                    assert status["client_id"] == device.client_id
                    assert status["keycloak_uuid"] == "uuid-123"
                    # console_url depends on config, may be None in test env
                    assert "console_url" in status

    def test_get_keycloak_status_client_missing(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test get_keycloak_status when client is missing from Keycloak."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="kc2", name="Keycloak Test 2")

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

                # Mock get_client_status to return exists=False
                with patch.object(
                    keycloak_service,
                    "get_client_status",
                    return_value=(False, None),
                ):
                    status = device_service.get_keycloak_status(device.id)

                    assert status["exists"] is False
                    assert status["client_id"] == device.client_id
                    assert status["keycloak_uuid"] is None
                    assert status["console_url"] is None

    def test_get_keycloak_status_device_not_found(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test get_keycloak_status raises for nonexistent device."""
        with app.app_context():
            device_service = container.device_service()

            with pytest.raises(RecordNotFoundException):
                device_service.get_keycloak_status(99999)

    def test_sync_keycloak_client_creates_missing(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test sync_keycloak_client creates client when missing."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="kc3", name="Keycloak Test 3")

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
                config = '{"deviceName": "Living Room Sensor"}'
                device = device_service.create_device(device_model_id=model.id, config=config)

                # Mock create_client, update_client_metadata, and get_client_status
                with patch.object(
                    keycloak_service,
                    "create_client",
                    return_value=MagicMock(client_id="test", secret="test-secret"),
                ) as mock_create, patch.object(
                    keycloak_service,
                    "update_client_metadata",
                ) as mock_update_metadata, patch.object(
                    keycloak_service,
                    "get_client_status",
                    return_value=(True, "uuid-456"),
                ):
                    status = device_service.sync_keycloak_client(device.id)

                    mock_create.assert_called_once_with(device.client_id)
                    mock_update_metadata.assert_called_once_with(
                        device.client_id,
                        name="Living Room Sensor",
                        description="This device is being managed in IoT Support.",
                    )
                    assert status["exists"] is True
                    assert status["keycloak_uuid"] == "uuid-456"

    def test_sync_keycloak_client_idempotent(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test sync_keycloak_client is idempotent when client already exists."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(code="kc4", name="Keycloak Test 4")

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

                # create_client is idempotent and returns existing client
                with patch.object(
                    keycloak_service,
                    "create_client",
                    return_value=MagicMock(client_id="test", secret="existing-secret"),
                ), patch.object(
                    keycloak_service,
                    "update_client_metadata",
                ), patch.object(
                    keycloak_service,
                    "get_client_status",
                    return_value=(True, "existing-uuid"),
                ):
                    status = device_service.sync_keycloak_client(device.id)

                    assert status["exists"] is True
                    assert status["keycloak_uuid"] == "existing-uuid"

    def test_sync_keycloak_client_device_not_found(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test sync_keycloak_client raises for nonexistent device."""
        with app.app_context():
            device_service = container.device_service()

            with pytest.raises(RecordNotFoundException):
                device_service.sync_keycloak_client(99999)


class TestDeviceServiceSchemaValidation:
    """Tests for JSON schema validation."""

    def test_create_device_with_schema_valid_config(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test creating a device with valid config matching schema."""
        with app.app_context():
            schema = '''{
                "type": "object",
                "required": ["deviceName"],
                "properties": {
                    "deviceName": {"type": "string"},
                    "enableOTA": {"type": "boolean"}
                }
            }'''

            model_service = container.device_model_service()
            model = model_service.create_device_model(
                code="schema1", name="Schema Test", config_schema=schema
            )

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
                    config='{"deviceName": "Test Device", "enableOTA": true}'
                )

                assert device.id is not None
                assert device.device_name == "Test Device"

    def test_create_device_with_schema_invalid_config_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test creating a device with invalid config fails schema validation."""
        with app.app_context():
            schema = '''{
                "type": "object",
                "required": ["deviceName"],
                "properties": {
                    "deviceName": {"type": "string"}
                }
            }'''

            model_service = container.device_model_service()
            model = model_service.create_device_model(
                code="schema2", name="Schema Test 2", config_schema=schema
            )

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

                # Missing required field "deviceName"
                with pytest.raises(ValidationException) as exc_info:
                    device_service.create_device(
                        device_model_id=model.id,
                        config='{"otherField": "value"}'
                    )

                assert "deviceName" in str(exc_info.value)

    def test_create_device_with_schema_wrong_type_raises(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test creating a device with wrong type fails schema validation."""
        with app.app_context():
            schema = '''{
                "type": "object",
                "properties": {
                    "enableOTA": {"type": "boolean"}
                }
            }'''

            model_service = container.device_model_service()
            model = model_service.create_device_model(
                code="schema3", name="Schema Test 3", config_schema=schema
            )

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

                # enableOTA should be boolean, not string
                with pytest.raises(ValidationException) as exc_info:
                    device_service.create_device(
                        device_model_id=model.id,
                        config='{"enableOTA": "yes"}'
                    )

                assert "enableOTA" in str(exc_info.value) or "boolean" in str(exc_info.value)

    def test_update_device_with_schema_validates(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test updating a device validates against schema."""
        with app.app_context():
            schema = '''{
                "type": "object",
                "required": ["deviceName"],
                "properties": {
                    "deviceName": {"type": "string"}
                }
            }'''

            model_service = container.device_model_service()
            model = model_service.create_device_model(
                code="schema4", name="Schema Test 4", config_schema=schema
            )

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
                    config='{"deviceName": "Original"}'
                )

                # Update with invalid config (missing required field)
                with pytest.raises(ValidationException):
                    device_service.update_device(device.id, config='{"other": "value"}')

    def test_create_device_without_schema_skips_validation(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """Test creating a device without schema accepts any valid JSON."""
        with app.app_context():
            model_service = container.device_model_service()
            model = model_service.create_device_model(
                code="schema5", name="Schema Test 5"
                # No config_schema
            )

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
                # Any JSON should be accepted
                device = device_service.create_device(
                    device_model_id=model.id,
                    config='{"anything": "goes", "nested": {"ok": true}}'
                )

                assert device.id is not None
