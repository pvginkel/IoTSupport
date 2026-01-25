"""Tests for NVS binary generator utility.

These tests verify the wrapper around the official Espressif
esp-idf-nvs-partition-gen library.
"""

import pytest

from app.exceptions import ValidationException
from app.utils.nvs_generator import (
    MIN_NVS_PARTITION_SIZE,
    NVS_MAX_KEY_LENGTH,
    NVS_PAGE_SIZE,
    PROVISIONING_NAMESPACE,
    generate_nvs_blob,
)

# Standard test partition size (12KB minimum)
TEST_PARTITION_SIZE = MIN_NVS_PARTITION_SIZE


class TestNvsGeneratorBasic:
    """Basic tests for NVS blob generation."""

    def _make_valid_data(self) -> dict[str, str | None]:
        """Create a valid provisioning data dict with all required fields."""
        return {
            "device_key": "abc12345",
            "client_id": "iotdevice-sensor-abc12345",
            "client_secret": "test-secret-value",
            "token_url": "https://auth.example.com/token",
            "base_url": "https://iot.example.com",
            "mqtt_url": "mqtt://mqtt.example.com:1883",
            "wifi_ssid": "TestNetwork",
            "wifi_password": "TestPassword123",
            "logging_url": "https://logs.example.com/ingest",
        }

    def test_generate_nvs_blob_returns_correct_size(self) -> None:
        """Test that generated blob matches the requested partition size."""
        data = self._make_valid_data()
        blob = generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert len(blob) == TEST_PARTITION_SIZE

    def test_generate_nvs_blob_larger_partition_size(self) -> None:
        """Test that larger partition sizes produce larger blobs."""
        data = self._make_valid_data()
        larger_size = TEST_PARTITION_SIZE + NVS_PAGE_SIZE  # 16KB

        blob = generate_nvs_blob(data, partition_size=larger_size)

        assert len(blob) == larger_size

    def test_generate_nvs_blob_contains_namespace(self) -> None:
        """Test that the blob contains the provisioning namespace."""
        data = self._make_valid_data()
        blob = generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        # The namespace name should appear in the blob
        assert PROVISIONING_NAMESPACE.encode() in blob

    def test_generate_nvs_blob_contains_values(self) -> None:
        """Test that string values are present in the blob."""
        data = self._make_valid_data()
        blob = generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        # All non-None values should appear in the blob
        for value in data.values():
            if value is not None:
                assert value.encode() in blob


class TestNvsGeneratorValidation:
    """Tests for input validation."""

    def _make_valid_data(self) -> dict[str, str | None]:
        """Create a valid provisioning data dict with all fields."""
        return {
            "device_key": "abc12345",
            "client_id": "iotdevice-sensor-abc12345",
            "client_secret": "test-secret-value",
            "token_url": "https://auth.example.com/token",
            "base_url": "https://iot.example.com",
            "mqtt_url": "mqtt://mqtt.example.com:1883",
            "wifi_ssid": "TestNetwork",
            "wifi_password": "TestPassword123",
            "logging_url": "https://logs.example.com/ingest",
        }

    def test_key_too_long_raises_validation_error(self) -> None:
        """Test that key longer than 15 characters raises ValidationException."""
        data = self._make_valid_data()
        long_key = "a" * 16  # 16 chars, exceeds limit
        data[long_key] = "value"

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert "exceeds maximum length" in str(exc_info.value)
        assert str(NVS_MAX_KEY_LENGTH) in str(exc_info.value)

    def test_required_field_none_raises_validation_error(self) -> None:
        """Test that required field with None value raises ValidationException."""
        data = {
            "device_key": "abc12345",
            "client_id": None,  # Required field is None
            "client_secret": "test-secret",
            "token_url": "https://auth.example.com/token",
            "base_url": "https://iot.example.com",
        }

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert "client_id" in str(exc_info.value)
        assert "missing" in str(exc_info.value)

    def test_required_field_empty_string_raises_validation_error(self) -> None:
        """Test that required field with empty string raises ValidationException."""
        data = {
            "device_key": "abc12345",
            "client_id": "iotdevice-test",
            "client_secret": "",  # Required field is empty
            "token_url": "https://auth.example.com/token",
            "base_url": "https://iot.example.com",
        }

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert "client_secret" in str(exc_info.value)
        assert "empty" in str(exc_info.value)

    def test_required_field_whitespace_only_raises_validation_error(self) -> None:
        """Test that required field with only whitespace raises ValidationException."""
        data = {
            "device_key": "   ",  # Whitespace only
            "client_id": "iotdevice-test",
            "client_secret": "secret",
            "token_url": "https://auth.example.com/token",
            "base_url": "https://iot.example.com",
        }

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert "device_key" in str(exc_info.value)
        assert "empty" in str(exc_info.value)

    def test_all_fields_are_mandatory(self) -> None:
        """Test that all provisioning fields are validated as mandatory."""
        # Any field with None value should raise
        for field in ["device_key", "client_id", "client_secret", "token_url",
                      "base_url", "mqtt_url", "wifi_ssid", "wifi_password", "logging_url"]:
            data = self._make_valid_data()
            data[field] = None

            with pytest.raises(ValidationException) as exc_info:
                generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

            assert field in str(exc_info.value)
            assert "missing" in str(exc_info.value)

    def test_mqtt_url_none_raises_validation_error(self) -> None:
        """Test that mqtt_url with None value raises ValidationException."""
        data = self._make_valid_data()
        data["mqtt_url"] = None

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert "mqtt_url" in str(exc_info.value)
        assert "missing" in str(exc_info.value)

    def test_wifi_ssid_none_raises_validation_error(self) -> None:
        """Test that wifi_ssid with None value raises ValidationException."""
        data = self._make_valid_data()
        data["wifi_ssid"] = None

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert "wifi_ssid" in str(exc_info.value)
        assert "missing" in str(exc_info.value)

    def test_wifi_password_none_raises_validation_error(self) -> None:
        """Test that wifi_password with None value raises ValidationException."""
        data = self._make_valid_data()
        data["wifi_password"] = None

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert "wifi_password" in str(exc_info.value)
        assert "missing" in str(exc_info.value)

    def test_logging_url_none_raises_validation_error(self) -> None:
        """Test that logging_url with None value raises ValidationException."""
        data = self._make_valid_data()
        data["logging_url"] = None

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert "logging_url" in str(exc_info.value)
        assert "missing" in str(exc_info.value)

    def test_partition_size_too_small_raises_validation_error(self) -> None:
        """Test that partition size below 12KB raises ValidationException."""
        data = self._make_valid_data()

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=0x2000)  # 8KB, too small

        assert "at least" in str(exc_info.value)
        assert "12KB" in str(exc_info.value)

    def test_partition_size_not_multiple_of_4kb_raises_validation_error(self) -> None:
        """Test that partition size not a multiple of 4KB raises ValidationException."""
        data = self._make_valid_data()

        with pytest.raises(ValidationException) as exc_info:
            generate_nvs_blob(data, partition_size=0x3500)  # Not a multiple of 4KB

        assert "multiple" in str(exc_info.value)
        assert "4KB" in str(exc_info.value)


