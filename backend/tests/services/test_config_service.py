"""Tests for ConfigService with database backend."""

from typing import Any

import pytest
from flask import Flask
from sqlalchemy.orm import Session

from app.exceptions import (
    InvalidOperationException,
    RecordExistsException,
    RecordNotFoundException,
)
from app.services.config_service import ConfigService
from app.services.container import ServiceContainer


class TestConfigServiceList:
    """Tests for ConfigService.list_configs()."""

    def test_list_configs_empty(self, app: Flask, session: Session, container: ServiceContainer):
        """Test listing configs when database is empty."""
        with app.app_context():
            service = container.config_service()
            configs = service.list_configs()
            assert configs == []

    def test_list_configs_with_data(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any]):
        """Test listing configs returns all configs sorted by MAC."""
        with app.app_context():
            service = container.config_service()

            # Create two configs in non-alphabetical order
            service.create_config("bb:bb:bb:bb:bb:bb", sample_config)
            service.create_config("aa:aa:aa:aa:aa:aa", sample_config)

            configs = service.list_configs()

            assert len(configs) == 2
            # Should be sorted by MAC address
            assert configs[0].mac_address == "aa:aa:aa:aa:aa:aa"
            assert configs[1].mac_address == "bb:bb:bb:bb:bb:bb"


