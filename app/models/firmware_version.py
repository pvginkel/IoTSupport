"""FirmwareVersion model for tracking stored firmware versions per device model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.device_model import DeviceModel


class FirmwareVersion(db.Model):  # type: ignore[name-defined]
    """SQLAlchemy model for firmware version history.

    Tracks each firmware version stored in S3 per device model, enabling
    MAX_FIRMWARES retention and version enumeration. The DeviceModel.firmware_version
    column continues to represent the current/active version.
    """

    __tablename__ = "firmware_versions"

    # Surrogate primary key (auto-increment)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to device_models (required, cascade delete with model)
    device_model_id: Mapped[int] = mapped_column(
        ForeignKey("device_models.id", ondelete="CASCADE"), nullable=False
    )

    # Firmware version string (e.g., "1.2.3")
    version: Mapped[str] = mapped_column(String(50), nullable=False)

    # When the firmware was uploaded
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Standard timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Unique constraint: one version per model
    __table_args__ = (
        UniqueConstraint("device_model_id", "version", name="uq_firmware_versions_model_version"),
    )

    # Relationships
    device_model: Mapped[DeviceModel] = relationship(
        "DeviceModel", back_populates="firmware_versions", lazy="selectin"
    )

    def __repr__(self) -> str:
        """Return string representation of FirmwareVersion."""
        return (
            f"<FirmwareVersion(id={self.id}, device_model_id={self.device_model_id}, "
            f"version='{self.version}')>"
        )
