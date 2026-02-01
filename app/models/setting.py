"""Setting model for persistent key-value storage."""

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import db


class Setting(db.Model):  # type: ignore[name-defined]
    """Key-value setting storage for application state.

    Used for storing persistent application state like rotation job timestamps.
    Keys are uppercase like environment variables (e.g., LAST_SCHEDULED_AT).
    This table will later support UI-configurable settings.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Setting key={self.key}>"