class TestConfigServiceGetById:
    """Tests for ConfigService.get_config_by_id()."""

    def test_get_config_by_id_success(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any], valid_mac: str):
        """Test getting config by ID returns correct config."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)

            config = service.get_config_by_id(created.id)

            assert config.id == created.id
            assert config.mac_address == valid_mac
            assert config.device_name == sample_config["deviceName"]

    def test_get_config_by_id_not_found(self, app: Flask, session: Session, container: ServiceContainer):
        """Test getting non-existent config raises RecordNotFoundException."""
        with app.app_context():
            service = container.config_service()

            with pytest.raises(RecordNotFoundException) as exc_info:
                service.get_config_by_id(99999)

            assert "Config" in str(exc_info.value.message)
            assert "99999" in str(exc_info.value.message)


class TestConfigServiceGetByMac:
    """Tests for ConfigService.get_config_by_mac()."""

    def test_get_config_by_mac_success(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any], valid_mac: str):
        """Test getting config by MAC address."""
        with app.app_context():
            service = container.config_service()
            service.create_config(valid_mac, sample_config)

            config = service.get_config_by_mac(valid_mac)

            assert config.mac_address == valid_mac
            assert config.device_name == sample_config["deviceName"]

    def test_get_config_by_mac_uppercase_normalization(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any]):
        """Test MAC address is normalized to lowercase."""
        with app.app_context():
            service = container.config_service()
            service.create_config("aa:bb:cc:dd:ee:ff", sample_config)

            # Request with uppercase should work
            config = service.get_config_by_mac("AA:BB:CC:DD:EE:FF")

            assert config.mac_address == "aa:bb:cc:dd:ee:ff"

    def test_get_config_by_mac_dash_separator_normalization(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any]):
        """Test dash-separated MAC is normalized to colon-separated."""
        with app.app_context():
            service = container.config_service()
            service.create_config("aa:bb:cc:dd:ee:ff", sample_config)

            # Request with dashes should work (backward compatibility)
            config = service.get_config_by_mac("aa-bb-cc-dd-ee-ff")

            assert config.mac_address == "aa:bb:cc:dd:ee:ff"

    def test_get_config_by_mac_not_found(self, app: Flask, session: Session, container: ServiceContainer, valid_mac: str):
        """Test getting non-existent MAC raises RecordNotFoundException."""
        with app.app_context():
            service = container.config_service()

            with pytest.raises(RecordNotFoundException) as exc_info:
                service.get_config_by_mac(valid_mac)

            assert "Config" in str(exc_info.value.message)

    def test_get_config_by_mac_invalid_format(self, app: Flask, session: Session, container: ServiceContainer):
        """Test invalid MAC format raises InvalidOperationException."""
        with app.app_context():
            service = container.config_service()

            with pytest.raises(InvalidOperationException) as exc_info:
                service.get_config_by_mac("invalid-mac")

            assert "invalid format" in str(exc_info.value.message)


class TestConfigServiceGetRaw:
    """Tests for ConfigService.get_raw_config()."""

    def test_get_raw_config_success(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any], valid_mac: str):
        """Test getting raw config content."""
        with app.app_context():
            service = container.config_service()
            service.create_config(valid_mac, sample_config)

            content = service.get_raw_config(valid_mac)

            assert content == sample_config

    def test_get_raw_config_with_dash_separator(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any]):
        """Test raw config works with dash-separated MAC for backward compatibility."""
        with app.app_context():
            service = container.config_service()
            service.create_config("aa:bb:cc:dd:ee:ff", sample_config)

            content = service.get_raw_config("aa-bb-cc-dd-ee-ff")

            assert content == sample_config


class TestConfigServiceCreate:
    """Tests for ConfigService.create_config()."""

    def test_create_config_full_data(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any], valid_mac: str):
        """Test creating config with all fields."""
        with app.app_context():
            service = container.config_service()

            config = service.create_config(valid_mac, sample_config)

            assert config.id is not None
            assert config.mac_address == valid_mac
            assert config.device_name == sample_config["deviceName"]
            assert config.device_entity_id == sample_config["deviceEntityId"]
            assert config.enable_ota == sample_config["enableOTA"]
            assert config.created_at is not None
            assert config.updated_at is not None

    def test_create_config_minimal(self, app: Flask, session: Session, container: ServiceContainer, sample_config_minimal: dict[str, Any], valid_mac: str):
        """Test creating config with minimal fields."""
        with app.app_context():
            service = container.config_service()

            config = service.create_config(valid_mac, sample_config_minimal)

            assert config.id is not None
            assert config.mac_address == valid_mac
            assert config.device_name is None
            assert config.device_entity_id is None
            assert config.enable_ota is None

    def test_create_config_normalizes_mac(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any]):
        """Test MAC address is normalized to lowercase colon-separated."""
        with app.app_context():
            service = container.config_service()

            config = service.create_config("AA:BB:CC:DD:EE:FF", sample_config)

            assert config.mac_address == "aa:bb:cc:dd:ee:ff"

    def test_create_config_duplicate_mac_raises(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any], valid_mac: str):
        """Test creating config with duplicate MAC raises RecordExistsException."""
        with app.app_context():
            service = container.config_service()
            service.create_config(valid_mac, sample_config)

            with pytest.raises(RecordExistsException) as exc_info:
                service.create_config(valid_mac, sample_config)

            assert "Config" in str(exc_info.value.message)
            assert valid_mac in str(exc_info.value.message)

    def test_create_config_invalid_mac_format(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any]):
        """Test creating config with invalid MAC raises InvalidOperationException."""
        with app.app_context():
            service = container.config_service()

            with pytest.raises(InvalidOperationException) as exc_info:
                service.create_config("invalid", sample_config)

            assert "invalid format" in str(exc_info.value.message)

    def test_create_config_short_mac(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any]):
        """Test creating config with short MAC raises error."""
        with app.app_context():
            service = container.config_service()

            with pytest.raises(InvalidOperationException):
                service.create_config("aa:bb:cc", sample_config)


class TestConfigServiceUpdate:
    """Tests for ConfigService.update_config()."""

    def test_update_config_success(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any], valid_mac: str):
        """Test updating config content."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)

            new_content = {
                "deviceName": "Updated Name",
                "deviceEntityId": "sensor.updated",
                "enableOTA": False,
                "mqttBroker": "mqtt.new",
            }

            updated = service.update_config(created.id, new_content)

            assert updated.device_name == "Updated Name"
            assert updated.device_entity_id == "sensor.updated"
            assert updated.enable_ota is False

    def test_update_config_removes_optional_fields(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any], valid_mac: str):
        """Test updating config with content lacking optional fields sets them to None."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)

            # Update with content lacking deviceName, deviceEntityId, enableOTA
            minimal_content = {"mqttBroker": "mqtt.local"}

            updated = service.update_config(created.id, minimal_content)

            assert updated.device_name is None
            assert updated.device_entity_id is None
            assert updated.enable_ota is None

    def test_update_config_not_found(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any]):
        """Test updating non-existent config raises RecordNotFoundException."""
        with app.app_context():
            service = container.config_service()

            with pytest.raises(RecordNotFoundException) as exc_info:
                service.update_config(99999, sample_config)

            assert "Config" in str(exc_info.value.message)


class TestConfigServiceDelete:
    """Tests for ConfigService.delete_config()."""

    def test_delete_config_success(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any], valid_mac: str):
        """Test deleting config removes it from database."""
        with app.app_context():
            service = container.config_service()
            created = service.create_config(valid_mac, sample_config)

            mac_address = service.delete_config(created.id)

            assert mac_address == valid_mac

            with pytest.raises(RecordNotFoundException):
                service.get_config_by_id(created.id)

    def test_delete_config_not_found(self, app: Flask, session: Session, container: ServiceContainer):
        """Test deleting non-existent config raises RecordNotFoundException."""
        with app.app_context():
            service = container.config_service()

            with pytest.raises(RecordNotFoundException) as exc_info:
                service.delete_config(99999)

            assert "Config" in str(exc_info.value.message)


class TestConfigServiceCount:
    """Tests for ConfigService.count_configs()."""

    def test_count_configs_empty(self, app: Flask, session: Session, container: ServiceContainer):
        """Test counting configs when empty."""
        with app.app_context():
            service = container.config_service()
            count = service.count_configs()
            assert count == 0

    def test_count_configs_with_data(self, app: Flask, session: Session, container: ServiceContainer, sample_config: dict[str, Any]):
        """Test counting configs with data."""
        with app.app_context():
            service = container.config_service()
            service.create_config("aa:aa:aa:aa:aa:aa", sample_config)
            service.create_config("bb:bb:bb:bb:bb:bb", sample_config)

            count = service.count_configs()
            assert count == 2


class TestConfigServiceMacValidation:
    """Tests for MAC address validation and normalization."""

    def test_normalize_mac_lowercase(self):
        """Test normalization converts to lowercase."""
        result = ConfigService.normalize_mac_address("AA:BB:CC:DD:EE:FF")
        assert result == "aa:bb:cc:dd:ee:ff"

    def test_normalize_mac_dash_to_colon(self):
        """Test normalization converts dashes to colons."""
        result = ConfigService.normalize_mac_address("aa-bb-cc-dd-ee-ff")
        assert result == "aa:bb:cc:dd:ee:ff"

    def test_normalize_mac_combined(self):
        """Test normalization handles uppercase and dashes together."""
        result = ConfigService.normalize_mac_address("AA-BB-CC-DD-EE-FF")
        assert result == "aa:bb:cc:dd:ee:ff"

    def test_validate_mac_valid(self):
        """Test validation accepts valid MAC."""
        assert ConfigService.validate_mac_address("aa:bb:cc:dd:ee:ff") is True

    def test_validate_mac_invalid_format(self):
        """Test validation rejects invalid format."""
        assert ConfigService.validate_mac_address("invalid") is False
        assert ConfigService.validate_mac_address("aa:bb:cc") is False
        assert ConfigService.validate_mac_address("aa:bb:cc:dd:ee:ff:gg") is False

    def test_validate_mac_rejects_dash_format(self):
        """Test validation rejects dash-separated format (must be normalized first)."""
        assert ConfigService.validate_mac_address("aa-bb-cc-dd-ee-ff") is False

    def test_validate_mac_rejects_uppercase(self):
        """Test validation rejects uppercase (must be normalized first)."""
        assert ConfigService.validate_mac_address("AA:BB:CC:DD:EE:FF") is False


class TestConfigServiceContentExtraction:
    """Tests for content field extraction."""

    def test_extracts_device_name(self, app: Flask, session: Session, container: ServiceContainer, valid_mac: str):
        """Test deviceName is extracted from content."""
        with app.app_context():
            service = container.config_service()
            content = {"deviceName": "Test Device", "mqttBroker": "mqtt.local"}

            config = service.create_config(valid_mac, content)

            assert config.device_name == "Test Device"

    def test_extracts_device_entity_id(self, app: Flask, session: Session, container: ServiceContainer, valid_mac: str):
        """Test deviceEntityId is extracted from content."""
        with app.app_context():
            service = container.config_service()
            content = {"deviceEntityId": "sensor.test", "mqttBroker": "mqtt.local"}

            config = service.create_config(valid_mac, content)

            assert config.device_entity_id == "sensor.test"

    def test_extracts_enable_ota(self, app: Flask, session: Session, container: ServiceContainer, valid_mac: str):
        """Test enableOTA is extracted from content."""
        with app.app_context():
            service = container.config_service()
            content = {"enableOTA": True, "mqttBroker": "mqtt.local"}

            config = service.create_config(valid_mac, content)

            assert config.enable_ota is True

    def test_missing_fields_are_none(self, app: Flask, session: Session, container: ServiceContainer, valid_mac: str):
        """Test missing optional fields are set to None."""
        with app.app_context():
            service = container.config_service()
            content = {"mqttBroker": "mqtt.local"}

            config = service.create_config(valid_mac, content)

            assert config.device_name is None
            assert config.device_entity_id is None
            assert config.enable_ota is None