class TestNvsGeneratorIntegration:
    """Integration tests for complete blob generation."""

    def test_all_provisioning_fields(self) -> None:
        """Test generating blob with all standard provisioning fields."""
        data = {
            "device_key": "abcd1234",
            "client_id": "iotdevice-tempsensor-abcd1234",
            "client_secret": "very-secret-client-credential",
            "token_url": "https://keycloak.example.com/realms/iot/protocol/openid-connect/token",
            "base_url": "https://iot-api.example.com",
            "mqtt_url": "mqtts://mqtt.example.com:8883",
            "wifi_ssid": "HomeNetwork",
            "wifi_password": "SuperSecretPassword123!",
            "logging_url": "https://logs.example.com/ingest",
        }

        blob = generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        # Basic sanity checks
        assert len(blob) == TEST_PARTITION_SIZE

        # All values should be present in the blob
        for value in data.values():
            if value:
                assert value.encode() in blob

    def test_all_fields_required(self) -> None:
        """Test that all fields must be present - no optional fields exist."""
        data = {
            "device_key": "xyz98765",
            "client_id": "iotdevice-relay-xyz98765",
            "client_secret": "minimal-secret",
            "token_url": "https://auth.local/token",
            "base_url": "https://api.local",
            "mqtt_url": "mqtt://mqtt.local:1883",
            "wifi_ssid": "LocalNetwork",
            "wifi_password": "LocalPassword",
            "logging_url": "https://logs.local/ingest",
        }

        blob = generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert len(blob) == TEST_PARTITION_SIZE

        # All values should be present
        assert b"xyz98765" in blob
        assert b"minimal-secret" in blob
        assert b"mqtt://mqtt.local:1883" in blob
        assert b"LocalNetwork" in blob

    def test_blob_deterministic(self) -> None:
        """Test that blob generation is deterministic for same input."""
        data = {
            "device_key": "test1234",
            "client_id": "iotdevice-test-test1234",
            "client_secret": "secret",
            "token_url": "https://auth.example.com/token",
            "base_url": "https://api.example.com",
            "mqtt_url": "mqtt://mqtt.example.com:1883",
            "wifi_ssid": "TestNetwork",
            "wifi_password": "TestPassword",
            "logging_url": "https://logs.example.com/ingest",
        }

        blob1 = generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)
        blob2 = generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        assert blob1 == blob2, "Same input should produce identical output"

    def test_utf8_string_encoding(self) -> None:
        """Test that non-ASCII UTF-8 strings are correctly encoded."""
        data = {
            "device_key": "abc12345",
            "client_id": "iotdevice-test",
            "client_secret": "secret",
            "token_url": "https://auth.example.com",
            "base_url": "https://api.example.com",
            "mqtt_url": "mqtt://mqtt.example.com:1883",
            "wifi_ssid": "Café",  # UTF-8 with accented character
            "wifi_password": "TestPassword",
            "logging_url": "https://logs.example.com/ingest",
        }

        blob = generate_nvs_blob(data, partition_size=TEST_PARTITION_SIZE)

        # The UTF-8 encoding of "Café" should be in the blob
        assert "Café".encode("utf-8") in blob

    def test_various_partition_sizes(self) -> None:
        """Test that different valid partition sizes work correctly."""
        data = {
            "device_key": "test1234",
            "client_id": "iotdevice-test",
            "client_secret": "secret",
            "token_url": "https://auth.example.com",
            "base_url": "https://api.example.com",
            "mqtt_url": "mqtt://mqtt.example.com:1883",
            "wifi_ssid": "TestNetwork",
            "wifi_password": "TestPassword",
            "logging_url": "https://logs.example.com/ingest",
        }

        # Test various valid sizes
        for size in [0x3000, 0x4000, 0x5000, 0x6000, 0x8000]:
            blob = generate_nvs_blob(data, partition_size=size)
            assert len(blob) == size
