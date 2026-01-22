"""Rotation schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RotationStatusSchema(BaseModel):
    """Response schema for rotation status."""

    counts_by_state: dict[str, int] = Field(
        ...,
        description="Count of devices in each rotation state",
        examples=[{"OK": 10, "QUEUED": 2, "PENDING": 1, "TIMEOUT": 0}],
    )
    pending_device_id: int | None = Field(
        None,
        description="ID of device currently being rotated (PENDING state)",
    )
    last_rotation_completed_at: datetime | None = Field(
        None,
        description="Timestamp of most recent rotation completion across all devices",
    )
    next_scheduled_rotation: str | None = Field(
        None,
        description="Next scheduled rotation time based on CRON expression",
    )


class RotationTriggerResponseSchema(BaseModel):
    """Response schema for manual rotation trigger."""

    queued_count: int = Field(
        ...,
        description="Number of devices queued for rotation",
    )


class RotationJobResultSchema(BaseModel):
    """Response schema for rotation job execution."""

    model_config = ConfigDict(from_attributes=True)

    processed_timeouts: int = Field(
        ...,
        description="Number of timed-out devices processed",
    )
    device_rotated: str | None = Field(
        None,
        description="Key of device that was rotated (if any)",
    )
    scheduled_rotation_triggered: bool = Field(
        ...,
        description="Whether CRON schedule triggered fleet-wide queueing",
    )
