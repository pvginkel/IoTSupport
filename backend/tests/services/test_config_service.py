"""Tests for ConfigService with database backend."""

import json
from typing import Any

import pytest

from app.exceptions import (
    InvalidOperationException,
    RecordExistsException,
    RecordNotFoundException,
)
from app.services.config_service import ConfigService


class TestConfigServiceList:
    """Tests for ConfigService.list_configs()."""

    def test_list_configs_empty(self, config_service: ConfigService):
        """Test listing configs when database is empty."""
        configs = config_service.list_configs()
        assert configs == []

    def test_list_configs_with_data(self, config_service: ConfigService, sample_config: str):
        """Test listing configs returns all configs sorted by MAC."""
        # Create two configs in non-alphabetical order
        config_service.create_config("bb:bb:bb:bb:bb:bb", sample_config)
        config_service.create_config("aa:aa:aa:aa:aa:aa", sample_config)

        configs = config_service.list_configs()

        assert len(configs) == 2
        # Should be sorted by MAC address
        assert configs[0].mac_address == "aa:aa:aa:aa:aa:aa"
        assert configs[1].mac_address == "bb:bb:bb:bb:bb:bb"


class TestConfigServiceGetById:
    """Tests for ConfigService.get_config_by_id()."""

    def test_get_config_by_id_success(
        self,
        config_service: ConfigService,
        sample_config: str,
        sample_config_dict: dict[str, Any],
        valid_mac: str,
    ):
        """Test getting config by ID returns correct config."""
        created = config_service.create_config(valid_mac, sample_config)

        config = config_service.get_config_by_id(created.id)

        assert config.id == created.id
        assert config.mac_address == valid_mac
        assert config.device_name == sample_config_dict["deviceName"]

    def test_get_config_by_id_not_found(self, config_service: ConfigService):
        """Test getting non-existent config raises RecordNotFoundException."""
        with pytest.raises(RecordNotFoundException) as exc_info:
            config_service.get_config_by_id(99999)

        assert "Config" in str(exc_info.value.message)
        assert "99999" in str(exc_info.value.message)


class TestConfigServiceGetByMac:
    """Tests for ConfigService.get_config_by_mac()."""

    def test_get_config_by_mac_success(
        self,
        config_service: ConfigService,
        sample_config: str,
        sample_config_dict: dict[str, Any],
        valid_mac: str,
    ):
        """Test getting config by MAC address."""
        config_service.create_config(valid_mac, sample_config)

        config = config_service.get_config_by_mac(valid_mac)

        assert config.mac_address == valid_mac
        assert config.device_name == sample_config_dict["deviceName"]

    def test_get_config_by_mac_uppercase_normalization(
        self, config_service: ConfigService, sample_config: str
    ):
        """Test MAC address is normalized to lowercase."""
        config_service.create_config("aa:bb:cc:dd:ee:ff", sample_config)

        # Request with uppercase should work
        config = config_service.get_config_by_mac("AA:BB:CC:DD:EE:FF")

        assert config.mac_address == "aa:bb:cc:dd:ee:ff"

    def test_get_config_by_mac_dash_separator_normalization(
        self, config_service: ConfigService, sample_config: str
    ):
        """Test dash-separated MAC is normalized to colon-separated."""
        config_service.create_config("aa:bb:cc:dd:ee:ff", sample_config)

        # Request with dashes should work (backward compatibility)
        config = config_service.get_config_by_mac("aa-bb-cc-dd-ee-ff")

        assert config.mac_address == "aa:bb:cc:dd:ee:ff"

    def test_get_config_by_mac_not_found(self, config_service: ConfigService, valid_mac: str):
        """Test getting non-existent MAC raises RecordNotFoundException."""
        with pytest.raises(RecordNotFoundException) as exc_info:
            config_service.get_config_by_mac(valid_mac)

        assert "Config" in str(exc_info.value.message)

    def test_get_config_by_mac_invalid_format(self, config_service: ConfigService):
        """Test invalid MAC format raises InvalidOperationException."""
        with pytest.raises(InvalidOperationException) as exc_info:
            config_service.get_config_by_mac("invalid-mac")

        assert "invalid format" in str(exc_info.value.message)


