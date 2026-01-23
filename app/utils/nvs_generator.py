"""NVS (Non-Volatile Storage) binary generator for ESP32 provisioning.

This module wraps the official Espressif esp-idf-nvs-partition-gen library
to generate NVS binary blobs for direct flashing to ESP32 devices.

The generated blobs are compatible with ESP-IDF's NVS library and can be
read using nvs_get_str() and similar functions on the device.
"""

from io import BytesIO

from esp_idf_nvs_partition_gen.nvs_partition_gen import (
    Page,
    nvs_close,
    nvs_open,
    write_entry,
)

from app.exceptions import ValidationException

# NVS page size (ESP-IDF constraint: partitions must be multiples of 4KB)
NVS_PAGE_SIZE = 0x1000

# Minimum NVS partition size (12KB - ESP-IDF requires at least 3 pages)
MIN_NVS_PARTITION_SIZE = 0x3000

# Provisioning namespace
PROVISIONING_NAMESPACE = "prov"

# Key length limit (ESP-IDF constraint)
NVS_MAX_KEY_LENGTH = 15


def _validate_key(key: str) -> None:
    """Validate NVS key name.

    Args:
        key: Key name to validate

    Raises:
        ValidationException: If key is invalid
    """
    if not key:
        raise ValidationException("NVS key name cannot be empty")
    if len(key) > NVS_MAX_KEY_LENGTH:
        raise ValidationException(
            f"NVS key '{key}' exceeds maximum length of {NVS_MAX_KEY_LENGTH} characters"
        )


def _validate_all_fields(data: dict[str, str | None]) -> None:
    """Validate that all provisioning fields are present and non-empty.

    All keys in the NVS data are mandatory - a device cannot function
    without any of them.

    Args:
        data: Dictionary of key-value pairs

    Raises:
        ValidationException: If any fields are None or empty
    """
    for key, value in data.items():
        if value is None:
            raise ValidationException(
                f"Provisioning field '{key}' is missing"
            )
        if isinstance(value, str) and not value.strip():
            raise ValidationException(
                f"Provisioning field '{key}' cannot be empty"
            )


def generate_nvs_blob(data: dict[str, str | None], partition_size: int) -> bytes:
    """Generate an NVS binary blob from key-value pairs.

    Uses the official Espressif esp-idf-nvs-partition-gen library to create
    a valid NVS partition containing the provided string data in the 'prov'
    namespace.

    All fields in the data dictionary are mandatory - a device cannot
    function without any of them.

    Args:
        data: Dictionary mapping NVS key names to string values.
              All keys must have non-None, non-empty values.
        partition_size: NVS partition size in bytes. Must match the partition
                        table on the device. Must be at least 12KB (0x3000) and
                        a multiple of 4KB (0x1000).

    Returns:
        NVS partition binary of the specified size

    Raises:
        ValidationException: If any field is None, empty, violates constraints,
                             or partition_size is invalid
    """
    # Validate partition size
    if partition_size < MIN_NVS_PARTITION_SIZE:
        raise ValidationException(
            f"NVS partition size must be at least {MIN_NVS_PARTITION_SIZE} bytes (12KB)"
        )
    if partition_size % NVS_PAGE_SIZE != 0:
        raise ValidationException(
            f"NVS partition size must be a multiple of {NVS_PAGE_SIZE} bytes (4KB)"
        )

    # Validate all fields are present and non-empty
    _validate_all_fields(data)

    # Filter out None values (optional fields) and validate keys
    filtered_data = {}
    for key, value in data.items():
        if value is not None:
            _validate_key(key)
            if not isinstance(value, str):
                raise ValidationException(
                    f"NVS value for key '{key}' must be a string, got {type(value).__name__}"
                )
            filtered_data[key] = value

    # Create a BytesIO buffer to capture the binary output
    buffer = BytesIO()

    # Create NVS instance with specified partition size, version 2 (multipage blob support)
    nvs = nvs_open(buffer, partition_size, Page.VERSION2, read_only=True)

    # Write namespace entry
    write_entry(nvs, PROVISIONING_NAMESPACE, "namespace", "", "")

    # Write all string entries
    for key, value in filtered_data.items():
        write_entry(nvs, key, "data", "string", value)

    # Close NVS and flush to buffer
    nvs_close(nvs)

    # Get the data written by the library
    result = buffer.getvalue()

    # Pad to the requested partition size with 0xFF bytes (unwritten flash value)
    # The library may not output the full partition size
    if len(result) < partition_size:
        result = result + (b"\xff" * (partition_size - len(result)))

    return result
