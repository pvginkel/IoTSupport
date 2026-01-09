"""Tests for ConfigService."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.exceptions import InvalidOperationException, RecordNotFoundException
from app.services.config_service import ConfigService


class TestConfigServiceListConfigs:
    """Tests for list_configs method."""

    def test_list_configs_empty(self, config_dir: Path):
        """Empty directory returns empty list."""
        service = ConfigService(config_dir)
        result = service.list_configs()
        assert result == []

    def test_list_configs_multiple(
        self, config_dir: Path, make_config_file: Any, sample_config: dict[str, Any]
    ):
        """Multiple config files are returned."""
        make_config_file("aa-bb-cc-dd-ee-ff", sample_config)
        make_config_file("11-22-33-44-55-66", sample_config)

        service = ConfigService(config_dir)
        result = service.list_configs()

        assert len(result) == 2
        # Should be sorted by MAC address
        assert result[0].mac_address == "11-22-33-44-55-66"
        assert result[1].mac_address == "aa-bb-cc-dd-ee-ff"

    def test_list_configs_extracts_fields(
        self, config_dir: Path, make_config_file: Any, sample_config: dict[str, Any]
    ):
        """Summary fields are correctly extracted from config content."""
        make_config_file("aa-bb-cc-dd-ee-ff", sample_config)

        service = ConfigService(config_dir)
        result = service.list_configs()

        assert len(result) == 1
        assert result[0].mac_address == "aa-bb-cc-dd-ee-ff"
        assert result[0].device_name == "Living Room Sensor"
        assert result[0].device_entity_id == "sensor.living_room"
        assert result[0].enable_ota is True

    def test_list_configs_handles_missing_fields(
        self, config_dir: Path, make_config_file: Any, sample_config_minimal: dict[str, Any]
    ):
        """Missing optional fields return None."""
        make_config_file("aa-bb-cc-dd-ee-ff", sample_config_minimal)

        service = ConfigService(config_dir)
        result = service.list_configs()

        assert len(result) == 1
        assert result[0].device_name is None
        assert result[0].device_entity_id is None
        assert result[0].enable_ota is None

    def test_list_configs_skips_invalid_json(
        self, config_dir: Path, make_config_file: Any, sample_config: dict[str, Any]
    ):
        """Invalid JSON files are skipped, not causing failure."""
        make_config_file("aa-bb-cc-dd-ee-ff", sample_config)

        # Create invalid JSON file
        invalid_file = config_dir / "11-22-33-44-55-66.json"
        invalid_file.write_text("not valid json {{{")

        service = ConfigService(config_dir)
        result = service.list_configs()

        # Only the valid config should be returned
        assert len(result) == 1
        assert result[0].mac_address == "aa-bb-cc-dd-ee-ff"

    def test_list_configs_skips_invalid_mac_filenames(
        self, config_dir: Path, sample_config: dict[str, Any]
    ):
        """Files with invalid MAC address names are skipped."""
        # Valid MAC file
        valid_file = config_dir / "aa-bb-cc-dd-ee-ff.json"
        with open(valid_file, "w") as f:
            json.dump(sample_config, f)

        # Invalid MAC file (uppercase)
        invalid_file = config_dir / "AA-BB-CC-DD-EE-FF.json"
        with open(invalid_file, "w") as f:
            json.dump(sample_config, f)

        service = ConfigService(config_dir)
        result = service.list_configs()

        assert len(result) == 1
        assert result[0].mac_address == "aa-bb-cc-dd-ee-ff"


class TestConfigServiceGetConfig:
    """Tests for get_config method."""

    def test_get_config_success(
        self, config_dir: Path, make_config_file: Any, sample_config: dict[str, Any], valid_mac: str
    ):
        """Retrieve existing config returns full content."""
        make_config_file(valid_mac, sample_config)

        service = ConfigService(config_dir)
        result = service.get_config(valid_mac)

        assert result.mac_address == valid_mac
        assert result.device_name == "Living Room Sensor"
        assert result.device_entity_id == "sensor.living_room"
        assert result.enable_ota is True
        assert result.content == sample_config

    def test_get_config_not_found(self, config_dir: Path, valid_mac: str):
        """Non-existent config raises RecordNotFoundException."""
        service = ConfigService(config_dir)

        with pytest.raises(RecordNotFoundException) as exc_info:
            service.get_config(valid_mac)

        assert valid_mac in str(exc_info.value)

    def test_get_config_invalid_mac(self, config_dir: Path):
        """Invalid MAC format raises InvalidOperationException."""
        service = ConfigService(config_dir)

        with pytest.raises(InvalidOperationException) as exc_info:
            service.get_config("invalid-mac")

        assert "invalid format" in str(exc_info.value).lower()


class TestConfigServiceSaveConfig:
    """Tests for save_config method."""

    def test_save_config_create(
        self, config_dir: Path, sample_config: dict[str, Any], valid_mac: str
    ):
        """Create new config file."""
        service = ConfigService(config_dir)
        result = service.save_config(valid_mac, sample_config)

        assert result.mac_address == valid_mac
        assert result.content == sample_config

        # Verify file was created
        file_path = config_dir / f"{valid_mac}.json"
        assert file_path.exists()

        with open(file_path) as f:
            saved_content = json.load(f)
        assert saved_content == sample_config

    def test_save_config_update(
        self, config_dir: Path, make_config_file: Any, sample_config: dict[str, Any], valid_mac: str
    ):
        """Update existing config file."""
        make_config_file(valid_mac, sample_config)

        service = ConfigService(config_dir)

        updated_config = {**sample_config, "deviceName": "Updated Name"}
        result = service.save_config(valid_mac, updated_config)

        assert result.device_name == "Updated Name"

        # Verify file was updated
        file_path = config_dir / f"{valid_mac}.json"
        with open(file_path) as f:
            saved_content = json.load(f)
        assert saved_content["deviceName"] == "Updated Name"

    def test_save_config_invalid_mac(self, config_dir: Path, sample_config: dict[str, Any]):
        """Invalid MAC format raises InvalidOperationException."""
        service = ConfigService(config_dir)

        with pytest.raises(InvalidOperationException) as exc_info:
            service.save_config("INVALID", sample_config)

        assert "invalid format" in str(exc_info.value).lower()

    def test_save_config_atomic_write(
        self, config_dir: Path, sample_config: dict[str, Any], valid_mac: str
    ):
        """Temp file is cleaned up after successful write."""
        service = ConfigService(config_dir)
        service.save_config(valid_mac, sample_config)

        # Ensure no .tmp files remain
        tmp_files = list(config_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestConfigServiceDeleteConfig:
    """Tests for delete_config method."""

    def test_delete_config_success(
        self, config_dir: Path, make_config_file: Any, sample_config: dict[str, Any], valid_mac: str
    ):
        """Delete existing config file."""
        make_config_file(valid_mac, sample_config)
        file_path = config_dir / f"{valid_mac}.json"
        assert file_path.exists()

        service = ConfigService(config_dir)
        service.delete_config(valid_mac)

        assert not file_path.exists()

    def test_delete_config_not_found(self, config_dir: Path, valid_mac: str):
        """Delete non-existent config raises RecordNotFoundException."""
        service = ConfigService(config_dir)

        with pytest.raises(RecordNotFoundException) as exc_info:
            service.delete_config(valid_mac)

        assert valid_mac in str(exc_info.value)

    def test_delete_config_invalid_mac(self, config_dir: Path):
        """Invalid MAC format raises InvalidOperationException."""
        service = ConfigService(config_dir)

        with pytest.raises(InvalidOperationException) as exc_info:
            service.delete_config("bad-mac")

        assert "invalid format" in str(exc_info.value).lower()


class TestValidateMacAddress:
    """Tests for validate_mac_address static method."""

    @pytest.mark.parametrize(
        "mac",
        [
            "aa-bb-cc-dd-ee-ff",
            "00-00-00-00-00-00",
            "12-34-56-78-9a-bc",
            "ff-ff-ff-ff-ff-ff",
        ],
    )
    def test_validate_mac_address_valid(self, mac: str):
        """Valid MAC addresses are accepted."""
        assert ConfigService.validate_mac_address(mac) is True

    @pytest.mark.parametrize(
        "mac",
        [
            "AA-BB-CC-DD-EE-FF",  # Uppercase
            "aa:bb:cc:dd:ee:ff",  # Colon separator
            "aabbccddeeff",  # No separator
            "aa-bb-cc-dd-ee",  # Too short
            "aa-bb-cc-dd-ee-ff-00",  # Too long
            "gg-bb-cc-dd-ee-ff",  # Invalid hex
            "aa-bb-cc-dd-ee-f",  # Incomplete octet
            "",  # Empty
            "invalid",  # Random string
        ],
    )
    def test_validate_mac_address_invalid(self, mac: str):
        """Invalid MAC addresses are rejected."""
        assert ConfigService.validate_mac_address(mac) is False


class TestConfigDirAccessible:
    """Tests for is_config_dir_accessible method."""

    def test_config_dir_accessible(self, config_dir: Path):
        """Accessible directory returns True."""
        service = ConfigService(config_dir)
        is_accessible, error = service.is_config_dir_accessible()

        assert is_accessible is True
        assert error is None

    def test_config_dir_not_exists(self, tmp_path: Path):
        """Non-existent directory returns False with reason."""
        non_existent = tmp_path / "does_not_exist"
        service = ConfigService(non_existent)
        is_accessible, error = service.is_config_dir_accessible()

        assert is_accessible is False
        assert "does not exist" in error.lower()

    def test_config_dir_is_file(self, tmp_path: Path):
        """Path that is a file returns False with reason."""
        file_path = tmp_path / "not_a_dir"
        file_path.touch()

        service = ConfigService(file_path)
        is_accessible, error = service.is_config_dir_accessible()

        assert is_accessible is False
        assert "not a directory" in error.lower()
