"""Device model for IoT device instances."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.coredump import CoreDump
    from app.models.device_model import DeviceModel


class RotationState(StrEnum):
    """Rotation state machine states.

    OK: Device is operating normally, secret is valid
    QUEUED: Device is scheduled for rotation (awaiting its turn)
    PENDING: Rotation in progress, device has been notified
    TIMEOUT: Device failed to complete rotation within timeout
    """

    OK = "OK"
    QUEUED = "QUEUED"
    PENDING = "PENDING"
    TIMEOUT = "TIMEOUT"


class Device(db.Model):  # type: ignore[name-defined]
    """SQLAlchemy model for provisioned IoT devices.

    Each device is identified by a unique 8-character key (lowercase alphanumeric)
    and is associated with a DeviceModel. The device has a JSON configuration
    and tracks its rotation state for credential management.
    """

    __tablename__ = "devices"

    # Surrogate primary key (auto-increment)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Device key (unique, 8 chars, pattern [a-z0-9])
    key: Mapped[str] = mapped_column(
        String(8), unique=True, nullable=False, index=True
    )

    # Foreign key to device model (required)
    device_model_id: Mapped[int] = mapped_column(
        ForeignKey("device_models.id", ondelete="CASCADE"), nullable=False
    )

    # JSON configuration content (stored as text)
    config: Mapped[str] = mapped_column(Text, nullable=False)

    # Fields extracted from config for display purposes
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enable_ota: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Rotation state machine
    rotation_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RotationState.OK.value
    )

    # Cached secret for timeout recovery (encrypted with Fernet)
    # Set when rotation starts, cleared when rotation completes or timeout handled
    cached_secret: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Rotation timestamps
    secret_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_rotation_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    last_rotation_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    device_model: Mapped[DeviceModel] = relationship(
        "DeviceModel", back_populates="devices", lazy="selectin"
    )
    coredumps: Mapped[list[CoreDump]] = relationship(
        "CoreDump",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="select",
    )

    @property
    def last_coredump_at(self) -> datetime | None:
        """Timestamp of the most recent coredump, or None."""
        if not self.coredumps:
            return None
        return max(c.uploaded_at for c in self.coredumps)

    @property
    def client_id(self) -> str:
        """Keycloak client ID derived from model code and device key."""
        return f"iotdevice-{self.device_model.code}-{self.key}"

    @property
    def rotation_state_enum(self) -> RotationState:
        """Get rotation state as enum."""
        return RotationState(self.rotation_state)

    def __repr__(self) -> str:
        """Return string representation of Device."""
        return f"<Device(id={self.id}, key='{self.key}', model='{self.device_model.code if self.device_model else 'N/A'}')>"