class TestConfigServiceGetRaw:
    """Tests for ConfigService.get_raw_config()."""

    def test_get_raw_config_success(
        self,
        config_service: ConfigService,
        sample_config: str,
        sample_config_dict: dict[str, Any],
        valid_mac: str,
    ):
        """Test getting raw config content."""
        config_service.create_config(valid_mac, sample_config)

        content = config_service.get_raw_config(valid_mac)

        assert content == sample_config_dict

    def test_get_raw_config_with_dash_separator(
        self,
        config_service: ConfigService,
        sample_config: str,
        sample_config_dict: dict[str, Any],
    ):
        """Test raw config works with dash-separated MAC for backward compatibility."""
        config_service.create_config("aa:bb:cc:dd:ee:ff", sample_config)

        content = config_service.get_raw_config("aa-bb-cc-dd-ee-ff")

        assert content == sample_config_dict


class TestConfigServiceCreate:
    """Tests for ConfigService.create_config()."""

    def test_create_config_full_data(
        self,
        config_service: ConfigService,
        sample_config: str,
        sample_config_dict: dict[str, Any],
        valid_mac: str,
    ):
        """Test creating config with all fields."""
        config = config_service.create_config(valid_mac, sample_config)

        assert config.id is not None
        assert config.mac_address == valid_mac
        assert config.device_name == sample_config_dict["deviceName"]
        assert config.device_entity_id == sample_config_dict["deviceEntityId"]
        assert config.enable_ota == sample_config_dict["enableOTA"]
        assert config.content == sample_config  # Stored verbatim
        assert config.created_at is not None
        assert config.updated_at is not None

    def test_create_config_minimal(
        self, config_service: ConfigService, sample_config_minimal: str, valid_mac: str
    ):
        """Test creating config with minimal fields."""
        config = config_service.create_config(valid_mac, sample_config_minimal)

        assert config.id is not None
        assert config.mac_address == valid_mac
        assert config.device_name is None
        assert config.device_entity_id is None
        assert config.enable_ota is None

    def test_create_config_normalizes_mac(
        self, config_service: ConfigService, sample_config: str
    ):
        """Test MAC address is normalized to lowercase colon-separated."""
        config = config_service.create_config("AA:BB:CC:DD:EE:FF", sample_config)

        assert config.mac_address == "aa:bb:cc:dd:ee:ff"

    def test_create_config_duplicate_mac_raises(
        self, config_service: ConfigService, sample_config: str, valid_mac: str
    ):
        """Test creating config with duplicate MAC raises RecordExistsException."""
        config_service.create_config(valid_mac, sample_config)

        with pytest.raises(RecordExistsException) as exc_info:
            config_service.create_config(valid_mac, sample_config)

        assert "Config" in str(exc_info.value.message)
        assert valid_mac in str(exc_info.value.message)

    def test_create_config_invalid_mac_format(
        self, config_service: ConfigService, sample_config: str
    ):
        """Test creating config with invalid MAC raises InvalidOperationException."""
        with pytest.raises(InvalidOperationException) as exc_info:
            config_service.create_config("invalid", sample_config)

        assert "invalid format" in str(exc_info.value.message)

    def test_create_config_short_mac(self, config_service: ConfigService, sample_config: str):
        """Test creating config with short MAC raises error."""
        with pytest.raises(InvalidOperationException):
            config_service.create_config("aa:bb:cc", sample_config)


