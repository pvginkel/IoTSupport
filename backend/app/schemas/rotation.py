"""Rotation schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RotationStatusSchema(BaseModel):
    """Response schema for rotation status."""

    counts_by_state: dict[str, int] = Field(
        ...,
        description="Count of devices in each rotation state (includes both active and inactive devices)",
        examples=[{"OK": 10, "QUEUED": 2, "PENDING": 1, "TIMEOUT": 0}],
    )
    inactive: int = Field(
        ...,
        description="Count of devices with active=False (orthogonal to rotation state)",
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


class DashboardDeviceSchema(BaseModel):
    """Device summary for dashboard display."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Device ID")
    key: str = Field(..., description="Unique 8-character device key")
    device_name: str | None = Field(None, description="Device name from config")
    device_model_code: str = Field(..., description="Device model code")
    active: bool = Field(..., description="Whether device participates in automatic fleet rotation")
    rotation_state: str = Field(..., description="Current rotation state")
    last_rotation_completed_at: datetime | None = Field(
        None, description="When last rotation completed"
    )
    days_since_rotation: int | None = Field(
        None, description="Days since last completed rotation"
    )


class DashboardResponseSchema(BaseModel):
    """Response schema for devices dashboard."""

    healthy: list[DashboardDeviceSchema] = Field(
        ...,
        description="Devices in healthy state (OK, QUEUED, PENDING)",
    )
    warning: list[DashboardDeviceSchema] = Field(
        ...,
        description="Devices in warning state (TIMEOUT, under critical threshold)",
    )
    critical: list[DashboardDeviceSchema] = Field(
        ...,
        description="Devices in critical state (TIMEOUT, over critical threshold)",
    )
    inactive: list[DashboardDeviceSchema] = Field(
        ...,
        description="Devices with active=False, excluded from rotation",
    )
    counts: dict[str, int] = Field(
        ...,
        description="Count of devices in each category",
        examples=[{"healthy": 10, "warning": 2, "critical": 1, "inactive": 0}],
    )
