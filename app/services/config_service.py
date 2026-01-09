"""Configuration service for managing ESP32 device config files."""

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.exceptions import InvalidOperationException, RecordNotFoundException

logger = logging.getLogger(__name__)

# MAC address pattern: lowercase, hyphen-separated (xx-xx-xx-xx-xx-xx)
MAC_ADDRESS_PATTERN = re.compile(r"^[0-9a-f]{2}(-[0-9a-f]{2}){5}$")


@dataclass
class ConfigSummary:
    """Summary of a configuration file for list endpoint."""

    mac_address: str
    device_name: str | None
    device_entity_id: str | None
    enable_ota: bool | None


@dataclass
class ConfigDetail:
    """Full configuration detail."""

    mac_address: str
    device_name: str | None
    device_entity_id: str | None
    enable_ota: bool | None
    content: dict[str, Any]


class ConfigService:
    """Service for managing ESP32 device configuration files."""

    def __init__(self, config_dir: Path) -> None:
        """Initialize service with configuration directory.

        Args:
            config_dir: Path to the configuration files directory
        """
        self.config_dir = config_dir

    def list_configs(self) -> list[ConfigSummary]:
        """List all config files with summary data.

        Returns:
            List of ConfigSummary objects sorted by MAC address

        Note:
            Invalid JSON files are skipped with a warning logged.
        """
        configs: list[ConfigSummary] = []

        if not self.config_dir.exists():
            return configs

        for file_path in sorted(self.config_dir.glob("*.json")):
            mac_address = file_path.stem

            # Validate MAC address format
            if not self.validate_mac_address(mac_address):
                logger.warning(
                    "Skipping file with invalid MAC address format: %s", file_path.name
                )
                continue

            try:
                with open(file_path, encoding="utf-8") as f:
                    content = json.load(f)

                # Extract summary fields, defaulting to None if missing
                summary = ConfigSummary(
                    mac_address=mac_address,
                    device_name=content.get("deviceName"),
                    device_entity_id=content.get("deviceEntityId"),
                    enable_ota=content.get("enableOTA"),
                )
                configs.append(summary)

            except json.JSONDecodeError as e:
                logger.warning(
                    "Skipping invalid JSON file %s: %s", file_path.name, str(e)
                )
                continue
            except OSError as e:
                logger.warning("Error reading file %s: %s", file_path.name, str(e))
                continue

        return configs

    def get_config(self, mac_address: str) -> ConfigDetail:
        """Get full config content by MAC address.

        Args:
            mac_address: Device MAC address

        Returns:
            ConfigDetail with full content

        Raises:
            InvalidOperationException: If MAC address format is invalid
            RecordNotFoundException: If config file does not exist
        """
        if not self.validate_mac_address(mac_address):
            raise InvalidOperationException(
                "get config", f"MAC address '{mac_address}' has invalid format"
            )

        file_path = self.config_dir / f"{mac_address}.json"

        if not file_path.exists():
            raise RecordNotFoundException("Config", mac_address)

        try:
            with open(file_path, encoding="utf-8") as f:
                content = json.load(f)
        except json.JSONDecodeError as e:
            raise InvalidOperationException(
                "get config", f"config file contains invalid JSON: {e}"
            ) from e

        return ConfigDetail(
            mac_address=mac_address,
            device_name=content.get("deviceName"),
            device_entity_id=content.get("deviceEntityId"),
            enable_ota=content.get("enableOTA"),
            content=content,
        )

    def save_config(self, mac_address: str, content: dict[str, Any]) -> ConfigDetail:
        """Create or update config (upsert).

        Args:
            mac_address: Device MAC address
            content: Configuration content as a dictionary

        Returns:
            ConfigDetail with saved content

        Raises:
            InvalidOperationException: If MAC address format is invalid
        """
        if not self.validate_mac_address(mac_address):
            raise InvalidOperationException(
                "save config", f"MAC address '{mac_address}' has invalid format"
            )

        file_path = self.config_dir / f"{mac_address}.json"

        # Write atomically using temp file + rename
        self._write_atomic(file_path, content)

        return ConfigDetail(
            mac_address=mac_address,
            device_name=content.get("deviceName"),
            device_entity_id=content.get("deviceEntityId"),
            enable_ota=content.get("enableOTA"),
            content=content,
        )

    def delete_config(self, mac_address: str) -> None:
        """Delete config by MAC address.

        Args:
            mac_address: Device MAC address

        Raises:
            InvalidOperationException: If MAC address format is invalid
            RecordNotFoundException: If config file does not exist
        """
        if not self.validate_mac_address(mac_address):
            raise InvalidOperationException(
                "delete config", f"MAC address '{mac_address}' has invalid format"
            )

        file_path = self.config_dir / f"{mac_address}.json"

        if not file_path.exists():
            raise RecordNotFoundException("Config", mac_address)

        file_path.unlink()

    def _write_atomic(self, file_path: Path, content: dict[str, Any]) -> None:
        """Write file atomically using temp file + rename.

        Args:
            file_path: Target file path
            content: Content to write as JSON
        """
        # Create temp file in SAME directory (required for atomic rename on same filesystem)
        temp_path = file_path.with_suffix(".tmp")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=2)

            # os.replace() is atomic on POSIX and overwrites existing files
            os.replace(temp_path, file_path)

        finally:
            # Clean up temp file if rename failed
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def validate_mac_address(mac: str) -> bool:
        """Validate MAC is lowercase, hyphen-separated format.

        Args:
            mac: MAC address string to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(MAC_ADDRESS_PATTERN.match(mac))

    def is_config_dir_accessible(self) -> tuple[bool, str | None]:
        """Check if the config directory is accessible.

        Returns:
            Tuple of (is_accessible, error_reason)
        """
        if not self.config_dir.exists():
            return False, f"Directory does not exist: {self.config_dir}"

        if not self.config_dir.is_dir():
            return False, f"Path is not a directory: {self.config_dir}"

        # Try to list directory to verify read access
        try:
            list(self.config_dir.iterdir())
        except PermissionError:
            return False, f"Permission denied: {self.config_dir}"
        except OSError as e:
            return False, f"Cannot access directory: {e}"

        return True, None