class TestConfigServiceUpdate:
    """Tests for ConfigService.update_config()."""

    def test_update_config_success(
        self, config_service: ConfigService, sample_config: str, valid_mac: str
    ):
        """Test updating config content."""
        created = config_service.create_config(valid_mac, sample_config)

        new_content = json.dumps({
            "deviceName": "Updated Name",
            "deviceEntityId": "sensor.updated",
            "enableOTA": False,
            "mqttBroker": "mqtt.new",
        })

        updated = config_service.update_config(created.id, new_content)

        assert updated.device_name == "Updated Name"
        assert updated.device_entity_id == "sensor.updated"
        assert updated.enable_ota is False
        assert updated.content == new_content  # Stored verbatim

    def test_update_config_removes_optional_fields(
        self, config_service: ConfigService, sample_config: str, valid_mac: str
    ):
        """Test updating config with content lacking optional fields sets them to None."""
        created = config_service.create_config(valid_mac, sample_config)

        # Update with content lacking deviceName, deviceEntityId, enableOTA
        minimal_content = json.dumps({"mqttBroker": "mqtt.local"})

        updated = config_service.update_config(created.id, minimal_content)

        assert updated.device_name is None
        assert updated.device_entity_id is None
        assert updated.enable_ota is None

    def test_update_config_not_found(self, config_service: ConfigService, sample_config: str):
        """Test updating non-existent config raises RecordNotFoundException."""
        with pytest.raises(RecordNotFoundException) as exc_info:
            config_service.update_config(99999, sample_config)

        assert "Config" in str(exc_info.value.message)


class TestConfigServiceDelete:
    """Tests for ConfigService.delete_config()."""

    def test_delete_config_success(
        self, config_service: ConfigService, sample_config: str, valid_mac: str
    ):
        """Test deleting config removes it from database."""
        created = config_service.create_config(valid_mac, sample_config)

        mac_address = config_service.delete_config(created.id)

        assert mac_address == valid_mac

        with pytest.raises(RecordNotFoundException):
            config_service.get_config_by_id(created.id)

    def test_delete_config_not_found(self, config_service: ConfigService):
        """Test deleting non-existent config raises RecordNotFoundException."""
        with pytest.raises(RecordNotFoundException) as exc_info:
            config_service.delete_config(99999)

        assert "Config" in str(exc_info.value.message)


class TestConfigServiceCount:
    """Tests for ConfigService.count_configs()."""

    def test_count_configs_empty(self, config_service: ConfigService):
        """Test counting configs when empty."""
        count = config_service.count_configs()
        assert count == 0

    def test_count_configs_with_data(self, config_service: ConfigService, sample_config: str):
        """Test counting configs with data."""
        config_service.create_config("aa:aa:aa:aa:aa:aa", sample_config)
        config_service.create_config("bb:bb:bb:bb:bb:bb", sample_config)

        count = config_service.count_configs()
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

    def test_extracts_device_name(self, config_service: ConfigService, valid_mac: str):
        """Test deviceName is extracted from content."""
        content = json.dumps({"deviceName": "Test Device", "mqttBroker": "mqtt.local"})

        config = config_service.create_config(valid_mac, content)

        assert config.device_name == "Test Device"

    def test_extracts_device_entity_id(self, config_service: ConfigService, valid_mac: str):
        """Test deviceEntityId is extracted from content."""
        content = json.dumps({"deviceEntityId": "sensor.test", "mqttBroker": "mqtt.local"})

        config = config_service.create_config(valid_mac, content)

        assert config.device_entity_id == "sensor.test"

    def test_extracts_enable_ota(self, config_service: ConfigService, valid_mac: str):
        """Test enableOTA is extracted from content."""
        content = json.dumps({"enableOTA": True, "mqttBroker": "mqtt.local"})

        config = config_service.create_config(valid_mac, content)

        assert config.enable_ota is True

    def test_missing_fields_are_none(self, config_service: ConfigService, valid_mac: str):
        """Test missing optional fields are set to None."""
        content = json.dumps({"mqttBroker": "mqtt.local"})

        config = config_service.create_config(valid_mac, content)

        assert config.device_name is None
        assert config.device_entity_id is None
        assert config.enable_ota is None

    def test_content_stored_verbatim(self, config_service: ConfigService, valid_mac: str):
        """Test content is stored exactly as provided."""
        # Use a specific format with specific whitespace
        content = '{"deviceName":"Test","extra":  123}'

        config = config_service.create_config(valid_mac, content)

        # Content should be stored verbatim
        assert config.content == content
