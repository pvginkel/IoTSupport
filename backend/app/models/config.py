"""Config model for device configurations."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Config(db.Model):  # type: ignore[name-defined]
    """SQLAlchemy model for device configurations.

    Each configuration represents a single IoT device identified by its MAC address.
    The content field stores the full JSON configuration as text, while commonly
    accessed fields are extracted and stored as columns for efficient querying.
    """

    __tablename__ = "configs"

    # Surrogate primary key (auto-increment)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # MAC address (unique, colon-separated format: aa:bb:cc:dd:ee:ff)
    # The index=True creates an index named ix_configs_mac_address automatically
    mac_address: Mapped[str] = mapped_column(
        String(17), unique=True, nullable=False, index=True
    )

    # Extracted fields from content (nullable, for efficient querying)
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enable_ota: Mapped[bool | None] = mapped_column(nullable=True)

    # Full JSON configuration content stored as text
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """Return string representation of Config."""
        return f"<Config(id={self.id}, mac_address='{self.mac_address}', device_name='{self.device_name}')>"
