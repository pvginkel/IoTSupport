"""DeviceModel model for device hardware types."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if False:  # TYPE_CHECKING
    from app.models.device import Device


class DeviceModel(db.Model):  # type: ignore[name-defined]
    """SQLAlchemy model for device hardware types.

    A DeviceModel represents a category of hardware (e.g., thermostat, sensor)
    that can have multiple devices provisioned. Each model has firmware that
    can be uploaded and distributed to devices of that type.
    """

    __tablename__ = "device_models"

    # Surrogate primary key (auto-increment)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Model code (unique, immutable, lowercase alphanumeric with underscores)
    # Pattern: [a-z0-9_]+, max 50 chars
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )

    # Human-readable model name
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Firmware version extracted from uploaded binary (nullable until firmware uploaded)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    devices: Mapped[list["Device"]] = relationship(
        "Device",
        back_populates="device_model",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def device_count(self) -> int:
        """Count of devices using this model."""
        return len(self.devices)

    def __repr__(self) -> str:
        """Return string representation of DeviceModel."""
        return f"<DeviceModel(id={self.id}, code='{self.code}', name='{self.name}')>"
