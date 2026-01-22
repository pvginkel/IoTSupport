"""Settings service for persistent key-value storage."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.setting import Setting

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing persistent application settings.

    Provides simple get/set interface for key-value settings stored in the database.
    Keys are uppercase like environment variables.
    Settings do not need to pre-exist - get() returns the default if not found.
    """

    def __init__(self, db: Session) -> None:
        """Initialize settings service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a setting value.

        Args:
            key: Setting key (will be uppercased)
            default: Default value if setting doesn't exist

        Returns:
            Setting value or default
        """
        key = key.upper()
        stmt = select(Setting).where(Setting.key == key)
        setting = self.db.scalars(stmt).first()

        if setting is None:
            return default

        return setting.value

    def set(self, key: str, value: str) -> None:
        """Set a setting value.

        Creates the setting if it doesn't exist, updates if it does.

        Args:
            key: Setting key (will be uppercased)
            value: Setting value
        """
        key = key.upper()
        stmt = select(Setting).where(Setting.key == key)
        setting = self.db.scalars(stmt).first()

        if setting is None:
            setting = Setting(key=key, value=value)
            self.db.add(setting)
            logger.debug("Created setting %s", key)
        else:
            setting.value = value
            logger.debug("Updated setting %s", key)

        self.db.flush()

    def delete(self, key: str) -> bool:
        """Delete a setting.

        Args:
            key: Setting key (will be uppercased)

        Returns:
            True if setting was deleted, False if it didn't exist
        """
        key = key.upper()
        stmt = select(Setting).where(Setting.key == key)
        setting = self.db.scalars(stmt).first()

        if setting is None:
            return False

        self.db.delete(setting)
        self.db.flush()
        logger.debug("Deleted setting %s", key)
        return True
