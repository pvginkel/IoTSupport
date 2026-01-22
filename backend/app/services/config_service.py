"""Configuration service for managing ESP32 device configurations in database."""

import json
import logging
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.exceptions import (
    InvalidOperationException,
    RecordExistsException,
    RecordNotFoundException,
)
from app.models.config import Config

logger = logging.getLogger(__name__)

# MAC address pattern: lowercase, colon-separated (aa:bb:cc:dd:ee:ff)
MAC_ADDRESS_PATTERN = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


class ConfigService:
    """Service for managing ESP32 device configurations in database."""

    def __init__(self, db: Session):
        """Initialize service with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def list_configs(self) -> list[Config]:
        """List all configs from database.

        Returns:
            List of Config model instances sorted by MAC address
        """
        stmt = select(Config).order_by(Config.mac_address)
        return list(self.db.scalars(stmt).all())

    def get_config_by_id(self, config_id: int) -> Config:
        """Get config by surrogate ID.

        Args:
            config_id: Config surrogate ID

        Returns:
            Config model instance

        Raises:
            RecordNotFoundException: If config with ID does not exist
        """
        stmt = select(Config).where(Config.id == config_id)
        config = self.db.scalars(stmt).one_or_none()

        if config is None:
            raise RecordNotFoundException("Config", str(config_id))

        return config

    def get_config_by_mac(self, mac_address: str) -> Config:
        """Get config by MAC address.

        This method is primarily used by the ESP32 device raw endpoint.
        It accepts both colon-separated and dash-separated MAC formats
        for backward compatibility with existing devices.

        Args:
            mac_address: Device MAC address (colon or dash separated)

        Returns:
            Config model instance

        Raises:
            InvalidOperationException: If MAC address format is invalid
            RecordNotFoundException: If config for MAC does not exist
        """
        # Normalize MAC address (convert dash to colon, lowercase)
        mac_address = self.normalize_mac_address(mac_address)

        if not self.validate_mac_address(mac_address):
            raise InvalidOperationException(
                "get config", f"MAC address '{mac_address}' has invalid format"
            )

        stmt = select(Config).where(Config.mac_address == mac_address)
        config = self.db.scalars(stmt).one_or_none()

        if config is None:
            raise RecordNotFoundException("Config", mac_address)

        return config

    def get_raw_config(self, mac_address: str) -> dict[str, Any]:
        """Get raw JSON config content by MAC address.

        Used by ESP32 devices to fetch their configuration.

        Args:
            mac_address: Device MAC address (colon or dash separated)

        Returns:
            Parsed JSON content dict

        Raises:
            InvalidOperationException: If MAC address format is invalid
            RecordNotFoundException: If config for MAC does not exist
        """
        config = self.get_config_by_mac(mac_address)
        return json.loads(config.content)

    def create_config(self, mac_address: str, content: dict[str, Any]) -> Config:
        """Create a new device configuration.

        Args:
            mac_address: Device MAC address (colon-separated format)
            content: Configuration content as a dictionary

        Returns:
            Created Config model instance

        Raises:
            InvalidOperationException: If MAC address format is invalid
            RecordExistsException: If config for MAC already exists
        """
        # Normalize to lowercase before validation
        mac_address = self.normalize_mac_address(mac_address)

        if not self.validate_mac_address(mac_address):
            raise InvalidOperationException(
                "create config", f"MAC address '{mac_address}' has invalid format"
            )

        # Check if config already exists
        stmt = select(Config).where(Config.mac_address == mac_address)
        existing = self.db.scalars(stmt).one_or_none()

        if existing is not None:
            raise RecordExistsException("Config", mac_address)

        # Extract optional fields from content
        device_name = content.get("deviceName")
        device_entity_id = content.get("deviceEntityId")
        enable_ota = content.get("enableOTA")

        # Create new config
        config = Config(
            mac_address=mac_address,
            device_name=device_name,
            device_entity_id=device_entity_id,
            enable_ota=enable_ota,
            content=json.dumps(content),
        )

        self.db.add(config)
        self.db.flush()  # Get ID immediately

        return config

    def update_config(self, config_id: int, content: dict[str, Any]) -> Config:
        """Update an existing configuration by ID.

        Args:
            config_id: Config surrogate ID
            content: New configuration content

        Returns:
            Updated Config model instance

        Raises:
            RecordNotFoundException: If config with ID does not exist
        """
        config = self.get_config_by_id(config_id)

        # Extract optional fields from content
        config.device_name = content.get("deviceName")
        config.device_entity_id = content.get("deviceEntityId")
        config.enable_ota = content.get("enableOTA")
        config.content = json.dumps(content)

        self.db.flush()

        return config

    def delete_config(self, config_id: int) -> str:
        """Delete config by ID.

        Args:
            config_id: Config surrogate ID

        Returns:
            MAC address of deleted config (for MQTT notification)

        Raises:
            RecordNotFoundException: If config with ID does not exist
        """
        config = self.get_config_by_id(config_id)
        mac_address = config.mac_address

        self.db.delete(config)
        self.db.flush()

        return mac_address

    def count_configs(self) -> int:
        """Count total number of configs.

        Returns:
            Total count of configs in database
        """
        stmt = select(func.count()).select_from(Config)
        result = self.db.execute(stmt).scalar()
        return result or 0

    @staticmethod
    def normalize_mac_address(mac: str) -> str:
        """Normalize MAC address to lowercase colon-separated format.

        Accepts both dash-separated and colon-separated formats.

        Args:
            mac: MAC address string to normalize

        Returns:
            Lowercase colon-separated MAC address
        """
        # Convert to lowercase and replace dashes with colons
        return mac.lower().replace("-", ":")

    @staticmethod
    def validate_mac_address(mac: str) -> bool:
        """Validate MAC is lowercase, colon-separated format.

        Args:
            mac: MAC address string to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(MAC_ADDRESS_PATTERN.match(mac))
