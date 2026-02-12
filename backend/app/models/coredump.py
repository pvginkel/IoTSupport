"""CoreDump model for ESP32 device crash dumps."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if False:  # TYPE_CHECKING
    from app.models.device import Device


class ParseStatus(str, Enum):
    """Parse status for coredump analysis.

    PENDING: Coredump uploaded, awaiting parsing (or sidecar not configured)
    PARSED: Successfully parsed by sidecar
    ERROR: Parsing failed after retries
    """

    PENDING = "PENDING"
    PARSED = "PARSED"
    ERROR = "ERROR"


class CoreDump(db.Model):  # type: ignore[name-defined]
    """SQLAlchemy model for ESP32 coredump records.

    Each coredump is associated with a device and stores metadata about
    the crash dump binary, along with parsed output from the sidecar.
    The binary .dmp file is stored on the filesystem under
    COREDUMPS_DIR/{device_key}/.
    """

    __tablename__ = "coredumps"

    # Surrogate primary key (auto-increment)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to device (required, cascade delete with device)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )

    # Filename of the .dmp file on disk (e.g., coredump_20260211T143000_123456Z.dmp)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    # Chip type (e.g., esp32, esp32s3)
    chip: Mapped[str] = mapped_column(String(50), nullable=False)

    # Firmware version at time of crash
    firmware_version: Mapped[str] = mapped_column(String(50), nullable=False)

    # Size of the coredump binary in bytes
    size: Mapped[int] = mapped_column(Integer, nullable=False)

    # Parse status: PENDING, PARSED, or ERROR (stored as text, not native enum)
    parse_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ParseStatus.PENDING.value
    )

    # Parsed output from sidecar (populated after successful parse)
    parsed_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When the coredump was uploaded by the device
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # When parsing completed (success or final error)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Standard timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    device: Mapped["Device"] = relationship(
        "Device", back_populates="coredumps", lazy="selectin"
    )

    def __repr__(self) -> str:
        """Return string representation of CoreDump."""
        return (
            f"<CoreDump(id={self.id}, device_id={self.device_id}, "
            f"filename='{self.filename}', status='{self.parse_status}')>"
        )
