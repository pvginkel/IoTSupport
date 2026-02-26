"""Service for loading test data into the database."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import dateparser
from sqlalchemy.orm import Session

from app.models.device import Device, RotationState
from app.models.device_model import DeviceModel

logger = logging.getLogger(__name__)


def _parse_relative_date(date_str: str | None) -> datetime | None:
    """Parse a natural language date string relative to now.

    Args:
        date_str: Natural language date like "2 weeks ago", "1 day ago"

    Returns:
        Parsed datetime or None if parsing fails or date_str is None
    """
    if date_str is None:
        return None

    result = dateparser.parse(
        date_str,
        settings={"RELATIVE_BASE": datetime.utcnow()}
    )

    if result is None:
        logger.warning(f"Failed to parse date string: {date_str}")

    return result

# Path to test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "data" / "test_data"


class TestDataService:
    """Service for loading test data from JSON files."""

    def __init__(self, db: Session):
        """Initialize service with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def load_device_models(self) -> int:
        """Load device model test data from device_models.json.

        Returns:
            Number of device models loaded
        """
        models_file = TEST_DATA_DIR / "device_models.json"

        if not models_file.exists():
            logger.warning(f"Test data file not found: {models_file}")
            return 0

        with open(models_file, encoding="utf-8") as f:
            data = json.load(f)

        models_data: list[dict[str, Any]] = data.get("device_models", [])
        loaded_count = 0

        for model_data in models_data:
            code = model_data.get("code")
            name = model_data.get("name")
            firmware_version = model_data.get("firmware_version")
            config_schema_obj = model_data.get("config_schema")

            if not code or not name:
                logger.warning("Skipping device model without code or name")
                continue

            # Convert config_schema object to JSON string if present
            config_schema: str | None = None
            if config_schema_obj is not None:
                config_schema = json.dumps(config_schema_obj)

            model = DeviceModel(
                code=code,
                name=name,
                firmware_version=firmware_version,
                config_schema=config_schema,
            )

            self.db.add(model)
            loaded_count += 1

        self.db.flush()
        logger.info(f"Loaded {loaded_count} device models from test data")

        return loaded_count

    def load_devices(self) -> int:
        """Load device test data from devices.json.

        Requires device models to be loaded first.

        Returns:
            Number of devices loaded
        """
        devices_file = TEST_DATA_DIR / "devices.json"

        if not devices_file.exists():
            logger.warning(f"Test data file not found: {devices_file}")
            return 0

        with open(devices_file, encoding="utf-8") as f:
            data = json.load(f)

        devices_data: list[dict[str, Any]] = data.get("devices", [])
        loaded_count = 0

        # Build model code to ID mapping
        from sqlalchemy import select
        stmt = select(DeviceModel)
        models = {m.code: m.id for m in self.db.scalars(stmt).all()}

        for device_data in devices_data:
            key = device_data.get("key")
            model_code = device_data.get("model_code")
            config = device_data.get("config", {})
            rotation_state = device_data.get("rotation_state", RotationState.OK.value)

            if not key or not model_code:
                logger.warning("Skipping device without key or model_code")
                continue

            model_id = models.get(model_code)
            if model_id is None:
                logger.warning(f"Skipping device {key}: unknown model_code {model_code}")
                continue

            # Parse optional date fields (natural language relative dates)
            last_rotation_completed_at = _parse_relative_date(
                device_data.get("last_rotation_completed_at")
            )
            last_rotation_attempt_at = _parse_relative_date(
                device_data.get("last_rotation_attempt_at")
            )
            secret_created_at = _parse_relative_date(
                device_data.get("secret_created_at")
            )

            # Extract entity fields from config
            device_name = config.get("deviceName")
            device_entity_id = config.get("deviceEntityId")
            enable_ota = config.get("enableOTA")

            # Active flag defaults to True if not specified
            active = device_data.get("active", True)

            device = Device(
                key=key,
                device_model_id=model_id,
                config=json.dumps(config),
                active=active,
                rotation_state=rotation_state,
                last_rotation_completed_at=last_rotation_completed_at,
                last_rotation_attempt_at=last_rotation_attempt_at,
                secret_created_at=secret_created_at,
                device_name=device_name,
                device_entity_id=device_entity_id,
                enable_ota=enable_ota,
            )

            self.db.add(device)
            loaded_count += 1

        self.db.flush()
        logger.info(f"Loaded {loaded_count} devices from test data")

        return loaded_count

    def load_all(self) -> dict[str, int]:
        """Load all test data in proper order.

        Returns:
            Dict with counts for each entity type
        """
        counts = {
            "device_models": self.load_device_models(),
            "devices": self.load_devices(),
        }
        return counts

    def clear_all_data(self) -> None:
        """Clear all data from the database.

        Used for test setup to ensure a clean state.
        """
        # Delete in reverse dependency order
        self.db.query(Device).delete()
        self.db.query(DeviceModel).delete()
        self.db.flush()
        logger.info("Cleared all data from database")
