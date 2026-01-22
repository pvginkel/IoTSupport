"""Service for loading test data into the database."""

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.config import Config

logger = logging.getLogger(__name__)

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

    def load_configs(self) -> int:
        """Load configuration test data from configs.json.

        Returns:
            Number of configs loaded
        """
        configs_file = TEST_DATA_DIR / "configs.json"

        if not configs_file.exists():
            logger.warning(f"Test data file not found: {configs_file}")
            return 0

        with open(configs_file, encoding="utf-8") as f:
            data = json.load(f)

        configs_data: list[dict[str, Any]] = data.get("configs", [])
        loaded_count = 0

        for config_data in configs_data:
            mac_address = config_data.get("mac_address")
            content = config_data.get("content", {})

            if not mac_address:
                logger.warning("Skipping config without mac_address")
                continue

            # Extract fields from content
            device_name = content.get("deviceName")
            device_entity_id = content.get("deviceEntityId")
            enable_ota = content.get("enableOTA")

            # Create config
            config = Config(
                mac_address=mac_address,
                device_name=device_name,
                device_entity_id=device_entity_id,
                enable_ota=enable_ota,
                content=json.dumps(content),
            )

            self.db.add(config)
            loaded_count += 1

        self.db.flush()
        logger.info(f"Loaded {loaded_count} configs from test data")

        return loaded_count

    def clear_all_data(self) -> None:
        """Clear all data from the database.

        Used for test setup to ensure a clean state.
        """
        # Delete all configs
        self.db.query(Config).delete()
        self.db.flush()
        logger.info("Cleared all data from database")
