"""Device logs schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeviceLogsQuerySchema(BaseModel):
    """Query parameters for device logs request."""

    start: datetime | None = Field(
        default=None,
        description="Start of time range (ISO datetime). Defaults to 1 hour ago.",
        examples=["2026-02-01T14:00:00Z"],
    )
    end: datetime | None = Field(
        default=None,
        description="End of time range (ISO datetime). Defaults to now.",
        examples=["2026-02-01T15:00:00Z"],
    )
    query: str | None = Field(
        default=None,
        description="Wildcard search pattern for message field (Elasticsearch wildcard syntax).",
        examples=["error*", "*timeout*"],
    )


class LogEntrySchema(BaseModel):
    """Schema for a single log entry."""

    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime = Field(
        ...,
        description="Log entry timestamp",
        examples=["2026-02-01T14:43:27.948Z"],
    )
    message: str = Field(
        ...,
        description="Log message content",
        examples=["Device started successfully"],
    )


class DeviceLogsResponseSchema(BaseModel):
    """Response schema for device logs."""

    logs: list[LogEntrySchema] = Field(
        ...,
        description="List of log entries sorted by timestamp ascending",
    )
    has_more: bool = Field(
        ...,
        description="True if more results exist beyond the returned set (max 1000 per request)",
    )
    window_start: datetime | None = Field(
        None,
        description="Timestamp of first returned log entry (null if no logs)",
        examples=["2026-02-01T14:40:00.000Z"],
    )
    window_end: datetime | None = Field(
        None,
        description="Timestamp of last returned log entry (null if no logs)",
        examples=["2026-02-01T14:43:27.948Z"],
    )
